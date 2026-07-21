"""IngestLogRepository の SQLAlchemy 実装（ingest_log: バッチ実行監査ログ）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pci.domain.ops.ingest_log import IngestLogEntry
from pci.infrastructure.database.models import IngestLogModel


class SqlAlchemyIngestLogRepository:
    """SQLAlchemy を使った IngestLogRepository 実装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def find_recent(self, limit: int = 20) -> list[IngestLogEntry]:
        stmt = select(IngestLogModel).order_by(IngestLogModel.started_at.desc()).limit(limit)
        return [self._to_entry(row) for row in self._s.scalars(stmt).all()]

    @staticmethod
    def _to_entry(row: IngestLogModel) -> IngestLogEntry:
        return IngestLogEntry(
            batch_date=row.batch_date,
            step=row.step,
            mode=row.mode,
            started_at=row.started_at,
            finished_at=row.finished_at,
            status=row.status,
            error_msg=row.error_msg,
        )
