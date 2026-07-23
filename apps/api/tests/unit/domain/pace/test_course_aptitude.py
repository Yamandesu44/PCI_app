"""過去成績から作るコース適性プロファイルの単体テスト。"""

from pci.domain.pace.course_aptitude import (
    CourseAptitudeRaceResult,
    build_course_aptitude_profile,
)


def _result(
    distance_m: int,
    finish_pos: int | None,
    *,
    track_type: str = "芝",
    track_condition: str | None = "良",
    field_size: int = 12,
) -> CourseAptitudeRaceResult:
    return CourseAptitudeRaceResult(
        distance_m=distance_m,
        track_type=track_type,
        track_condition=track_condition,
        finish_pos=finish_pos,
        field_size=field_size,
    )


class TestDistanceAptitude:
    def test_uses_closest_good_distance_on_same_track_type(self) -> None:
        profile = build_course_aptitude_profile(
            (
                _result(1200, 1),
                _result(1600, 3),
                _result(2400, 10),
                _result(2000, 1, track_type="ダート"),
            ),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.distance_aptitude_m == 1600
        assert profile.distance_sample_size == 2

    def test_does_not_infer_distance_from_single_good_run(self) -> None:
        profile = build_course_aptitude_profile(
            (_result(1200, 1), _result(1600, 8)),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.distance_aptitude_m is None
        assert profile.distance_sample_size == 1

    def test_treats_adjacent_distance_as_matching(self) -> None:
        profile = build_course_aptitude_profile(
            (_result(1400, 1), _result(1400, 2)),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.distance_aptitude_m == 1600

    def test_ignores_invalid_results(self) -> None:
        profile = build_course_aptitude_profile(
            (
                _result(1200, None),
                _result(1400, 0),
                _result(1600, 13),
                _result(1800, 1, field_size=1),
            ),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.distance_aptitude_m is None
        assert profile.distance_sample_size == 0


class TestOffTrackAptitude:
    def test_marks_weak_when_off_track_performance_is_clearly_lower(self) -> None:
        profile = build_course_aptitude_profile(
            (
                _result(1600, 1, track_condition="良"),
                _result(1800, 2, track_condition="良"),
                _result(1400, 1, track_condition="良"),
                _result(1600, 9, track_condition="重"),
                _result(1800, 10, track_condition="稍重"),
                _result(1400, 9, track_condition="不良"),
            ),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.weak_on_off_track is True
        assert profile.good_track_sample_size == 3
        assert profile.off_track_sample_size == 3

    def test_does_not_mark_weak_when_samples_are_insufficient(self) -> None:
        profile = build_course_aptitude_profile(
            (
                _result(1600, 1, track_condition="良"),
                _result(1800, 2, track_condition="良"),
                _result(1600, 9, track_condition="重"),
                _result(1600, 10, track_condition="不良"),
                _result(1400, 9, track_condition="稍重"),
            ),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.weak_on_off_track is False
        assert profile.good_track_sample_size == 2
        assert profile.off_track_sample_size == 3

    def test_excludes_distant_runs_from_track_comparison(self) -> None:
        profile = build_course_aptitude_profile(
            (
                _result(1600, 1, track_condition="良"),
                _result(1800, 2, track_condition="良"),
                _result(2400, 9, track_condition="重"),
                _result(2600, 10, track_condition="不良"),
            ),
            target_track_type="芝",
            target_distance_m=1600,
        )

        assert profile.weak_on_off_track is False
        assert profile.off_track_sample_size == 0
