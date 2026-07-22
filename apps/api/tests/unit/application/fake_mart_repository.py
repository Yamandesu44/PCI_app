"""テスト用インメモリ MartRepository 実装。"""

from __future__ import annotations

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.mart_repository import PredictedPaceRecord, RaceBoardForecastRecord
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

    def find_predicted_pace(self, race_key: str) -> PredictedPaceRecord | None:
        for (key, _model_version), forecast in self.predicted_pace.items():
            if key == race_key:
                return PredictedPaceRecord(
                    race_key=race_key,
                    model_version=forecast.model_version,
                    predicted_rpci=forecast.value,
                    pace_label=str(forecast.label),
                    confidence=forecast.confidence,
                )
        return None

    def find_race_board_forecasts(
        self, race_keys: list[str]
    ) -> dict[str, RaceBoardForecastRecord]:
        result: dict[str, RaceBoardForecastRecord] = {}
        for race_key in race_keys:
            predicted = self.find_predicted_pace(race_key)
            fits = [
                (horse_no, fit)
                for (key, horse_no, _version), fit in self.pace_fit.items()
                if key == race_key
            ]
            if predicted is None or not fits:
                continue
            horse_no, top = max(fits, key=lambda item: item[1].pai)
            result[race_key] = RaceBoardForecastRecord(
                race_key=race_key,
                pace_label=predicted.pace_label,
                confidence=predicted.confidence,
                top_horse_no=horse_no,
                top_horse_name=None,
                top_pai=top.pai,
                top_fit_label=str(top.fit_label),
            )
        return result
