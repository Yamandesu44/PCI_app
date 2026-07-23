"""取り込み状況エンドポイント（/api/v1/ingest-status）の契約テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient

STATUS_KEYS = {
    "has_history",
    "last_success_at",
    "last_success_step",
    "last_attempt_failed",
    "days_since_last_success",
    "is_stale",
    "recent_failures",
    "has_incomplete_races",
    "incomplete_race_count",
    "recommended_sync_days_back",
    "incomplete_races",
    "race_metadata_date_from",
    "race_metadata_date_to",
    "has_missing_track_conditions",
    "missing_track_condition_count",
    "missing_track_condition_races",
}


def test_ingest_status_contract(client: TestClient) -> None:
    resp = client.get("/api/v1/ingest-status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == STATUS_KEYS


def test_ingest_status_reflects_recent_success(client: TestClient) -> None:
    """conftest の client フィクスチャは3時間前の成功ログを1件持つ。"""
    body = client.get("/api/v1/ingest-status").json()
    assert body["has_history"] is True
    assert body["last_success_step"] == "entries"
    assert body["last_attempt_failed"] is False
    assert body["is_stale"] is False
    # UTC日付の切り替わり直後は「3時間前」が前日になるため、0〜1日を直近とする。
    assert body["days_since_last_success"] in {0, 1}
    assert body["recent_failures"] == []
    assert body["has_incomplete_races"] is True
    assert body["incomplete_race_count"] == 1
    assert body["recommended_sync_days_back"] >= 10
    assert body["incomplete_races"][0]["race_key"] == "2026062005010101"
    assert body["race_metadata_date_from"]
    assert body["race_metadata_date_to"]


def test_openapi_exposes_ingest_status(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/ingest-status" in schema["paths"]
