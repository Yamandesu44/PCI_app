"""展開予想ユースケース（想定RPCI + PAI + 展開シナリオ）。

ADR-0005 に従い、予測ロジックは戦略インターフェース `RpciForecaster` 経由で注入する。
MVP は RuleBasedRpciForecaster（rule-v2）を既定値とし、ML 実装へ無変更で差し替え可能。
mart 層への永続化は MartRepository を注入して本ユースケース内で実行する（ADR-0006）。
"""

from __future__ import annotations

from pci.application.dto import (
    CommentOutput,
    ForecastOutput,
    FormationGroupOutput,
    FormationHorseOutput,
    FormationOutput,
    HorseFitOutput,
    ReasonOutput,
    StyleAdvantageEntryOutput,
    StyleAdvantageOutput,
)
from pci.domain.pace.adaptability import HorsePaceProfile, PaceAdaptabilityScorer, PaiResult
from pci.domain.pace.affinity import (
    HorsePaceAffinityProfile,
    PaceAffinityRaceResult,
    build_horse_pace_affinity_profile,
)
from pci.domain.pace.commentary import (
    BeneficiaryRef,
    Commentary,
    CommentGenerator,
    ForecastCommentInput,
    RuleBasedCommentGenerator,
)
from pci.domain.pace.formation import (
    FormationHorseInput,
    FormationPrediction,
    predict_formation,
)
from pci.domain.pace.mart_repository import MartRepository
from pci.domain.pace.rpci_forecast import (
    FrontRunnerPaceSample,
    RaceContext,
    RpciForecaster,
    RuleBasedRpciForecaster,
)
from pci.domain.pace.running_style import (
    RunningStyleHistory,
    RunningStyleLabel,
    predict_running_style_for_distance,
)
from pci.domain.pace.scenario import build_pace_scenario
from pci.domain.pace.style_advantage import StyleAdvantage, build_style_advantage
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason


