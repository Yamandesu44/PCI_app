"""SE レコード（馬毎レース情報）パーサ。

JV-Data 実データ（2026-06-13 函館1R, DataKubun=7 確定）より byte 単位で校正済み。
オフセットは jv_spec.SE_FIELDS と一致させること（単一の真実の場所）。

重要: JV-Link が返す Unicode 文字列は **CP932 バイト列に戻してから** byte オフセットで
切り出す。馬名(全角18字=36byte)・馬主名・服色などの全角フィールドを跨ぐと char
スライスは破綻するため、本パーサは全フィールドを to_cp932() 後の bytes 上で読む。

SE レコードは DataKubun によって内容が変わる:
  "1": 新規（出走前） / "2": 更新（出馬表・騎手変更等）
  "3": 取消/除外
  "4": 確定（旧仕様） / "7": 確定（実測確認: 2026-06-13 函館1R）
"""

from __future__ import annotations

from ingestion.models import EntryRecord, ResultRecord
from ingestion.parser.common import (
    _bi,
    _bs,
    build_race_key,
    decode_sex,
    to_cp932,
)
from ingestion.parser.jv_spec import SE_RECORD_BYTES

_CORNER_MAX = 18  # フルゲート最大頭数（有効コーナー通過順位の上限）

# ---------------------------------------------------------------------------
# SE レコード byte オフセット（jv_spec.SE_FIELDS と一致。実測確定）
# ---------------------------------------------------------------------------
# 共通: KaisaiNengappi[11:19] JyoCD[19:21] Kaiji[21:23] Nichiji[23:25] RaceNum[25:27]
#       Wakuban[27:28] Umaban[28:30] KettoNum[30:40] Bamei[40:76] SexCD[78:79]
# コード: ChokyosiCode[85:90]（名略称[90:98] 直前） KisyuCode[296:301]（名略称[306:314] 直前）
# 確定後: BaTaijyu[324:327] NyusenJyuni[332:334] KakuteiJyuni[334:336]
#         Time[338:342] MSSf 上り3F[390:393]（直後[393:403]=1着馬血統番号）
# コーナー通過順位は未特定（2レコード目で差分校正予定）→ None を返す。
# ---------------------------------------------------------------------------

def _corner_pos(raw: bytes, start: int, end: int) -> int | None:
    """コーナー通過順位を CP932 バイト列から取り出す。

    有効範囲 [1..18] 外の値（"00" や非数字、> 18）は None を返す。
    """
    s = raw[start:end].decode("cp932", errors="replace").strip()
    if not s.isdigit():
        return None
    n = int(s)
    return n if 1 <= n <= _CORNER_MAX else None


_KUBUN_ENTRY = frozenset({"1", "2"})     # 出走前・出馬表
_KUBUN_RESULT = frozenset({"4", "7"})    # 確定後（'4' 旧仕様 / '7' 実測確認）
_KUBUN_CANCEL = frozenset({"3"})         # 取消/除外
# エントリ情報（枠番・馬番・血統・騎手・調教師）を持つ DataKubun。
# 確定後('4'/'7')レコードも全エントリ項目を含むため、過去レース（出走表が
# 既に確定へ置き換わったデータ）でも出走表を再構成できる。取消('3')のみ除外。
_KUBUN_ENTRYABLE = _KUBUN_ENTRY | _KUBUN_RESULT


def parse_race_key_from_se(record: str) -> str:
    """SE レコードからレースキーを取り出す。

    開催年月日は KaisaiNengappi [11:19] から取り出す（MakeDate ではない）。
    """
    raw = to_cp932(record)
    nen = _bs(raw, 11, 15)        # KaisaiNengappi の YYYY
    month_day = _bs(raw, 15, 19)  # KaisaiNengappi の MMDD
    jyo_cd = _bs(raw, 19, 21)
    kaiji = _bs(raw, 21, 23)
    nichiji = _bs(raw, 23, 25)
    race_no = _bs(raw, 25, 27)
    return build_race_key(jyo_cd, kaiji, nichiji, race_no, nen, month_day)


