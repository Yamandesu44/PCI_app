"""RA レコード（レース詳細）パーサ。

JV-Data Ver.4.9 実データより逆算したフィールド定義。
Ver.3.0.0 からの変更点:
  - [11:19] KaisaiNengappi（開催年月日 YYYYMMDD）が追加された
  - 旧 Nen[20:24] / MonthDay[24:28] は KaisaiNengappi に統合
  - JyoCd 以降が +8 にシフト
  - RaceName は [32:82] から始まる（40文字ログで実測確認済み）
  - ToraCd / TenkoCd / BabaCd / GradeCd の新オフセット未確定（dump_records で調査中）

RA レコード総バイト数: 856 bytes（改行を含む場合は 857 or 858）
エンコード: Shift-JIS（ただし JV-Link は Unicode 変換済み文字列を返すため str として処理）
"""

from __future__ import annotations

from ingestion.models import RaceEntriesRecord
from ingestion.parser.common import (
    _i,
    _s,
    build_race_key,
    parse_race_date,
)

# ---------------------------------------------------------------------------
# RA レコード フィールド定義（Ver.4.9 実測オフセット）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "RA"
# [2:3]   DataKubun (1=新規, 2=更新, 0=削除)
# [3:11]  MakeDate (作成日 YYYYMMDD)
# [11:19] KaisaiNengappi（開催年月日 YYYYMMDD）← Ver.4.9 追加
# [19:21] JyoCd
# [21:23] Kaiji（開催回）
# [23:25] Nichiji（開催日）
# [25:27] RaceNo
# [27:28] YoubiCd
# [28:32] ??? (実データ確認中: 非グレードは "0000"、G2は "0074" — 距離でも等級でもない可能性)
# [32:82] RaceName（50 Unicode chars / 40文字ログで開始位置を実測確認済み）
# [82:84] Tosu（出走頭数）
# [84:134] RaceClass（レースクラス名）
# ToraCd / TenkoCd / BabaCd / GradeCd: dump_records.py で全体確認後に追記予定
# ---------------------------------------------------------------------------


def parse_ra(record: str) -> RaceEntriesRecord | None:
    """RA 固定長レコード文字列を RaceEntriesRecord に変換する。

    DataKubun の意味（実データで確認済み）:
      "1": 新規  "2": 更新  "7": 確定（レース後）  "0": 削除
    DataKubun "0"（削除）の場合は None を返す。
    """
    if len(record) < 84:
        raise ValueError(f"RA レコードが短すぎます: {len(record)} bytes")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "RA":
        raise ValueError(f"RecordSpec が RA ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None  # 削除レコード

    # 開催年月日は KaisaiNengappi [11:19] から取り出す
    nen = _s(record, 11, 15)
    month_day = _s(record, 15, 19)

    jyo_cd = _s(record, 19, 21)
    kaiji = _s(record, 21, 23)
    nichiji = _s(record, 23, 25)
    race_no = _s(record, 25, 27)

    race_key = build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)
    race_date = parse_race_date(nen, month_day)

    # [28:32] の正体は dump_records で確認中。100-4000m の範囲のみ距離として採用する。
    kyori_raw = _i(record, 28, 32)
    kyori = kyori_raw if 100 <= kyori_raw <= 4000 else 0

    # ToraCd / TenkoCd / BabaCd / GradeCd はオフセット未確定 → dump_records 確認後に追記
    track_type = "芝"
    weather = None
    track_condition = None
    grade = None

    race_name = _s(record, 32, 82) if len(record) >= 82 else _s(record, 32, len(record))
    tosu = _i(record, 82, 84) if len(record) >= 84 else 0
    race_class = _s(record, 84, 134) if len(record) >= 134 else race_name

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
