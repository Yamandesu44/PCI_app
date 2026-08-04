"""展開コメント生成（RuleBasedCommentGenerator / comment-v2）の単体テスト。

決定論的なルールベース生成のため、見出し・本文・説明可能性 reasons を検証する。
"""

from __future__ import annotations

import re

from pci.domain.pace.commentary import (
    COMMENTARY_VERSION,
    BeneficiaryRef,
    ForecastCommentInput,
    ReviewCommentInput,
    ReviewHorseRef,
    RuleBasedCommentGenerator,
)
from pci.domain.pace.rpci_forecast import PaceLabel

_BEGINNER_FORBIDDEN = re.compile(r"\b(PCI3?|RPCI|PAI)\b|\d+\.\d+", re.IGNORECASE)


def _visible_text(out) -> str:
    body = "\n".join(out.body)
    return f"{out.headline}\n{body}"


def _assert_beginner_safe(out: object) -> None:
    assert _BEGINNER_FORBIDDEN.search(_visible_text(out)) is None


def _forecast_input(
    *,
    pace_label: PaceLabel = PaceLabel.SLOW,
    rpci: float = 52.5,
    confidence: float = 0.7,
    front: tuple[int, ...] = (1, 2),
    beneficiaries: tuple[BeneficiaryRef, ...] = (BeneficiaryRef(3, 82.0),),
    horse_numbers_confirmed: bool = True,
) -> ForecastCommentInput:
    return ForecastCommentInput(
        distance_m=1600,
        track_type="芝",
        field_size=8,
        pace_label=pace_label,
        predicted_rpci=rpci,
        confidence=confidence,
        front_runners=front,
        beneficiaries=beneficiaries,
        horse_numbers_confirmed=horse_numbers_confirmed,
    )


class TestForecastComment:
    def test_all_pace_labels_produce_distinct_headlines(self) -> None:
        gen = RuleBasedCommentGenerator()
        headlines = {
            label: gen.forecast_comment(_forecast_input(pace_label=label)).headline
            for label in PaceLabel
        }
        assert len(set(headlines.values())) == 3  # 3 ラベルで見出しが重複しない

    def test_output_has_version_body_and_reasons(self) -> None:
        out = RuleBasedCommentGenerator().forecast_comment(_forecast_input())
        assert out.model_version == COMMENTARY_VERSION
        assert len(out.body) >= 3  # 流れ・帰結・注目馬
        assert out.reasons  # 説明可能性
        assert all(para for para in out.body)  # 空段落なし

    def test_deterministic(self) -> None:
        gen = RuleBasedCommentGenerator()
        data = _forecast_input()
        assert gen.forecast_comment(data) == gen.forecast_comment(data)

    def test_beneficiary_mentioned_in_body(self) -> None:
        out = RuleBasedCommentGenerator().forecast_comment(
            _forecast_input(beneficiaries=(BeneficiaryRef(7, 88.0),))
        )
        joined = "".join(out.body)
        assert "7番" in joined
        _assert_beginner_safe(out)

    def test_forecast_visible_text_hides_raw_indexes(self) -> None:
        out = RuleBasedCommentGenerator().forecast_comment(_forecast_input())
        _assert_beginner_safe(out)

    def test_no_beneficiary_uses_fallback_wording(self) -> None:
        out = RuleBasedCommentGenerator().forecast_comment(_forecast_input(beneficiaries=()))
        joined = "".join(out.body)
        assert "力関係どおり" in joined

    def test_low_confidence_appends_caveat(self) -> None:
        gen = RuleBasedCommentGenerator()
        strong = gen.forecast_comment(_forecast_input(confidence=0.8))
        weak = gen.forecast_comment(_forecast_input(confidence=0.3))
        assert len(weak.body) == len(strong.body) + 1
        assert "確信度は高くなく" in weak.body[-1]

    def test_front_runner_count_reflected(self) -> None:
        gen = RuleBasedCommentGenerator()
        none_front = "".join(gen.forecast_comment(_forecast_input(front=())).body)
        one_front = "".join(gen.forecast_comment(_forecast_input(front=(1,))).body)
        many_front = "".join(gen.forecast_comment(_forecast_input(front=(1, 2, 3))).body)
        assert "見当たらず" in none_front
        assert "1頭だけで" in one_front
        assert "3頭そろい" in many_front

    def test_multiple_beneficiaries_mentions_others(self) -> None:
        """注目馬が2頭以上のとき「複数います」の文言が入る。"""
        out = RuleBasedCommentGenerator().forecast_comment(
            _forecast_input(beneficiaries=(BeneficiaryRef(3, 82.0), BeneficiaryRef(6, 75.0)))
        )
        joined = "".join(out.body)
        assert "3番" in joined
        assert "複数" in joined
        _assert_beginner_safe(out)

    def test_unconfirmed_beneficiary_is_described_as_registration_order(self) -> None:
        out = RuleBasedCommentGenerator().forecast_comment(
            _forecast_input(
                beneficiaries=(BeneficiaryRef(7, 88.0),),
                horse_numbers_confirmed=False,
            )
        )
        joined = "".join(out.body)
        assert "登録順 7（馬番未確定）" in joined
        assert "7番" not in joined


