"""アプリケーション層 DTO。

domain エンティティを外部（presentation / ingestion-worker）に露出させないための薄いラッパー。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntryInput:
    """1頭分の出走情報（RegisterRaceEntriesUseCase の入力）。"""

    horse_no: int
    frame_no: int
    ketto_num: str
    weight: float
    jockey_code: str
    trainer_code: str


@dataclass(frozen=True)
class ResultInput:
    """1頭分の確定成績（RecordRaceResultUseCase の入力）。"""

    horse_no: int
    finish_pos: int
    race_time_s: float
    agari_3f_s: float
    corner_1: int | None = None
    corner_2: int | None = None
    corner_3: int | None = None
    corner_4: int | None = None


@dataclass(frozen=True)
class RaceInfo:
    """レース基本情報（RegisterRaceEntriesUseCase の入力）。"""

    race_key: str
    race_date: datetime.date
    jyo_cd: str
    distance_m: int
    track_type: str
    field_size: int
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None


@dataclass
class RaceResultOutput:
    """RecordRaceResultUseCase の出力。"""

    race_key: str
    rpci: float
    pci3: float | None
    formula_version: str
    entry_pcis: dict[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReasonOutput:
    """説明可能性 Reason の DTO 表現（presentation 層が JSON 化する）。"""

    code: str
    description: str
    contribution: float | None = None


@dataclass
class HorseFitOutput:
    """ForecastRaceUseCase の馬単位出力。"""

    horse_no: int
    running_style: str
    pai: float
    fit_label: str
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class ForecastOutput:
    """ForecastRaceUseCase の出力（想定RPCI + 展開シナリオ + 各馬 PAI）。"""

    race_key: str
    predicted_rpci: float
    pace_label: str
    confidence: float
    model_version: str
    scenario_headline: str
    scenario_detail: str
    front_runners: list[int] = field(default_factory=list)
    beneficiaries: list[int] = field(default_factory=list)
    horses: list[HorseFitOutput] = field(default_factory=list)
    forecast_reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class EntryDetailOutput:
    """レース詳細の馬単位出力（確定済みなら成績を含む）。"""

    horse_no: int
    frame_no: int
    ketto_num: str
    running_style: str | None = None
    pci_actual: float | None = None
    finish_pos: int | None = None


@dataclass
class RaceDetailOutput:
    """GetRaceDetailUseCase の出力（core 層のレース情報 + 確定指標）。"""

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
    entries: list[EntryDetailOutput] = field(default_factory=list)


@dataclass
class HorsePaceAnalysisOutput:
    """確定後の馬単位ペース分析（各馬 PCI）。"""

    horse_no: int
    finish_pos: int | None = None
    running_style: str | None = None
    pci: float | None = None
    agari_3f_s: float | None = None
    is_pci3_contributor: bool = False


@dataclass
class PaceAnalysisOutput:
    """GetPaceAnalysisUseCase の出力（確定後: 各馬PCI・実績RPCI・PCI3）。

    PCI 系指標のため `formula_version` を必ず付す（設計書 04 §3）。
    """

    race_key: str
    formula_version: str
    field_size: int
    sample_size: int
    rpci_actual: float | None = None
    pci3_actual: float | None = None
    horses: list[HorsePaceAnalysisOutput] = field(default_factory=list)
    reasons: list[ReasonOutput] = field(default_factory=list)
