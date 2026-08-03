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
                "GRADE_CODE": "A",
                "TENKO_CODE": "3",
                "SHIBA_BABAJOTAI_CODE": "2",
                "DIRT_BABAJOTAI_CODE": "1",
                "ZENHAN_3F": 352,
                "KOHAN_3F": 358,
            }
        ]

    client = MyKeibaDbClient(connection=_WMyKeibaDbConnection())

    records = list(client.iter_ra_records("20260621", "20260621"))
    parsed = parse_ra(records[0])

    assert parsed.race_key == "2026062105030411"
    assert parsed.distance_m == 1600
    assert parsed.grade == "G1"
    assert parsed.race_s3f == 35.2
    assert parsed.race_l3f == 35.8
    metadata = client.race_metadata(parsed.race_key)
    assert metadata is not None
    assert metadata.track_condition == "稍重"
    assert metadata.weather == "小雨"


def test_iter_race_metadata_uses_condition_for_actual_track() -> None:
    class _TrackConditionConnection(_Connection):
        ra = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": 2026,
                "KAISAI_GAPPI": "0621",
                "KEIBAJO_CODE": 5,
                "KAISAI_KAI": 3,
                "KAISAI_NICHIME": 4,
                "RACE_BANGO": 10,
                "KYORI": 1600,
                "TRACK_CODE": 17,
                "TENKO_CODE": "1",
                "SHIBA_BABAJOTAI_CODE": "2",
                "DIRT_BABAJOTAI_CODE": "4",
            },
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": 2026,
                "KAISAI_GAPPI": "0621",
                "KEIBAJO_CODE": 5,
                "KAISAI_KAI": 3,
                "KAISAI_NICHIME": 4,
                "RACE_BANGO": 11,
                "KYORI": 1600,
                "TRACK_CODE": 24,
                "TENKO_CODE": "4",
                "SHIBA_BABAJOTAI_CODE": "1",
                "DIRT_BABAJOTAI_CODE": "3",
            },
        ]

    client = MyKeibaDbClient(connection=_TrackConditionConnection())

    records = list(client.iter_race_metadata("20260621", "20260621"))

    assert [
        (record.track_type, record.track_condition, record.weather)
        for record in records
    ] == [
        ("芝", "稍重", "晴"),
        ("ダート", "重", "雨"),
    ]


def test_iter_ra_records_preserves_hurdle_track_code() -> None:
    class _HurdleConnection(_Connection):
        ra = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0719",
                "KEIBAJO_CODE": "10",
                "KAISAI_KAI": "02",
                "KAISAI_NICHIME": "08",
                "RACE_BANGO": "01",
                "KYORI": "2860",
                "TRACK_CODE": "54",
                "DIRT_BABAJOTAI_CODE": "4",
            }
        ]

    client = MyKeibaDbClient(connection=_HurdleConnection())
    record = next(client.iter_ra_records("20260719", "20260719"))
    parsed = parse_ra(record)

    assert parsed is not None
    assert parsed.track_type == "障害"
    metadata = client.race_metadata(parsed.race_key)
    assert metadata is not None
    assert metadata.track_condition is None


def test_iter_race_records_excludes_non_jra_venues() -> None:
    class _LocalVenueConnection(_Connection):
        ra = [
            {
                "開催年月日": "20260716",
                "競馬場コード": "42",
                "開催回": "04",
                "開催日次": "04",
                "レース番号": "09",
                "距離": "1400",
                "芝ダ": "ダート",
            }
        ]
        se = [
            {
                "開催年月日": "20260716",
                "競馬場コード": "42",
                "開催回": "04",
                "開催日次": "04",
                "レース番号": "09",
                "枠番": "1",
                "馬番": "1",
                "血統登録番号": "2021100001",
            }
        ]

    client = MyKeibaDbClient(connection=_LocalVenueConnection())

    assert list(client.iter_ra_records("20260716", "20260716")) == []
    assert list(client.iter_se_records("20260716", "20260716")) == []


