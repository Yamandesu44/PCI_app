"""契約テスト共通フィクスチャ。

Repository 依存を FakeRaceRepository でオーバーライドし、DB なしで API 契約を検証する。
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient

from pci.application.dto import EntryInput, RaceInfo, ResultInput
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_use_cases import RecordRaceResultUseCase, RegisterRaceEntriesUseCase
from pci.domain.ops.ingest_log import IngestLogEntry
from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.readiness import DatabaseReadiness
from pci.presentation.app import create_app
from pci.presentation.dependencies import (
    get_database_readiness,
    get_forecast_use_case,
    get_ingest_log_repository,
    get_mart_repository,
    get_race_repository,
)
from tests.unit.application.fake_ingest_log_repository import FakeIngestLogRepository
from tests.unit.application.fake_mart_repository import FakeMartRepository
from tests.unit.application.fake_repository import FakeRaceRepository

UPCOMING_KEY = "2026062005010101"
CONFIRMED_KEY = "2026061705010101"


def _seed_history(repo: FakeRaceRepository, ketto_num: str, corner4: int, base_idx: int) -> None:
    """脚質判定用に、確定済みの過去走を3走付与する。"""
    for i in range(3):
        rk = f"20260{base_idx}{i + 1:02d}05010199"
        repo.save_race(
            Race(
                race_key=RaceKey(rk),
                race_date=datetime.date(2026, 5, i + 1),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(rk),
                horse_no=1,
                frame_no=1,
                ketto_num=ketto_num,
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=3,
                corner_4=corner4,
            )
        )


def _seed_upcoming(repo: FakeRaceRepository) -> None:
    """未確定レース（展開予想対象）。逃げ3・追込3の混成で合致馬が出る構成。"""
    info = RaceInfo(
        race_key=UPCOMING_KEY,
        race_date=datetime.date(2026, 6, 20),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=6,
        track_condition="良",
    )
    entries = [
        EntryInput(
            horse_no=i,
            frame_no=i,
            ketto_num=f"202010000{i}",
            weight=480.0,
            jockey_code=f"J00{i}",
            trainer_code=f"T00{i}",
        )
        for i in range(1, 7)
    ]
    RegisterRaceEntriesUseCase(repo).execute(info, entries)
    # 1-3番を逃げ（4角1番手）、4-6番を追込（4角12番手）に仕立てる
    for i in range(1, 4):
        _seed_history(repo, f"202010000{i}", corner4=1, base_idx=i)
    for i in range(4, 7):
        _seed_history(repo, f"202010000{i}", corner4=12, base_idx=i)


def _seed_confirmed(repo: FakeRaceRepository) -> None:
    """確定レース（詳細照会対象）。RPCI/PCI3 と各馬 PCI が埋まる。"""
    info = RaceInfo(
        race_key=CONFIRMED_KEY,
        race_date=datetime.date(2026, 6, 17),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=3,
        track_condition="良",
    )
    entries = [
        EntryInput(
            horse_no=i,
            frame_no=i,
            ketto_num=f"202110000{i}",
            weight=480.0,
            jockey_code=f"J10{i}",
            trainer_code=f"T10{i}",
        )
        for i in range(1, 4)
    ]
    RegisterRaceEntriesUseCase(repo).execute(info, entries)
    results = [
        ResultInput(horse_no=1, finish_pos=1, race_time_s=94.4, agari_3f_s=34.0, corner_4=2),
        ResultInput(horse_no=2, finish_pos=2, race_time_s=94.6, agari_3f_s=34.2, corner_4=1),
        ResultInput(horse_no=3, finish_pos=3, race_time_s=95.0, agari_3f_s=34.5, corner_4=4),
    ]
    RecordRaceResultUseCase(repo).execute(CONFIRMED_KEY, results, track_condition="良")


@pytest.fixture
def repo() -> FakeRaceRepository:
    r = FakeRaceRepository()
    _seed_upcoming(r)
    _seed_confirmed(r)
    return r


@pytest.fixture
def client(repo: FakeRaceRepository) -> TestClient:
    app = create_app()
    mart_repo = FakeMartRepository()
    app.dependency_overrides[get_race_repository] = lambda: repo
    app.dependency_overrides[get_mart_repository] = lambda: mart_repo
    # 契約テストはAPI形状が対象。ネイティブMLライブラリに依存させず決定的にする。
    app.dependency_overrides[get_forecast_use_case] = lambda: ForecastRaceUseCase(
        repo,
        forecaster=RuleBasedRpciForecaster(),
        mart_repo=mart_repo,
    )
    # 実行時刻からの相対時刻にし、テスト実行日に依存せず「直近成功」を再現する。
    started_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=3)
    recent_success = IngestLogEntry(
        batch_date=started_at.date(),
        step="entries",
        mode="mykeibadb",
        started_at=started_at,
        finished_at=started_at + datetime.timedelta(minutes=5),
        status="ok",
        error_msg=None,
    )
    app.dependency_overrides[get_ingest_log_repository] = lambda: FakeIngestLogRepository(
        [recent_success]
    )
    app.dependency_overrides[get_database_readiness] = lambda: DatabaseReadiness(
        ready=True, database="ok"
    )
    return TestClient(app)
