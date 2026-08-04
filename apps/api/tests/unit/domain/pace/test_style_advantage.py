"""脚質別有利度（style-advantage-v4）のテスト。"""

from __future__ import annotations

import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.rpci_forecast import DEFAULT_WEIGHTS
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.pace.style_advantage import (
    MODEL_VERSION,
    StyleAdvantageReliability,
    StyleAdvantageWeights,
    build_style_advantage,
    neutral_rpci,
)

ESCAPE = RunningStyleLabel.ESCAPE
FRONT = RunningStyleLabel.FRONT
STALKER = RunningStyleLabel.STALKER
CLOSER = RunningStyleLabel.CLOSER


def _scores(advantage) -> dict[RunningStyleLabel, float]:  # type: ignore[no-untyped-def]
    return {entry.style: entry.score for entry in advantage.entries}


class TestNeutralRpci:
    def test_turf_neutral_is_threshold_midpoint(self) -> None:
        expected = (DEFAULT_WEIGHTS.high_threshold + DEFAULT_WEIGHTS.slow_threshold) / 2
        assert neutral_rpci("芝") == expected

    def test_dirt_neutral_is_dirt_threshold_midpoint(self) -> None:
        assert (
            neutral_rpci("ダート")
            == (DEFAULT_WEIGHTS.dirt_high_threshold + DEFAULT_WEIGHTS.dirt_slow_threshold) / 2
        )


class TestBuildStyleAdvantage:
    def test_slow_pace_favors_front_styles(self) -> None:
        """スロー想定（RPCI高）では 逃げ・先行 > 50。逃げは増幅率で先行より外へ振れる。"""
        advantage = build_style_advantage(55.0, "芝", (ESCAPE, STALKER))
        scores = _scores(advantage)
        assert scores[ESCAPE] > scores[FRONT] > 50

    def test_high_pace_is_unfavorable_for_front_styles(self) -> None:
        """ハイ想定（RPCI低）では 逃げ・先行 < 50。後方は互角のまま動かさない。"""
        advantage = build_style_advantage(45.0, "芝", (ESCAPE, STALKER))
        scores = _scores(advantage)
        assert scores[ESCAPE] < scores[FRONT] < 50

    def test_back_styles_stay_even_regardless_of_pace(self) -> None:
        """差し・追込は展開で動かさない（v4・ADR-0010）。

        実測で後方脚質は帯別好走率が単調にならず、係数を弱めても順序づけられなかった。
        「ハイなら差しに向く」と主張しないことが、この指標の意味そのもの。
        """
        for rpci in (40.0, 45.0, 50.0, 55.0, 60.0):
            scores = _scores(build_style_advantage(rpci, "芝", (ESCAPE, STALKER)))
            assert scores[STALKER] == 50.0
            assert scores[CLOSER] == 50.0

    def test_neutral_pace_is_even(self) -> None:
        advantage = build_style_advantage(neutral_rpci("芝"), "芝", (ESCAPE,))
        assert all(entry.score == 50.0 for entry in advantage.entries)

    def test_dirt_uses_dirt_neutral(self) -> None:
        """ダートはRPCI 46.5が中立。芝の中立51.85を渡すと大きくスロー扱いになる。"""
        even = build_style_advantage(neutral_rpci("ダート"), "ダート", ())
        assert all(entry.score == 50.0 for entry in even.entries)
        slow_on_dirt = build_style_advantage(neutral_rpci("芝"), "ダート", ())
        assert _scores(slow_on_dirt)[FRONT] > 70

    def test_escape_crowd_penalizes_escape_only(self) -> None:
        solo = build_style_advantage(55.0, "芝", (ESCAPE, FRONT))
        crowded = build_style_advantage(55.0, "芝", (ESCAPE, ESCAPE, ESCAPE, FRONT))
        assert _scores(crowded)[ESCAPE] < _scores(solo)[ESCAPE]
        assert _scores(crowded)[FRONT] == _scores(solo)[FRONT]
        assert any(reason.code == "escape_crowd" for reason in crowded.reasons)
        assert not any(reason.code == "escape_crowd" for reason in solo.reasons)

    def test_scores_are_clamped(self) -> None:
        """RPCIクランプ端（65）でもスコアは設定レンジに収まる。"""
        advantage = build_style_advantage(65.0, "芝", ())
        assert _scores(advantage)[ESCAPE] == 95.0
        # 下端の確認は後方脚質を動かす候補係数で行う（既定では常に50のため）。
        low = build_style_advantage(65.0, "芝", (), weights=StyleAdvantageWeights(closer_gain=1.2))
        assert _scores(low)[CLOSER] == 5.0

    def test_model_version_and_reasons(self) -> None:
        advantage = build_style_advantage(53.0, "芝", ())
        assert advantage.model_version == MODEL_VERSION
        assert advantage.reasons
        assert advantage.reasons[0].code == "pace_direction"

    def test_kokura_turf_in_july_is_reference_only(self) -> None:
        advantage = build_style_advantage(
            53.0,
            "芝",
            (ESCAPE, STALKER),
            venue_code="10",
            race_date=datetime.date(2026, 7, 19),
            distance_m=1200,
        )
        standard = build_style_advantage(
            53.0,
            "芝",
            (ESCAPE, STALKER),
            venue_code="02",
            race_date=datetime.date(2026, 7, 19),
            distance_m=1200,
        )

        assert advantage.reliability == StyleAdvantageReliability.REFERENCE
        assert advantage.reliability_reason is not None
        assert "馬場状態別でも同じ傾向" in advantage.reliability_reason
        assert any(reason.code == "seasonal_venue_caution" for reason in advantage.reasons)
        assert advantage.entries == standard.entries

    @pytest.mark.parametrize(
        ("track_type", "venue_code", "race_date", "distance_m"),
        [
            ("芝", "10", datetime.date(2026, 6, 30), 1200),
            ("ダート", "10", datetime.date(2026, 7, 19), 1200),
            ("芝", "02", datetime.date(2026, 7, 19), 1200),
            ("芝", "10", datetime.date(2026, 7, 19), 1800),
        ],
    )
    def test_other_conditions_remain_standard(
        self,
        track_type: str,
        venue_code: str,
        race_date: datetime.date,
        distance_m: int,
    ) -> None:
        advantage = build_style_advantage(
            53.0,
            track_type,
            (),
            venue_code=venue_code,
            race_date=race_date,
            distance_m=distance_m,
        )

        assert advantage.reliability == StyleAdvantageReliability.STANDARD
        assert advantage.reliability_reason is None

    @given(st.floats(min_value=35.0, max_value=65.0))
    def test_front_score_stays_in_range_and_back_stays_even(self, rpci: float) -> None:
        """先行スコアはレンジ内に収まり、差しはRPCIによらず互角のまま。"""
        scores = _scores(build_style_advantage(rpci, "芝", ()))
        assert 5.0 <= scores[FRONT] <= 95.0
        assert scores[STALKER] == 50.0

    @given(st.floats(min_value=35.0, max_value=65.0))
    def test_front_and_back_are_symmetric_when_back_is_scored(self, rpci: float) -> None:
        """後方を採点する候補係数では、先行と差しが50を挟んで対称になる。"""
        scores = _scores(
            build_style_advantage(rpci, "芝", (), weights=StyleAdvantageWeights(stalker_gain=1.0))
        )
        assert scores[FRONT] + scores[STALKER] == pytest.approx(100.0)


