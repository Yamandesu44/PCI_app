"""統合順位予想 (integrated-v1) — 展開適性(PAI)と能力(ability-v1)の2軸分類。

能力の高低（レース内相対）と、想定される流れへの展開適性（PAI/合致ラベル）を
掛け合わせ、各馬を ◎本命 / ○対抗 / ▲穴 / △危険 / 無印 に分類する。

    ◎本命 : 能力上位 × 展開も向く（合致）
    ○対抗 : 能力上位 × 展開は普通（中立）
    △危険 : 能力上位 × 展開が向かない（不利）  ← 「強いが取りこぼしに注意」
    ▲穴   : 能力中位 × 展開が特に向く（合致）  ← 「流れ次第で浮上」
    無印   : 上記以外

恣意的な重み付け合算（能力とPAIを1本のスコアに混ぜる）は採らず、
「能力の相対順位」を主・「展開の向き不向き」を従とした説明可能な分類にする
（`docs/DECISIONS.md`）。表示順も同じ2軸から決定的に導く（マジックナンバーの合算なし）。

能力 tier は絶対値ではなくレース内の相対順位で決める（ability の score の絶対値は
現データ制約上ノイズが大きいため。`docs/SPEC.md §9`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.ability import AbilityScore
from pci.domain.pace.adaptability import FitLabel, PaiResult
from pci.domain.shared.reason import Reason

MODEL_VERSION = "integrated-v1"


class AbilityTier(StrEnum):
    """レース内相対の能力階層。"""

    TOP = "上位"
    MIDDLE = "中位"
    LOWER = "下位"
    UNKNOWN = "評価難"  # 近走データ不足


class Mark(StrEnum):
    """統合分類記号。"""

    HONMEI = "本命"
    TAIKO = "対抗"
    ANA = "穴"
    KIKEN = "危険"
    NONE = "無印"


@dataclass(frozen=True)
class IntegratedEntry:
    """統合順位予想の1頭分。"""

    horse_no: int
    rank: int  # 表示順（1始まり）
    mark: Mark
    ability_tier: AbilityTier
    fit_label: FitLabel
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class IntegratedRanking:
    """統合順位予想の結果。"""

    model_version: str
    entries: tuple[IntegratedEntry, ...]  # rank 昇順
    reasons: tuple[Reason, ...]


# 表示順の従属キー: 展開の向き（合致→中立→不利）。
_FIT_ORDER = {FitLabel.MATCHED: 0, FitLabel.NEUTRAL: 1, FitLabel.UNFAVORABLE: 2}
_TIER_ORDER = {
    AbilityTier.TOP: 0,
    AbilityTier.MIDDLE: 1,
    AbilityTier.LOWER: 2,
    AbilityTier.UNKNOWN: 3,
}


class RankingStrategy(StrEnum):
    """表示順の決め方。既定は本番の CURRENT で、他は検証専用。

    2026-08-04: 統合順位が単勝人気に大きく負けている（1位勝率 20.2% 対 36.9%）ことが
    判明した。CURRENT は同一tier内で fit_label（PAI由来）を能力scoreより優先するため、
    PAIが雑音なら上位tier内の並びをかき混ぜる。どの成分が効いているかを切り分けるために
    別の並べ方を注入できるようにした（本番の既定は変えない）。
    """

    CURRENT = "tier-fit-score"      # 能力tier → 展開向き → 能力score（本番）
    ABILITY_FIRST = "tier-score"    # 能力tier → 能力score（展開を順位付けに使わない）
    SCORE_ONLY = "score"            # 能力scoreの連続値のみ（tierも使わない）


def _sort_key(
    strategy: RankingStrategy,
    tier_order: int,
    fit_order: int,
    score: float,
) -> tuple[float, float, float]:
    if strategy is RankingStrategy.ABILITY_FIRST:
        return (tier_order, -score, 0.0)
    if strategy is RankingStrategy.SCORE_ONLY:
        return (-score, 0.0, 0.0)
    return (tier_order, fit_order, -score)


def build_integrated_ranking(
    abilities: tuple[AbilityScore, ...],
    fits: tuple[PaiResult, ...],
    strategy: RankingStrategy = RankingStrategy.CURRENT,
) -> IntegratedRanking:
    """能力スコアとPAI結果から2軸分類・表示順を組み立てる。

    abilities / fits は同一レースの全出走馬分。horse_no で突き合わせる。
    strategy は表示順の決め方（既定は本番）。mark・tier・fit_label の判定は
    strategy に依らず同じで、変わるのは並び順だけ。
    """
    fit_by_no = {f.horse_no: f for f in fits}
    tier_by_no = _assign_relative_tiers(abilities)

    entries_unranked: list[tuple[float, float, float, IntegratedEntry]] = []
    for ability in abilities:
        fit = fit_by_no.get(ability.horse_no)
        fit_label = fit.fit_label if fit is not None else FitLabel.NEUTRAL
        tier = tier_by_no[ability.horse_no]
        mark = _classify(tier, fit_label)
        # 既定の表示順キー: 能力tier（主） → 展開向き（従） → 能力score（細分）。
        sort_key = _sort_key(
            strategy, _TIER_ORDER[tier], _FIT_ORDER[fit_label], ability.score
        )
        entry = IntegratedEntry(
            horse_no=ability.horse_no,
            rank=0,  # 後で採番
            mark=mark,
            ability_tier=tier,
            fit_label=fit_label,
            reasons=_entry_reasons(mark, tier, fit_label),
        )
        entries_unranked.append((*sort_key, entry))

    entries_unranked.sort(key=lambda t: (t[0], t[1], t[2]))
    ranked = tuple(
        IntegratedEntry(
            horse_no=e.horse_no,
            rank=i + 1,
            mark=e.mark,
            ability_tier=e.ability_tier,
            fit_label=e.fit_label,
            reasons=e.reasons,
        )
        for i, (_, _, _, e) in enumerate(entries_unranked)
    )

    return IntegratedRanking(
        model_version=MODEL_VERSION,
        entries=ranked,
        reasons=_summary_reasons(ranked),
    )


def _assign_relative_tiers(abilities: tuple[AbilityScore, ...]) -> dict[int, AbilityTier]:
    """能力scoreのレース内相対順位から上位/中位/下位を割り当てる。

    近走データ無し(sample_size=0)は公平に順位付けできないため UNKNOWN。
    """
    tiers: dict[int, AbilityTier] = {}
    ranked = sorted(
        (a for a in abilities if a.sample_size > 0),
        key=lambda a: a.score,
        reverse=True,
    )
    for a in abilities:
        if a.sample_size == 0:
            tiers[a.horse_no] = AbilityTier.UNKNOWN

    n = len(ranked)
    if n == 0:
        return tiers
    top_n = max(1, n // 3)
    lower_n = max(1, n // 3)
    for i, a in enumerate(ranked):
        if i < top_n:
            tiers[a.horse_no] = AbilityTier.TOP
        elif i >= n - lower_n:
            tiers[a.horse_no] = AbilityTier.LOWER
        else:
            tiers[a.horse_no] = AbilityTier.MIDDLE
    return tiers


def _classify(tier: AbilityTier, fit_label: FitLabel) -> Mark:
    if tier == AbilityTier.TOP:
        if fit_label == FitLabel.MATCHED:
            return Mark.HONMEI
        if fit_label == FitLabel.UNFAVORABLE:
            return Mark.KIKEN
        return Mark.TAIKO
    if tier == AbilityTier.MIDDLE and fit_label == FitLabel.MATCHED:
        return Mark.ANA
    return Mark.NONE


def _entry_reasons(mark: Mark, tier: AbilityTier, fit_label: FitLabel) -> tuple[Reason, ...]:
    description = {
        Mark.HONMEI: "地力は上位で、想定される流れも向くと見ています。",
        Mark.TAIKO: "地力は上位。流れの後押しは限定的でも軸として信頼できます。",
        Mark.KIKEN: "地力は上位ですが、想定の流れは向きにくく取りこぼしに注意です。",
        Mark.ANA: "地力は中位ですが、想定の流れが向けば上位進出の余地があります。",
        Mark.NONE: "現時点では能力・展開の両面から強調材料は多くありません。",
    }[mark]
    return (
        Reason(code="integrated_mark", description=description),
        Reason(
            code="integrated_axes",
            description=f"能力は{tier}、展開との相性は「{fit_label}」と評価しています。",
        ),
    )


def _summary_reasons(entries: tuple[IntegratedEntry, ...]) -> tuple[Reason, ...]:
    honmei = [e.horse_no for e in entries if e.mark == Mark.HONMEI]
    ana = [e.horse_no for e in entries if e.mark == Mark.ANA]
    kiken = [e.horse_no for e in entries if e.mark == Mark.KIKEN]
    reasons: list[Reason] = [
        Reason(
            code="integrated_method",
            description="地力（近走内容）と想定される流れへの適性の2軸で分類しています。",
        )
    ]
    if honmei:
        reasons.append(
            Reason(
                code="integrated_honmei",
                description=f"能力・展開の両面がそろう本命候補は{_nos(honmei)}です。",
            )
        )
    if ana:
        reasons.append(
            Reason(
                code="integrated_ana",
                description=f"流れ次第で浮上する穴候補は{_nos(ana)}です。",
            )
        )
    if kiken:
        reasons.append(
            Reason(
                code="integrated_kiken",
                description=f"地力上位でも流れが向きにくい注意馬は{_nos(kiken)}です。",
            )
        )
    return tuple(reasons)


def _nos(horse_nos: list[int]) -> str:
    return "・".join(f"{n}番" for n in horse_nos)
