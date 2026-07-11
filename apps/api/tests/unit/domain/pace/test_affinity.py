from __future__ import annotations

import datetime

from pci.domain.pace.affinity import (
    PaceAffinityRaceResult,
    PaceSpeedLevel,
    affinity_label,
    build_horse_pace_affinity_profile,
    is_good_run,
    pace_level_from_index,
)
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.race_key import RaceKey


def _result(
    race_key: str,
    finish_pos: int | None,
    rpci: float | None,
    *,
    race_date: datetime.date = datetime.date(2026, 1, 1),
    grade: str | None = None,
    pci3: float | None = None,
    pci: float | None = None,
) -> PaceAffinityRaceResult:
    return PaceAffinityRaceResult(
        race_key=RaceKey(race_key),
        race_date=race_date,
        finish_pos=finish_pos,
        grade=grade,
        rpci_actual=rpci,
        pci3_actual=pci3,
        pci_actual=pci,
    )


class TestPaceLevelFromIndex:
    def test_boundaries(self) -> None:
        assert pace_level_from_index(46.9) == PaceSpeedLevel.VERY_HIGH
        assert pace_level_from_index(47.0) == PaceSpeedLevel.HIGH
        assert pace_level_from_index(50.0) == PaceSpeedLevel.AVERAGE
        assert pace_level_from_index(52.1) == PaceSpeedLevel.SLOW
        assert pace_level_from_index(55.1) == PaceSpeedLevel.VERY_SLOW


