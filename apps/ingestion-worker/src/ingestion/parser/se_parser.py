"""SE レコード（馬毎レース情報）パーサ。

JV-Data仕様書 Ver.3.0.0 — SE レコードのフィールド定義。

SE レコードは DataKubun によって内容が変わる:
  DataKubun "1": 新規（出走前、出走確定時に配信）
  DataKubun "2": 更新（騎手変更等）
  DataKubun "3": 取消/除外
  DataKubun "4": 確定（レース終了後の成績データ）

NOTE: バイト位置は JV-Data仕様書 Ver.3.0.0 の「SE レコード」ページに準拠。
      実際の JV-Link 出力との照合を実施すること。

SE レコード総バイト数: 約 1060 bytes
"""

from __future__ import annotations

from ingestion.models import EntryRecord, ResultRecord
from ingestion.parser.common import (
    _f,
    _i,
    _opt_i,
    _s,
    build_race_key,
    decode_sex,
)

# ---------------------------------------------------------------------------
# SE レコード フィールド定義（バイト位置、0-indexed・end-exclusive）
# ---------------------------------------------------------------------------
# 共通ヘッダ:
# [0:2]   RecordSpec = "SE"
# [2:3]   DataKubun
# [3:11]  MakeDate (YYYYMMDD)
# [11:13] JyoCd
# [13:15] Kaiji
# [15:17] Nichiji
# [17:19] RaceNo
# [19:21] Umaban（馬番、2桁右詰）
# [21:23] Wakuban（枠番、2桁右詰）
# [23:33] KettoNum（血統登録番号、10桁）
# [33:69] UmaName（馬名、36 bytes、左詰空白パディング）
# [69:70] UmaKigo
# [70:71] SeibetsuCd (1=牡, 2=牝, 3=騸)
# [71:73] TozaiSo（東西所属）
# [73:77] ChokyosiCode（調教師コード、4桁）
# [77:113] ChokyosiName（調教師名、36 bytes）
# [113:117] (その他フィールド)
# [117:121] KisoCode（騎手コード、4桁）
# [121:157] KisoName（騎手名、36 bytes）
# [157:159] Futan（負担重量、単位 0.1kg、例: "55" → 55.0 kg）
# [159:163] Bataijyu（馬体重、kg）
# [163:165] ZogenSa（増減差、kg）
# [165:166] ZogenFugo（+/-）
#
# 確定後フィールド (DataKubun="4"):
# [580:582] ChakuJunni（着順、"99"=中止/失格）
# [582:584] SohaTimeM（走破タイム 分）
# [584:586] SohaTimeS（走破タイム 秒）
# [586:588] SohaTimeK（走破タイム 1/10秒）
# [588:590] Agari3FBu（上がり3F 秒）
# [590:592] Agari3FKou（上がり3F 1/10秒）
# [592:594] Corner1（1コーナー通過順位）
# [594:596] Corner2（2コーナー通過順位）
# [596:598] Corner3（3コーナー通過順位）
# [598:600] Corner4（4コーナー通過順位）
# ---------------------------------------------------------------------------

_KUBUN_ENTRY = frozenset({"1", "2"})  # 出走前
_KUBUN_RESULT = frozenset({"4"})      # 確定後
_KUBUN_CANCEL = frozenset({"3"})      # 取消/除外


def parse_race_key_from_se(record: str) -> str:
    """SE レコードからレースキーを取り出す。"""
    jyo_cd = _s(record, 11, 13)
    kaiji = _s(record, 13, 15)
    nichiji = _s(record, 15, 17)
    race_no = _s(record, 17, 19)
    # SE の場合、年・月日は MakeDate (byte 3-10) から取り出す
    nen = _s(record, 3, 7)
    month_day = _s(record, 7, 11)
    return build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)


def parse_se_entry(record: str) -> EntryRecord | None:
    """SE レコード（出走前）を EntryRecord に変換する。

    DataKubun が "1" または "2" の場合のみ変換。
    Returns None for cancel/result records.
    """
    if len(record) < 166:
        raise ValueError(f"SE レコードが短すぎます: {len(record)} bytes")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun not in _KUBUN_ENTRY:
        return None

    horse_no = _i(record, 19, 21)
    frame_no = _i(record, 21, 23)
    ketto_num = _s(record, 23, 33)
    jockey_code = _s(record, 117, 121)
    trainer_code = _s(record, 73, 77)
    # 馬体重（kg）
    weight = _f(record, 159, 163)
    if weight == 0.0:
        weight = 460.0  # 計測不能時のデフォルト

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

    DataKubun が "4" の場合のみ変換。
    Returns None for entry/cancel records.
    着順 "99"（中止/失格）は None を返す。
    """
    if len(record) < 600:
        raise ValueError(f"SE 確定レコードが短すぎます: {len(record)} bytes")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun not in _KUBUN_RESULT:
        return None

    horse_no = _i(record, 19, 21)

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
    """SE レコードから (ketto_num, uma_name, sex) を取り出す（UM レコード不在時の補完）。"""
    ketto_num = _s(record, 23, 33)
    uma_name = _s(record, 33, 69)
    sex_cd = _s(record, 70, 71)
    sex = decode_sex(sex_cd)
    return ketto_num, uma_name, sex
