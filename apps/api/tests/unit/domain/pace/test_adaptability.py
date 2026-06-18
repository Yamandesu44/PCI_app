"""PaceAdaptabilityScorer (PAI) 単体テスト + 不変条件プロパティテスト。"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.adaptability import (
    FitLabel,
    HorsePaceProfile,
    PaceAdaptabilityScorer,
    PaiWeights,
)
from pci.domain.pace.rpci_forecast import PaceLabel, RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel

ESCAPE = RunningStyleLabel.ESCAPE
CLOSER = RunningStyleLabel.CLOSER
FLEXIBLE = RunningStyleLabel.FLEXIBLE


def _forecast(value: float, label: PaceLabel) -> RpciForecast:
    return RpciForecast(
        value=value, label=label, confidence=0.7, model_version="rule-v1", reasons=()
    )


SLOW = _forecast(57.0, PaceLabel.SLOW)
HIGH = _forecast(43.0, PaceLabel.HIGH)
AVERAGE = _forecast(50.0, PaceLabel.AVERAGE)


class TestPaiCoreLogic:
    def test_escape_horse_matches_slow_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, ESCAPE), SLOW, 1600)
        assert result.fit_label == FitLabel.MATCHED
        assert result.pai >= 70.0

    def test_escape_horse_unfavorable_in_high_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, ESCAPE), HIGH, 1600)
        assert result.fit_label == FitLabel.UNFAVORABLE
        assert result.pai < 46.0

    def test_closer_horse_matches_high_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, CLOSER), HIGH, 1600)
        assert result.fit_label == FitLabel.MATCHED

    def test_closer_horse_unfavorable_in_slow_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, CLOSER), SLOW, 1600)
        assert result.fit_label == FitLabel.UNFAVORABLE

    def test_flexible_horse_is_robust(self) -> None:
        """自在馬はどの展開でも極端に不利にはならない。"""
        scorer = PaceAdaptabilityScorer()
        for fc in (SLOW, HIGH, AVERAGE):
            result = scorer.score(HorsePaceProfile(1, FLEXIBLE), fc, 1600)
            assert result.fit_label != FitLabel.UNFAVORABLE

    def test_distance_mismatch_lowers_pai(self) -> None:
        scorer = PaceAdaptabilityScorer()
        on_dist = scorer.score(HorsePaceProfile(1, ESCAPE, distance_aptitude_m=1600), SLOW, 1600)
        off_dist = scorer.score(HorsePaceProfile(1, ESCAPE, distance_aptitude_m=1200), SLOW, 2000)
        assert off_dist.pai < on_dist.pai

    def test_off_track_penalty_applied(self) -> None:
        scorer = PaceAdaptabilityScorer()
        good = scorer.score(HorsePaceProfile(1, ESCAPE, weak_on_off_track=True), SLOW, 1600, "良")
        heavy = scorer.score(HorsePaceProfile(1, ESCAPE, weak_on_off_track=True), SLOW, 1600, "重")
        assert heavy.pai < good.pai
        assert heavy.pai == pytest.approx(good.pai - 15.0, abs=0.1)

    def test_off_track_not_applied_when_not_weak(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(
            HorsePaceProfile(1, ESCAPE, weak_on_off_track=False), SLOW, 1600, "重"
        )
        assert not any(r.code == "off_track" for r in result.reasons)

    def test_reasons_contain_breakdown(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, ESCAPE), HIGH, 1600)
        codes = {r.code for r in result.reasons}
        assert "rpci_diff" in codes
        assert "pai" in codes

    def test_model_version_is_pai_v1(self) -> None:
        result = PaceAdaptabilityScorer().score(HorsePaceProfile(1, ESCAPE), SLOW, 1600)
        assert result.model_version == "pai-v1"

    def test_custom_weights_change_thresholds(self) -> None:
        strict = PaiWeights(matched_threshold=95.0)
        scorer = PaceAdaptabilityScorer(strict)
        # 平均ペースの逃げ馬（好ペース55との差5→減点25→PAI75）は厳格閾値で合致しない
        result = scorer.score(HorsePaceProfile(1, ESCAPE), AVERAGE, 1600)
        assert result.fit_label != FitLabel.MATCHED


class TestPaiProperties:
    _profiles = st.builds(
        HorsePaceProfile,
        horse_no=st.integers(min_value=1, max_value=18),
        running_style=st.sampled_from([ESCAPE, CLOSER, FLEXIBLE]),
        distance_aptitude_m=st.one_of(st.none(), st.integers(min_value=1000, max_value=3600)),
        weak_on_off_track=st.booleans(),
    )
    _forecasts = st.builds(
        _forecast,
        value=st.floats(min_value=35.0, max_value=65.0),
        label=st.sampled_from(list(PaceLabel)),
    )

    @given(profile=_profiles, fc=_forecasts, dist=st.integers(1000, 3600))
    def test_pai_within_0_100(self, profile: HorsePaceProfile, fc: RpciForecast, dist: int) -> None:
        result = PaceAdaptabilityScorer().score(profile, fc, dist, "重")
        assert 0.0 <= result.pai <= 100.0

    @given(profile=_profiles, fc=_forecasts, dist=st.integers(1000, 3600))
    def test_label_consistent_with_pai(
        self, profile: HorsePaceProfile, fc: RpciForecast, dist: int
    ) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(profile, fc, dist)
        if result.pai >= 70.0:
            assert result.fit_label == FitLabel.MATCHED
        elif result.pai < 46.0:
            assert result.fit_label == FitLabel.UNFAVORABLE
        else:
            assert result.fit_label == FitLabel.NEUTRAL
