"""能力指数 (ability-v3) 算出モジュール。

展開適性(PAI)とは独立に、馬の「地力（近走内容の強さ）」を推定する指標。
統合順位予想（展開×能力の2軸分類）の能力軸として使う。

設計上の制約:
    本指標の中核は「出走頭数で正規化した近走着順の新しさ加重平均」。クラス補正は
    grade を優先し、欠損時だけ race_class のキーワードから best-effort で行う。
    人気・獲得本賞金も補助成分として使うが、未取得の成分は除外して安全に縮退する。
    馬体重は永続化するものの、体格の大小を地力と結び付ける根拠がないため加点しない。
    → 絶対値の意味は限定的なので、上位/中位/下位の tier 判定はレース内の相対順位で
      行う（統合層 `integrated_ranking` が担当）。本モジュールは 0〜100 の score と
      根拠のみを返す。

説明可能性の原則（CLAUDE.md）に従い、全算出結果に reasons を付与する。
UI へは実数値を出さず、統合層で言葉・記号（◎○▲△）へ翻訳する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pci.domain.shared.reason import Reason

MODEL_VERSION = "ability-v3"


@dataclass(frozen=True)
class AbilityRaceResult:
    """能力指数の入力となる過去1走（core 層の確定データから組み立てる）。"""

    finish_pos: int | None
    field_size: int
    race_class: str | None
    days_ago: int
    grade: str | None = None
    # Phase2。未取得は None（旧データ）→ 該当成分を使わず form のみへ縮退。
    popularity: int | None = None  # 単勝人気順（1=1番人気）
    prize_money: int | None = None  # 獲得本賞金（円・入着時のみ正値）


@dataclass(frozen=True)
class AbilityWeights:
    """能力指数の重み（🧪暫定・実データ検証後に確定。`docs/SPEC.md §9`）。"""

    recent_races: int = 5
    # 新しさ減衰（レース日からの経過日数で加重）
    decay_within_180d: float = 1.0
    decay_within_365d: float = 0.7
    decay_beyond_365d: float = 0.4
    # クラス係数（race_class キーワードから best-effort 判定）
    class_g1: float = 1.5
    class_g2: float = 1.35
    class_g3: float = 1.25
    class_open: float = 1.15  # オープン・リステッド・重賞以外のステークス
    class_3win: float = 1.05
    class_2win: float = 1.0
    class_1win: float = 0.9
    class_maiden: float = 0.8  # 未勝利・新馬
    class_unknown: float = 1.0
    # score 正規化基準（contribution=finish_rate×class_coef の想定最大値）
    score_reference: float = 1.5
    # 能力成分のブレンド重み（🧪暫定）。データが無い成分は自動的に除外し、
    # 残りの重みで再正規化する（旧データは form のみ＝v1 相当へ縮退）。
    weight_form: float = 0.55
    weight_prize: float = 0.30
    weight_popularity: float = 0.15
    # 本賞金の対数正規化レンジ（円）。base=下限, top=上限（G1級の入着賞金相当）。
    prize_log_base: float = 100_000.0
    prize_log_top: float = 100_000_000.0
    # 人気サポートの正規化上限（この人気以下を 0 とみなす）。
    popularity_span: int = 18


DEFAULT_WEIGHTS = AbilityWeights()


@dataclass(frozen=True)
class AbilityScore:
    """能力指数の算出結果（1頭分）。tier はレース内相対のため統合層で付与する。"""

    horse_no: int
    score: float  # 0〜100（内部値・UIには出さない）
    sample_size: int  # 有効な近走数
    model_version: str
    reasons: tuple[Reason, ...]


class AbilityScorer:
    """近走着順・grade・賞金・人気から地力を推定する能力指数算出器。"""

    def __init__(self, weights: AbilityWeights | None = None) -> None:
        self._w = weights or DEFAULT_WEIGHTS

    def score(self, horse_no: int, results: tuple[AbilityRaceResult, ...]) -> AbilityScore:
        w = self._w
        # 新しい順に上位 recent_races 走のみを対象とする（呼び出し側で並べ替え済みでも
        # ここで days_ago 昇順に整えて上限本数を切る）。
        usable = [
            r
            for r in sorted(results, key=lambda r: r.days_ago)
            if r.finish_pos is not None and r.field_size >= 2 and 1 <= r.finish_pos <= r.field_size
        ][: w.recent_races]

        if not usable:
            return AbilityScore(
                horse_no=horse_no,
                score=0.0,
                sample_size=0,
                model_version=MODEL_VERSION,
                reasons=(
                    Reason(
                        code="ability_no_data",
                        description="近走の確定データが少なく、地力は評価しづらい状況です。",
                    ),
                ),
            )

        # 成分1: 近走内容（着順×クラス）。常に算出する。
        form_sum = 0.0
        form_wt = 0.0
        prize_sum = 0.0
        prize_wt = 0.0
        pop_sum = 0.0
        pop_wt = 0.0
        best: tuple[float, AbilityRaceResult, str] | None = None
        for r in usable:
            assert r.finish_pos is not None  # usable 条件で保証
            recency = _recency_weight(r.days_ago, w)
            finish_rate = (r.field_size - r.finish_pos) / (r.field_size - 1)
            class_coef, class_label = _class_coefficient(r.grade, r.race_class, w)
            contribution = finish_rate * class_coef
            form_sum += min(contribution / w.score_reference, 1.0) * recency
            form_wt += recency
            if best is None or contribution > best[0]:
                best = (contribution, r, class_label)
            # 成分2: 本賞金（入着時のみ正値。対数正規化）。
            if r.prize_money is not None and r.prize_money > 0:
                prize_sum += _prize_score(float(r.prize_money), w) * recency
                prize_wt += recency
            # 成分3: 人気サポート（1番人気=1.0）。
            if r.popularity is not None and r.popularity >= 1:
                pop_sum += _popularity_score(r.popularity, w) * recency
                pop_wt += recency

        components: list[tuple[float, float]] = []
        if form_wt > 0:
            components.append((w.weight_form, form_sum / form_wt))
        if prize_wt > 0:
            components.append((w.weight_prize, prize_sum / prize_wt))
        if pop_wt > 0:
            components.append((w.weight_popularity, pop_sum / pop_wt))

        weight_total = sum(weight for weight, _ in components)
        blended = (
            sum(weight * value for weight, value in components) / weight_total
            if weight_total > 0
            else 0.0
        )
        score = round(min(max(blended, 0.0), 1.0) * 100.0, 1)

        used_prize = prize_wt > 0
        used_pop = pop_wt > 0
        reasons = _build_reasons(usable, best, score, used_prize=used_prize, used_pop=used_pop)
        return AbilityScore(
            horse_no=horse_no,
            score=score,
            sample_size=len(usable),
            model_version=MODEL_VERSION,
            reasons=reasons,
        )


def _recency_weight(days_ago: int, w: AbilityWeights) -> float:
    if days_ago <= 180:
        return w.decay_within_180d
    if days_ago <= 365:
        return w.decay_within_365d
    return w.decay_beyond_365d


def _prize_score(prize: float, w: AbilityWeights) -> float:
    """本賞金を対数スケールで 0〜1 へ正規化する（高額入着ほど高い）。"""
    lo = math.log10(w.prize_log_base)
    hi = math.log10(w.prize_log_top)
    x = math.log10(max(prize, 1.0))
    return min(max((x - lo) / (hi - lo), 0.0), 1.0)


def _popularity_score(popularity: int, w: AbilityWeights) -> float:
    """人気サポートを 0〜1 へ（1番人気=1.0、下位人気=0）。"""
    return min(max((w.popularity_span - popularity) / (w.popularity_span - 1), 0.0), 1.0)


def _class_coefficient(
    grade: str | None, race_class: str | None, w: AbilityWeights
) -> tuple[float, str]:
    """gradeを優先し、欠損時だけrace_classからクラス係数を推定する。"""
    normalized_grade = (grade or "").upper().replace("・", "")
    if normalized_grade in {"G1", "JG1"}:
        return w.class_g1, "G1級"
    if normalized_grade in {"G2", "JG2"}:
        return w.class_g2, "G2級"
    if normalized_grade in {"G3", "JG3"}:
        return w.class_g3, "G3級"
    if normalized_grade == "L":
        return w.class_open, "リステッド"
    if normalized_grade == "重賞":
        return w.class_open, "重賞"
    if not race_class:
        return w.class_unknown, "クラス不明"
    s = race_class.upper()
    if any(k in s for k in ("G1", "GI ", "ＧＩ", "JPN1", "GRADE 1")):
        return w.class_g1, "G1級"
    if any(k in s for k in ("G2", "GII", "ＧＩＩ", "JPN2", "GRADE 2")):
        return w.class_g2, "G2級"
    if any(k in s for k in ("G3", "GIII", "ＧＩＩＩ", "JPN3", "GRADE 3")):
        return w.class_g3, "G3級"
    if "未勝利" in race_class or "新馬" in race_class:
        return w.class_maiden, "未勝利・新馬"
    if any(k in race_class for k in ("3勝", "３勝", "1600万", "１６００万")):
        return w.class_3win, "3勝クラス"
    if any(k in race_class for k in ("2勝", "２勝", "1000万", "１０００万")):
        return w.class_2win, "2勝クラス"
    if any(k in race_class for k in ("1勝", "１勝", "500万", "５００万")):
        return w.class_1win, "1勝クラス"
    if any(k in race_class for k in ("オープン", "ステークス", "Ｓ", "(L)", "（Ｌ）", " L")):
        return w.class_open, "オープン級"
    return w.class_unknown, "クラス不明"


def _build_reasons(
    usable: list[AbilityRaceResult],
    best: tuple[float, AbilityRaceResult, str] | None,
    score: float,
    *,
    used_prize: bool,
    used_pop: bool,
) -> tuple[Reason, ...]:
    reasons: list[Reason] = []
    signals = ["近走の着順内容"]
    if used_prize:
        signals.append("獲得賞金")
    if used_pop:
        signals.append("人気")
    reasons.append(
        Reason(
            code="ability_form",
            description=f"直近{len(usable)}走の{'・'.join(signals)}から地力を評価しています。",
        )
    )
    if best is not None:
        _, r, class_label = best
        assert r.finish_pos is not None
        reasons.append(
            Reason(
                code="ability_best_run",
                description=(
                    f"近走で最も評価できるのは{class_label}での"
                    f"{r.field_size}頭立て{r.finish_pos}着の内容です。"
                ),
            )
        )
    reasons.append(
        Reason(
            code="ability_level",
            description=_level_reason(score),
        )
    )
    return tuple(reasons)


def _level_reason(score: float) -> str:
    if score >= 62.0:
        return "近走の相手・着順を踏まえると地力は上位クラスと見ています。"
    if score >= 40.0:
        return "近走内容は平均的で、地力は中位クラスと見ています。"
    return "近走内容からは地力上位とまでは見ていません。"
