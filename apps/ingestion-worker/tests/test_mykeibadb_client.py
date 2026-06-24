"""mykeibadb MySQL 読み取りモードのユニットテスト（実DB不要）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.client.mykeibadb_client import MyKeibaDbClient


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self._result: list[dict[str, Any]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        if sql == "SHOW TABLES":
            self._result = [
                {"Tables_in_mykeibadb": "TOKUBETSU_TOROKUBA"},
                {"Tables_in_mykeibadb": "TOKUBETSU_TOROKUBAGOTO_JOHO"},
            ]
            return
        if "TOKUBETSU_TOROKUBAGOTO_JOHO" in sql:
            self._result = self._connection.entries
            return
        if "TOKUBETSU_TOROKUBA" in sql:
            self._result = self._connection.races
            return
        raise AssertionError(sql)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._result


class _Connection:
    races = [
        {
            "開催年月日": "20260628",
            "競馬場コード": "09",
            "開催回": "01",
            "開催日次": "11",
            "レース番号": "11",
            "距離": "2200",
            "芝ダ": "芝",
            "レース名": "宝塚記念",
            "グレード": "G1",
        }
    ]
    entries = [
        {
            "開催年月日": "20260628",
            "競馬場コード": "09",
            "レース番号": "11",
            "血統登録番号": "2021100001",
            "馬名": "ベラジオオペラ",
            "性別": "牡",
            "調教師コード": "01001",
        },
        {
            "開催年月日": "20260628",
            "競馬場コード": "09",
            "レース番号": "11",
            "血統登録番号": "2021100002",
            "馬名": "ロードデルレイ",
            "性別": "牡",
            "調教師コード": "01002",
        },
    ]

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def test_fetch_special_entries_converts_mykeibadb_rows() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    races = client.fetch_special_entries("20260627", "20260628")

    assert len(races) == 1
    race = races[0]
    assert race.race_key == "2026062809011111"
    assert race.distance_m == 2200
    assert race.track_type == "芝"
    assert race.race_class == "宝塚記念 特別登録"
    assert [entry.horse_no for entry in race.entries] == [1, 2]
    assert [entry.ketto_num for entry in race.entries] == ["2021100001", "2021100002"]
    assert {entry.jockey_code for entry in race.entries} == {"TBD"}


def test_fetch_special_horses_uses_horse_names() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    horses = client.fetch_special_horses("20260627", "20260628")

    assert {horse.ketto_num: horse.name for horse in horses} == {
        "2021100001": "ベラジオオペラ",
        "2021100002": "ロードデルレイ",
    }