class TestNeighborBleed:
    """隣接ペースレベルへの適性のにじみ（誤って「不安」判定されないための回帰テスト）。"""

    def test_very_slow_specialist_is_not_unfavorable_for_slow(self) -> None:
        """過去の好走が全て「かなり落ち着いた流れ」でも、「落ち着いた流れ」を
        直接の好走実績ゼロ＝スコア0（＝不安）と誤判定しない。

        実際に観測された事象: 好走がVERY_SLOWに集中する馬について、想定ペースが
        隣接するSLOWのとき「相性は『不安』」と表示され、その馬が実際には好走する
        ことが再三あった。VERY_SLOWとSLOWは連続的なペース値の隣接区分であり、
        直接の実績がないだけで0点にするのは不適切。
        """
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (
                _result("2026010105010101", 1, 56.0),
                _result("2026020105010101", 1, 57.0),
                _result("2026030105010101", 1, 58.0),
            ),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.preferred_level == PaceSpeedLevel.VERY_SLOW
        assert profile.scores[PaceSpeedLevel.VERY_SLOW] == 100
        # 隣接(SLOW)は「にじみ」で中立圏(40)まで持ち上がり、「不安」(<40)を回避する
        assert profile.scores[PaceSpeedLevel.SLOW] >= 40
        assert affinity_label(profile.scores[PaceSpeedLevel.SLOW]) != "不安"
        # 2ホップ離れたレベルにはにじまない
        assert profile.scores[PaceSpeedLevel.AVERAGE] == 0
        assert profile.scores[PaceSpeedLevel.HIGH] == 0
        assert profile.scores[PaceSpeedLevel.VERY_HIGH] == 0

    def test_bleed_does_not_reach_two_hops_away(self) -> None:
        """にじみは直接隣接するレベルのみ。2ホップ以上先には広がらない。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, 45.0),),  # VERY_HIGH
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.scores[PaceSpeedLevel.VERY_HIGH] == 100
        assert profile.scores[PaceSpeedLevel.HIGH] > 0       # 隣接
        assert profile.scores[PaceSpeedLevel.AVERAGE] == 0   # 2ホップ
        assert profile.scores[PaceSpeedLevel.SLOW] == 0
        assert profile.scores[PaceSpeedLevel.VERY_SLOW] == 0


class TestHorsePaceAffinityProfile:
    def test_uses_only_good_runs(self) -> None:
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (
                _result("2026010105010101", 1, 48.0),
                _result("2026010205010101", 6, 56.0),
            ),
            as_of=datetime.date(2026, 6, 1),
        )

        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.HIGH
        assert profile.scores[PaceSpeedLevel.HIGH] == 100
        assert profile.scores[PaceSpeedLevel.VERY_SLOW] == 0

    def test_graded_fifth_is_good_run(self) -> None:
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.STALKER,
            (_result("2026010105010101", 5, 46.0, grade="G3"),),
            as_of=datetime.date(2026, 6, 1),
        )

        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.VERY_HIGH

    def test_falls_back_to_running_style_when_sample_is_empty(self) -> None:
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.ESCAPE,
            (_result("2026010105010101", 8, 48.0),),
            as_of=datetime.date(2026, 6, 1),
        )

        assert profile.sample_size == 0
        assert profile.is_fallback is True
        assert profile.preferred_level == PaceSpeedLevel.VERY_SLOW
        assert profile.scores[PaceSpeedLevel.SLOW] == 55

    def test_uses_pci3_when_rpci_is_none(self) -> None:
        """rpci_actual が None のとき pci3_actual を代替ペース指標として使う。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, None, pci3=46.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.VERY_HIGH

    def test_recency_weight_medium_old(self) -> None:
        """181〜365 日前の好走は weight 0.9 でサンプルに含まれる。"""
        as_of = datetime.date(2026, 6, 28)
        race_date = as_of - datetime.timedelta(days=200)
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, 48.0, race_date=race_date),),
            as_of=as_of,
        )
        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.HIGH

    def test_recency_weight_old(self) -> None:
        """366〜730 日前の好走は weight 0.75 でサンプルに含まれる。"""
        as_of = datetime.date(2026, 6, 28)
        race_date = as_of - datetime.timedelta(days=500)
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, 54.0, race_date=race_date),),
            as_of=as_of,
        )
        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.SLOW

    def test_recency_weight_very_old(self) -> None:
        """730 日超の好走は weight 0.6 でサンプルに含まれる。"""
        as_of = datetime.date(2026, 6, 28)
        race_date = as_of - datetime.timedelta(days=800)
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, 48.0, race_date=race_date),),
            as_of=as_of,
        )
        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.HIGH

    def test_front_fallback_scores(self) -> None:
        """FRONT 脚質のフォールバックスコアが平均・スローに強い。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.FRONT,
            (_result("2026010105010101", 8, 48.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.is_fallback is True
        assert profile.scores[PaceSpeedLevel.SLOW] == 55
        assert profile.scores[PaceSpeedLevel.AVERAGE] == 55
        assert profile.scores[PaceSpeedLevel.VERY_HIGH] == 30

    def test_stalker_fallback_scores(self) -> None:
        """STALKER 脚質のフォールバックスコアが速い流れに強い。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.STALKER,
            (_result("2026010105010101", 8, 48.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.is_fallback is True
        assert profile.scores[PaceSpeedLevel.HIGH] == 55
        assert profile.preferred_level == PaceSpeedLevel.HIGH


class TestAffinityLabel:
    def test_all_levels(self) -> None:
        assert affinity_label(75) == "高相性"
        assert affinity_label(100) == "高相性"
        assert affinity_label(74) == "合致"
        assert affinity_label(55) == "合致"
        assert affinity_label(54) == "中立"
        assert affinity_label(40) == "中立"
        assert affinity_label(39) == "不安"
        assert affinity_label(0) == "不安"


class TestIsGoodRun:
    def test_none_finish_pos_returns_false(self) -> None:
        assert is_good_run(None, None) is False
        assert is_good_run(None, "G1") is False


class TestEvidenceEdgeCases:
    def test_good_run_with_no_pace_index_is_excluded(self) -> None:
        """好走でも rpci/pci3/pci_actual が全て None なら evidence に含まれない。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (
                _result("2026010105010101", 1, None),  # 好走だが pace index なし
                _result("2026010205010101", 1, 48.0),  # 通常の好走
            ),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.sample_size == 1  # None のエントリは除外される

    def test_pci_actual_used_when_rpci_and_pci3_none(self) -> None:
        """rpci_actual / pci3_actual が共に None のとき pci_actual を代替として使う。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 1, None, pci3=None, pci=48.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.sample_size == 1
        assert profile.preferred_level == PaceSpeedLevel.HIGH


class TestConfidenceThresholds:
    def test_confidence_high_with_three_samples(self) -> None:
        """3 サンプルのとき confidence = 0.8。"""
        results = tuple(
            _result(f"202601{i:02d}05010101", 1, 48.0) for i in range(1, 4)
        )
        profile = build_horse_pace_affinity_profile(
            "H001", RunningStyleLabel.CLOSER, results, as_of=datetime.date(2026, 6, 1)
        )
        assert profile.sample_size == 3
        assert profile.confidence == 0.8

    def test_confidence_max_with_five_samples(self) -> None:
        """5 サンプル以上のとき confidence = 1.0。"""
        results = tuple(
            _result(f"202601{i:02d}05010101", 1, 48.0) for i in range(1, 6)
        )
        profile = build_horse_pace_affinity_profile(
            "H001", RunningStyleLabel.CLOSER, results, as_of=datetime.date(2026, 6, 1)
        )
        assert profile.sample_size == 5
        assert profile.confidence == 1.0


class TestFallbackStylesCoverage:
    """CLOSER / FLEXIBLE 脚質のフォールバックスコアを検証する。"""

    def test_closer_fallback_scores(self) -> None:
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.CLOSER,
            (_result("2026010105010101", 8, 48.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.is_fallback is True
        assert profile.scores[PaceSpeedLevel.VERY_HIGH] == 60
        assert profile.scores[PaceSpeedLevel.HIGH] == 55
        assert profile.preferred_level == PaceSpeedLevel.VERY_HIGH

    def test_flexible_fallback_uses_default_scores(self) -> None:
        """FLEXIBLE 脚質はデフォルトフォールバック（全レベル 40）になる。"""
        profile = build_horse_pace_affinity_profile(
            "H001",
            RunningStyleLabel.FLEXIBLE,
            (_result("2026010105010101", 8, 48.0),),
            as_of=datetime.date(2026, 6, 1),
        )
        assert profile.is_fallback is True
        assert all(v == 40 for v in profile.scores.values())
