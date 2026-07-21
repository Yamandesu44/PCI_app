"""取り込み鮮度判定（evaluate_freshness）のテスト。"""

from __future__ import annotations

import datetime

from pci.domain.ops.ingest_log import IngestLogEntry, evaluate_freshness

UTC = datetime.UTC


def _entry(
    *,
    days_ago: int,
    status: str | None = "ok",
    step: str = "entries",
    finished: bool = True,
    error_msg: str | None = None,
) -> IngestLogEntry:
    started = datetime.datetime(2026, 7, 12, 10, 0, tzinfo=UTC) - datetime.timedelta(days=days_ago)
    return IngestLogEntry(
        batch_date=started.date(),
        step=step,
        mode="mykeibadb",
        started_at=started,
        finished_at=started + datetime.timedelta(minutes=5) if finished else None,
        status=status,
        error_msg=error_msg,
    )


NOW = datetime.datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


class TestEvaluateFreshness:
    def test_empty_history_is_not_stale(self) -> None:
        """ログ皆無（開発/fixture環境等）は「問題あり」に見せない。"""
        result = evaluate_freshness([], NOW)
        assert result.has_history is False
        assert result.is_stale is False
        assert result.last_success is None
        assert result.days_since_last_success is None

    def test_recent_success_is_fresh(self) -> None:
        entries = [_entry(days_ago=1)]
        result = evaluate_freshness(entries, NOW)
        assert result.has_history is True
        assert result.is_stale is False
        assert result.days_since_last_success == 1
        assert result.last_success is entries[0]
        assert result.last_attempt_failed is False

    def test_old_success_is_stale(self) -> None:
        entries = [_entry(days_ago=10)]
        result = evaluate_freshness(entries, NOW)
        assert result.is_stale is True
        assert result.days_since_last_success == 10

    def test_stale_after_days_boundary(self) -> None:
        exactly_at_threshold = evaluate_freshness([_entry(days_ago=4)], NOW, stale_after_days=4)
        assert exactly_at_threshold.is_stale is False
        one_over = evaluate_freshness([_entry(days_ago=5)], NOW, stale_after_days=4)
        assert one_over.is_stale is True

    def test_never_succeeded_is_stale(self) -> None:
        entries = [_entry(days_ago=1, status="error", error_msg="boom")]
        result = evaluate_freshness(entries, NOW)
        assert result.has_history is True
        assert result.last_success is None
        assert result.days_since_last_success is None
        assert result.is_stale is True

    def test_last_attempt_failed_flag_checks_most_recent_only(self) -> None:
        """直近が失敗でも、その前が成功していれば last_success は拾う。"""
        entries = [
            _entry(days_ago=0, status="error", error_msg="timeout"),
            _entry(days_ago=1, status="ok"),
        ]
        result = evaluate_freshness(entries, NOW)
        assert result.last_attempt_failed is True
        assert result.last_success is entries[1]
        assert result.is_stale is False  # 前日に成功していれば鮮度自体は問題なし

    def test_running_status_does_not_count_as_failed_or_success(self) -> None:
        entries = [_entry(days_ago=0, status="running", finished=False)]
        result = evaluate_freshness(entries, NOW)
        assert result.last_attempt_failed is False
        assert result.last_success is None

    def test_recent_failures_collects_all_errors_in_window(self) -> None:
        entries = [
            _entry(days_ago=0, status="ok"),
            _entry(days_ago=1, status="error", step="results", error_msg="e1"),
            _entry(days_ago=2, status="error", step="entries", error_msg="e2"),
        ]
        result = evaluate_freshness(entries, NOW)
        assert [f.error_msg for f in result.recent_failures] == ["e1", "e2"]

    def test_effective_time_prefers_finished_at(self) -> None:
        entry = _entry(days_ago=0)
        assert entry.effective_time == entry.finished_at

    def test_effective_time_falls_back_to_started_at_when_unfinished(self) -> None:
        entry = _entry(days_ago=0, status="running", finished=False)
        assert entry.effective_time == entry.started_at
