"""API エンドツーエンド統合テスト。

FastAPI アプリを実 DB（testcontainers-postgres）に接続し、
get_session → SqlAlchemyRaceRepository → 実 DB の経路を HTTP 越しに検証する。
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import HorseModel, JockeyModel, TrainerModel
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository
from pci.presentation.app import create_app
from pci.presentation.dependencies import get_session

pytestmark = pytest.mark.integration

RACE_KEY = "2026061705010101"


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app)


def _seed_confirmed_race(session: Session) -> None:
    session.add(HorseModel(ketto_num="2021100001", name="テストホース", sex="牡", birth_year=2021))
    session.add(JockeyModel(code="J101", name="テスト騎手"))
    session.add(TrainerModel(code="T101", name="テスト調教師"))
    session.flush()

    repo = SqlAlchemyRaceRepository(session)
    repo.save_race(
        Race(
            race_key=RaceKey(RACE_KEY),
            race_date=datetime.date(2026, 6, 17),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=1,
            status=RaceStatus.RESULT,
            track_condition="良",
            rpci_actual=51.0,
            pci3_actual=52.0,
        )
    )
    repo.save_entry(
        RaceEntry(
            race_key=RaceKey(RACE_KEY),
            horse_no=1,
            frame_no=1,
            ketto_num="2021100001",
            weight=480.0,
            jockey_code="J101",
            trainer_code="T101",
            finish_pos=1,
            race_time_s=94.4,
            agari_3f_s=34.0,
            corner_4=2,
            pci_actual=53.5,
            running_style="先行",
        )
    )
    session.flush()


def test_health_endpoint(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_race_detail_through_real_db(client: TestClient, db_session: Session) -> None:
    _seed_confirmed_race(db_session)

    resp = client.get(f"/api/v1/races/{RACE_KEY}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["race_key"] == RACE_KEY
    assert body["status"] == "result"
    assert body["rpci_actual"] == pytest.approx(51.0)
    assert len(body["entries"]) == 1
    assert body["entries"][0]["pci_actual"] == pytest.approx(53.5)
    assert body["entries"][0]["running_style"] == "先行"


def test_unknown_race_returns_404_through_real_db(client: TestClient) -> None:
    resp = client.get("/api/v1/races/2026010105010101")
    assert resp.status_code == 404
