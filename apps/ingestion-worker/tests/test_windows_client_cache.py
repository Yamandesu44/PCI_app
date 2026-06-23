"""WindowsJvLinkClient の取得キャッシュを JV-Link なしで検証する。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.client.windows_client import WindowsJvLinkClient


def _race_record(spec: str, race_date: str) -> str:
    return f"{spec}{' ' * 9}{race_date}{' ' * 20}"


def _client_with_records(records: list[str], calls: list[tuple[Any, ...]]) -> WindowsJvLinkClient:
    client = WindowsJvLinkClient.__new__(WindowsJvLinkClient)
    client._record_cache = {}

    def fake_iter_records(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))
        yield from records

    client._iter_records = fake_iter_records  # type: ignore[method-assign]
    return client


def test_race_records_are_opened_once_for_ra_and_se() -> None:
    calls: list[tuple[Any, ...]] = []
    client = _client_with_records(
        [
            _race_record("RA", "20260613"),
            _race_record("SE", "20260613"),
            _race_record("SE", "20260614"),
            _race_record("RA", "20260615"),
        ],
        calls,
    )

    ra = list(client.iter_ra_records("20260613", "20260614"))
    se = list(client.iter_se_records("20260613", "20260614"))

    assert [r[:2] for r in ra] == ["RA"]
    assert [r[:2] for r in se] == ["SE", "SE"]
    assert len(calls) == 1


def test_diff_records_are_opened_once_for_all_masters() -> None:
    calls: list[tuple[Any, ...]] = []
    client = _client_with_records(["UMxxxxx", "KSxxxxx", "CHxxxxx"], calls)

    assert list(client.iter_um_records()) == ["UMxxxxx"]
    assert list(client.iter_ks_records()) == ["KSxxxxx"]
    assert list(client.iter_ch_records()) == ["CHxxxxx"]
    assert len(calls) == 1
