"""重複レース監査の内容署名テスト。"""

import datetime

from pci.infrastructure.database.models import RaceEntryModel, RaceModel
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository


def _entry(
    race_key: str,
    ketto_num: str,
    *,
    popularity: int | None,
    prize_money: int | None,
) -> RaceEntryModel:
    return RaceEntryModel(
        race_key=race_key,
        horse_no=1,
        frame_no=1,
        ketto_num=ketto_num,
        weight=480.0,
        jockey_code="J001",
        trainer_code="T001",
        finish_pos=1,
        race_time_s=95.4,
        agari_3f_s=34.1,
        corner_1=None,
        corner_2=2,
        corner_3=2,
        corner_4=1,
        popularity=popularity,
        prize_money=prize_money,
    )


def _race(race_key: str) -> RaceModel:
    return RaceModel(
        race_key=race_key,
        race_date=datetime.date(2026, 2, 1),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=1,
        status="result",
    )


def test_result_signature_ignores_identity_and_optional_result_metadata() -> None:
    """中核成績が同じなら、馬ID・人気・賞金の差を結果衝突にしない。"""
    stale = SqlAlchemyRaceRepository._build_duplicate_key_audit(
        _race("2026020105010109"),
        [
            _entry(
                "2026020105010109",
                "2023000001",
                popularity=None,
                prize_money=None,
            )
        ],
        predicted_pace_models=(),
        pace_fit_models=(),
    )
    canonical = SqlAlchemyRaceRepository._build_duplicate_key_audit(
        _race("2026020105010209"),
        [
            _entry(
                "2026020105010209",
                "2023000002",
                popularity=1,
                prize_money=100_000,
            )
        ],
        predicted_pace_models=(),
        pace_fit_models=(),
    )

    assert stale.result_signature == canonical.result_signature
    assert stale.entry_signature != canonical.entry_signature
