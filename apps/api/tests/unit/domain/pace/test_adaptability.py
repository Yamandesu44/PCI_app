"""PaceAdaptabilityScorer (PAI) 単体テスト + 不変条件プロパティテスト。"""

from __future__ import annotations

import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.adaptability import (
    DEFAULT_WEIGHTS,
    FitLabel,
    HorsePaceProfile,
    PaceAdaptabilityScorer,
    PaiWeights,
    pace_center,
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
STALKER = RunningStyleLabel.STALKER
FLEXIBLE = RunningStyleLabel.FLEXIBLE


def _forecast(value: float, label: PaceLabel) -> RpciForecast:
    return RpciForecast(
        value=value, label=label, confidence=0.7, model_version="rule-v1", reasons=()
    )


# pai-v4 はコース相対で判定する。既定 track_type="芝"。
# 振れの中心は neutral_rpci(51.85) + pace_center_offset_turf(-1.17) = 50.68。
SLOW = _forecast(56.0, PaceLabel.SLOW)
HIGH = _forecast(48.0, PaceLabel.HIGH)
AVERAGE = _forecast(pace_center("芝"), PaceLabel.AVERAGE)


class TestPaiCoreLogic:
    def test_escape_horse_matches_slow_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, ESCAPE), SLOW, 1600)
        assert result.fit_label == FitLabel.MATCHED
        assert result.pai >= DEFAULT_WEIGHTS.matched_threshold

    def test_escape_horse_unfavorable_in_high_pace(self) -> None:
        scorer = PaceAdaptabilityScorer()
        result = scorer.score(HorsePaceProfile(1, ESCAPE), HIGH, 1600)
        assert result.fit_label == FitLabel.UNFAVORABLE
        assert result.pai < DEFAULT_WEIGHTS.unfavorable_threshold

    def test_back_styles_stay_neutral_whatever_the_pace(self) -> None:
        """後方脚質はペース依存が小さいため常に中立（ADR-0010・pai-v3）。

        pai-v2 は追込に preferred=45.0 を与えていたが、ダート(分布46.5)では
        それが最高スコアになり、実際には最も走らない脚質(0.47x)を推していた。
        """
        scorer = PaceAdaptabilityScorer()
        for style in (STALKER, CLOSER):
            for fc in (SLOW, HIGH, AVERAGE):
                result = scorer.score(HorsePaceProfile(1, style), fc, 1600)
                assert result.fit_label == FitLabel.NEUTRAL

    def test_same_pace_gives_different_labels_per_track(self) -> None:
        """コース相対で判定する。同じRPCIでも芝とダートで意味が違う。

        RPCI 48.0 は芝では中心(50.68)より下、ダートでは中心(46.97)より上。
        pai-v2 は絶対値で判定していたため、この区別ができなかった。
        """
        scorer = PaceAdaptabilityScorer()
        fc = _forecast(48.0, PaceLabel.AVERAGE)

        turf = scorer.score(HorsePaceProfile(1, ESCAPE), fc, 1600, None, "芝")
        dirt = scorer.score(HorsePaceProfile(1, ESCAPE), fc, 1600, None, "ダート")

        assert turf.pai < 50.0  # 芝では向かい風
        assert dirt.pai > 50.0  # ダートでは追い風

    def test_flexible_horse_swings_less_than_escape(self) -> None:
        """自在馬はペースの影響を受けるが、逃げ馬より振れ幅が小さい。

        実測（2026-08-04）でも 自在は芝1.13x/ダート1.09x、逃げは1.21x/1.17x。
        """
        scorer = PaceAdaptabilityScorer()
        for fc in (SLOW, HIGH):
            flexible = scorer.score(HorsePaceProfile(1, FLEXIBLE), fc, 1600)
            escape = scorer.score(HorsePaceProfile(1, ESCAPE), fc, 1600)
            assert abs(flexible.pai - 50.0) < abs(escape.pai - 50.0)

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
        assert "pace_fit" in codes
        assert "pai" in codes

    def test_model_version_is_pai_v4(self) -> None:
        result = PaceAdaptabilityScorer().score(HorsePaceProfile(1, ESCAPE), SLOW, 1600)
        assert result.model_version == "pai-v4"

    def test_custom_weights_change_thresholds(self) -> None:
        strict = PaiWeights(matched_threshold=95.0)
        scorer = PaceAdaptabilityScorer(strict)
        # 中心ちょうどの逃げ馬は PAI=50。厳格閾値では合致しない。
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
        if result.pai >= DEFAULT_WEIGHTS.matched_threshold:
            assert result.fit_label == FitLabel.MATCHED
        elif result.pai < DEFAULT_WEIGHTS.unfavorable_threshold:
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

        pai-v4: ESCAPE + SLOW(56.0)、芝の中心50.68・半幅2.15・振れ幅10。
        deviation = (56.0 - 50.68) / 2.15 → 1.0 でクリップ
        base_pai = 50 + 1.0 × 10 = 60.0
        predicted_level=SLOW → affinity_score=50（_make_affinity の設定による）
        blended = (60 × 0.5) + (50 × 0.5) = 55.0
        """
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity())
        result = PaceAdaptabilityScorer().score(profile, SLOW, 1600)
        assert result.pai == pytest.approx(55.0, abs=0.1)

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

    def test_direct_evidence_at_non_preferred_level_is_mentioned(self) -> None:
        """ピーク(preferred_level)とは別レベルでも直接の好走実績があるとき、
        「ピークに集まっており」だけで済ませず、そのレベルでの実績にも触れる。

        実際に観測された事象: 好走がVERY_SLOWに集中する馬と、VERY_SLOWを
        ピークにしつつSLOWでも直接好走している馬の両方が、同一の説明文
        （「過去の好走はかなり落ち着いた流れに集まっており」）で始まりながら
        相性ラベルだけが異なっていた。後者は今回レベルでの実績自体が
        言及されず、読み手に「ピークだけで判定された」という誤解を与える。
        """
        results = tuple(
            PaceAffinityRaceResult(
                race_key=RaceKey(f"202601{d:02d}05010101"),
                race_date=datetime.date(2026, 1, d),
                finish_pos=1,
                grade=None,
                rpci_actual=rpci,
                pci3_actual=None,
                pci_actual=None,
            )
            for d, rpci in enumerate((57.0, 57.0, 57.0, 53.0, 53.0), start=1)
        )
        affinity = build_horse_pace_affinity_profile(
            "H001", CLOSER, results, as_of=datetime.date(2026, 6, 1)
        )
        assert affinity.preferred_level == PaceSpeedLevel.VERY_SLOW  # ピークは VERY_SLOW
        assert affinity.scores[PaceSpeedLevel.SLOW] >= 75  # SLOW 自体にも直接実績あり

        forecast_slow = _forecast(53.0, PaceLabel.SLOW)  # PaceSpeedLevel.SLOW 相当
        profile = HorsePaceProfile(1, CLOSER, pace_affinity=affinity)
        result = PaceAdaptabilityScorer().score(profile, forecast_slow, 1600)

        reason = next(r for r in result.reasons if r.code == "pace_affinity")
        assert "でも好走実績があり" in reason.description
        assert "落ち着いた流れでも好走実績があり" in reason.description


class TestPaceCenterOffset:
    """振れの中心を `neutral_rpci` から動かせること（pai-v3 の中心ずれ対策）。

    `neutral_rpci` は全履歴の3分位境界の中点だが、予測RPCIの分布はそこへ揃わない。
    ずれたままだと感応度の高い脚質だけが系統的に底上げ/底下げされ、pai-v2 の
    「脚質の定数効果をPAIへ埋め込む」誤りを別経路で再現する。
    """

    @staticmethod
    def _pai(weights: PaiWeights, rpci: float, track: str = "芝") -> float:
        scorer = PaceAdaptabilityScorer(weights)
        profile = HorsePaceProfile(horse_no=1, running_style=ESCAPE)
        forecast = _forecast(rpci, PaceLabel.AVERAGE)
        return scorer.score(profile, forecast, 1600, track_type=track).pai

    def test_defaults_are_the_measured_offsets(self) -> None:
        """pai-v4 の既定は実測から解いた中心合わせ値（ADR-2026-08-04）。"""
        assert PaiWeights().pace_center_offset_turf == -1.17
        assert PaiWeights().pace_center_offset_dirt == 0.47
        # 補正後の中心ちょうどで PAI=50。
        assert self._pai(PaiWeights(), pace_center("芝")) == 50.0

    def test_zero_offset_restores_the_uncentered_centre(self) -> None:
        w = PaiWeights(pace_center_offset_turf=0.0)
        # 中心が neutral_rpci(51.85) へ戻る。
        assert self._pai(w, 51.85) == pytest.approx(50.0, abs=0.1)
        # 補正後の中心(50.68)は、そこより下＝逃げに不利側へ振れる。
        assert self._pai(w, pace_center("芝")) < 50.0

    def test_turf_and_dirt_offsets_are_independent(self) -> None:
        w = PaiWeights(pace_center_offset_turf=-1.17, pace_center_offset_dirt=0.47)
        # ダート側のオフセットは芝の判定に影響しない。
        assert self._pai(w, pace_center("ダート", w), track="ダート") == pytest.approx(
            50.0, abs=0.1
        )
        assert self._pai(w, pace_center("芝", w), track="芝") == pytest.approx(50.0, abs=0.1)


class TestStyleReasonDirection:
    """展開の向き不向きを表す文言が、実際の向きと一致すること。

    pai-v3 で `_style_reason` の引数が「減点」から「加点」へ変わったのに閾値が
    旧スケール（0〜100の減点）のまま残っており、**最も不利な馬にも
    「持ち味を出しやすい流れです」と出していた**。符号を見ずに上限だけで
    分岐していたため、負の加点（＝不利）が全て最初の枝へ落ちていた。
    """

    @staticmethod
    def _pace_reason(style: RunningStyleLabel, fc: RpciForecast) -> str:
        result = PaceAdaptabilityScorer().score(HorsePaceProfile(1, style), fc, 1600)
        return next(r for r in result.reasons if r.code == "pace_fit").description

    def test_favourable_pace_says_so(self) -> None:
        assert "持ち味を出しやすい" in self._pace_reason(ESCAPE, SLOW)

    def test_unfavourable_pace_says_so(self) -> None:
        text = self._pace_reason(ESCAPE, HIGH)
        assert "力を出しにくい" in text
        assert "持ち味を出しやすい" not in text

    def test_neutral_pace_says_neither(self) -> None:
        text = self._pace_reason(ESCAPE, AVERAGE)
        assert "極端な有利・不利は見ていません" in text

    def test_pace_insensitive_styles_always_read_neutral(self) -> None:
        """感応度0の差し・追込は、どの流れでも向き不向きを主張しない。"""
        for fc in (SLOW, HIGH, AVERAGE):
            assert "極端な有利・不利は見ていません" in self._pace_reason(CLOSER, fc)

    def test_wording_is_stable_across_swing_settings(self) -> None:
        """振れ幅を変えても文言の出方は変わらない（比で判定しているため）。"""
        for swing in (5.0, 10.0, 25.0):
            scorer = PaceAdaptabilityScorer(PaiWeights(pace_swing=swing))
            result = scorer.score(HorsePaceProfile(1, ESCAPE), HIGH, 1600)
            text = next(r for r in result.reasons if r.code == "pace_fit").description
            assert "力を出しにくい" in text


class TestLowEvidence:
    """「中立」が展開の判定なのか判断材料不足なのかを、ラベルと別に持つ。

    実測（2026-08-04・500レース）で「中立」の好走率が「不利」を下回った。原因は
    過去データが無い馬が中立へ集中すること。感応度0の差しなら PAI は
    {40, 45, 50, 52.5} の4値だけになり、5段階中4段階が中立へ落ちる。
    ラベルだけでは区別できないので別フラグにする（docs/DECISIONS.md ADR-2026-08-04）。
    """

    def test_no_affinity_profile_is_low_evidence(self) -> None:
        result = PaceAdaptabilityScorer().score(HorsePaceProfile(1, ESCAPE), SLOW, 1600)
        assert result.low_evidence is True

    def test_fallback_affinity_is_low_evidence(self) -> None:
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity(is_fallback=True))
        result = PaceAdaptabilityScorer().score(profile, SLOW, 1600)
        assert result.low_evidence is True

    def test_real_affinity_is_not_low_evidence(self) -> None:
        profile = HorsePaceProfile(1, ESCAPE, pace_affinity=_make_affinity(is_fallback=False))
        result = PaceAdaptabilityScorer().score(profile, SLOW, 1600)
        assert result.low_evidence is False

    def test_flag_is_independent_of_the_label(self) -> None:
        """判断材料の有無とラベルは別軸。合致でも材料不足はありうる。"""
        seen = set()
        for fc in (SLOW, HIGH, AVERAGE):
            for affinity in (None, _make_affinity(is_fallback=True), _make_affinity()):
                r = PaceAdaptabilityScorer().score(
                    HorsePaceProfile(1, ESCAPE, pace_affinity=affinity), fc, 1600
                )
                seen.add((r.fit_label, r.low_evidence))
        labels_with_low = {lab for lab, low in seen if low}
        assert len(labels_with_low) > 1, "材料不足が特定のラベルだけに現れるなら別軸ではない"
