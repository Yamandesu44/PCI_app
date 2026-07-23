"""脚質別有利度（style-advantage-v3）のテスト。"""

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
        """スロー想定（RPCI高）では 逃げ・先行 > 50 > 差し・追込。"""
        advantage = build_style_advantage(55.0, "芝", (ESCAPE, STALKER))
        scores = _scores(advantage)
        assert scores[ESCAPE] > 50 > scores[STALKER]
        assert scores[FRONT] > 50 > scores[CLOSER]
        # 増幅率により、逃げ・追込は先行・差しより外側に振れる。
        assert scores[ESCAPE] > scores[FRONT]
        assert scores[CLOSER] < scores[STALKER]

    def test_high_pace_favors_closer_styles(self) -> None:
        """ハイ想定（RPCI低）では 差し・追込 > 50 > 逃げ・先行。"""
        advantage = build_style_advantage(45.0, "芝", (ESCAPE, STALKER))
        scores = _scores(advantage)
        assert scores[CLOSER] > scores[STALKER] > 50 > scores[FRONT] > scores[ESCAPE]

    def test_neutral_pace_is_even(self) -> None:
        advantage = build_style_advantage(neutral_rpci("芝"), "芝", (ESCAPE,))
        assert all(entry.score == 50.0 for entry in advantage.entries)

    def test_dirt_uses_dirt_neutral(self) -> None:
        """ダートはRPCI 43が中立。芝の中立50を渡すと大きくスロー扱いになる。"""
        even = build_style_advantage(neutral_rpci("ダート"), "ダート", ())
        assert all(entry.score == 50.0 for entry in even.entries)
        slow_on_dirt = build_style_advantage(50.0, "ダート", ())
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
        scores = _scores(advantage)
        assert scores[ESCAPE] == 95.0
        assert scores[CLOSER] == 5.0

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
    def test_front_score_monotonic_in_rpci(self, rpci: float) -> None:
        """先行スコアはRPCIに単調（スロー寄りほど高い）で、差しと対称。"""
        scores = _scores(build_style_advantage(rpci, "芝", ()))
        assert 5.0 <= scores[FRONT] <= 95.0
        assert scores[FRONT] + scores[STALKER] == pytest.approx(100.0)


class TestStyleAdvantageWeights:
    def test_invalid_slope_rejected(self) -> None:
        with pytest.raises(ValueError, match="勾配"):
            StyleAdvantageWeights(slope_per_point=0)

    def test_invalid_score_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="スコア範囲"):
            StyleAdvantageWeights(score_min=50, score_max=50)
