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
import unicodedata
from collections.abc import Callable, Iterable
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
    pace_center,
    pace_deviation,
    pace_half_band,
)
from pci.domain.pace.affinity import is_good_run
from pci.domain.pace.commentary import CommentGenerator
from pci.domain.pace.integrated_ranking import RankingStrategy
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
from pci.domain.pace.style_advantage import StyleAdvantageWeights, build_style_advantage
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
    # PAIが「展開適性」ではなく脚質そのものを符号化していないか調べるために持つ。
    running_style: str = ""
    # ペース補正が脚質どうしを相対的にずらしていないかを測るために持つ。
    forecast_rpci: float = 0.0
    # ラベル閾値がスケールに合っているかを測るために持つ。
    fit_label: str = ""


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
    # 同じ「有利」でも前付けと差し追込では実績が異なりうるため、
    # 帯別集計を脚質グループで割れるように保持する。
    running_style: RunningStyleLabel | None = None


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
class StyleAdvantageBand:
    """有利度スコア帯ごとの好走率。帯の境界はUI表示ラベルと同一。"""

    label: str
    lo: float
    hi: float
    n: int
    good_runs: int

    @property
    def good_rate(self) -> float:
        return self.good_runs / self.n if self.n else 0.0


@dataclass(frozen=True)
class ClampImpact:
    """予測値のクランプが誤差へどれだけ効いているかの内訳。

    想定RPCIは安全弁として[rpci_min, rpci_max]へ丸められる（domain: RuleWeights、
    infra: lgbm_forecaster が同じ値を持つ）。実績がこの範囲の外側にあるレースでは
    予測が構造的に届かないため、モデルを差し替えても消えない系統誤差が残る。
    「バイアスがモデル起因か、クランプ起因か」を切り分けるために内訳を出す。
    """

    n: int
    lower: float
    upper: float
    at_lower_n: int
    at_lower_bias: float
    at_lower_actual_mean: float
    at_upper_n: int
    at_upper_bias: float
    interior_n: int
    interior_bias: float
    interior_mae: float

    @property
    def at_lower_share(self) -> float:
        return self.at_lower_n / self.n if self.n else 0.0

    @property
    def bias_from_lower(self) -> float:
        """全体バイアスのうち、下限に張り付いた群が寄与している量。"""
        return self.at_lower_n * self.at_lower_bias / self.n if self.n else 0.0

    @property
    def bias_from_upper(self) -> float:
        return self.at_upper_n * self.at_upper_bias / self.n if self.n else 0.0


def summarize_clamp_impact(
    samples: list[RpciSample],
    rule_weights: RuleWeights = DEFAULT_RULE_WEIGHTS,
    clamp: tuple[float, float] | None = None,
) -> ClampImpact | None:
    """予測がクランプ端に張り付いた群と、内側の群とで誤差を分けて集計する。

    clamp を渡すと本番既定ではなくその境界で判定する（較正の実測用）。
    """
    if not samples:
        return None
    lower, upper = clamp if clamp is not None else (rule_weights.rpci_min, rule_weights.rpci_max)
    # 予測値は小数1桁へ丸めてから返るため、端値との比較は微小誤差だけ見れば足りる。
    at_lower = [s for s in samples if s.predicted <= lower + 1e-9]
    at_upper = [s for s in samples if s.predicted >= upper - 1e-9]
    interior = [s for s in samples if lower + 1e-9 < s.predicted < upper - 1e-9]

    def _bias(group: list[RpciSample]) -> float:
        return sum(s.predicted - s.actual for s in group) / len(group) if group else 0.0

    def _mae(group: list[RpciSample]) -> float:
        return sum(abs(s.predicted - s.actual) for s in group) / len(group) if group else 0.0

    return ClampImpact(
        n=len(samples),
        lower=lower,
        upper=upper,
        at_lower_n=len(at_lower),
        at_lower_bias=round(_bias(at_lower), 3),
        at_lower_actual_mean=round(sum(s.actual for s in at_lower) / len(at_lower), 2)
        if at_lower
        else 0.0,
        at_upper_n=len(at_upper),
        at_upper_bias=round(_bias(at_upper), 3),
        interior_n=len(interior),
        interior_bias=round(_bias(interior), 3),
        interior_mae=round(_mae(interior), 3),
    )


def format_clamp_impact(impact: ClampImpact | None) -> str:
    """クランプ影響の内訳をCLI向けに整形する。端に張り付きが無ければ空文字。"""
    if impact is None or (impact.at_lower_n == 0 and impact.at_upper_n == 0):
        return ""
    lines = [
        "",
        f"■ 予測値クランプ[{impact.lower:.0f}, {impact.upper:.0f}]の影響",
        f"  内側      : {impact.interior_n:5,d}件  バイアス {impact.interior_bias:+.3f}"
        f"  MAE {impact.interior_mae:.3f}",
    ]
    if impact.at_lower_n:
        lines.append(
            f"  下限張付き: {impact.at_lower_n:5,d}件"
            f"（{impact.at_lower_share:.1%}） バイアス {impact.at_lower_bias:+.3f}"
            f"  実績平均 {impact.at_lower_actual_mean:.1f}"
        )
    if impact.at_upper_n:
        lines.append(
            f"  上限張付き: {impact.at_upper_n:5,d}件  バイアス {impact.at_upper_bias:+.3f}"
        )
    lines.append(
        f"  → 全体バイアスへの寄与: 下限 {impact.bias_from_lower:+.3f}"
        f" / 上限 {impact.bias_from_upper:+.3f}"
    )
    lines.append("  ※ 内側のバイアスが小さいのに全体が偏るなら、原因はモデルではなくクランプ幅。")
    return "\n".join(lines)


@dataclass(frozen=True)
class StyleAdvantageProfile:
    """実DB比較に使う脚質別有利度の候補係数。本番設定は書き換えない。"""

    name: str
    description: str
    # None は現行（DEFAULT_STYLE_ADVANTAGE_WEIGHTS）を意味する。
    weights: StyleAdvantageWeights | None


@dataclass(frozen=True)
class StyleAdvantageProfileResult:
    """候補係数を同一レース集合へ適用した結果。"""

    profile: StyleAdvantageProfile
    lift: StyleAdvantageLift | None


@dataclass(frozen=True)
class PaceStyleCell:
    """ある脚質×あるペース区分の好走実績。"""

    pace_label: str
    n: int
    good_runs: int

    @property
    def good_rate(self) -> float:
        return self.good_runs / self.n if self.n else 0.0


@dataclass(frozen=True)
class PaceStyleRow:
    """ある脚質の、ペース区分別の好走実績。"""

    style: str
    n: int
    good_runs: int
    cells: tuple[PaceStyleCell, ...]

    @property
    def good_rate(self) -> float:
        return self.good_runs / self.n if self.n else 0.0


@dataclass(frozen=True)
class PaceStyleMatrix:
    """実績ペース×確定脚質の素の好走率。有利度スコアを介さない一次データ。"""

    n_races: int
    n_horses: int
    baseline_rate: float
    rows: tuple[PaceStyleRow, ...]


