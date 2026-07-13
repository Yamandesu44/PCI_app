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
class CommentOutput:
    """展開コメント（自然文の解説）の DTO。生成器の model_version を必ず付す。"""

    headline: str
    body: list[str] = field(default_factory=list)
    model_version: str = ""
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class HorseFitOutput:
    """ForecastRaceUseCase の馬単位出力。

    frame_no=0 は特別登録段階で枠順未確定を意味し、その場合 horse_no も
    暫定の仮番号（ingest_entries の連番割当）である可能性がある。表示側は
    frame_no で確定/未確定を判定し、未確定時は horse_no を確定馬番として
    扱わないこと（FormationHorseOutput と同じ判定基準）。
    """

    horse_no: int
    frame_no: int
    horse_name: str | None
    running_style: str
    pai: float
    fit_label: str
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class StyleAdvantageEntryOutput:
    """1脚質分の展開有利度（50=互角）。"""

    style: str
    score: float


@dataclass
class StyleAdvantageOutput:
    """脚質別の展開有利度（style-advantage-v1）。"""

    model_version: str
    entries: list[StyleAdvantageEntryOutput] = field(default_factory=list)
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class FormationHorseOutput:
    """隊列予想における1頭分の配置。"""

    horse_no: int
    frame_no: int
    horse_name: str | None
    running_style: str
    confidence_label: str
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class FormationGroupOutput:
    """先頭・好位・中団・後方のいずれかの隊列グループ。"""

    key: str
    label: str
    horses: list[FormationHorseOutput] = field(default_factory=list)


@dataclass
class FormationOutput:
    """枠順確定後にのみ返す序盤隊列予想。"""

    model_version: str
    groups: list[FormationGroupOutput] = field(default_factory=list)


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
    comment: CommentOutput | None = None
    formation: FormationOutput | None = None
    style_advantage: StyleAdvantageOutput | None = None


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
class RaceSummaryOutput:
    """レース一覧の1件分（トップ画面のレース選択用）。

    status により遷移先（出走前=展開予想／確定後=ペース分析）を判別できる。
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


@dataclass
class HorsePaceAnalysisOutput:
    """確定後の馬単位ペース分析（各馬 PCI）。"""

    horse_no: int
    finish_pos: int | None = None
    running_style: str | None = None
    pci: float | None = None
    agari_3f_s: float | None = None
    is_pci3_contributor: bool = False
    horse_name: str | None = None


@dataclass
class ForecastAccuracyOutput:
    """出走前の想定RPCIと実績RPCIの答え合わせ結果（GetPaceAnalysisUseCase の出力）。"""

    predicted_rpci: float
    predicted_label: str
    actual_rpci: float
    actual_label: str
    error: float
    label_hit: bool
    model_version: str


@dataclass
class PaceAnalysisOutput:
    """GetPaceAnalysisUseCase の出力（確定後: 各馬PCI・実績RPCI・PCI3）。

    PCI 系指標のため `formula_version` を必ず付す（設計書 04 §3）。
    forecast_accuracy は出走前予測が保存されている場合のみ付与される（答え合わせ）。
    """

    race_key: str
    formula_version: str
    field_size: int
    sample_size: int
    rpci_actual: float | None = None
    pci3_actual: float | None = None
    horses: list[HorsePaceAnalysisOutput] = field(default_factory=list)
    reasons: list[ReasonOutput] = field(default_factory=list)
    comment: CommentOutput | None = None
    forecast_accuracy: ForecastAccuracyOutput | None = None


@dataclass
class IngestFailureOutput:
    """直近の取り込み失敗1件（GetIngestStatusUseCase の出力の一部）。"""

    batch_date: str
    step: str
    mode: str
    started_at: str
    error_summary: str


@dataclass
class IngestStatusOutput:
    """取り込みバッチの鮮度サマリ（GetIngestStatusUseCase の出力）。

    ingest_log を1件も持たない環境（開発/fixture運用）では has_history=False とし、
    「監視対象外」であって「異常」ではないことを区別する。
    """

    has_history: bool
    last_success_at: str | None = None
    last_success_step: str | None = None
    last_attempt_failed: bool = False
    days_since_last_success: int | None = None
    is_stale: bool = False
    recent_failures: list[IngestFailureOutput] = field(default_factory=list)
