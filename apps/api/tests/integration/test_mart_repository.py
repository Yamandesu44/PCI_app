"""一覧向けmart一括読取のPostgreSQL統合テスト。"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import Session

from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import (
    HorseModel,
    JockeyModel,
    PaceFitModel,
    PredictedPaceModel,
    RaceEntryModel,
    RaceModel,
    TrainerModel,
)
from pci.infrastructure.repositories.mart_repository import SqlAlchemyMartRepository
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository

pytestmark = pytest.mark.integration


def test_find_race_board_forecasts_selects_top_fit_horse(db_session: Session) -> None:
    race_key = "2026072205010101"
    db_session.add(
        RaceModel(
            race_key=race_key,
            race_date=datetime.date(2026, 7, 22),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=2,
            status="entries",
        )
    )
    db_session.add_all(
        [
            HorseModel(ketto_num="2022100001", name="先行候補"),
            HorseModel(ketto_num="2022100002", name="最上位候補"),
            JockeyModel(code="J001", name="騎手"),
            TrainerModel(code="T001", name="調教師"),
        ]
    )
    db_session.flush()
    for horse_no in (1, 2):
        db_session.add(
            RaceEntryModel(
                race_key=race_key,
                horse_no=horse_no,
                frame_no=horse_no,
                ketto_num=f"202210000{horse_no}",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
            )
        )
    db_session.add(
        PredictedPaceModel(
            race_key=race_key,
            model_version="rule-v4",
            predicted_rpci=48.0,
            pace_label="ハイ",
            confidence=0.72,
            factors=[],
        )
    )
    db_session.add_all(
        [
            PaceFitModel(
                race_key=race_key,
                horse_no=1,
                model_version="pai-v1",
                pai=68.0,
                fit_label="中立",
                reasons=[],
            ),
            PaceFitModel(
                race_key=race_key,
                horse_no=2,
                model_version="pai-v1",
                pai=84.0,
                fit_label="合致",
                reasons=[],
            ),
        ]
    )
    db_session.flush()

    records = SqlAlchemyMartRepository(db_session).find_race_board_forecasts([race_key])

    assert records[race_key].pace_label == "ハイ"
    assert records[race_key].top_horse_no == 2
    assert records[race_key].top_horse_name == "最上位候補"
    assert records[race_key].top_pai == pytest.approx(84.0)


def test_entry_draw_change_invalidates_saved_forecast(db_session: Session) -> None:
    race_key = "2026072205010102"
    db_session.add(
        RaceModel(
            race_key=race_key,
            race_date=datetime.date(2026, 7, 22),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=1,
            status="entries",
        )
    )
    db_session.add_all(
        [
            HorseModel(ketto_num="2022100003", name="枠変更馬"),
            JockeyModel(code="J002", name="騎手2"),
            TrainerModel(code="T002", name="調教師2"),
        ]
    )
    db_session.flush()
    repo = SqlAlchemyRaceRepository(db_session)
    original = RaceEntry(
        race_key=RaceKey(race_key),
        horse_no=1,
        frame_no=1,
        ketto_num="2022100003",
        weight=480.0,
        jockey_code="J002",
        trainer_code="T002",
    )
    repo.save_entry(original)
    db_session.flush()
    db_session.add(
        PredictedPaceModel(
            race_key=race_key,
            model_version="rule-v4",
            predicted_rpci=50.0,
            pace_label="平均",
            confidence=0.6,
            factors=[],
        )
    )
    db_session.flush()

    repo.save_entry(
        RaceEntry(
            race_key=RaceKey(race_key),
            horse_no=1,
            frame_no=2,
            ketto_num="2022100003",
            weight=480.0,
            jockey_code="J002",
            trainer_code="T002",
        )
    )
    db_session.flush()

    assert db_session.get(PredictedPaceModel, (race_key, "rule-v4")) is None
