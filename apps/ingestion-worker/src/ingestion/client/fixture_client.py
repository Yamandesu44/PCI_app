"""開発用フィクスチャクライアント。

fixtures/ ディレクトリの JSON ファイルを読み込み、RA / SE / UM / KS / CH
固定長レコード風の文字列を生成して返す。

JV-Link が必要な Windows 環境なしで開発・テストが可能（ADR-0002）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

_log = logging.getLogger(__name__)

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


class FixtureJvLinkClient:
    """fixtures/ の JSON をもとに擬似レコードを生成する開発用クライアント。

    JSON → 固定長文字列に変換することで、本番と同一のパーサパスを通す。
    fixtures/RA_sample.txt, SE_sample_entry.txt 等が存在すれば直接読む。
    存在しなければ JSON ファイルから生成する。
    """

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or _DEFAULT_FIXTURES

    # ----- ra records -----

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        txt = self._dir / "RA_sample.txt"
        if txt.exists():
            yield from _read_lines(txt)
            return
        # JSON から生成
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rec = _json_to_ra(data["race_info"])
            if rec:
                yield rec

    # ----- se records -----

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        for txt in sorted(self._dir.glob("SE_sample*.txt")):
            yield from _read_lines(txt)
            return
        # JSON から生成（エントリ）
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data["entries"]:
                rec = _json_entry_to_se(data["race_info"], entry)
                if rec:
                    yield rec
        # JSON から生成（成績）
        for path in sorted(self._dir.glob("sample_race_result*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for result in data["results"]:
                rec = _json_result_to_se(data, result)
                if rec:
                    yield rec

    # ----- master records -----

    def iter_um_records(self) -> Iterator[str]:
        txt = self._dir / "UM_sample.txt"
        if txt.exists():
            yield from _read_lines(txt)
            return
        # JSON エントリから馬マスタを生成
        seen: set[str] = set()
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in data["entries"]:
                k = e["ketto_num"]
                if k not in seen:
                    seen.add(k)
                    yield _json_entry_to_um(e)

    def iter_ks_records(self) -> Iterator[str]:
        txt = self._dir / "KS_sample.txt"
        if txt.exists():
            yield from _read_lines(txt)
            return
        seen: set[str] = set()
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in data["entries"]:
                code = e.get("jockey_code", "")
                if code and code not in seen:
                    seen.add(code)
                    yield _make_ks(code, e.get("jockey_name", f"騎手{code}"))

    def iter_ch_records(self) -> Iterator[str]:
        txt = self._dir / "CH_sample.txt"
        if txt.exists():
            yield from _read_lines(txt)
            return
        seen: set[str] = set()
        for path in sorted(self._dir.glob("sample_race_entries*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in data["entries"]:
                code = e.get("trainer_code", "")
                if code and code not in seen:
                    seen.add(code)
                    yield _make_ch(code, e.get("trainer_name", f"調教師{code}"))


# ---------------------------------------------------------------------------
# JSON → 固定長レコード文字列 生成ヘルパー
# ---------------------------------------------------------------------------

def _read_lines(path: Path) -> Iterator[str]:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield line.ljust(200)  # 固定長フィールドの位置を保つため200文字にパディング


def _pad(value: str, width: int, fill: str = " ", right_justify: bool = False) -> str:
    if right_justify:
        return value.zfill(width)[:width]
    return value.ljust(width)[:width]


def _json_to_ra(info: dict[str, object]) -> str:
    """sample_race_entries.json の race_info → RA 固定長レコード（Ver.4.9 オフセット）。"""
    race_key = str(info.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    nen = race_key[0:4]
    month_day = race_key[4:8]
    jyo_cd = race_key[8:10]
    kaiji = race_key[10:12]
    nichiji = race_key[12:14]
    race_no = race_key[14:16]
    hold_date = f"{nen}{month_day}"  # 開催年月日 YYYYMMDD

    race_name = _pad(str(info.get("race_class", "") or ""), 50)
    tosu = _pad(str(info.get("field_size", 8)), 2, right_justify=True)
    race_class = _pad(str(info.get("race_class", "") or ""), 50)
    kyori = _pad(str(int(info.get("distance_m", 0) or 0)), 4, right_justify=True)

    ra = (
        "RA"               # [0:2]   RecordSpec
        + "1"              # [2:3]   DataKubun
        + "20260618"       # [3:11]  MakeDate (作成日、固定)
        + hold_date        # [11:19] KaisaiNengappi (開催年月日)
        + jyo_cd           # [19:21]
        + kaiji            # [21:23]
        + nichiji          # [23:25]
        + race_no          # [25:27]
        + "1"              # [27:28] YoubiCd
        + kyori            # [28:32] Kyori (仮置き)
        + race_name        # [32:82] RaceName
        + tosu             # [82:84] Tosu
        + race_class       # [84:134] RaceClass
    )
    return ra


def _json_entry_to_se(info: dict[str, object], entry: dict[str, object]) -> str:
    """sample_race_entries.json の entry → SE 固定長レコード（出走前）。"""
    race_key = str(info.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    nen = race_key[0:4]
    month_day = race_key[4:8]
    jyo_cd = race_key[8:10]
    kaiji = race_key[10:12]
    nichiji = race_key[12:14]
    race_no = race_key[14:16]

    umaban = _pad(str(entry.get("horse_no", 0)), 2, right_justify=True)
    wakuban = _pad(str(entry.get("frame_no", 0)), 2, right_justify=True)
    ketto = _pad(str(entry.get("ketto_num", "")), 10)
    uma_name = _pad(str(entry.get("horse_name", "")), 36)
    sex_cd = {"牡": "1", "牝": "2", "騸": "3"}.get(str(entry.get("sex", "牡")), "1")
    trainer_code = _pad(str(entry.get("trainer_code", "")), 4)
    trainer_name = _pad(str(entry.get("trainer_name", "")), 36)
    jockey_code = _pad(str(entry.get("jockey_code", "")), 4)
    jockey_name = _pad(str(entry.get("jockey_name", "")), 36)
    futan = _pad("55", 2, right_justify=True)
    weight = int(entry.get("weight", 460) or 460)
    bataijyu = _pad(str(weight), 4, right_justify=True)

    se = (
        "SE"                        # [0:2]
        + "1"                       # [2:3] DataKubun
        + f"{nen}{month_day}".ljust(8)[:8]  # [3:11] MakeDate
        + jyo_cd                    # [11:13]
        + kaiji                     # [13:15]
        + nichiji                   # [15:17]
        + race_no                   # [17:19]
        + umaban                    # [19:21]
        + wakuban                   # [21:23]
        + ketto                     # [23:33]
        + uma_name                  # [33:69]
        + " "                       # [69:70] UmaKigo
        + sex_cd                    # [70:71]
        + "01"                      # [71:73] TozaiSo
        + trainer_code              # [73:77]
        + trainer_name              # [77:113]
        + "    "                    # [113:117] 予備フィールド
        + jockey_code               # [117:121]
        + jockey_name               # [121:157]
        + futan                     # [157:159]
        + bataijyu                  # [159:163]
        + "00"                      # [163:165] ZogenSa
        + " "                       # [165:166] ZogenFugo
    )
    # 600 バイトまで空白パディング（確定フィールドを未使用のまま確保）
    return se.ljust(600)


def _json_result_to_se(data: dict[str, object], result: dict[str, object]) -> str:
    """sample_race_result.json の result → SE 固定長レコード（確定後）。"""
    race_key = str(data.get("race_key", ""))
    if len(race_key) != 16:
        return ""
    nen = race_key[0:4]
    month_day = race_key[4:8]
    jyo_cd = race_key[8:10]
    kaiji = race_key[10:12]
    nichiji = race_key[12:14]
    race_no = race_key[14:16]

    umaban = _pad(str(result.get("horse_no", 0)), 2, right_justify=True)

    # 走破タイム
    race_time_s: float = float(result.get("race_time_s", 0) or 0)
    time_m = int(race_time_s // 60)
    time_s = int(race_time_s % 60)
    time_k = round((race_time_s - int(race_time_s)) * 10)
    soha_m = _pad(str(time_m), 2, right_justify=True)
    soha_s = _pad(str(time_s), 2, right_justify=True)
    soha_k = _pad(str(time_k), 2, right_justify=True)

    # 上がり3F
    agari: float = float(result.get("agari_3f_s", 0) or 0)
    agari_bu = _pad(str(int(agari)), 2, right_justify=True)
    agari_ko = _pad(str(round((agari - int(agari)) * 10)), 2, right_justify=True)

    finish_pos = _pad(str(result.get("finish_pos", 0)), 2, right_justify=True)
    c1 = _pad(str(result.get("corner_1", 0) or 0), 2, right_justify=True)
    c2 = _pad(str(result.get("corner_2", 0) or 0), 2, right_justify=True)
    c3 = _pad(str(result.get("corner_3", 0) or 0), 2, right_justify=True)
    c4 = _pad(str(result.get("corner_4", 0) or 0), 2, right_justify=True)

    # 580バイトまで空白埋めして確定フィールドを配置
    header = (
        "SE"
        + "4"              # DataKubun=4（確定）
        + f"{nen}{month_day}".ljust(8)[:8]
        + jyo_cd + kaiji + nichiji + race_no
        + umaban
        + "  "             # wakuban（空白）
        + " " * 10         # ketto_num（空白）
        + " " * 36         # uma_name（空白）
        + " " * 2          # UmaKigo + sex
        + " " * 2          # TozaiSo
        + " " * 4          # trainer_code
        + " " * 36         # trainer_name
        + " " * 4          # 予備
        + " " * 4          # jockey_code
        + " " * 36         # jockey_name
        + " " * 2          # futan
        + " " * 4          # bataijyu
        + " " * 3          # zogen
    )
    # [2:167] = 165 bytes、残り 580-167=413 bytes を空白埋め後、確定フィールドを追加
    result_fields = finish_pos + soha_m + soha_s + soha_k + agari_bu + agari_ko + c1 + c2 + c3 + c4
    se = header.ljust(580) + result_fields
    return se.ljust(620)


def _json_entry_to_um(entry: dict[str, object]) -> str:
    """entry データから UM 固定長レコードを生成する（Ver.4.9 オフセット）。"""
    ketto = _pad(str(entry.get("ketto_num", "")), 10)
    name = _pad(str(entry.get("horse_name", "")), 18)       # [46:64] 18 chars
    name_kana = _pad(str(entry.get("horse_name", "")), 36)  # [64:100] 36 chars
    sex_cd = {"牡": "1", "牝": "2", "騸": "3"}.get(str(entry.get("sex", "牡")), "1")
    age = int(entry.get("age", 3) or 3)
    birth_year = 2026 - age
    um = (
        "UM"
        + "1"
        + "20260101"           # MakeDate [3:11]
        + " "                  # UmaKigo [11:12]
        + ketto                # [12:22]
        + "00000000"           # [22:30] 追加日付1
        + "00000000"           # [30:38] 追加日付2
        + f"{birth_year}0101"  # [38:46] 生年月日
        + name                 # [46:64] UmaName (18 chars)
        + name_kana            # [64:100] UmaNameKana (36 chars)
        + " " * 60             # [100:160] UmaNameEng
        + "0"                  # [160:161] ZaikyuFlag
        + " " * 19             # [161:180] Reserved
        + "00"                 # [180:182] UmaKigoCD
        + sex_cd               # [182:183] SexCD
    )
    return um.ljust(200)


def _make_ks(code: str, name: str) -> str:
    """KS 固定長レコードを生成する（Ver.4.9 オフセット）。"""
    return (
        "KS"
        + "1"
        + "20260101"        # MakeDate [3:11]
        + _pad(code, 5)     # [11:16] KisyuCode (5桁)
        + "0"               # [16:17] フラグ
        + "00000000"        # [17:25] Date1
        + "00000000"        # [25:33] Date2
        + "00000000"        # [33:41] BirthDate
        + _pad(name, 17)    # [41:58] 騎手氏名 (17 chars)
    ).ljust(100)


def _make_ch(code: str, name: str) -> str:
    """CH 固定長レコードを生成する（Ver.4.9 オフセット）。"""
    return (
        "CH"
        + "1"
        + "20260101"        # MakeDate [3:11]
        + _pad(code, 5)     # [11:16] ChokyosiCode (5桁)
        + "0"               # [16:17] フラグ
        + "00000000"        # [17:25] Date1
        + "00000000"        # [25:33] Date2
        + "00000000"        # [33:41] BirthDate
        + _pad(name, 17)    # [41:58] 調教師氏名 (17 chars)
    ).ljust(100)
