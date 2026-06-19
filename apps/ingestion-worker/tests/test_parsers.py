"""JV-Link 固定長レコードパーサのユニットテスト（DB 不要）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import datetime

import pytest

from ingestion.parser.common import (
    build_race_key,
    decode_baba,
    decode_sex,
    decode_tenko,
    decode_track,
)
from ingestion.parser.master_parsers import parse_ch, parse_ks, parse_um
from ingestion.parser.ra_parser import parse_ra
from ingestion.parser.se_parser import (
    get_horse_info_from_se,
    parse_race_key_from_se,
    parse_se_entry,
    parse_se_result,
)

# ---------------------------------------------------------------------------
# ヘルパー: テスト用固定長レコード生成
# ---------------------------------------------------------------------------

def _ra(
    jyo_cd: str = "05",
    kaiji: str = "01",
    nichiji: str = "01",
    race_no: str = "01",
    nen: str = "2026",
    month_day: str = "0618",
    kyori: int = 1600,
    tora_cd: str = "1",
    tenko_cd: str = "1",
    baba_cd: str = "1",
    grade: str = "  ",
    race_name: str = "3歳未勝利",
    tosu: int = 10,
    race_class: str = "3歳未勝利",
) -> str:
    def p(v: str, w: int, fill: str = " ") -> str:
        return v.ljust(w)[:w]

    def pr(v: str, w: int) -> str:
        return v.rjust(w, "0")[:w]

    ra = (
        "RA"
        + "1"
        + f"{nen}{month_day}"
        + jyo_cd + kaiji + nichiji + race_no
        + "1"
        + nen + month_day
        + pr(str(kyori), 4)
        + tora_cd
        + "1"
        + tenko_cd
        + baba_cd + baba_cd
        + p(grade, 2)
        + p(race_name, 50)
        + pr(str(tosu), 2)
        + p(race_class, 50)
    )
    return ra.ljust(200)


def _se_entry(
    jyo_cd: str = "05",
    kaiji: str = "01",
    nichiji: str = "01",
    race_no: str = "01",
    nen: str = "2026",
    month_day: str = "0618",
    horse_no: int = 1,
    frame_no: int = 1,
    ketto_num: str = "2023100001",
    uma_name: str = "テストホース",
    sex_cd: str = "1",
    trainer_code: str = "0001",
    jockey_code: str = "0001",
    weight: int = 460,
) -> str:
    def p(v: str, w: int) -> str:
        return v.ljust(w)[:w]

    def pr(v: str, w: int) -> str:
        return v.rjust(w, "0")[:w]

    se = (
        "SE"
        + "1"
        + f"{nen}{month_day}"
        + jyo_cd + kaiji + nichiji + race_no
        + pr(str(horse_no), 2)
        + pr(str(frame_no), 2)
        + p(ketto_num, 10)
        + p(uma_name, 36)
        + " "  # UmaKigo
        + sex_cd
        + "01"
        + p(trainer_code, 4)
        + p("調教師テスト", 36)
        + "    "
        + p(jockey_code, 4)
        + p("騎手テスト", 36)
        + "55"
        + pr(str(weight), 4)
        + "00 "
    )
    return se.ljust(600)


def _se_result(
    jyo_cd: str = "05",
    kaiji: str = "01",
    nichiji: str = "01",
    race_no: str = "01",
    nen: str = "2026",
    month_day: str = "0618",
    horse_no: int = 3,
    finish_pos: int = 1,
    race_time_s: float = 94.4,
    agari_3f_s: float = 33.9,
    c1: int = 3,
    c2: int = 3,
    c3: int = 3,
    c4: int = 3,
) -> str:
    def p(v: str, w: int) -> str:
        return v.ljust(w)[:w]

    def pr(v: str, w: int) -> str:
        return v.rjust(w, "0")[:w]

    time_m = int(race_time_s // 60)
    time_s = int(race_time_s % 60)
    time_k = round((race_time_s - int(race_time_s)) * 10)
    agari_bu = int(agari_3f_s)
    agari_ko = round((agari_3f_s - agari_bu) * 10)

    header = (
        "SE"
        + "4"
        + f"{nen}{month_day}"
        + jyo_cd + kaiji + nichiji + race_no
        + pr(str(horse_no), 2)
        + "  "
        + " " * 10
        + " " * 36
        + " " * 2
        + " " * 2
        + " " * 4
        + " " * 36
        + " " * 4
        + " " * 4
        + " " * 36
        + " " * 2
        + " " * 4
        + "   "
    )
    result_fields = (
        pr(str(finish_pos), 2)
        + pr(str(time_m), 2)
        + pr(str(time_s), 2)
        + pr(str(time_k), 2)
        + pr(str(agari_bu), 2)
        + pr(str(agari_ko), 2)
        + pr(str(c1), 2)
        + pr(str(c2), 2)
        + pr(str(c3), 2)
        + pr(str(c4), 2)
    )
    se = header.ljust(580) + result_fields
    return se.ljust(620)


def _um(ketto: str = "2023100001", name: str = "テストホース", sex: str = "1", birth_year: int = 2023) -> str:
    def p(v: str, w: int) -> str:
        return v.ljust(w)[:w]

    um = (
        "UM"
        + "1"
        + "20260101"
        + " "
        + p(ketto, 10)
        + p(name, 36)
        + p(name, 36)
        + sex
        + str(birth_year)
        + " "
    )
    return um.ljust(200)


def _ks(code: str = "0001", name: str = "テスト騎手") -> str:
    return ("KS" + "1" + "20260101" + code.ljust(4)[:4] + name.ljust(36)[:36]).ljust(100)


def _ch(code: str = "0001", name: str = "テスト調教師") -> str:
    return ("CH" + "1" + "20260101" + code.ljust(4)[:4] + name.ljust(36)[:36]).ljust(100)


# ---------------------------------------------------------------------------
# TestCommon
# ---------------------------------------------------------------------------

class TestCommon:
    def test_build_race_key(self) -> None:
        key = build_race_key("05", "01", "01", "01", "2026", "0618")
        assert key == "2026061805010101"
        assert len(key) == 16

    def test_decode_track_turf(self) -> None:
        assert decode_track("1") == "芝"

    def test_decode_track_dirt(self) -> None:
        assert decode_track("2") == "ダート"

    def test_decode_tenko_sunny(self) -> None:
        assert decode_tenko("1") == "晴"

    def test_decode_tenko_rain(self) -> None:
        assert decode_tenko("4") == "雨"

    def test_decode_baba_good(self) -> None:
        assert decode_baba("1") == "良"

    def test_decode_baba_heavy(self) -> None:
        assert decode_baba("4") == "不良"

    def test_decode_sex_male(self) -> None:
        assert decode_sex("1") == "牡"

    def test_decode_sex_female(self) -> None:
        assert decode_sex("2") == "牝"


# ---------------------------------------------------------------------------
# TestRaParser
# ---------------------------------------------------------------------------

class TestRaParser:
    def test_race_key(self) -> None:
        rec = _ra()
        result = parse_ra(rec)
        assert result is not None
        assert result.race_key == "2026061805010101"

    def test_race_date(self) -> None:
        result = parse_ra(_ra())
        assert result is not None
        assert result.race_date == datetime.date(2026, 6, 18)

    def test_distance(self) -> None:
        result = parse_ra(_ra(kyori=1800))
        assert result is not None
        assert result.distance_m == 1800

    def test_track_type_turf(self) -> None:
        result = parse_ra(_ra(tora_cd="1"))
        assert result is not None
        assert result.track_type == "芝"

    def test_track_type_dirt(self) -> None:
        result = parse_ra(_ra(tora_cd="2"))
        assert result is not None
        assert result.track_type == "ダート"

    def test_weather(self) -> None:
        result = parse_ra(_ra(tenko_cd="1"))
        assert result is not None
        assert result.weather == "晴"

    def test_track_condition(self) -> None:
        result = parse_ra(_ra(baba_cd="1"))
        assert result is not None
        assert result.track_condition == "良"

    def test_field_size(self) -> None:
        result = parse_ra(_ra(tosu=8))
        assert result is not None
        assert result.field_size == 8

    def test_jyo_cd(self) -> None:
        result = parse_ra(_ra(jyo_cd="05"))
        assert result is not None
        assert result.jyo_cd == "05"

    def test_delete_record_returns_none(self) -> None:
        rec = _ra().replace("RA1", "RA0", 1)
        result = parse_ra(rec)
        assert result is None

    def test_wrong_spec_raises(self) -> None:
        rec = "XX" + _ra()[2:]
        with pytest.raises(ValueError, match="RecordSpec"):
            parse_ra(rec)

    def test_grade_none_for_blank(self) -> None:
        result = parse_ra(_ra(grade="  "))
        assert result is not None
        assert result.grade is None

    def test_grade_g1(self) -> None:
        result = parse_ra(_ra(grade="A1"))
        assert result is not None
        assert result.grade == "A1"


# ---------------------------------------------------------------------------
# TestSeEntryParser
# ---------------------------------------------------------------------------

class TestSeEntryParser:
    def test_horse_no(self) -> None:
        rec = _se_entry(horse_no=5)
        result = parse_se_entry(rec)
        assert result is not None
        assert result.horse_no == 5

    def test_frame_no(self) -> None:
        rec = _se_entry(frame_no=3)
        result = parse_se_entry(rec)
        assert result is not None
        assert result.frame_no == 3

    def test_ketto_num(self) -> None:
        rec = _se_entry(ketto_num="2023999001")
        result = parse_se_entry(rec)
        assert result is not None
        assert result.ketto_num == "2023999001"

    def test_jockey_code(self) -> None:
        rec = _se_entry(jockey_code="0099")
        result = parse_se_entry(rec)
        assert result is not None
        assert result.jockey_code == "0099"

    def test_trainer_code(self) -> None:
        rec = _se_entry(trainer_code="0042")
        result = parse_se_entry(rec)
        assert result is not None
        assert result.trainer_code == "0042"

    def test_weight(self) -> None:
        rec = _se_entry(weight=480)
        result = parse_se_entry(rec)
        assert result is not None
        assert result.weight == 480.0

    def test_result_record_returns_none(self) -> None:
        rec = _se_result()
        result = parse_se_entry(rec)
        assert result is None

    def test_race_key_extraction(self) -> None:
        rec = _se_entry(nen="2026", month_day="0620", jyo_cd="05", kaiji="01", nichiji="01", race_no="03")
        key = parse_race_key_from_se(rec)
        assert key == "2026062005010103"

    def test_horse_info_extraction(self) -> None:
        rec = _se_entry(ketto_num="2023100001", uma_name="テストホース", sex_cd="2")
        ketto, name, sex = get_horse_info_from_se(rec)
        assert ketto == "2023100001"
        assert "テスト" in name
        assert sex == "牝"


# ---------------------------------------------------------------------------
# TestSeResultParser
# ---------------------------------------------------------------------------

class TestSeResultParser:
    def test_finish_pos(self) -> None:
        rec = _se_result(finish_pos=1)
        result = parse_se_result(rec)
        assert result is not None
        assert result.finish_pos == 1

    def test_horse_no(self) -> None:
        rec = _se_result(horse_no=3)
        result = parse_se_result(rec)
        assert result is not None
        assert result.horse_no == 3

    def test_race_time_s(self) -> None:
        rec = _se_result(race_time_s=94.4)
        result = parse_se_result(rec)
        assert result is not None
        assert abs(result.race_time_s - 94.4) < 0.15  # 1/10秒精度

    def test_agari_3f_s(self) -> None:
        rec = _se_result(agari_3f_s=33.9)
        result = parse_se_result(rec)
        assert result is not None
        assert abs(result.agari_3f_s - 33.9) < 0.15

    def test_corner_4(self) -> None:
        rec = _se_result(c4=5)
        result = parse_se_result(rec)
        assert result is not None
        assert result.corner_4 == 5

    def test_entry_record_returns_none(self) -> None:
        rec = _se_entry()
        result = parse_se_result(rec)
        assert result is None

    def test_dnf_returns_none(self) -> None:
        """着順 99（中止）は None を返す。"""
        rec = _se_result(finish_pos=99)
        result = parse_se_result(rec)
        assert result is None


# ---------------------------------------------------------------------------
# TestMasterParsers
# ---------------------------------------------------------------------------

class TestUmParser:
    def test_ketto_num(self) -> None:
        result = parse_um(_um(ketto="2023100001"))
        assert result is not None
        assert result.ketto_num == "2023100001"

    def test_name(self) -> None:
        result = parse_um(_um(name="テストホース"))
        assert result is not None
        assert result.name == "テストホース"

    def test_sex_male(self) -> None:
        result = parse_um(_um(sex="1"))
        assert result is not None
        assert result.sex == "牡"

    def test_sex_female(self) -> None:
        result = parse_um(_um(sex="2"))
        assert result is not None
        assert result.sex == "牝"

    def test_birth_year(self) -> None:
        result = parse_um(_um(birth_year=2023))
        assert result is not None
        assert result.birth_year == 2023

    def test_delete_returns_none(self) -> None:
        rec = _um().replace("UM1", "UM0", 1)
        result = parse_um(rec)
        assert result is None

    def test_wrong_spec_raises(self) -> None:
        with pytest.raises(ValueError, match="RecordSpec|短すぎます"):
            parse_um("SE" + _um()[2:])


class TestKsParser:
    def test_code(self) -> None:
        result = parse_ks(_ks(code="0099"))
        assert result is not None
        assert result.code == "0099"

    def test_name(self) -> None:
        result = parse_ks(_ks(name="テスト騎手"))
        assert result is not None
        assert result.name == "テスト騎手"

    def test_delete_returns_none(self) -> None:
        rec = _ks().replace("KS1", "KS0", 1)
        result = parse_ks(rec)
        assert result is None


class TestChParser:
    def test_code(self) -> None:
        result = parse_ch(_ch(code="0042"))
        assert result is not None
        assert result.code == "0042"

    def test_name(self) -> None:
        result = parse_ch(_ch(name="テスト調教師"))
        assert result is not None
        assert result.name == "テスト調教師"

    def test_delete_returns_none(self) -> None:
        rec = _ch().replace("CH1", "CH0", 1)
        result = parse_ch(rec)
        assert result is None
