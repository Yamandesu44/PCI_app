"""重複レース統合計画のテスト。"""

from ingestion.audit_duplicate_races import DuplicateGroupAudit, RaceKeyAudit
from ingestion.reconcile_duplicate_races import build_delete_guards


def _key(
    race_key: str,
    *,
    predicted: int = 0,
    result_signature: str = "result",
) -> RaceKeyAudit:
    return RaceKeyAudit(
        race_key=race_key,
        status="result",
        field_size=12,
        entry_count=12,
        finished_count=12,
        entry_signature=f"entry-{race_key}",
        result_signature=result_signature,
        predicted_pace_count=predicted,
        pace_fit_count=0,
    )


def test_builds_guards_only_for_safe_groups() -> None:
    safe_stale = _key("2026020105010111")
    safe_canonical = _key("2026020105010211")
    unsafe_stale = _key("2026020108010111", predicted=1)
    unsafe_canonical = _key("2026020108020211")
    groups = [
        DuplicateGroupAudit(
            race_date="2026-02-01",
            jyo_cd="05",
            race_no="11",
            keys=(safe_stale, safe_canonical),
        ),
        DuplicateGroupAudit(
            race_date="2026-02-01",
            jyo_cd="08",
            race_no="11",
            keys=(unsafe_stale, unsafe_canonical),
        ),
    ]

    guards, decisions = build_delete_guards(
        groups,
        {safe_canonical.race_key, unsafe_canonical.race_key},
    )

    assert set(guards) == {safe_canonical.race_key}
    assert guards[safe_canonical.race_key][0].stale_race_key == safe_stale.race_key
    assert decisions["removable_after_resync"] == 1
    assert decisions["mart_migration_required"] == 1
