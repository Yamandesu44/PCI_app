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
    "comment",
    "formation",
    "style_advantage",
}

HORSE_KEYS = {"horse_no", "horse_name", "running_style", "pai", "fit_label", "reasons"}

COMMENT_KEYS = {"headline", "body", "model_version", "reasons"}

STYLE_ADVANTAGE_KEYS = {"model_version", "entries", "reasons"}
STYLE_ADVANTAGE_ENTRY_KEYS = {"style", "score"}

FORMATION_KEYS = {"model_version", "groups"}
FORMATION_GROUP_KEYS = {"key", "label", "horses"}
FORMATION_HORSE_KEYS = {
    "horse_no",
    "frame_no",
    "horse_name",
    "running_style",
    "confidence_label",
    "reasons",
}

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
    "comment",
    "forecast_accuracy",
}

PACE_ANALYSIS_HORSE_KEYS = {
    "horse_no",
    "finish_pos",
    "horse_name",
    "running_style",
    "pci",
    "agari_3f_s",
    "is_pci3_contributor",
}


RACE_SUMMARY_KEYS = {
    "race_key",
    "race_date",
    "jyo_cd",
    "distance_m",
    "track_type",
    "status",
    "field_size",
    "grade",
    "race_class",
}


class TestListRacesEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient) -> None:
        body = client.get("/api/v1/races").json()
        assert isinstance(body, list)
        assert len(body) >= 2  # 出走前 + 確定後（+ 過去走）

    def test_summary_contract(self, client: TestClient) -> None:
        body = client.get("/api/v1/races").json()
        for item in body:
            assert set(item.keys()) == RACE_SUMMARY_KEYS

    def test_includes_upcoming_and_confirmed(self, client: TestClient) -> None:
        body = client.get("/api/v1/races").json()
        keys = {item["race_key"] for item in body}
        assert UPCOMING_KEY in keys
        assert CONFIRMED_KEY in keys

    def test_ordered_newest_first(self, client: TestClient) -> None:
        body = client.get("/api/v1/races").json()
        dates = [item["race_date"] for item in body]
        assert dates == sorted(dates, reverse=True)

    def test_status_values_valid(self, client: TestClient) -> None:
        body = client.get("/api/v1/races").json()
        for item in body:
            assert item["status"] in ("entries", "result")

    def test_limit_query_respected(self, client: TestClient) -> None:
        body = client.get("/api/v1/races?limit=1").json()
        assert len(body) == 1

    def test_limit_zero_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races?limit=0")
        assert resp.status_code == 422

    def test_limit_over_max_returns_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/races?limit=1001")
        assert resp.status_code == 422


class TestForecastEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast")
        assert resp.status_code == 200

    def test_response_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert set(body.keys()) == FORECAST_KEYS
        assert body["race_key"] == UPCOMING_KEY
        # model_version はルールベース (rule-v*) または ML (lgbm-*) どちらも許容する。
        # テスト環境にモデルファイルが無い場合は rule-v4 にフォールバックする。
        assert body["model_version"], "model_version は空であってはならない"
        assert body["pace_label"] in ("ハイ", "平均", "スロー")
        assert 35.0 <= body["predicted_rpci"] <= 65.0

    def test_horses_contract(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert len(body["horses"]) == 6
        for horse in body["horses"]:
            assert set(horse.keys()) == HORSE_KEYS
            assert horse["horse_name"]
            assert 0.0 <= horse["pai"] <= 100.0
            assert horse["fit_label"] in ("合致", "中立", "不利")
            assert horse["reasons"], "説明可能性: reasons は必須"

    def test_scenario_present(self, client: TestClient) -> None:
        body = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()
        assert body["scenario_headline"]
        assert body["scenario_detail"]

    def test_comment_contract(self, client: TestClient) -> None:
        comment = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()["comment"]
        assert set(comment.keys()) == COMMENT_KEYS
        assert comment["headline"]
        assert comment["body"], "自然文の段落本文は必須"
        assert comment["model_version"] == "comment-v1"
        assert comment["reasons"], "説明可能性: コメントの根拠は必須"

    def test_formation_contract(self, client: TestClient) -> None:
        formation = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()["formation"]
        assert set(formation.keys()) == FORMATION_KEYS
        assert formation["model_version"] == "formation-v1"
        assert [group["key"] for group in formation["groups"]] == [
            "lead",
            "front",
            "midfield",
            "rear",
        ]
        for group in formation["groups"]:
            assert set(group.keys()) == FORMATION_GROUP_KEYS
            for horse in group["horses"]:
                assert set(horse.keys()) == FORMATION_HORSE_KEYS
                assert 1 <= horse["frame_no"] <= 8
                assert horse["confidence_label"] in ("高", "標準", "参考")
                assert horse["reasons"]

    def test_style_advantage_contract(self, client: TestClient) -> None:
        advantage = client.get(f"/api/v1/races/{UPCOMING_KEY}/forecast").json()["style_advantage"]
        assert set(advantage.keys()) == STYLE_ADVANTAGE_KEYS
        assert advantage["model_version"] == "style-advantage-v1"
        styles = [entry["style"] for entry in advantage["entries"]]
        assert styles == ["逃げ", "先行", "差し", "追込"]
        for entry in advantage["entries"]:
            assert set(entry.keys()) == STYLE_ADVANTAGE_ENTRY_KEYS
            assert 0 <= entry["score"] <= 100
        assert advantage["reasons"], "説明可能性: 有利度の根拠は必須"

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
        assert body["formula_version"] == "pci-v2"  # PCI 系は formula_version 必須
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

    def test_comment_contract(self, client: TestClient) -> None:
        comment = client.get(f"/api/v1/races/{CONFIRMED_KEY}/pace-analysis").json()["comment"]
        assert set(comment.keys()) == COMMENT_KEYS
        assert comment["headline"]
        assert comment["body"]
        assert comment["model_version"] == "comment-v1"
        assert comment["reasons"]

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
