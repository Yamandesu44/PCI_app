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


def build_race_key(jyo_cd: str, kaiji: str, nichiji: str, race_no: str, nen: str, month_day: str) -> str:
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

_TRACK_MAP: dict[str, str] = {
    "1": "芝",
    "2": "ダート",
    "3": "障害",
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
    return _TRACK_MAP.get(code.strip(), "芝")


def decode_sex(code: str) -> str | None:
    return _SEX_MAP.get(code.strip())


def parse_race_date(nen: str, month_day: str) -> datetime.date:
    """年(4桁) + 月日(4桁 MMDD) → datetime.date。"""
    return datetime.date(int(nen), int(month_day[:2]), int(month_day[2:]))
