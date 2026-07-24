"""mykeibadbラップ利用率診断の単体テスト（実DB不要）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_mykeibadb_client import _Connection  # noqa: E402

from ingestion.client.mykeibadb_client import MyKeibaDbClient  # noqa: E402
from ingestion.diagnose_lap_coverage import _seconds, diagnose  # noqa: E402


def _race(
    race_no: int,
    *,
    track_code: int = 17,
    distance: int = 1200,
    s3: object = 352,
    l3: object = 358,
    laps: list[object] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "DATA_KUBUN": "7",
        "KAISAI_NEN": 2026,
        "KAISAI_GAPPI": "0621",
        "KEIBAJO_CODE": 5,
        "KAISAI_KAI": 3,
        "KAISAI_NICHIME": 4,
        "RACE_BANGO": race_no,
        "KYORI": distance,
        "TRACK_CODE": track_code,
        "ZENHAN_3F": s3,
        "KOHAN_3F": l3,
    }
    for index, value in enumerate(laps or [], start=1):
        row[f"LAP_TIME{index}"] = value
    return row


class _LapConnection(_Connection):
    ra = [
        _race(1, laps=[121, 119, 118, 117, 116, 115]),
        _race(2),
        _race(
            3,
            track_code=24,
            distance=1600,
            s3=0,
            laps=[121, 119, 118, 117, 116, 115, 114, 113],
        ),
        _race(4, track_code=52, distance=2850),
        # 同一レースの低品質な更新行は分母を増やさず、情報量の多い行を残す。
        _race(1, s3=0, l3=0),
        {**_race(5), "DATA_KUBUN": "2"},
    ]


def test_diagnose_groups_flat_races_and_deduplicates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = MyKeibaDbClient(connection=_LapConnection())

    report = diagnose(
        "20260620",
        "20260622",
        min_races=2,
        min_coverage=0.5,
        client=client,
    )

    assert report.duplicate_rows == 1
    assert report.ignored_nonfinal == 1
    assert report.ignored_non_jra_or_obstacle == 1
    assert len(report.buckets) == 2
    by_track = {bucket.track_type: bucket for bucket in report.buckets}
    turf = by_track["芝"]
    dirt = by_track["ダート"]
    assert (turf.track_type, turf.distance_band, turf.total) == ("芝", "1399m以下", 2)
    assert (turf.pair, turf.complete_intervals) == (2, 1)
    assert (dirt.track_type, dirt.distance_band, dirt.total) == (
        "ダート",
        "1400-1799m",
        1,
    )
    assert (dirt.s3, dirt.l3, dirt.complete_intervals) == (0, 1, 1)

    payload = report.to_dict(min_races=2, min_coverage=0.5)
    buckets = payload["buckets"]
    assert isinstance(buckets, list)
    turf_payload = next(
        item for item in buckets if isinstance(item, dict) and item["track_type"] == "芝"
    )
    assert isinstance(turf_payload, dict)
    assert turf_payload["s3_l3_ready"] is True
    assert turf_payload["interval_ready"] is True
    out = capsys.readouterr().out
    assert "区間ラップ可" in out


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (352, 35.2),
        ("35.8", 35.8),
        ("000", None),
        ("999", None),
        (None, None),
    ],
)
def test_seconds_accepts_tenths_and_seconds(raw: object, expected: float | None) -> None:
    assert _seconds(raw, 25.0, 50.0) == expected


def test_diagnose_rejects_invalid_thresholds() -> None:
    client = MyKeibaDbClient(connection=_LapConnection())

    with pytest.raises(ValueError, match="min_coverage"):
        diagnose(
            "20260620",
            "20260622",
            min_races=1,
            min_coverage=1.1,
            client=client,
        )