class ForecastRaceUseCase:
    """未確定レースの展開予想を生成し、mart 層へ永続化するユースケース。

    出走各馬の脚質を直近5走から判定し、想定RPCI・展開シナリオ・各馬 PAI を返す。
    mart_repo が注入された場合、算出結果を predicted_pace / pace_fit に保存する。
    """

    def __init__(
        self,
        repo: RaceRepository,
        forecaster: RpciForecaster | None = None,
        scorer: PaceAdaptabilityScorer | None = None,
        mart_repo: MartRepository | None = None,
        comment_generator: CommentGenerator | None = None,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster or RuleBasedRpciForecaster()
        self._scorer = scorer or PaceAdaptabilityScorer()
        self._mart_repo = mart_repo
        self._commenter = comment_generator or RuleBasedCommentGenerator()

    def execute(self, race_key_str: str) -> ForecastOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")

        entries = self._repo.find_entries(key)
        if not entries:
            raise ValueError(f"出走馬が登録されていません: {race_key_str}")

        profiles: list[HorsePaceProfile] = []
        front_pace_samples: list[FrontRunnerPaceSample] = []
        formation_inputs: list[FormationHorseInput] = []
        for e in entries:
            style, style_confidence, early_position, early_sample_size = (
                self._resolve_style_evidence(e.ketto_num, race)
            )
            profiles.append(
                HorsePaceProfile(
                    horse_no=e.horse_no,
                    running_style=style,
                    pace_affinity=self._build_affinity_profile(e.ketto_num, style, race),
                )
            )
            formation_inputs.append(
                FormationHorseInput(
                    horse_no=e.horse_no,
                    frame_no=e.frame_no,
                    running_style=style,
                    style_confidence=style_confidence,
                    recent_early_position=early_position,
                    recent_sample_size=early_sample_size,
                )
            )
            sample = self._build_front_pace_sample(e.horse_no, e.ketto_num, style)
            if sample is not None:
                front_pace_samples.append(sample)

        context = RaceContext(
            distance_m=race.distance_m,
            track_type=race.track_type,
            running_styles=tuple(p.running_style for p in profiles),
            track_condition=race.track_condition,
            venue_code=race.jyo_cd,
            front_pace_samples=tuple(front_pace_samples),
        )
        forecast = self._forecaster.forecast(context)

        fit_results: list[PaiResult] = [
            self._scorer.score(p, forecast, race.distance_m, race.track_condition) for p in profiles
        ]

        if self._mart_repo is not None:
            self._mart_repo.save_predicted_pace(race_key_str, forecast)
            for profile, fit_result in zip(profiles, fit_results, strict=True):
                self._mart_repo.save_pace_fit(race_key_str, profile.horse_no, fit_result)

        scenario = build_pace_scenario(forecast, fit_results, profiles)
        style_advantage = build_style_advantage(
            forecast.value,
            race.track_type,
            tuple(p.running_style for p in profiles),
        )

        name_map = self._repo.find_horse_names(e.ketto_num for e in entries if e.ketto_num)
        formation_prediction = predict_formation(tuple(formation_inputs))
        ketto_by_no = {e.horse_no: e.ketto_num for e in entries}
        frame_no_by_no = {e.horse_no: e.frame_no for e in entries}
        fit_by_no = {r.horse_no: r for r in fit_results}
        horses = [
            HorseFitOutput(
                horse_no=p.horse_no,
                frame_no=frame_no_by_no[p.horse_no],
                horse_name=name_map.get(ketto_by_no.get(p.horse_no, "")),
                running_style=str(p.running_style),
                pai=fit_by_no[p.horse_no].pai,
                fit_label=str(fit_by_no[p.horse_no].fit_label),
                reasons=_to_reason_outputs(fit_by_no[p.horse_no].reasons),
            )
            for p in profiles
        ]

        comment_input = ForecastCommentInput(
            distance_m=race.distance_m,
            track_type=race.track_type,
            field_size=len(profiles),
            pace_label=forecast.label,
            predicted_rpci=forecast.value,
            confidence=forecast.confidence,
            front_runners=scenario.front_runners,
            beneficiaries=tuple(
                BeneficiaryRef(horse_no=no, pai=fit_by_no[no].pai) for no in scenario.beneficiaries
            ),
        )
        comment = _to_comment_output(self._commenter.forecast_comment(comment_input))

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
            comment=comment,
            formation=_to_formation_output(formation_prediction, name_map, ketto_by_no),
            style_advantage=_to_style_advantage_output(style_advantage),
        )

    def _resolve_style_evidence(
        self, ketto_num: str, target_race: Race
    ) -> tuple[RunningStyleLabel, float, float | None, int]:
        """脚質と、隊列予想に使う近走序盤位置の証拠をまとめて返す。"""
        if not ketto_num:
            return RunningStyleLabel.FLEXIBLE, 0.0, None, 0
        recent = self._repo.find_horse_recent_entries(
            ketto_num,
            limit=5,
            before=target_race.race_date,
        )
        early_position_items: list[int] = []
        style_histories: list[RunningStyleHistory] = []
        for entry in recent:
            early_position = entry.corner_1 if entry.corner_1 is not None else entry.corner_4
            if early_position is not None:
                early_position_items.append(early_position)
            if entry.corner_4 is None:
                continue
            past_race = self._repo.find_by_key(entry.race_key)
            if past_race is not None:
                style_histories.append(
                    RunningStyleHistory(
                        corner_position=entry.corner_4,
                        distance_m=past_race.distance_m,
                    )
                )
        style = predict_running_style_for_distance(
            tuple(style_histories),
            target_race.distance_m,
        )
        early_positions = tuple(early_position_items)
        average = sum(early_positions) / len(early_positions) if early_positions else None
        return style.label, style.confidence, average, len(early_positions)

    def _build_front_pace_sample(
        self, horse_no: int, ketto_num: str, style: RunningStyleLabel
    ) -> FrontRunnerPaceSample | None:
        """逃げ・先行候補が近10走で「前で運んだとき」に作ったペース傾向を集計する（rule-v2）。

        前付け（1角通過≤2、無ければ4角通過≤2）の過去走だけを対象に、その馬自身の
        PCI（欠損時は当該レースの実績RPCIで補完）を平均する。前付け実績が無ければ
        None を返し、想定RPCI 予測は頭数ベース（rule-v1 相当）にフォールバックする。
        """
        if not ketto_num or style not in _FRONT_STYLES:
            return None
        recent = self._repo.find_horse_recent_entries(ketto_num, limit=10)
        paces: list[float] = []
        for entry in recent:
            if not _led_from_front(entry):
                continue
            pace = entry.pci_actual
            if pace is None:
                past = self._repo.find_by_key(entry.race_key)
                pace = past.rpci_actual if past is not None else None
            if pace is not None:
                paces.append(pace)
        if not paces:
            return None
        return FrontRunnerPaceSample(
            horse_no=horse_no,
            style=style,
            avg_pci=round(sum(paces) / len(paces), 1),
            sample_size=len(paces),
        )

    def _build_affinity_profile(
        self, ketto_num: str, style: RunningStyleLabel, target_race: Race
    ) -> HorsePaceAffinityProfile:
        """過去好走時のペースから、馬ごとの得意なレース質を作る。"""
        recent = self._repo.find_horse_recent_entries(ketto_num, limit=12)
        results: list[PaceAffinityRaceResult] = []
        for entry in recent:
            past_race = self._repo.find_by_key(entry.race_key)
            if past_race is None:
                continue
            results.append(
                PaceAffinityRaceResult(
                    race_key=entry.race_key,
                    race_date=past_race.race_date,
                    finish_pos=entry.finish_pos,
                    grade=past_race.grade,
                    rpci_actual=past_race.rpci_actual,
                    pci3_actual=past_race.pci3_actual,
                    pci_actual=entry.pci_actual,
                )
            )
        return build_horse_pace_affinity_profile(
            ketto_num,
            style,
            tuple(results),
            as_of=target_race.race_date,
        )


