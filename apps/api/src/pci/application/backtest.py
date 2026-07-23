"""想定RPCI / PAI のバックテスト（予測精度の検証基盤）。

目的: 確定済みレースを「未確定だった時点」に巻き戻して予測を再現し、実績と
比較することで、本プロダクトの中核（展開予想）の精度を数値化する。

測定する2軸:
    1. 想定RPCI の誤差     : predicted_rpci vs rpci_actual（MAE / RMSE / バイアス /
                             展開3分類ラベルの的中率）
    2. PAI のリフト        : PAI 帯ごとの「好走率」。高PAI ほど好走率が高ければ、
                             PAI が展開合致を捉えられている証拠になる。

lookahead 防止が要: 各レースの予測には「そのレース当日より前」の馬履歴だけを
使う。`_AsOfRaceRepository` が find_horse_recent_entries に開催日カットオフを
注入することで、未来のデータ参照（情報漏洩）を防ぐ。

予測経路は本番の ForecastRaceUseCase をそのまま使う（mart 保存なし）。これにより
「出荷されるロジックそのもの」を検証する（評価専用の別経路を作らない）。
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from pci.application.dto import ForecastOutput
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.domain.pace.ability import (
    DEFAULT_WEIGHTS as DEFAULT_ABILITY_WEIGHTS,
)
from pci.domain.pace.ability import (
    AbilityScorer,
    AbilityWeights,
)
from pci.domain.pace.adaptability import (
    DEFAULT_WEIGHTS as DEFAULT_PAI_WEIGHTS,
)
from pci.domain.pace.adaptability import (
    PaceAdaptabilityScorer,
    PaiWeights,
)
from pci.domain.pace.affinity import is_good_run
from pci.domain.pace.commentary import CommentGenerator
from pci.domain.pace.rpci_forecast import (
    DEFAULT_WEIGHTS as DEFAULT_RULE_WEIGHTS,
)
from pci.domain.pace.rpci_forecast import (
    PaceLabel,
    RpciForecaster,
    RuleWeights,
    classify_pace,
)
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.pace.style_advantage import build_style_advantage
from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey

DEFAULT_BAND_EDGES: tuple[int, ...] = (0, 20, 40, 60, 80, 100)
_SCOREABLE_STYLES = frozenset(
    {
        RunningStyleLabel.ESCAPE,
        RunningStyleLabel.FRONT,
        RunningStyleLabel.STALKER,
        RunningStyleLabel.CLOSER,
    }
)
StyleAdvantageBreakdownDimension = Literal[
    "year",
    "distance",
    "track-condition",
    "distance-track-condition",
]


class _AsOfRaceRepository:
    """find_horse_recent_entries に開催日カットオフを差し込む読み取りラッパー。

    ForecastRaceUseCase は履歴取得を 2 引数で呼ぶため、ここで before=as_of を
    強制注入し、予測対象レース当日以降のデータを履歴から除外する。
    その他のメソッドは内側リポジトリへ素通しする。
    """

    def __init__(self, inner: RaceRepository, as_of: datetime.date) -> None:
        self._inner = inner
        self._as_of = as_of

    def find_horse_recent_entries(
        self, ketto_num: str, limit: int = 5, before: datetime.date | None = None
    ) -> list[RaceEntry]:
        # 呼び出し側指定の before があればより厳しい方（早い日付）を採用する。
        cutoff = self._as_of if before is None else min(self._as_of, before)
        return self._inner.find_horse_recent_entries(ketto_num, limit, before=cutoff)

    # ----- 以下は素通し -----
    def find_by_key(self, key: RaceKey) -> Race | None:
        return self._inner.find_by_key(key)

    def find_entries(self, key: RaceKey) -> list[RaceEntry]:
        return self._inner.find_entries(key)

    def list_recent_races(self, limit: int = 50) -> list[Race]:
        return self._inner.list_recent_races(limit)

    def list_race_dates(self) -> list[datetime.date]:
        return self._inner.list_race_dates()

    def list_races_by_date(self, date: datetime.date) -> list[Race]:
        return self._inner.list_races_by_date(date)

    def save_race(self, race: Race) -> None:
        self._inner.save_race(race)

    def save_entry(self, entry: RaceEntry) -> None:
        self._inner.save_entry(entry)

    def delete_entries_not_in(self, key: RaceKey, horse_nos: set[int]) -> int:
        return self._inner.delete_entries_not_in(key, horse_nos)

    def delete_race(self, key: RaceKey) -> bool:
        return self._inner.delete_race(key)

    def find_horse_names(self, ketto_nums: Iterable[str]) -> dict[str, str]:
        return self._inner.find_horse_names(ketto_nums)

    def save_horse(self, horse: Horse) -> None:
        self._inner.save_horse(horse)

    def save_jockey(self, jockey: Jockey) -> None:
        self._inner.save_jockey(jockey)

    def save_trainer(self, trainer: Trainer) -> None:
        self._inner.save_trainer(trainer)

    def ensure_horses(self, ketto_nums: Iterable[str]) -> None:
        self._inner.ensure_horses(ketto_nums)

    def ensure_jockeys(self, codes: Iterable[str]) -> None:
        self._inner.ensure_jockeys(codes)

    def ensure_trainers(self, codes: Iterable[str]) -> None:
        self._inner.ensure_trainers(codes)


# ----- 観測サンプル -----


@dataclass(frozen=True)
class RpciSample:
    """1レース分の想定RPCI 予測と実績のペア。"""

    race_key: str
    predicted: float
    actual: float
    predicted_label: PaceLabel
    actual_label: PaceLabel
    track_type: str = ""

    @property
    def error(self) -> float:
        return self.predicted - self.actual


@dataclass(frozen=True)
class HorseSample:
    """1頭分の PAI と好走実績のペア。"""

    race_key: str
    horse_no: int
    pai: float
    good_run: bool
    track_type: str = ""


@dataclass(frozen=True)
class IntegratedSample:
    """統合順位1頭分と実績の比較サンプル。"""

    race_key: str
    horse_no: int
    rank: int
    finish_pos: int | None
    good_run: bool


@dataclass(frozen=True)
class StyleAdvantageSample:
    """予測した脚質別有利度と、その馬の好走実績の比較サンプル。"""

    race_key: str
    horse_no: int
    score: float
    good_run: bool


# ----- 集計結果 -----


@dataclass(frozen=True)
class RpciAccuracy:
    """想定RPCI の誤差サマリ。"""

    n: int
    mae: float
    rmse: float
    bias: float
    label_accuracy: float
    per_label_accuracy: dict[str, float]


@dataclass(frozen=True)
class PaiBand:
    """PAI 帯ごとの好走率。"""

    lo: int
    hi: int
    n: int
    good_runs: int

    @property
    def good_rate(self) -> float:
        return self.good_runs / self.n if self.n else 0.0


@dataclass(frozen=True)
class PaiLift:
    """PAI のリフト（高PAI ほど好走するか）サマリ。"""

    n: int
    baseline_rate: float
    bands: list[PaiBand]
    point_biserial: float
    top_band_lift: float  # 最上位帯の好走率 / 全体好走率


@dataclass(frozen=True)
class IntegratedAccuracy:
    """統合順位の実績指標。AbilityWeights比較時の共通評価軸として使う。"""

    n_races: int
    n_horses: int
    top1_win_rate: float
    top1_good_rate: float
    top3_good_capture_rate: float


@dataclass(frozen=True)
class StyleAdvantageLift:
    """脚質別有利度が好走率を分離できているかを示すサマリ。"""

    n: int
    baseline_rate: float
    advantaged_n: int
    advantaged_rate: float
    advantaged_lift: float
    disadvantaged_n: int
    disadvantaged_rate: float
    disadvantaged_lift: float
    rate_gap: float
    point_biserial: float


@dataclass(frozen=True)
class StyleAdvantageAttribution:
    """ペース予測と脚質予測を入れ替えて有利度の誤差要因を比較する診断結果。"""

    n_races: int
    n_horses: int
    skipped: int
    forecast: StyleAdvantageLift | None
    actual_pace: StyleAdvantageLift | None
    actual_style: StyleAdvantageLift | None
    oracle: StyleAdvantageLift | None


@dataclass(frozen=True)
class StyleAdvantageBreakdownGroup:
    """確定値による脚質別有利度を、1つの開催条件で集計した結果。"""

    label: str
    n_races: int
    lift: StyleAdvantageLift | None


@dataclass(frozen=True)
class AbilityWeightProfile:
    """実DB比較に使う能力重みの候補。本番設定は書き換えない。"""

    name: str
    description: str
    weights: AbilityWeights


DEFAULT_ABILITY_WEIGHT_PROFILES: tuple[AbilityWeightProfile, ...] = (
    AbilityWeightProfile(
        name="current",
        description="現行重み",
        weights=DEFAULT_ABILITY_WEIGHTS,
    ),
    AbilityWeightProfile(
        name="form-only",
        description="近走内容のみ（Phase 1相当）",
        weights=AbilityWeights(weight_form=1.0, weight_prize=0.0, weight_popularity=0.0),
    ),
    AbilityWeightProfile(
        name="form-heavy",
        description="近走内容を重視",
        weights=AbilityWeights(weight_form=0.70, weight_prize=0.20, weight_popularity=0.10),
    ),
    AbilityWeightProfile(
        name="market-aware",
        description="人気の市場支持をやや重視",
        weights=AbilityWeights(weight_form=0.45, weight_prize=0.30, weight_popularity=0.25),
    ),
)


@dataclass(frozen=True)
class AbilityWeightComparison:
    """同一対象レースでの候補重みと現行重みの差。"""

    profile: AbilityWeightProfile
    accuracy: IntegratedAccuracy | None
    delta_top1_win_rate: float | None
    delta_top1_good_rate: float | None
    delta_top3_good_capture_rate: float | None


@dataclass(frozen=True)
class RuleWeightProfile:
    """実DB比較に使うルール重みの候補。本番設定は書き換えない。"""

    name: str
    description: str
    weights: RuleWeights


DEFAULT_RULE_WEIGHT_PROFILES: tuple[RuleWeightProfile, ...] = (
    RuleWeightProfile(
        name="current",
        description="現行重み",
        weights=DEFAULT_RULE_WEIGHTS,
    ),
    RuleWeightProfile(
        name="style-light",
        description="脚質構成の影響を弱める",
        weights=replace(DEFAULT_RULE_WEIGHTS, style_balance_weight=6.0),
    ),
    RuleWeightProfile(
        name="style-heavy",
        description="脚質構成の影響を強める",
        weights=replace(DEFAULT_RULE_WEIGHTS, style_balance_weight=10.0),
    ),
    RuleWeightProfile(
        name="evidence-light",
        description="前付け実績の混合を弱める",
        weights=replace(
            DEFAULT_RULE_WEIGHTS,
            evidence_weight_per_sample=0.075,
            evidence_weight_cap=0.6,
        ),
    ),
    RuleWeightProfile(
        name="evidence-heavy",
        description="前付け実績の混合を強める",
        weights=replace(
            DEFAULT_RULE_WEIGHTS,
            evidence_weight_per_sample=0.125,
            evidence_weight_cap=0.8,
        ),
    ),
)


@dataclass(frozen=True)
class RuleWeightMetrics:
    """候補ルールの精度と現行値との差。"""

    accuracy: RpciAccuracy | None
    delta_mae: float | None
    delta_label_accuracy: float | None


@dataclass(frozen=True)
class RuleWeightComparison:
    """同一対象レースでのルール重み候補の比較結果。"""

    profile: RuleWeightProfile
    combined: RuleWeightMetrics
    turf: RuleWeightMetrics
    dirt: RuleWeightMetrics


@dataclass(frozen=True)
class PaiWeightProfile:
    """実DB比較に使うPAI重みの候補。本番設定は書き換えない。"""

    name: str
    description: str
    weights: PaiWeights


DEFAULT_PAI_WEIGHT_PROFILES: tuple[PaiWeightProfile, ...] = (
    PaiWeightProfile(
        name="current",
        description="現行重み",
        weights=DEFAULT_PAI_WEIGHTS,
    ),
    PaiWeightProfile(
        name="rpci-light",
        description="想定ペース差の減点を弱める",
        weights=replace(DEFAULT_PAI_WEIGHTS, rpci_diff_weight=4.0),
    ),
    PaiWeightProfile(
        name="rpci-heavy",
        description="想定ペース差の減点を強める",
        weights=replace(DEFAULT_PAI_WEIGHTS, rpci_diff_weight=6.0),
    ),
    PaiWeightProfile(
        name="preference-compressed",
        description="脚質ごとの好ペース差を縮める",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            preferred_escape=53.0,
            preferred_front=52.0,
            preferred_stalker=48.0,
            preferred_closer=47.0,
        ),
    ),
    PaiWeightProfile(
        name="preference-expanded",
        description="脚質ごとの好ペース差を広げる",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            preferred_escape=57.0,
            preferred_front=54.0,
            preferred_stalker=46.0,
            preferred_closer=43.0,
        ),
    ),
)


@dataclass(frozen=True)
class PaiWeightMetrics:
    """候補PAI重みのリフトと現行値との差。"""

    lift: PaiLift | None
    delta_point_biserial: float | None
    delta_top_band_lift: float | None


@dataclass(frozen=True)
class PaiWeightComparison:
    """同一対象レースでのPAI重み候補の比較結果。"""

    profile: PaiWeightProfile
    combined: PaiWeightMetrics
    turf: PaiWeightMetrics
    dirt: PaiWeightMetrics


@dataclass(frozen=True)
class BacktestReport:
    """バックテスト全体の結果。"""

    model_version: str
    n_races: int
    n_horses: int
    skipped: int
    rpci: RpciAccuracy | None
    pai: PaiLift | None
    integrated: IntegratedAccuracy | None = None
    style_advantage: StyleAdvantageLift | None = None
    rpci_samples: list[RpciSample] = field(default_factory=list)
    horse_samples: list[HorseSample] = field(default_factory=list)
    integrated_samples: list[IntegratedSample] = field(default_factory=list)
    style_advantage_samples: list[StyleAdvantageSample] = field(default_factory=list)


def summarize_rpci(samples: list[RpciSample]) -> RpciAccuracy | None:
    """想定RPCI 予測の誤差指標を計算する（純粋関数）。"""
    if not samples:
        return None
    n = len(samples)
    errors = [s.error for s in samples]
    mae = sum(abs(e) for e in errors) / n
    rmse = math.sqrt(sum(e * e for e in errors) / n)
    bias = sum(errors) / n
    hits = sum(1 for s in samples if s.predicted_label == s.actual_label)

    per_label: dict[str, float] = {}
    for label in PaceLabel:
        group = [s for s in samples if s.actual_label == label]
        if group:
            correct = sum(1 for s in group if s.predicted_label == label)
            per_label[str(label)] = correct / len(group)
    return RpciAccuracy(
        n=n,
        mae=round(mae, 3),
        rmse=round(rmse, 3),
        bias=round(bias, 3),
        label_accuracy=round(hits / n, 4),
        per_label_accuracy={k: round(v, 4) for k, v in per_label.items()},
    )


def summarize_pai_lift(
    samples: list[HorseSample], band_edges: tuple[int, ...] = DEFAULT_BAND_EDGES
) -> PaiLift | None:
    """PAI 帯ごとの好走率と、PAI と好走の相関（point-biserial）を計算する。"""
    if not samples:
        return None
    n = len(samples)
    total_good = sum(1 for s in samples if s.good_run)
    baseline = total_good / n

    bands: list[PaiBand] = []
    for i in range(len(band_edges) - 1):
        lo, hi = band_edges[i], band_edges[i + 1]
        is_last = i == len(band_edges) - 2
        # 最終帯は上端を含める（PAI=100 を取りこぼさない）。
        members = [s for s in samples if lo <= s.pai < hi or (is_last and s.pai == hi)]
        good = sum(1 for s in members if s.good_run)
        bands.append(PaiBand(lo=lo, hi=hi, n=len(members), good_runs=good))

    top_lift = bands[-1].good_rate / baseline if baseline > 0 and bands else 0.0
    return PaiLift(
        n=n,
        baseline_rate=round(baseline, 4),
        bands=bands,
        point_biserial=round(_point_biserial(samples), 4),
        top_band_lift=round(top_lift, 3),
    )


def summarize_integrated_accuracy(
    samples: list[IntegratedSample],
) -> IntegratedAccuracy | None:
    """統合順位の上位が勝利・好走を捉えた割合を集計する。"""
    if not samples:
        return None
    top1 = [sample for sample in samples if sample.rank == 1]
    good_runs = [sample for sample in samples if sample.good_run]
    return IntegratedAccuracy(
        n_races=len(top1),
        n_horses=len(samples),
        top1_win_rate=round(
            sum(1 for sample in top1 if sample.finish_pos == 1) / len(top1), 4
        )
        if top1
        else 0.0,
        top1_good_rate=round(sum(1 for sample in top1 if sample.good_run) / len(top1), 4)
        if top1
        else 0.0,
        top3_good_capture_rate=round(
            sum(1 for sample in good_runs if sample.rank <= 3) / len(good_runs), 4
        )
        if good_runs
        else 0.0,
    )


def summarize_style_advantage(
    samples: list[StyleAdvantageSample],
) -> StyleAdvantageLift | None:
    """UIと同じ境界で有利・不利群の好走率とリフトを集計する。"""
    if not samples:
        return None
    baseline_rate = sum(sample.good_run for sample in samples) / len(samples)
    advantaged = [sample for sample in samples if sample.score >= 55]
    disadvantaged = [sample for sample in samples if sample.score <= 45]

    def _rate(group: list[StyleAdvantageSample]) -> float:
        return sum(sample.good_run for sample in group) / len(group) if group else 0.0

    advantaged_rate = _rate(advantaged)
    disadvantaged_rate = _rate(disadvantaged)
    return StyleAdvantageLift(
        n=len(samples),
        baseline_rate=round(baseline_rate, 4),
        advantaged_n=len(advantaged),
        advantaged_rate=round(advantaged_rate, 4),
        advantaged_lift=round(advantaged_rate / baseline_rate, 3) if baseline_rate else 0.0,
        disadvantaged_n=len(disadvantaged),
        disadvantaged_rate=round(disadvantaged_rate, 4),
        disadvantaged_lift=(round(disadvantaged_rate / baseline_rate, 3) if baseline_rate else 0.0),
        rate_gap=round(advantaged_rate - disadvantaged_rate, 4),
        point_biserial=round(_style_advantage_point_biserial(samples), 4),
    )


def collect_actual_style_advantage_samples(
    targets: Iterable[Race], repo: RaceRepository
) -> list[StyleAdvantageSample]:
    """実績ペース・確定脚質で、脚質有利度ルール単体の理論上限を検証する。"""
    samples: list[StyleAdvantageSample] = []
    for race in targets:
        if race.rpci_actual is None:
            continue
        entries = repo.find_entries(race.race_key)
        styles_by_horse: dict[int, RunningStyleLabel] = {}
        for entry in entries:
            if entry.running_style is None:
                continue
            try:
                styles_by_horse[entry.horse_no] = RunningStyleLabel(entry.running_style)
            except ValueError:
                continue
        if not styles_by_horse:
            continue
        advantage = build_style_advantage(
            race.rpci_actual,
            race.track_type,
            tuple(styles_by_horse.values()),
        )
        scores = {entry.style: entry.score for entry in advantage.entries}
        for entry in entries:
            style = styles_by_horse.get(entry.horse_no)
            score = scores.get(style) if style is not None else None
            if score is None:
                continue
            samples.append(
                StyleAdvantageSample(
                    race_key=str(race.race_key),
                    horse_no=entry.horse_no,
                    score=score,
                    good_run=is_good_run(entry.finish_pos, race.grade),
                )
            )
    return samples


def build_actual_style_advantage_breakdown(
    targets: Iterable[Race],
    repo: RaceRepository,
    dimension: StyleAdvantageBreakdownDimension,
) -> list[StyleAdvantageBreakdownGroup]:
    """確定値診断を年・実距離・馬場状態、または距離×馬場状態で分割する。"""
    groups: dict[str, list[Race]] = {}
    for race in targets:
        if dimension == "year":
            label = str(race.race_date.year)
        elif dimension == "distance":
            label = f"{race.distance_m}m"
        elif dimension == "track-condition":
            label = race.track_condition or "不明"
        else:
            label = f"{race.distance_m}m / {race.track_condition or '不明'}"
        groups.setdefault(label, []).append(race)

    condition_order = {"良": 0, "稍重": 1, "重": 2, "不良": 3, "不明": 4}
    if dimension == "track-condition":
        labels = sorted(groups, key=lambda value: (condition_order.get(value, 5), value))
    elif dimension == "distance-track-condition":
        labels = sorted(
            groups,
            key=lambda value: (
                int(value.split("m", maxsplit=1)[0]),
                condition_order.get(value.rsplit(" / ", maxsplit=1)[-1], 5),
                value,
            ),
        )
    else:
        labels = sorted(groups, key=lambda value: int(value.removesuffix("m")))

    return [
        StyleAdvantageBreakdownGroup(
            label=label,
            n_races=len(groups[label]),
            lift=summarize_style_advantage(
                collect_actual_style_advantage_samples(groups[label], repo)
            ),
        )
        for label in labels
    ]


def compare_ability_weight_reports(
    reports: dict[str, BacktestReport],
    profiles: tuple[AbilityWeightProfile, ...] = DEFAULT_ABILITY_WEIGHT_PROFILES,
    *,
    baseline_name: str = "current",
) -> list[AbilityWeightComparison]:
    """同一対象で実行した重み別レポートを現行重みと比較する。"""
    baseline_report = reports.get(baseline_name)
    if baseline_report is None:
        raise ValueError(f"基準プロファイルがありません: {baseline_name}")
    baseline = baseline_report.integrated
    comparisons: list[AbilityWeightComparison] = []
    for profile in profiles:
        report = reports.get(profile.name)
        if report is None:
            raise ValueError(f"比較レポートがありません: {profile.name}")
        accuracy = report.integrated
        if (
            baseline is not None
            and accuracy is not None
            and (accuracy.n_races, accuracy.n_horses)
            != (baseline.n_races, baseline.n_horses)
        ):
            raise ValueError(
                f"比較サンプル数が現行重みと一致しません: {profile.name}"
            )
        if baseline is None or accuracy is None:
            deltas: tuple[float | None, float | None, float | None] = (None, None, None)
        else:
            deltas = (
                round(accuracy.top1_win_rate - baseline.top1_win_rate, 4),
                round(accuracy.top1_good_rate - baseline.top1_good_rate, 4),
                round(
                    accuracy.top3_good_capture_rate - baseline.top3_good_capture_rate,
                    4,
                ),
            )
        comparisons.append(
            AbilityWeightComparison(
                profile=profile,
                accuracy=accuracy,
                delta_top1_win_rate=deltas[0],
                delta_top1_good_rate=deltas[1],
                delta_top3_good_capture_rate=deltas[2],
            )
        )
    return comparisons


def compare_rule_weight_reports(
    reports: dict[str, BacktestReport],
    profiles: tuple[RuleWeightProfile, ...] = DEFAULT_RULE_WEIGHT_PROFILES,
    *,
    baseline_name: str = "current",
) -> list[RuleWeightComparison]:
    """同一レースのルール重み候補を全体・芝・ダートで比較する。"""
    baseline_report = reports.get(baseline_name)
    if baseline_report is None:
        raise ValueError(f"基準プロファイルがありません: {baseline_name}")
    baseline_keys = [sample.race_key for sample in baseline_report.rpci_samples]

    comparisons: list[RuleWeightComparison] = []
    for profile in profiles:
        report = reports.get(profile.name)
        if report is None:
            raise ValueError(f"比較レポートがありません: {profile.name}")
        if [sample.race_key for sample in report.rpci_samples] != baseline_keys:
            raise ValueError(f"比較対象レースが現行重みと一致しません: {profile.name}")

        comparisons.append(
            RuleWeightComparison(
                profile=profile,
                combined=_compare_rule_scope(
                    baseline_report.rpci_samples,
                    report.rpci_samples,
                ),
                turf=_compare_rule_scope(
                    _filter_rpci_samples(baseline_report.rpci_samples, "芝"),
                    _filter_rpci_samples(report.rpci_samples, "芝"),
                ),
                dirt=_compare_rule_scope(
                    _filter_rpci_samples(baseline_report.rpci_samples, "ダート"),
                    _filter_rpci_samples(report.rpci_samples, "ダート"),
                ),
            )
        )
    return comparisons


def compare_pai_weight_reports(
    reports: dict[str, BacktestReport],
    profiles: tuple[PaiWeightProfile, ...] = DEFAULT_PAI_WEIGHT_PROFILES,
    *,
    baseline_name: str = "current",
) -> list[PaiWeightComparison]:
    """同一レース・同一馬のPAI重み候補を全体・芝・ダートで比較する。"""
    baseline_report = reports.get(baseline_name)
    if baseline_report is None:
        raise ValueError(f"基準プロファイルがありません: {baseline_name}")
    baseline_keys = [
        (sample.race_key, sample.horse_no) for sample in baseline_report.horse_samples
    ]

    comparisons: list[PaiWeightComparison] = []
    for profile in profiles:
        report = reports.get(profile.name)
        if report is None:
            raise ValueError(f"比較レポートがありません: {profile.name}")
        candidate_keys = [(sample.race_key, sample.horse_no) for sample in report.horse_samples]
        if candidate_keys != baseline_keys:
            raise ValueError(f"比較対象馬が現行重みと一致しません: {profile.name}")

        comparisons.append(
            PaiWeightComparison(
                profile=profile,
                combined=_compare_pai_scope(
                    baseline_report.horse_samples,
                    report.horse_samples,
                ),
                turf=_compare_pai_scope(
                    _filter_horse_samples(baseline_report.horse_samples, "芝"),
                    _filter_horse_samples(report.horse_samples, "芝"),
                ),
                dirt=_compare_pai_scope(
                    _filter_horse_samples(baseline_report.horse_samples, "ダート"),
                    _filter_horse_samples(report.horse_samples, "ダート"),
                ),
            )
        )
    return comparisons


def _filter_horse_samples(
    samples: list[HorseSample], track_type: str
) -> list[HorseSample]:
    return [sample for sample in samples if sample.track_type == track_type]


def _compare_pai_scope(
    baseline_samples: list[HorseSample],
    candidate_samples: list[HorseSample],
) -> PaiWeightMetrics:
    baseline = summarize_pai_lift(baseline_samples)
    candidate = summarize_pai_lift(candidate_samples)
    if baseline is None or candidate is None:
        return PaiWeightMetrics(
            lift=candidate,
            delta_point_biserial=None,
            delta_top_band_lift=None,
        )
    return PaiWeightMetrics(
        lift=candidate,
        delta_point_biserial=round(
            candidate.point_biserial - baseline.point_biserial,
            4,
        ),
        delta_top_band_lift=round(
            candidate.top_band_lift - baseline.top_band_lift,
            4,
        ),
    )


def _filter_rpci_samples(samples: list[RpciSample], track_type: str) -> list[RpciSample]:
    return [sample for sample in samples if sample.track_type == track_type]


def _compare_rule_scope(
    baseline_samples: list[RpciSample],
    candidate_samples: list[RpciSample],
) -> RuleWeightMetrics:
    baseline = summarize_rpci(baseline_samples)
    candidate = summarize_rpci(candidate_samples)
    if baseline is None or candidate is None:
        return RuleWeightMetrics(
            accuracy=candidate,
            delta_mae=None,
            delta_label_accuracy=None,
        )
    return RuleWeightMetrics(
        accuracy=candidate,
        delta_mae=round(candidate.mae - baseline.mae, 4),
        delta_label_accuracy=round(
            candidate.label_accuracy - baseline.label_accuracy,
            4,
        ),
    )


def group_races_by_track(races: Iterable[Race]) -> dict[str, list[Race]]:
    """レース群をコース種別ごとにグルーピングする。

    コース混合のまま `ForecastBacktester.run()` すると PAI の point-biserial 相関が
    希釈されて見える（芝とダートでスコア分布・好走率ベースラインが異なるため。
    docs/adr/0005-rpci-forecast-strategy.md §5.4）。呼び出し側で track 別にも
    run() を回せるよう、レースを分割するだけの純粋関数として提供する。
    """
    grouped: dict[str, list[Race]] = {}
    for race in races:
        grouped.setdefault(race.track_type, []).append(race)
    return grouped


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    """BacktestReport をJSON保存用の辞書に変換する（的中率推移の記録・後日の再集計に使う）。"""
    return {
        "model_version": report.model_version,
        "n_races": report.n_races,
        "n_horses": report.n_horses,
        "skipped": report.skipped,
        "rpci": _rpci_accuracy_to_dict(report.rpci),
        "pai": _pai_lift_to_dict(report.pai),
        "integrated": _integrated_accuracy_to_dict(report.integrated),
        "style_advantage": style_advantage_lift_to_dict(report.style_advantage),
        "rpci_samples": [_rpci_sample_to_dict(s) for s in report.rpci_samples],
        "horse_samples": [_horse_sample_to_dict(s) for s in report.horse_samples],
        "integrated_samples": [
            _integrated_sample_to_dict(s) for s in report.integrated_samples
        ],
        "style_advantage_samples": [
            _style_advantage_sample_to_dict(s) for s in report.style_advantage_samples
        ],
    }


def _rpci_accuracy_to_dict(accuracy: RpciAccuracy | None) -> dict[str, Any] | None:
    if accuracy is None:
        return None
    return {
        "n": accuracy.n,
        "mae": accuracy.mae,
        "rmse": accuracy.rmse,
        "bias": accuracy.bias,
        "label_accuracy": accuracy.label_accuracy,
        "per_label_accuracy": dict(accuracy.per_label_accuracy),
    }


def _pai_lift_to_dict(lift: PaiLift | None) -> dict[str, Any] | None:
    if lift is None:
        return None
    return {
        "n": lift.n,
        "baseline_rate": lift.baseline_rate,
        "point_biserial": lift.point_biserial,
        "top_band_lift": lift.top_band_lift,
        "bands": [
            {"lo": b.lo, "hi": b.hi, "n": b.n, "good_runs": b.good_runs, "good_rate": b.good_rate}
            for b in lift.bands
        ],
    }


def ability_weight_comparisons_to_dict(
    comparisons: list[AbilityWeightComparison],
) -> list[dict[str, Any]]:
    """重み比較結果をJSON保存用の辞書へ変換する。"""
    return [
        {
            "name": item.profile.name,
            "description": item.profile.description,
            "weights": {
                "form": item.profile.weights.weight_form,
                "prize": item.profile.weights.weight_prize,
                "popularity": item.profile.weights.weight_popularity,
            },
            "integrated": _integrated_accuracy_to_dict(item.accuracy),
            "delta_vs_current": {
                "top1_win_rate": item.delta_top1_win_rate,
                "top1_good_rate": item.delta_top1_good_rate,
                "top3_good_capture_rate": item.delta_top3_good_capture_rate,
            },
        }
        for item in comparisons
    ]


def rule_weight_comparisons_to_dict(
    comparisons: list[RuleWeightComparison],
) -> list[dict[str, Any]]:
    """ルール重み比較結果をJSON保存用の辞書へ変換する。"""
    return [
        {
            "name": item.profile.name,
            "description": item.profile.description,
            "weights": {
                "style_balance": item.profile.weights.style_balance_weight,
                "evidence_per_sample": item.profile.weights.evidence_weight_per_sample,
                "evidence_cap": item.profile.weights.evidence_weight_cap,
            },
            "combined": _rule_weight_metrics_to_dict(item.combined),
            "turf": _rule_weight_metrics_to_dict(item.turf),
            "dirt": _rule_weight_metrics_to_dict(item.dirt),
        }
        for item in comparisons
    ]


def pai_weight_comparisons_to_dict(
    comparisons: list[PaiWeightComparison],
) -> list[dict[str, Any]]:
    """PAI重み比較結果をJSON保存用の辞書へ変換する。"""
    return [
        {
            "name": item.profile.name,
            "description": item.profile.description,
            "weights": {
                "preferred_escape": item.profile.weights.preferred_escape,
                "preferred_front": item.profile.weights.preferred_front,
                "preferred_flexible": item.profile.weights.preferred_flexible,
                "preferred_stalker": item.profile.weights.preferred_stalker,
                "preferred_closer": item.profile.weights.preferred_closer,
                "rpci_diff_weight": item.profile.weights.rpci_diff_weight,
            },
            "combined": _pai_weight_metrics_to_dict(item.combined),
            "turf": _pai_weight_metrics_to_dict(item.turf),
            "dirt": _pai_weight_metrics_to_dict(item.dirt),
        }
        for item in comparisons
    ]


def _pai_weight_metrics_to_dict(metrics: PaiWeightMetrics) -> dict[str, Any]:
    return {
        "pai": _pai_lift_to_dict(metrics.lift),
        "delta_vs_current": {
            "point_biserial": metrics.delta_point_biserial,
            "top_band_lift": metrics.delta_top_band_lift,
        },
    }


def _rule_weight_metrics_to_dict(metrics: RuleWeightMetrics) -> dict[str, Any]:
    return {
        "rpci": _rpci_accuracy_to_dict(metrics.accuracy),
        "delta_vs_current": {
            "mae": metrics.delta_mae,
            "label_accuracy": metrics.delta_label_accuracy,
        },
    }


def _integrated_accuracy_to_dict(
    accuracy: IntegratedAccuracy | None,
) -> dict[str, Any] | None:
    if accuracy is None:
        return None
    return {
        "n_races": accuracy.n_races,
        "n_horses": accuracy.n_horses,
        "top1_win_rate": accuracy.top1_win_rate,
        "top1_good_rate": accuracy.top1_good_rate,
        "top3_good_capture_rate": accuracy.top3_good_capture_rate,
    }


def style_advantage_lift_to_dict(
    lift: StyleAdvantageLift | None,
) -> dict[str, Any] | None:
    if lift is None:
        return None
    return {
        "n": lift.n,
        "baseline_rate": lift.baseline_rate,
        "advantaged_n": lift.advantaged_n,
        "advantaged_rate": lift.advantaged_rate,
        "advantaged_lift": lift.advantaged_lift,
        "disadvantaged_n": lift.disadvantaged_n,
        "disadvantaged_rate": lift.disadvantaged_rate,
        "disadvantaged_lift": lift.disadvantaged_lift,
        "rate_gap": lift.rate_gap,
        "point_biserial": lift.point_biserial,
    }


def style_advantage_attribution_to_dict(
    report: StyleAdvantageAttribution,
) -> dict[str, Any]:
    return {
        "n_races": report.n_races,
        "n_horses": report.n_horses,
        "skipped": report.skipped,
        "forecast": style_advantage_lift_to_dict(report.forecast),
        "actual_pace": style_advantage_lift_to_dict(report.actual_pace),
        "actual_style": style_advantage_lift_to_dict(report.actual_style),
        "oracle": style_advantage_lift_to_dict(report.oracle),
        "pace_recovery": _rate_gap_delta(report.actual_pace, report.forecast),
        "style_recovery": _rate_gap_delta(report.actual_style, report.forecast),
    }


def style_advantage_breakdown_to_dict(
    groups: Iterable[StyleAdvantageBreakdownGroup],
) -> dict[str, Any]:
    return {
        group.label: {
            "n_races": group.n_races,
            "style_advantage": style_advantage_lift_to_dict(group.lift),
        }
        for group in groups
    }


def _rpci_sample_to_dict(sample: RpciSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "predicted": sample.predicted,
        "actual": sample.actual,
        "error": sample.error,
        "predicted_label": str(sample.predicted_label),
        "actual_label": str(sample.actual_label),
        "track_type": sample.track_type,
    }


def _horse_sample_to_dict(sample: HorseSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "horse_no": sample.horse_no,
        "pai": sample.pai,
        "good_run": sample.good_run,
        "track_type": sample.track_type,
    }


def _integrated_sample_to_dict(sample: IntegratedSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "horse_no": sample.horse_no,
        "rank": sample.rank,
        "finish_pos": sample.finish_pos,
        "good_run": sample.good_run,
    }


def _style_advantage_sample_to_dict(sample: StyleAdvantageSample) -> dict[str, Any]:
    return {
        "race_key": sample.race_key,
        "horse_no": sample.horse_no,
        "score": sample.score,
        "good_run": sample.good_run,
    }


def format_report(report: BacktestReport) -> str:
    """バックテスト結果を人間可読のテキストへ整形する（CLI 出力用）。"""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"バックテスト結果  model_version={report.model_version or '(不明)'}")
    lines.append(
        f"対象レース {report.n_races} / 出走 {report.n_horses} 頭 "
        f"（スキップ {report.skipped}）"
    )
    lines.append("=" * 60)

    if report.rpci is not None:
        r = report.rpci
        lines.append("\n■ 想定RPCI の誤差")
        lines.append(f"  MAE  : {r.mae:.3f}   RMSE: {r.rmse:.3f}   バイアス: {r.bias:+.3f}")
        lines.append(f"  展開ラベル的中率: {r.label_accuracy:.1%}")
        for label, acc in r.per_label_accuracy.items():
            lines.append(f"    - 実績「{label}」の再現率: {acc:.1%}")
    else:
        lines.append("\n■ 想定RPCI: 有効サンプルなし")

    if report.pai is not None:
        p = report.pai
        lines.append("\n■ PAI のリフト（高PAI ほど好走するか）")
        lines.append(f"  全体好走率(ベースライン): {p.baseline_rate:.1%}")
        lines.append(f"  PAI×好走 の相関(point-biserial): {p.point_biserial:+.3f}")
        lines.append(f"  最上位帯リフト: {p.top_band_lift:.2f}x")
        lines.append("  PAI帯       頭数    好走   好走率   対ベース")
        for b in p.bands:
            lift = (b.good_rate / p.baseline_rate) if p.baseline_rate > 0 else 0.0
            lines.append(
                f"   {b.lo:3d}-{b.hi:<3d}  {b.n:6d}  {b.good_runs:6d}   "
                f"{b.good_rate:5.1%}   {lift:5.2f}x"
            )
    else:
        lines.append("\n■ PAI: 有効サンプルなし")

    if report.integrated is not None:
        i = report.integrated
        lines.append("\n■ 統合順位予想の実績")
        lines.append(f"  1位馬の勝率: {i.top1_win_rate:.1%}")
        lines.append(f"  1位馬の好走率: {i.top1_good_rate:.1%}")
        lines.append(f"  TOP3の好走馬捕捉率: {i.top3_good_capture_rate:.1%}")
    else:
        lines.append("\n■ 統合順位予想: 有効サンプルなし")

    if report.style_advantage is not None:
        s = report.style_advantage
        lines.append("\n■ 脚質別展開有利度のリフト")
        lines.append(f"  全体好走率(ベースライン): {s.baseline_rate:.1%}")
        lines.append(
            f"  やや有利以上: {s.advantaged_rate:.1%} "
            f"({s.advantaged_n}頭 / {s.advantaged_lift:.2f}x)"
        )
        lines.append(
            f"  やや不利以下: {s.disadvantaged_rate:.1%} "
            f"({s.disadvantaged_n}頭 / {s.disadvantaged_lift:.2f}x)"
        )
        lines.append(f"  有利−不利の好走率差: {s.rate_gap:+.1%}")
        lines.append(f"  有利度×好走 の相関(point-biserial): {s.point_biserial:+.3f}")
    else:
        lines.append("\n■ 脚質別展開有利度: 有効サンプルなし")

    return "\n".join(lines)


def format_ability_weight_comparison(comparisons: list[AbilityWeightComparison]) -> str:
    """重み候補の比較をCLI向けの表に整形する。"""
    lines = [
        "=" * 88,
        "能力重みの同一期間比較（候補は自動採用しません）",
        "候補              form 賞金 人気   1位勝率(差)   1位好走率(差)   TOP3捕捉率(差)",
        "-" * 88,
    ]
    for item in comparisons:
        weights = item.profile.weights
        if item.accuracy is None:
            metrics = "有効サンプルなし"
        else:
            accuracy = item.accuracy
            metrics = (
                f"{accuracy.top1_win_rate:6.1%}({_format_delta(item.delta_top1_win_rate)})  "
                f"{accuracy.top1_good_rate:6.1%}({_format_delta(item.delta_top1_good_rate)})  "
                f"{accuracy.top3_good_capture_rate:6.1%}"
                f"({_format_delta(item.delta_top3_good_capture_rate)})"
            )
        lines.append(
            f"{item.profile.name:<18} "
            f"{weights.weight_form:4.2f} {weights.weight_prize:4.2f} "
            f"{weights.weight_popularity:4.2f}   {metrics}"
        )
    lines.append("=" * 88)
    return "\n".join(lines)


def format_rule_weight_comparison(comparisons: list[RuleWeightComparison]) -> str:
    """ルール重み候補の比較をCLI向けの表に整形する。"""
    lines = [
        "=" * 96,
        "RuleWeightsの同一期間比較（候補は自動採用しません）",
        "MAEは低いほど良く、展開分類一致率は高いほど良い指標です。",
        "-" * 96,
    ]
    for item in comparisons:
        weights = item.profile.weights
        lines.append(
            f"{item.profile.name} "
            f"(style={weights.style_balance_weight:.3f}, "
            f"evidence={weights.evidence_weight_per_sample:.3f}, "
            f"cap={weights.evidence_weight_cap:.3f})"
        )
        for label, metrics in (
            ("全体", item.combined),
            ("芝", item.turf),
            ("ダート", item.dirt),
        ):
            if metrics.accuracy is None:
                summary = "有効サンプルなし"
            else:
                summary = (
                    f"n={metrics.accuracy.n:4d} "
                    f"MAE={metrics.accuracy.mae:6.3f}"
                    f"({_format_number_delta(metrics.delta_mae)}) "
                    f"一致率={metrics.accuracy.label_accuracy:6.1%}"
                    f"({_format_delta(metrics.delta_label_accuracy)})"
                )
            lines.append(f"  {label:<4} {summary}")
    lines.append("=" * 96)
    return "\n".join(lines)


def format_pai_weight_comparison(comparisons: list[PaiWeightComparison]) -> str:
    """PAI重み候補の比較をCLI向けの表に整形する。"""
    lines = [
        "=" * 96,
        "PaiWeightsの同一期間比較（候補は自動採用しません）",
        "相関と最上位帯リフトは高いほど良い指標です。",
        "-" * 96,
    ]
    for item in comparisons:
        weights = item.profile.weights
        lines.append(
            f"{item.profile.name} "
            f"(preferred={weights.preferred_escape:.1f}/"
            f"{weights.preferred_front:.1f}/{weights.preferred_flexible:.1f}/"
            f"{weights.preferred_stalker:.1f}/{weights.preferred_closer:.1f}, "
            f"rpci_weight={weights.rpci_diff_weight:.1f})"
        )
        for label, metrics in (
            ("全体", item.combined),
            ("芝", item.turf),
            ("ダート", item.dirt),
        ):
            if metrics.lift is None:
                summary = "有効サンプルなし"
            else:
                summary = (
                    f"n={metrics.lift.n:5d} "
                    f"相関={metrics.lift.point_biserial:+.3f}"
                    f"({_format_number_delta(metrics.delta_point_biserial)}) "
                    f"上位帯={metrics.lift.top_band_lift:5.2f}x"
                    f"({_format_number_delta(metrics.delta_top_band_lift)})"
                )
            lines.append(f"  {label:<4} {summary}")
    lines.append("=" * 96)
    return "\n".join(lines)


def format_actual_style_advantage_validation(
    lift: StyleAdvantageLift | None,
) -> str:
    """実績ペース・確定脚質を使う診断結果をCLI向けに整形する。"""
    if lift is None:
        return "脚質別展開有利度: 有効サンプルなし"
    return "\n".join(
        [
            "=" * 72,
            "脚質別展開有利度の単体検証（実績ペース・確定脚質を使用）",
            "※ 本番予測ではなく、方向性と係数の診断専用",
            f"全体好走率: {lift.baseline_rate:.1%}（{lift.n}頭）",
            (
                f"やや有利以上: {lift.advantaged_rate:.1%} "
                f"（{lift.advantaged_n}頭 / {lift.advantaged_lift:.2f}x）"
            ),
            (
                f"やや不利以下: {lift.disadvantaged_rate:.1%} "
                f"（{lift.disadvantaged_n}頭 / {lift.disadvantaged_lift:.2f}x）"
            ),
            f"有利−不利の好走率差: {lift.rate_gap:+.1%}",
            f"有利度×好走の相関: {lift.point_biserial:+.3f}",
            "=" * 72,
        ]
    )


def format_actual_style_advantage_breakdown(
    dimension: StyleAdvantageBreakdownDimension,
    groups: Iterable[StyleAdvantageBreakdownGroup],
) -> str:
    """確定値診断の開催条件別内訳をCLI向けの表に整形する。"""
    dimension_labels = {
        "year": "年",
        "distance": "距離",
        "track-condition": "馬場状態",
        "distance-track-condition": "距離×馬場状態",
    }
    lines = [
        "",
        f"■ 脚質別展開有利度の内訳（{dimension_labels[dimension]}別）",
        "条件          レース  対象頭数   有利好走率   不利好走率   好走率差",
        "-" * 72,
    ]
    for group in groups:
        lift = group.lift
        if lift is None:
            metrics = "有効サンプルなし"
        else:
            metrics = (
                f"{lift.n:8d}   {lift.advantaged_rate:9.1%}   "
                f"{lift.disadvantaged_rate:9.1%}   {lift.rate_gap:+8.1%}"
            )
        lines.append(f"{group.label:<12} {group.n_races:6d}  {metrics}")
    return "\n".join(lines)


def format_style_advantage_attribution(report: StyleAdvantageAttribution) -> str:
    """脚質別有利度の誤差要因をCLI向けに比較表示する。"""
    lines = [
        "=" * 72,
        "脚質別展開有利度の誤差要因診断",
        f"対象: {report.n_races}レース / {report.n_horses}頭（スキップ {report.skipped}）",
        "※ 4パターンで共通して脚質を判定できた馬だけを比較",
        "-" * 72,
    ]
    rows = (
        ("予測ペース × 予測脚質", report.forecast),
        ("実績ペース × 予測脚質", report.actual_pace),
        ("予測ペース × 確定脚質", report.actual_style),
        ("実績ペース × 確定脚質", report.oracle),
    )
    for label, lift in rows:
        if lift is None:
            lines.append(f"{label}: 有効サンプルなし")
            continue
        lines.append(
            f"{label}: 有利 {lift.advantaged_rate:.1%} / "
            f"不利 {lift.disadvantaged_rate:.1%} / 差 {lift.rate_gap:+.1%}"
        )
    pace_recovery = _rate_gap_delta(report.actual_pace, report.forecast)
    style_recovery = _rate_gap_delta(report.actual_style, report.forecast)
    lines.append("-" * 72)
    lines.append(f"ペースを実績へ置換した改善幅: {_format_optional_delta(pace_recovery)}")
    lines.append(f"脚質を確定値へ置換した改善幅: {_format_optional_delta(style_recovery)}")
    if pace_recovery is not None and style_recovery is not None:
        if pace_recovery > style_recovery:
            conclusion = "想定RPCI側の影響が相対的に大きい"
        elif style_recovery > pace_recovery:
            conclusion = "脚質予測側の影響が相対的に大きい"
        else:
            conclusion = "想定RPCIと脚質予測の影響は同程度"
        lines.append(f"診断: {conclusion}")
    lines.append("=" * 72)
    return "\n".join(lines)


def _format_delta(value: float | None) -> str:
    return "   n/a" if value is None else f"{value:+6.1%}"


def _format_number_delta(value: float | None) -> str:
    return "   n/a" if value is None else f"{value:+7.3f}"


def _point_biserial(samples: list[HorseSample]) -> float:
    """PAI（連続）と好走（0/1）の相関係数。分散ゼロや少数時は 0 を返す。"""
    n = len(samples)
    if n < 2:
        return 0.0
    xs = [s.pai for s in samples]
    ys = [1.0 if s.good_run else 0.0 for s in samples]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mx) ** 2 for x in xs)
    var_y = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom > 0 else 0.0


def _style_advantage_point_biserial(samples: list[StyleAdvantageSample]) -> float:
    """脚質別有利度（連続）と好走（0/1）の相関係数。"""
    n = len(samples)
    if n < 2:
        return 0.0
    xs = [sample.score for sample in samples]
    ys = [1.0 if sample.good_run else 0.0 for sample in samples]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = math.sqrt(variance_x * variance_y)
    return covariance / denominator if denominator > 0 else 0.0


def _rate_gap_delta(
    candidate: StyleAdvantageLift | None,
    baseline: StyleAdvantageLift | None,
) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(candidate.rate_gap - baseline.rate_gap, 4)


def _format_optional_delta(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


class ForecastBacktester:
    """確定レース群に対して予測を再現し、実績と突き合わせる。"""

    def __init__(
        self,
        repo: RaceRepository,
        forecaster: RpciForecaster | None = None,
        comment_generator: CommentGenerator | None = None,
        ability_scorer: AbilityScorer | None = None,
        pai_scorer: PaceAdaptabilityScorer | None = None,
        band_edges: tuple[int, ...] = DEFAULT_BAND_EDGES,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster
        self._commenter = comment_generator
        self._ability_scorer = ability_scorer
        self._pai_scorer = pai_scorer
        self._band_edges = band_edges

    def run(self, targets: Iterable[Race]) -> BacktestReport:
        rpci_samples: list[RpciSample] = []
        horse_samples: list[HorseSample] = []
        integrated_samples: list[IntegratedSample] = []
        style_advantage_samples: list[StyleAdvantageSample] = []
        n_races = 0
        skipped = 0
        model_versions: set[str] = set()

        for race in targets:
            if race.rpci_actual is None:
                skipped += 1
                continue
            key = str(race.race_key)
            try:
                out = self._predict_as_of(race)
            except Exception:
                # 履歴皆無・出走馬未登録などはバックテスト対象外として飛ばす。
                skipped += 1
                continue

            model_versions.add(out.model_version)
            rpci_samples.append(
                RpciSample(
                    race_key=key,
                    predicted=out.predicted_rpci,
                    actual=race.rpci_actual,
                    predicted_label=classify_pace(out.predicted_rpci, race.track_type),
                    actual_label=classify_pace(race.rpci_actual, race.track_type),
                    track_type=race.track_type,
                )
            )

            actual_entries = self._repo.find_entries(race.race_key)
            finish_by_no = {e.horse_no: e.finish_pos for e in actual_entries}
            style_scores = (
                {entry.style: entry.score for entry in out.style_advantage.entries}
                if out.style_advantage is not None
                else {}
            )
            for horse in out.horses:
                finish = finish_by_no.get(horse.horse_no)
                good_run = is_good_run(finish, race.grade)
                horse_samples.append(
                    HorseSample(
                        race_key=key,
                        horse_no=horse.horse_no,
                        pai=horse.pai,
                        good_run=good_run,
                        track_type=race.track_type,
                    )
                )
                style_score = style_scores.get(horse.running_style)
                if style_score is not None:
                    style_advantage_samples.append(
                        StyleAdvantageSample(
                            race_key=key,
                            horse_no=horse.horse_no,
                            score=style_score,
                            good_run=good_run,
                        )
                    )
            if out.integrated_ranking is not None:
                for entry in out.integrated_ranking.entries:
                    finish = finish_by_no.get(entry.horse_no)
                    integrated_samples.append(
                        IntegratedSample(
                            race_key=key,
                            horse_no=entry.horse_no,
                            rank=entry.rank,
                            finish_pos=finish,
                            good_run=is_good_run(finish, race.grade),
                        )
                    )
            n_races += 1

        model_version = " / ".join(sorted(model_versions)) if model_versions else ""
        return BacktestReport(
            model_version=model_version,
            n_races=n_races,
            n_horses=len(horse_samples),
            skipped=skipped,
            rpci=summarize_rpci(rpci_samples),
            pai=summarize_pai_lift(horse_samples, self._band_edges),
            integrated=summarize_integrated_accuracy(integrated_samples),
            style_advantage=summarize_style_advantage(style_advantage_samples),
            rpci_samples=rpci_samples,
            horse_samples=horse_samples,
            integrated_samples=integrated_samples,
            style_advantage_samples=style_advantage_samples,
        )

    def diagnose_style_advantage(
        self, targets: Iterable[Race]
    ) -> StyleAdvantageAttribution:
        """ペースと脚質を個別に確定値へ置換し、有利度の誤差要因を切り分ける。"""
        forecast_samples: list[StyleAdvantageSample] = []
        actual_pace_samples: list[StyleAdvantageSample] = []
        actual_style_samples: list[StyleAdvantageSample] = []
        oracle_samples: list[StyleAdvantageSample] = []
        n_races = 0
        skipped = 0

        for race in targets:
            if race.rpci_actual is None:
                skipped += 1
                continue
            try:
                output = self._predict_as_of(race)
            except Exception:
                skipped += 1
                continue

            actual_entries = {
                entry.horse_no: entry for entry in self._repo.find_entries(race.race_key)
            }
            predicted_styles = {
                horse.horse_no: style
                for horse in output.horses
                if (style := _scoreable_style(horse.running_style)) is not None
            }
            actual_styles = {
                horse_no: style
                for horse_no, entry in actual_entries.items()
                if (style := _scoreable_style(entry.running_style)) is not None
            }
            eligible = sorted(predicted_styles.keys() & actual_styles.keys())
            if not eligible:
                skipped += 1
                continue
            predicted_composition = tuple(predicted_styles[horse_no] for horse_no in eligible)
            actual_composition = tuple(actual_styles[horse_no] for horse_no in eligible)

            forecast_scores = _style_score_map(
                output.predicted_rpci,
                race.track_type,
                predicted_composition,
            )
            actual_pace_scores = _style_score_map(
                race.rpci_actual,
                race.track_type,
                predicted_composition,
            )
            actual_style_scores = _style_score_map(
                output.predicted_rpci,
                race.track_type,
                actual_composition,
            )
            oracle_scores = _style_score_map(
                race.rpci_actual,
                race.track_type,
                actual_composition,
            )

            race_key = str(race.race_key)
            for horse_no in eligible:
                predicted_style = predicted_styles[horse_no]
                actual_style = actual_styles[horse_no]
                good_run = is_good_run(actual_entries[horse_no].finish_pos, race.grade)
                values = (
                    (forecast_samples, forecast_scores[predicted_style]),
                    (actual_pace_samples, actual_pace_scores[predicted_style]),
                    (actual_style_samples, actual_style_scores[actual_style]),
                    (oracle_samples, oracle_scores[actual_style]),
                )
                for samples, score in values:
                    samples.append(
                        StyleAdvantageSample(
                            race_key=race_key,
                            horse_no=horse_no,
                            score=score,
                            good_run=good_run,
                        )
                    )
            n_races += 1

        return StyleAdvantageAttribution(
            n_races=n_races,
            n_horses=len(forecast_samples),
            skipped=skipped,
            forecast=summarize_style_advantage(forecast_samples),
            actual_pace=summarize_style_advantage(actual_pace_samples),
            actual_style=summarize_style_advantage(actual_style_samples),
            oracle=summarize_style_advantage(oracle_samples),
        )

    def _predict_as_of(self, race: Race) -> ForecastOutput:
        # mart_repo=None で保存を抑止し、実績データを汚さずに予測だけ再現する。
        as_of_repo = _AsOfRaceRepository(self._repo, race.race_date)
        use_case = ForecastRaceUseCase(
            as_of_repo,
            forecaster=self._forecaster,
            mart_repo=None,
            comment_generator=self._commenter,
            ability_scorer=self._ability_scorer,
            scorer=self._pai_scorer,
        )
        return use_case.execute(str(race.race_key))


def _scoreable_style(value: str | RunningStyleLabel | None) -> RunningStyleLabel | None:
    if value is None:
        return None
    try:
        style = RunningStyleLabel(value)
    except ValueError:
        return None
    return style if style in _SCOREABLE_STYLES else None


def _style_score_map(
    rpci: float,
    track_type: str,
    running_styles: tuple[RunningStyleLabel, ...],
) -> dict[RunningStyleLabel, float]:
    advantage = build_style_advantage(rpci, track_type, running_styles)
    return {entry.style: entry.score for entry in advantage.entries}
