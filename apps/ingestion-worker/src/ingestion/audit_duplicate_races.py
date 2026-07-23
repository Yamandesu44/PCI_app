"""mykeibadbを正規キーの根拠として重複レースをdry-run監査するCLI。"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

from ingestion.client.mykeibadb_client import MyKeibaDbClient
from ingestion.ingest_api import IngestApiClient
from ingestion.parser.ra_parser import parse_ra

AuditDecision = Literal[
    "removable_after_resync",
    "mart_migration_required",
    "result_conflict",
    "canonical_incomplete",
    "source_unresolved",
]


@dataclass(frozen=True)
class RaceKeyAudit:
    race_key: str
    status: str
    field_size: int
    entry_count: int
    finished_count: int
    entry_signature: str
    result_signature: str
    predicted_pace_count: int
    pace_fit_count: int


@dataclass(frozen=True)
class DuplicateGroupAudit:
    race_date: str
    jyo_cd: str
    race_no: str
    keys: tuple[RaceKeyAudit, ...]


@dataclass(frozen=True)
class DuplicateAuditResult:
    race_date: str
    jyo_cd: str
    race_no: str
    canonical_key: str | None
    stale_keys: tuple[str, ...]
    decision: AuditDecision
    reasons: tuple[str, ...]


def classify_duplicate_group(
    group: DuplicateGroupAudit,
    source_race_keys: set[str],
) -> DuplicateAuditResult:
    """mykeibadbに存在するキーと関連データ差分から、統合前の扱いを分類する。"""
    source_matches = [key for key in group.keys if key.race_key in source_race_keys]
    if len(source_matches) != 1:
        return DuplicateAuditResult(
            race_date=group.race_date,
            jyo_cd=group.jyo_cd,
            race_no=group.race_no,
            canonical_key=None,
            stale_keys=tuple(key.race_key for key in group.keys),
            decision="source_unresolved",
            reasons=(
                f"mykeibadb一致キーが{len(source_matches)}件のため正規キーを一意に決定できない",
            ),
        )

    canonical = source_matches[0]
    stale = [key for key in group.keys if key.race_key != canonical.race_key]
    reasons: list[str] = []

    if canonical.status != "result" or canonical.finished_count == 0:
        decision: AuditDecision = "canonical_incomplete"
        reasons.append("正規キー候補に確定成績が揃っていない")
    elif any(
        key.finished_count > 0
        and key.result_signature != canonical.result_signature
        for key in stale
    ):
        decision = "result_conflict"
        reasons.append("旧キーと正規キー候補の確定成績内容が一致しない")
    elif any(
        key.predicted_pace_count > 0 or key.pace_fit_count > 0
        for key in stale
    ):
        decision = "mart_migration_required"
        reasons.append("旧キーに保存済み予想があり、削除前に予想martの移行が必要")
    else:
        decision = "removable_after_resync"
        reasons.append("正規キー候補の成績が確定し、旧キーに予想martがない")

    if any(key.entry_signature != canonical.entry_signature for key in stale):
        reasons.append("出走馬構成には差があるため、正規キー再同期後の削除を前提とする")

    return DuplicateAuditResult(
        race_date=group.race_date,
        jyo_cd=group.jyo_cd,
        race_no=group.race_no,
        canonical_key=canonical.race_key,
        stale_keys=tuple(key.race_key for key in stale),
        decision=decision,
        reasons=tuple(reasons),
    )


def _parse_group(payload: dict[str, Any]) -> DuplicateGroupAudit:
    return DuplicateGroupAudit(
        race_date=str(payload["race_date"]),
        jyo_cd=str(payload["jyo_cd"]),
        race_no=str(payload["race_no"]),
        keys=tuple(RaceKeyAudit(**key) for key in payload["keys"]),
    )


def _date_chunks(
    date_from: datetime.date,
    date_to: datetime.date,
    days: int = 31,
) -> list[tuple[datetime.date, datetime.date]]:
    chunks: list[tuple[datetime.date, datetime.date]] = []
    current = date_from
    while current <= date_to:
        end = min(current + datetime.timedelta(days=days - 1), date_to)
        chunks.append((current, end))
        current = end + datetime.timedelta(days=1)
    return chunks


def _source_race_keys(
    client: MyKeibaDbClient,
    date_from: datetime.date,
    date_to: datetime.date,
) -> set[str]:
    race_keys: set[str] = set()
    for chunk_from, chunk_to in _date_chunks(date_from, date_to):
        for record in client.iter_ra_records(
            chunk_from.strftime("%Y%m%d"),
            chunk_to.strftime("%Y%m%d"),
        ):
            race = parse_ra(record)
            if race is not None:
                race_keys.add(race.race_key)
    return race_keys


def _parse_args() -> argparse.Namespace:
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description="重複レースを読み取り専用で監査する")
    parser.add_argument(
        "--date",
        default=(today - datetime.timedelta(days=365)).isoformat(),
        help="開始日 YYYY-MM-DD",
    )
    parser.add_argument("--date-to", default=today.isoformat(), help="終了日 YYYY-MM-DD")
    parser.add_argument(
        "--output",
        default="duplicate_race_audit.json",
        help="監査JSONの保存先",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = _parse_args()
    date_from = datetime.date.fromisoformat(args.date)
    date_to = datetime.date.fromisoformat(args.date_to)
    if date_to < date_from:
        raise SystemExit("--date-to は --date 以降を指定してください")

    api = IngestApiClient(
        base_url=os.environ.get("API_BASE_URL", "http://localhost:8000"),
        token=os.environ.get("INGEST_TOKEN", ""),
    )
    groups = [
        _parse_group(payload)
        for payload in api.duplicate_race_audit(args.date, args.date_to)
    ]
    source_keys = _source_race_keys(MyKeibaDbClient(), date_from, date_to)
    results = [classify_duplicate_group(group, source_keys) for group in groups]
    counts = Counter(result.decision for result in results)
    report = {
        "date_from": args.date,
        "date_to": args.date_to,
        "duplicate_group_count": len(results),
        "source_race_key_count": len(source_keys),
        "decision_counts": dict(sorted(counts.items())),
        "groups": [asdict(result) for result in results],
    }
    output = Path(args.output)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"重複レース: {len(results)}組")
    for decision, count in sorted(counts.items()):
        print(f"  {decision}: {count}組")
    print(f"監査結果: {output.resolve()}")


if __name__ == "__main__":
    main()
