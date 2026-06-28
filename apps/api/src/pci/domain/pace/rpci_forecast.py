"""想定RPCI 予測モジュール（本プロダクトの中核機能・ADR-0005）。

戦略インターフェース `RpciForecaster` を定義し、MVP ではルールベース実装
`RuleBasedRpciForecaster`（model_version = "rule-v4"）を提供する。
将来の LightGBM 実装は同一インターフェースを満たすことで差し替え可能。

想定RPCI の方向性（pci.py と統一）:
    RPCI > slow_threshold : スロー（前半が緩む → 差し・追込有利）
    RPCI < high_threshold : ハイ（前傾ラップ → 逃げ・先行有利）
    その間               : 平均

ルール要因（rule-v4・すべて reasons に出力）:
    1. 距離基準ペース      : 長距離ほど緩む傾向（RPCI高）
    2. 脚質構成バランス    : 差し追込比率が高い→スロー / 逃げ先行比率が高い→ハイ
    3. 逃げ馬頭数の競合    : 逃げ不在→スロー / 逃げ複数→先行争いでハイ
    4. 馬場状態補正        : 道悪での補正（調整可能なプレースホルダ）
    5. 前付け馬の実績ペース傾向（rule-v2 で追加・本質的改善）:
       逃げ・先行候補が近走で「前で運んだとき」に実際どんなペース（個馬PCI平均）
       を作ったかを集計し、頭数ベースの 1〜3 を実データで補正する。
       これにより「単騎で緩める逃げ馬」と「ハナを切ると毎回飛ばす逃げ馬」を区別する。
       履歴が無ければ自動的に 1〜4 のみ（rule-v1 相当）へフォールバックする。
    rule-v3: コース種別基準 RPCI 補正（芝+5.0 / ダート-9.75）を追加。
    rule-v4: ダートの展開3分類閾値を実績分布に合わせて個別設定（ハイ<40/スロー>46）。

    【芝「平均ペース」再現率 0% について】
    lgbm-turf-v1 バックテストで芝「平均（49–51）」再現率が 0.0% と観測される。
    閾値を 48–52 に緩和しても改善しなかった（むしろ全体的中率 76% → 67% に悪化）。
    これは芝の実績 RPCI がほとんどスロー (>51) かハイ (<49) に分布しているか、
    lgbm が RPCI の中間帯 (49–51) を予測しない構造的問題によるもの。
    PAI 相関 +0.108・最上位帯リフト 1.33x は良好なため、主目的は達成済みと判断。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "rule-v4"


class PaceLabel(StrEnum):
    """展開3分類（ADR-0005）。"""

    HIGH = "ハイ"
    AVERAGE = "平均"
    SLOW = "スロー"


@dataclass(frozen=True)
class FrontRunnerPaceSample:
    """逃げ・先行候補の「前で運んだときのペース」傾向（rule-v2）。

    application 層が各馬の近走から、実際に前付けした過去走の個馬PCI（欠損時は
    実績RPCIで補完）を平均して構築する。sample_size はその集計に使った走数。
    """

    horse_no: int
    style: RunningStyleLabel
    avg_pci: float
    sample_size: int


@dataclass(frozen=True)
class RaceContext:
    """想定RPCI 予測の入力コンテキスト。"""

    distance_m: int
    track_type: str
    running_styles: tuple[RunningStyleLabel, ...]
    track_condition: str | None = None
    venue_code: str | None = None  # 競馬場コード (jyo_cd "01"〜"10")。LightGBM 特徴量。
    # rule-v2: 逃げ・先行候補の実績ペース傾向。空なら頭数ベース（rule-v1相当）。
    front_pace_samples: tuple[FrontRunnerPaceSample, ...] = ()


@dataclass(frozen=True)
class RpciForecast:
    """想定RPCI 予測結果。"""

    value: float
    label: PaceLabel
    confidence: float
    model_version: str
    reasons: tuple[Reason, ...]


class RpciForecaster(Protocol):
    """想定RPCI 予測の戦略インターフェース（ADR-0005）。

    application / presentation 層はこの Protocol にのみ依存し、
    具体実装（ルールベース / ML）は DI で注入する。
    """

    def forecast(self, context: RaceContext) -> RpciForecast: ...


@dataclass(frozen=True)
class RuleWeights:
    """ルールベース予測の重み（設定ファイルから上書き可能）。"""

    base_rpci: float = 50.0
    distance_pivot_m: int = 1800
    distance_slope_per_200m: float = 0.25
    style_balance_weight: float = 8.0
    escape_pressure_weight: float = 0.8
    # コース種別基準ペース補正（rule-v3〜: 実績 rpci_actual 平均から較正）
    # 芝: 実績平均 53.1 / ダート: 実績平均 43.0（DB 2022〜2026 約 15,440 レース集計）
    turf_base_adjust: float = 5.0
    dirt_base_adjust: float = -9.75
    # 馬場補正（道悪は前傾化しやすい傾向の暫定値。検証で調整）
    track_good_adjust: float = 0.0
    track_slightly_heavy_adjust: float = -0.3
    track_heavy_adjust: float = -0.5
    track_bad_adjust: float = -0.8
    # 展開3分類の閾値（芝）
    high_threshold: float = 49.0
    slow_threshold: float = 51.0
    # 展開3分類の閾値（ダート・rule-v4）
    # 芝平均 53.1 と異なりダート平均 43.0 → ハイ中心のため専用閾値で3分類を均等化
    dirt_high_threshold: float = 40.0
    dirt_slow_threshold: float = 46.0
    # RPCI の現実的なクランプ範囲（安全弁）
    rpci_min: float = 35.0
    rpci_max: float = 65.0
    # rule-v2: 前付け馬の実績ペース傾向（個馬PCI平均）の混合度。
    # サンプル数（前付け走数の合計）に比例して実績側を信頼し、上限で頭打ち。
    # 上限を 1 未満に保つことで、距離・脚質ベースの prior を常に残す。
    evidence_weight_per_sample: float = 0.1
    evidence_weight_cap: float = 0.7


DEFAULT_WEIGHTS = RuleWeights()

_FRONT_STYLES = (RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT)
_CLOSER_STYLES = (RunningStyleLabel.STALKER, RunningStyleLabel.CLOSER)


def classify_pace(
    rpci: float,
    track_type: str = "芝",
    weights: RuleWeights = DEFAULT_WEIGHTS,
) -> PaceLabel:
    """RPCI 値を展開3分類へ写す（予測・実績で共通利用する唯一の判定）。

    実績RPCI を同じ閾値でラベル化することで、バックテストが予測ラベルと
    実績ラベルを公平に比較できる（rpci_forecast がラベル判定の真実の場所）。

    rule-v4: ダートは実績分布（平均 43.0）が芝（53.1）と大きく異なるため、
    コース種別別の閾値を使用する。
    """
    if track_type == "ダート":
        hi, sl = weights.dirt_high_threshold, weights.dirt_slow_threshold
    else:
        hi, sl = weights.high_threshold, weights.slow_threshold
    if rpci < hi:
        return PaceLabel.HIGH
    if rpci > sl:
        return PaceLabel.SLOW
    return PaceLabel.AVERAGE


class RuleBasedRpciForecaster:
    """ルールベース想定RPCI 予測器（rule-v2）。

    説明可能性を最優先し、各要因の寄与を reasons として出力する（ADR-0005）。
    """

    def __init__(self, weights: RuleWeights | None = None) -> None:
        self._w = weights or DEFAULT_WEIGHTS

    def forecast(self, context: RaceContext) -> RpciForecast:
        styles = context.running_styles
        n = len(styles)
        if n == 0:
            raise ValueError("出走馬の脚質情報がありません。想定RPCI を予測できません。")

        w = self._w
        reasons: list[Reason] = []

        # 1. 距離基準ペース
        dist_adj = (
            (context.distance_m - w.distance_pivot_m) / 200.0 * w.distance_slope_per_200m
        )
        base = w.base_rpci + dist_adj
        reasons.append(
            Reason(
                code="distance_base",
                description=f"距離{context.distance_m}m の基準ペース → RPCI基準 {base:.2f}",
                contribution=round(dist_adj, 2),
            )
        )

        # 1b. コース種別基準補正（rule-v3: 芝/ダートで実績 RPCI 平均が大きく異なる）
        track_type_adj = (
            w.turf_base_adjust if context.track_type == "芝"
            else w.dirt_base_adjust if context.track_type == "ダート"
            else 0.0
        )
        if track_type_adj != 0.0:
            reasons.append(
                Reason(
                    code="track_type_base",
                    description=(
                        f"コース「{context.track_type}」基準補正 {track_type_adj:+.2f}"
                    ),
                    contribution=round(track_type_adj, 2),
                )
            )
        base += track_type_adj

        # 2. 脚質構成バランス
        front = sum(1 for s in styles if s in _FRONT_STYLES)
        closer = sum(1 for s in styles if s in _CLOSER_STYLES)
        balance = (closer / n - front / n) * w.style_balance_weight
        reasons.append(
            Reason(
                code="style_balance",
                description=(
                    f"逃先{front}頭 / 差追{closer}頭（全{n}頭）→ "
                    f"{'スロー' if balance > 0 else 'ハイ'}方向 {balance:+.2f}"
                ),
                contribution=round(balance, 2),
            )
        )

        # 3. 逃げ馬頭数の競合（逃げ不在=緩む / 複数=先行争い）
        escape = sum(1 for s in styles if s == RunningStyleLabel.ESCAPE)
        escape_pressure = -(escape - 1) * w.escape_pressure_weight
        reasons.append(
            Reason(
                code="escape_pressure",
                description=(
                    f"逃げ馬{escape}頭 → "
                    f"{'先行争いでハイ' if escape_pressure < 0 else '緩みやすくスロー'}"
                    f"方向 {escape_pressure:+.2f}"
                ),
                contribution=round(escape_pressure, 2),
            )
        )

        # 4. 馬場補正
        track_adjust = self._track_adjust(context.track_condition)
        if track_adjust != 0.0:
            reasons.append(
                Reason(
                    code="track_condition",
                    description=f"馬場「{context.track_condition}」補正 {track_adjust:+.2f}",
                    contribution=track_adjust,
                )
            )

        structural = base + balance + escape_pressure
        evidence_pace, evidence_samples = _aggregate_front_pace(context.front_pace_samples)
        if evidence_samples > 0:
            # 前付け馬が近走で実際に作ったペース（個馬PCI平均）を競合補正込みで反映。
            # 逃げ複数なら escape_pressure が負＝先行争いで速い方向、を実績平均にも効かせる。
            evidence_raw = evidence_pace + escape_pressure
            ew = min(evidence_samples * w.evidence_weight_per_sample, w.evidence_weight_cap)
            blended = ew * evidence_raw + (1.0 - ew) * structural
            reasons.append(
                Reason(
                    code="front_pace_evidence",
                    description=(
                        f"逃げ・先行{len(context.front_pace_samples)}頭の近走ペース傾向"
                        f"（平均PCI {evidence_pace:.1f}・実績{evidence_samples}走）を"
                        f"{ew:.0%}反映 → {blended:.2f}"
                    ),
                    contribution=round(blended - structural, 2),
                )
            )
        else:
            blended = structural

        raw = blended + track_adjust
        rpci = round(min(max(raw, w.rpci_min), w.rpci_max), 1)

        label = self._classify(rpci, context.track_type)
        confidence = self._confidence(balance, escape_pressure, evidence_samples)
        reasons.append(
            Reason(
                code="forecast",
                description=f"想定RPCI={rpci} → 展開「{label}」（信頼度 {confidence:.0%}）",
            )
        )

        return RpciForecast(
            value=rpci,
            label=label,
            confidence=confidence,
            model_version=MODEL_VERSION,
            reasons=tuple(reasons),
        )

    def _track_adjust(self, condition: str | None) -> float:
        w = self._w
        return {
            "良": w.track_good_adjust,
            "稍重": w.track_slightly_heavy_adjust,
            "重": w.track_heavy_adjust,
            "不良": w.track_bad_adjust,
        }.get(condition or "良", 0.0)

    def _classify(self, rpci: float, track_type: str = "芝") -> PaceLabel:
        return classify_pace(rpci, track_type, self._w)

    def _confidence(
        self, balance: float, escape_pressure: float, evidence_samples: int = 0
    ) -> float:
        # 実績ペース傾向のサンプルが多いほど予測の確からしさを上げる（上限 6 走で頭打ち）。
        signal = abs(balance) + abs(escape_pressure) + min(evidence_samples, 6) * 0.5
        return round(min(max(0.4 + signal / 20.0, 0.3), 0.9), 2)


def _aggregate_front_pace(
    samples: tuple[FrontRunnerPaceSample, ...],
) -> tuple[float, int]:
    """前付け候補の実績ペース傾向を「馬単位の平均」と「総サンプル数」へ集約する。

    ユーザ意図どおり各馬の傾向を等加重で平均する（頭数で割る）。総サンプル数は
    実績への信頼度（混合比 evidence_weight）の決定に使う。
    """
    valid = [s for s in samples if s.sample_size > 0]
    if not valid:
        return 0.0, 0
    avg_pace = sum(s.avg_pci for s in valid) / len(valid)
    total_samples = sum(s.sample_size for s in valid)
    return avg_pace, total_samples
