"""重複レースを正規キーへ再同期してから旧キーを安全に削除するCLI。"""

from __future__ import annotations

import argparse
import datetime
import os
from collections import Counter

from dotenv import load_dotenv

from ingestion.audit_duplicate_races import (
    DuplicateGroupAudit,
    _parse_group,
    _source_race_keys,
    classify_duplicate_group,
)
from ingestion.batch import ingest_results
from ingestion.client.mykeibadb_client import MyKeibaDbClient
from ingestion.ingest_api import IngestApiClient
from ingestion.models import DuplicateDeleteGuard


def build_delete_guards(
    groups: list[DuplicateGroupAudit],
    source_race_keys: set[str],
) -> tuple[
    dict[str, tuple[DuplicateDeleteGuard, ...]],
    Counter[str],
]:
    """監査結果から自動統合できる組だけの削除ガードを組み立てる。"""
    guards: dict[str, list[DuplicateDeleteGuard]] = {}
    decisions: Counter[str] = Counter()
    for group in groups:
        result = classify_duplicate_group(group, source_race_keys)
        decisions[result.decision] += 1
        if (
            result.decision != "removable_after_resync"
            or result.canonical_key is None
        ):
            continue
        key_by_value = {key.race_key: key for key in group.keys}
        for stale_race_key in result.stale_keys:
            stale = key_by_value[stale_race_key]
            guards.setdefault(result.canonical_key, []).append(
                DuplicateDeleteGuard(
                    stale_race_key=stale_race_key,
                    canonical_race_key=result.canonical_key,
                    stale_entry_signature=stale.entry_signature,
                    stale_result_signature=stale.result_signature,
                )
            )
    return (
        {
            canonical: tuple(sorted(items, key=lambda item: item.stale_race_key))
            for canonical, items in guards.items()
        },
        decisions,
    )


def _parse_args() -> argparse.Namespace:
    today = datetime.date.today()
    parser = argparse.ArgumentParser(
        description="重複レースを正規キー再同期後に安全条件付きで統合する"
    )
    parser.add_argument(
        "--date",
        default=(today - datetime.timedelta(days=365)).isoformat(),
        help="開始日 YYYY-MM-DD",
    )
    parser.add_argument("--date-to", default=today.isoformat(), help="終了日 YYYY-MM-DD")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="再同期と旧キー削除を実行する。未指定時は計画表示のみ",
    )
    parser.add_argument(
        "--expected-groups",
        type=int,
        default=None,
        help="--apply時に必須。dry-runで確認した自動統合対象組数",
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
    client = MyKeibaDbClient()
    source_keys = _source_race_keys(client, date_from, date_to)
    guards, decisions = build_delete_guards(groups, source_keys)
    safe_group_count = len(guards)

    print(f"重複レース: {len(groups)}組")
    for decision, count in sorted(decisions.items()):
        print(f"  {decision}: {count}組")
    print(f"自動統合対象: {safe_group_count}組")

    if not args.apply:
        print(
            "dry-runのみ。実行時は --apply "
            f"--expected-groups {safe_group_count} を追加してください。"
        )
        return
    if args.expected_groups is None:
        raise SystemExit("--apply時は--expected-groupsが必須です")
    if args.expected_groups != safe_group_count:
        raise SystemExit(
            "自動統合対象数がdry-run時と一致しません: "
            f"expected={args.expected_groups} actual={safe_group_count}"
        )
    if not guards:
        print("統合対象はありません。")
        return

    stale_keys = {
        guard.stale_race_key
        for items in guards.values()
        for guard in items
    }
    summary = ingest_results(
        client,
        api,
        date_from.strftime("%Y%m%d"),
        date_to.strftime("%Y%m%d"),
        race_keys=stale_keys,
        duplicate_guards=guards,
    )
    if summary.sent_fail:
        raise SystemExit(
            "統合中に失敗が発生しました: "
            f"同期成功={summary.sent_ok} 失敗={summary.sent_fail} "
            f"削除={summary.deleted_stale}"
        )

    remaining_groups = api.duplicate_race_audit(args.date, args.date_to)
    remaining_stale = {
        str(key["race_key"])
        for group in remaining_groups
        for key in group["keys"]
        if str(key["race_key"]) in stale_keys
    }
    if remaining_stale:
        raise SystemExit(f"統合後も旧キーが{len(remaining_stale)}件残っています")
    print(
        "統合完了: "
        f"正規キー同期={summary.sent_ok}組 / 旧キー削除={summary.deleted_stale}件"
    )


if __name__ == "__main__":
    main()
