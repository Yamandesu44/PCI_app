"""RuleBasedRpciForecaster 単体テスト + 不変条件プロパティテスト。"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.rpci_forecast import (
    DEFAULT_WEIGHTS,
    FrontRunnerPaceSample,
    PaceLabel,
    RaceContext,
    RpciForecaster,
    RuleBasedRpciForecaster,
    RuleWeights,
)
from pci.domain.pace.running_style import RunningStyleLabel

ESCAPE = RunningStyleLabel.ESCAPE
FRONT = RunningStyleLabel.FRONT
STALKER = RunningStyleLabel.STALKER
CLOSER = RunningStyleLabel.CLOSER
FLEXIBLE = RunningStyleLabel.FLEXIBLE


def _ctx(
    styles: tuple[RunningStyleLabel, ...],
    distance_m: int = 1600,
    cond: str | None = None,
    front_pace_samples: tuple[FrontRunnerPaceSample, ...] = (),
) -> RaceContext:
    return RaceContext(
        distance_m=distance_m,
        track_type="芝",
        running_styles=styles,
        track_condition=cond,
        front_pace_samples=front_pace_samples,
    )


class TestRuleBasedForecast:
    def test_all_front_runners_gives_high_pace(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        result = forecaster.forecast(_ctx((FRONT,) * 8 + (ESCAPE,) * 2))
        assert result.label == PaceLabel.HIGH
        assert result.value < DEFAULT_WEIGHTS.high_threshold

    def test_all_closers_gives_slow_pace(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        result = forecaster.forecast(_ctx((CLOSER,) * 6 + (STALKER,) * 4))
        assert result.label == PaceLabel.SLOW
        assert result.value > DEFAULT_WEIGHTS.slow_threshold

    def test_balanced_field_gives_average(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        result = forecaster.forecast(_ctx((FRONT,) * 5 + (STALKER,) * 5))
        assert result.label == PaceLabel.AVERAGE

    def test_multiple_escape_lowers_rpci(self) -> None:
        """逃げ馬が増えると先行争いで RPCI が下がる（ハイ方向）。"""
        forecaster = RuleBasedRpciForecaster()
        one = forecaster.forecast(_ctx((ESCAPE,) + (STALKER,) * 9))
        three = forecaster.forecast(_ctx((ESCAPE,) * 3 + (STALKER,) * 7))
        assert three.value < one.value

    def test_longer_distance_raises_base_rpci(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        styles = (FRONT,) * 5 + (STALKER,) * 5
        short = forecaster.forecast(_ctx(styles, distance_m=1200))
        long = forecaster.forecast(_ctx(styles, distance_m=2400))
        assert long.value > short.value

    def test_reasons_always_present(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        result = forecaster.forecast(_ctx((FRONT,) * 5 + (CLOSER,) * 5))
        codes = {r.code for r in result.reasons}
        assert {"distance_base", "style_balance", "escape_pressure", "forecast"} <= codes

    def test_track_condition_reason_added_when_off(self) -> None:
        forecaster = RuleBasedRpciForecaster()
        result = forecaster.forecast(_ctx((FRONT,) * 10, cond="重"))
        assert any(r.code == "track_condition" for r in result.reasons)

    def test_model_version_is_rule_v2(self) -> None:
        result = RuleBasedRpciForecaster().forecast(_ctx((FRONT,) * 10))
        assert result.model_version == "rule-v2"

    def test_empty_field_raises(self) -> None:
        with pytest.raises(ValueError, match="脚質情報がありません"):
            RuleBasedRpciForecaster().forecast(_ctx(()))

    def test_custom_weights_applied(self) -> None:
        weak = RuleWeights(style_balance_weight=0.0, escape_pressure_weight=0.0)
        forecaster = RuleBasedRpciForecaster(weak)
        # バランス無効化 → 距離基準のみ（1800m pivot で base=50）
        result = forecaster.forecast(_ctx((CLOSER,) * 10, distance_m=1800))
        assert result.value == pytest.approx(50.0, abs=0.05)

    def test_satisfies_protocol(self) -> None:
        forecaster: RpciForecaster = RuleBasedRpciForecaster()
        assert forecaster.forecast(_ctx((FRONT,) * 10)) is not None


class TestFrontPaceEvidence:
    """rule-v2: 前付け馬の実績ペース傾向の反映。"""

    @staticmethod
    def _sample(avg_pci: float, size: int = 5, style: RunningStyleLabel = ESCAPE) -> (
        FrontRunnerPaceSample
    ):
        return FrontRunnerPaceSample(horse_no=1, style=style, avg_pci=avg_pci, sample_size=size)

    def test_no_samples_matches_rule_v1_path(self) -> None:
        """サンプル空なら頭数ベース（rule-v1相当）と完全一致する。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) + (STALKER,) * 9
        without = forecaster.forecast(_ctx(styles))
        with_empty = forecaster.forecast(_ctx(styles, front_pace_samples=()))
        assert without.value == with_empty.value
        assert not any(r.code == "front_pace_evidence" for r in without.reasons)

    def test_slow_front_history_pulls_rpci_up(self) -> None:
        """前で緩める傾向（高PCI）の逃げ馬がいるとスロー方向へ動く。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) + (STALKER,) * 9
        base = forecaster.forecast(_ctx(styles))
        slow = forecaster.forecast(_ctx(styles, front_pace_samples=(self._sample(58.0),)))
        assert slow.value > base.value
        assert any(r.code == "front_pace_evidence" for r in slow.reasons)

    def test_fast_front_history_pulls_rpci_down(self) -> None:
        """前で飛ばす傾向（低PCI）の逃げ馬がいるとハイ方向へ動く。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) + (STALKER,) * 9
        base = forecaster.forecast(_ctx(styles))
        fast = forecaster.forecast(_ctx(styles, front_pace_samples=(self._sample(42.0),)))
        assert fast.value < base.value

    def test_more_samples_increase_evidence_weight(self) -> None:
        """同じ平均でもサンプルが多いほど実績側に強く寄る。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) + (STALKER,) * 9
        base = forecaster.forecast(_ctx(styles)).value
        few = forecaster.forecast(_ctx(styles, front_pace_samples=(self._sample(60.0, size=1),)))
        many = forecaster.forecast(_ctx(styles, front_pace_samples=(self._sample(60.0, size=8),)))
        assert abs(many.value - base) > abs(few.value - base)

    def test_zero_size_sample_ignored(self) -> None:
        """sample_size=0 は集計から除外され、頭数ベースのままになる。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) + (STALKER,) * 9
        base = forecaster.forecast(_ctx(styles))
        with_empty = forecaster.forecast(
            _ctx(styles, front_pace_samples=(self._sample(58.0, size=0),))
        )
        assert with_empty.value == base.value
        assert not any(r.code == "front_pace_evidence" for r in with_empty.reasons)

    def test_evidence_path_stays_within_clamp(self) -> None:
        """極端なサンプルでもクランプ範囲を逸脱しない。"""
        forecaster = RuleBasedRpciForecaster()
        styles = (ESCAPE,) * 3 + (STALKER,) * 7
        result = forecaster.forecast(
            _ctx(styles, front_pace_samples=(self._sample(99.0, size=10),))
        )
        assert DEFAULT_WEIGHTS.rpci_min <= result.value <= DEFAULT_WEIGHTS.rpci_max


