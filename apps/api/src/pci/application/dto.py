"""アプリケーション層 DTO。

domain エンティティを外部（presentation / ingestion-worker）に露出させないための薄いラッパー。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Literal


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
    body_weight: float | None = None  # 確定時の馬体重（kg）
    popularity: int | None = None  # 単勝人気順（Phase2）
    prize_money: int | None = None  # 獲得本賞金（円・Phase2）


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
    # ペース別の実績が無く、脚質からの推定で埋めている。
    # 「中立」の多くはこれ（docs/DECISIONS.md ADR-2026-08-04）。
    low_evidence: bool = False


@dataclass
class StyleAdvantageEntryOutput:
    """1脚質分の展開有利度（50=互角）。"""

    style: str
    score: float


@dataclass
class StyleAdvantageOutput:
    """脚質別の展開有利度（style-advantage-v4）。"""

    model_version: str
    reliability: Literal["standard", "reference"] = "standard"
    reliability_reason: str | None = None
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
class IntegratedEntryOutput:
    """統合順位予想における1頭分（展開×能力の2軸分類）。"""

    horse_no: int
    frame_no: int
    horse_name: str | None
    rank: int
    mark: str  # 本命 / 対抗 / 穴 / 危険 / 無印
    ability_tier: str  # 上位 / 中位 / 下位 / 評価難
    fit_label: str  # 合致 / 中立 / 不利
    reasons: list[ReasonOutput] = field(default_factory=list)


@dataclass
class IntegratedRankingOutput:
    """展開適性と能力の2軸統合順位予想（integrated-v1）。"""

    model_version: str
    entries: list[IntegratedEntryOutput] = field(default_factory=list)
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
    comment: CommentOutput | None = None
    formation: FormationOutput | None = None
    style_advantage: StyleAdvantageOutput | None = None
    integrated_ranking: IntegratedRankingOutput | None = None


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


@dataclass(frozen=True)
class RaceBoardForecastOutput:
    """一覧表示に必要な最小限の展開予想。内部PCI実数値は公開しない。"""

    pace_label: str
    confidence: float
    top_horse_no: int
    top_horse_name: str | None
    top_fit_label: str
    top_fit_strength: str


@dataclass(frozen=True)
class RaceBoardItemOutput:
    """レース基本情報と、存在する場合だけ軽量予想を返す。"""

    race: RaceSummaryOutput
    forecast: RaceBoardForecastOutput | None = None


@dataclass
class HorsePaceAnalysisOutput:
    """確定後の馬単位ペース分析（各馬 PCI）。"""

    horse_no: int
    frame_no: int
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
class IncompleteRaceOutput:
    """開催日を過ぎても結果が反映されていないレース。"""

    race_key: str
    race_date: str
    jyo_cd: str
    track_type: str
    distance_m: int


@dataclass
class MissingTrackConditionRaceOutput:
    """確定済みだが馬場状態が反映されていないレース。"""

    race_key: str
    race_date: str
    jyo_cd: str
    track_type: str
    distance_m: int


@dataclass
class DuplicateRaceGroupOutput:
    """同一レースとして扱うべき複数レースキー。"""

    race_date: str
    jyo_cd: str
    race_no: str
    race_keys: list[str]


@dataclass(frozen=True)
class ForecastPerformanceGroupOutput:
    """予想精度の表示用集計。PCI/RPCI実数値は含めない。"""

    key: str
    label: str
    sample_size: int
    hit_count: int
    hit_rate: float | None


@dataclass(frozen=True)
class ForecastPerformanceComparisonOutput:
    """直前の同期間における予想精度。"""

    date_from: str
    date_to: str
    groups: list[ForecastPerformanceGroupOutput] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastPerformanceTrendPointOutput:
    """完了した1週間の予想精度。内部実数値は含めない。"""

    date_from: str
    date_to: str
    sample_size: int
    hit_count: int
    hit_rate: float | None


@dataclass(frozen=True)
class ForecastPaceMatrixCellOutput:
    """予想展開に対する実績展開1区分の件数と割合。"""

    key: str
    label: str
    count: int
    rate: float | None


@dataclass(frozen=True)
class ForecastPaceMatrixRowOutput:
    """予想展開1区分について、実績展開3区分への分布を表す。"""

    predicted_key: str
    predicted_label: str
    sample_size: int
    cells: list[ForecastPaceMatrixCellOutput] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastMissOutput:
    """予想区分と実績区分が一致しなかったレース。内部実数値は含めない。"""

    race_key: str
    race_date: str
    jyo_cd: str
    distance_m: int
    track_type: str
    race_class: str | None
    predicted_label: str
    actual_label: str


@dataclass(frozen=True)
class ForecastMissesOutput:
    """不一致レース検索結果。"""

    date_from: str
    date_to: str
    period_days: int
    total_count: int
    offset: int
    limit: int
    items: list[ForecastMissOutput] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastPerformanceOutput:
    """直近期間の展開ラベル的中率サマリー。"""

    date_from: str
    date_to: str
    period_days: int
    eligible_race_count: int
    sample_size: int
    coverage_rate: float | None
    hit_count: int
    hit_rate: float | None
    confidence_review_target: int
    confidence_review_ready: bool
    previous_period: ForecastPerformanceComparisonOutput
    groups: list[ForecastPerformanceGroupOutput] = field(default_factory=list)
    confidence_groups: list[ForecastPerformanceGroupOutput] = field(default_factory=list)
    confidence_cohort_groups: list[ForecastPerformanceGroupOutput] = field(default_factory=list)
    pace_matrix: list[ForecastPaceMatrixRowOutput] = field(default_factory=list)
    weekly_trend: list[ForecastPerformanceTrendPointOutput] = field(default_factory=list)
    recent_misses: list[ForecastMissOutput] = field(default_factory=list)


@dataclass
class IngestStatusOutput:
    """取り込みバッチの鮮度サマリ（GetIngestStatusUseCase の出力）。

    ingest_log を1件も持たない環境（開発/fixture運用）では has_history=False とし、
    「監視対象外」であって「異常」ではないことを区別する。
    """

    has_history: bool
    recommended_sync_days_back: int
    last_success_at: str | None = None
    last_success_step: str | None = None
    last_attempt_failed: bool = False
    days_since_last_success: int | None = None
    is_stale: bool = False
    recent_failures: list[IngestFailureOutput] = field(default_factory=list)
    has_incomplete_races: bool = False
    incomplete_race_count: int = 0
    incomplete_races: list[IncompleteRaceOutput] = field(default_factory=list)
    race_metadata_date_from: str = ""
    race_metadata_date_to: str = ""
    has_missing_track_conditions: bool = False
    missing_track_condition_count: int = 0
    missing_track_condition_races: list[MissingTrackConditionRaceOutput] = field(
        default_factory=list
    )
    has_duplicate_races: bool = False
    duplicate_race_group_count: int = 0
    duplicate_race_groups: list[DuplicateRaceGroupOutput] = field(default_factory=list)