def test_iter_race_records_excludes_zero_meeting_overseas_rows() -> None:
    class _OverseasConnection(_Connection):
        ra = [
            {
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0328",
                "KEIBAJO_CODE": "07",
                "KAISAI_KAI": "00",
                "KAISAI_NICHIME": "00",
                "RACE_BANGO": "09",
                "KYORI": "2000",
                "TRACK_CODE": "24",
            }
        ]
        se = []

    client = MyKeibaDbClient(connection=_OverseasConnection())

    assert list(client.iter_ra_records("20260328", "20260328")) == []


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
    result = parse_se_result(record, synthetic_result_fields=True)
    assert result is not None
    assert result.finish_pos == 1
    assert result.race_time_s == 94.4
    assert result.agari_3f_s == 34.5
    assert result.corner_4 == 2


def test_iter_se_records_treats_full_result_data_as_confirmed_even_if_data_kubun_is_stale() -> None:
    """DATA_KUBUN列が確定コード('4'/'7')以外でも、着順・タイム・上り3Fが揃っていれば確定扱いする。

    回帰: mykeibadb環境によってはDATA_KUBUN列がJV-Data由来の確定コードを正しく反映せず
    "1"(出走前)のまま止まる場合があり、この値をそのまま信用すると成績が揃っているレコードでも
    parse_se_result が None を返し続け、確定成績が一切反映されなくなる
    （2026-07-20 ユーザー報告: 特別登録は反映されるのに確定成績だけ1週間以上反映されない）。
    """

    class _StaleDataKubunConnection(_Connection):
        se = [
            {
                "DATA_KUBUN": "1",  # 確定後にも関わらず出走前のまま止まっている想定
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0712",
                "KEIBAJO_CODE": "02",
                "KAISAI_KAIJI": "01",
                "KAISAI_NICHIJI": "03",
                "RACE_BANGO": "09",
                "WAKUBAN": "1",
                "UMABAN": "01",
                "KETTO_TOROKU_BANGO": "2021100001",
                "BAMEI": "テストホース",
                "SEIBETSU_CODE": "1",
                "CHOKYOSHI_CODE": "01001",
                "KISHU_CODE": "02001",
                "BATAIJU": "480",
                "KAKUTEI_CHAKUJUN": "01",
                "SOHA_TIME": "1344",
                "KOHAN_3F": "345",
                "CORNER1_JUNI": "02",
                "CORNER2_JUNI": "02",
                "CORNER3_JUNI": "03",
                "CORNER4_JUNI": "02",
            }
        ]

    client = MyKeibaDbClient(connection=_StaleDataKubunConnection())
    record = next(client.iter_se_records("20260712", "20260712"))

    result = parse_se_result(record)
    assert result is not None
    assert result.finish_pos == 1
    assert result.race_time_s == 94.4
    assert result.agari_3f_s == 34.5


def test_iter_se_records_uses_race_code_for_kaiji_nichiji() -> None:
    """RACE_CODE (16桁) から kaiji/nichiji を取り出し、正しい race_key が合成される。

    回帰: KAISAI_KAIJI/KAISAI_NICHIJI 列が候補リストに無く kaiji/nichiji が "01"
    に固定され、PostgreSQL の race_key と一致しなくなる問題を防ぐ。
    """
    from ingestion.parser.se_parser import parse_race_key_from_se

    class _RaceCodeConnection(_Connection):
        se = [
            {
                "DATA_KUBUN": "7",
                # RACE_CODE が 16桁の場合、kaiji=03/nichiji=02 を正確に取れる
                "RACE_CODE": "2025072707030205",
                "KAISAI_NEN": "2025",
                "KAISAI_GAPPI": "0727",
                "KEIBAJO_CODE": "07",
                # KAISAI_KAIJI / KAISAI_NICHIJI（候補リスト外の列名）
                "KAISAI_KAIJI": "03",
                "KAISAI_NICHIJI": "02",
                "RACE_BANGO": "05",
                "WAKUBAN": "1",
                "UMABAN": "01",
                "KETTO_TOROKU_BANGO": "2021100001",
                "BAMEI": "テストホース",
                "SEIBETSU_CODE": "1",
                "CHOKYOSHI_CODE": "01001",
                "KISHU_CODE": "02001",
                "BATAIJU": "480",
                "KAKUTEI_CHAKUJUN": "01",
                "SOHA_TIME": "1344",
                "KOHAN_3F": "345",
                "CORNER1_JUNI": "02",
                "CORNER2_JUNI": "02",
                "CORNER3_JUNI": "03",
                "CORNER4_JUNI": "02",
            }
        ]

    client = MyKeibaDbClient(connection=_RaceCodeConnection())
    record = next(client.iter_se_records("20250727", "20250727"))

    # RACE_CODE から kaiji=03, nichiji=02 が正しく反映されること
    race_key = parse_race_key_from_se(record)
    assert race_key == "2025072707030205", f"想定外の race_key: {race_key}"


