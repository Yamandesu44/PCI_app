"""能力指数 (ability-v1) 算出モジュール。

展開適性(PAI)とは独立に、馬の「地力（近走内容の強さ）」を推定する指標。
統合順位予想（展開×能力の2軸分類）の能力軸として使う。

設計上の制約（現データのみ・Phase1）:
    現状 core 層に永続化されている過去走データは finish_pos / field_size /
    race_class（レース名 or 条件名の文字列）/ race_date 等に限られ、人気・オッズ・
    獲得賞金・grade コードは未取得（`docs/SPEC.md §9`）。そのため本指標の中核は
    「出走頭数で正規化した近走着順の新しさ加重平均」= 事実上の近走充実度で、
    クラス補正は race_class のキーワードから best-effort で行う（判別不能時は中立）。
    → 絶対値の意味は限定的なので、上位/中位/下位の tier 判定はレース内の相対順位で
      行う（統合層 `integrated_ranking` が担当）。本モジュールは 0〜100 の score と
      根拠のみを返す。

説明可能性の原則（CLAUDE.md）に従い、全算出結果に reasons を付与する。
UI へは実数値を出さず、統合層で言葉・記号（◎○▲△）へ翻訳する。
"""

from __future__ import annotations

from dataclasses import dataclass

from pci.domain.shared.reason import Reason

MODEL_VERSION = "ability-v1"


@dataclass(frozen=True)
class AbilityRaceResult:
    """能力指数の入力となる過去1走（core 層の確定データから組み立てる）。"""

    finish_pos: int | None
    field_size: int
    race_class: str | None
    days_ago: int


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
    """能力指数算出器（ability-v1）。近走着順×クラス×新しさから地力を推定する。"""

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

        weighted_sum = 0.0
        weight_total = 0.0
        best: tuple[float, AbilityRaceResult, str] | None = None
        for r in usable:
            assert r.finish_pos is not None  # usable 条件で保証
            finish_rate = (r.field_size - r.finish_pos) / (r.field_size - 1)
            class_coef, class_label = _class_coefficient(r.race_class, w)
            recency = _recency_weight(r.days_ago, w)
            contribution = finish_rate * class_coef
            weighted_sum += contribution * recency
            weight_total += recency
            if best is None or contribution > best[0]:
                best = (contribution, r, class_label)

        avg = weighted_sum / weight_total if weight_total > 0 else 0.0
        score = round(min(max(avg / w.score_reference, 0.0), 1.0) * 100.0, 1)

        reasons = _build_reasons(usable, best, score)
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


def _class_coefficient(race_class: str | None, w: AbilityWeights) -> tuple[float, str]:
    """race_class 文字列からクラス係数を best-effort で推定する。

    grade コードは未永続化のため（`docs/SPEC.md §9`）、レース名／条件名の
    キーワードで判定する。半角・全角の数字表記の両方に対応。判別不能時は中立(1.0)。
    """
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
) -> tuple[Reason, ...]:
    reasons: list[Reason] = []
    reasons.append(
        Reason(
            code="ability_form",
            description=(
                f"直近{len(usable)}走の着順内容から地力を評価しています。"
            ),
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
