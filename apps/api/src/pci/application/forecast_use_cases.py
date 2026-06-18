"""展開予想ユースケース（想定RPCI + PAI + 展開シナリオ）。

ADR-0005 に従い、予測ロジックは戦略インターフェース `RpciForecaster` 経由で注入する。
MVP は RuleBasedRpciForecaster（rule-v1）を既定値とし、ML 実装へ無変更で差し替え可能。
"""

from __future__ import annotations

from pci.application.dto import (
    ForecastOutput,
    HorseFitOutput,
    ReasonOutput,
)
from pci.domain.pace.adaptability import HorsePaceProfile, PaceAdaptabilityScorer, PaiResult
from pci.domain.pace.rpci_forecast import (
    RaceContext,
    RpciForecaster,
    RuleBasedRpciForecaster,
)
from pci.domain.pace.running_style import RunningStyleLabel, classify_running_style
from pci.domain.pace.scenario import build_pace_scenario
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason


class ForecastRaceUseCase:
    """未確定レースの展開予想を生成するユースケース。

    出走各馬の脚質を直近5走から判定し、想定RPCI・展開シナリオ・各馬 PAI を返す。
    mart 層への永続化は presentation/API 層の責務とし、本ユースケースは算出に専念する。
    """

    def __init__(
        self,
        repo: RaceRepository,
        forecaster: RpciForecaster | None = None,
        scorer: PaceAdaptabilityScorer | None = None,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster or RuleBasedRpciForecaster()
        self._scorer = scorer or PaceAdaptabilityScorer()

    def execute(self, race_key_str: str) -> ForecastOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")

        entries = self._repo.find_entries(key)
        if not entries:
            raise ValueError(f"出走馬が登録されていません: {race_key_str}")

        profiles = [
            HorsePaceProfile(
                horse_no=e.horse_no,
                running_style=self._resolve_style(e.ketto_num),
            )
            for e in entries
        ]

        context = RaceContext(
            distance_m=race.distance_m,
            track_type=race.track_type,
            running_styles=tuple(p.running_style for p in profiles),
            track_condition=race.track_condition,
        )
        forecast = self._forecaster.forecast(context)

        fit_results: list[PaiResult] = [
            self._scorer.score(p, forecast, race.distance_m, race.track_condition) for p in profiles
        ]
        scenario = build_pace_scenario(forecast, fit_results, profiles)

        fit_by_no = {r.horse_no: r for r in fit_results}
        horses = [
            HorseFitOutput(
                horse_no=p.horse_no,
                running_style=str(p.running_style),
                pai=fit_by_no[p.horse_no].pai,
                fit_label=str(fit_by_no[p.horse_no].fit_label),
                reasons=_to_reason_outputs(fit_by_no[p.horse_no].reasons),
            )
            for p in profiles
        ]

        return ForecastOutput(
            race_key=race_key_str,
            predicted_rpci=forecast.value,
            pace_label=str(forecast.label),
            confidence=forecast.confidence,
            model_version=forecast.model_version,
            scenario_headline=scenario.headline,
            scenario_detail=scenario.detail,
            front_runners=list(scenario.front_runners),
            beneficiaries=list(scenario.beneficiaries),
            horses=horses,
            forecast_reasons=_to_reason_outputs(forecast.reasons),
        )

    def _resolve_style(self, ketto_num: str) -> RunningStyleLabel:
        """直近5走の4角通過順位から脚質を判定する。データ不足時は自在。"""
        if not ketto_num:
            return RunningStyleLabel.FLEXIBLE
        recent = self._repo.find_horse_recent_entries(ketto_num, limit=5)
        c4 = tuple(e.corner_4 for e in recent if e.corner_4 is not None)
        return classify_running_style(c4).label


def _to_reason_outputs(reasons: tuple[Reason, ...]) -> list[ReasonOutput]:
    return [
        ReasonOutput(code=r.code, description=r.description, contribution=r.contribution)
        for r in reasons
    ]
