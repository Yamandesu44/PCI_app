"""取り込みバッチの実行状況（監視用の読み取り専用ドメイン）。

ingest_log は分析結果（PCI/RPCI等）ではなく運用監査データのため、算出式は持たない。
ここに置くのは「直近ログから鮮度・失敗有無を判定する」薄い純粋関数のみ。

鮮度判定の基本方針:
    - 直近の実行（started_at 降順の先頭）が失敗していれば `last_attempt_failed`。
    - 直近の成功からの経過日数が `stale_after_days` を超えたら `is_stale`。
      Task Scheduler の実運用は週3回（金/土/日）のため、取りこぼしのマージンを
      考慮した暫定値を既定とする（`STALE_AFTER_DAYS` 🧪仮値）。
    - ログが1件も無い場合（開発/fixture環境等）は「問題あり」と誤判定しないよう
      `has_history=False` とし、`is_stale` は立てない。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Protocol

STALE_AFTER_DAYS = 4


@dataclass(frozen=True)
class IngestLogEntry:
    """1回のバッチ実行ログ（ingest_log の1行）。"""

    batch_date: datetime.date
    step: str
    mode: str
    started_at: datetime.datetime
    finished_at: datetime.datetime | None
    status: str | None  # "running" | "ok" | "error"
    error_msg: str | None

    @property
    def effective_time(self) -> datetime.datetime:
        """鮮度計算に使う代表時刻（完了時刻優先、未完了なら開始時刻）。"""
        return self.finished_at or self.started_at


class IngestLogRepository(Protocol):
    """取り込みログの読み取り専用リポジトリ。"""

    def find_recent(self, limit: int = 20) -> list[IngestLogEntry]:
        """開始時刻の新しい順に直近ログを返す。"""
        ...


@dataclass(frozen=True)
class IngestFreshness:
    """取り込みの鮮度サマリ（画面表示用）。"""

    has_history: bool
    last_success: IngestLogEntry | None
    last_attempt_failed: bool
    days_since_last_success: int | None
    is_stale: bool
    recent_failures: tuple[IngestLogEntry, ...] = field(default_factory=tuple)


def evaluate_freshness(
    entries: list[IngestLogEntry],
    now: datetime.datetime,
    *,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> IngestFreshness:
    """直近ログ（新しい順）から鮮度・失敗有無を判定する。

    Args:
        entries: `IngestLogRepository.find_recent()` の戻り値（started_at 降順）。
        now:     判定基準時刻。呼び出し側（application 層）が注入する
                 （domain 層を純粋・決定的に保つため `datetime.now()` をここで呼ばない）。
        stale_after_days: 最終成功からの経過日数がこれを超えたら stale とする。
    """
    if not entries:
        return IngestFreshness(
            has_history=False,
            last_success=None,
            last_attempt_failed=False,
            days_since_last_success=None,
            is_stale=False,
        )

    successes = [e for e in entries if e.status == "ok"]
    last_success = successes[0] if successes else None
    days_since = (now.date() - last_success.effective_time.date()).days if last_success else None
    is_stale = days_since is None or days_since > stale_after_days
    last_attempt_failed = entries[0].status == "error"
    recent_failures = tuple(e for e in entries if e.status == "error")

    return IngestFreshness(
        has_history=True,
        last_success=last_success,
        last_attempt_failed=last_attempt_failed,
        days_since_last_success=days_since,
        is_stale=is_stale,
        recent_failures=recent_failures,
    )
