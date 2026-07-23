"""重複レースdry-run分類のテスト。"""

from ingestion.audit_duplicate_races import (
    DuplicateGroupAudit,
    RaceKeyAudit,
    classify_duplicate_group,
)


def _key(
    race_key: str,
    *,
    result_signature: str = "same-result",
    entry_signature: str = "same-entry",
    predicted: int = 0,
    fit: int = 0,
    status: str = "result",
    finished: int = 12,
) -> RaceKeyAudit:
    return RaceKeyAudit(
        race_key=race_key,
        status=status,
        field_size=12,
        entry_count=12,
        finished_count=finished,
        entry_signature=entry_signature,
        result_signature=result_signature,
        predicted_pace_count=predicted,
        pace_fit_count=fit,
    )


def _group(*keys: RaceKeyAudit) -> DuplicateGroupAudit:
    return DuplicateGroupAudit(
        race_date="2026-02-01",
        jyo_cd="05",
        race_no="11",
        keys=keys,
    )


def test_identical_stale_key_without_mart_is_removable_after_resync() -> None:
    canonical = _key("2026020105010211")
    stale = _key("2026020105010111")

    result = classify_duplicate_group(
        _group(stale, canonical),
        {canonical.race_key},
    )

    assert result.canonical_key == canonical.race_key
    assert result.stale_keys == (stale.race_key,)
    assert result.decision == "removable_after_resync"


def test_stale_prediction_requires_mart_migration() -> None:
    canonical = _key("2026020105010211")
    stale = _key("2026020105010111", predicted=1, fit=12)

    result = classify_duplicate_group(_group(stale, canonical), {canonical.race_key})

    assert result.decision == "mart_migration_required"


def test_different_finished_results_are_conflict() -> None:
    canonical = _key("2026020105010211", result_signature="canonical")
    stale = _key("2026020105010111", result_signature="stale")

    result = classify_duplicate_group(_group(stale, canonical), {canonical.race_key})

    assert result.decision == "result_conflict"


def test_missing_or_multiple_source_keys_are_unresolved() -> None:
    first = _key("2026020105010111")
    second = _key("2026020105010211")
    group = _group(first, second)

    assert classify_duplicate_group(group, set()).decision == "source_unresolved"
    assert (
        classify_duplicate_group(
            group,
            {first.race_key, second.race_key},
        ).decision
        == "source_unresolved"
    )


def test_incomplete_canonical_is_not_removable() -> None:
    canonical = _key("2026020105010211", status="entries", finished=0)
    stale = _key("2026020105010111")

    result = classify_duplicate_group(_group(stale, canonical), {canonical.race_key})

    assert result.decision == "canonical_incomplete"
