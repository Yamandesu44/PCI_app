"""JV-Link option 診断コマンドのユニットテスト（JV-Link 不要）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.probe_race_options import _date_candidates, _race_date


def test_race_date_reads_jv_race_key_date() -> None:
    record = f"RA{' ' * 9}20260627{' ' * 20}"

    assert _race_date(record) == "20260627"


def test_race_date_returns_empty_for_short_record() -> None:
    assert _race_date("RA") == ""


def test_date_candidates_include_base_date_and_past_dates() -> None:
    assert _date_candidates("20260624", days_back=2) == [
        "20260624",
        "20260623",
        "20260622",
    ]