def test_race_time_mssf_handles_sub_minute_time() -> None:
    """SOHA_TIME '0594'（0:59.4）が MSSf として正しく扱われる。"""
    from ingestion.client.mykeibadb_client import _race_time_to_mssf

    assert _race_time_to_mssf("0594") == "0594"
    assert _race_time_to_mssf("1344") == "1344"
    # 秒・小数表記は従来どおり MSSf へ変換する。
    assert _race_time_to_mssf("94.4") == "1344"


def test_iter_se_records_roundtrips_popularity_and_prize() -> None:
    """Phase2: 人気(TANSHO_NINKIJUN)・本賞金(KAKUTOKU_HONSHOKIN)が SE 合成→解析で往復する。"""

    class _PrizeConnection(_Connection):
        se = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0712",
                "KEIBAJO_CODE": "02",
                "KAISAI_KAIJI": "01",
                "KAISAI_NICHIJI": "03",
                "RACE_BANGO": "09",
                "WAKUBAN": "1",
                "UMABAN": "01",
                "KETTO_TOROKU_BANGO": "2021100001",
                "BAMEI": "テストホース",
                "SEIBETSU_CODE": "1",
                "CHOKYOSHI_CODE": "01001",
                "KISHU_CODE": "02001",
                "BATAIJU": "480",
                "KAKUTEI_CHAKUJUN": "01",
                "SOHA_TIME": "1344",
                "KOHAN_3F": "345",
                "TANSHO_NINKIJUN": "3",
                "KAKUTOKU_HONSHOKIN": "12000000",
            }
        ]

    client = MyKeibaDbClient(connection=_PrizeConnection())
    record = next(client.iter_se_records("20260712", "20260712"))

    jvlink_result = parse_se_result(record)
    assert jvlink_result is not None
    assert jvlink_result.popularity is None
    assert jvlink_result.prize_money is None

    result = parse_se_result(record, synthetic_result_fields=True)
    assert result is not None
    assert result.popularity == 3
    assert result.prize_money == 12000000


def test_parse_se_result_ignores_implausible_popularity_and_prize() -> None:
    """人気・本賞金が無い（予約領域が空白の）合成レコードでは None を返す。"""

    class _NoPrizeConnection(_Connection):
        se = [
            {
                "DATA_KUBUN": "7",
                "KAISAI_NEN": "2026",
                "KAISAI_GAPPI": "0712",
                "KEIBAJO_CODE": "02",
                "KAISAI_KAIJI": "01",
                "KAISAI_NICHIJI": "03",
                "RACE_BANGO": "09",
                "WAKUBAN": "1",
                "UMABAN": "01",
                "KETTO_TOROKU_BANGO": "2021100001",
                "BAMEI": "テストホース",
                "SEIBETSU_CODE": "1",
                "CHOKYOSHI_CODE": "01001",
                "KISHU_CODE": "02001",
                "BATAIJU": "480",
                "KAKUTEI_CHAKUJUN": "01",
                "SOHA_TIME": "1344",
                "KOHAN_3F": "345",
            }
        ]

    client = MyKeibaDbClient(connection=_NoPrizeConnection())
    record = next(client.iter_se_records("20260712", "20260712"))

    result = parse_se_result(record)
    assert result is not None
    assert result.popularity is None
    assert result.prize_money is None


def test_iter_master_records_build_from_mysql_rows() -> None:
    client = MyKeibaDbClient(connection=_Connection())

    assert "テストホース" in next(client.iter_um_records())
    assert "テスト騎手" in next(client.iter_ks_records())
    assert "テスト調教師" in next(client.iter_ch_records())
