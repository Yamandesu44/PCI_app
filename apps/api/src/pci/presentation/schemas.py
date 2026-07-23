"""API レスポンススキーマ（Pydantic）。

application 層の DTO を HTTP/JSON 契約へマッピングする。
domain/application からは独立（presentation 層の詳細）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pci.application.dto import (
    CommentOutput,
    ForecastOutput,
    IngestStatusOutput,
    PaceAnalysisOutput,
    RaceBoardItemOutput,
    RaceDetailOutput,
    RaceSummaryOutput,
)


class ReasonSchema(BaseModel):
    """説明可能性の根拠（要因コード・説明・寄与度）。"""

    code: str
    description: str
    contribution: float | None = None


class CommentSchema(BaseModel):
    """展開コメント（自然文の解説）。生成器の model_version を付す。"""

    headline: str
    body: list[str] = []
    model_version: str
    reasons: list[ReasonSchema] = []

    @classmethod
    def from_dto(cls, dto: CommentOutput) -> CommentSchema:
        return cls(
            headline=dto.headline,
            body=dto.body,
            model_version=dto.model_version,
            reasons=[ReasonSchema(**vars(r)) for r in dto.reasons],
        )


class HorseFitSchema(BaseModel):
    """馬単位の展開適性（PAI）。

    frame_no=0 は枠順未確定（特別登録段階）。horse_no はその場合、
    確定した公式馬番ではない可能性がある（FormationHorseSchema と同じ判定基準）。
    """

    horse_no: int
    frame_no: int
    horse_name: str | None = None
    running_style: str
    pai: float = Field(ge=0.0, le=100.0)
    fit_label: str
    reasons: list[ReasonSchema] = []


class StyleAdvantageEntrySchema(BaseModel):
    """1脚質分の展開有利度（50=互角、大きいほど今回の流れが向く）。"""

    style: str
    score: float = Field(ge=0.0, le=100.0)


class StyleAdvantageSchema(BaseModel):
    """脚質別の展開有利度（style-advantage-v3）。"""

    model_version: str
    reliability: Literal["standard", "reference"] = "standard"
    reliability_reason: str | None = None
    entries: list[StyleAdvantageEntrySchema] = []
    reasons: list[ReasonSchema] = []


class IntegratedEntrySchema(BaseModel):
    """統合順位予想の1頭分（展開×能力の2軸分類）。

    frame_no=0 は枠順未確定（HorseFitSchema と同じ判定基準）。
    """

    horse_no: int
    frame_no: int
    horse_name: str | None = None
    rank: int
    mark: str  # 本命 / 対抗 / 穴 / 危険 / 無印
    ability_tier: str  # 上位 / 中位 / 下位 / 評価難
    fit_label: str  # 合致 / 中立 / 不利
    reasons: list[ReasonSchema] = []


class IntegratedRankingSchema(BaseModel):
    """展開適性と能力の2軸統合順位予想（integrated-v1）。"""

    model_version: str
    entries: list[IntegratedEntrySchema] = []
    reasons: list[ReasonSchema] = []


class FormationHorseSchema(BaseModel):
    """隊列予想に表示する1頭分の配置。"""

    horse_no: int
    frame_no: int = Field(ge=1, le=8)
    horse_name: str | None = None
    running_style: str
    confidence_label: str
    reasons: list[ReasonSchema] = []


class FormationGroupSchema(BaseModel):
    """先頭・好位・中団・後方の隊列グループ。"""

    key: str
    label: str
    horses: list[FormationHorseSchema] = []


class FormationSchema(BaseModel):
    """枠順確定後にのみ返す序盤隊列予想。"""

    model_version: str
    groups: list[FormationGroupSchema] = []


class ForecastSchema(BaseModel):
    """レース展開予想（想定RPCI + 展開シナリオ + 各馬 PAI）。"""

    race_key: str
    predicted_rpci: float
    pace_label: str
    confidence: float
    model_version: str
    scenario_headline: str
    scenario_detail: str
    front_runners: list[int] = []
    beneficiaries: list[int] = []
    horses: list[HorseFitSchema] = []
    forecast_reasons: list[ReasonSchema] = []
    comment: CommentSchema | None = None
    formation: FormationSchema | None = None
    style_advantage: StyleAdvantageSchema | None = None
    integrated_ranking: IntegratedRankingSchema | None = None

    @classmethod
    def from_dto(cls, dto: ForecastOutput) -> ForecastSchema:
        return cls(
            race_key=dto.race_key,
            predicted_rpci=dto.predicted_rpci,
            pace_label=dto.pace_label,
            confidence=dto.confidence,
            model_version=dto.model_version,
            scenario_headline=dto.scenario_headline,
            scenario_detail=dto.scenario_detail,
            front_runners=dto.front_runners,
            beneficiaries=dto.beneficiaries,
            horses=[
                HorseFitSchema(
                    horse_no=h.horse_no,
                    frame_no=h.frame_no,
                    horse_name=h.horse_name,
                    running_style=h.running_style,
                    pai=h.pai,
                    fit_label=h.fit_label,
                    reasons=[ReasonSchema(**vars(r)) for r in h.reasons],
                )
                for h in dto.horses
            ],
            forecast_reasons=[ReasonSchema(**vars(r)) for r in dto.forecast_reasons],
            comment=CommentSchema.from_dto(dto.comment) if dto.comment else None,
            formation=(
                FormationSchema(
                    model_version=dto.formation.model_version,
                    groups=[
                        FormationGroupSchema(
                            key=group.key,
                            label=group.label,
                            horses=[
                                FormationHorseSchema(
                                    horse_no=horse.horse_no,
                                    frame_no=horse.frame_no,
                                    horse_name=horse.horse_name,
                                    running_style=horse.running_style,
                                    confidence_label=horse.confidence_label,
                                    reasons=[ReasonSchema(**vars(r)) for r in horse.reasons],
                                )
                                for horse in group.horses
                            ],
                        )
                        for group in dto.formation.groups
                    ],
                )
                if dto.formation
                else None
            ),
            style_advantage=(
                StyleAdvantageSchema(
                    model_version=dto.style_advantage.model_version,
                    reliability=dto.style_advantage.reliability,
                    reliability_reason=dto.style_advantage.reliability_reason,
                    entries=[
                        StyleAdvantageEntrySchema(style=entry.style, score=entry.score)
                        for entry in dto.style_advantage.entries
                    ],
                    reasons=[ReasonSchema(**vars(r)) for r in dto.style_advantage.reasons],
                )
                if dto.style_advantage
                else None
            ),
            integrated_ranking=(
                IntegratedRankingSchema(
                    model_version=dto.integrated_ranking.model_version,
                    entries=[
                        IntegratedEntrySchema(
                            horse_no=entry.horse_no,
                            frame_no=entry.frame_no,
                            horse_name=entry.horse_name,
                            rank=entry.rank,
                            mark=entry.mark,
                            ability_tier=entry.ability_tier,
                            fit_label=entry.fit_label,
                            reasons=[ReasonSchema(**vars(r)) for r in entry.reasons],
                        )
                        for entry in dto.integrated_ranking.entries
                    ],
                    reasons=[ReasonSchema(**vars(r)) for r in dto.integrated_ranking.reasons],
                )
                if dto.integrated_ranking
                else None
            ),
        )


class RaceSummarySchema(BaseModel):
    """レース一覧の1件分（トップ画面のレース選択用）。

    status で遷移先（entries=展開予想／result=ペース分析）を判別する。
    """

    race_key: str
    race_date: str
    jyo_cd: str
    distance_m: int
    track_type: str
    status: str
    field_size: int
    grade: str | None = None
    race_class: str | None = None

    @classmethod
    def from_dto(cls, dto: RaceSummaryOutput) -> RaceSummarySchema:
        return cls(
            race_key=dto.race_key,
            race_date=dto.race_date,
            jyo_cd=dto.jyo_cd,
            distance_m=dto.distance_m,
            track_type=dto.track_type,
            status=dto.status,
            field_size=dto.field_size,
            grade=dto.grade,
            race_class=dto.race_class,
        )


class EntryDetailSchema(BaseModel):
    """出走馬の詳細（確定済みなら成績を含む）。"""

    horse_no: int
    frame_no: int
    ketto_num: str
    running_style: str | None = None
    pci_actual: float | None = None
    finish_pos: int | None = None


class RaceDetailSchema(BaseModel):
    """レース詳細（core 層の情報 + 確定指標）。"""

    race_key: str
    race_date: str
    jyo_cd: str
    distance_m: int
    track_type: str
    status: str
    field_size: int
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None
    rpci_actual: float | None = None
    pci3_actual: float | None = None
    entries: list[EntryDetailSchema] = []

    @classmethod
    def from_dto(cls, dto: RaceDetailOutput) -> RaceDetailSchema:
        return cls(
            race_key=dto.race_key,
            race_date=dto.race_date,
            jyo_cd=dto.jyo_cd,
            distance_m=dto.distance_m,
            track_type=dto.track_type,
            status=dto.status,
            field_size=dto.field_size,
            track_condition=dto.track_condition,
            weather=dto.weather,
            grade=dto.grade,
            race_class=dto.race_class,
            rpci_actual=dto.rpci_actual,
            pci3_actual=dto.pci3_actual,
            entries=[EntryDetailSchema(**vars(e)) for e in dto.entries],
        )


class HorsePaceAnalysisSchema(BaseModel):
    """確定後の馬単位ペース分析（各馬 PCI）。"""

    horse_no: int
    finish_pos: int | None = None
    horse_name: str | None = None
    running_style: str | None = None
    pci: float | None = None
    agari_3f_s: float | None = None
    is_pci3_contributor: bool = False


class ForecastAccuracySchema(BaseModel):
    """出走前の想定RPCIと実績RPCIの答え合わせ結果。"""

    predicted_rpci: float
    predicted_label: str
    actual_rpci: float
    actual_label: str
    error: float
    label_hit: bool
    model_version: str


class PaceAnalysisSchema(BaseModel):
    """確定後ペース分析（各馬PCI・実績RPCI・PCI3）。PCI 系は formula_version を返す。"""

    race_key: str
    formula_version: str
    field_size: int
    sample_size: int
    rpci_actual: float | None = None
    pci3_actual: float | None = None
    horses: list[HorsePaceAnalysisSchema] = []
    reasons: list[ReasonSchema] = []
    comment: CommentSchema | None = None
    forecast_accuracy: ForecastAccuracySchema | None = None

    @classmethod
    def from_dto(cls, dto: PaceAnalysisOutput) -> PaceAnalysisSchema:
        return cls(
            race_key=dto.race_key,
            formula_version=dto.formula_version,
            field_size=dto.field_size,
            sample_size=dto.sample_size,
            rpci_actual=dto.rpci_actual,
            pci3_actual=dto.pci3_actual,
            horses=[
                HorsePaceAnalysisSchema(
                    horse_no=h.horse_no,
                    finish_pos=h.finish_pos,
                    horse_name=h.horse_name,
                    running_style=h.running_style,
                    pci=h.pci,
                    agari_3f_s=h.agari_3f_s,
                    is_pci3_contributor=h.is_pci3_contributor,
                )
                for h in dto.horses
            ],
            reasons=[ReasonSchema(**vars(r)) for r in dto.reasons],
            comment=CommentSchema.from_dto(dto.comment) if dto.comment else None,
            forecast_accuracy=(
                ForecastAccuracySchema(**vars(dto.forecast_accuracy))
                if dto.forecast_accuracy
                else None
            ),
        )


class IngestFailureSchema(BaseModel):
    """直近の取り込み失敗1件。"""

    batch_date: str
    step: str
    mode: str
    started_at: str
    error_summary: str


class IncompleteRaceSchema(BaseModel):
    """開催日を過ぎても結果が反映されていないレース。"""

    race_key: str
    race_date: str
    jyo_cd: str
    track_type: str
    distance_m: int


class IngestStatusSchema(BaseModel):
    """取り込みバッチの鮮度サマリ（トップ画面の更新状況表示に使用）。

    has_history=False は「ログが無い（開発/fixture環境等）」を表し、異常を意味しない。
    """

    has_history: bool
    recommended_sync_days_back: int
    last_success_at: str | None = None
    last_success_step: str | None = None
    last_attempt_failed: bool = False
    days_since_last_success: int | None = None
    is_stale: bool = False
    recent_failures: list[IngestFailureSchema] = []
    has_incomplete_races: bool = False
    incomplete_race_count: int = 0
    incomplete_races: list[IncompleteRaceSchema] = []

    @classmethod
    def from_dto(cls, dto: IngestStatusOutput) -> IngestStatusSchema:
        return cls(
            has_history=dto.has_history,
            last_success_at=dto.last_success_at,
            last_success_step=dto.last_success_step,
            last_attempt_failed=dto.last_attempt_failed,
            days_since_last_success=dto.days_since_last_success,
            is_stale=dto.is_stale,
            recent_failures=[IngestFailureSchema(**vars(f)) for f in dto.recent_failures],
            has_incomplete_races=dto.has_incomplete_races,
            incomplete_race_count=dto.incomplete_race_count,
            recommended_sync_days_back=dto.recommended_sync_days_back,
            incomplete_races=[IncompleteRaceSchema(**vars(r)) for r in dto.incomplete_races],
        )


class RaceBoardForecastSchema(BaseModel):
    """一覧用の軽量予想。PCI/RPCIの内部実数値は含めない。"""

    pace_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    top_horse_no: int
    top_horse_name: str | None = None
    top_fit_label: str
    top_fit_strength: str


class RaceBoardItemSchema(BaseModel):
    """レースボードの1件分。"""

    race: RaceSummarySchema
    forecast: RaceBoardForecastSchema | None = None

    @classmethod
    def from_dto(cls, dto: RaceBoardItemOutput) -> RaceBoardItemSchema:
        return cls(
            race=RaceSummarySchema.from_dto(dto.race),
            forecast=(
                RaceBoardForecastSchema(**vars(dto.forecast)) if dto.forecast else None
            ),
        )


class HealthSchema(BaseModel):
    status: str = "ok"


class ReadinessSchema(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable", "schema_outdated"]
    message: str | None = None
    action: str | None = None
