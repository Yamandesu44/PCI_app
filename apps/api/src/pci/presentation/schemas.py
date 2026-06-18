"""API レスポンススキーマ（Pydantic）。

application 層の DTO を HTTP/JSON 契約へマッピングする。
domain/application からは独立（presentation 層の詳細）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from pci.application.dto import ForecastOutput, PaceAnalysisOutput, RaceDetailOutput


class ReasonSchema(BaseModel):
    """説明可能性の根拠（要因コード・説明・寄与度）。"""

    code: str
    description: str
    contribution: float | None = None


class HorseFitSchema(BaseModel):
    """馬単位の展開適性（PAI）。"""

    horse_no: int
    running_style: str
    pai: float = Field(ge=0.0, le=100.0)
    fit_label: str
    reasons: list[ReasonSchema] = []


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
                    running_style=h.running_style,
                    pai=h.pai,
                    fit_label=h.fit_label,
                    reasons=[ReasonSchema(**vars(r)) for r in h.reasons],
                )
                for h in dto.horses
            ],
            forecast_reasons=[ReasonSchema(**vars(r)) for r in dto.forecast_reasons],
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
    running_style: str | None = None
    pci: float | None = None
    agari_3f_s: float | None = None
    is_pci3_contributor: bool = False


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
                    running_style=h.running_style,
                    pci=h.pci,
                    agari_3f_s=h.agari_3f_s,
                    is_pci3_contributor=h.is_pci3_contributor,
                )
                for h in dto.horses
            ],
            reasons=[ReasonSchema(**vars(r)) for r in dto.reasons],
        )


class HealthSchema(BaseModel):
    status: str = "ok"
