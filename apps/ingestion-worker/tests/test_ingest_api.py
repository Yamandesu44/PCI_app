"""IngestApiClient のユニットテスト（httpx をモック注入）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import datetime

import httpx

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
    # httpx.Response.is_error は status_code >= 400 で True。Mock spec では自動生成されず
    # 既定で truthy な Mock になり _post のエラー分岐へ誤って入るため明示的に設定する。
    resp.is_error = status_code >= 400
    resp.text = ""
    client = Mock(spec=httpx.Client)
    client.post.return_value = resp
    client.delete.return_value = resp
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
                EntryRecord(
                    horse_no=1, frame_no=1, ketto_num="2023100001",
                    weight=460.0, jockey_code="0001", trainer_code="0001",
                ),
                EntryRecord(
                    horse_no=2, frame_no=1, ketto_num="2023100002",
                    weight=456.0, jockey_code="0002", trainer_code="0001",
                ),
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
            grade="G3",
            results=[
                ResultRecord(
                    horse_no=3, finish_pos=1, race_time_s=94.4, agari_3f_s=33.9,
                    corner_1=3, corner_2=3, corner_3=3, corner_4=3,
                    body_weight=486.0,
                ),
                ResultRecord(
                    horse_no=1, finish_pos=2, race_time_s=94.6, agari_3f_s=34.2, corner_4=2,
                ),
            ],
        )

    def test_sends_to_results_endpoint(self) -> None:
        http = _make_http_client(
            {"race_key": "2026061805010101", "rpci": 52.0, "pci3": 52.0, "formula_version": "v1"}
        )
        api = IngestApiClient("http://api", http_client=http)
        api.record_results(self._make_record())
        url = http.post.call_args.args[0]
        assert "/internal/ingest/results" in url

    def test_payload_includes_results(self) -> None:
        http = _make_http_client(
            {"race_key": "x", "rpci": 52.0, "pci3": 52.0, "formula_version": "pci-v1"}
        )
        api = IngestApiClient("http://api", http_client=http)
        api.record_results(self._make_record())
        payload = http.post.call_args.kwargs["json"]
        assert payload["grade"] == "G3"
        assert len(payload["results"]) == 2
        assert payload["results"][0]["finish_pos"] == 1
        assert payload["results"][0]["body_weight"] == 486.0

    def test_returns_rpci(self) -> None:
        http = _make_http_client(
            {"race_key": "x", "rpci": 53.5, "pci3": 52.0, "formula_version": "pci-v1"}
        )
        api = IngestApiClient("http://api", http_client=http)
        result = api.record_results(self._make_record())
        assert result["rpci"] == 53.5


class TestDeleteRace:
    def test_sends_to_delete_endpoint(self) -> None:
        http = _make_http_client({"accepted": 1})
        api = IngestApiClient("http://api", http_client=http)

        result = api.delete_race("2026062809011111")

        assert result == 1
        url = http.delete.call_args.args[0]
        assert "/internal/ingest/races/2026062809011111" in url


class TestLogBatch:
    def test_sends_to_log_endpoint(self) -> None:
        http = _make_http_client({"id": 42})
        api = IngestApiClient("http://api", http_client=http)

        log_id = api.log_batch(
            batch_date="2026-07-06",
            step="all",
            mode="fixture",
            started_at="2026-07-06T13:31:35+00:00",
            finished_at="2026-07-06T13:31:37+00:00",
            status="ok",
        )

        assert log_id == 42
        url = http.post.call_args.args[0]
        assert "/internal/ingest/log" in url
        payload = http.post.call_args.kwargs["json"]
        assert payload["batch_date"] == "2026-07-06"
        assert payload["status"] == "ok"

    def test_failure_is_swallowed_and_returns_zero(self) -> None:
        """API 側エラー（422 等）でもバッチ本体を止めないよう、例外を握りつぶし 0 を返す。"""
        http = _make_http_client({"detail": "invalid"}, status_code=422)
        api = IngestApiClient("http://api", http_client=http)

        log_id = api.log_batch(
            batch_date="2026-07-06",
            step="all",
            mode="fixture",
            started_at="2026-07-06T13:31:35+00:00",
            finished_at=None,
            status="running",
        )

        assert log_id == 0
