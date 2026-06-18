"""レース API 契約テスト（TestClient + スキーマ契約）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.contract.conftest import CONFIRMED_KEY, UPCOMING_KEY

FORECAST_KEYS = {
    "race_key",
    "predicted_rpci",
    "pace_label",
    "confidence",
    "model_version",
    "scenario_headline",
    "scenario_detail",
    "front_runners",
    "beneficiaries",
    "horses",
    "forecast_reasons",
}

HORSE_KEYS = {"horse_no", "running_style", "pai", "fit_label", "reasons"}

RACE_DETAIL_KEYS = {
    "race_key",
    "race_date",
    "jyo_cd",
    "distance_m",
    "track_type",
    "status",
    "field_size",
    "track_condition",
    "weather",
    "grade",
    "race_class",
    "rpci_actual",
    "pci3_actual",
    "entries",
}

PACE_ANALYSIS_KEYS = {
    "race_key",
    "formula_version",
    "field_size",
    "sample_size",
    "rpci_actual",
    "pci3_actual",
    "horses",
    "reasons",
}

PACE_ANALYSIS_HORSE_KEYS = {
    "horse_no",
    "finish_pos",
    "running_style",
    "pci",
    "agari_3f_s",
    "is_pci3_contributor",
}


class TestForecastEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast")
        assert resp.status_code == 200

    def test_response_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert set(body.keys()) == FORECAST_KEYS
        assert body["race_key"] == UPCOMING_KEY
        assert body["model_version"] == "rule-v1"
        assert body["pace_label"] in ("ハイ", "平均", "スロー")
        assert 35.0 <= body["predicted_rpci"] <= 65.0

    def test_horses_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert len(body["horses"]) == 6
        for horse in body["horses"]:
            assert set(horse.keys()) == HORSE_KEYS
            assert 0.0 <= horse["pai"] <= 100.0
            assert horse["fit_label"] in ("合致", "中立", "不利")
            assert horse["reasons"], "説明可能性: reasons は必須"

    def test_scenario_present(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert body["scenario_headline"]
        assert body["scenario_detail"]

    def test_unknown_race_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races/9999999999999999/forecast")
        assert resp.status_code == 404
        assert "見つかりません" in resp.json()["detail"]

    def test_malformed_race_key_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races/abc/forecast")
        assert resp.status_code == 422


class TestRaceDetailEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/races/{CONFIRMED_KEY}")
        assert resp.status_code == 200

    def test_response_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{CONFIRMED_KEY}").json()
        assert set(body.keys()) == RACE_DETAIL_KEYS
        assert body["race_key"] == CONFIRMED_KEY
        assert body["status"] == "result"
        assert body["rpci_actual"] is not None
        assert body["pci3_actual"] is not None

    def test_entries_have_pci_after_result(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{CONFIRMED_KEY}").json()
        assert len(body["entries"]) == 3
        for e in body["entries"]:
            assert e["pci_actual"] is not None
            assert e["finish_pos"] is not None

    def test_unknown_race_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races/9999999999999999")
        assert resp.status_code == 404


class TestPaceAnalysisEndpoint:
    def test_returns_200_for_confirmed(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/races/{CONFIRMED_KEY}/pace-analysis")
        assert resp.status_code == 200

    def test_response_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{CONFIRMED_KEY}/pace-analysis").json()
        assert set(body.keys()) == PACE_ANALYSIS_KEYS
        assert body["race_key"] == CONFIRMED_KEY
        assert body["formula_version"] == "pci-v1"  # PCI 系は formula_version 必須
        assert body["sample_size"] == 3
        assert body["rpci_actual"] is not None
        assert body["pci3_actual"] is not None
        assert body["reasons"], "説明可能性: reasons は必須"

    def test_horses_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{CONFIRMED_KEY}/pace-analysis").json()
        assert len(body["horses"]) == 3
        assert [h["finish_pos"] for h in body["horses"]] == [1, 2, 3]
        for h in body["horses"]:
            assert set(h.keys()) == PACE_ANALYSIS_HORSE_KEYS
            assert h["pci"] is not None
            assert h["is_pci3_contributor"] is True

    def test_unconfirmed_race_returns_409(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/races/{UPCOMING_KEY}/pace-analysis")
        assert resp.status_code == 409
        assert "確定していません" in resp.json()["detail"]

    def test_unknown_race_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races/9999999999999999/pace-analysis")
        assert resp.status_code == 404

    def test_malformed_race_key_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races/abc/pace-analysis")
        assert resp.status_code == 422
