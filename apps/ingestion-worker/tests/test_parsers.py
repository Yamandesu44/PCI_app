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

def _put_field(buf: bytearray, off: int, s: str) -> None:
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
    condition_name: str | None = None,
    haron_s3: int | None = None,
    haron_l3: int | None = None,
    grade_code: str | None = None,
) -> str:
    """RA レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: Hondai[33:93], Kyori[697:701], TrackCD[705:707]='17'(芝内回り)。
    field_size/weather/track_condition の byte 位置は未確定のため省略（0/None を返す）。
    haron_s3/haron_l3: HaronTime の生整数値（例: 339 = 33.9s）。None の場合は '   '（空白）。
    """
    buf = bytearray(b" " * RA_RECORD_BYTES)
    _put_field(buf, 0, "RA")
    _put_field(buf, 2, "1")                       # DataKubun=1（新規）
    _put_field(buf, 3, "20260618")                # MakeDate
    _put_field(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _put_field(buf, 19, jyo_cd)
    _put_field(buf, 21, kaiji)
    _put_field(buf, 23, nichiji)
    _put_field(buf, 25, race_no)
    _put_field(buf, 27, "10")                     # YoubiCD (2byte)
    _put_field(buf, 29, "0000")                   # TokuNum (一般)
    _put_field(buf, 33, race_name)                # Hondai（全角30字まで）
    if condition_name is not None:
        _put_field(buf, 623, condition_name)      # JyokenName（競走条件名称）
    if grade_code is not None:
        _put_field(buf, 615, grade_code)          # GradeCD（JV-Data仕様）
    _put_field(buf, 697, f"{kyori:04d}")          # Kyori CONFIRMED
    _put_field(buf, 705, "17")                    # TrackCD='17'(芝内回り) CONFIRMED
    if haron_s3 is not None:
        _put_field(buf, 969, f"{haron_s3:03d}")  # HaronTimeS3 [969:972]
    if haron_l3 is not None:
        _put_field(buf, 975, f"{haron_l3:03d}")  # HaronTimeL3 [975:978]
    return buf.decode("cp932")


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
    data_kubun: str = "1",
) -> str:
    """SE 出走前レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: Bamei[40:76], SexCD[78:79], ChokyosiCode[85:90]（名略称[90:98]直前）,
               KisyuCode[296:301]（名略称[306:314]直前）。
    data_kubun で区分を差し替え可能（"3"=取消/除外 など）。
    """
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _put_field(buf, 0, "SE")
    _put_field(buf, 2, data_kubun[:1])            # DataKubun（既定 "1"=新規・出走前）
    _put_field(buf, 3, "20260617")                # MakeDate
    _put_field(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _put_field(buf, 19, jyo_cd)
    _put_field(buf, 21, kaiji)
    _put_field(buf, 23, nichiji)
    _put_field(buf, 25, race_no)
    _put_field(buf, 27, str(frame_no)[:1])        # Wakuban
    _put_field(buf, 28, f"{horse_no:02d}")        # Umaban
    _put_field(buf, 30, ketto_num[:10])           # KettoNum
    _put_field(buf, 40, uma_name)                 # Bamei（全角）
    _put_field(buf, 78, sex_cd)                   # SexCD
    _put_field(buf, 85, trainer_code[:5])         # ChokyosiCode
    _put_field(buf, 90, "調教師名")               # 調教師名略称（錨）
    _put_field(buf, 296, jockey_code[:5])         # KisyuCode
    _put_field(buf, 306, "騎手名")                # 騎手名略称（錨）
    return buf.decode("cp932")


def _se_result(
    jyo_cd: str = "05",
    kaiji: str = "01",
    nichiji: str = "01",
    race_no: str = "01",
    nen: str = "2026",
    month_day: str = "0618",
    horse_no: int = 3,
    frame_no: int = 3,
    ketto_num: str = "2023100003",
    trainer_code: str = "00003",
    jockey_code: str = "00003",
    ba_taijyu: int = 480,
    finish_pos: int = 1,
    race_time_s: float = 94.4,
    agari_3f_s: float = 33.9,
    corners: tuple[int, int, int, int] | None = None,
) -> str:
    """SE 確定後レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実データの確定レコードは出走情報（枠番・馬番・血統・騎手・調教師・馬体重）と
    成績（着順・タイム・上り）を両方含む。本フィクスチャもそれを再現する。
    実測 byte: ChokyosiCode[85:90], KisyuCode[296:301], BaTaijyu[324:327],
               KakuteiJyuni[334:336], Time[338:342] MSSf, 上り3F[390:393]。
    走破タイムは 分1+秒2+1/10秒1 の MSSf 形式（例 94.4s → '1344'）。
    corners: (c1, c2, c3, c4) を指定するとコーナー通過順位を [356:364] に書き込む（実データ候補）。
    """
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _put_field(buf, 0, "SE")
    _put_field(buf, 2, "7")                       # DataKubun=7（確定・実測区分）
    _put_field(buf, 3, "20260618")                # MakeDate
    _put_field(buf, 11, f"{nen}{month_day}")      # KaisaiNengappi
    _put_field(buf, 19, jyo_cd)
    _put_field(buf, 21, kaiji)
    _put_field(buf, 23, nichiji)
    _put_field(buf, 25, race_no)
    _put_field(buf, 27, str(frame_no)[:1])        # Wakuban
    _put_field(buf, 28, f"{horse_no:02d}")        # Umaban
    _put_field(buf, 30, ketto_num[:10])           # KettoNum
    _put_field(buf, 85, trainer_code[:5])         # ChokyosiCode
    _put_field(buf, 296, jockey_code[:5])         # KisyuCode

    # 走破タイム MSSf: 分1 + 秒2 + 1/10秒1
    minutes = int(race_time_s // 60)
    seconds = int(race_time_s % 60)
    tenths = round((race_time_s - int(race_time_s)) * 10)
    time_mssf = f"{minutes}{seconds:02d}{tenths}"   # 4桁

    # 上り3F: 3桁 1/10秒（33.9s → '339'）
    agari_tenths = round(agari_3f_s * 10)

    _put_field(buf, 324, f"{ba_taijyu:03d}")      # BaTaijyu（馬体重）
    _put_field(buf, 334, f"{finish_pos:02d}")     # KakuteiJyuni
    _put_field(buf, 338, time_mssf)               # Time
    _put_field(buf, 390, f"{agari_tenths:03d}")   # HaronTimeL3

    # コーナー通過順位 [356:364]: 各 2byte。実データ候補オフセット。
    if corners is not None:
        c1, c2, c3, c4 = corners
        _put_field(buf, 356, f"{c1:02d}")
        _put_field(buf, 358, f"{c2:02d}")
        _put_field(buf, 360, f"{c3:02d}")
        _put_field(buf, 362, f"{c4:02d}")

    return buf.decode("cp932")


def _um(
    ketto: str = "2023100001", name: str = "テストホース", sex: str = "1", birth_year: int = 2023
) -> str:
    """UM レコードのテスト用フィクスチャ（byte 正確 / 実測オフセット）。

    実測 byte: ketto[12:22], birth[38:42], name[46:82]（全角18字）, sex[182:183]。
    SexCD は全角名・カナ名・英字名の後 byte[182:183]。
    """
    buf = bytearray(b" " * 200)
    _put_field(buf, 0, "UM")
    _put_field(buf, 2, "1")                    # DataKubun
    _put_field(buf, 3, "20260101")             # MakeDate
    _put_field(buf, 12, ketto[:10])            # KettoNum
    _put_field(buf, 38, f"{birth_year}0101")   # 生年月日 YYYYMMDD
    _put_field(buf, 46, name)                  # UmaName（全角）
    _put_field(buf, 180, "00")                 # UmaKigoCD
    _put_field(buf, 182, sex)                  # SexCD
    return buf.decode("cp932")


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

    def test_placeholder_race_name_is_ignored(self) -> None:
        result = parse_ra(_ra(race_name="@"))
        assert result is not None
        assert result.race_class is None

    def test_condition_name_used_when_hondai_is_placeholder(self) -> None:
        result = parse_ra(_ra(race_name="@", condition_name="3歳未勝利"))
        assert result is not None
        assert result.race_class == "3歳未勝利"

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
        result = parse_ra(_ra())
        assert result is not None
        assert result.grade is None

    @pytest.mark.parametrize(
        ("code", "expected"),
        [("A", "G1"), ("B", "G2"), ("C", "G3"), ("F", "J・G1"), ("L", "L")],
    )
    def test_grade_code_is_decoded(self, code: str, expected: str) -> None:
        result = parse_ra(_ra(grade_code=code))
        assert result is not None
        assert result.grade == expected

    def test_field_size_unknown_is_zero(self) -> None:
        # SyussoTosu の byte 位置は未特定のため暫定 0（RA --map で特定予定）
        result = parse_ra(_ra())
        assert result is not None
        assert result.field_size == 0

    def test_jyo_cd(self) -> None:
        result = parse_ra(_ra(jyo_cd="05"))
        assert result is not None
        assert result.jyo_cd == "05"

    def test_harontime_valid_values_parsed(self) -> None:
        # 芝レースの典型値: S3=33.9s(339), L3=34.6s(346)
        result = parse_ra(_ra(haron_s3=339, haron_l3=346))
        assert result is not None
        assert result.race_s3f == pytest.approx(33.9, abs=0.05)
        assert result.race_l3f == pytest.approx(34.6, abs=0.05)

    def test_harontime_l3_too_small_returns_none(self) -> None:
        # ダートの誤読典型値 '010'(=1.0s) は 25s 未満 → None
        result = parse_ra(_ra(haron_s3=339, haron_l3=10))
        assert result is not None
        assert result.race_s3f == pytest.approx(33.9, abs=0.05)
        assert result.race_l3f is None

    def test_harontime_too_large_returns_none(self) -> None:
        # '999'(=99.9s) は 50s 超 → None
        result = parse_ra(_ra(haron_s3=339, haron_l3=999))
        assert result is not None
        assert result.race_l3f is None

    def test_harontime_zero_returns_none(self) -> None:
        # '000' (未取得 or 出走前) → None
        result = parse_ra(_ra(haron_s3=0, haron_l3=0))
        assert result is not None
        assert result.race_s3f is None
        assert result.race_l3f is None

    def test_harontime_absent_returns_none(self) -> None:
        # HaronTime を設定しない（空白）→ None
        result = parse_ra(_ra())
        assert result is not None
        assert result.race_s3f is None
        assert result.race_l3f is None

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

    def test_confirmed_record_is_entryable(self) -> None:
        # 確定後('7')レコードもエントリ情報を持つため EntryRecord を生成する。
        # 過去レース（出走表が確定へ置き換わったデータ）の出走表再構成に必須。
        rec = _se_result(
            horse_no=3, frame_no=3, ketto_num="2023100003",
            jockey_code="01184", trainer_code="00420",
        )
        result = parse_se_entry(rec)
        assert result is not None
        assert result.horse_no == 3
        assert result.frame_no == 3
        assert result.ketto_num == "2023100003"
        assert result.jockey_code == "01184"
        assert result.trainer_code == "00420"

    def test_weight_from_confirmed_bataijyu(self) -> None:
        # 確定後レコードは BaTaijyu[324:327] に実馬体重を持つ。
        rec = _se_result(ba_taijyu=486)
        result = parse_se_entry(rec)
        assert result is not None
        assert result.weight == 486.0

    def test_cancel_record_returns_none(self) -> None:
        # 取消/除外('3')は出走しないためエントリにしない。
        rec = _se_entry(data_kubun="3")
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

    def test_body_weight(self) -> None:
        result = parse_se_result(_se_result(ba_taijyu=486))
        assert result is not None
        assert result.body_weight == 486.0

    def test_corners_absent_returns_none(self) -> None:
        """コーナーデータを埋め込まない（空白）レコードは None を返す。"""
        result = parse_se_result(_se_result())
        assert result is not None
        assert result.corner_1 is None
        assert result.corner_2 is None
        assert result.corner_3 is None
        assert result.corner_4 is None

    def test_corners_extracted_from_hypothesis_offset(self) -> None:
        """実データ候補オフセット [356:364] にコーナーを書き込むと正しく抽出される。"""
        rec = _se_result(corners=(5, 5, 4, 2))
        result = parse_se_result(rec)
        assert result is not None
        assert result.corner_1 == 5
        assert result.corner_2 == 5
        assert result.corner_3 == 4
        assert result.corner_4 == 2

    def test_corner_zero_returns_none(self) -> None:
        """コーナー順位 '00' は有効範囲外（0）→ None を返す。"""
        rec = _se_result(corners=(0, 0, 0, 0))
        result = parse_se_result(rec)
        assert result is not None
        assert result.corner_4 is None

    def test_corner_out_of_range_returns_none(self) -> None:
        """コーナー順位が 19 以上（フルゲート超）→ None を返す。"""
        rec = _se_result(corners=(19, 19, 19, 19))
        result = parse_se_result(rec)
        assert result is not None
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

    def test_implausibly_fast_agari_returns_none(self) -> None:
        """上がり3Fが物理的にありえない速さ（600mを13.7秒）→ データ異常として None。

        2026-07-04 小倉1R (mykeibadb KOHAN_3F='137') で実際に観測された異常値の再現。
        """
        rec = _se_result(agari_3f_s=13.7)
        result = parse_se_result(rec)
        assert result is None

    def test_implausibly_slow_agari_returns_none(self) -> None:
        """上がり3Fが異常に遅い（60秒）→ データ異常として None。"""
        rec = _se_result(agari_3f_s=60.0)
        result = parse_se_result(rec)
        assert result is None

    def test_agari_at_plausible_bounds_accepted(self) -> None:
        """妥当範囲の境界値（25秒・55秒）は正常に採用される。"""
        assert parse_se_result(_se_result(agari_3f_s=25.0)) is not None
        assert parse_se_result(_se_result(agari_3f_s=55.0)) is not None


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