_FRONT_STYLES = (RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT)


def _led_from_front(entry: RaceEntry) -> bool:
    """その過去走で前（逃げ・番手）にいたか。1角通過≤2、無ければ4角通過≤2で判定。"""
    if entry.corner_1 is not None:
        return entry.corner_1 <= 2
    if entry.corner_4 is not None:
        return entry.corner_4 <= 2
    return False


def _to_reason_outputs(reasons: tuple[Reason, ...]) -> list[ReasonOutput]:
    return [
        ReasonOutput(code=r.code, description=r.description, contribution=r.contribution)
        for r in reasons
    ]


def _to_comment_output(commentary: Commentary) -> CommentOutput:
    return CommentOutput(
        headline=commentary.headline,
        body=list(commentary.body),
        model_version=commentary.model_version,
        reasons=_to_reason_outputs(commentary.reasons),
    )


def _to_style_advantage_output(advantage: StyleAdvantage) -> StyleAdvantageOutput:
    return StyleAdvantageOutput(
        model_version=advantage.model_version,
        entries=[
            StyleAdvantageEntryOutput(style=str(entry.style), score=entry.score)
            for entry in advantage.entries
        ],
        reasons=_to_reason_outputs(advantage.reasons),
    )


def _to_formation_output(
    prediction: FormationPrediction | None,
    name_map: dict[str, str],
    ketto_by_no: dict[int, str],
) -> FormationOutput | None:
    if prediction is None:
        return None
    return FormationOutput(
        model_version=prediction.model_version,
        groups=[
            FormationGroupOutput(
                key=str(group.zone),
                label=group.label,
                horses=[
                    FormationHorseOutput(
                        horse_no=horse.horse_no,
                        frame_no=horse.frame_no,
                        horse_name=name_map.get(ketto_by_no.get(horse.horse_no, "")),
                        running_style=str(horse.running_style),
                        confidence_label=horse.confidence_label,
                        reasons=_to_reason_outputs(horse.reasons),
                    )
                    for horse in group.horses
                ],
            )
            for group in prediction.groups
        ],
    )
