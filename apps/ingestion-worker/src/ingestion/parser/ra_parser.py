"""RA レコード（レース詳細）パーサ。

JV-Data仕様書 Ver.3.0.0 — RA レコード（レース詳細）のフィールド定義。

NOTE: バイト位置は JV-Data 仕様書の公式ドキュメントに基づく。
      実際の JV-Link 出力との照合を推奨する（特に result 部分）。

RA レコード総バイト数: 856 bytes（改行を含む場合は 857 or 858）
エンコード: Shift-JIS（ただし JV-Link は Unicode 変換済み文字列を返すため str として処理）
"""

from __future__ import annotations

from ingestion.models import RaceEntriesRecord
from ingestion.parser.common import (
    _i,
    _s,
    build_race_key,
    decode_baba,
    decode_tenko,
    decode_track,
    parse_race_date,
)

# ---------------------------------------------------------------------------
# RA レコード フィールド定義（バイト位置、0-indexed・end-exclusive）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "RA"
# [2:3]   DataKubun (1=新規, 2=更新, 0=削除)
# [3:11]  MakeDate (YYYYMMDD)
# [11:13] JyoCd
# [13:15] Kaiji（開催回）
# [15:17] Nichiji（開催日）
# [17:19] RaceNo
# [19:20] YoubiCd
# [20:24] Nen (YYYY)
# [24:28] MonthDay (MMDD)
# [28:32] Kyori（距離 m）
# [32:33] ToraCd (1=芝, 2=ダート, 3=障害)
# [33:34] CoursCd
# [34:35] TenkoCd (1=晴, 2=曇, 3=小雨, 4=雨, 5=小雪, 6=雪)
# [35:36] SibaBabaJotaiCd (1=良, 2=稍重, 3=重, 4=不良)
# [36:37] DirtBabaJotaiCd
# [37:39] GradeCd ("  "=一般, "A1"=G1, "A2"=G2, "A3"=G3, "L "=Listed)
# [39:89] RaceName（50 bytes）
# [89:91] Tosu（出走頭数）
# [91:141] RaceClass（レースクラス名、50 bytes）
# ---------------------------------------------------------------------------


def parse_ra(record: str) -> RaceEntriesRecord | None:
    """RA 固定長レコード文字列を RaceEntriesRecord に変換する。

    DataKubun "0"（削除）の場合は None を返す。
    """
    if len(record) < 91:
        raise ValueError(f"RA レコードが短すぎます: {len(record)} bytes")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "RA":
        raise ValueError(f"RecordSpec が RA ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None  # 削除レコード

    jyo_cd = _s(record, 11, 13)
    kaiji = _s(record, 13, 15)
    nichiji = _s(record, 15, 17)
    race_no = _s(record, 17, 19)
    nen = _s(record, 20, 24)
    month_day = _s(record, 24, 28)

    race_key = build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)
    race_date = parse_race_date(nen, month_day)

    kyori = _i(record, 28, 32)
    tora_cd = _s(record, 32, 33)
    track_type = decode_track(tora_cd)

    tenko_cd = _s(record, 34, 35)
    weather = decode_tenko(tenko_cd)

    # 芝/ダートどちらの馬場状態を使うかはトラック種別で判断
    if tora_cd == "2":
        baba_cd = _s(record, 36, 37)
    else:
        baba_cd = _s(record, 35, 36)
    track_condition = decode_baba(baba_cd)

    grade_raw = _s(record, 37, 39)
    grade = grade_raw if grade_raw not in ("", "  ") else None

    race_name = _s(record, 39, 89)
    tosu = _i(record, 89, 91)
    race_class = _s(record, 91, 141) if len(record) >= 141 else race_name

    return RaceEntriesRecord(
        race_key=race_key,
        race_date=race_date,
        jyo_cd=jyo_cd,
        distance_m=kyori,
        track_type=track_type,
        field_size=tosu,
        track_condition=track_condition,
        weather=weather,
        grade=grade,
        race_class=race_class or race_name or None,
    )
