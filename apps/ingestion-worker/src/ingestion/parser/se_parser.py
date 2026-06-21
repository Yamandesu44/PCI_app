"""SE レコード（馬毎レース情報）パーサ。

JV-Data Ver.4.9 実データより逆算したフィールド定義。
Ver.3.0.0 からの変更点:
  - [11:19] KaisaiNengappi（開催年月日 YYYYMMDD）が追加され、以降が +8 シフト
  - 枠番(1桁) → 馬番(2桁) → 血統番号 の順（Ver.3 では別オフセット）

SE レコードは DataKubun によって内容が変わる:
  DataKubun "1": 新規（出走前）
  DataKubun "2": 更新（出馬表・騎手変更等）
  DataKubun "3": 取消/除外
  DataKubun "4": 確定（レース終了後の成績データ）

NOTE: 確定後フィールド（着順・走破タイム・通過順位）の Ver.4.9 オフセットは
      確定後 SE（DataKubun=4）の実データで再校正が必要（dump_records で確認）。
      出馬表データ（DataKubun=2）では本セクションは参照されない。
"""

from __future__ import annotations

from ingestion.models import EntryRecord, ResultRecord
from ingestion.parser.common import (
    _i,
    _opt_i,
    _s,
    build_race_key,
    decode_sex,
)

# ---------------------------------------------------------------------------
# SE レコード 共通ヘッダ（Ver.4.9 実測オフセット）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "SE"
# [2:3]   DataKubun
# [3:11]  MakeDate（作成日 YYYYMMDD）
# [11:19] KaisaiNengappi（開催年月日 YYYYMMDD）← Ver.4.9 追加。race_key はここから
# [19:21] JyoCd
# [21:23] Kaiji
# [23:25] Nichiji
# [25:27] RaceNo
# [27:28] Wakuban（枠番 1桁）
# [28:30] Umaban（馬番 2桁）
# [30:40] KettoNum（血統登録番号 10桁）
# [40:58] Bamei（馬名 18 Unicode chars = 36 bytes ShiftJIS）
# [58:60] UmaKigoCD
# [60:61] SexCD（1=牡 2=牝 3=騸）
# [61:62] HinsyuCD
# [62:64] KeiroCD
# [67:72] KisyuCode（騎手コード 5桁、騎手略称 [72:76] の直前）
# [77:82] ChokyosiCode（調教師コード 5桁、調教師名 [82:] の直前）
#
# 確定後フィールド (DataKubun="4"): ※確定後 SE 実データで要再校正
# [580:600] 着順/走破タイム/上がり3F/通過順位（Ver.3 暫定位置）
# ---------------------------------------------------------------------------

_KUBUN_ENTRY = frozenset({"1", "2"})     # 出走前・出馬表
_KUBUN_RESULT = frozenset({"4", "7"})   # 確定後（'4' 旧仕様 / '7' 実測確認: 2026-06-13 函館1R）
_KUBUN_CANCEL = frozenset({"3"})        # 取消/除外


def parse_race_key_from_se(record: str) -> str:
    """SE レコードからレースキーを取り出す（Ver.4.9 オフセット）。

    開催年月日は KaisaiNengappi [11:19] から取り出す（MakeDate ではない）。
    """
    nen = _s(record, 11, 15)        # KaisaiNengappi の YYYY
    month_day = _s(record, 15, 19)  # KaisaiNengappi の MMDD
    jyo_cd = _s(record, 19, 21)
    kaiji = _s(record, 21, 23)
    nichiji = _s(record, 23, 25)
    race_no = _s(record, 25, 27)
    return build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)


def parse_se_entry(record: str) -> EntryRecord | None:
    """SE レコード（出走前・出馬表）を EntryRecord に変換する。

    DataKubun が "1" または "2" の場合のみ変換。それ以外は None。
    """
    if len(record) < 82:
        raise ValueError(f"SE レコードが短すぎます: {len(record)} bytes（最低82必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun not in _KUBUN_ENTRY:
        return None

    frame_no = _i(record, 27, 28)   # Wakuban（枠番 1桁）
    horse_no = _i(record, 28, 30)   # Umaban（馬番 2桁）
    ketto_num = _s(record, 30, 40)
    jockey_code = _s(record, 67, 72)
    trainer_code = _s(record, 77, 82)

    # 馬体重は出馬表段階では未発表（"000"）。確定後 SE で取得するため暫定デフォルト。
    # TODO: 確定後 SE の BaTaijyu オフセット確定後に実装する。
    weight = 460.0

    return EntryRecord(
        horse_no=horse_no,
        frame_no=frame_no,
        ketto_num=ketto_num,
        weight=weight,
        jockey_code=jockey_code,
        trainer_code=trainer_code,
    )


def parse_se_result(record: str) -> ResultRecord | None:
    """SE レコード（確定後）を ResultRecord に変換する。

    DataKubun が "4" の場合のみ変換。着順 "99"（中止/失格）は None を返す。

    NOTE: 着順以降の成績フィールド位置は Ver.4.9 確定後 SE で要再校正。
    """
    if len(record) < 600:
        raise ValueError(f"SE 確定レコードが短すぎます: {len(record)} bytes")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun not in _KUBUN_RESULT:
        return None

    horse_no = _i(record, 28, 30)  # Umaban（Ver.4.9）

    # 着順（"99" = 中止/失格）
    chaku_raw = _s(record, 580, 582)
    if not chaku_raw.isdigit() or int(chaku_raw) >= 99:
        return None
    finish_pos = int(chaku_raw)

    # 走破タイム: 分(2)+秒(2)+1/10秒(2) → 秒に変換
    time_m = _i(record, 582, 584)
    time_s = _i(record, 584, 586)
    time_k = _i(record, 586, 588)
    race_time_s = time_m * 60.0 + time_s + time_k / 10.0

    # 上がり3F: 秒(2)+1/10秒(2)
    agari_bu = _i(record, 588, 590)
    agari_ko = _i(record, 590, 592)
    agari_3f_s = agari_bu + agari_ko / 10.0

    # コーナー通過順位
    c1 = _opt_i(record, 592, 594)
    c2 = _opt_i(record, 594, 596)
    c3 = _opt_i(record, 596, 598)
    c4 = _opt_i(record, 598, 600)

    if race_time_s <= 0 or agari_3f_s <= 0:
        return None

    return ResultRecord(
        horse_no=horse_no,
        finish_pos=finish_pos,
        race_time_s=race_time_s,
        agari_3f_s=agari_3f_s,
        corner_1=c1,
        corner_2=c2,
        corner_3=c3,
        corner_4=c4,
    )


def get_horse_info_from_se(record: str) -> tuple[str, str, str | None]:
    """SE レコードから (ketto_num, uma_name, sex) を取り出す（UM 不在時の補完用）。"""
    ketto_num = _s(record, 30, 40)
    uma_name = _s(record, 40, 58)
    sex_cd = _s(record, 60, 61)
    sex = decode_sex(sex_cd)
    return ketto_num, uma_name, sex
