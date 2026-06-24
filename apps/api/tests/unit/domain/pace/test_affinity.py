from __future__ import annotations

import datetime

from pci.domain.pace.affinity import (
    PaceAffinityRaceResult,
    PaceSpeedLevel,
    build_horse_pace_affinity_profile,
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
