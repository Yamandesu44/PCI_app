"""JV-Data 固定長レコードのバイトオフセット仕様マップ（単一の真実の場所）。

JV-Data のフィールド位置は仕様書上すべて **バイト** 単位（Shift-JIS/CP932）で定義される。
全角文字は 2 バイト、半角は 1 バイト。JV-Link が返す Unicode 文字列をそのまま
``str`` の文字位置でスライスすると、全角フィールド（レース名・馬名など）を跨いだ
時点で以降の全フィールドがズレる。

そのため本マップのオフセットは必ず ``record.encode("cp932")`` した bytes 上で適用する。
CR/LF を除いたデータ長は RA=1270 byte / SE=553 byte（= 仕様総レコード長 − 2）。

各フィールドの ``confidence``:
  CONFIRMED … 共通ヘッダ・レースID・馬番など全レコード共通で確度が高い領域
  TENTATIVE … 実データで要確認（verify_layout / dump_records で校正する）

オフセットは 0-indexed・end-exclusive（Python スライス記法）。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal

# text=全角を含む SJIS 文字列 / code=コード・ID / num=数値 / date=日付
FieldKind = Literal["text", "code", "num", "date"]

RA_RECORD_BYTES = 1270  # RA レコード総長 1272 − CR/LF(2)
SE_RECORD_BYTES = 553   # SE レコード総長 555 − CR/LF(2)


class Confidence(enum.Enum):
    """フィールドオフセットの確度。"""

    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"


@dataclass(frozen=True)
class FieldSpec:
    """1 フィールドのバイトオフセット定義。"""

    name: str
    offset: int           # バイト開始位置（0-indexed）
    length: int           # バイト長
    kind: FieldKind
    confidence: Confidence
    note: str = ""

    @property
    def end(self) -> int:
        """end-exclusive のバイト終端位置。"""
        return self.offset + self.length


_C = Confidence.CONFIRMED
_T = Confidence.TENTATIVE


# ---------------------------------------------------------------------------
# RA レコード（レース詳細）
# ---------------------------------------------------------------------------
# [0:33] は半角コード/数字領域のため char 位置 == byte 位置（確度高）。
# 競走名 本題(Hondai)[33:] から全角が始まり、ここから char スライスは破綻する。
RA_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("RecordSpec", 0, 2, "code", _C, "レコード種別ID = 'RA'"),
    FieldSpec("DataKubun", 2, 1, "code", _C, "1=新規 2=更新 7=確定 0=削除 など（RA確定は7）"),
    FieldSpec("MakeDate", 3, 8, "date", _C, "データ作成年月日 YYYYMMDD"),
    FieldSpec("Year", 11, 4, "num", _C, "開催年 YYYY（race_key はここから）"),
    FieldSpec("MonthDay", 15, 4, "num", _C, "開催月日 MMDD"),
    FieldSpec("JyoCD", 19, 2, "code", _C, "競馬場コード"),
    FieldSpec("Kaiji", 21, 2, "num", _C, "開催回 [第N回]"),
    FieldSpec("Nichiji", 23, 2, "num", _C, "開催日 [N日目]"),
    FieldSpec("RaceNum", 25, 2, "num", _C, "レース番号"),
    FieldSpec("YoubiCD", 27, 2, "code", _C, "曜日コード（2byte）"),
    FieldSpec(
        "TokuNum", 29, 4, "num", _C,
        "特別競走番号（一般=0000）。旧 parser が [28:32] で距離/等級と誤認していた領域の正体",
    ),
    # ----- ここから全角テキスト領域。char で切ると以降が全部ズレる -----
    FieldSpec("Hondai", 33, 60, "text", _T, "競走名 本題（全角30字）= char ドリフト開始点"),
    FieldSpec("Fukudai", 93, 60, "text", _T, "競走名 副題"),
    FieldSpec("Kakko", 153, 60, "text", _T, "競走名 カッコ内"),
    FieldSpec("HondaiEng", 213, 120, "text", _T, "競走名 本題 英字"),
    FieldSpec("FukudaiEng", 333, 120, "text", _T, "競走名 副題 英字"),
    FieldSpec("KakkoEng", 453, 120, "text", _T, "競走名 カッコ 英字"),
    FieldSpec("Ryakusyo10", 573, 20, "text", _T, "競走名 略称10字"),
    FieldSpec("Ryakusyo6", 593, 12, "text", _T, "競走名 略称6字"),
    FieldSpec("Ryakusyo3", 605, 6, "text", _T, "競走名 略称3字"),
    FieldSpec("Kubun", 611, 1, "code", _T, "競走名区分"),
    FieldSpec("Nkai", 612, 3, "num", _T, "回次 [第N回]"),
    FieldSpec(
        "GradeCD", 615, 1, "code", _T,
        "615=spec標準（Nkai[612:615]直後）。dump_records は614仮定→要確認",
    ),
    FieldSpec("GradeCDBefore", 616, 1, "code", _T, "変更前グレードコード"),
    FieldSpec("SyubetuCD", 617, 2, "code", _T, "競走種別コード"),
    FieldSpec("KigoCD", 619, 3, "code", _T, "競走記号コード"),
    FieldSpec("JyuryoCD", 622, 1, "code", _T, "重量種別コード"),
    # 623〜696 は JyokenCD 配列 + 競走条件名称(60byte) 等。未マップ（byte ルーラーで調査）。
    # 実測確定: 2026-06-13 函館1R(JyoCD=02 Kyori=1200 TrackCD=17)
    FieldSpec("Kyori", 697, 4, "num", _C, "距離(m)。実測確定"),
    FieldSpec("TrackCD", 705, 2, "code", _C, "トラックコード(10番台=芝/20番台=ダ)。実測 '17'=芝"),
    # 707〜??? は賞金・条件 等。未マップ。
    # 下記は DataKubun='7'(確定後)RA で全て '0'/'00' → オフセット誤りの疑い。要再調査。
    # _dump_nonblank_regions で非空白領域を探して正しい位置を特定すること。
    FieldSpec("SyussoTosu", 819, 2, "num", _T, "出走頭数【要再調査: 確定後で '00'】"),
    FieldSpec("TenkoCD", 823, 1, "code", _T, "天候コード【要再調査: 確定後で '0'】"),
    FieldSpec("SibaBabaCD", 824, 1, "code", _T, "芝馬場状態コード【要再調査】"),
    FieldSpec("DirtBabaCD", 825, 1, "code", _T, "ダート馬場状態コード【要再調査】"),
    # ----- ラップタイム / HaronTime ブロック — 実測確定（2026-06-13 函館1R） -----
    # locate_haron ツールで LapTime 配列(890) と HaronTime ブロック(969) を特定。
    # LapTime[890:965] = 各ハロン 3桁×25本=75byte（1200mは6本, 残り 000）
    # HaronTimeS3[969:972] 前半3F / HaronTimeS4[972:975] 前半4F
    FieldSpec("HaronTimeS3", 969, 3, "num", _C, "前半3ハロンタイム合計（1/10秒3桁）。実測確定"),
    FieldSpec("HaronTimeS4", 972, 3, "num", _C, "前半4ハロンタイム合計（1/10秒3桁）。実測確定"),
    FieldSpec(
        "HaronTimeL3", 975, 3, "num", _C,
        "後半3ハロンタイム合計（1/10秒3桁）= RPCI 算出に使用。実測確定",
    ),
    FieldSpec("HaronTimeL4", 978, 3, "num", _C, "後半4ハロンタイム合計（1/10秒3桁）。実測確定"),
)


# ---------------------------------------------------------------------------
# SE レコード（馬毎レース情報）
# ---------------------------------------------------------------------------
# [0:40] は半角コード/数字領域のため char 位置 == byte 位置（確度高）。
# 馬名(Bamei)[40:76] は全角18字=36byte。旧 parser の char[40:58] と異なり、
# ここから char スライスは 18byte ぶんズレ始める。
SE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("RecordSpec", 0, 2, "code", _C, "レコード種別ID = 'SE'"),
    FieldSpec("DataKubun", 2, 1, "code", _C, "1=新規 2=更新 3=取消/除外 4=確定 など"),
    FieldSpec("MakeDate", 3, 8, "date", _C, "データ作成年月日 YYYYMMDD"),
    FieldSpec("Year", 11, 4, "num", _C, "開催年 YYYY（race_key はここから）"),
    FieldSpec("MonthDay", 15, 4, "num", _C, "開催月日 MMDD"),
    FieldSpec("JyoCD", 19, 2, "code", _C, "競馬場コード"),
    FieldSpec("Kaiji", 21, 2, "num", _C, "開催回"),
    FieldSpec("Nichiji", 23, 2, "num", _C, "開催日"),
    FieldSpec("RaceNum", 25, 2, "num", _C, "レース番号"),
    FieldSpec("Wakuban", 27, 1, "num", _C, "枠番（1桁）"),
    FieldSpec("Umaban", 28, 2, "num", _C, "馬番（2桁）"),
    FieldSpec("KettoNum", 30, 10, "code", _C, "血統登録番号（10桁）"),
    # ----- ここから全角テキスト領域。char で切ると以降が全部ズレる -----
    FieldSpec("Bamei", 40, 36, "text", _C, "馬名（全角18字=36byte）= char ドリフト開始点"),
    FieldSpec("UmaKigoCD", 76, 2, "code", _T, "馬記号コード"),
    FieldSpec("SexCD", 78, 1, "code", _C, "性別コード（1=牡 2=牝 3=騸）。実測確定"),
    FieldSpec("HinsyuCD", 79, 1, "code", _T, "品種コード"),
    FieldSpec("KeiroCD", 80, 2, "code", _T, "毛色コード"),
    # ----- 以下は実データ(2026-06-13 函館1R, DataKubun=7)で byte 確定 -----
    # 錨1: 調教師名略称 '青木孝文' @ [90:98] → 直前 [85:90] が調教師コード
    FieldSpec("ChokyosiCode", 85, 5, "code", _C, "調教師コード。名略称[90:98]が直後で確定"),
    # 錨2: 騎手名略称 '河原田菜' @ [306:314] → 直前 [296:301]=現/[301:306]=変更前
    FieldSpec("KisyuCode", 296, 5, "code", _C, "騎手コード。名略称[306:314]が直後で確定"),
    FieldSpec("KisyuCodeBefore", 301, 5, "code", _T, "変更前騎手コード（無変更時 00000）"),
    # 錨3: 馬体重 '456' + 増減符号 '-' @ [327] のパターンで確定
    FieldSpec("BaTaijyu", 324, 3, "num", _C, "馬体重(kg)。直後[327]に増減符号"),
    FieldSpec("NyusenJyuni", 332, 2, "num", _C, "入線順位"),
    FieldSpec("KakuteiJyuni", 334, 2, "num", _C, "確定着順（99=中止/失格 00=未確定）"),
    FieldSpec("Time", 338, 4, "num", _C, "走破タイム MSSf（分1+秒2+1/10秒1）。'1107'=1:10.7"),
    # コーナー通過順位 [356:364]: 各2byte×4本。
    # 実データ（2026-06-21 阪神9R 2000m SE）で locate_corners.py スキャンにより特定。
    # 553byte 全体で唯一の「4連続有効値（1-18）@2byte 刻み」候補 → [356:364]=10,10,5,10。
    # netkeiba 通過順位との照合で CONFIRMED に昇格すること。
    FieldSpec("Jyuni1c", 356, 2, "num", _T, "コーナー通過順位1（実データ候補: [356:358]）"),
    FieldSpec("Jyuni2c", 358, 2, "num", _T, "コーナー通過順位2（実データ候補: [358:360]）"),
    FieldSpec("Jyuni3c", 360, 2, "num", _T, "コーナー通過順位3（実データ候補: [360:362]）"),
    FieldSpec("Jyuni4c", 362, 2, "num", _T, "コーナー通過順位4（実データ候補: [362:364]）"),
    # 錨4: 上り3F '358'(=35.8s) の直後 [393:403] が1着馬血統番号 → 位置確定
    FieldSpec("HaronTimeL3", 390, 3, "num", _C, "後3ハロンタイム（上り3F・1/10秒, 3桁）"),
    FieldSpec("ChakuKettoNum1", 393, 10, "code", _C, "1着馬(勝ち馬)血統登録番号。錨"),
    FieldSpec("ChakuBamei1", 403, 36, "text", _C, "1着馬(勝ち馬)馬名 全角18字。錨"),
    # 2着/3着馬情報（各10byte血統番号 + 36byte馬名）が続いた後にコーナー通過順位が来る。
    # 合計 [439:531] = 10+36+10+36=92byte（仮説・未実測確認）。
    FieldSpec("ChakuKettoNum2", 439, 10, "code", _T, "2着馬血統登録番号（仮説）"),
    FieldSpec("ChakuBamei2", 449, 36, "text", _T, "2着馬名 全角18字（仮説）"),
    FieldSpec("ChakuKettoNum3", 485, 10, "code", _T, "3着馬血統登録番号（仮説）"),
    FieldSpec("ChakuBamei3", 495, 36, "text", _T, "3着馬名 全角18字（仮説）"),
)


_LAYOUTS: dict[str, tuple[tuple[FieldSpec, ...], int]] = {
    "RA": (RA_FIELDS, RA_RECORD_BYTES),
    "SE": (SE_FIELDS, SE_RECORD_BYTES),
}


def get_layout(record_spec: str) -> tuple[tuple[FieldSpec, ...], int]:
    """レコード種別IDからフィールド定義と期待バイト長を返す。

    未対応の種別は ValueError。
    """
    try:
        return _LAYOUTS[record_spec]
    except KeyError:
        supported = ", ".join(sorted(_LAYOUTS))
        raise ValueError(f"未対応のレコード種別: {record_spec!r}（対応: {supported}）") from None


def supported_specs() -> tuple[str, ...]:
    """マップを持つレコード種別IDの一覧。"""
    return tuple(sorted(_LAYOUTS))
