"""過去成績から距離適性と道悪傾向を組み立てる。"""

from __future__ import annotations

from dataclasses import dataclass

_OFF_TRACK_CONDITIONS = ("稍重", "重", "不良")
_MIN_DISTANCE_GOOD_RUNS = 2
_MIN_TRACK_RUNS = 3
_TRACK_COMPARISON_DISTANCE_GAP_M = 400
_OFF_TRACK_WEAKNESS_GAP = 0.30
_DISTANCE_MATCH_TOLERANCE_M = 200


@dataclass(frozen=True)
class CourseAptitudeRaceResult:
    """コース適性の判定に使う確定済みの過去走。"""

    distance_m: int
    track_type: str
    track_condition: str | None
    finish_pos: int | None
    field_size: int


@dataclass(frozen=True)
class CourseAptitudeProfile:
    """PAIへ渡す距離・馬場適性と、その判定標本数。"""

    distance_aptitude_m: int | None
    weak_on_off_track: bool
    distance_sample_size: int
    good_track_sample_size: int
    off_track_sample_size: int


def build_course_aptitude_profile(
    results: tuple[CourseAptitudeRaceResult, ...],
    *,
    target_track_type: str,
    target_distance_m: int,
) -> CourseAptitudeProfile:
    """同一馬場種別の過去成績から、保守的にコース適性を推定する。

    距離適性は上位4分の1相当（または3着以内）の好走が2件以上ある場合だけ算出し、
    今回距離に最も近い好走距離を基準にする。複数距離での好走を中央値へ潰さないためである。
    道悪弱点は今回距離の前後400m以内にある良・道悪各3件以上を比較し、
    頭数差を補正した着順評価が明確に低い場合だけ立てる。
    """

    comparable = tuple(
        result
        for result in results
        if result.track_type == target_track_type and _has_valid_result(result)
    )
    good_runs = tuple(result for result in comparable if _is_good_run(result))
    closest_good_distance = (
        min(
            (result.distance_m for result in good_runs),
            key=lambda distance_m: (abs(distance_m - target_distance_m), distance_m),
        )
        if len(good_runs) >= _MIN_DISTANCE_GOOD_RUNS
        else None
    )
    distance_aptitude_m = (
        target_distance_m
        if closest_good_distance is not None
        and abs(closest_good_distance - target_distance_m) <= _DISTANCE_MATCH_TOLERANCE_M
        else closest_good_distance
    )

    track_comparable = tuple(
        result
        for result in comparable
        if abs(result.distance_m - target_distance_m) <= _TRACK_COMPARISON_DISTANCE_GAP_M
    )
    good_track = tuple(
        result for result in track_comparable if result.track_condition == "良"
    )
    off_track = tuple(
        result
        for result in track_comparable
        if result.track_condition in _OFF_TRACK_CONDITIONS
    )
    weak_on_off_track = False
    if len(good_track) >= _MIN_TRACK_RUNS and len(off_track) >= _MIN_TRACK_RUNS:
        good_score = _average_performance(good_track)
        off_score = _average_performance(off_track)
        weak_on_off_track = good_score - off_score >= _OFF_TRACK_WEAKNESS_GAP

    return CourseAptitudeProfile(
        distance_aptitude_m=distance_aptitude_m,
        weak_on_off_track=weak_on_off_track,
        distance_sample_size=len(good_runs),
        good_track_sample_size=len(good_track),
        off_track_sample_size=len(off_track),
    )


def _has_valid_result(result: CourseAptitudeRaceResult) -> bool:
    return (
        result.finish_pos is not None
        and result.field_size >= 2
        and 1 <= result.finish_pos <= result.field_size
    )


def _is_good_run(result: CourseAptitudeRaceResult) -> bool:
    assert result.finish_pos is not None
    return result.finish_pos <= 3 or (result.finish_pos - 1) / (result.field_size - 1) <= 0.25


def _average_performance(results: tuple[CourseAptitudeRaceResult, ...]) -> float:
    scores = [
        (result.field_size - result.finish_pos) / (result.field_size - 1)
        for result in results
        if result.finish_pos is not None
    ]
    return sum(scores) / len(scores)
