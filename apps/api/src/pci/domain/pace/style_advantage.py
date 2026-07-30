"""脚質別の展開有利度（style-advantage-v3）。

想定RPCIが中立点からどちらへ寄っているかを、脚質（逃/先/差/追）ごとの
有利・不利スコアへ翻訳する。UIの「展開分析」カードの算出元。

方向性（pci.py / rpci_forecast.py と統一）:
    スロー寄り（RPCI > 中立） → 前半が緩む → 逃げ・先行が有利、差し・追込が不利
    ハイ寄り  （RPCI < 中立） → 前傾ラップ → 差し・追込が有利、逃げ・先行が不利

スコアは 50 を「互角」とする 0〜100 の対称尺度。中立点はコース種別ごとの
展開3分類閾値（rule-v4、`classify_pace` と同じ RuleWeights）の中点から導出し、
判定基準の二重定義を作らない。逃げ候補が複数いる場合は先行争いの消耗を見込んで
逃げのみ減点する。

以前の実装（web 側でその脚質の最大PAIを流用）は「脚質内の最良馬の適性」であり
「脚質自体の有利さ」ではなかったため、スコアが高止まりして差が出なかった。
本モジュールはその置き換え（ドメインでの正式算出・reasons 付き）。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.rpci_forecast import DEFAULT_WEIGHTS, RuleWeights
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "style-advantage-v3"


class StyleAdvantageReliability(StrEnum):
    """脚質別有利度を予想判断へ使う際の信頼度。"""

    STANDARD = "standard"
    REFERENCE = "reference"


@dataclass(frozen=True)
class StyleAdvantageWeights:
    """style-advantage-v3 の仮係数。実データ検証後の調整を前提とする。"""

    # RPCIが中立から1ポイント離れるごとのスコア変化量
    slope_per_point: float = 4.0
    # 逃げ・追込は先行・差しより展開の影響を強く受ける（増幅率）
    escape_gain: float = 1.2
    closer_gain: float = 1.2
    # 逃げ候補が2頭以上のとき、1頭増えるごとに逃げスコアを減点
    escape_crowd_penalty: float = 6.0
    score_min: float = 5.0
    score_max: float = 95.0
    # 先行・差しの増幅率。既定1.0は従来の暗黙値と同じで、挙動は変わらない。
    # 実測ではペース感応度が脚質間で最大6倍以上違うため、候補比較で
    # 脚質ごとに独立して動かせるようにしている（ADR-0010）。
    front_gain: float = 1.0
    stalker_gain: float = 1.0
    # 自在の増幅率。None は「採点しない」＝現行の挙動（entries は4件）。
    # 実測では自在が先行と同等に反応するが、採点対象へ加えると公開スキーマが
    # 変わるため、既定では従来どおり採点しない（ADR-0010 が Proposed のため）。
    flexible_gain: float | None = None

    def __post_init__(self) -> None:
        if self.slope_per_point <= 0:
            raise ValueError("スコア勾配は正の値である必要があります")
        # 増幅率の下限は0。実測（ADR-0010）で差し・追込の感応度は前付けの1/4以下と
        # 判明しており、「逃げ・追込は必ず1.0以上」という当初の前提は成立しない。
        gains = (self.escape_gain, self.closer_gain, self.front_gain, self.stalker_gain)
        if any(gain < 0 for gain in gains):
            raise ValueError("脚質ごとの増幅率は0以上である必要があります")
        if self.flexible_gain is not None and self.flexible_gain < 0:
            raise ValueError("自在の増幅率は0以上である必要があります")
        if self.escape_crowd_penalty < 0:
            raise ValueError("逃げ競合の減点は0以上である必要があります")
        if not 0 <= self.score_min < self.score_max <= 100:
            raise ValueError("スコア範囲は 0 <= min < max <= 100 である必要があります")


DEFAULT_STYLE_ADVANTAGE_WEIGHTS = StyleAdvantageWeights()


@dataclass(frozen=True)
class StyleAdvantageEntry:
    """1脚質分の有利度（50=互角、大きいほど今回の流れが向く）。"""

    style: RunningStyleLabel
    score: float


@dataclass(frozen=True)
class StyleAdvantage:
    """脚質別有利度の算出結果。"""

    model_version: str
    reliability: StyleAdvantageReliability
    reliability_reason: str | None
    entries: tuple[StyleAdvantageEntry, ...]
    reasons: tuple[Reason, ...]


def neutral_rpci(track_type: str, rule_weights: RuleWeights = DEFAULT_WEIGHTS) -> float:
    """コース種別の「互角」となる RPCI（展開3分類閾値の中点）。"""
    if track_type == "ダート":
        return (rule_weights.dirt_high_threshold + rule_weights.dirt_slow_threshold) / 2
    return (rule_weights.high_threshold + rule_weights.slow_threshold) / 2


def build_style_advantage(
    predicted_rpci: float,
    track_type: str,
    running_styles: tuple[RunningStyleLabel, ...],
    *,
    venue_code: str | None = None,
    race_date: datetime.date | None = None,
    distance_m: int | None = None,
    weights: StyleAdvantageWeights | None = None,
    rule_weights: RuleWeights = DEFAULT_WEIGHTS,
) -> StyleAdvantage:
    """想定RPCIと出走馬の脚質構成から、脚質別有利度を算出する。

    Args:
        predicted_rpci:  想定RPCI（rule-v4 / lgbm-* の出力値）
        track_type:      コース種別（芝/ダート/障害。障害は芝と同じ中立点）
        running_styles:  出走各馬の判定済み脚質（逃げ競合の検出に使用）
        venue_code:      競馬場コード（開催条件別の信頼度判定に使用）
        race_date:       開催日（季節別の信頼度判定に使用）
        distance_m:      実施距離（距離別の信頼度判定に使用）
        weights:         仮係数。省略時は DEFAULT_STYLE_ADVANTAGE_WEIGHTS
        rule_weights:    展開3分類の閾値（classify_pace と共有し中立点を導出）

    Returns:
        StyleAdvantage（4脚質のスコア・reasons・model_version）
    """
    config = weights or DEFAULT_STYLE_ADVANTAGE_WEIGHTS
    neutral = neutral_rpci(track_type, rule_weights)
    delta = predicted_rpci - neutral
    escape_count = sum(1 for s in running_styles if s == RunningStyleLabel.ESCAPE)

    def _score(multiplier: float) -> float:
        raw = 50.0 + config.slope_per_point * delta * multiplier
        return max(config.score_min, min(config.score_max, raw))

    escape_score = _score(config.escape_gain)
    crowd_penalty = 0.0
    if escape_count >= 2:
        crowd_penalty = config.escape_crowd_penalty * (escape_count - 1)
        escape_score = max(config.score_min, escape_score - crowd_penalty)

    closer_score = _score(-config.closer_gain)
    scored = [
        StyleAdvantageEntry(style=RunningStyleLabel.ESCAPE, score=round(escape_score, 1)),
        StyleAdvantageEntry(
            style=RunningStyleLabel.FRONT, score=round(_score(config.front_gain), 1)
        ),
        StyleAdvantageEntry(
            style=RunningStyleLabel.STALKER, score=round(_score(-config.stalker_gain), 1)
        ),
        StyleAdvantageEntry(style=RunningStyleLabel.CLOSER, score=round(closer_score, 1)),
    ]
    # 自在はスロー寄りで前付けと同方向に反応する（ADR-0010の実測）。
    # 採点するかは重み側で決め、既定（None）では従来どおり entries に含めない。
    if config.flexible_gain is not None:
        scored.append(
            StyleAdvantageEntry(
                style=RunningStyleLabel.FLEXIBLE,
                score=round(_score(config.flexible_gain), 1),
            )
        )
    entries = tuple(scored)

    if delta > 0:
        direction = "前半が緩む想定のため前に行く脚質が有利"
    elif delta < 0:
        direction = "前傾ラップの想定のため後ろから運ぶ脚質が有利"
    else:
        direction = "想定ペースが中立のため脚質間の有利不利は小さい"
    reasons = [
        Reason(
            code="pace_direction",
            description=(
                f"想定RPCI {predicted_rpci:.1f}（{track_type}の中立 {neutral:.1f} から"
                f" {delta:+.1f}）: {direction}"
            ),
            contribution=delta,
        )
    ]
    if crowd_penalty > 0:
        reasons.append(
            Reason(
                code="escape_crowd",
                description=f"逃げ候補が{escape_count}頭おり、先行争いの消耗を見込んで逃げを減点",
                contribution=-crowd_penalty,
            )
        )

    reliability = StyleAdvantageReliability.STANDARD
    reliability_reason: str | None = None
    if (
        track_type == "芝"
        and venue_code == "10"
        and race_date is not None
        and race_date.month == 7
        and distance_m == 1200
    ):
        reliability = StyleAdvantageReliability.REFERENCE
        reliability_reason = (
            "7月の小倉芝1200mでは過去複数年で脚質別有利度の方向が実績と逆転し、"
            "馬場状態別でも同じ傾向のため参考扱い"
        )
        reasons.append(
            Reason(
                code="seasonal_venue_caution",
                description=reliability_reason,
            )
        )

    return StyleAdvantage(
        model_version=MODEL_VERSION,
        reliability=reliability,
        reliability_reason=reliability_reason,
        entries=entries,
        reasons=tuple(reasons),
    )
