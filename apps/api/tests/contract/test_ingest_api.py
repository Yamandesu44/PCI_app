"""Ingest API 契約テスト（TestClient + FakeRaceRepository）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pci.application.dto import EntryInput, RaceInfo
from pci.application.forecast_precompute_use_cases import ForecastPrecomputeOutput
from pci.application.race_use_cases import RegisterRaceEntriesUseCase
from pci.presentation.app import create_app
from pci.presentation.dependencies import (
    get_precompute_forecasts_use_case,
    get_race_repository,
    get_session,
)
from tests.unit.application.fake_repository import FakeRaceRepository

RACE_KEY = "2026062005010101"

HORSE_PAYLOAD = [
    {"ketto_num": "2020100001", "name": "テスト馬A", "sex": "牡", "birth_year": 2020},
    {"ketto_num": "2020100002", "name": "テスト馬B"},
]

JOCKEY_PAYLOAD = [
    {"code": "J001", "name": "武豊"},
    {"code": "J002", "name": "川田将雅"},
]

TRAINER_PAYLOAD = [
    {"code": "T001", "name": "藤原英昭"},
]

ENTRIES_PAYLOAD = {
    "race_key": RACE_KEY,
    "race_date": "2026-06-20",
    "jyo_cd": "05",
    "distance_m": 1600,
    "track_type": "芝",
    "field_size": 3,
    "track_condition": "良",
    "entries": [
        {"horse_no": 1, "frame_no": 1, "ketto_num": "2020100001",
         "weight": 480.0, "jockey_code": "J001", "trainer_code": "T001"},
        {"horse_no": 2, "frame_no": 2, "ketto_num": "2020100002",
         "weight": 476.0, "jockey_code": "J002", "trainer_code": "T002"},
        {"horse_no": 3, "frame_no": 3, "ketto_num": "2020100003",
         "weight": 490.0, "jockey_code": "J003", "trainer_code": "T003"},
    ],
}

RESULTS_PAYLOAD = {
    "race_key": RACE_KEY,
    "track_condition": "良",
    "grade": "G3",
    "results": [
        {"horse_no": 1, "finish_pos": 1, "race_time_s": 94.4, "agari_3f_s": 34.0, "corner_4": 2,
         "body_weight": 486.0},
        {"horse_no": 2, "finish_pos": 2, "race_time_s": 94.6, "agari_3f_s": 34.2, "corner_4": 1},
        {"horse_no": 3, "finish_pos": 3, "race_time_s": 95.0, "agari_3f_s": 34.5, "corner_4": 4},
    ],
}


@pytest.fixture
def fake_repo() -> FakeRaceRepository:
    return FakeRaceRepository()


@pytest.fixture
def client(fake_repo: FakeRaceRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_race_repository] = lambda: fake_repo
    app.dependency_overrides[get_session] = lambda: MagicMock()
    return TestClient(app)


@pytest.fixture
def seeded_client(fake_repo: FakeRaceRepository) -> TestClient:
    """出走表が登録済みのクライアント（成績登録テスト用）。"""
    info = RaceInfo(
        race_key=RACE_KEY,
        race_date=__import__("datetime").date(2026, 6, 20),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=3,
    )
    entries = [
        EntryInput(
            horse_no=i, frame_no=i, ketto_num=f"202010000{i}",
            weight=480.0, jockey_code=f"J00{i}", trainer_code=f"T00{i}",
        )
        for i in range(1, 4)
    ]
    RegisterRaceEntriesUseCase(fake_repo).execute(info, entries)

    app = create_app()
    app.dependency_overrides[get_race_repository] = lambda: fake_repo
    app.dependency_overrides[get_session] = lambda: MagicMock()
    return TestClient(app)


class TestIngestHorses:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/horses", json=HORSE_PAYLOAD)
        assert resp.status_code == 200

    def test_accepted_count_matches_payload(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/horses", json=HORSE_PAYLOAD)
        assert resp.json()["accepted"] == 2

    def test_response_contract(self, client: TestClient) -> None:
        body = client.post("/internal/ingest/horses", json=HORSE_PAYLOAD).json()
        assert set(body.keys()) == {"accepted", "message"}
        assert body["message"] == "ok"

    def test_persists_to_repo(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        client.post("/internal/ingest/horses", json=HORSE_PAYLOAD)
        assert "2020100001" in fake_repo._horses
        assert fake_repo._horses["2020100001"].name == "テスト馬A"

    def test_invalid_ketto_num_length_returns_422(self, client: TestClient) -> None:
        bad = [{"ketto_num": "TOO_SHORT", "name": "テスト"}]
        resp = client.post("/internal/ingest/horses", json=bad)
        assert resp.status_code == 422

    def test_missing_ingest_token_in_dev_mode_allowed(self, client: TestClient) -> None:
        """INGEST_TOKEN 未設定（dev モード）ならトークンなしでも許可。"""
        resp = client.post("/internal/ingest/horses", json=HORSE_PAYLOAD)
        assert resp.status_code == 200


class TestIngestJockeys:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/jockeys", json=JOCKEY_PAYLOAD)
        assert resp.status_code == 200

    def test_accepted_count(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/jockeys", json=JOCKEY_PAYLOAD)
        assert resp.json()["accepted"] == 2

    def test_persists_to_repo(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        client.post("/internal/ingest/jockeys", json=JOCKEY_PAYLOAD)
        assert "J001" in fake_repo._jockeys
        assert fake_repo._jockeys["J001"].name == "武豊"


class TestIngestTrainers:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/trainers", json=TRAINER_PAYLOAD)
        assert resp.status_code == 200

    def test_accepted_count(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/trainers", json=TRAINER_PAYLOAD)
        assert resp.json()["accepted"] == 1

    def test_persists_to_repo(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        client.post("/internal/ingest/trainers", json=TRAINER_PAYLOAD)
        assert "T001" in fake_repo._trainers
        assert fake_repo._trainers["T001"].name == "藤原英昭"


class TestIngestEntries:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/entries", json=ENTRIES_PAYLOAD)
        assert resp.status_code == 200

    def test_accepted_count(self, client: TestClient) -> None:
        resp = client.post("/internal/ingest/entries", json=ENTRIES_PAYLOAD)
        assert resp.json()["accepted"] == 3

    def test_race_persisted(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        from pci.domain.shared.race_key import RaceKey

        client.post("/internal/ingest/entries", json=ENTRIES_PAYLOAD)
        race = fake_repo.find_by_key(RaceKey(RACE_KEY))
        assert race is not None
        assert race.distance_m == 1600
        assert race.track_condition == "良"

    def test_entries_persisted(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        from pci.domain.shared.race_key import RaceKey

        client.post("/internal/ingest/entries", json=ENTRIES_PAYLOAD)
        entries = fake_repo.find_entries(RaceKey(RACE_KEY))
        assert len(entries) == 3

    def test_invalid_race_key_pattern_returns_422(self, client: TestClient) -> None:
        bad = {**ENTRIES_PAYLOAD, "race_key": "SHORT"}
        resp = client.post("/internal/ingest/entries", json=bad)
        assert resp.status_code == 422

    def test_negative_distance_returns_422(self, client: TestClient) -> None:
        bad = {**ENTRIES_PAYLOAD, "distance_m": -1}
        resp = client.post("/internal/ingest/entries", json=bad)
        assert resp.status_code == 422


class TestDeleteIngestedRace:
    def test_deletes_existing_race(self, client: TestClient, fake_repo: FakeRaceRepository) -> None:
        client.post("/internal/ingest/entries", json=ENTRIES_PAYLOAD)

        resp = client.delete(f"/internal/ingest/races/{RACE_KEY}")

        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1
        assert RACE_KEY not in fake_repo._races
        assert not any(key[0] == RACE_KEY for key in fake_repo._entries)

    def test_unknown_race_is_idempotent(self, client: TestClient) -> None:
        resp = client.delete("/internal/ingest/races/9999999999999999")

        assert resp.status_code == 200
        assert resp.json()["accepted"] == 0

    def test_invalid_race_key_returns_422(self, client: TestClient) -> None:
        resp = client.delete("/internal/ingest/races/SHORT")

        assert resp.status_code == 422


class TestIngestResults:
    def test_returns_200(self, seeded_client: TestClient) -> None:
        resp = seeded_client.post("/internal/ingest/results", json=RESULTS_PAYLOAD)
        assert resp.status_code == 200

    def test_response_contract(self, seeded_client: TestClient) -> None:
        body = seeded_client.post("/internal/ingest/results", json=RESULTS_PAYLOAD).json()
        assert set(body.keys()) == {"race_key", "rpci", "pci3", "formula_version", "entry_pcis"}
        assert body["race_key"] == RACE_KEY
        assert body["formula_version"] == "pci-v2"

    def test_rpci_is_numeric(self, seeded_client: TestClient) -> None:
        body = seeded_client.post("/internal/ingest/results", json=RESULTS_PAYLOAD).json()
        assert isinstance(body["rpci"], float)
        assert 30.0 < body["rpci"] < 70.0

    def test_entry_pcis_keyed_by_horse_no(self, seeded_client: TestClient) -> None:
        body = seeded_client.post("/internal/ingest/results", json=RESULTS_PAYLOAD).json()
        assert set(body["entry_pcis"].keys()) == {"1", "2", "3"}

    def test_result_updates_grade_and_body_weight(
        self, seeded_client: TestClient, fake_repo: FakeRaceRepository
    ) -> None:
        from pci.domain.shared.race_key import RaceKey

        seeded_client.post("/internal/ingest/results", json=RESULTS_PAYLOAD)

        race = fake_repo.find_by_key(RaceKey(RACE_KEY))
        entries = fake_repo.find_entries(RaceKey(RACE_KEY))
        assert race is not None and race.grade == "G3"
        assert next(e for e in entries if e.horse_no == 1).weight == 486.0

    def test_unknown_race_key_returns_500_or_4xx(self, client: TestClient) -> None:
        bad = {**RESULTS_PAYLOAD, "race_key": "9999999999999999"}
        resp = client.post("/internal/ingest/results", json=bad)
        assert resp.status_code in (400, 404, 422, 500)


class TestPrecomputeForecasts:
    def test_returns_generation_summary(self, client: TestClient) -> None:
        use_case = MagicMock()
        use_case.execute.return_value = ForecastPrecomputeOutput(
            scanned=12,
            generated=10,
            skipped=2,
        )
        client.app.dependency_overrides[get_precompute_forecasts_use_case] = lambda: use_case

        resp = client.post(
            "/internal/ingest/forecasts/precompute",
            json={"date_from": "2026-07-22", "date_to": "2026-07-26"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"scanned": 12, "generated": 10, "skipped": 2}

    def test_rejects_more_than_32_days(self, client: TestClient) -> None:
        resp = client.post(
            "/internal/ingest/forecasts/precompute",
            json={"date_from": "2026-07-01", "date_to": "2026-08-02"},
        )

        assert resp.status_code == 422


class TestIngestAuth:
    """INGEST_TOKEN 設定時の認証動作を検証する。"""

    _TARGET = "pci.presentation.routers.ingest.get_settings"

    def _mock_settings(self, token: str) -> MagicMock:
        s = MagicMock()
        s.ingest_token = token
        return s

    def test_missing_token_returns_401(self, client: TestClient) -> None:
        """INGEST_TOKEN 設定時、トークンなしリクエストは 401。"""
        with patch(self._TARGET, return_value=self._mock_settings("secret")):
            resp = client.post("/internal/ingest/horses", json=HORSE_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client: TestClient) -> None:
        """誤ったトークンは 401。"""
        with patch(self._TARGET, return_value=self._mock_settings("secret")):
            resp = client.post(
                "/internal/ingest/horses",
                json=HORSE_PAYLOAD,
                headers={"X-Ingest-Token": "wrong"},
            )
        assert resp.status_code == 401

    def test_correct_token_returns_200(self, client: TestClient) -> None:
        """正しいトークンは 200。"""
        with patch(self._TARGET, return_value=self._mock_settings("secret")):
            resp = client.post(
                "/internal/ingest/horses",
                json=HORSE_PAYLOAD,
                headers={"X-Ingest-Token": "secret"},
            )
        assert resp.status_code == 200
