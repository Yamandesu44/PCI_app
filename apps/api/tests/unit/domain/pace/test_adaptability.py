"""PaceAdaptabilityScorer (PAI) 単体テスト + 不変条件プロパティテスト。"""

from __future__ import annotations

import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.adaptability import (
    FitLabel,
    HorsePaceProfile,
    PaceAdaptabilityScorer,
    PaiWeights,
)
from pci.domain.pace.affinity import (
    HorsePaceAffinityProfile,
    PaceAffinityRaceResult,
    PaceSpeedLevel,
    build_horse_pace_affinity_profile,
)
from pci.domain.pace.rpci_forecast import PaceLabel, RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.race_key import RaceKey

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


def _make_affinity(is_fallback: bool = False) -> HorsePaceAffinityProfile:
    """テスト用の HorsePaceAffinityProfile を生成する。"""
    scores = {level: 50 for level in PaceSpeedLevel}
    scores[PaceSpeedLevel.HIGH] = 80
    return HorsePaceAffinityProfile(
        horse_id="H001",
        sample_size=0 if is_fallback else 3,
        preferred_level=PaceSpeedLevel.HIGH,
        scores=scores,
        evidence=(),
        confidence=0.4 if is_fallback else 0.8,
        is_fallback=is_fallback,
    )


class TestPaiPaceAffinityBlend:
    """pace_affinity を渡した場合の _blend_pace_affinity ブランチを検証する。"""

    def test_pace_affinity_reason_added(self) -> None:
        """pace_affinity 指定時に pace_affinity reason が出力される。"""
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity())
        result = PaceAdaptabilityScorer().score(profile, AVERAGE, 1600)
        assert any(r.code == "pace_affinity" for r in result.reasons)

    def test_non_fallback_description_references_past_runs(self) -> None:
        """好走データあり（is_fallback=False）の説明文は「過去の好走は」を含む。"""
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity(is_fallback=False))
        result = PaceAdaptabilityScorer().score(profile, AVERAGE, 1600)
        reason = next(r for r in result.reasons if r.code == "pace_affinity")
        assert "過去の好走は" in reason.description

    def test_fallback_description_notes_insufficient_data(self) -> None:
        """好走データ不足（is_fallback=True）の説明文は補完を示すメッセージを含む。"""
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity(is_fallback=True))
        result = PaceAdaptabilityScorer().score(profile, AVERAGE, 1600)
        reason = next(r for r in result.reasons if r.code == "pace_affinity")
        assert "過去好走データが少ない" in reason.description

    def test_pai_is_blended_50_50_with_affinity_score(self) -> None:
        """PAI = (base_pai × 0.5) + (affinity_score × 0.5) のブレンドを検証する。

        ESCAPE + AVERAGE(50.0): preferred=55, gap=5 → rpci_penalty=25
        base_pai = 100 - 25 = 75.0
        predicted_level=AVERAGE → affinity_score=50
        blended = (75 × 0.5) + (50 × 0.5) = 62.5
        """
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity())
        result = PaceAdaptabilityScorer().score(profile, AVERAGE, 1600)
        assert result.pai == pytest.approx(62.5, abs=0.1)

    def test_very_slow_specialist_not_unfavorable_when_forecast_is_slow(self) -> None:
        """好走が全て「かなり落ち着いた流れ」の馬は、想定が隣接する「落ち着いた
        流れ」でも「不利」判定にならない（隣接レベルへのにじみの回帰テスト）。

        実際に観測された事象: この組み合わせで「相性は不安」と表示され続けた
        馬が、実際のレースでは好走することが再三あった。
        """
        results = tuple(
            PaceAffinityRaceResult(
                race_key=RaceKey(f"202601{d:02d}05010101"),
                race_date=datetime.date(2026, 1, d),
                finish_pos=1,
                grade=None,
                rpci_actual=57.0,
                pci3_actual=None,
                pci_actual=None,
            )
            for d in (1, 2, 3)
        )
        affinity = build_horse_pace_affinity_profile(
            "H001", CLOSER, results, as_of=datetime.date(2026, 6, 1)
        )
        forecast_slow = _forecast(53.0, PaceLabel.SLOW)  # PaceSpeedLevel.SLOW 相当
        profile = HorsePaceProfile(1, CLOSER, pace_affinity=affinity)
        result = PaceAdaptabilityScorer().score(profile, forecast_slow, 1600)

        reason = next(r for r in result.reasons if r.code == "pace_affinity")
        assert "不安" not in reason.description
        assert result.fit_label != FitLabel.UNFAVORABLE
