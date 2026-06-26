"""mykeibadb MySQL 読み取りモードのユニットテスト（実DB不要）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.client.mykeibadb_client import MyKeibaDbClient
from ingestion.parser.ra_parser import parse_ra
from ingestion.parser.se_parser import parse_se_entry, parse_se_result


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
                {"Tables_in_mykeibadb": "race_shosai"},
                {"Tables_in_mykeibadb": "umagoto_race_joho"},
                {"Tables_in_mykeibadb": "kyosoba_master2"},
                {"Tables_in_mykeibadb": "kishu_master"},
                {"Tables_in_mykeibadb": "chokyoshi_master"},
            ]
            return
        table = sql.split("`")[1]
        if table == "race_shosai":
            self._result = self._connection.ra
            return
        if table == "umagoto_race_joho":
            self._result = self._connection.se
            return
        if table == "kyosoba_master2":
            self._result = self._connection.um
            return
        if table == "kishu_master":
            self._result = self._connection.ks
            return
        if table == "chokyoshi_master":
            self._result = self._connection.ch
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

    def fetchmany(self, size: int) -> list[dict[str, Any]]:
        rows = self._result[:size]
        self._result = self._result[size:]
        return rows


class _Connection:
    ra = [
        {
            "開催年月日": "20260621",
            "競馬場コード": "09",
            "開催回": "01",
            "開催日次": "03",
            "レース番号": "11",
            "距離": "1600",
            "芝ダ": "芝",
            "レース名": "@",
            "競走条件名称": "3歳未勝利",
            "前半3F": "35.2",
            "後半3F": "35.8",
        }
    ]
    se = [
        {
            "開催年月日": "20260621",
            "競馬場コード": "09",
            "開催回": "01",
            "開催日次": "03",
            "レース番号": "11",
            "枠番": "1",
            "馬番": "1",
            "血統登録番号": "2021100001",
            "馬名": "テストホース",
            "性別": "牡",
            "調教師コード": "01001",
            "騎手コード": "02001",
            "馬体重": "480",
            "着順": "1",
            "タイム": "94.4",
            "上がり3F": "34.5",
            "1角": "2",
            "2角": "2",
            "3角": "2",
            "4角": "2",
        }
    ]
    um = [{"血統登録番号": "2021100001", "馬名": "テストホース", "性別": "牡", "生年": "2021"}]
    ks = [{"騎手コード": "02001", "騎手名": "テスト騎手"}]
    ch = [{"調教師コード": "01001", "調教師名": "テスト調教師"}]
    races = [
        {
            "開催年月日": "20260628",
            "競馬場コード": "02",
            "開催回": "01",
            "開催日次": "06",
            "レース番号": "11",
            "距離": "2200",
            "芝ダ": "芝",
            "レース名": "函館記念",
            "グレード": "G3",
        }
    ]
    entries = [
        {
            "開催年月日": "20260628",
            "競馬場コード": "02",
            "レース番号": "11",
            "血統登録番号": "2021100001",
            "馬名": "ベラジオオペラ",
            "性別": "牡",
            "調教師コード": "01001",
        },
        {
            "開催年月日": "20260628",
            "競馬場コード": "02",
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
    assert race.race_key == "2026062802010611"
    assert race.distance_m == 2200
    assert race.track_type == "芝"
    assert race.race_class == "函館記念 特別登録"
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


def test_fetch_special_entries_excludes_known_stale_hanshin_race() -> None:
    class _StaleConnection(_Connection):
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
            }
        ]

    client = MyKeibaDbClient(connection=_StaleConnection())

    assert client.fetch_special_entries("20260627", "20260628") == []


def test_iter_ra_records_builds_jv_record_from_mysql_row() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    records = list(client.iter_ra_records("20260621", "20260621"))

    assert len(records) == 1
    assert records[0].startswith("RA")
    assert "3歳未勝利" in records[0]


def test_iter_ra_records_accepts_wmykeibadb_race_shosai_columns() -> None:
    class _WMyKeibaDbConnection(_Connection):
        ra = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": 2026,
                "KAISAI_GAPPI": "0621",
                "KEIBAJO_CODE": 5,
                "KAISAI_KAI": 3,
                "KAISAI_NICHIME": 4,
                "RACE_BANGO": 11,
                "KYOSOMEI_HONDAI": "@",
                "KYOSO_JOKEN_MEISHO": "3歳未勝利",
                "KYORI": 1600,
                "TRACK_CODE": 17,
                "ZENHAN_3F": 35.2,
                "KOHAN_3F": 35.8,
            }
        ]

    client = MyKeibaDbClient(connection=_WMyKeibaDbConnection())

    records = list(client.iter_ra_records("20260621", "20260621"))
    parsed = parse_ra(records[0])

    assert parsed.race_key == "2026062105030411"
    assert parsed.distance_m == 1600


def test_iter_se_records_builds_result_record_from_mysql_row() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    records = list(client.iter_se_records("20260621", "20260621"))

    assert len(records) == 1
    assert records[0].startswith("SE7")
    assert "テストホース" in records[0]


def test_iter_se_records_parses_results_from_wmykeibadb_columns() -> None:
    """実 mykeibadb の大文字ローマ字列（SOHA_TIME 等）から確定成績がパースできる。

    回帰: 列名が候補リストと一致せず agari/time/着順が空欄になり、
    parse_se_result が全件 None を返して成績0件になっていた問題を防ぐ。
    """

    class _WMyKeibaDbConnection(_Connection):
        se = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0621",
                "KEIBAJO_CODE": "09",
                "KAISAI_KAIJI": "01",
                "KAISAI_NICHIJI": "03",
                "RACE_BANGO": "11",
                "WAKUBAN": "1",
                "UMABAN": "01",
                "KETTO_TOROKU_BANGO": "2021100001",
                "BAMEI": "テストホース",
                "SEIBETSU_CODE": "1",
                "CHOKYOSHI_CODE": "01001",
                "KISHU_CODE": "02001",
                "BATAIJU": "480",
                "KAKUTEI_CHAKUJUN": "01",
                "SOHA_TIME": "1344",  # 1:34.4
                "KOHAN_3F": "345",    # 34.5秒（1/10秒の生値）
                "CORNER1_JUNI": "02",
                "CORNER2_JUNI": "02",
                "CORNER3_JUNI": "03",
                "CORNER4_JUNI": "02",
            }
        ]

    client = MyKeibaDbClient(connection=_WMyKeibaDbConnection())
    record = next(client.iter_se_records("20260621", "20260621"))

    # 出走表（枠番・馬番・血統・馬体重）
    entry = parse_se_entry(record)
    assert entry is not None
    assert entry.horse_no == 1
    assert entry.frame_no == 1
    assert entry.ketto_num == "2021100001"
    assert entry.weight == 480.0

    # 確定成績（着順・タイム・上り3F・コーナー通過順位）
    result = parse_se_result(record)
    assert result is not None
    assert result.finish_pos == 1
    assert result.race_time_s == 94.4
    assert result.agari_3f_s == 34.5
    assert result.corner_4 == 2


def test_race_time_mssf_handles_sub_minute_time() -> None:
    """SOHA_TIME '0594'（0:59.4）が MSSf として正しく扱われる。"""
    from ingestion.client.mykeibadb_client import _race_time_to_mssf

    assert _race_time_to_mssf("0594") == "0594"
    assert _race_time_to_mssf("1344") == "1344"
    # 秒・小数表記は従来どおり MSSf へ変換する。
    assert _race_time_to_mssf("94.4") == "1344"


def test_iter_master_records_build_from_mysql_rows() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    assert "テストホース" in next(client.iter_um_records())
    assert "テスト騎手" in next(client.iter_ks_records())
    assert "テスト調教師" in next(client.iter_ch_records())
