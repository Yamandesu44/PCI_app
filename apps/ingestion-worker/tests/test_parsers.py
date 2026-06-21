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
from ingestion.parser.jv_spec import RA_RECORD_BYTES, SE_RECORD_BYTES
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

def _ra_put(buf: bytearray, off: int, s: str) -> None:
    """CP932 バイト列としてフィールドを byte オフセットへ書き込む（全角=2byte）。"""
    b = s.encode("cp932")
    buf[off:off + len(b)] = b


def _ra(
    jyo_cd: str = "05",
    kaiji: str = "01",
    nichiji: str = "01",
    race_no: str = "01",
    nen: str = "2026",
    month_day: str = "0618",
    kyori: int = 1600,
    race_name: str = "3歳未勝利",
) -> str:
    """RA レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: Hondai[33:93], Kyori[697:701], TrackCD[705:707]='17'(芝内回り)。
    field_size/weather/track_condition の byte 位置は未確定のため省略（0/None を返す）。
    """
    buf = bytearray(b" " * RA_RECORD_BYTES)
    _ra_put(buf, 0, "RA")
    _ra_put(buf, 2, "1")                       # DataKubun=1（新規）
    _ra_put(buf, 3, "20260618")                # MakeDate
    _ra_put(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _ra_put(buf, 19, jyo_cd)
    _ra_put(buf, 21, kaiji)
    _ra_put(buf, 23, nichiji)
    _ra_put(buf, 25, race_no)
    _ra_put(buf, 27, "10")                     # YoubiCD (2byte)
    _ra_put(buf, 29, "0000")                   # TokuNum (一般)
    _ra_put(buf, 33, race_name)                # Hondai（全角30字まで）
    _ra_put(buf, 697, f"{kyori:04d}")          # Kyori CONFIRMED
    _ra_put(buf, 705, "17")                    # TrackCD='17'(芝内回り) CONFIRMED
    return buf.decode("cp932")


def _se_put(buf: bytearray, off: int, s: str) -> None:
    """CP932 バイト列としてフィールドを byte オフセットへ書き込む（全角=2byte）。"""
    b = s.encode("cp932")
    buf[off:off + len(b)] = b


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
    trainer_code: str = "00001",
    jockey_code: str = "00001",
) -> str:
    """SE 出走前レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: Bamei[40:76], SexCD[78:79], ChokyosiCode[85:90]（名略称[90:98]直前）,
               KisyuCode[296:301]（名略称[306:314]直前）。
    """
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _se_put(buf, 0, "SE")
    _se_put(buf, 2, "1")                       # DataKubun=1（新規・出走前）
    _se_put(buf, 3, "20260617")                # MakeDate
    _se_put(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _se_put(buf, 19, jyo_cd)
    _se_put(buf, 21, kaiji)
    _se_put(buf, 23, nichiji)
    _se_put(buf, 25, race_no)
    _se_put(buf, 27, str(frame_no)[:1])        # Wakuban
    _se_put(buf, 28, f"{horse_no:02d}")        # Umaban
    _se_put(buf, 30, ketto_num[:10])           # KettoNum
    _se_put(buf, 40, uma_name)                 # Bamei（全角）
    _se_put(buf, 78, sex_cd)                   # SexCD
    _se_put(buf, 85, trainer_code[:5])         # ChokyosiCode
    _se_put(buf, 90, "調教師名")               # 調教師名略称（錨）
    _se_put(buf, 296, jockey_code[:5])         # KisyuCode
    _se_put(buf, 306, "騎手名")                # 騎手名略称（錨）
    return buf.decode("cp932")


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
) -> str:
    """SE 確定後レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: KakuteiJyuni[334:336], Time[338:342] MSSf, 上り3F[390:393]。
    走破タイムは 分1+秒2+1/10秒1 の MSSf 形式（例 94.4s → '1344'）。
    """
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _se_put(buf, 0, "SE")
    _se_put(buf, 2, "7")                       # DataKubun=7（確定・実測区分）
    _se_put(buf, 3, "20260618")                # MakeDate
    _se_put(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _se_put(buf, 19, jyo_cd)
    _se_put(buf, 21, kaiji)
    _se_put(buf, 23, nichiji)
    _se_put(buf, 25, race_no)
    _se_put(buf, 28, f"{horse_no:02d}")        # Umaban

    # 走破タイム MSSf: 分1 + 秒2 + 1/10秒1
    minutes = int(race_time_s // 60)
    seconds = int(race_time_s % 60)
    tenths = round((race_time_s - int(race_time_s)) * 10)
    time_mssf = f"{minutes}{seconds:02d}{tenths}"   # 4桁

    # 上り3F: 3桁 1/10秒（33.9s → '339'）
    agari_tenths = round(agari_3f_s * 10)

    _se_put(buf, 334, f"{finish_pos:02d}")     # KakuteiJyuni
    _se_put(buf, 338, time_mssf)               # Time
    _se_put(buf, 390, f"{agari_tenths:03d}")   # HaronTimeL3
    return buf.decode("cp932")


def _um(
    ketto: str = "2023100001", name: str = "テストホース", sex: str = "1", birth_year: int = 2023
) -> str:
    """Ver.4.9 UM レコードのテスト用フィクスチャ。
    実測オフセット: ketto[12:22], birth[38:46], name[46:64], sex[182:183]
    """
    def p(v: str, w: int) -> str:
        return v.ljust(w)[:w]

    um = (
        "UM"                         # [0:2]
        + "1"                        # [2:3]  DataKubun
        + "20260101"                 # [3:11] MakeDate
        + " "                        # [11:12] UmaKigo
        + p(ketto, 10)              # [12:22] KettoNum
        + "00000000"                 # [22:30] 追加日付1
        + "00000000"                 # [30:38] 追加日付2
        + f"{birth_year}0101"        # [38:46] 生年月日 (YYYY0101)
        + p(name, 18)               # [46:64] UmaName
        + p(name, 36)               # [64:100] UmaNameKana (ダミー)
        + " " * 60                  # [100:160] UmaNameEng (ダミー)
        + "0"                        # [160:161] ZaikyuFlag
        + " " * 19                  # [161:180] Reserved
        + "00"                       # [180:182] UmaKigoCD
        + sex                        # [182:183] SexCD
    )
    return um.ljust(200)


def _ks(code: str = "0001", name: str = "テスト騎手") -> str:
    """Ver.4.9 KS レコードのテスト用フィクスチャ。
    実測オフセット: code[11:16], name[41:58]
    """
    ks = (
        "KS"                         # [0:2]
        + "1"                        # [2:3]  DataKubun
        + "20260101"                 # [3:11] MakeDate
        + code.ljust(5)[:5]         # [11:16] KisyuCode (5桁)
        + " "                        # [16:17] フラグ
        + "00000000"                 # [17:25] 追加日付1
        + "00000000"                 # [25:33] 追加日付2
        + "00000000"                 # [33:41] 生年月日
        + name.ljust(17)[:17]       # [41:58] 騎手氏名
    )
    return ks.ljust(100)


def _ch(code: str = "0001", name: str = "テスト調教師") -> str:
    """Ver.4.9 CH レコードのテスト用フィクスチャ。
    実測オフセット: code[11:16], name[41:58]
    """
    ch = (
        "CH"                         # [0:2]
        + "1"                        # [2:3]  DataKubun
        + "20260101"                 # [3:11] MakeDate
        + code.ljust(5)[:5]         # [11:16] ChokyosiCode (5桁)
        + " "                        # [16:17] フラグ
        + "00000000"                 # [17:25] 追加日付1
        + "00000000"                 # [25:33] 追加日付2
        + "00000000"                 # [33:41] 生年月日
        + name.ljust(17)[:17]       # [41:58] 調教師氏名
    )
    return ch.ljust(100)


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

    def test_distance_invalid_clamped_to_zero(self) -> None:
        # 100m未満は不正値（例: 実データのグレードコード "0074"）→ 0 に丸める
        result = parse_ra(_ra(kyori=74))
        assert result is not None
        assert result.distance_m == 0

    def test_track_type_turf_from_trackcd(self) -> None:
        # TrackCD='17'(芝内回り) を実測確定 → decode_track で "芝"
        result = parse_ra(_ra())
        assert result is not None
        assert result.track_type == "芝"

    def test_weather_unknown(self) -> None:
        # TenkoCd オフセット未確定のため None を返す
        result = parse_ra(_ra())
        assert result is not None
        assert result.weather is None

    def test_track_condition_unknown(self) -> None:
        # BabaCd オフセット未確定のため None を返す
        result = parse_ra(_ra())
        assert result is not None
        assert result.track_condition is None

    def test_grade_unknown(self) -> None:
        # GradeCd オフセット未確定のため None を返す
        result = parse_ra(_ra())
        assert result is not None
        assert result.grade is None

    def test_field_size_unknown_is_zero(self) -> None:
        # SyussoTosu の byte 位置は未特定のため暫定 0（RA --map で特定予定）
        result = parse_ra(_ra())
        assert result is not None
        assert result.field_size == 0

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
        rec = _se_entry(jockey_code="01184")
        result = parse_se_entry(rec)
        assert result is not None
        assert result.jockey_code == "01184"

    def test_trainer_code(self) -> None:
        rec = _se_entry(trainer_code="00420")
        result = parse_se_entry(rec)
        assert result is not None
        assert result.trainer_code == "00420"

    def test_weight_default(self) -> None:
        # 馬体重は出馬表段階では未発表のため暫定デフォルト 460
        rec = _se_entry()
        result = parse_se_entry(rec)
        assert result is not None
        assert result.weight == 460.0

    def test_result_record_returns_none(self) -> None:
        rec = _se_result()
        result = parse_se_entry(rec)
        assert result is None

    def test_race_key_extraction(self) -> None:
        rec = _se_entry(
            nen="2026", month_day="0620", jyo_cd="05", kaiji="01", nichiji="01", race_no="03"
        )
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

    def test_corners_unresolved_returns_none(self) -> None:
        # コーナー通過順位の実バイト位置は未特定（旧 [291:299] は騎手コード領域の
        # 誤認だった）。2レコード目で差分校正するまで現状は None を返す。
        result = parse_se_result(_se_result())
        assert result is not None
        assert result.corner_1 is None
        assert result.corner_2 is None
        assert result.corner_3 is None
        assert result.corner_4 is None

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