@dataclass(frozen=True)
class StyleAdvantageGroupBands:
    """脚質グループ（前付け／差し追込）ごとの帯別集計。"""

    label: str
    n: int
    baseline_rate: float
    bands: tuple[StyleAdvantageBand, ...]


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
    # 2群比較だけでは「全域で弱い」と「極端な場面だけ強い」を区別できないため、
    # ユーザーが実際に目にする5段階ラベルと同じ粒度で好走率を並べる。
    bands: tuple[StyleAdvantageBand, ...] = ()
    # 同じ帯にスロー想定で加点された前付け馬とハイ想定で加点された差し追込馬が
    # 混ざるため、実績が食い違うと帯全体では相殺される。分けて保持する。
    style_groups: tuple[StyleAdvantageGroupBands, ...] = ()


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
    AbilityWeightProfile(
        name="recent10",
        description="参照走数を5走→10走へ拡大（得意なペース以外の要因も含め古い好走を拾えるか検証）",
        weights=AbilityWeights(recent_races=10),
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
        name="swing5",
        description="ペースの振れ幅をさらに弱める",
        weights=replace(DEFAULT_PAI_WEIGHTS, pace_swing=5.0),
    ),
    PaiWeightProfile(
        name="front-only",
        description="前付けだけ採点（ADR-0010と同じ構造）",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            sensitivity_flexible=0.0,
            sensitivity_stalker=0.0,
            sensitivity_closer=0.0,
        ),
    ),
    PaiWeightProfile(
        name="back-included",
        description="後方脚質にも実測どおりの弱い感応度を与える",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            sensitivity_stalker=-0.1,
            sensitivity_closer=-0.2,
        ),
    ),
    # pai-v4 が採った中心合わせを外した版。current との差が、中心合わせの寄与そのもの。
    # 未補正だと感応度1.0の脚質が 芝−6.2点・ダート+4.3点 の定数シフトを受ける。
    PaiWeightProfile(
        name="uncentered",
        description="中心合わせを外す（pai-v3 までの挙動）",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            pace_center_offset_turf=0.0,
            pace_center_offset_dirt=0.0,
        ),
    ),
    # 振れ幅を pai-v3 の値へ戻した版。中心を合わせた状態では swing 25/10/5/0 が
    # 全体相関 +0.073〜+0.074 で並ぶことを確認済み。回帰監視として常設する。
    PaiWeightProfile(
        name="swing25",
        description="振れ幅を pai-v3 の 25 へ戻す",
        weights=replace(DEFAULT_PAI_WEIGHTS, pace_swing=25.0),
    ),
    # 帰無仮説。ペース補正を全て切り、pace_affinity と距離・馬場減点だけにする。
    # これが current と並ぶなら、ペース補正は判別に寄与していないことになる。
    # 実測で感応度1.0の逃げが脚質内で最も判別できていない（芝+4.1% ダート+2.6%・
    # いずれも誤差内）ため、まず疑うべき仮説として常設する。
    PaiWeightProfile(
        name="pace-off",
        description="ペース補正を全て切る（帰無仮説・pace_affinityと減点のみ）",
        weights=replace(
            DEFAULT_PAI_WEIGHTS,
            sensitivity_escape=0.0,
            sensitivity_front=0.0,
            sensitivity_flexible=0.0,
            sensitivity_stalker=0.0,
            sensitivity_closer=0.0,
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
    # 市場比較用。popularity を rank として扱った同型のサンプル。
    market_samples: list[IntegratedSample] = field(default_factory=list)
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
        top1_win_rate=round(sum(1 for sample in top1 if sample.finish_pos == 1) / len(top1), 4)
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


def collect_pace_style_matrix(
    targets: Iterable[Race],
    repo: RaceRepository,
    rule_weights: RuleWeights = DEFAULT_RULE_WEIGHTS,
) -> PaceStyleMatrix | None:
    """実績ペース×確定脚質で、素の好走率を集計する。

    `--validate-style-advantage`は「現行ルールが当たっているか」を測るが、
    ここでは有利度スコアを介さず「どの脚質が、どのペースで走るのか」そのものを測る。
    ルールを作り直す際は、ルールの答え合わせではなくこちらが土台になる。
    自在は有利度スコアの対象外（_SCOREABLE_STYLES）だが、出走の3割超を占め
    前が苦しくなった分の受け皿になっている可能性があるため、ここでは対象に含める。
    """
    styles = (
        RunningStyleLabel.ESCAPE,
        RunningStyleLabel.FRONT,
        RunningStyleLabel.STALKER,
        RunningStyleLabel.CLOSER,
        RunningStyleLabel.FLEXIBLE,
    )
    labels = (PaceLabel.HIGH, PaceLabel.AVERAGE, PaceLabel.SLOW)
    # (脚質, ペース) -> [頭数, 好走数]
    counts: dict[tuple[RunningStyleLabel, PaceLabel], list[int]] = {
        (style, label): [0, 0] for style in styles for label in labels
    }
    n_races = 0
    for race in targets:
        if race.rpci_actual is None:
            continue
        pace = classify_pace(race.rpci_actual, race.track_type, rule_weights)
        counted = False
        for entry in repo.find_entries(race.race_key):
            if entry.running_style is None:
                continue
            try:
                style = RunningStyleLabel(entry.running_style)
            except ValueError:
                continue
            slot = counts.get((style, pace))
            if slot is None:
                continue
            slot[0] += 1
            slot[1] += int(is_good_run(entry.finish_pos, race.grade))
            counted = True
        if counted:
            n_races += 1

    total_n = sum(slot[0] for slot in counts.values())
    if total_n == 0:
        return None
    total_good = sum(slot[1] for slot in counts.values())
    rows = tuple(
        PaceStyleRow(
            style=style.value,
            n=sum(counts[(style, label)][0] for label in labels),
            good_runs=sum(counts[(style, label)][1] for label in labels),
            cells=tuple(
                PaceStyleCell(
                    pace_label=label.value,
                    n=counts[(style, label)][0],
                    good_runs=counts[(style, label)][1],
                )
                for label in labels
            ),
        )
        for style in styles
    )
    return PaceStyleMatrix(
        n_races=n_races,
        n_horses=total_n,
        baseline_rate=round(total_good / total_n, 4),
        rows=rows,
    )


DEFAULT_STYLE_ADVANTAGE_PROFILES: tuple[StyleAdvantageProfile, ...] = (
    StyleAdvantageProfile(
        name="current",
        description="現行（前後対称・自在は採点なし）",
        weights=None,
    ),
    StyleAdvantageProfile(
        name="closer-weak",
        description="差し追込の増幅だけ実測へ寄せる（差しは0＝常に互角）",
        weights=StyleAdvantageWeights(stalker_gain=0.0, closer_gain=0.4),
    ),
    StyleAdvantageProfile(
        # stalker_gain=0 だと差しが全頭スコア50へ潰れ、帯がひとつに集中して
        # 単調性を判定できない。差しを動かしたまま弱める案も並べて比べる。
        name="closer-mild",
        description="差し追込を弱めるが差しも動かす（差0.3/追0.5）",
        weights=StyleAdvantageWeights(stalker_gain=0.3, closer_gain=0.5),
    ),
    StyleAdvantageProfile(
        # 「後方脚質には順序づけられるシグナルが無い」という実測の論理的な終点。
        # 差し・追込を常に互角(50)とし、有利不利の主張を前付けだけに限る。
        name="back-neutral",
        description="差し・追込を常に互角にする（後方は順序づけない）",
        weights=StyleAdvantageWeights(stalker_gain=0.0, closer_gain=0.0),
    ),
    StyleAdvantageProfile(
        name="flexible-only",
        description="自在の採点だけ追加（前後の係数は現行のまま）",
        weights=StyleAdvantageWeights(flexible_gain=0.8),
    ),
    StyleAdvantageProfile(
        name="measured",
        description="ADR-0010の実測示唆値（逃1.3/先1.0/自在0.8/差0.0/追0.4）",
        weights=StyleAdvantageWeights(
            escape_gain=1.3,
            front_gain=1.0,
            stalker_gain=0.0,
            closer_gain=0.4,
            flexible_gain=0.8,
        ),
    ),
)


def compare_style_advantage_profiles(
    targets: Iterable[Race],
    repo: RaceRepository,
    profiles: Iterable[StyleAdvantageProfile] = DEFAULT_STYLE_ADVANTAGE_PROFILES,
) -> list[StyleAdvantageProfileResult]:
    """候補係数を同一レース集合へ適用し、有利度の分離力を比べる。候補は自動採用しない。"""
    races = list(targets)
    results: list[StyleAdvantageProfileResult] = []
    for profile in profiles:
        samples = collect_actual_style_advantage_samples(races, repo, weights=profile.weights)
        results.append(
            StyleAdvantageProfileResult(
                profile=profile,
                lift=summarize_style_advantage(samples),
            )
        )
    return results


def _is_monotonic(bands: tuple[StyleAdvantageBand, ...]) -> bool:
    """帯の好走率が不利→有利へ単調非減少か。頭数0の帯は判定から除く。"""
    rates = [band.good_rate for band in bands if band.n > 0]
    return all(a <= b for a, b in zip(rates, rates[1:], strict=False))


def format_style_advantage_profile_comparison(
    results: list[StyleAdvantageProfileResult],
) -> str:
    """候補係数の比較結果をCLI向けに整形する。"""
    lines = [
        "=" * 88,
        "脚質別有利度の係数候補比較（候補は自動採用しません）",
        "※ 実績ペース・確定脚質で採点し直した結果。単調性は帯別好走率が不利→有利で崩れないこと",
        "-" * 88,
        f"  {_pad_display('候補', 16)}{_pad_display('好走率差（現行差）', 20)}"
        f"{_pad_display('相関', 10)}{_pad_display('単調 前/後/自在', 18)}",
    ]
    baseline_gap: float | None = None
    for result in results:
        lift = result.lift
        if lift is None:
            lines.append(f"  {_pad_display(result.profile.name, 16)}有効サンプルなし")
            continue
        if baseline_gap is None:
            baseline_gap = lift.rate_gap
        delta = lift.rate_gap - baseline_gap
        by_label = {group.label: group for group in lift.style_groups}
        marks = []
        for label in ("前付け（逃げ・先行）", "差し追込", "自在"):
            group = by_label.get(label)
            # 採点していない脚質は「－」。×（非単調）と区別する。
            marks.append("－" if group is None else ("○" if _is_monotonic(group.bands) else "×"))
        lines.append(
            f"  {_pad_display(result.profile.name, 16)}"
            f"{_pad_display(f'{lift.rate_gap:+.1%} ({delta:+.1%})', 20)}"
            f"{_pad_display(f'{lift.point_biserial:+.3f}', 10)}"
            f"{_pad_display(' '.join(marks), 18)}"
        )
    lines.append("-" * 88)
    for result in results:
        lines.append(f"  {result.profile.name}: {result.profile.description}")
    lines.append("=" * 88)
    return "\n".join(lines)


def style_advantage_profiles_to_dict(
    results: list[StyleAdvantageProfileResult],
) -> list[dict[str, Any]]:
    return [
        {
            "name": result.profile.name,
            "description": result.profile.description,
            "lift": style_advantage_lift_to_dict(result.lift),
        }
        for result in results
    ]


def format_pace_style_matrix(matrix: PaceStyleMatrix | None) -> str:
    """実績ペース×確定脚質の素の好走率をCLI向けの表に整形する。"""
    if matrix is None:
        return "実績ペース×脚質: 有効サンプルなし"
    lines = [
        "=" * 78,
        "実績ペース × 確定脚質 の素の好走率（有利度スコアを介さない）",
        "※ ルールの答え合わせではなく、ルールを作り直すための土台",
        f"対象: {matrix.n_races:,}レース / {matrix.n_horses:,}頭"
        f" / 全体好走率 {matrix.baseline_rate:.1%}",
        "-" * 78,
        f"  {_pad_display('脚質', 8)}{_pad_display('頭数', 9)}{_pad_display('自脚質の平均', 14)}"
        f"{_pad_display('ハイ', 16)}{_pad_display('平均', 16)}{_pad_display('スロー', 16)}",
    ]
    for row in matrix.rows:
        if row.n == 0:
            continue
        cells = ""
        for cell in row.cells:
            if cell.n == 0:
                cells += _pad_display("-", 16)
                continue
            # 自脚質の平均と比べることで「この脚質がどのペースで走るか」だけを取り出す。
            ratio = cell.good_rate / row.good_rate if row.good_rate else 0.0
            cells += _pad_display(f"{cell.good_rate:.1%} ({ratio:.2f}x)", 16)
        lines.append(
            f"  {_pad_display(row.style, 8)}{_pad_display(f'{row.n:,}', 9)}"
            f"{_pad_display(f'{row.good_rate:.1%}', 14)}{cells}"
        )
    lines.append("-" * 78)
    lines.append("※ 括弧内はその脚質自身の平均に対する比。1.00xから離れるほどペースの影響が大きい")
    lines.append("=" * 78)
    return "\n".join(lines)


def _style_advantage_band_label(score: float) -> str:
    """スコアを5段階ラベルへ写す。

    境界は web の `styleVerdict`（apps/web/src/lib/pace.ts）と同一。ここを揃えないと
    「画面で有利と出ている馬の実績」を測っていることにならないため、
    独自の等間隔帯は使わない。
    """
    if score >= 65:
        return "有利"
    if score >= 55:
        return "やや有利"
    if score > 45:
        return "互角"
    if score > 35:
        return "やや不利"
    return "不利"


_STYLE_ADVANTAGE_GROUPS: tuple[tuple[str, frozenset[RunningStyleLabel]], ...] = (
    (
        "前付け（逃げ・先行）",
        frozenset({RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT}),
    ),
    (
        "差し追込",
        frozenset({RunningStyleLabel.STALKER, RunningStyleLabel.CLOSER}),
    ),
    # 自在を採点する候補では、どちらのグループにも属さないまま全体帯にだけ現れ、
    # 単調性を確認できなくなる。空なら表示側で落ちるので既定候補でも害はない。
    ("自在", frozenset({RunningStyleLabel.FLEXIBLE})),
)

_STYLE_ADVANTAGE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("不利", 0.0, 35.0),
    ("やや不利", 35.0, 45.0),
    ("互角", 45.0, 55.0),
    ("やや有利", 55.0, 65.0),
    ("有利", 65.0, 100.0),
)


def _summarize_style_advantage_bands(
    samples: list[StyleAdvantageSample],
) -> tuple[StyleAdvantageBand, ...]:
    """5段階ラベルごとの頭数と好走数を数える。"""
    counts: dict[str, list[int]] = {label: [0, 0] for label, _, _ in _STYLE_ADVANTAGE_BANDS}
    for sample in samples:
        slot = counts[_style_advantage_band_label(sample.score)]
        slot[0] += 1
        slot[1] += int(sample.good_run)
    return tuple(
        StyleAdvantageBand(
            label=label,
            lo=lo,
            hi=hi,
            n=counts[label][0],
            good_runs=counts[label][1],
        )
        for label, lo, hi in _STYLE_ADVANTAGE_BANDS
    )


def _summarize_style_advantage_groups(
    samples: list[StyleAdvantageSample],
) -> tuple[StyleAdvantageGroupBands, ...]:
    """前付け・差し追込それぞれの帯別集計を作る。脚質不明のサンプルは除く。"""
    groups: list[StyleAdvantageGroupBands] = []
    for label, members in _STYLE_ADVANTAGE_GROUPS:
        subset = [s for s in samples if s.running_style in members]
        if not subset:
            continue
        groups.append(
            StyleAdvantageGroupBands(
                label=label,
                n=len(subset),
                baseline_rate=round(sum(s.good_run for s in subset) / len(subset), 4),
                bands=_summarize_style_advantage_bands(subset),
            )
        )
    return tuple(groups)


@dataclass(frozen=True)
class RankingComparison:
    """統合順位と市場（単勝人気）を同一レース集合で比較した結果。

    利用者が比べる相手は「全馬平均」ではなく「1番人気を買った場合」なので、
    製品価値の判断にはこの比較が要る。`ability-v3` は成分に単勝人気を含むため、
    市場情報を使いながら市場を上回れているかという意味でも重要。
    """

    n_races: int  # 両方を計算できたレース数
    n_races_total: int  # バックテスト対象の全レース数
    integrated: IntegratedAccuracy
    market: IntegratedAccuracy

    @property
    def coverage(self) -> float:
        return self.n_races / self.n_races_total if self.n_races_total else 0.0

    @property
    def win_rate_delta(self) -> float:
        return round(self.integrated.top1_win_rate - self.market.top1_win_rate, 4)

    @property
    def good_rate_delta(self) -> float:
        return round(self.integrated.top1_good_rate - self.market.top1_good_rate, 4)

    @property
    def capture_rate_delta(self) -> float:
        return round(self.integrated.top3_good_capture_rate - self.market.top3_good_capture_rate, 4)

    @property
    def beats_market(self) -> bool:
        """3指標すべてで市場以上か。1つでも下回れば False。"""
        return (
            self.win_rate_delta >= 0 and self.good_rate_delta >= 0 and self.capture_rate_delta >= 0
        )


def compare_with_market(
    integrated_samples: list[IntegratedSample],
    market_samples: list[IntegratedSample],
    n_races_total: int,
) -> RankingComparison | None:
    """統合順位と単勝人気を、同じレース集合へ揃えてから比較する。

    人気が未取得のレースを片方だけに含めると比較が歪むため、両方に現れる
    レースだけを対象にする。市場側は popularity をそのまま rank として扱う。
    """
    if not integrated_samples or not market_samples:
        return None
    common = {s.race_key for s in integrated_samples} & {s.race_key for s in market_samples}
    if not common:
        return None

    integrated = summarize_integrated_accuracy(
        [s for s in integrated_samples if s.race_key in common]
    )
    market = summarize_integrated_accuracy([s for s in market_samples if s.race_key in common])
    if integrated is None or market is None:
        return None
    return RankingComparison(
        n_races=len(common),
        n_races_total=n_races_total,
        integrated=integrated,
        market=market,
    )


def format_ranking_comparison(comparison: RankingComparison | None) -> str:
    """統合順位と市場の比較をCLI向けに整形する。比較不能なら空文字。"""
    if comparison is None:
        return ""
    lines = [
        "",
        "■ 市場（単勝人気）との比較"
        f"  対象 {comparison.n_races:,}レース（{comparison.coverage:.0%}／人気データのある分）",
        f"    {'指標':<20}{'統合順位':>12}{'人気順':>12}{'差':>12}",
    ]
    rows = (
        (
            "1位の勝率",
            comparison.integrated.top1_win_rate,
            comparison.market.top1_win_rate,
            comparison.win_rate_delta,
        ),
        (
            "1位の好走率",
            comparison.integrated.top1_good_rate,
            comparison.market.top1_good_rate,
            comparison.good_rate_delta,
        ),
        (
            "TOP3の好走馬捕捉率",
            comparison.integrated.top3_good_capture_rate,
            comparison.market.top3_good_capture_rate,
            comparison.capture_rate_delta,
        ),
    )
    for label, ours, theirs, delta in rows:
        mark = " " if delta >= 0 else "!"
        lines.append(f"  {mark} {label:<20}{ours:>11.1%}{theirs:>12.1%}{delta:>+12.1%}")
    verdict = (
        "統合順位が3指標すべてで市場以上。"
        if comparison.beats_market
        else "市場を下回る指標がある（! 印）。順位予想の看板としての価値を再検討する材料。"
    )
    lines.append(f"  → {verdict}")
    lines.append(
        "  ※ ability-v3 は成分に単勝人気を含む。市場情報を使いながら市場に勝てているかを見る。"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class RankingStrategyResult:
    """並べ方ごとの統合順位の実績。市場との差も併記する。"""

    strategy: RankingStrategy
    accuracy: IntegratedAccuracy
    market: IntegratedAccuracy

    @property
    def win_rate_delta(self) -> float:
        return round(self.accuracy.top1_win_rate - self.market.top1_win_rate, 4)

    @property
    def good_rate_delta(self) -> float:
        return round(self.accuracy.top1_good_rate - self.market.top1_good_rate, 4)

    @property
    def capture_rate_delta(self) -> float:
        return round(self.accuracy.top3_good_capture_rate - self.market.top3_good_capture_rate, 4)


def format_ranking_strategy_comparison(
    results: list[RankingStrategyResult],
) -> str:
    """並べ方の比較をCLI向けに整形する。

    どの成分が順位付けに効いているかを切り分けるための出力。
    CURRENT と ABILITY_FIRST の差が「展開（PAI）を順位付けに使うことの効果」、
    ABILITY_FIRST と SCORE_ONLY の差が「tierで粗く丸めることの効果」になる。
    """
    if not results:
        return ""
    labels = {
        RankingStrategy.CURRENT: "現行(tier→展開→score)",
        RankingStrategy.ABILITY_FIRST: "展開を使わない(tier→score)",
        RankingStrategy.SCORE_ONLY: "能力scoreのみ",
    }
    lines = [
        "",
        "=" * 78,
        "■ 統合順位の並べ方の比較（どの成分が効いているかの切り分け）",
        "=" * 78,
        f"  {'並べ方':<28}{'1位勝率':>10}{'1位好走率':>12}{'TOP3捕捉':>11}",
    ]
    for r in results:
        lines.append(
            f"  {labels.get(r.strategy, str(r.strategy)):<28}"
            f"{r.accuracy.top1_win_rate:>9.1%}"
            f"{r.accuracy.top1_good_rate:>11.1%}"
            f"{r.accuracy.top3_good_capture_rate:>10.1%}"
        )
    market = results[0].market
    lines.append(
        f"  {'（参考）単勝人気順':<28}"
        f"{market.top1_win_rate:>9.1%}"
        f"{market.top1_good_rate:>11.1%}"
        f"{market.top3_good_capture_rate:>10.1%}"
    )
    lines.append(
        "\n  読み方: 現行と「展開を使わない」の差が、展開(PAI)を順位付けへ使うことの効果。"
        "\n          さらに「能力scoreのみ」との差が、tierで粗く丸めることの効果。"
        "\n  ※ どれも人気順を下回るなら、順位予想そのものを看板から外す判断材料になる。"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class PaiStyleRow:
    """脚質ごとの PAI 平均と実際の好走率。"""

    style: str
    n: int
    mean_pai: float
    good_rate: float


def summarize_pai_by_style(samples: list[HorseSample]) -> list[PaiStyleRow]:
    """脚質ごとに PAI の平均と実際の好走率を並べる。

    構成を把握するための表であって、性能評価ではない。pai-v3 の PAI は
    「その脚質にとって普段どおりの流れか」を表す**脚質内の相対量**なので、
    脚質をまたいだ平均の大小は何も主張していない（感応度0の差し・追込は
    ペース由来の振れが無く、常に基準点付近へ集まる）。
    脚質の定数効果を除いた効きは `summarize_pai_within_style` で見ること。
    """
    styles = sorted({s.running_style for s in samples if s.running_style})
    rows: list[PaiStyleRow] = []
    for style in styles:
        group = [s for s in samples if s.running_style == style]
        if not group:
            continue
        rows.append(
            PaiStyleRow(
                style=style,
                n=len(group),
                mean_pai=round(sum(s.pai for s in group) / len(group), 1),
                good_rate=round(sum(1 for s in group if s.good_run) / len(group), 4),
            )
        )
    return sorted(rows, key=lambda r: -r.mean_pai)


@dataclass(frozen=True)
class PaiWithinStyleRow:
    """脚質を固定したときに、PAI が好走を判別できているか。"""

    style: str
    n: int
    baseline_rate: float
    group_n: int  # 上位1/3・下位1/3それぞれの頭数
    low_mean_pai: float
    low_rate: float
    high_mean_pai: float
    high_rate: float

    @property
    def spread(self) -> float:
        """上位1/3と下位1/3の好走率差。脚質の定数効果を除いたペース依存の純効果。"""
        return self.high_rate - self.low_rate

    @property
    def pai_spread(self) -> float:
        """上位1/3と下位1/3の PAI 差。小さいならそもそも判別する幅が無い。"""
        return self.high_mean_pai - self.low_mean_pai

    @property
    def spread_se(self) -> float:
        """好走率差の標準誤差。独立2標本の比率差なので分散を足す。"""
        if self.group_n <= 0:
            return 0.0
        hi, lo = self.high_rate, self.low_rate
        return math.sqrt((hi * (1 - hi) + lo * (1 - lo)) / self.group_n)

    @property
    def is_significant(self) -> bool:
        """差が誤差の2倍を超えているか。頭数の閾値より直接的に判断できる。"""
        se = self.spread_se
        return se > 0 and abs(self.spread) >= 2 * se


def summarize_pai_within_style(samples: list[HorseSample]) -> list[PaiWithinStyleRow]:
    """脚質を固定した上で、PAI 上位1/3と下位1/3の好走率を比べる。

    pai-v3 の PAI は脚質内の相対量なので、脚質をまたいだ集計では性能を測れない。
    実際「PAI帯 → 好走率」の表が 40-60 帯で沈むのは、感応度0の差し・追込
    （好走率 0.47〜0.99x と元々走らない脚質）がそこへ積み上がるためで、
    PAI の判別力とは別の話。脚質を固定すれば定数効果が落ち、ペース依存の
    純効果だけが残る。

    同値が多い脚質では順位で切るため境界の割り当ては任意になる。判別する幅が
    あったかは `pai_spread` で確認すること。
    """
    rows: list[PaiWithinStyleRow] = []
    for style in sorted({s.running_style for s in samples if s.running_style}):
        group = sorted((s for s in samples if s.running_style == style), key=lambda s: s.pai)
        cut = len(group) // 3
        if cut < 1:
            continue
        low, high = group[:cut], group[-cut:]
        rows.append(
            PaiWithinStyleRow(
                style=style,
                n=len(group),
                baseline_rate=round(sum(1 for s in group if s.good_run) / len(group), 4),
                group_n=cut,
                low_mean_pai=round(sum(s.pai for s in low) / cut, 1),
                low_rate=round(sum(1 for s in low if s.good_run) / cut, 4),
                high_mean_pai=round(sum(s.pai for s in high) / cut, 1),
                high_rate=round(sum(1 for s in high if s.good_run) / cut, 4),
            )
        )
    return sorted(rows, key=lambda r: -r.spread)


@dataclass(frozen=True)
class FitLabelShare:
    """展開合致ラベルの構成比と、各ラベルの実際の好走率。

    `style` が空文字なら、そのコース全体（脚質を跨いだ集計）を表す。
    """

    track_type: str
    style: str
    label: str
    n: int
    share: float
    good_rate: float


def summarize_fit_label_shares(samples: list[HorseSample]) -> list[FitLabelShare]:
    """コース×脚質×ラベルごとの構成比と好走率を出す。

    **脚質を跨いだ集計だけを見て閾値の良し悪しを判断してはいけない。** ラベルは
    PAI から作られ、PAI は脚質内の相対量だからである。実測では「不利」の好走率が
    「中立」を上回る（芝 24.3% 対 17.9%・ダート 22.8% 対 16.2%）が、これは閾値の
    ずれではなく脚質構成の差である可能性が高い——絶対的な好走率は脚質ごとに
    0.47x〜1.43x と大きく違うため。

    判断は**脚質を固定した行**で行う。同一脚質の中で 合致 > 中立 > 不利 の順に
    なっていればラベルは機能している。なっていなければ閾値がスケールに合っていない。
    """

    def _rows_for(track: str, style: str, group: list[HorseSample]) -> list[FitLabelShare]:
        out: list[FitLabelShare] = []
        for label in ("合致", "中立", "不利"):
            members = [s for s in group if s.fit_label == label]
            out.append(
                FitLabelShare(
                    track_type=track,
                    style=style,
                    label=label,
                    n=len(members),
                    share=round(len(members) / len(group), 4),
                    good_rate=(
                        round(sum(1 for s in members if s.good_run) / len(members), 4)
                        if members
                        else 0.0
                    ),
                )
            )
        return out

    rows: list[FitLabelShare] = []
    for track in ("芝", "ダート"):
        group = [s for s in samples if s.track_type == track and s.fit_label]
        if not group:
            continue
        rows.extend(_rows_for(track, "", group))
        for style in sorted({s.running_style for s in group if s.running_style}):
            in_style = [s for s in group if s.running_style == style]
            rows.extend(_rows_for(track, style, in_style))
    return rows


FIT_CROWDING_TARGET_MEDIAN_SHARE = 0.30
"""1レースあたり「向く」と出す頭数の目標割合（中央値）。

根拠は思い付きではなく**芝の現状**。芝は中央値30.0%・合致4.0頭で、16頭立てなら
4頭という使える絞り込みになっており、実機で問題として挙がったのはダート側だった
（中央値53.8%・7.0頭）。**問題の出ていない側を目標に置く**のが、恣意的な数字を
新しく持ち込まずに済む唯一の選び方。
"""


@dataclass(frozen=True)
class FitCrowdingRow:
    """1コース分の「レースあたり何割が合致になるか」の分布。"""

    track_type: str
    races: int
    median_share: float
    p90_share: float
    majority_race_share: float
    all_suited_race_share: float
    median_suited_count: float
    # 中央値を目標割合まで下げる `matched_threshold`。届かなければ None。
    recommended_threshold: float | None = None
    # 上の閾値を当てたときの中央値（目標に届いたかを目で確かめるため）。
    recommended_median_share: float | None = None


def summarize_fit_crowding(samples: list[HorseSample]) -> list[FitCrowdingRow]:
    """**レース単位**で合致の割合を集計する。

    `summarize_fit_label_shares` は全頭を混ぜた構成比なので、「1レースの中で
    何頭が合致になるか」が見えない。全体で3割でも、**一部のレースで全頭合致**に
    なっていれば、そのレースでは絞り込みの手がかりにならない。

    展開の恩恵は本来相対的な価値で、**全員に向く流れは誰の武器でもない**。
    合致の判定は馬ごとの絶対閾値（PAI >= 55）で、レース内の頭数を制御しないため、
    ペースが強く傾いたレースほど片側の脚質が丸ごと合致になりうる。その頻度を測る。
    """
    rows: list[FitCrowdingRow] = []
    for track in ("芝", "ダート"):
        group = [s for s in samples if s.track_type == track and s.fit_label]
        if not group:
            continue
        by_race: dict[str, list[HorseSample]] = {}
        for sample in group:
            by_race.setdefault(sample.race_key, []).append(sample)

        shares: list[float] = []
        counts: list[int] = []
        for horses in by_race.values():
            matched = sum(1 for h in horses if h.fit_label == "合致")
            shares.append(matched / len(horses))
            counts.append(matched)
        shares.sort()
        counts.sort()

        def _percentile(values: list[float], q: float) -> float:
            if not values:
                return 0.0
            index = min(len(values) - 1, int(q * len(values)))
            return values[index]

        threshold, threshold_median = _solve_matched_threshold(list(by_race.values()))

        rows.append(
            FitCrowdingRow(
                track_type=track,
                races=len(by_race),
                median_share=round(_percentile(shares, 0.5), 4),
                p90_share=round(_percentile(shares, 0.9), 4),
                majority_race_share=round(
                    sum(1 for share in shares if share >= 0.5) / len(shares), 4
                ),
                all_suited_race_share=round(
                    sum(1 for share in shares if share >= 0.999) / len(shares), 4
                ),
                median_suited_count=round(_percentile([float(c) for c in counts], 0.5), 2),
                recommended_threshold=threshold,
                recommended_median_share=threshold_median,
            )
        )
    return rows


def _solve_matched_threshold(
    races: list[list[HorseSample]],
    target: float = FIT_CROWDING_TARGET_MEDIAN_SHARE,
) -> tuple[float | None, float | None]:
    """レースあたりの合致割合の中央値を `target` 以下にする最小の閾値を返す。

    **最小**を採るのは、絞れさえすれば良いわけではないため。閾値を上げるほど
    合致は減るが、上げ過ぎれば本来恩恵を受ける馬まで落ちる。目標に届いた時点で
    止めるのが、絞り込みのために失う情報を最小にする置き方になる。

    0.5点刻みで走査する。PAI は小数第1位まで丸めて出るので、それより細かい刻みは
    データに無い精度を装うだけになる。
    """
    if not races:
        return None, None

    def median_share(threshold: float) -> float:
        shares = sorted(
            sum(1 for h in horses if h.pai >= threshold) / len(horses) for horses in races
        )
        return shares[min(len(shares) - 1, len(shares) // 2)]

    candidate = 45.0
    while candidate <= 85.0:
        share = median_share(candidate)
        if share <= target:
            return candidate, round(share, 4)
        candidate += 0.5
    return None, None


@dataclass(frozen=True)
class FitThresholdByStyleRow:
    """1（コース×脚質）分の、合致になっている割合と目標へ合わせる閾値。"""

    track_type: str
    running_style: str
    horses: int
    current_share: float
    recommended_threshold: float | None
    recommended_share: float | None
    # 推奨閾値の1段手前（0.5点下）での割合。閾値を跨いだ落差を見るために持つ。
    share_before: float | None = None
    # 落差が目標割合より大きい＝1刻みの中に目標より多くの馬が固まっている。
    # このとき閾値では目標へ着地できず、推奨値は「答えに見えるだけの数字」になる。
    splittable: bool = True


def summarize_fit_threshold_by_style(
    samples: list[HorseSample],
    target: float = FIT_CROWDING_TARGET_MEDIAN_SHARE,
) -> list[FitThresholdByStyleRow]:
    """**（コース×脚質）ごとに**合致の閾値を解く。

    診断表の注記が言うとおり、PAI は脚質内の相対量で、大小を脚質間で比較できない
    （pai-v3 以降）。ところが `matched_threshold` は全脚質・両コース共通の定数で、
    **脚質内の量を絶対値と比べている**。これは内部矛盾で、実測にそのまま出ている:

        ダート  差し PAI平均 59.4 → 合致 48.1%
        ダート  自在 PAI平均 46.8 → 合致  5.1%
        芝     自在 PAI平均 48.7 → 合致  0.0%（602頭中0頭）

    芝の自在は**構造的に合致へ到達できない**。単一の閾値は、脚質間で比べないという
    前提を破った上で、暗黙のうちに脚質の順位付けを持ち込んでいる。

    コース単位で閾値を上げるだけではこれが悪化する（ダートを70.5にすると自在は
    確実に0になる）。脚質ごとに同じ割合で切れば、レース内の合致頭数は脚質構成に
    依らず目標へ寄り、**かつ脚質をまたいだ比較を持ち込まない**。

    目標は馬単位の割合。1レースの出走馬がどの脚質で構成されていても、各脚質から
    目標割合ずつ選ばれるので、レース単位の割合もそこへ収束する。
    """
    rows: list[FitThresholdByStyleRow] = []
    for track in ("芝", "ダート"):
        in_track = [s for s in samples if s.track_type == track and s.fit_label]
        styles = sorted({s.running_style for s in in_track if s.running_style})
        for style in styles:
            group = [s for s in in_track if s.running_style == style]
            if not group:
                continue
            threshold, share, before = _solve_share_threshold(group, target)
            rows.append(
                FitThresholdByStyleRow(
                    track_type=track,
                    running_style=style,
                    horses=len(group),
                    current_share=round(
                        sum(1 for s in group if s.fit_label == "合致") / len(group), 4
                    ),
                    recommended_threshold=threshold,
                    recommended_share=share,
                    share_before=before,
                    splittable=_is_splittable(share, before, target),
                )
            )
    return rows


def _is_splittable(
    share: float | None,
    share_before: float | None,
    target: float,
) -> bool:
    """閾値で目標割合へ着地できるか。0.5点の1刻みに目標より多く固まっていたら不可。

    実測で `ダート 差し` がこれに当たった: 75.0 で48.1%、75.5 で0.0%。
    **PAI 75.0 に馬が固まっていて、その上には1頭もいない。**

    理由は式にある。感応度0の脚質（差し・追込）は `base_pai` が中立の50で固定され、
    PAI は `0.5×50 + 0.5×affinity` になる。affinity は
    `build_horse_pace_affinity_profile` が**その馬自身の最良レベルを100へ正規化**する
    ので上限100、つまり PAI の上限は 75.0。予測ペースがその馬の得意レベルと一致すれば
    誰でも 100 が付く。ダートはほぼ全レースが同じペース区分に入るため、多くの馬が
    そこに並ぶ。**affinity が「どれだけ向くか」ではなく「一番得意か否か」を答えている。**

    このとき閾値をどこに置いても目標へは着地できない。塊ごと入れるか、丸ごと落とすか
    しかない。**そこで返す数字は答えではないので、答えの顔をさせない。**
    """
    if share is None or share_before is None:
        return False
    return (share_before - share) <= target


def _solve_share_threshold(
    horses: list[HorseSample],
    target: float,
) -> tuple[float | None, float | None, float | None]:
    """この集団の合致割合を `target` 以下にする最小の閾値を返す。

    `_solve_matched_threshold` と同じ規則（最小・0.5点刻み・届かなければ None）だが、
    見るのはレース単位の中央値ではなく集団全体の割合。

    3つ目に返すのは1段手前（0.5点下）での割合。**落差を見ないと、塊を跨いだだけの
    値を「推奨」として受け取ってしまう。**

    走査は中立点の1段上から始める。**分布だけを見て解くと意味を踏み外す**——
    pai-v5 の初版で芝の自在に 49.5（中立点50の下）が出て、「普段どおりより悪い流れ」の
    馬を合致と呼びかけた。ドメイン側でも `PaiWeights.__post_init__` が弾くが、
    弾かれる値を推奨として出すこと自体が誤り。
    """
    if not horses:
        return None, None, None

    def share_at(threshold: float) -> float:
        return sum(1 for h in horses if h.pai >= threshold) / len(horses)

    candidate = DEFAULT_PAI_WEIGHTS.pace_neutral_pai + 0.5
    previous = share_at(candidate)
    while candidate <= 85.0:
        share = share_at(candidate)
        if share <= target:
            return candidate, round(share, 4), round(previous, 4)
        previous = share
        candidate += 0.5
    return None, None, None


def format_fit_threshold_by_style(rows: list[FitThresholdByStyleRow]) -> str:
    """脚質ごとの合致割合と推奨閾値を表示する。"""
    if not rows:
        return ""
    lines = [
        "",
        "  ── 脚質ごとの合致割合と推奨閾値（PAIは脚質内の相対量なので、閾値も脚質ごと）",
        f"    {'コース':<8}{'脚質':<8}{'頭数':>8}{'現在の合致':>12}"
        f"{'推奨閾値':>10}{'1段手前':>10}{'適用後':>9}{'判定':>10}",
    ]
    for row in rows:
        threshold = (
            "届かず" if row.recommended_threshold is None else f"{row.recommended_threshold:.1f}"
        )
        share = "—" if row.recommended_share is None else f"{row.recommended_share:.1%}"
        before = "—" if row.share_before is None else f"{row.share_before:.1%}"
        verdict = "採用可" if row.splittable else "分割不能"
        lines.append(
            f"    {row.track_type:<8}{row.running_style:<8}{row.horses:>8,}"
            f"{row.current_share:>11.1%}{threshold:>10}{before:>10}{share:>9}{verdict:>8}"
        )
    lines.append("    ※ 単一の閾値は、脚質間で比較できない量を共通の絶対値と比べている。")
    lines.append("       実測では芝の自在が602頭中0頭で、構造的に合致へ到達できない。")
    lines.append("       コース単位で閾値を上げるとこれが悪化する（脚質ごとに切ること）。")
    lines.append("    ※ 「分割不能」は、0.5点の1刻みに目標より多くの馬が固まっている状態。")
    lines.append("       閾値をどこへ置いても目標へ着地できないので、推奨値を採用しないこと。")
    lines.append("       感応度0の脚質（差し・追込）は PAI が 25〜75 に収まり、")
    lines.append("       予測ペースが得意レベルと一致した馬は一律 75.0 に並ぶ（affinity=100）。")
    return "\n".join(lines)


CROWDING_SWEEP_TARGETS = (0.30, 0.25, 0.20, 0.15, 0.10)
"""試す目標割合（脚質ごとに合致にする馬の割合）。"""


@dataclass(frozen=True)
class CrowdingSweepRow:
    """ある目標割合を当てたときの、レース単位の絞り込み具合。"""

    target: float
    track_type: str
    median_share: float
    majority_race_share: float
    all_suited_race_share: float
    median_suited_count: float
    thresholds: tuple[tuple[str, float], ...]
    # 分割不能で現行の閾値を据え置いた脚質。**この行の数字はその分だけ現状寄り**。
    kept_as_is: tuple[str, ...] = ()


def summarize_crowding_sweep(
    samples: list[HorseSample],
    targets: tuple[float, ...] = CROWDING_SWEEP_TARGETS,
) -> list[CrowdingSweepRow]:
    """目標割合を振って、**「絞りにくい」と出るレースの割合**がどう動くかを測る。

    `summarize_fit_threshold_by_style` は目標を1つ決め打ちして閾値を解く。だが
    実際に効くのは中央値ではなく**裾**で、pai-v5（目標30%）の実測はこうなっていた:

        芝    中央値 25.0% / 90%点 60.0% / 半数以上 21.6%
        ダート  中央値 33.3% / 90%点 66.7% / 半数以上 30.4%

    重み付ければ**約4分の1のレース**で「展開では絞りにくいレースです」が出る。
    フォールバックが4回に1回出るなら、それはフォールバックではない。

    裾がここまで広いのは構造。`pace_deviation` はレース単位の定数で、脚質ごとの
    感応度を掛けて全馬に同じ向きの加減点を与える。**ある脚質の馬は揃って閾値を
    跨ぐ**ので、レース内の合致頭数は「ほぼ0か、ほぼ全部」に寄りやすい。
    馬ごとの絶対閾値をどう置いても、レース単位の頭数は直接には制御できない。

    できるのは目標割合を下げて分布ごと左へ寄せることなので、**下げ幅と裾の縮み方の
    対応表**を出す。目標を勘で選び直さないための材料。
    """
    rows: list[CrowdingSweepRow] = []
    for target in targets:
        thresholds: dict[tuple[str, str], float] = {}
        unsplittable: set[tuple[str, str]] = set()
        for row in summarize_fit_threshold_by_style(samples, target):
            # **分割不能なセルの解を当ててはいけない。** そこで返る値は目標へ着地
            # できておらず、たいてい PAI の上限（75.0）の外側で合致0頭になる。
            # ドメインは現にダートの差しを 55.0 のまま据え置いているので、
            # ここも現行のラベルを使う。これを取り違えると、そのセルの馬が丸ごと
            # 合致から消え、**「絞りにくい」レースが実際より少なく見える**
            # （最初の実装がこれで、ダートの実測30.4%に対し6.9%と出していた）。
            if row.recommended_threshold is None or not row.splittable:
                unsplittable.add((row.track_type, row.running_style))
                continue
            thresholds[(row.track_type, row.running_style)] = row.recommended_threshold

        for track in ("芝", "ダート"):
            group = [s for s in samples if s.track_type == track and s.fit_label]
            if not group:
                continue
            by_race: dict[str, list[HorseSample]] = {}
            for sample in group:
                by_race.setdefault(sample.race_key, []).append(sample)

            shares: list[float] = []
            counts: list[float] = []
            for horses in by_race.values():
                matched = sum(
                    1
                    for h in horses
                    # 閾値が解けなかった脚質は現状のラベルのまま数える。
                    if (
                        h.pai >= thresholds[(track, h.running_style)]
                        if (track, h.running_style) in thresholds
                        else h.fit_label == "合致"
                    )
                )
                shares.append(matched / len(horses))
                counts.append(float(matched))
            shares.sort()
            counts.sort()
            middle = min(len(shares) - 1, len(shares) // 2)

            rows.append(
                CrowdingSweepRow(
                    target=target,
                    track_type=track,
                    median_share=round(shares[middle], 4),
                    majority_race_share=round(sum(1 for s in shares if s >= 0.5) / len(shares), 4),
                    all_suited_race_share=round(
                        sum(1 for s in shares if s >= 0.999) / len(shares), 4
                    ),
                    median_suited_count=round(counts[middle], 2),
                    thresholds=tuple(
                        (style, value)
                        for (row_track, style), value in sorted(thresholds.items())
                        if row_track == track
                    ),
                    kept_as_is=tuple(
                        style for (row_track, style) in sorted(unsplittable) if row_track == track
                    ),
                )
            )
    return rows


def format_crowding_sweep(rows: list[CrowdingSweepRow]) -> str:
    """目標割合ごとの「絞りにくい」レース比率を表示する。"""
    if not rows:
        return ""
    lines = [
        "",
        "  ── 目標割合を振ったときの「絞りにくい」レース比率（裾がどこまで縮むか）",
        f"    {'目標':>5}  {'コース':<8}{'中央値':>9}{'半数以上':>10}"
        f"{'全頭合致':>10}{'合致頭数':>10}  脚質別の閾値",
    ]
    for row in rows:
        thresholds = " / ".join(f"{style}{value:.1f}" for style, value in row.thresholds)
        if row.kept_as_is:
            thresholds += f" ／ 据え置き: {'・'.join(row.kept_as_is)}"
        lines.append(
            f"    {row.target:>5.0%}  {row.track_type:<8}{row.median_share:>8.1%}"
            f"{row.majority_race_share:>10.1%}{row.all_suited_race_share:>10.1%}"
            f"{row.median_suited_count:>10.1f}  {thresholds}"
        )
    lines.append("    ※ 「半数以上」がそのまま**画面に『絞りにくい』と出るレースの割合**。")
    lines.append(
        "       pai-v5（目標30%）では重み付きで約25%。4回に1回出るならフォールバックではない。"
    )
    lines.append("    ※ 中央値ではなく裾を見て決めること。裾が広いのは構造で、")
    lines.append("       `pace_deviation` がレース単位の定数のため同じ脚質の馬が揃って閾値を跨ぐ。")
    lines.append(
        "    ※ 「据え置き」は分割不能で現行の閾値のままにした脚質。その分この行は現状寄り。"
    )
    lines.append("       **解が出ても分割不能なら当てないこと。** PAI上限の外側で合致0頭になり、")
    lines.append("       そのセルの馬が丸ごと消えて「絞りにくい」が実際より少なく見える。")
    return "\n".join(lines)


def format_fit_crowding(rows: list[FitCrowdingRow]) -> str:
    """レースあたりの合致割合を表示する。"""
    if not rows:
        return ""
    lines = [
        "",
        "  ── レースあたりの合致割合（絞り込みが効いているか）",
        f"    {'コース':<8}{'レース数':>9}{'中央値':>9}{'90%点':>9}"
        f"{'半数以上':>10}{'全頭合致':>10}{'合致頭数':>10}{'推奨閾値':>10}{'適用後':>9}",
    ]
    for row in rows:
        threshold = (
            "届かず" if row.recommended_threshold is None else f"{row.recommended_threshold:.1f}"
        )
        applied = (
            "—" if row.recommended_median_share is None else f"{row.recommended_median_share:.1%}"
        )
        lines.append(
            f"    {row.track_type:<8}{row.races:>9,}"
            f"{row.median_share:>8.1%}{row.p90_share:>9.1%}"
            f"{row.majority_race_share:>10.1%}{row.all_suited_race_share:>10.1%}"
            f"{row.median_suited_count:>10.1f}{threshold:>10}{applied:>9}"
        )
    lines.append("    ※ 「半数以上」は、出走馬の半数以上が合致になったレースの割合。")
    lines.append("       この値が高いほど、展開では馬を絞れていない。")
    lines.append(
        f"    ※ 推奨閾値は、中央値を目標 {FIT_CROWDING_TARGET_MEDIAN_SHARE:.0%} 以下へ下げる"
        "最小の `matched_threshold`。"
    )
    lines.append("       目標は芝の現状。**問題が出ていない側**を基準に置き、")
    lines.append("       新しい恣意的な数字を持ち込まない。")
    lines.append(
        "       採用するなら期間外でも確認すること（同一期間から取った当てはめ値のため）。"
    )
    return "\n".join(lines)


def format_fit_label_shares(rows: list[FitLabelShare]) -> str:
    """展開合致ラベルの構成比を表示する。"""
    if not rows:
        return ""
    lines = [
        "",
        "  ── 展開合致ラベルの構成比（脚質を固定して見ること）",
        f"    {'コース':<8}{'脚質':<8}{'ラベル':<8}{'頭数':>8}"
        f"{'構成比':>9}{'好走率':>9}{'判定':>8}",
    ]
    by_group: dict[tuple[str, str], list[FitLabelShare]] = {}
    for r in rows:
        by_group.setdefault((r.track_type, r.style), []).append(r)

    for (track, style), items in by_group.items():
        rates = {i.label: i.good_rate for i in items}
        ordered = rates["合致"] >= rates["中立"] >= rates["不利"]
        verdict = "順当" if ordered else "逆転"
        for i, item in enumerate(items):
            lines.append(
                f"    {track:<8}{(style or '全体'):<8}{item.label:<8}{item.n:>9,}"
                f"{item.share:>9.1%}{item.good_rate:>9.1%}"
                f"{(verdict if i == 0 else ''):>9}"
            )
    lines.append(
        "    ※ **「全体」行の逆転で閾値を判断しないこと。** ラベルはPAIから作られ、"
        "\n       PAIは脚質内の相対量なので、脚質を跨いだ集計は脚質構成の差を拾う"
        "\n       （絶対的な好走率は脚質ごとに 0.47x〜1.43x と違う）。"
        "\n    ※ 判断は脚質を固定した行で行う。同一脚質の中で 合致 > 中立 > 不利 に"
        "\n       なっていればラベルは機能している。ラベルはUI表示と mart 層へそのまま出る。"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class PaceCentering:
    """ペース補正が0を中心に振れているか。ずれていれば脚質を相対的にずらす。"""

    track_type: str
    n: int
    mean_forecast_rpci: float
    neutral: float
    half_band: float
    mean_deviation: float
    pace_swing: float
    # 平均ずれを0にする `pace_center_offset_*`。現行中心からの差分（RPCI点）。
    recommended_offset: float

    @property
    def mean_bonus_at_full_sensitivity(self) -> float:
        """感応度1.0の脚質が平均して受け取る加点。0でなければ定数シフト。"""
        return self.mean_deviation * self.pace_swing

    @property
    def is_centered(self) -> bool:
        """加点の平均が1点未満なら、実用上は中心が合っているとみなす。"""
        return abs(self.mean_bonus_at_full_sensitivity) < 1.0


def _solve_center_offset(forecasts: list[float], track_type: str, weights: PaiWeights) -> float:
    """平均 deviation を0にする中心オフセットを二分法で求める。

    予測RPCIの平均を中心に置くだけでは足りない。deviation は±1で頭打ちになるため、
    分布が非対称なら平均が中心と一致していても平均 deviation は0にならない。
    実際ダートは予測平均46.55・中立46.50とほぼ一致しているのに平均ずれ +0.172 で、
    感応度1.0の脚質が +4.3点 の底上げを受けていた。頭打ちの効果まで含めて解く。
    """

    def mean_dev(offset: float) -> float:
        shifted = replace(
            weights,
            pace_center_offset_dirt=offset if track_type == "ダート" else 0.0,
            pace_center_offset_turf=0.0 if track_type == "ダート" else offset,
        )
        return sum(pace_deviation(f, track_type, shifted) for f in forecasts) / len(forecasts)

    base = (
        weights.pace_center_offset_dirt
        if track_type == "ダート"
        else weights.pace_center_offset_turf
    )
    lo, hi = base - 10.0, base + 10.0
    # mean_dev は offset について単調減少。端で符号が変わらなければ解無し。
    if mean_dev(lo) < 0 or mean_dev(hi) > 0:
        return base
    for _ in range(60):
        mid = (lo + hi) / 2
        if mean_dev(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


def summarize_pace_centering(
    samples: list[HorseSample], weights: PaiWeights = DEFAULT_PAI_WEIGHTS
) -> list[PaceCentering]:
    """コース別に、ペース補正の平均が0からどれだけずれているかを測る。

    pai-v3 は「コース平均を0として±へ振れる」設計なので、平均が0なら脚質間の
    相対位置は動かず、脚質内の判別だけに寄与する。平均が0から離れていると、
    感応度の高い脚質だけが系統的に底上げ（または底下げ）され、**pai-v2 が
    やっていた「脚質の定数効果をPAIへ埋め込む」ことを別経路で再現してしまう**。

    予測RPCI の分布が `neutral_rpci`（閾値の中点）とずれると、これが起きる。
    """
    rows: list[PaceCentering] = []
    for track in ("芝", "ダート"):
        group = [s for s in samples if s.track_type == track and s.forecast_rpci]
        if not group:
            continue
        forecasts = [s.forecast_rpci for s in group]
        deviations = [pace_deviation(f, track, weights) for f in forecasts]
        rows.append(
            PaceCentering(
                track_type=track,
                n=len(group),
                mean_forecast_rpci=round(sum(forecasts) / len(forecasts), 2),
                neutral=pace_center(track, weights),
                half_band=pace_half_band(track),
                mean_deviation=round(sum(deviations) / len(deviations), 4),
                pace_swing=weights.pace_swing,
                recommended_offset=_solve_center_offset(forecasts, track, weights),
            )
        )
    return rows


def format_pace_centering(rows: list[PaceCentering]) -> str:
    """ペース補正の中心ずれを表示する。"""
    if not rows:
        return ""
    lines = [
        "",
        "  ── ペース補正の中心ずれ（0から離れるほど脚質の定数効果を埋め込む）",
        f"    {'コース':<8}{'頭数':>8}{'予測RPCI平均':>13}{'中立値':>9}"
        f"{'平均ずれ':>10}{'感応度1.0の平均加点':>20}{'判定':>7}{'推奨offset':>12}",
    ]
    for r in rows:
        verdict = "中心一致" if r.is_centered else "ずれ"
        lines.append(
            f"    {r.track_type:<8}{r.n:>9,}{r.mean_forecast_rpci:>12.2f}{r.neutral:>10.2f}"
            f"{r.mean_deviation:>+11.3f}{r.mean_bonus_at_full_sensitivity:>+17.1f}点{verdict:>8}"
            f"{r.recommended_offset:>+12.2f}"
        )
    lines.append(
        "    ※ 加点の平均が0でなければ、感応度の高い脚質だけが系統的に底上げされる。"
        "\n       脚質間の相対位置が動くので、脚質をまたいだ相関は改善して見えるが、"
        "\n       脚質内の判別は良くならない（pai-v2 と同じ誤りを別経路で再現する）。"
        "\n    ※ 推奨offset は平均ずれを0にする `pace_center_offset_*`（現行中心からの差分）。"
        "\n       予測平均を中心へ置くだけでは足りない。deviation は±1で頭打ちになるため、"
        "\n       分布が非対称だと平均が一致していても平均ずれは0にならない。"
        "\n    ※ 同一期間から取った当てはめ値なので、採用するなら期間外で確認すること。"
    )
    return "\n".join(lines)


def format_pai_by_style(samples: list[HorseSample]) -> str:
    """脚質の定数効果と、脚質内での PAI の効きを分けて示す。"""
    if not samples:
        return ""
    lines = ["", "=" * 78, "■ PAI診断（脚質の定数効果 / 脚質内での PAI の効き）", "=" * 78]
    for track in ("芝", "ダート"):
        group = [s for s in samples if s.track_type == track]
        rows = summarize_pai_by_style(group)
        if not rows:
            continue
        base = sum(1 for s in group if s.good_run) / len(group)
        lines.append(f"\n  ── {track}（ベースライン好走率 {base:.1%}）")
        lines.append(f"    {'脚質':<8}{'頭数':>8}{'PAI平均':>10}{'好走率':>10}{'対ベース':>10}")
        for r in rows:
            lines.append(
                f"    {r.style:<8}{r.n:>8,}{r.mean_pai:>10.1f}"
                f"{r.good_rate:>10.1%}{r.good_rate / base if base else 0:>9.2f}x"
            )
        lines.append("    ※ PAI平均の大小は脚質間で比較できない（pai-v3 は脚質内の相対量）。")

        within = summarize_pai_within_style(group)
        if not within:
            continue
        lines.append(f"\n    脚質内でのPAIの効き（上位1/3 対 下位1/3・{track}）")
        lines.append(
            f"    {'脚質':<8}{'1/3頭数':>9}{'下位PAI':>9}{'下位好走':>9}"
            f"{'上位PAI':>9}{'上位好走':>9}{'差':>9}{'±2誤差':>9}{'判定':>7}"
        )
        for w in within:
            verdict = "有意" if w.is_significant else "誤差内"
            lines.append(
                f"    {w.style:<8}{w.group_n:>9,}{w.low_mean_pai:>9.1f}"
                f"{w.low_rate:>9.1%}{w.high_mean_pai:>9.1f}{w.high_rate:>9.1%}"
                f"{w.spread:>+9.1%}{2 * w.spread_se:>9.1%}{verdict:>7}"
            )
    lines.append(format_fit_label_shares(summarize_fit_label_shares(samples)))
    lines.append(format_fit_crowding(summarize_fit_crowding(samples)))
    lines.append(format_fit_threshold_by_style(summarize_fit_threshold_by_style(samples)))
    lines.append(format_crowding_sweep(summarize_crowding_sweep(samples)))
    lines.append(format_pace_centering(summarize_pace_centering(samples)))
    lines.append(
        "\n  ※ 「差」が正なら、脚質を固定しても PAI が好走を判別できている。"
        "\n  ※ 「誤差内」の行は偶然と区別できない。頭数ではなく差と標準誤差で判定している。"
        "\n  ※ 下位PAIと上位PAIが近い脚質は、そもそも判別する幅が無い（感応度0など）。"
        "\n  ※ 感応度が高い脚質ほど差が小さいなら、ペース補正が効いていないことを意味する。"
        "\n     PAI の残り半分は pace_affinity（その馬自身の過去のペース別実績）由来。"
        "\n  ※ 脚質をまたいだ順位付けに PAI を使わないこと（docs/DECISIONS.md ADR-2026-08-04）。"
    )
    return "\n".join(lines)


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
        bands=_summarize_style_advantage_bands(samples),
        style_groups=_summarize_style_advantage_groups(samples),
    )


def collect_actual_style_advantage_samples(
    targets: Iterable[Race],
    repo: RaceRepository,
    weights: StyleAdvantageWeights | None = None,
) -> list[StyleAdvantageSample]:
    """実績ペース・確定脚質で、脚質有利度ルール単体の理論上限を検証する。

    `weights`を渡すと候補係数で採点し直す。同じ対象レースで現行と候補を
    比べるために使う（本番の重みは書き換えない）。
    """
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
            weights=weights,
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
                    running_style=style,
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
            and (accuracy.n_races, accuracy.n_horses) != (baseline.n_races, baseline.n_horses)
        ):
            raise ValueError(f"比較サンプル数が現行重みと一致しません: {profile.name}")
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
    baseline_keys = [(sample.race_key, sample.horse_no) for sample in baseline_report.horse_samples]

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


def _filter_horse_samples(samples: list[HorseSample], track_type: str) -> list[HorseSample]:
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
        "integrated_samples": [_integrated_sample_to_dict(s) for s in report.integrated_samples],
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
                "sensitivity_escape": item.profile.weights.sensitivity_escape,
                "sensitivity_front": item.profile.weights.sensitivity_front,
                "sensitivity_flexible": item.profile.weights.sensitivity_flexible,
                "sensitivity_stalker": item.profile.weights.sensitivity_stalker,
                "sensitivity_closer": item.profile.weights.sensitivity_closer,
                "pace_swing": item.profile.weights.pace_swing,
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
        "bands": [_style_advantage_band_to_dict(band) for band in lift.bands],
        "style_groups": [
            {
                "label": group.label,
                "n": group.n,
                "baseline_rate": group.baseline_rate,
                "bands": [_style_advantage_band_to_dict(band) for band in group.bands],
            }
            for group in lift.style_groups
        ],
    }


def pace_style_matrix_to_dict(matrix: PaceStyleMatrix | None) -> dict[str, Any] | None:
    if matrix is None:
        return None
    return {
        "n_races": matrix.n_races,
        "n_horses": matrix.n_horses,
        "baseline_rate": matrix.baseline_rate,
        "rows": [
            {
                "style": row.style,
                "n": row.n,
                "good_runs": row.good_runs,
                "good_rate": round(row.good_rate, 4),
                "cells": [
                    {
                        "pace_label": cell.pace_label,
                        "n": cell.n,
                        "good_runs": cell.good_runs,
                        "good_rate": round(cell.good_rate, 4),
                    }
                    for cell in row.cells
                ],
            }
            for row in matrix.rows
        ],
    }


def _style_advantage_band_to_dict(band: StyleAdvantageBand) -> dict[str, Any]:
    return {
        "label": band.label,
        "lo": band.lo,
        "hi": band.hi,
        "n": band.n,
        "good_runs": band.good_runs,
        "good_rate": round(band.good_rate, 4),
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


def format_report(
    report: BacktestReport,
    clamp: tuple[float, float] | None = None,
) -> str:
    """バックテスト結果を人間可読のテキストへ整形する（CLI 出力用）。

    clamp は実際に予測へ適用された安全弁。application 層からは予測器の実装値を
    参照できないため、省略時はクランプ内訳を出さない（誤った境界で判定するより、
    黙っているほうが安全）。CLI は常に実際の値を渡す。
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"バックテスト結果  model_version={report.model_version or '(不明)'}")
    lines.append(
        f"対象レース {report.n_races} / 出走 {report.n_horses} 頭 （スキップ {report.skipped}）"
    )
    lines.append("=" * 60)

    if report.rpci is not None:
        r = report.rpci
        lines.append("\n■ 想定RPCI の誤差")
        lines.append(f"  MAE  : {r.mae:.3f}   RMSE: {r.rmse:.3f}   バイアス: {r.bias:+.3f}")
        lines.append(f"  展開ラベル的中率: {r.label_accuracy:.1%}")
        for label, acc in r.per_label_accuracy.items():
            lines.append(f"    - 実績「{label}」の再現率: {acc:.1%}")
        # 端に張り付きが無ければ空文字が返るので、通常時は出力を汚さない。
        if clamp is not None:
            clamp_text = format_clamp_impact(
                summarize_clamp_impact(report.rpci_samples, clamp=clamp)
            )
            if clamp_text:
                lines.append(clamp_text)
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
        # 人気データが無ければ空文字が返るので、通常時は出力を汚さない。
        market_text = format_ranking_comparison(
            compare_with_market(report.integrated_samples, report.market_samples, report.n_races)
        )
        if market_text:
            lines.append(market_text)
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
            f"(感応度={weights.sensitivity_escape:.2f}/"
            f"{weights.sensitivity_front:.2f}/{weights.sensitivity_flexible:.2f}/"
            f"{weights.sensitivity_stalker:.2f}/{weights.sensitivity_closer:.2f}, "
            f"振れ幅={weights.pace_swing:.1f})"
        )
        for label, metrics in (
            ("全体", item.combined),
            ("芝", item.turf),
            ("ダート", item.dirt),
        ):
            if metrics.lift is None:
                summary = "有効サンプルなし"
            else:
                # 上位帯の頭数を必ず併記する。振れ幅を狭めると上位帯へ届く馬が減り、
                # 少数の当たりでリフトだけが跳ね上がるため、n 無しでは比較できない。
                top_n = metrics.lift.bands[-1].n if metrics.lift.bands else 0
                summary = (
                    f"n={metrics.lift.n:5d} "
                    f"相関={metrics.lift.point_biserial:+.3f}"
                    f"({_format_number_delta(metrics.delta_point_biserial)}) "
                    f"上位帯={metrics.lift.top_band_lift:5.2f}x"
                    f"({_format_number_delta(metrics.delta_top_band_lift)}) "
                    f"上位帯n={top_n:5d}"
                )
            lines.append(f"  {label:<4} {summary}")
    lines.append(
        "※ 上位帯nが小さい候補のリフトは信用しないこと。相関は全頭を使うため頭数の影響を受けない。"
    )
    lines.append("=" * 96)
    return "\n".join(lines)


def _pad_display(text: str, width: int) -> str:
    """全角を2桁として数え、等幅端末で列が揃うよう右側を空白で埋める。

    `str.ljust`は文字数で数えるため、日本語ラベルの列が崩れる。
    """
    display = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
    return text + " " * max(0, width - display)


def format_actual_style_advantage_validation(
    lift: StyleAdvantageLift | None,
) -> str:
    """実績ペース・確定脚質を使う診断結果をCLI向けに整形する。"""
    if lift is None:
        return "脚質別展開有利度: 有効サンプルなし"
    lines = [
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
    ]
    if lift.bands:
        lines.append("")
        header = _pad_display("表示ラベル", 12) + _pad_display("スコア帯", 12)
        lines.append(f"  {header}    頭数     好走   好走率   対ベース")
        for band in lift.bands:
            lift_ratio = band.good_rate / lift.baseline_rate if lift.baseline_rate else 0.0
            span = f"{band.lo:.0f}〜{band.hi:.0f}"
            lines.append(
                f"  {_pad_display(band.label, 12)}{_pad_display(span, 12)}"
                f"{band.n:8,d} {band.good_runs:8,d} {band.good_rate:7.1%} {lift_ratio:8.2f}x"
            )
        lines.append("※ 単調に増えていれば全域で機能、両端だけ離れていれば極端な場面のみ有効")
    lines.extend(_format_style_group_bands(lift))
    lines.append("=" * 72)
    return "\n".join(lines)


def _format_style_group_bands(lift: StyleAdvantageLift) -> list[str]:
    """前付け・差し追込に分けた帯別好走率を整形する。"""
    lines: list[str] = []
    for group in lift.style_groups:
        if group.n == 0:
            continue
        lines.append("")
        lines.append(f"■ {group.label}のみ（{group.n:,}頭 / 好走率 {group.baseline_rate:.1%}）")
        header = _pad_display("表示ラベル", 12) + _pad_display("スコア帯", 12)
        lines.append(f"  {header}    頭数     好走   好走率   対ベース")
        for band in group.bands:
            if band.n == 0:
                continue
            ratio = band.good_rate / group.baseline_rate if group.baseline_rate else 0.0
            span = f"{band.lo:.0f}〜{band.hi:.0f}"
            lines.append(
                f"  {_pad_display(band.label, 12)}{_pad_display(span, 12)}"
                f"{band.n:8,d} {band.good_runs:8,d} {band.good_rate:7.1%} {ratio:8.2f}x"
            )
    if lines:
        lines.append("※ 片方だけ非単調なら、そのグループの加点則が実態と合っていない")
    return lines


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


ProgressCallback = Callable[[int], None]
"""処理済みレース数を受け取る通知口。集計そのものには影響しない。"""


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
        ranking_strategy: RankingStrategy = RankingStrategy.CURRENT,
    ) -> None:
        self._repo = repo
        self._forecaster = forecaster
        self._commenter = comment_generator
        self._ability_scorer = ability_scorer
        self._pai_scorer = pai_scorer
        self._band_edges = band_edges
        self._ranking_strategy = ranking_strategy

    def run(
        self,
        targets: Iterable[Race],
        progress: ProgressCallback | None = None,
    ) -> BacktestReport:
        """確定レース群を再予測して集計する。

        `progress` は「何レース処理したか」を呼び出し側へ渡すだけの通知口。
        **表示はここでは行わない**（application 層に I/O を持ち込まない）。

        レース1件あたり、出走馬ごとの履歴取得で十数回の往復が要る。DB がリモート
        （Supabase 東京）だとこれが支配的になり、500レースで数分から十数分かかる。
        その間まったく無音だと、**進んでいるのか止まっているのか区別できない**。
        """
        rpci_samples: list[RpciSample] = []
        horse_samples: list[HorseSample] = []
        integrated_samples: list[IntegratedSample] = []
        market_samples: list[IntegratedSample] = []
        style_advantage_samples: list[StyleAdvantageSample] = []
        n_races = 0
        skipped = 0
        processed = 0
        model_versions: set[str] = set()

        for race in targets:
            if progress is not None:
                processed += 1
                progress(processed)
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
                        running_style=horse.running_style,
                        forecast_rpci=out.predicted_rpci,
                        fit_label=horse.fit_label,
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
                            running_style=_scoreable_style(horse.running_style),
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
            # 市場ベースライン: 単勝人気をそのまま順位として同じ指標で測る。
            for actual in actual_entries:
                if actual.popularity is None:
                    continue
                market_samples.append(
                    IntegratedSample(
                        race_key=key,
                        horse_no=actual.horse_no,
                        rank=actual.popularity,
                        finish_pos=actual.finish_pos,
                        good_run=is_good_run(actual.finish_pos, race.grade),
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
            market_samples=market_samples,
            style_advantage_samples=style_advantage_samples,
        )

    def diagnose_style_advantage(self, targets: Iterable[Race]) -> StyleAdvantageAttribution:
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
                # 各パターンで使った脚質をそのまま持たせる（予測脚質を使うパターンは
                # 予測脚質、確定脚質を使うパターンは確定脚質）。
                values = (
                    (forecast_samples, forecast_scores[predicted_style], predicted_style),
                    (actual_pace_samples, actual_pace_scores[predicted_style], predicted_style),
                    (actual_style_samples, actual_style_scores[actual_style], actual_style),
                    (oracle_samples, oracle_scores[actual_style], actual_style),
                )
                for samples, score, sample_style in values:
                    samples.append(
                        StyleAdvantageSample(
                            race_key=race_key,
                            horse_no=horse_no,
                            score=score,
                            good_run=good_run,
                            running_style=sample_style,
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
            ranking_strategy=self._ranking_strategy,
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