class TestReviewComment:
    def test_slow_pace_classified(self) -> None:
        # 芝のスローは >54.0（pci-v3の3分位）。53.0は平均帯に入る。
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=56.0,
                pci3_actual=52.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=10,
                sample_size=8,
                horses=(ReviewHorseRef(1, 1, "先行", 54.0),),
            )
        )
        assert "落ち着いた" in out.headline
        assert out.model_version == COMMENTARY_VERSION
        _assert_beginner_safe(out)

    def test_high_pace_classified(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=46.0,
                pci3_actual=45.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=12,
                sample_size=10,
                horses=(ReviewHorseRef(5, 1, "差し", 44.0),),
            )
        )
        assert "速い" in out.headline
        _assert_beginner_safe(out)

    def test_winner_mentioned(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=50.0,
                pci3_actual=50.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=8,
                sample_size=8,
                horses=(
                    ReviewHorseRef(3, 2, "差し", 49.0),
                    ReviewHorseRef(7, 1, "逃げ", 51.0),
                ),
            )
        )
        joined = "".join(out.body)
        assert "7番" in joined  # 1着馬
        assert "逃げ" in joined

    def test_insufficient_data(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=None,
                pci3_actual=None,
                formula_version="pci-v3",
                track_type="芝",
                field_size=5,
                sample_size=0,
                horses=(),
            )
        )
        assert "不足" in out.headline
        assert out.body  # 空ではない
        assert out.reasons
        _assert_beginner_safe(out)

    def test_small_sample_caveat(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=50.0,
                pci3_actual=None,
                formula_version="pci-v3",
                track_type="芝",
                field_size=3,
                sample_size=2,
                horses=(ReviewHorseRef(1, 1, "先行", 50.0),),
            )
        )
        assert any("参考値" in para for para in out.body)

    def test_winner_pace_phrase_variants(self) -> None:
        gen = RuleBasedCommentGenerator()
        # 勝ち馬 PCI が実績RPCI より高い → 後半に脚を伸ばす形
        late = gen.review_comment(
            ReviewCommentInput(
                rpci_actual=48.0,
                pci3_actual=48.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=8,
                sample_size=8,
                horses=(ReviewHorseRef(4, 1, "追込", 54.0),),
            )
        )
        # 勝ち馬 PCI が実績RPCI より低い → 前々で押し切る形
        early = gen.review_comment(
            ReviewCommentInput(
                rpci_actual=54.0,
                pci3_actual=54.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=8,
                sample_size=8,
                horses=(ReviewHorseRef(2, 1, "逃げ", 47.0),),
            )
        )
        assert any("後半に脚を伸ばす" in para for para in late.body)
        assert any("押し切り" in para for para in early.body)

    def test_no_confirmed_finisher_skips_winner_sentence(self) -> None:
        """着順未確定の馬しかいない場合でも、勝ち馬文なしでコメントを返す。"""
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=50.0,
                pci3_actual=50.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=8,
                sample_size=8,
                horses=(ReviewHorseRef(1, None, "先行", 50.0),),
            )
        )
        assert out.body  # 概況の段落は出る
        assert not any("勝ったのは" in para for para in out.body)


class TestForecastAccuracyInReview:
    """出走前の想定RPCIとの答え合わせ文言（回顧フィードバックループ）。"""

    def _input(self, predicted_label: PaceLabel | None, actual_label: PaceLabel | None) -> (
        ReviewCommentInput
    ):
        return ReviewCommentInput(
            rpci_actual=52.0,
            pci3_actual=52.0,
            formula_version="pci-v3",
            track_type="芝",
            field_size=8,
            sample_size=8,
            horses=(ReviewHorseRef(1, 1, "先行", 52.0),),
            predicted_rpci=53.0,
            predicted_label=predicted_label,
            actual_label=actual_label,
        )

    def test_no_prediction_data_omits_accuracy_sentence(self) -> None:
        """predicted_label が None（予測未保存）なら答え合わせ文言は出ない（後方互換）。"""
        out = RuleBasedCommentGenerator().review_comment(
            ReviewCommentInput(
                rpci_actual=52.0,
                pci3_actual=52.0,
                formula_version="pci-v3",
                track_type="芝",
                field_size=8,
                sample_size=8,
                horses=(ReviewHorseRef(1, 1, "先行", 52.0),),
            )
        )
        assert not any("事前の想定" in para for para in out.body)

    def test_label_hit_mentions_correct_forecast(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            self._input(PaceLabel.SLOW, PaceLabel.SLOW)
        )
        joined = "".join(out.body)
        assert "事前の想定「やや落ち着いた流れ」が的中しました。" in joined

    def test_label_miss_mentions_both_predicted_and_actual(self) -> None:
        out = RuleBasedCommentGenerator().review_comment(
            self._input(PaceLabel.SLOW, PaceLabel.HIGH)
        )
        joined = "".join(out.body)
        assert "事前の想定は「やや落ち着いた流れ」でしたが" in joined
        assert "実際は「やや速い流れ」という結果でした。" in joined

    def test_accuracy_reason_included(self) -> None:
        """reasons に forecast_accuracy コードで的中/外れの根拠が出力される。"""
        out = RuleBasedCommentGenerator().review_comment(
            self._input(PaceLabel.SLOW, PaceLabel.HIGH)
        )
        reason = next(r for r in out.reasons if r.code == "forecast_accuracy")
        assert "外れ" in reason.description
