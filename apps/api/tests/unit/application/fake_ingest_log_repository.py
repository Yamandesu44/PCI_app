"""テスト用インメモリ IngestLogRepository 実装。"""

from __future__ import annotations

from pci.domain.ops.ingest_log import IngestLogEntry


class FakeIngestLogRepository:
    """テスト専用インメモリ実装。IngestLogRepository Protocol を満たす。

    エントリは新しい順（started_at 降順）で保持することを呼び出し側の責任とする
    （実装 SqlAlchemyIngestLogRepository の ORDER BY started_at DESC を模す）。
    """

    def __init__(self, entries: list[IngestLogEntry] | None = None) -> None:
        self._entries = entries or []

    def find_recent(self, limit: int = 20) -> list[IngestLogEntry]:
        return self._entries[:limit]