class TestStyleAdvantageWeights:
    def test_invalid_slope_rejected(self) -> None:
        with pytest.raises(ValueError, match="勾配"):
            StyleAdvantageWeights(slope_per_point=0)

    def test_invalid_score_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="スコア範囲"):
            StyleAdvantageWeights(score_min=50, score_max=50)

    def test_negative_gain_rejected(self) -> None:
        with pytest.raises(ValueError, match="増幅率"):
            StyleAdvantageWeights(closer_gain=-0.1)

    def test_gain_below_one_allowed(self) -> None:
        """実測で差し・追込の感応度は前付けの1/4以下と判明したため1.0未満を許す。

        当初は「逃げ・追込は必ず1.0以上」と検証していたが、その前提はデータで
        否定された（ADR-0010）。候補比較で下げられないと検証自体ができない。
        """
        weights = StyleAdvantageWeights(closer_gain=0.4, stalker_gain=0.0)
        assert weights.closer_gain == 0.4
        assert weights.stalker_gain == 0.0


class TestFlexibleScoring:
    """自在の採点は重みで切り替える（既定は従来どおり採点しない）。"""

    def test_default_keeps_four_entries_without_flexible(self) -> None:
        advantage = build_style_advantage(55.0, "芝", (ESCAPE, FRONT, STALKER, CLOSER))

        styles = [entry.style for entry in advantage.entries]
        assert styles == [ESCAPE, FRONT, STALKER, CLOSER]
        assert RunningStyleLabel.FLEXIBLE not in styles

    def test_flexible_gain_adds_a_fifth_entry(self) -> None:
        advantage = build_style_advantage(
            55.0,
            "芝",
            (ESCAPE, FRONT, STALKER, CLOSER),
            weights=StyleAdvantageWeights(flexible_gain=0.8),
        )

        scores = _scores(advantage)
        assert RunningStyleLabel.FLEXIBLE in scores
        # 自在はスロー寄りで前付けと同方向（50超）、かつ先行より弱く反応する。
        assert 50.0 < scores[RunningStyleLabel.FLEXIBLE] < scores[FRONT]

    def test_v3_symmetric_behaviour_is_reproducible_via_weights(self) -> None:
        """旧v3（前後対称）の挙動が候補係数で再現できることを固定する。

        v4は後方を採点しないが、比較検証のために旧挙動を作れる必要がある。
        """
        # 中立(46.5)より上＝スロー側。旧v3はここで後方を有利、前方を不利と採点していた。
        v4 = _scores(build_style_advantage(49.5, "ダート", (ESCAPE, FRONT, STALKER, CLOSER)))
        v3 = _scores(
            build_style_advantage(
                49.5,
                "ダート",
                (ESCAPE, FRONT, STALKER, CLOSER),
                weights=StyleAdvantageWeights(stalker_gain=1.0, closer_gain=1.2),
            )
        )

        assert v4[STALKER] == 50.0 and v4[CLOSER] == 50.0
        assert v3[STALKER] < 50.0
        assert v3[CLOSER] < v3[STALKER]
        # 前付け側は v3/v4 で変えていない。
        assert v4[ESCAPE] == v3[ESCAPE]
        assert v4[FRONT] == v3[FRONT]
