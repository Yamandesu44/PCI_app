"""PAI (Pace Adaptability Index) 算出モジュール。

想定RPCI に対する各馬の展開適性を 0〜100 で表す独自指標（ドメインの王冠）。
本プロダクトの最重要価値「PCI を理解していない競馬ファンでも展開予想を活用できる」を
体現する説明可能な指標として、減点内訳を必ず reasons に出力する。

算出式（pai-v5・重みは設定ファイルで調整可能）:
    deviation = clamp((想定RPCI − コース中立値) ÷ 平均帯の半幅, −1, +1)
    PAI = 50 + 感応度(脚質) × pace_swing × deviation − 距離補正 − 馬場補正
      ペース補正: コース平均からの振れに対し、脚質ごとの感応度で加減点する
      距離補正  : 距離適性の乖離に対する減点
      馬場補正  : 馬場（道悪）不適性に対する減点
    `pace_affinity`（その馬自身の過去のペース別実績）があれば最後に50%で混ぜる。

**PAI は脚質内の相対量**。50 =「今回の流れは、この脚質にとって普段どおり」で、
絶対的な強さではない。ダートの追込は常に50だが好走率は 0.47x と低い。
**脚質をまたいで馬を PAI 順に並べてはならない**（docs/DECISIONS.md ADR-2026-08-04）。

合致ラベル:
    PAI >= matched_threshold(コース, 脚質) : 合致（展開の恩恵を受ける）
    PAI <  unfavorable_threshold           : 不利（展開が向かない）
    その間                                 : 中立

**合致の閾値は（コース×脚質）ごと**（pai-v5）。PAI が脚質内の相対量である以上、
全脚質共通の絶対値と比べるのは前提の裏切りで、実測にそのまま出ていた（500レース）:

    芝   自在  PAI平均 48.7 → 合致  0.0%（602頭中0頭・**構造的に到達できない**）
    ダート 差し  PAI平均 59.4 → 合致 48.1%
    ダート 全体                → レース中央値 53.8% が合致（絞り込みに使えない）

単一閾値は「脚質をまたいで比べない」と言いながら、暗黙に脚質を順位付けていた。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.affinity import (
    HorsePaceAffinityProfile,
    affinity_label,
    level_display,
    pace_level_from_index,
)
from pci.domain.pace.rpci_forecast import RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "pai-v5"

_OFF_TRACK_CONDITIONS = ("稍重", "重", "不良")


class FitLabel(StrEnum):
    """展開合致ラベル。"""

    MATCHED = "合致"
    NEUTRAL = "中立"
    UNFAVORABLE = "不利"


@dataclass(frozen=True)
class HorsePaceProfile:
    """PAI 算出に必要な馬のプロファイル。"""

    horse_no: int
    running_style: RunningStyleLabel
    distance_aptitude_m: int | None = None
    weak_on_off_track: bool = False
    pace_affinity: HorsePaceAffinityProfile | None = None


@dataclass(frozen=True)
class PaiWeights:
    """PAI 算出の重み（C10・設定ファイルから上書き可能）。"""

    # 脚質ごとのペース感応度（pai-v3 で導入）。正=スローで有利、0=ペース依存なし。
    # 2026-08-04に21万頭で較正（`--pace-style-matrix` の「自脚質の平均に対する比」）。
    #   芝   スロー時: 逃げ1.21x 先行1.12x 自在1.13x 差し1.04x 追込0.98x
    #   ダート スロー時: 逃げ1.17x 先行1.12x 自在1.09x 差し0.94x 追込0.96x
    # 差し・追込は芝とダートで符号が揃わず（差し 1.04x 対 0.94x）、ADR-0010 が
    # 「後方脚質に一貫した有利はない」と結論した通りなので 0 とする。
    #
    # 旧 pai-v2 は preferred RPCI を絶対値（逃げ55.0〜追込45.0）で持ち、コース種別の
    # 補正が無かった。分布の異なる芝(52.0)とダート(46.5)で脚質の順序が反転し、
    # ダートでは最も好走する逃げ(1.41x)に低い値、最も走らない追込(0.47x)に高い値を
    # 与えていた（docs/DECISIONS.md ADR-2026-08-04）。
    sensitivity_escape: float = 1.0
    sensitivity_front: float = 0.65
    sensitivity_flexible: float = 0.6
    sensitivity_stalker: float = 0.0
    sensitivity_closer: float = 0.0
    # 感応度1.0の脚質が、区分境界まで振れたときの最大加点/減点（PAI点）。
    #
    # pai-v4 で 25.0 → 10.0 へ下げた。中心ずれを直した上で振れ幅を変えても、
    # 個別馬の判別精度が動かないことを実測で確認したため（500レース・6,575頭）:
    #     全体相関  swing25 +0.073 / swing10 +0.074 / swing5 +0.074 / swing0 +0.073
    # 差はいずれも誤差。加えて実測の効果量そのものが小さい——脚質別展開有利度の
    # 「有利−不利」は 芝+2.8% / ダート+6.5% しかなく、±25点はこれに対し過大だった。
    # 精度が同じなら、実測の効果量へ寄せた側を採る（docs/DECISIONS.md ADR-2026-08-04）。
    pace_swing: float = 10.0
    # 振れの中心を `neutral_rpci` から動かす量（RPCI点）。
    #
    # `neutral_rpci` は全履歴の3分位境界の中点だが、予測RPCIの分布はそこへ揃わない。
    # ずれたままだと感応度の高い脚質だけが系統的に底上げ/底下げされ、pai-v2 の
    # 「脚質の定数効果をPAIへ埋め込む」誤りを別経路で再現する。実測（未補正時）:
    #     芝   予測平均50.72 / 中立51.85 → 平均ずれ-0.248 → 感応度1.0で -6.2点
    #     ダート 予測平均46.55 / 中立46.50 → 平均ずれ+0.172 → 感応度1.0で +4.3点
    # 逃げは両コースとも最良の脚質（芝1.39x・ダート1.41x）なので、芝では実力と逆へ、
    # ダートでは実力と同じ向きへずれていた。`pace-off` の芝/ダート符号逆転
    # （芝+0.016 / ダート-0.016）はこれで全て説明が付く。
    #
    # 値は平均 deviation を0にする解（`--diagnose-pai` の「推奨offset」）。予測平均を
    # 中心へ置くだけでは足りない——deviation は±1で頭打ちになるため、分布が非対称だと
    # 平均が一致していても平均ずれは0にならない（ダートがまさにこれ。予測平均と中立が
    # 0.05しか違わないのに平均ずれ+0.172）。
    #
    # **注意: 2026-06-01以降の500レースから取った当てはめ値。期間外で再確認すること。**
    # `neutral_rpci` 自体は変えていないので、脚質別展開有利度・展開3分類には影響しない。
    pace_center_offset_turf: float = -1.17
    pace_center_offset_dirt: float = 0.47
    # ペースの影響が無いときの基準点。ここへ加減点を足し引きする。
    # 50 = 「今回の流れは、この脚質にとって普段どおり」。
    pace_neutral_pai: float = 50.0
    distance_weight_per_200m: float = 5.0
    distance_cap: float = 20.0
    off_track_penalty: float = 15.0
    # 合致ラベル閾値（pai-v5 で（コース×脚質）別へ）。
    #
    # pai-v4 までは全脚質・両コース共通の 55.0 だった。PAI は脚質内の相対量なので、
    # 共通の絶対値と比べると脚質ごとに実効的な厳しさが変わる。500レース6,575頭の実測:
    #
    #   コース 脚質  現在の合致  → この値で目標30%へ揃う
    #   芝    逃げ   49.7%        70.0
    #   芝    先行   45.6%        68.5
    #   芝    差し   33.5%        59.5
    #   芝    追込   30.4%        55.5
    #   芝    自在    0.0%        49.5   ← 602頭中0頭。到達不能を解消する
    #                                     （ただし中立点50を下回るため 50.5 を採用。下記）
    #   ダート 逃げ   64.6%        70.5
    #   ダート 先行   53.6%        72.0
    #   ダート 差し   48.1%        （分割不能・下記）
    #   ダート 自在    5.1%        50.5
    #   ダート 追込   48.4%        58.0
    #
    # 目標30%は芝の現状（中央値30.0%・合致4.0頭）。**問題が出ていない側**を基準に
    # 置き、新しい恣意的な数字を持ち込まない。
    #
    # **ダートの差しだけ 55.0 に据え置く。** この集団は閾値で分割できない:
    # 感応度0の脚質は base_pai が中立の50で固定され PAI = 0.5×50 + 0.5×affinity、
    # affinity は自分の最良レベルを100へ正規化するので **PAI の上限が 75.0**。
    # ダートはほぼ全レースが同じペース区分に入るため、多くの馬がそこへ並ぶ
    # （75.0 に48.1%・その上は0頭）。塊ごと入れるか丸ごと落とすかしかない。
    # 根治は affinity の正規化を母集団基準へ変えること（pai-v6 で扱う）。
    #
    # **芝の自在は解 49.5 ではなく 50.5 を採る。** 解は分布だけを見るので、49.5 が
    # 中立点50を下回ることを知らない。下回る値を合致にすると「普段どおりより悪い流れ」の
    # 馬に「向く」と言うことになる。実測でもこのセルだけ **合致25.0% < 中立26.2%** と
    # 逆転しており、そもそも芝の自在は PAI で判別できていない（上位1/3対下位1/3が
    # +2.0%・±8.7% で全10セル中もっとも弱い）。中立点の上へ置いて意味を守る。
    #
    # **2026-06-01以降の500レースから取った当てはめ値。期間外で再確認すること。**
    matched_threshold_turf_escape: float = 70.0
    matched_threshold_turf_front: float = 68.5
    matched_threshold_turf_flexible: float = 50.5
    matched_threshold_turf_stalker: float = 59.5
    matched_threshold_turf_closer: float = 55.5
    matched_threshold_dirt_escape: float = 70.5
    matched_threshold_dirt_front: float = 72.0
    matched_threshold_dirt_flexible: float = 50.5
    matched_threshold_dirt_stalker: float = 55.0
    matched_threshold_dirt_closer: float = 58.0
    unfavorable_threshold: float = 45.0

    def __post_init__(self) -> None:
        """閾値の並びを構成時に確かめる。

        1. 合致と不利が重ならないこと。重なると同じ馬が「向く」と「向きにくい」の
           両方に出る。web 側で実際に起きた（割引条件が `pai < 60` のまま合致の
           下限55と重なっていた）。閾値が10個に増えた分、取り違えても気付きにくい。
        2. 合致が中立点を**上回る**こと。`pace_neutral_pai` は「今回の流れは、この脚質に
           とって普段どおり」を表す。そこを下回る値を合致にすると、
           **普段どおりより悪い流れの馬に「向く」と言う**ことになる。
           較正で実際に起きた（pai-v5 初版の芝・自在が 49.5）。目標割合に合わせる
           解き方は分布しか見ないので、意味の側から下限を置いておく必要がある。
        """
        for style in RunningStyleLabel:
            for track in ("芝", "ダート"):
                threshold = self.matched_threshold_for(track, style)
                if threshold <= self.unfavorable_threshold:
                    raise ValueError(
                        f"{track}{style} の合致閾値 {threshold} が"
                        f"不利閾値 {self.unfavorable_threshold} 以下です"
                    )
                if threshold <= self.pace_neutral_pai:
                    raise ValueError(
                        f"{track}{style} の合致閾値 {threshold} が"
                        f"中立点 {self.pace_neutral_pai} 以下です"
                        "（普段どおり以下の流れを「向く」と呼ぶことになります）"
                    )

    def max_pai_for(self, style: RunningStyleLabel) -> float:
        """この脚質が構造上取りうる PAI の上限。

        振れが最大（deviation=+1）・補正なし・affinity が満点のとき。
        感応度0の脚質（差し・追込）は `0.5×50 + 0.5×100 = 75.0` で頭打ちになる。

        **合致より上の帯を作るときは必ずこれと突き合わせること。** 上限を超えた線を
        引くと、その帯は一度も現れないまま「該当なし」を返し続ける。実際 pai-v5 で
        合致閾値を上げた際、固定幅+10の「注目」が10セル中3セルで到達不能になった。
        """
        sensitivity = self._sensitivity_for(style)
        return 0.5 * (self.pace_neutral_pai + sensitivity * self.pace_swing) + 50.0

    def _sensitivity_for(self, style: RunningStyleLabel) -> float:
        return {
            RunningStyleLabel.ESCAPE: self.sensitivity_escape,
            RunningStyleLabel.FRONT: self.sensitivity_front,
            RunningStyleLabel.FLEXIBLE: self.sensitivity_flexible,
            RunningStyleLabel.STALKER: self.sensitivity_stalker,
            RunningStyleLabel.CLOSER: self.sensitivity_closer,
        }[style]

    def matched_threshold_for(self, track_type: str, style: RunningStyleLabel) -> float:
        """このコース・脚質で合致とみなす PAI の下限。

        障害は芝側を使う（`pace_center` と同じ扱い。専用の較正データが無いため）。
        """
        dirt = track_type == "ダート"
        return {
            RunningStyleLabel.ESCAPE: (
                self.matched_threshold_dirt_escape if dirt else self.matched_threshold_turf_escape
            ),
            RunningStyleLabel.FRONT: (
                self.matched_threshold_dirt_front if dirt else self.matched_threshold_turf_front
            ),
            RunningStyleLabel.FLEXIBLE: (
                self.matched_threshold_dirt_flexible
                if dirt
                else self.matched_threshold_turf_flexible
            ),
            RunningStyleLabel.STALKER: (
                self.matched_threshold_dirt_stalker if dirt else self.matched_threshold_turf_stalker
            ),
            RunningStyleLabel.CLOSER: (
                self.matched_threshold_dirt_closer if dirt else self.matched_threshold_turf_closer
            ),
        }[style]


DEFAULT_WEIGHTS = PaiWeights()


def pace_half_band(track_type: str) -> float:
    """展開3分類の「平均」帯の半幅。境界で deviation が±1になるようにする。"""
    from pci.domain.pace.rpci_forecast import DEFAULT_WEIGHTS as RW

    if track_type == "ダート":
        return (RW.dirt_slow_threshold - RW.dirt_high_threshold) / 2
    return (RW.slow_threshold - RW.high_threshold) / 2


def pace_center(track_type: str, weights: PaiWeights = DEFAULT_WEIGHTS) -> float:
    """振れの中心となる RPCI。既定は `neutral_rpci` そのもの。"""
    from pci.domain.pace.style_advantage import neutral_rpci

    offset = (
        weights.pace_center_offset_dirt
        if track_type == "ダート"
        else weights.pace_center_offset_turf
    )
    return neutral_rpci(track_type) + offset


def pace_deviation(
    forecast_rpci: float, track_type: str, weights: PaiWeights = DEFAULT_WEIGHTS
) -> float:
    """コース平均からの振れを −1〜+1 へ正規化する。

    診断側でも同じ値を再現できるよう公開する。この平均が0から離れていると、
    ペース補正が脚質どうしを相対的にずらす（＝脚質の定数効果を再び埋め込む）。
    """
    half_band = pace_half_band(track_type)
    if not half_band:
        return 0.0
    return min(max((forecast_rpci - pace_center(track_type, weights)) / half_band, -1.0), 1.0)


class PaceAdaptabilityScorer:
    """PAI 算出器（pai-v4）。加減点の内訳を reasons として出力する。"""

    def __init__(self, weights: PaiWeights | None = None) -> None:
        self._w = weights or DEFAULT_WEIGHTS

    def score(
        self,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        race_distance_m: int,
        track_condition: str | None = None,
        track_type: str = "芝",
    ) -> PaiResult:
        reasons: list[Reason] = []

        # pai-v3以降: ペースは加減点。基準点からの振れ幅で「普段より有利か」を表す。
        pace_bonus = self._pace_bonus(profile, forecast, track_type, reasons)
        distance_penalty = self._distance_penalty(profile, race_distance_m, reasons)
        track_penalty = self._track_penalty(profile, track_condition, reasons)

        base_pai = round(
            min(
                max(
                    self._w.pace_neutral_pai + pace_bonus - distance_penalty - track_penalty,
                    0.0,
                ),
                100.0,
            ),
            1,
        )
        pai = self._blend_pace_affinity(base_pai, profile, forecast, reasons)
        label = self._classify(pai, track_type, profile.running_style)
        reasons.append(
            Reason(
                code="pai",
                description=f"今回の流れとの総合的な相性は「{label}」です。",
            )
        )

        return PaiResult(
            horse_no=profile.horse_no,
            pai=pai,
            fit_label=label,
            model_version=MODEL_VERSION,
            reasons=tuple(reasons),
            low_evidence=profile.pace_affinity is None or profile.pace_affinity.is_fallback,
        )

    def _sensitivity(self, style: RunningStyleLabel) -> float:
        return self._w._sensitivity_for(style)

    def _pace_bonus(
        self,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        track_type: str,
        reasons: list[Reason],
    ) -> float:
        """今回の流れが、この脚質にとって普段より追い風か向かい風かを点数にする。

        コース平均（neutral_rpci）を0とし、展開区分の境界で±1になるよう正規化する。
        絶対RPCIではなくコース相対で見るのが pai-v3 の要点。芝とダートは分布が
        異なる（52.0 対 46.5）ため、絶対値で判定すると脚質の順序が反転する。
        """
        deviation = pace_deviation(forecast.value, track_type, self._w)
        bonus = self._sensitivity(profile.running_style) * self._w.pace_swing * deviation
        reasons.append(
            Reason(
                code="pace_fit",
                description=_style_reason(profile.running_style, bonus, self._w.pace_swing),
            )
        )
        return bonus

    def _distance_penalty(
        self, profile: HorsePaceProfile, race_distance_m: int, reasons: list[Reason]
    ) -> float:
        if profile.distance_aptitude_m is None:
            reasons.append(
                Reason(
                    code="distance_no_data",
                    description="距離面は大きな不安材料を見ていません。",
                )
            )
            return 0.0
        gap_m = abs(race_distance_m - profile.distance_aptitude_m)
        penalty = min((gap_m / 200.0) * self._w.distance_weight_per_200m, self._w.distance_cap)
        reasons.append(
            Reason(
                code="distance_diff",
                description=_distance_reason(penalty),
            )
        )
        return penalty

    def _track_penalty(
        self, profile: HorsePaceProfile, track_condition: str | None, reasons: list[Reason]
    ) -> float:
        if profile.weak_on_off_track and track_condition in _OFF_TRACK_CONDITIONS:
            penalty = self._w.off_track_penalty
            reasons.append(
                Reason(
                    code="off_track",
                    description="馬場が渋ると力を出し切れない可能性があります。",
                )
            )
            return penalty
        reasons.append(
            Reason(code="track_ok", description="馬場面は大きな不安材料を見ていません。")
        )
        return 0.0

    def _blend_pace_affinity(
        self,
        base_pai: float,
        profile: HorsePaceProfile,
        forecast: RpciForecast,
        reasons: list[Reason],
    ) -> float:
        if profile.pace_affinity is None:
            return base_pai

        predicted_level = pace_level_from_index(forecast.value)
        pace_affinity_score = profile.pace_affinity.scores[predicted_level]
        label = affinity_label(pace_affinity_score)
        preferred = level_display(profile.pace_affinity.preferred_level)
        current = level_display(predicted_level)
        if profile.pace_affinity.is_fallback:
            description = (
                "過去好走データが少ないため脚質傾向から補完しています。"
                f"得意な流れは{preferred}寄りで、今回との相性は「{label}」です。"
            )
        elif profile.pace_affinity.preferred_level != predicted_level and label in (
            "高相性",
            "合致",
        ):
            # ピーク(preferred_level)は別レベルだが、今回のレベル自体にも
            # 隣接にじみでは届かない高スコア＝直接の好走実績がある。
            # 「ピークにしか実績がない」という誤解を避けるため、今回レベルでの
            # 実績にも言及する（さもないと同じ preferred_level を持つ馬でも
            # 今回レベルでの実際の強さが説明文に反映されない）。
            description = (
                f"過去の好走は{preferred}を中心に、今回の{current}でも好走実績があり、"
                f"相性は「{label}」です。"
            )
        else:
            description = (
                f"過去の好走は{preferred}に集まっており、今回の{current}との相性は「{label}」です。"
            )
        reasons.append(Reason(code="pace_affinity", description=description))
        return round((base_pai * 0.5) + (pace_affinity_score * 0.5), 1)

    def _classify(self, pai: float, track_type: str, style: RunningStyleLabel) -> FitLabel:
        if pai >= self._w.matched_threshold_for(track_type, style):
            return FitLabel.MATCHED
        if pai < self._w.unfavorable_threshold:
            return FitLabel.UNFAVORABLE
        return FitLabel.NEUTRAL


def _style_reason(style: RunningStyleLabel, bonus: float, swing: float) -> str:
    """今回の流れがこの脚質に向くかを言葉にする。bonus は正=向く・負=向かない。

    振れ幅に対する比で判定するので、`pace_swing` を変えても文言の出方は変わらない。
    感応度0の脚質（差し・追込）は常に比0＝中立の文言になる。

    pai-v3 で引数が「減点」から「加点」へ変わったのに閾値が旧スケール（0〜100の減点）
    のまま残っており、**最も不利な馬（bonus=-25）にも「持ち味を出しやすい流れです」と
    出していた**。符号を見ずに上限だけで分岐していたため。
    """
    ratio = bonus / swing if swing else 0.0
    if ratio >= 0.35:
        return f"脚質「{style}」の持ち味を出しやすい流れです。"
    if ratio <= -0.35:
        return f"脚質「{style}」だけで見ると、今回は少し力を出しにくい流れです。"
    return f"脚質「{style}」としては極端な有利・不利は見ていません。"


def _distance_reason(penalty: float) -> str:
    if penalty <= 5.0:
        return "距離面は大きな不安材料を見ていません。"
    if penalty <= 15.0:
        return "距離面では少し注意が必要です。"
    return "距離面では適性から外れる可能性があります。"


@dataclass(frozen=True)
class PaiResult:
    """PAI 算出結果。"""

    horse_no: int
    pai: float
    fit_label: FitLabel
    model_version: str
    reasons: tuple[Reason, ...]
    # この馬について、ペース別の実績が無い（脚質からの推定で埋めている）。
    #
    # 実測（2026-08-04・500レース）で「中立」の好走率が「不利」を下回る現象があり、
    # 原因はここにあった。過去データが無い馬は脚質由来の固定プロファイルを使うが、
    # `_blend_pace_affinity` の50%混合を通ると PAI が狭い範囲へ寄る。感応度0の
    # 差しなら PAI は {40, 45, 50, 52.5} の4値だけになり、5段階中4段階が「中立」へ落ちる。
    # つまり**「中立」は展開の判定ではなく「判断材料が足りない」を吸収していた**。
    # ラベルだけでは区別できないので、表示側が言い分けられるよう別に持つ。
    low_evidence: bool = False
