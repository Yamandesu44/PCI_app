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
    "has_duplicate_races",
    "duplicate_race_group_count",
    "duplicate_race_groups",
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


def test_forecast_performance_contract_hides_internal_values(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/forecast-performance")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "date_from",
        "date_to",
        "period_days",
        "eligible_race_count",
        "sample_size",
        "coverage_rate",
        "hit_count",
        "hit_rate",
        "groups",
        "previous_period",
        "confidence_groups",
        "pace_matrix",
        "weekly_trend",
        "recent_misses",
    }
    assert body["period_days"] == 90
    assert body["eligible_race_count"] == 0
    assert body["sample_size"] == 0
    assert body["coverage_rate"] is None
    assert body["hit_rate"] is None
    assert [group["key"] for group in body["groups"]] == [
        "overall",
        "turf",
        "dirt",
    ]
    assert set(body["previous_period"]) == {
        "date_from",
        "date_to",
        "groups",
    }
    assert [group["key"] for group in body["previous_period"]["groups"]] == [
        "overall",
        "turf",
        "dirt",
    ]
    assert len(body["weekly_trend"]) == 8
    assert body["recent_misses"] == []
    assert [group["key"] for group in body["confidence_groups"]] == [
        "strong",
        "normal",
        "caution",
    ]
    assert [row["predicted_key"] for row in body["pace_matrix"]] == [
        "high",
        "average",
        "slow",
    ]
    assert [cell["key"] for cell in body["pace_matrix"][0]["cells"]] == [
        "high",
        "average",
        "slow",
    ]
    assert set(body["weekly_trend"][0]) == {
        "date_from",
        "date_to",
        "sample_size",
        "hit_count",
        "hit_rate",
    }
    assert "rpci" not in response.text.lower()
    assert "pci" not in response.text.lower()


def test_openapi_exposes_forecast_performance(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/forecast-performance" in schema["paths"]


def test_forecast_performance_accepts_supported_period(client: TestClient) -> None:
    response = client.get("/api/v1/forecast-performance?days=30")

    assert response.status_code == 200
    assert response.json()["period_days"] == 30


def test_forecast_performance_rejects_unsupported_period(client: TestClient) -> None:
    response = client.get("/api/v1/forecast-performance?days=60")

    assert response.status_code == 422


def test_forecast_misses_contract_hides_internal_values(client: TestClient) -> None:
    response = client.get(
        "/api/v1/forecast-performance/misses"
        "?days=30&track_type=%E8%8A%9D&predicted_label=%E5%B9%B3%E5%9D%87"
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "date_from",
        "date_to",
        "period_days",
        "total_count",
        "offset",
        "limit",
        "items",
    }
    assert body["period_days"] == 30
    assert body["total_count"] == 0
    assert body["items"] == []
    assert "rpci" not in response.text.lower()
    assert "pci" not in response.text.lower()


def test_forecast_misses_rejects_invalid_filter(client: TestClient) -> None:
    response = client.get(
        "/api/v1/forecast-performance/misses?actual_label=unknown"
    )

    assert response.status_code == 422
