"""UM / KS / CH マスタレコードパーサ。

JV-Data仕様書 Ver.3.0.0 に基づく。

UM: 競走馬マスタ
KS: 騎手マスタ
CH: 調教師マスタ
"""

from __future__ import annotations

from ingestion.models import HorseRecord, JockeyRecord, TrainerRecord
from ingestion.parser.common import _i, _s, decode_sex

# ---------------------------------------------------------------------------
# UM レコード（競走馬マスタ）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "UM"
# [2:3]   DataKubun
# [3:11]  MakeDate (YYYYMMDD)
# [11:12] UmaKigo（馬記号）
# [12:22] KettoNum（血統登録番号 10桁）
# [22:58] UmaName（馬名 36 bytes）
# [58:94] UmaNameKana（馬名カナ 36 bytes）
# [94:100] SeibetsuNengetsu（性齢年月: 性別(1)+年月(5), "12604"=牡2026年4月生）
# ↑ [94:95] = 性別コード, [95:99] = 生年 (YYYY), [99:100] = 未使用
# ---------------------------------------------------------------------------


def parse_um(record: str) -> HorseRecord | None:
    """UM 固定長レコードを HorseRecord に変換する。"""
    if len(record) < 22:
        raise ValueError(f"UM レコードが短すぎます: {len(record)} bytes（最低22必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "UM":
        raise ValueError(f"RecordSpec が UM ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None

    ketto_num = _s(record, 12, 22)
    name = _s(record, 22, 58)
    sex_cd = _s(record, 94, 95) if len(record) > 94 else ""
    sex = decode_sex(sex_cd)
    birth_year = _i(record, 95, 99) if len(record) > 99 else None

    return HorseRecord(
        ketto_num=ketto_num,
        name=name,
        sex=sex,
        birth_year=birth_year if birth_year and birth_year > 1900 else None,
    )


# ---------------------------------------------------------------------------
# KS レコード（騎手マスタ）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "KS"
# [2:3]   DataKubun
# [3:11]  MakeDate
# [11:15] KisoCode（騎手コード 4桁）
# [15:51] KisoName（騎手名 36 bytes）
# ---------------------------------------------------------------------------


def parse_ks(record: str) -> JockeyRecord | None:
    """KS 固定長レコードを JockeyRecord に変換する。"""
    if len(record) < 15:
        raise ValueError(f"KS レコードが短すぎます: {len(record)} bytes（最低15必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "KS":
        raise ValueError(f"RecordSpec が KS ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None

    code = _s(record, 11, 15)
    name = _s(record, 15, 51)

    return JockeyRecord(code=code, name=name)


# ---------------------------------------------------------------------------
# CH レコード（調教師マスタ）
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "CH"
# [2:3]   DataKubun
# [3:11]  MakeDate
# [11:15] ChokyosiCode（調教師コード 4桁）
# [15:51] ChokyosiName（調教師名 36 bytes）
# ---------------------------------------------------------------------------


def parse_ch(record: str) -> TrainerRecord | None:
    """CH レコードを TrainerRecord に変換する。"""
    if len(record) < 15:
        raise ValueError(f"CH レコードが短すぎます: {len(record)} bytes（最低15必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "CH":
        raise ValueError(f"RecordSpec が CH ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None

    code = _s(record, 11, 15)
    name = _s(record, 15, 51)

    return TrainerRecord(code=code, name=name)
