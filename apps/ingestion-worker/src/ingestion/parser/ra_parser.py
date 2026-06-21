"""RA レコード（レース詳細）パーサ。

JV-Data 実データ（2026-06-13 函館1R, DataKubun=7 確定）で byte 位置を校正済み。
オフセットは jv_spec.RA_FIELDS と一致させること（単一の真実の場所）。

重要: JV-Link が返す Unicode 文字列は **CP932 バイト列に戻してから** byte オフセットで
切り出す。競走名 Hondai[33:93]（全角30字=60byte）以降、char スライスは破綻するため
全フィールドを to_cp932() 後の bytes 上で読む。

byte オフセット（実測確定分）:
  KaisaiNengappi [11:19]  YoubiCD [27:29]  TokuNum [29:33]
  Hondai         [33:93]  （競走名本題 全角30字）
  Kyori          [697:701] CONFIRMED 2026-06-13 函館1R = 1200
  TrackCD        [705:707] CONFIRMED 実測 '17'=芝内回り

未確定（実バイト位置未特定）→ 暫定デフォルト:
  SyussoTosu / TenkoCD / SibaBabaCD / DirtBabaCD → field_size=0, weather=None, track_condition=None
"""

from __future__ import annotations

from ingestion.models import RaceEntriesRecord
from ingestion.parser.common import (
    _bi,
    _bs,
    build_race_key,
    decode_track,
    parse_race_date,
    to_cp932,
)
from ingestion.parser.jv_spec import RA_RECORD_BYTES


def parse_ra(record: str) -> RaceEntriesRecord | None:
    """RA 固定長レコード文字列を RaceEntriesRecord に変換する。

    DataKubun の意味（実データで確認済み）:
      "1": 新規  "2": 更新  "7": 確定（レース後）  "0": 削除
    DataKubun "0"（削除）の場合は None を返す。
    """
    raw = to_cp932(record)
    if len(raw) < RA_RECORD_BYTES:
        raise ValueError(
            f"RA レコードが短すぎます: {len(raw)} bytes（{RA_RECORD_BYTES}必要）"
        )

    rec_spec = _bs(raw, 0, 2)
    if rec_spec != "RA":
        raise ValueError(f"RecordSpec が RA ではありません: {rec_spec!r}")

    data_kubun = _bs(raw, 2, 3)
    if data_kubun == "0":
        return None

    # 開催年月日 [11:19] — 全て半角のため char == byte
    nen = _bs(raw, 11, 15)
    month_day = _bs(raw, 15, 19)
    jyo_cd = _bs(raw, 19, 21)
    kaiji = _bs(raw, 21, 23)
    nichiji = _bs(raw, 23, 25)
    race_no = _bs(raw, 25, 27)

    race_key = build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)
    race_date = parse_race_date(nen, month_day)

    # 競走名 本題 [33:93] = 全角30字(60byte)。char スライスはここで破綻するため byte で読む。
    race_name = _bs(raw, 33, 93)

    # 距離 [697:701] — 実測確定（2026-06-13 函館1R = 1200m）
    dist_raw = _bi(raw, 697, 701)
    distance_m = dist_raw if 100 <= dist_raw <= 4000 else 0

    # トラックコード [705:707] — 実測確定（'17'=芝内回り）
    track_cd = _bs(raw, 705, 707)
    track_type = decode_track(track_cd)

    # 以下は実バイト位置が未確定のため暫定デフォルト。
    # RA の --map 結果から SyussoTosu/TenkoCD/BabaCd の正しい位置を特定すること。
    field_size = 0
    weather = None
    track_condition = None
    grade = None

    return RaceEntriesRecord(
        race_key=race_key,
        race_date=race_date,
        jyo_cd=jyo_cd,
        distance_m=distance_m,
        track_type=track_type,
        field_size=field_size,
        track_condition=track_condition,
        weather=weather,
        grade=grade,
        race_class=race_name or None,
    )
