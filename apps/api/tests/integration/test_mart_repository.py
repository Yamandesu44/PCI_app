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
    old_generated_at = datetime.datetime(2026, 7, 21, 10, 0, tzinfo=datetime.UTC)
    latest_generated_at = datetime.datetime(2026, 7, 22, 10, 0, tzinfo=datetime.UTC)
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
            generated_at=latest_generated_at,
        )
    )
    db_session.add(
        PredictedPaceModel(
            race_key=race_key,
            model_version="zzz-old-model",
            predicted_rpci=55.0,
            pace_label="スロー",
            confidence=0.95,
            factors=[],
            generated_at=old_generated_at,
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
                generated_at=latest_generated_at,
            ),
            PaceFitModel(
                race_key=race_key,
                horse_no=2,
                model_version="pai-v1",
                pai=84.0,
                fit_label="合致",
                reasons=[],
                generated_at=latest_generated_at,
            ),
            PaceFitModel(
                race_key=race_key,
                horse_no=1,
                model_version="zzz-old-pai",
                pai=99.0,
                fit_label="合致",
                reasons=[],
                generated_at=old_generated_at,
            ),
        ]
    )
    db_session.flush()

    records = SqlAlchemyMartRepository(db_session).find_race_board_forecasts([race_key])
    predicted = SqlAlchemyMartRepository(db_session).find_predicted_pace(race_key)

    assert records[race_key].pace_label == "ハイ"
    assert records[race_key].top_horse_no == 2
    assert records[race_key].top_horse_name == "最上位候補"
    assert records[race_key].top_pai == pytest.approx(84.0)
    assert predicted is not None
    assert predicted.model_version == "rule-v4"


def test_find_prediction_evaluations_uses_latest_pre_result_forecast(
    db_session: Session,
) -> None:
    race_key = "2026072005010101"
    db_session.add_all(
        [
            RaceModel(
                race_key=race_key,
                race_date=datetime.date(2026, 7, 20),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status="result",
                race_class="テスト特別",
                rpci_actual=55.0,
            ),
            RaceModel(
                race_key="2026071905010102",
                race_date=datetime.date(2026, 7, 19),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status="entries",
                rpci_actual=None,
            ),
            RaceModel(
                race_key="2026071842010103",
                race_date=datetime.date(2026, 7, 18),
                jyo_cd="42",
                distance_m=1400,
                track_type="ダート",
                field_size=12,
                status="result",
                rpci_actual=43.0,
            ),
            RaceModel(
                race_key="2026071705010104",
                race_date=datetime.date(2026, 7, 17),
                jyo_cd="05",
                distance_m=1800,
                track_type="ダート",
                field_size=14,
                status="result",
                rpci_actual=44.0,
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            PredictedPaceModel(
                race_key=race_key,
                model_version="rule-v3",
                predicted_rpci=50.0,
                pace_label="平均",
                confidence=0.55,
                factors=[],
                generated_at=datetime.datetime(
                    2026, 7, 19, 8, 0, tzinfo=datetime.UTC
                ),
            ),
            PredictedPaceModel(
                race_key=race_key,
                model_version="rule-v4",
                predicted_rpci=55.0,
                pace_label="スロー",
                confidence=0.72,
                factors=[],
                generated_at=datetime.datetime(
                    2026, 7, 20, 8, 0, tzinfo=datetime.UTC
                ),
            ),
            PredictedPaceModel(
                race_key=race_key,
                model_version="post-result",
                predicted_rpci=45.0,
                pace_label="ハイ",
                confidence=0.99,
                factors=[],
                generated_at=datetime.datetime(
                    2026, 7, 21, 8, 0, tzinfo=datetime.UTC
                ),
            ),
            PredictedPaceModel(
                race_key="2026071842010103",
                model_version="rule-v4",
                predicted_rpci=43.0,
                pace_label="平均",
                confidence=0.7,
                factors=[],
                generated_at=datetime.datetime(
                    2026, 7, 18, 7, 0, tzinfo=datetime.UTC
                ),
            ),
        ]
    )
    db_session.flush()

    records = SqlAlchemyMartRepository(db_session).find_prediction_evaluations(
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 31),
    )
    candidate_count = SqlAlchemyMartRepository(
        db_session
    ).count_prediction_evaluation_candidates(
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 31),
    )

    assert len(records) == 1
    assert candidate_count == 2
    assert records[0].race_key == race_key
    assert records[0].model_version == "rule-v4"
    assert records[0].predicted_label == "スロー"
    assert records[0].jyo_cd == "05"
    assert records[0].distance_m == 1600
    assert records[0].race_class == "テスト特別"


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
