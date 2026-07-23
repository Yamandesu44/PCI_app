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
    IntegratedEntryOutput,
    IntegratedRankingOutput,
    ReasonOutput,
    StyleAdvantageEntryOutput,
    StyleAdvantageOutput,
)
from pci.domain.pace.ability import AbilityRaceResult, AbilityScore, AbilityScorer
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
from pci.domain.pace.course_aptitude import (
    CourseAptitudeProfile,
    CourseAptitudeRaceResult,
    build_course_aptitude_profile,
)
from pci.domain.pace.formation import (
    FormationHorseInput,
    FormationPrediction,
    predict_formation,
)
from pci.domain.pace.integrated_ranking import IntegratedRanking, build_integrated_ranking
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
from pci.domain.pace.style_advantage import (
    StyleAdvantage,
    StyleAdvantageReliability,
    build_style_advantage,
)
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
        ability_scorer: AbilityScorer | None = None,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster or RuleBasedRpciForecaster()
        self._scorer = scorer or PaceAdaptabilityScorer()
        self._mart_repo = mart_repo
        self._commenter = comment_generator or RuleBasedCommentGenerator()
        self._ability_scorer = ability_scorer or AbilityScorer()

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
        history_by_horse_no: dict[int, tuple[tuple[RaceEntry, Race], ...]] = {}
        for e in entries:
            history = self._load_history(e.ketto_num, race)
            history_by_horse_no[e.horse_no] = history
            style, style_confidence, early_position, early_sample_size = (
                self._resolve_style_evidence(history, race)
            )
            course_aptitude = self._build_course_aptitude_profile(history, race)
            profiles.append(
                HorsePaceProfile(
                    horse_no=e.horse_no,
                    running_style=style,
                    distance_aptitude_m=course_aptitude.distance_aptitude_m,
                    weak_on_off_track=course_aptitude.weak_on_off_track,
                    pace_affinity=self._build_affinity_profile(
                        e.ketto_num, style, race, history
                    ),
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
            sample = self._build_front_pace_sample(e.horse_no, style, history)
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

        formation_prediction = predict_formation(tuple(formation_inputs))
        horse_numbers_confirmed = formation_prediction is not None
        scenario = build_pace_scenario(
            forecast,
            fit_results,
            profiles,
            horse_numbers_confirmed=horse_numbers_confirmed,
        )
        style_advantage = build_style_advantage(
            forecast.value,
            race.track_type,
            tuple(p.running_style for p in profiles),
            venue_code=race.jyo_cd,
            race_date=race.race_date,
            distance_m=race.distance_m,
        )

        name_map = self._repo.find_horse_names(e.ketto_num for e in entries if e.ketto_num)
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

        abilities = tuple(
            self._build_ability_score(
                e.horse_no,
                e.ketto_num,
                race,
                history_by_horse_no[e.horse_no],
            )
            for e in entries
        )
        integrated = build_integrated_ranking(abilities, tuple(fit_results))

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
            horse_numbers_confirmed=horse_numbers_confirmed,
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
            integrated_ranking=_to_integrated_ranking_output(
                integrated, name_map, ketto_by_no, frame_no_by_no
            ),
        )

    def _load_history(
        self, ketto_num: str, target_race: Race
    ) -> tuple[tuple[RaceEntry, Race], ...]:
        """同一予想内で共用する、予想日より前の確定成績とレース情報を読む。"""
        if not ketto_num:
            return ()
        entries = self._repo.find_horse_recent_entries(
            ketto_num,
            limit=20,
            before=target_race.race_date,
        )
        history: list[tuple[RaceEntry, Race]] = []
        for entry in entries:
            past_race = self._repo.find_by_key(entry.race_key)
            if past_race is not None:
                history.append((entry, past_race))
        return tuple(history)

    def _resolve_style_evidence(
        self,
        history: tuple[tuple[RaceEntry, Race], ...],
        target_race: Race,
    ) -> tuple[RunningStyleLabel, float, float | None, int]:
        """脚質と、隊列予想に使う近走序盤位置の証拠をまとめて返す。"""
        if not history:
            return RunningStyleLabel.FLEXIBLE, 0.0, None, 0
        early_position_items: list[int] = []
        style_histories: list[RunningStyleHistory] = []
        for entry, past_race in history[:5]:
            early_position = entry.corner_1 if entry.corner_1 is not None else entry.corner_4
            if early_position is not None:
                early_position_items.append(early_position)
            if entry.corner_4 is None:
                continue
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
        self,
        horse_no: int,
        style: RunningStyleLabel,
        history: tuple[tuple[RaceEntry, Race], ...],
    ) -> FrontRunnerPaceSample | None:
        """逃げ・先行候補が近10走で「前で運んだとき」に作ったペース傾向を集計する（rule-v2）。

        前付け（1角通過≤2、無ければ4角通過≤2）の過去走だけを対象に、その馬自身の
        PCI（欠損時は当該レースの実績RPCIで補完）を平均する。前付け実績が無ければ
        None を返し、想定RPCI 予測は頭数ベース（rule-v1 相当）にフォールバックする。
        """
        if not history or style not in _FRONT_STYLES:
            return None
        paces: list[float] = []
        for entry, past_race in history[:10]:
            if not _led_from_front(entry):
                continue
            pace = entry.pci_actual
            if pace is None:
                pace = past_race.rpci_actual
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
        self,
        ketto_num: str,
        style: RunningStyleLabel,
        target_race: Race,
        history: tuple[tuple[RaceEntry, Race], ...],
    ) -> HorsePaceAffinityProfile:
        """過去好走時のペースから、馬ごとの得意なレース質を作る。"""
        results: list[PaceAffinityRaceResult] = []
        for entry, past_race in history[:12]:
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

    def _build_course_aptitude_profile(
        self,
        history: tuple[tuple[RaceEntry, Race], ...],
        target_race: Race,
    ) -> CourseAptitudeProfile:
        """予想日より前の同一馬場種別の成績から距離・道悪適性を作る。"""
        results: list[CourseAptitudeRaceResult] = []
        for entry, past_race in history:
            results.append(
                CourseAptitudeRaceResult(
                    distance_m=past_race.distance_m,
                    track_type=past_race.track_type,
                    track_condition=past_race.track_condition,
                    finish_pos=entry.finish_pos,
                    field_size=past_race.field_size,
                )
            )
        return build_course_aptitude_profile(
            tuple(results),
            target_track_type=target_race.track_type,
            target_distance_m=target_race.distance_m,
        )

    def _build_ability_score(
        self,
        horse_no: int,
        ketto_num: str,
        target_race: Race,
        history: tuple[tuple[RaceEntry, Race], ...],
    ) -> AbilityScore:
        """近走の着順・grade・賞金・人気から能力指数を算出する。"""
        if not ketto_num:
            return self._ability_scorer.score(horse_no, ())
        results: list[AbilityRaceResult] = []
        for entry, past_race in history[:5]:
            results.append(
                AbilityRaceResult(
                    finish_pos=entry.finish_pos,
                    field_size=past_race.field_size,
                    race_class=past_race.race_class,
                    days_ago=(target_race.race_date - past_race.race_date).days,
                    grade=past_race.grade,
                    popularity=entry.popularity,
                    prize_money=entry.prize_money,
                )
            )
        return self._ability_scorer.score(horse_no, tuple(results))


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
        reliability=(
            "reference"
            if advantage.reliability == StyleAdvantageReliability.REFERENCE
            else "standard"
        ),
        reliability_reason=advantage.reliability_reason,
        entries=[
            StyleAdvantageEntryOutput(style=str(entry.style), score=entry.score)
            for entry in advantage.entries
        ],
        reasons=_to_reason_outputs(advantage.reasons),
    )


def _to_integrated_ranking_output(
    ranking: IntegratedRanking,
    name_map: dict[str, str],
    ketto_by_no: dict[int, str],
    frame_no_by_no: dict[int, int],
) -> IntegratedRankingOutput:
    return IntegratedRankingOutput(
        model_version=ranking.model_version,
        entries=[
            IntegratedEntryOutput(
                horse_no=e.horse_no,
                frame_no=frame_no_by_no.get(e.horse_no, 0),
                horse_name=name_map.get(ketto_by_no.get(e.horse_no, "")),
                rank=e.rank,
                mark=str(e.mark),
                ability_tier=str(e.ability_tier),
                fit_label=str(e.fit_label),
                reasons=_to_reason_outputs(e.reasons),
            )
            for e in ranking.entries
        ],
        reasons=_to_reason_outputs(ranking.reasons),
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
