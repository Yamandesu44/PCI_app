"""実JV-LinkのSEとmykeibadbを照合し、人気・本賞金の位置候補を診断する。"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ingestion.client.mykeibadb_client import MyKeibaDbConfig
from ingestion.client.windows_client import WindowsJvLinkClient

_POPULARITY_RESERVED = (541, 543)
_PRIZE_RESERVED = (543, 552)


@dataclass(frozen=True)
class ResultSample:
    """同一馬について照合できた実SEとmykeibadbの期待値。"""

    raw: bytes
    finish_pos: int
    popularity: int
    prize_money: int


@dataclass(frozen=True, order=True)
class NumericCandidate:
    """複数レコードで同じ意味の数値が現れるバイト位置候補。"""

    offset: int
    width: int
    scale: int
    padding: str


def _sample_value(sample: ResultSample, field: str) -> int:
    if field == "finish_pos":
        return sample.finish_pos
    if field == "popularity":
        return sample.popularity
    return sample.prize_money


def find_numeric_candidates(
    raw: bytes,
    value: int,
    *,
    widths: range,
    scales: tuple[int, ...] = (1,),
) -> set[NumericCandidate]:
    """数値のゼロ埋め表現を走査し、位置・幅・単位の候補を返す。"""
    candidates: set[NumericCandidate] = set()
    for scale in scales:
        if value <= 0 or value % scale != 0:
            continue
        digits = str(value // scale)
        for width in widths:
            if len(digits) > width:
                continue
            forms = (
                ((digits if len(digits) == width else digits.zfill(width)), "zero"),
                (digits.rjust(width), "space-left"),
                (digits.ljust(width), "space-right"),
            )
            seen: set[bytes] = set()
            for text, padding in forms:
                needle = text.encode("ascii")
                if needle in seen:
                    continue
                seen.add(needle)
                start = 0
                while True:
                    offset = raw.find(needle, start)
                    if offset < 0:
                        break
                    candidates.add(NumericCandidate(offset, width, scale, padding))
                    start = offset + 1
    return candidates


def common_numeric_candidates(
    samples: list[ResultSample],
    *,
    field: str,
    widths: range,
    scales: tuple[int, ...] = (1,),
) -> set[NumericCandidate]:
    """全サンプルで共通する数値位置候補を求める。"""
    common: set[NumericCandidate] | None = None
    for sample in samples:
        value = _sample_value(sample, field)
        found = find_numeric_candidates(sample.raw, value, widths=widths, scales=scales)
        common = found if common is None else common & found
        if not common:
            return set()
    return common or set()


def supported_numeric_candidates(
    samples: list[ResultSample],
    *,
    field: str,
    widths: range,
    scales: tuple[int, ...] = (1,),
    minimum_ratio: float = 0.8,
) -> list[tuple[NumericCandidate, int]]:
    """一定割合以上のサンプルで一致した位置候補を支持件数順に返す。"""
    counts: Counter[NumericCandidate] = Counter()
    for sample in samples:
        value = _sample_value(sample, field)
        counts.update(find_numeric_candidates(sample.raw, value, widths=widths, scales=scales))
    minimum = max(1, int(len(samples) * minimum_ratio + 0.999999))
    supported = [(candidate, count) for candidate, count in counts.items() if count >= minimum]
    return sorted(supported, key=lambda item: (-item[1], item[0]))


def reserved_match_count(
    samples: list[ResultSample], field: str, start: int, end: int
) -> int:
    """既存の合成専用予約位置が期待値と一致する件数を返す。"""
    matches = 0
    for sample in samples:
        value = _sample_value(sample, field)
        text = sample.raw[start:end].decode("ascii", errors="ignore").strip()
        if text.isdigit() and int(text) == value:
            matches += 1
    return matches


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _reference_key(row: dict[str, Any]) -> tuple[str, int] | None:
    race_key = str(row.get("RACE_CODE") or row.get("race_key") or "").strip()
    horse_no = _positive_int(row.get("UMABAN") or row.get("horse_no"))
    if len(race_key) != 16 or not race_key.isdigit() or horse_no is None:
        return None
    return race_key, horse_no


def _load_references(
    config: MyKeibaDbConfig, date_from: str, date_to: str
) -> dict[tuple[str, int], tuple[int, int, int]]:
    try:
        import pymysql  # type: ignore[import-untyped]
        from pymysql.cursors import DictCursor  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("診断にはPyMySQLが必要です。") from exc

    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset=config.charset,
        cursorclass=DictCursor,
    )
    try:
        sql = """
            SELECT RACE_CODE, UMABAN, KAKUTEI_CHAKUJUN,
                   TANSHO_NINKIJUN, KAKUTOKU_HONSHOKIN
              FROM umagoto_race_joho
             WHERE CAST(CONCAT(KAISAI_NEN, LPAD(KAISAI_GAPPI, 4, '0')) AS UNSIGNED)
                   BETWEEN %s AND %s
               AND DATA_KUBUN IN ('4', '7')
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, (int(date_from), int(date_to)))
            rows = cursor.fetchall()
    finally:
        connection.close()

    references: dict[tuple[str, int], tuple[int, int, int]] = {}
    for row in rows:
        key = _reference_key(row)
        finish_pos = _positive_int(row.get("KAKUTEI_CHAKUJUN"))
        popularity = _positive_int(row.get("TANSHO_NINKIJUN"))
        prize = _positive_int(row.get("KAKUTOKU_HONSHOKIN"))
        if (
            key is not None
            and finish_pos is not None
            and popularity is not None
            and prize is not None
        ):
            references[key] = (finish_pos, popularity, prize)
    return references


