"""IngestApiClient のユニットテスト（httpx をモック注入）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import datetime

import httpx
import pytest

from ingestion.ingest_api import IngestApiClient
from ingestion.models import (
    EntryRecord,
    HorseRecord,
    JockeyRecord,
    RaceEntriesRecord,
    RaceResultRecord,
    ResultRecord,
    TrainerRecord,
)


def _make_http_client(response_body: dict[str, Any], status_code: int = 200) -> Mock:
    resp = Mock(spec=httpx.Response)
    resp.json.return_value = response_body
    resp.raise_for_status.return_value = None
    resp.status_code = status_code
    client = Mock(spec=httpx.Client)
    client.post.return_value = resp
    return client


class TestUpsertHorses:
    def test_sends_correct_payload(self) -> None:
        http = _make_http_client({"accepted": 1})
        api = IngestApiClient("http://api", token="tok", http_client=http)
        horses = [HorseRecord(ketto_num="2023100001", name="テスト", sex="牡", birth_year=2023)]
        api.upsert_horses(horses)
        call_args = http.post.call_args
        assert "/internal/ingest/horses" in call_args.args[0]
        payload = call_args.kwargs["json"]
        assert payload[0]["ketto_num"] == "2023100001"
        assert payload[0]["name"] == "テスト"

    def test_returns_total_accepted(self) -> None:
        http = _make_http_client({"accepted": 3})
        api = IngestApiClient("http://api", http_client=http)
        horses = [HorseRecord(ketto_num=f"202310000{i}", name=f"馬{i}") for i in range(3)]
        result = api.upsert_horses(horses)
        assert result == 3

    def test_token_sent_in_header(self) -> None:
        http = _make_http_client({"accepted": 0})
        api = IngestApiClient("http://api", token="secret", http_client=http)
        api.upsert_jockeys([JockeyRecord(code="0001", name="騎手")])
        headers = http.post.call_args.kwargs["headers"]
        assert headers.get("X-Ingest-Token") == "secret"

    def test_no_token_header_when_empty(self) -> None:
        http = _make_http_client({"accepted": 0})
        api = IngestApiClient("http://api", token="", http_client=http)
        api.upsert_trainers([TrainerRecord(code="0001", name="調教師")])
        headers = http.post.call_args.kwargs["headers"]
        assert "X-Ingest-Token" not in headers


class TestRegisterEntries:
    def _make_record(self) -> RaceEntriesRecord:
        return RaceEntriesRecord(
            race_key="2026061805010101",
            race_date=datetime.date(2026, 6, 18),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=3,
            track_condition="良",
            weather="晴",
            entries=[
                EntryRecord(horse_no=1, frame_no=1, ketto_num="2023100001", weight=460.0, jockey_code="0001", trainer_code="0001"),
                EntryRecord(horse_no=2, frame_no=1, ketto_num="2023100002", weight=456.0, jockey_code="0002", trainer_code="0001"),
            ],
        )

    def test_sends_to_entries_endpoint(self) -> None:
        http = _make_http_client({"accepted": 2})
        api = IngestApiClient("http://api", http_client=http)
        api.register_entries(self._make_record())
        url = http.post.call_args.args[0]
        assert "/internal/ingest/entries" in url

    def test_payload_includes_race_key(self) -> None:
        http = _make_http_client({"accepted": 2})
        api = IngestApiClient("http://api", http_client=http)
        api.register_entries(self._make_record())
        payload = http.post.call_args.kwargs["json"]
        assert payload["race_key"] == "2026061805010101"

    def test_payload_includes_entries(self) -> None:
        http = _make_http_client({"accepted": 2})
        api = IngestApiClient("http://api", http_client=http)
        api.register_entries(self._make_record())
        payload = http.post.call_args.kwargs["json"]
        assert len(payload["entries"]) == 2

    def test_returns_accepted_count(self) -> None:
        http = _make_http_client({"accepted": 2})
        api = IngestApiClient("http://api", http_client=http)
        result = api.register_entries(self._make_record())
        assert result == 2


class TestRecordResults:
    def _make_record(self) -> RaceResultRecord:
        return RaceResultRecord(
            race_key="2026061805010101",
            track_condition="良",
            results=[
                ResultRecord(horse_no=3, finish_pos=1, race_time_s=94.4, agari_3f_s=33.9, corner_1=3, corner_2=3, corner_3=3, corner_4=3),
                ResultRecord(horse_no=1, finish_pos=2, race_time_s=94.6, agari_3f_s=34.2, corner_4=2),
            ],
        )

    def test_sends_to_results_endpoint(self) -> None:
        http = _make_http_client({"race_key": "2026061805010101", "rpci": 52.0, "pci3": 52.0, "formula_version": "pci-v1"})
        api = IngestApiClient("http://api", http_client=http)
        api.record_results(self._make_record())
        url = http.post.call_args.args[0]
        assert "/internal/ingest/results" in url

    def test_payload_includes_results(self) -> None:
        http = _make_http_client({"race_key": "x", "rpci": 52.0, "pci3": 52.0, "formula_version": "pci-v1"})
        api = IngestApiClient("http://api", http_client=http)
        api.record_results(self._make_record())
        payload = http.post.call_args.kwargs["json"]
        assert len(payload["results"]) == 2
        assert payload["results"][0]["finish_pos"] == 1

    def test_returns_rpci(self) -> None:
        http = _make_http_client({"race_key": "x", "rpci": 53.5, "pci3": 52.0, "formula_version": "pci-v1"})
        api = IngestApiClient("http://api", http_client=http)
        result = api.record_results(self._make_record())
        assert result["rpci"] == 53.5
