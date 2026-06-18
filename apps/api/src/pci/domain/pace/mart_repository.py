"""mart 層 Repository Protocol（ADR-0006）。

predicted_pace / pace_fit の書き込みを担う戦略インターフェース。
実装は infrastructure 層（SqlAlchemyMartRepository）。
アプリケーション層はこの Protocol のみ参照し、SQLAlchemy 詳細を知らない。
"""

from __future__ import annotations

from typing import Protocol

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.rpci_forecast import RpciForecast


class MartRepository(Protocol):
    """mart 層（predicted_pace / pace_fit）の書き込み専用インターフェース（ADR-0006）。

    model_version をプライマリキーの一部として保持するため、
    同一レースを再予測しても既存レコードを安全に上書きできる。
    """

    def save_predicted_pace(
        self,
        race_key: str,
        forecast: RpciForecast,
    ) -> None: ...

    def save_pace_fit(
        self,
        race_key: str,
        horse_no: int,
        result: PaiResult,
    ) -> None: ...