def save_references(
    path: Path, references: dict[tuple[str, int], tuple[int, int, int]]
) -> None:
    """32bit COM診断へ渡す最小限の照合値をJSONへ保存する。"""
    rows = [
        {
            "race_key": race_key,
            "horse_no": horse_no,
            "finish_pos": finish_pos,
            "popularity": popularity,
            "prize_money": prize,
        }
        for (race_key, horse_no), (finish_pos, popularity, prize) in sorted(references.items())
    ]
    path.write_text(json.dumps(rows, ensure_ascii=True), encoding="utf-8")


def load_references(path: Path) -> dict[tuple[str, int], tuple[int, int, int]]:
    """一時JSONから照合値を読み、形式不正を早期に拒否する。"""
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("照合JSONのルートは配列である必要があります。")
    references: dict[tuple[str, int], tuple[int, int, int]] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("照合JSONの各要素はオブジェクトである必要があります。")
        key = _reference_key(row)
        finish_pos = _positive_int(row.get("finish_pos"))
        popularity = _positive_int(row.get("popularity"))
        prize = _positive_int(row.get("prize_money"))
        if key is None or finish_pos is None or popularity is None or prize is None:
            raise ValueError("照合JSONに不正なレースキー、馬番、着順、人気、本賞金があります。")
        references[key] = (finish_pos, popularity, prize)
    return references


def _raw_key(record: str) -> tuple[str, int] | None:
    if record[:2] != "SE" or record[2:3] not in {"4", "7"}:
        return None
    horse_no = _positive_int(record[28:30])
    race_key = record[11:27]
    if horse_no is None or len(race_key) != 16 or not race_key.isdigit():
        return None
    return race_key, horse_no


def _format_candidates(candidates: set[NumericCandidate]) -> str:
    if not candidates:
        return "候補なし"
    return ", ".join(
        f"[{item.offset}:{item.offset + item.width}] / 単位={item.scale} / {item.padding}"
        for item in sorted(candidates)
    )


def _format_supported(candidates: list[tuple[NumericCandidate, int]], total: int) -> str:
    if not candidates:
        return "候補なし"
    return ", ".join(
        f"[{item.offset}:{item.offset + item.width}] / 単位={item.scale} / "
        f"{item.padding} / {count}/{total}"
        for item, count in candidates[:10]
    )


