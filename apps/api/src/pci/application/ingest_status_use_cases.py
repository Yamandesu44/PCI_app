"""取り込み状況（鮮度・失敗履歴）の参照ユースケース。"""

from __future__ import annotations

import datetime

from pci.application.dto import IngestFailureOutput, IngestStatusOutput
from pci.domain.ops.ingest_log import IngestLogRepository, evaluate_freshness

_HISTORY_LOOKBACK = 20
_RECENT_FAILURES_LIMIT = 5
_ERROR_SUMMARY_MAX_LEN = 200


class GetIngestStatusUseCase:
    """直近の取り込みログから、データの鮮度・失敗有無を判定する。"""

    def __init__(self, repo: IngestLogRepository) -> None:
        self._repo = repo

    def execute(self) -> IngestStatusOutput:
        entries = self._repo.find_recent(limit=_HISTORY_LOOKBACK)
        now = datetime.datetime.now(datetime.UTC)
        freshness = evaluate_freshness(entries, now)

        failures = [
            IngestFailureOutput(
                batch_date=e.batch_date.isoformat(),
                step=e.step,
                mode=e.mode,
                started_at=e.started_at.isoformat(),
                error_summary=(e.error_msg or "")[:_ERROR_SUMMARY_MAX_LEN],
            )
            for e in freshness.recent_failures[:_RECENT_FAILURES_LIMIT]
        ]

        return IngestStatusOutput(
            has_history=freshness.has_history,
            last_success_at=(
                freshness.last_success.effective_time.isoformat()
                if freshness.last_success
                else None
            ),
            last_success_step=freshness.last_success.step if freshness.last_success else None,
            last_attempt_failed=freshness.last_attempt_failed,
            days_since_last_success=freshness.days_since_last_success,
            is_stale=freshness.is_stale,
            recent_failures=failures,
        )
