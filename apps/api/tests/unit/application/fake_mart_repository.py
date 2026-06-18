"""テスト用インメモリ MartRepository 実装。"""

from __future__ import annotations

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.rpci_forecast import RpciForecast


class FakeMartRepository:
    """テスト専用インメモリ実装。MartRepository Protocol を満たす。"""

    def __init__(self) -> None:
        self.predicted_pace: dict[tuple[str, str], RpciForecast] = {}
        self.pace_fit: dict[tuple[str, int, str], PaiResult] = {}

    def save_predicted_pace(self, race_key: str, forecast: RpciForecast) -> None:
        self.predicted_pace[(race_key, forecast.model_version)] = forecast

    def save_pace_fit(self, race_key: str, horse_no: int, result: PaiResult) -> None:
        self.pace_fit[(race_key, horse_no, result.model_version)] = result
