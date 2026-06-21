"""UM / KS / CH マスタレコードパーサ。

JV-Data仕様書 Ver.4.9 実データより逆算したバイト位置定義。
Ver.3.0.0 から Ver.4.9 での変更点:
  - UM: ketto_num 後に 24 バイトの日付フィールド群が追加 → 名前は [46:64]
  - KS/CH: code 拡張 + 24 バイトの日付フィールド群追加 → 名前は [41:58]

UM: 競走馬マスタ
KS: 騎手マスタ
CH: 調教師マスタ
"""

from __future__ import annotations

from ingestion.models import HorseRecord, JockeyRecord, TrainerRecord
from ingestion.parser.common import _bi, _bs, _s, decode_sex, to_cp932

# ---------------------------------------------------------------------------
# UM レコード（競走馬マスタ）  ― Ver.4.9 実測オフセット
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "UM"
# [2:3]   DataKubun（0=削除/無効）
# [3:11]  MakeDate (YYYYMMDD)
# [11:12] UmaKigo（馬記号 1桁）
# [12:22] KettoNum（血統登録番号 10桁）
# [22:30] 追加日付フィールド1（Ver.4.9 追加）
# [30:38] 追加日付フィールド2（Ver.4.9 追加）
# [38:46] 生年月日 YYYYMMDD（Ver.4.9 追加） ← [38:42] = 生年
# [46:64] UmaName（馬名 18 Unicode chars = 36 bytes ShiftJIS）
# [64:100] UmaNameKana（カタカナ馬名 36 half-width chars）
# [100:160] UmaNameEng（英字馬名 60 chars）
# [160:161] ZaikyuFlag（在きゅうフラグ） ※sex ではない
# [161:180] Reserved（予備 19 chars 空白）
# [180:182] UmaKigoCD（馬記号コード 2桁）
# [182:183] SexCD（性別コード: 1=牡 2=牝 3=騸）
# [183:184] HinsyuCD（品種コード）
# [184:186] KeiroCD（毛色コード 2桁）
#
# NOTE: 馬名フィールド以降のバイト位置は、馬名(36バイト=18全角文字)の
#       Unicode 圧縮を前提に算出している。JRA 馬名は常に全角のため安定。
# ---------------------------------------------------------------------------


def parse_um(record: str) -> HorseRecord | None:
    """UM 固定長レコードを HorseRecord に変換する。

    SexCD は馬名(全角)・カナ名・英字名の後 byte[182:183] にあり、char スライスでは
    ドリフトするため CP932 バイト列上で読む。
    """
    raw = to_cp932(record)
    if len(raw) < 64:
        raise ValueError(f"UM レコードが短すぎます: {len(raw)} bytes（最低64必要）")

    rec_spec = _bs(raw, 0, 2)
    if rec_spec != "UM":
        raise ValueError(f"RecordSpec が UM ではありません: {rec_spec!r}")

    data_kubun = _bs(raw, 2, 3)
    if data_kubun == "0":
        return None

    ketto_num = _bs(raw, 12, 22)
    birth_year = _bi(raw, 38, 42)  # 生年月日 YYYYMMDD の YYYY 部分
    name = _bs(raw, 46, 82)        # 馬名 全角18字=36byte
    sex_cd = _bs(raw, 182, 183) if len(raw) > 182 else ""
    sex = decode_sex(sex_cd)

    return HorseRecord(
        ketto_num=ketto_num,
        name=name,
        sex=sex,
        birth_year=birth_year if birth_year and birth_year > 1900 else None,
    )


# ---------------------------------------------------------------------------
# KS レコード（騎手マスタ）  ― Ver.4.9 実測オフセット
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "KS"
# [2:3]   DataKubun
# [3:11]  MakeDate (YYYYMMDD)
# [11:16] KisyuCode（騎手コード 5桁）
# [16:17] フラグ/記号（1桁）
# [17:25] 追加日付フィールド1（免許取得日等）
# [25:33] 追加日付フィールド2（免許失効日等）
# [33:41] 生年月日 YYYYMMDD
# [41:58] KisoName（騎手氏名 17 Unicode chars = 34 bytes ShiftJIS）
# ---------------------------------------------------------------------------


def parse_ks(record: str) -> JockeyRecord | None:
    """KS 固定長レコードを JockeyRecord に変換する。"""
    if len(record) < 58:
        raise ValueError(f"KS レコードが短すぎます: {len(record)} chars（最低58必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "KS":
        raise ValueError(f"RecordSpec が KS ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None

    code = _s(record, 11, 16)
    name = _s(record, 41, 58)

    return JockeyRecord(code=code, name=name)


# ---------------------------------------------------------------------------
# CH レコード（調教師マスタ）  ― Ver.4.9 実測オフセット
# ---------------------------------------------------------------------------
# [0:2]   RecordSpec = "CH"
# [2:3]   DataKubun
# [3:11]  MakeDate (YYYYMMDD)
# [11:16] ChokyosiCode（調教師コード 5桁）
# [16:17] フラグ/記号（1桁）
# [17:25] 追加日付フィールド1（免許取得日等）
# [25:33] 追加日付フィールド2（免許失効日等）
# [33:41] 生年月日 YYYYMMDD
# [41:58] ChokyosiName（調教師氏名 17 Unicode chars = 34 bytes ShiftJIS）
# ---------------------------------------------------------------------------


def parse_ch(record: str) -> TrainerRecord | None:
    """CH 固定長レコードを TrainerRecord に変換する。"""
    if len(record) < 58:
        raise ValueError(f"CH レコードが短すぎます: {len(record)} chars（最低58必要）")

    rec_spec = _s(record, 0, 2)
    if rec_spec != "CH":
        raise ValueError(f"RecordSpec が CH ではありません: {rec_spec!r}")

    data_kubun = _s(record, 2, 3)
    if data_kubun == "0":
        return None

    code = _s(record, 11, 16)
    name = _s(record, 41, 58)

    return TrainerRecord(code=code, name=name)