def _load_environment() -> None:
    """通常実行とworktree越しの診断の双方でworkerの.envを読む。"""
    candidates = (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env")
    for path in candidates:
        if path.is_file():
            load_dotenv(path)
            return
    load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="実JV-Link SEの人気・本賞金位置をmykeibadbと照合します。"
    )
    parser.add_argument("--date", required=True, help="開始日 YYYYMMDD")
    parser.add_argument("--date-to", required=True, help="終了日 YYYYMMDD")
    parser.add_argument("--race-option", type=int, default=1, choices=(1, 2, 3, 4))
    parser.add_argument("--max-samples", type=int, default=50)
    parser.add_argument("--reference-file", type=Path, help="32bit COM診断用の照合JSON")
    parser.add_argument(
        "--export-references",
        type=Path,
        help="mykeibadbの最小照合値をJSONへ出力して終了",
    )
    args = parser.parse_args()

    _load_environment()
    references = (
        load_references(args.reference_file)
        if args.reference_file
        else _load_references(MyKeibaDbConfig.from_env(), args.date, args.date_to)
    )
    if not references:
        raise RuntimeError("指定期間のmykeibadbに照合可能な確定成績がありません。")
    if args.export_references:
        save_references(args.export_references, references)
        print(f"照合値{len(references)}件を保存しました: {args.export_references}")
        return

    sid = os.environ.get("JV_LINK_SID", "")
    client = WindowsJvLinkClient(sid=sid)
    matched_records: dict[tuple[str, int], str] = {}
    with contextlib.closing(
        client.iter_race_records_raw(args.date, args.date_to, option=args.race_option)
    ) as records:
        for record in records:
            key = _raw_key(record)
            if key is None or key not in references:
                continue
            current = matched_records.get(key)
            if current is None or (current[2:3] != "7" and record[2:3] == "7"):
                matched_records[key] = record

    samples: list[ResultSample] = []
    for key, record in sorted(matched_records.items())[: args.max_samples]:
        finish_pos, popularity, prize = references[key]
        raw = record.encode("cp932", errors="replace")
        samples.append(ResultSample(raw, finish_pos, popularity, prize))

    if len(samples) < 3:
        raise RuntimeError(f"照合できた実SEが{len(samples)}件です。3件以上必要です。")

    popularity_candidates = common_numeric_candidates(
        samples, field="popularity", widths=range(1, 4)
    )
    finish_candidates = common_numeric_candidates(
        samples, field="finish_pos", widths=range(1, 4)
    )
    prize_candidates = common_numeric_candidates(
        samples,
        field="prize_money",
        widths=range(1, 11),
        scales=(1, 100, 1000),
    )
    popularity_supported = supported_numeric_candidates(
        samples, field="popularity", widths=range(1, 4)
    )
    finish_supported = supported_numeric_candidates(
        samples, field="finish_pos", widths=range(1, 4)
    )
    prize_supported = supported_numeric_candidates(
        samples,
        field="prize_money",
        widths=range(1, 11),
        scales=(1, 100, 1000),
    )
    pop_reserved = reserved_match_count(samples, "popularity", *_POPULARITY_RESERVED)
    prize_reserved = reserved_match_count(samples, "prize_money", *_PRIZE_RESERVED)
    finish_matches = reserved_match_count(samples, "finish_pos", 334, 336)

    print("===== 実JV-Data 人気・本賞金オフセット診断 =====")
    print(f"照合件数: {len(samples)}")
    print(f"対応確認（確定着順[334:336]）: {finish_matches}/{len(samples)}")
    print(
        f"合成予約の人気[{_POPULARITY_RESERVED[0]}:{_POPULARITY_RESERVED[1]}]一致: "
        f"{pop_reserved}/{len(samples)}"
    )
    print(
        f"合成予約の本賞金[{_PRIZE_RESERVED[0]}:{_PRIZE_RESERVED[1]}]一致: "
        f"{prize_reserved}/{len(samples)}"
    )
    print(f"人気の共通候補: {_format_candidates(popularity_candidates)}")
    print(f"着順の共通候補: {_format_candidates(finish_candidates)}")
    print(f"本賞金の共通候補: {_format_candidates(prize_candidates)}")
    print(f"人気の80%以上支持候補: {_format_supported(popularity_supported, len(samples))}")
    print(f"着順の80%以上支持候補: {_format_supported(finish_supported, len(samples))}")
    print(f"本賞金の80%以上支持候補: {_format_supported(prize_supported, len(samples))}")
    popularity_ranked = supported_numeric_candidates(
        samples, field="popularity", widths=range(1, 4), minimum_ratio=0.0
    )
    finish_ranked = supported_numeric_candidates(
        samples, field="finish_pos", widths=range(1, 4), minimum_ratio=0.0
    )
    prize_ranked = supported_numeric_candidates(
        samples,
        field="prize_money",
        widths=range(1, 11),
        scales=(1, 100, 1000),
        minimum_ratio=0.0,
    )
    print(f"人気の最多支持候補: {_format_supported(popularity_ranked[:3], len(samples))}")
    print(f"着順の最多支持候補: {_format_supported(finish_ranked[:3], len(samples))}")
    print(f"本賞金の最多支持候補: {_format_supported(prize_ranked[:3], len(samples))}")
    print("生レコード、馬名、期待値は表示・保存していません。")


if __name__ == "__main__":
    main()