def parse_se_entry(record: str) -> EntryRecord | None:
    """SE レコード（出走前・出馬表 / 確定後）を EntryRecord に変換する。

    DataKubun が "1"/"2"（出走前）または "4"/"7"（確定後）の場合に変換する。
    確定後レコードも枠番・馬番・血統・騎手・調教師を含むため、過去レース
    （出走表が確定へ置き換わったデータ）でも出走表を再構成できる。
    取消/除外("3")・その他は None。
    """
    raw = to_cp932(record)
    if len(raw) < 98:  # 騎手名略称 [90:98] までは最低限必要
        raise ValueError(f"SE レコードが短すぎます: {len(raw)} bytes（最低98必要）")

    rec_spec = _bs(raw, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _bs(raw, 2, 3)
    if data_kubun not in _KUBUN_ENTRYABLE:
        return None

    frame_no = _bi(raw, 27, 28)        # Wakuban（枠番 1桁）
    horse_no = _bi(raw, 28, 30)        # Umaban（馬番 2桁）
    ketto_num = _bs(raw, 30, 40)
    trainer_code = _bs(raw, 85, 90)    # 名略称[90:98] 直前で確定
    # 騎手コード[296:301] はレコード後方。出馬表(短縮長)では範囲外になり得るため保護。
    jockey_code = _bs(raw, 296, 301) if len(raw) >= 301 else ""

    # 馬体重: 確定後 SE は BaTaijyu[324:327] に実値。出馬表段階は未発表("000"/
    # 範囲外)のため暫定デフォルト 460.0 を使う。
    weight = 460.0
    if len(raw) >= 327:
        bataijyu = _bs(raw, 324, 327)
        if bataijyu.isdigit() and int(bataijyu) > 0:
            weight = float(bataijyu)

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

    DataKubun が "4"/"7" の場合のみ変換。着順 "00"(未確定)/"99"(中止/失格) は None。

    コーナー通過順位は実バイト位置が未特定のため None（2レコード目で要差分校正）。
    """
    raw = to_cp932(record)
    if len(raw) < SE_RECORD_BYTES:
        raise ValueError(f"SE 確定レコードが短すぎます: {len(raw)} bytes（{SE_RECORD_BYTES}必要）")

    rec_spec = _bs(raw, 0, 2)
    if rec_spec != "SE":
        raise ValueError(f"RecordSpec が SE ではありません: {rec_spec!r}")

    data_kubun = _bs(raw, 2, 3)
    if data_kubun not in _KUBUN_RESULT:
        return None

    horse_no = _bi(raw, 28, 30)  # Umaban

    # 確定着順 [334:336]（"00"=未確定 / "99"=中止・失格 は対象外）
    chaku_raw = _bs(raw, 334, 336)
    if not chaku_raw.isdigit() or not 1 <= int(chaku_raw) <= 98:
        return None
    finish_pos = int(chaku_raw)

    # 走破タイム [338:342] = MSSf（分1 + 秒2 + 1/10秒1）。例 '1107' = 1分10秒7
    time_raw = _bs(raw, 338, 342)
    if len(time_raw) != 4 or not time_raw.isdigit():
        return None
    race_time_s = int(time_raw[0]) * 60.0 + int(time_raw[1:3]) + int(time_raw[3]) / 10.0

    # 上り3F [390:393] = 3桁 1/10秒。例 '358' = 35.8秒
    agari_raw = _bs(raw, 390, 393)
    if not agari_raw.isdigit():
        return None
    agari_3f_s = int(agari_raw) / 10.0

    if race_time_s <= 0 or agari_3f_s <= 0:
        return None

    # コーナー通過順位 [356:364]: Jyuni1c-4c 各2byte。
    # 2026-06-21 阪神9R(2000m) SE の locate_corners.py スキャンで特定した実データ候補。
    # 有効範囲外（0 または > 18）は None とし、脚質判定をスキップする。
    return ResultRecord(
        horse_no=horse_no,
        finish_pos=finish_pos,
        race_time_s=race_time_s,
        agari_3f_s=agari_3f_s,
        corner_1=_corner_pos(raw, 356, 358),
        corner_2=_corner_pos(raw, 358, 360),
        corner_3=_corner_pos(raw, 360, 362),
        corner_4=_corner_pos(raw, 362, 364),
    )


def get_horse_info_from_se(record: str) -> tuple[str, str, str | None]:
    """SE レコードから (ketto_num, uma_name, sex) を取り出す（UM 不在時の補完用）。"""
    raw = to_cp932(record)
    ketto_num = _bs(raw, 30, 40)
    uma_name = _bs(raw, 40, 76)   # 全角18字=36byte
    sex_cd = _bs(raw, 78, 79)
    sex = decode_sex(sex_cd)
    return ketto_num, uma_name, sex
