"""JV-Link 固定長レコードの共通パーサユーティリティ。

JV-Data仕様書 Ver.3.0.0 に基づくバイト位置定義（Shift-JIS エンコード）。
実際の JV-Link 出力との照合時は、レコード種別ごとの仕様書ページを参照すること。

バイト位置はすべて 0-indexed・end-exclusive（Python スライス記法）。
"""

from __future__ import annotations

import datetime


def _s(record: str, start: int, end: int) -> str:
    """固定長レコードから指定バイト範囲を取り出してトリムする。"""
    return record[start:end].strip()


def _i(record: str, start: int, end: int, default: int = 0) -> int:
    raw = _s(record, start, end)
    return int(raw) if raw.isdigit() else default


def _f(record: str, start: int, end: int, scale: float = 1.0) -> float:
    raw = _s(record, start, end)
    return float(raw) * scale if raw.isdigit() else 0.0


def _opt_i(record: str, start: int, end: int) -> int | None:
    raw = _s(record, start, end)
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


# ---------------------------------------------------------------------------
# バイト単位スライス（CP932）
# ---------------------------------------------------------------------------
# JV-Data 仕様のオフセットはすべて **バイト** 単位。JV-Link が返す Unicode str を
# そのまま char でスライスすると、全角フィールド（馬名・馬主名・服色等）を跨いだ
# 時点で以降が全部ズレる。jv_spec のオフセットは必ず CP932 バイト列上で適用する。


def to_cp932(record: str) -> bytes:
    """JV-Link が返す Unicode 文字列を元の CP932(Shift-JIS) バイト列に戻す。"""
    return record.encode("cp932", errors="replace")


def _bs(raw: bytes, start: int, end: int) -> str:
    """CP932 バイト列から指定バイト範囲を取り出してデコード・トリムする。"""
    return raw[start:end].decode("cp932", errors="replace").strip()


def _bi(raw: bytes, start: int, end: int, default: int = 0) -> int:
    s = _bs(raw, start, end)
    return int(s) if s.isdigit() else default


def _opt_bi(raw: bytes, start: int, end: int) -> int | None:
    s = _bs(raw, start, end)
    return int(s) if s.isdigit() and int(s) > 0 else None


def build_race_key(
    jyo_cd: str, kaiji: str, nichiji: str, race_no: str, nen: str, month_day: str
) -> str:
    """レースキー 16桁を組み立てる: YYYY(4) + MMDD(4) + JYO(2) + KAI(2) + NICHI(2) + R(2)。"""
    return f"{nen}{month_day}{jyo_cd}{kaiji}{nichiji}{race_no}"


# ----- コードテーブル -----

_TENKO_MAP: dict[str, str] = {
    "1": "晴",
    "2": "曇",
    "3": "小雨",
    "4": "雨",
    "5": "小雪",
    "6": "雪",
}

_BABA_MAP: dict[str, str] = {
    "1": "良",
    "2": "稍重",
    "3": "重",
    "4": "不良",
}

_SEX_MAP: dict[str, str] = {
    "1": "牡",
    "2": "牝",
    "3": "騸",
}


def decode_tenko(code: str) -> str | None:
    return _TENKO_MAP.get(code.strip())


def decode_baba(code: str) -> str | None:
    return _BABA_MAP.get(code.strip())


def decode_track(code: str) -> str:
    """TrackCD を芝/ダート/障害に変換する。

    JV-Data Ver.4.9 の TrackCD は2桁コード: 10番台=芝, 20番台=ダート, 50番台=障害。
    旧仕様の1桁コード(1/2/3)も受け付ける。
    """
    c = code.strip()
    if c.isdigit():
        n = int(c)
        if n == 1 or 10 <= n <= 19:
            return "芝"
        if n == 2 or 20 <= n <= 29:
            return "ダート"
        if n == 3 or 50 <= n <= 59:
            return "障害"
    return "芝"


def decode_sex(code: str) -> str | None:
    return _SEX_MAP.get(code.strip())


def parse_race_date(nen: str, month_day: str) -> datetime.date:
    """年(4桁) + 月日(4桁 MMDD) → datetime.date。"""
    return datetime.date(int(nen), int(month_day[:2]), int(month_day[2:]))
