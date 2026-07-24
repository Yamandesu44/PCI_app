"""mykeibadbのレースラップ利用率を距離帯別に診断する。

RPCIの次世代特徴量へ前半3F・区間ラップを使う前に、対象日より前の履歴が
十分な割合で存在するかを確認する。JRA平地レースだけを対象とし、生データは
表示せず集計値だけを出力する。

使い方:
    python -m ingestion.diagnose_lap_coverage --date 20250701 --date-to 20260630
    python -m ingestion.diagnose_lap_coverage --date 20250701 --date-to 20260630 \
        --min-races 200 --min-coverage 0.8 --output lap_coverage.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ingestion.client.mykeibadb_client import (
    _DATA_KUBUN_COLUMNS,
    _DISTANCE_COLUMNS,
    _JRA_PLACE_CODES,
    _RA_TABLE_CANDIDATES,
    _RACE_L3F_COLUMNS,
    _RACE_S3F_COLUMNS,
    _TRACK_COLUMNS,
    MyKeibaDbClient,
    _jyo_cd_from_row,
    _pick,
    _race_key_from_row,
    _raw_record,
    _row_in_date_range,
    _str_or_none,
    _track_type,
)
from ingestion.parser.ra_parser import parse_ra

_LAP_COLUMNS = tuple(f"LAP_TIME{index}" for index in range(1, 26))
_DISTANCE_BANDS = (
    (0, 1399, "1399m以下"),
    (1400, 1799, "1400-1799m"),
    (1800, 2199, "1800-2199m"),
    (2200, 9999, "2200m以上"),
)


@dataclass
class LapCoverageBucket:
    """同一馬場種別・距離帯のラップ保有件数。"""

    track_type: str
    distance_band: str
    total: int = 0
    s3: int = 0
    l3: int = 0
    pair: int = 0
    any_intervals: int = 0
    complete_intervals: int = 0

    def rate(self, count: int) -> float:
        return count / self.total if self.total else 0.0

    def to_dict(self, min_races: int, min_coverage: float) -> dict[str, object]:
        return {
            "track_type": self.track_type,
            "distance_band": self.distance_band,
            "total": self.total,
            "s3": self.s3,
            "l3": self.l3,
            "pair": self.pair,
            "any_intervals": self.any_intervals,
            "complete_intervals": self.complete_intervals,
            "s3_l3_coverage": round(self.rate(self.pair), 4),
            "complete_interval_coverage": round(self.rate(self.complete_intervals), 4),
            "s3_l3_ready": self.total >= min_races
            and self.rate(self.pair) >= min_coverage,
            "interval_ready": self.total >= min_races
            and self.rate(self.complete_intervals) >= min_coverage,
        }


@dataclass(frozen=True)
class LapCoverageReport:
    """診断結果。JSON化できる集計値だけを保持する。"""

    date_from: str
    date_to: str
    table: str
    buckets: tuple[LapCoverageBucket, ...]
    duplicate_rows: int
    ignored_nonfinal: int
    ignored_non_jra_or_obstacle: int

    def to_dict(self, min_races: int, min_coverage: float) -> dict[str, object]:
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "table": self.table,
            "thresholds": {
                "min_races": min_races,
                "min_coverage": min_coverage,
            },
            "duplicate_rows": self.duplicate_rows,
            "ignored_nonfinal": self.ignored_nonfinal,
            "ignored_non_jra_or_obstacle": self.ignored_non_jra_or_obstacle,
            "buckets": [
                bucket.to_dict(min_races, min_coverage) for bucket in self.buckets
            ],
        }


@dataclass(frozen=True)
class _LapRow:
    race_key: str
    track_type: str
    distance_m: int
    s3: float | None
    l3: float | None
    interval_count: int
    complete_intervals: bool

    @property
    def quality(self) -> tuple[int, int]:
        return (int(self.s3 is not None) + int(self.l3 is not None), self.interval_count)


def diagnose(
    date_from: str,
    date_to: str,
    min_races: int,
    min_coverage: float,
    client: MyKeibaDbClient | None = None,
) -> LapCoverageReport:
    """指定期間の確定RAを集計し、結果を標準出力と戻り値で返す。"""
    _validate_inputs(date_from, date_to, min_races, min_coverage)
    client = client or MyKeibaDbClient()
    connection = client._connection or client._connect()
    table = client._find_table(connection, _RA_TABLE_CANDIDATES)

    by_race_key: dict[str, _LapRow] = {}
    duplicate_rows = 0
    ignored_nonfinal = 0
    ignored_non_jra_or_obstacle = 0

    for row in client._iter_table_by_date_range(connection, table, date_from, date_to):
        if not _row_in_date_range(row, date_from, date_to):
            continue
        data_kubun = _str_or_none(_pick(row, _DATA_KUBUN_COLUMNS))
        if data_kubun is not None and data_kubun != "7":
            ignored_nonfinal += 1
            continue
        parsed = _lap_row(row)
        if parsed is None:
            ignored_non_jra_or_obstacle += 1
            continue
        current = by_race_key.get(parsed.race_key)
        if current is not None:
            duplicate_rows += 1
            if parsed.quality <= current.quality:
                continue
        by_race_key[parsed.race_key] = parsed

    buckets: dict[tuple[str, str], LapCoverageBucket] = {}
    for lap_row in by_race_key.values():
        key = (lap_row.track_type, _distance_band(lap_row.distance_m))
        bucket = buckets.setdefault(key, LapCoverageBucket(*key))
        bucket.total += 1
        bucket.s3 += int(lap_row.s3 is not None)
        bucket.l3 += int(lap_row.l3 is not None)
        bucket.pair += int(lap_row.s3 is not None and lap_row.l3 is not None)
        bucket.any_intervals += int(lap_row.interval_count > 0)
        bucket.complete_intervals += int(lap_row.complete_intervals)

    report = LapCoverageReport(
        date_from=date_from,
        date_to=date_to,
        table=table,
        buckets=tuple(
            sorted(
                buckets.values(),
                key=lambda item: (item.track_type, _band_order(item.distance_band)),
            )
        ),
        duplicate_rows=duplicate_rows,
        ignored_nonfinal=ignored_nonfinal,
        ignored_non_jra_or_obstacle=ignored_non_jra_or_obstacle,
    )
    _print_report(report, min_races, min_coverage)
    return report


def _lap_row(row: dict[str, Any]) -> _LapRow | None:
    raw = _raw_record(row)
    if raw is not None:
        try:
            race = parse_ra(raw)
        except (ValueError, UnicodeError):
            return None
        if race is None or race.jyo_cd not in _JRA_PLACE_CODES or race.track_type == "障害":
            return None
        race_key = race.race_key
        track_type = race.track_type
        distance_m = race.distance_m
        s3 = race.race_s3f
        l3 = race.race_l3f
    else:
        try:
            jyo_cd = _jyo_cd_from_row(row)
            race_key = _race_key_from_row(row)
        except RuntimeError:
            return None
        track_type = _track_type(_pick(row, _TRACK_COLUMNS))
        parsed_distance = _positive_int(_pick(row, _DISTANCE_COLUMNS))
        if (
            jyo_cd not in _JRA_PLACE_CODES
            or track_type == "障害"
            or parsed_distance is None
            or race_key[10:14] == "0000"
        ):
            return None
        distance_m = parsed_distance
        s3 = _seconds(_pick(row, _RACE_S3F_COLUMNS), 25.0, 50.0)
        l3 = _seconds(_pick(row, _RACE_L3F_COLUMNS), 25.0, 50.0)

    if distance_m <= 0:
        return None
    interval_values = [
        _seconds(_pick(row, (column, column.lower())), 5.0, 30.0)
        for column in _LAP_COLUMNS
    ]
    expected = math.ceil(distance_m / 200)
    return _LapRow(
        race_key=race_key,
        track_type=track_type,
        distance_m=distance_m,
        s3=s3,
        l3=l3,
        interval_count=sum(value is not None for value in interval_values),
        complete_intervals=all(
            value is not None for value in interval_values[:expected]
        ),
    )


def _seconds(value: Any, minimum: float, maximum: float) -> float | None:
    text = _str_or_none(value)
    if not text:
        return None
    try:
        seconds = float(text.replace(",", ""))
    except ValueError:
        return None
    if seconds >= 100:
        seconds /= 10.0
    return seconds if minimum <= seconds <= maximum else None


def _positive_int(value: Any) -> int | None:
    text = _str_or_none(value)
    if not text:
        return None
    try:
        result = int(float(text.replace(",", "")))
    except ValueError:
        return None
    return result if result > 0 else None


def _distance_band(distance_m: int) -> str:
    for lower, upper, label in _DISTANCE_BANDS:
        if lower <= distance_m <= upper:
            return label
    raise ValueError(f"距離帯を特定できません: {distance_m}")


def _band_order(label: str) -> int:
    labels = [item[2] for item in _DISTANCE_BANDS]
    return labels.index(label)


def _validate_inputs(
    date_from: str,
    date_to: str,
    min_races: int,
    min_coverage: float,
) -> None:
    for value in (date_from, date_to):
        datetime.datetime.strptime(value, "%Y%m%d")
    if date_from > date_to:
        raise ValueError("開始日は終了日以前にしてください")
    if min_races < 1:
        raise ValueError("min_racesは1以上にしてください")
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverageは0以上1以下にしてください")


def _print_report(
    report: LapCoverageReport,
    min_races: int,
    min_coverage: float,
) -> None:
    print("===== mykeibadb ラップ利用率診断 =====")
    print(f"対象期間: {report.date_from}→{report.date_to} / RAテーブル: {report.table}")
    print(
        f"判定条件: 最低{min_races}レース、カバー率{min_coverage:.0%} "
        "（診断用の可変条件）"
    )
    print(
        f"重複行: {report.duplicate_rows} / 確定前行除外: {report.ignored_nonfinal} / "
        f"JRA平地外・解析不能除外: {report.ignored_non_jra_or_obstacle}"
    )
    if not report.buckets:
        print("対象となる確定済みJRA平地レースがありません。")
        return

    print("\n馬場     距離帯          件数   S3+L3       区間完全     v4候補")
    for bucket in report.buckets:
        pair_ready = bucket.total >= min_races and bucket.rate(bucket.pair) >= min_coverage
        interval_ready = (
            bucket.total >= min_races
            and bucket.rate(bucket.complete_intervals) >= min_coverage
        )
        if interval_ready:
            readiness = "区間ラップ可"
        elif pair_ready:
            readiness = "3Fペア可"
        else:
            readiness = "保留"
        print(
            f"{bucket.track_type:<8} {bucket.distance_band:<13} {bucket.total:>5} "
            f"{bucket.pair:>5} ({bucket.rate(bucket.pair):>6.1%}) "
            f"{bucket.complete_intervals:>5} "
            f"({bucket.rate(bucket.complete_intervals):>6.1%}) {readiness}"
        )


def main() -> None:
    load_dotenv()
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=(today - datetime.timedelta(days=365)).strftime("%Y%m%d"),
        help="診断開始日 YYYYMMDD（既定: 365日前）",
    )
    parser.add_argument(
        "--date-to",
        default=(today - datetime.timedelta(days=1)).strftime("%Y%m%d"),
        help="診断終了日 YYYYMMDD（既定: 昨日）",
    )
    parser.add_argument(
        "--min-races",
        type=int,
        default=200,
        help="候補判定に必要な距離帯ごとの最低レース数（既定: 200）",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        help="候補判定に必要な最低カバー率 0〜1（既定: 0.8）",
    )
    parser.add_argument(
        "--output",
        help="集計JSONの保存先。生ラップ値は含まない",
    )
    args = parser.parse_args()
    report = diagnose(args.date, args.date_to, args.min_races, args.min_coverage)
    if args.output:
        payload = report.to_dict(args.min_races, args.min_coverage)
        Path(args.output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSONを保存しました: {args.output}")


if __name__ == "__main__":
    main()
