"""開発用フィクスチャクライアント。

fixtures/ の JSON（sample_race_entries.json / sample_race_result.json）から、
JV-Data 実レイアウトと同じ **byte オフセット** に値を配置した固定長レコードを生成する。
これにより JV-Link（Windows 専用 COM）なしで、本番と同一のパーサパスを検証できる（ADR-0002）。

重要: レコードは bytearray を CP932 バイト列として組み立て、jv_spec のオフセット位置へ
書き込む。馬名など全角フィールドを跨いでも実データと同じ byte 配置になる。
（旧実装は char 連結で組んでいたため全角以降がズレ、byte 単位パーサで解析不能だった）

生データ・認証情報は一切コミットしない（法務: C2、セキュリティ: CLAUDE.md）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ingestion.parser.jv_spec import RA_RECORD_BYTES, SE_RECORD_BYTES

_log = logging.getLogger(__name__)

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

_UM_RECORD_BYTES = 200   # マスタは固定長の先頭側のみ使用（char パーサが許容）
_MASTER_RECORD_BYTES = 100


class FixtureJvLinkClient:
    """fixtures/ の JSON をもとに byte 正確な擬似レコードを生成する開発用クライアント。"""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or _DEFAULT_FIXTURES

    def _entries_json(self) -> Iterator[dict[str, Any]]:
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            yield json.loads(path.read_text(encoding="utf-8"))

    def _results_json(self) -> Iterator[dict[str, Any]]:
        for path in sorted(self._dir.glob("sample_race_result*.json")):
            yield json.loads(path.read_text(encoding="utf-8"))

    # ----- race records -----

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        for data in self._entries_json():
            rec = _json_to_ra(data["race_info"])
            if rec:
                yield rec

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        # 出走前（エントリ）
        for data in self._entries_json():
            for entry in data["entries"]:
                rec = _json_entry_to_se(data["race_info"], entry)
                if rec:
                    yield rec
        # 確定後（成績）
        for data in self._results_json():
            for result in data["results"]:
                rec = _json_result_to_se(data, result)
                if rec:
                    yield rec

    # ----- master records -----

    def iter_um_records(self) -> Iterator[str]:
        seen: set[str] = set()
        for data in self._entries_json():
            for e in data["entries"]:
                k = str(e["ketto_num"])
                if k not in seen:
                    seen.add(k)
                    yield _json_entry_to_um(e)

    def iter_ks_records(self) -> Iterator[str]:
        seen: set[str] = set()
        for data in self._entries_json():
            for e in data["entries"]:
                code = str(e.get("jockey_code", ""))
                if code and code not in seen:
                    seen.add(code)
                    yield _make_ks(code, str(e.get("jockey_name", f"騎手{code}")))

    def iter_ch_records(self) -> Iterator[str]:
        seen: set[str] = set()
        for data in self._entries_json():
            for e in data["entries"]:
                code = str(e.get("trainer_code", ""))
                if code and code not in seen:
                    seen.add(code)
                    yield _make_ch(code, str(e.get("trainer_name", f"調教師{code}")))


# ---------------------------------------------------------------------------
# JSON → byte 正確な固定長レコード生成ヘルパー
# ---------------------------------------------------------------------------


def _put(buf: bytearray, off: int, s: str) -> None:
    """CP932 バイト列としてフィールドを byte オフセットへ書き込む（全角=2byte）。"""
    b = s.encode("cp932", errors="replace")
    buf[off : off + len(b)] = b


def _track_cd(track_type: str) -> str:
    """track_type を TrackCD（10番台=芝/20番台=ダ/30番台=障害）へ。"""
    return {"芝": "17", "ダート": "23", "障害": "33"}.get(track_type, "17")


def _sex_cd(sex: str) -> str:
    return {"牡": "1", "牝": "2", "騸": "3"}.get(sex, "1")


def _json_to_ra(info: dict[str, Any]) -> str:
    """race_info → RA 固定長レコード（byte 正確）。"""
    race_key = str(info.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    buf = bytearray(b" " * RA_RECORD_BYTES)
    _put(buf, 0, "RA")
    _put(buf, 2, "1")                       # DataKubun=1（新規）
    _put(buf, 3, "20260618")                # MakeDate
    _put(buf, 11, race_key[0:8])            # KaisaiNengappi (YYYYMMDD)
    _put(buf, 19, race_key[8:10])           # JyoCD
    _put(buf, 21, race_key[10:12])          # Kaiji
    _put(buf, 23, race_key[12:14])          # Nichiji
    _put(buf, 25, race_key[14:16])          # RaceNum
    _put(buf, 27, "10")                     # YoubiCD
    _put(buf, 29, "0000")                   # TokuNum（一般）
    _put(buf, 33, str(info.get("race_class", "") or ""))   # Hondai（競走名）
    _put(buf, 697, f"{int(info.get('distance_m', 0) or 0):04d}")  # Kyori
    _put(buf, 705, _track_cd(str(info.get("track_type", "芝"))))   # TrackCD
    return buf.decode("cp932")


def _json_entry_to_se(info: dict[str, Any], entry: dict[str, Any]) -> str:
    """entry → SE 固定長レコード（出走前 / byte 正確）。"""
    race_key = str(info.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _put(buf, 0, "SE")
    _put(buf, 2, "1")                       # DataKubun=1（出走前）
    _put(buf, 3, "20260617")                # MakeDate
    _put(buf, 11, race_key[0:8])            # KaisaiNengappi
    _put(buf, 19, race_key[8:10])
    _put(buf, 21, race_key[10:12])
    _put(buf, 23, race_key[12:14])
    _put(buf, 25, race_key[14:16])
    _put(buf, 27, str(int(entry.get("frame_no", 0)))[:1])   # Wakuban
    _put(buf, 28, f"{int(entry.get('horse_no', 0)):02d}")   # Umaban
    _put(buf, 30, str(entry.get("ketto_num", ""))[:10])     # KettoNum
    _put(buf, 40, str(entry.get("horse_name", "")))         # Bamei（全角）
    _put(buf, 78, _sex_cd(str(entry.get("sex", "牡"))))     # SexCD
    _put(buf, 85, str(entry.get("trainer_code", ""))[:5])   # ChokyosiCode
    _put(buf, 90, str(entry.get("trainer_name", "")))       # 調教師名略称
    _put(buf, 296, str(entry.get("jockey_code", ""))[:5])   # KisyuCode
    _put(buf, 306, str(entry.get("jockey_name", "")))       # 騎手名略称
    return buf.decode("cp932")


def _json_result_to_se(data: dict[str, Any], result: dict[str, Any]) -> str:
    """result → SE 固定長レコード（確定後 / byte 正確）。"""
    race_key = str(data.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    buf = bytearray(b" " * SE_RECORD_BYTES)
    _put(buf, 0, "SE")
    _put(buf, 2, "7")                       # DataKubun=7（確定・実測区分）
    _put(buf, 3, "20260618")                # MakeDate
    _put(buf, 11, race_key[0:8])            # KaisaiNengappi
    _put(buf, 19, race_key[8:10])
    _put(buf, 21, race_key[10:12])
    _put(buf, 23, race_key[12:14])
    _put(buf, 25, race_key[14:16])
    _put(buf, 28, f"{int(result.get('horse_no', 0)):02d}")  # Umaban
    _put(buf, 334, f"{int(result.get('finish_pos', 0)):02d}")  # KakuteiJyuni

    # 走破タイム MSSf: 分1 + 秒2 + 1/10秒1
    rt = float(result.get("race_time_s", 0) or 0)
    minutes = int(rt // 60)
    seconds = int(rt % 60)
    tenths = round((rt - int(rt)) * 10)
    _put(buf, 338, f"{minutes}{seconds:02d}{tenths}")

    # 上り3F: 3桁 1/10秒
    agari = float(result.get("agari_3f_s", 0) or 0)
    _put(buf, 390, f"{round(agari * 10):03d}")
    return buf.decode("cp932")


def _json_entry_to_um(entry: dict[str, Any]) -> str:
    """entry → UM 固定長レコード（byte 正確）。SexCD は全角名の後 byte[182:183]。"""
    buf = bytearray(b" " * _UM_RECORD_BYTES)
    _put(buf, 0, "UM")
    _put(buf, 2, "1")
    _put(buf, 3, "20260101")                # MakeDate
    _put(buf, 12, str(entry.get("ketto_num", ""))[:10])    # KettoNum
    age = int(entry.get("age", 3) or 3)
    _put(buf, 38, f"{2026 - age}0101")      # 生年月日 YYYYMMDD
    _put(buf, 46, str(entry.get("horse_name", "")))        # UmaName（全角）
    _put(buf, 180, "00")                    # UmaKigoCD
    _put(buf, 182, _sex_cd(str(entry.get("sex", "牡"))))   # SexCD
    return buf.decode("cp932")


def _make_ks(code: str, name: str) -> str:
    """KS 固定長レコード（byte 正確）。code[11:16], 騎手名[41:]。"""
    buf = bytearray(b" " * _MASTER_RECORD_BYTES)
    _put(buf, 0, "KS")
    _put(buf, 2, "1")
    _put(buf, 3, "20260101")
    _put(buf, 11, code[:5])                 # KisyuCode
    _put(buf, 41, name)                     # 騎手氏名（全角）
    return buf.decode("cp932")


def _make_ch(code: str, name: str) -> str:
    """CH 固定長レコード（byte 正確）。code[11:16], 調教師名[41:]。"""
    buf = bytearray(b" " * _MASTER_RECORD_BYTES)
    _put(buf, 0, "CH")
    _put(buf, 2, "1")
    _put(buf, 3, "20260101")
    _put(buf, 11, code[:5])                 # ChokyosiCode
    _put(buf, 41, name)                     # 調教師氏名（全角）
    return buf.decode("cp932")