class TestForecastProperties:
    _styles = st.lists(
        st.sampled_from([ESCAPE, FRONT, STALKER, CLOSER, FLEXIBLE]),
        min_size=1,
        max_size=18,
    )

    @given(styles=_styles, distance=st.integers(min_value=1000, max_value=3600))
    def test_rpci_within_clamp_range(self, styles: list[RunningStyleLabel], distance: int) -> None:
        result = RuleBasedRpciForecaster().forecast(_ctx(tuple(styles), distance_m=distance))
        assert DEFAULT_WEIGHTS.rpci_min <= result.value <= DEFAULT_WEIGHTS.rpci_max

    @given(styles=_styles)
    def test_confidence_within_bounds(self, styles: list[RunningStyleLabel]) -> None:
        result = RuleBasedRpciForecaster().forecast(_ctx(tuple(styles)))
        assert 0.3 <= result.confidence <= 0.9

    @given(styles=_styles)
    def test_label_consistent_with_value(self, styles: list[RunningStyleLabel]) -> None:
        result = RuleBasedRpciForecaster().forecast(_ctx(tuple(styles)))
        if result.value < DEFAULT_WEIGHTS.high_threshold:
            assert result.label == PaceLabel.HIGH
        elif result.value > DEFAULT_WEIGHTS.slow_threshold:
            assert result.label == PaceLabel.SLOW
        else:
            assert result.label == PaceLabel.AVERAGE
