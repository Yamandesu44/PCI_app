"""GetIngestStatusUseCase のテスト。"""

from __future__ import annotations

import datetime

from pci.application.ingest_status_use_cases import GetIngestStatusUseCase
from pci.domain.ops.ingest_log import IngestLogEntry
from tests.unit.application.fake_ingest_log_repository import FakeIngestLogRepository

UTC = datetime.UTC


def _entry(
    *,
    days_ago: int,
    status: str | None = "ok",
    step: str = "entries",
    error_msg: str | None = None,
) -> IngestLogEntry:
    started = datetime.datetime.now(UTC) - datetime.timedelta(days=days_ago)
    return IngestLogEntry(
        batch_date=started.date(),
        step=step,
        mode="mykeibadb",
        started_at=started,
        finished_at=started + datetime.timedelta(minutes=5),
        status=status,
        error_msg=error_msg,
    )


class TestGetIngestStatusUseCase:
    def test_no_history_reports_not_applicable(self) -> None:
        output = GetIngestStatusUseCase(FakeIngestLogRepository([])).execute()
        assert output.has_history is False
        assert output.is_stale is False
        assert output.last_success_at is None
        assert output.recent_failures == []

    def test_recent_success_is_reported(self) -> None:
        entry = _entry(days_ago=1, step="results")
        output = GetIngestStatusUseCase(FakeIngestLogRepository([entry])).execute()
        assert output.has_history is True
        assert output.is_stale is False
        assert output.last_success_step == "results"
        assert output.last_success_at == entry.effective_time.isoformat()
        assert output.days_since_last_success == 1

    def test_stale_history_is_flagged(self) -> None:
        output = GetIngestStatusUseCase(
            FakeIngestLogRepository([_entry(days_ago=10)])
        ).execute()
        assert output.is_stale is True

    def test_recent_failures_are_summarized_and_truncated(self) -> None:
        long_error = "x" * 500
        entries = [
            _entry(days_ago=0, status="error", step="entries", error_msg=long_error),
            _entry(days_ago=1, status="ok"),
        ]
        output = GetIngestStatusUseCase(FakeIngestLogRepository(entries)).execute()
        assert output.last_attempt_failed is True
        assert len(output.recent_failures) == 1
        failure = output.recent_failures[0]
        assert failure.step == "entries"
        assert failure.mode == "mykeibadb"
        assert len(failure.error_summary) == 200

    def test_recent_failures_capped_at_five(self) -> None:
        entries = [
            _entry(days_ago=i, status="error", error_msg=f"e{i}") for i in range(8)
        ]
        output = GetIngestStatusUseCase(FakeIngestLogRepository(entries)).execute()
        assert len(output.recent_failures) == 5
