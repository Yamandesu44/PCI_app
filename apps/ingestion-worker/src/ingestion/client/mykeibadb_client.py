"""mykeibadb MySQL から特別登録データを読むクライアント。"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ingestion.models import EntryRecord, HorseRecord, RaceEntriesRecord

_RACE_TABLE_CANDIDATES = ("TOKUBETSU_TOROKUBA", "tokubetsu_torokuba")
_ENTRY_TABLE_CANDIDATES = (
    "TOKUBETSU_TOROKUBAGOTO_JOHO",
    "tokubetsu_torokubagoto_joho",
)

_PLACE_CODES = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}

_TRACK_TYPES = {
    "1": "芝",
    "2": "ダート",
    "3": "障害",
    "芝": "芝",
    "ダ": "ダート",
    "ダート": "ダート",
    "障": "障害",
    "障害": "障害",
}


@dataclass(frozen=True)
class MyKeibaDbConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "mykeibadb"
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls) -> MyKeibaDbConfig:
        dsn = os.environ.get("MYKEIBADB_DSN", "")
        if dsn:
            parsed = urlparse(dsn)
            return cls(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=parsed.password or "",
                database=parsed.path.lstrip("/") or "mykeibadb",
            )
        return cls(
            host=os.environ.get("MYKEIBADB_HOST", "localhost"),
            port=int(os.environ.get("MYKEIBADB_PORT", "3306")),
            user=os.environ.get("MYKEIBADB_USER", "root"),
            password=os.environ.get("MYKEIBADB_PASSWORD", ""),
            database=os.environ.get("MYKEIBADB_DATABASE", "mykeibadb"),
            charset=os.environ.get("MYKEIBADB_CHARSET", "utf8mb4"),
        )


class MyKeibaDbClient:
    """mykeibadb の特別登録テーブルを PCI_app の取り込みモデルへ変換する。"""

    def __init__(
        self,
        config: MyKeibaDbConfig | None = None,
        connection: Any | None = None,
    ) -> None:
        self._config = config or MyKeibaDbConfig.from_env()
        self._connection = connection

    def fetch_special_entries(self, date_from: str, date_to: str) -> list[RaceEntriesRecord]:
        connection = self._connection or self._connect()
        race_table = self._find_table(connection, _RACE_TABLE_CANDIDATES)
        entry_table = self._find_table(connection, _ENTRY_TABLE_CANDIDATES)
        races = self._fetch_table(connection, race_table)
        entries = self._fetch_table(connection, entry_table)

        by_key: dict[str, RaceEntriesRecord] = {}
        by_loose_key: dict[str, RaceEntriesRecord] = {}
        for row in races:
            race = _race_from_row(row)
            if date_from <= race.race_date.strftime("%Y%m%d") <= date_to:
                by_key[race.race_key] = race
                by_loose_key[_loose_race_key(row)] = race

        horse_no_by_race: dict[str, int] = {}
        for row in entries:
            race = by_key.get(_race_key_from_row(row)) or by_loose_key.get(_loose_race_key(row))
            if race is None:
                continue
            horse_no_by_race[race.race_key] = horse_no_by_race.get(race.race_key, 0) + 1
            horse_no = _int_or_none(_pick(row, _ENTRY_HORSE_NO_COLUMNS)) or horse_no_by_race[
                race.race_key
            ]
            race.entries.append(_entry_from_row(row, horse_no))

        return [race for race in by_key.values() if race.entries]

    def fetch_special_horses(self, date_from: str, date_to: str) -> list[HorseRecord]:
        connection = self._connection or self._connect()
        entry_table = self._find_table(connection, _ENTRY_TABLE_CANDIDATES)
        horses: dict[str, HorseRecord] = {}
        for row in self._fetch_table(connection, entry_table):
            race_date = _date_from_row(row).strftime("%Y%m%d")
            if not (date_from <= race_date <= date_to):
                continue
            ketto = _str_or_none(_pick(row, _KETTO_COLUMNS))
            if not ketto:
                continue
            name = _str_or_none(_pick(row, _HORSE_NAME_COLUMNS)) or ketto
            sex = _str_or_none(_pick(row, _SEX_COLUMNS))
            horses[ketto] = HorseRecord(ketto_num=ketto.zfill(10), name=name, sex=sex)
        return list(horses.values())

    def _connect(self) -> Any:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:
            raise RuntimeError(
                "mykeibadb モードには PyMySQL が必要です。"
                "`python -m pip install -e \".[mysql]\"` を実行してください。"
            ) from exc
        return pymysql.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database,
            charset=self._config.charset,
            cursorclass=DictCursor,
        )

    def _find_table(self, connection: Any, candidates: tuple[str, ...]) -> str:
        with connection.cursor() as cur:
            cur.execute("SHOW TABLES")
            rows = cur.fetchall()
        table_names = [_first_value(row) for row in rows]
        normalized = {_normalize_name(t): t for t in table_names}
        for candidate in candidates:
            found = normalized.get(_normalize_name(candidate))
            if found:
                return found
        raise RuntimeError(
            f"mykeibadb のテーブルが見つかりません: {', '.join(candidates)}。"
            f"存在するテーブル: {', '.join(table_names)}"
        )

    def _fetch_table(self, connection: Any, table: str) -> list[dict[str, Any]]:
        with connection.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}`")
            rows: list[dict[str, Any]] = cur.fetchall()
        return rows


_RACE_DATE_COLUMNS = (
    "race_date",
    "kaisai_date",
    "ymd",
    "年月日",
    "開催年月日",
    "月日",
    "kaisai_gappi",
    "kaisai_nengappi",
)
_RACE_YEAR_COLUMNS = ("year", "nen", "kaisai_nen", "開催年")
_JYO_COLUMNS = ("jyo_cd", "keibajo_code", "keibajo_cd", "場コード", "競馬場コード", "場所")
_JYO_NAME_COLUMNS = ("jyo_name", "keibajo_name", "競馬場", "場所名")
_KAiji_COLUMNS = ("kaiji", "回次", "開催回")
_NICHiji_COLUMNS = ("nichiji", "日次", "開催日次")
_RACE_NO_COLUMNS = ("race_no", "race_bango", "race_num", "レース番号", "r")
_DISTANCE_COLUMNS = ("distance_m", "kyori", "距離")
_TRACK_COLUMNS = ("track_type", "track_code", "track_cd", "トラックコード", "芝ダ")
_RACE_NAME_COLUMNS = ("race_name", "kyosomei_hondai", "レース名", "競走名", "名称")
_GRADE_COLUMNS = ("grade", "grade_code", "グレード", "重賞区分")

_ENTRY_RACE_DATE_COLUMNS = _RACE_DATE_COLUMNS
_ENTRY_HORSE_NO_COLUMNS = ("horse_no", "umaban", "馬番")
_KETTO_COLUMNS = ("ketto_num", "ketto_toroku_bango", "血統登録番号", "kettobango")
_HORSE_NAME_COLUMNS = ("horse_name", "bamei", "馬名")
_SEX_COLUMNS = ("sex", "seibetsu", "性別")
_TRAINER_COLUMNS = ("trainer_code", "chokyoshi_code", "調教師コード")


def _race_from_row(row: dict[str, Any]) -> RaceEntriesRecord:
    race_date = _date_from_row(row)
    race_key = _race_key_from_row(row)
    jyo_cd = _jyo_cd_from_row(row)
    distance = _int_or_none(_pick(row, _DISTANCE_COLUMNS)) or 1600
    track_type = _track_type(_pick(row, _TRACK_COLUMNS))
    race_name = _str_or_none(_pick(row, _RACE_NAME_COLUMNS))
    grade = _str_or_none(_pick(row, _GRADE_COLUMNS))
    return RaceEntriesRecord(
        race_key=race_key,
        race_date=race_date,
        jyo_cd=jyo_cd,
        distance_m=distance,
        track_type=track_type,
        field_size=1,
        grade=grade,
        race_class=f"{race_name or '特別登録'} 特別登録",
    )


def _entry_from_row(row: dict[str, Any], horse_no: int) -> EntryRecord:
    ketto = _str_or_none(_pick(row, _KETTO_COLUMNS))
    if not ketto:
        raise RuntimeError(f"特別登録馬の血統登録番号を特定できません。列: {', '.join(row.keys())}")
    trainer = _str_or_none(_pick(row, _TRAINER_COLUMNS)) or "TBD"
    return EntryRecord(
        horse_no=horse_no,
        frame_no=0,
        ketto_num=ketto.zfill(10),
        weight=0.0,
        jockey_code="TBD",
        trainer_code=trainer,
    )


def _race_key_from_row(row: dict[str, Any]) -> str:
    date = _date_from_row(row).strftime("%Y%m%d")
    jyo = _jyo_cd_from_row(row)
    kaiji = (_str_or_none(_pick(row, _KAiji_COLUMNS)) or "01").zfill(2)[-2:]
    nichiji = (_str_or_none(_pick(row, _NICHiji_COLUMNS)) or "01").zfill(2)[-2:]
    race_no = (_str_or_none(_pick(row, _RACE_NO_COLUMNS)) or "00").zfill(2)[-2:]
    return f"{date}{jyo}{kaiji}{nichiji}{race_no}"


def _loose_race_key(row: dict[str, Any]) -> str:
    date = _date_from_row(row).strftime("%Y%m%d")
    jyo = _jyo_cd_from_row(row)
    race_no = (_str_or_none(_pick(row, _RACE_NO_COLUMNS)) or "00").zfill(2)[-2:]
    return f"{date}{jyo}{race_no}"


def _date_from_row(row: dict[str, Any]) -> dt.date:
    value = _pick(row, _RACE_DATE_COLUMNS)
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = _str_or_none(value)
    if s:
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) == 8:
            return dt.datetime.strptime(digits, "%Y%m%d").date()
        if len(digits) == 4:
            year = _str_or_none(_pick(row, _RACE_YEAR_COLUMNS))
            if year:
                return dt.datetime.strptime(year[:4] + digits, "%Y%m%d").date()
    raise RuntimeError(f"レース日を特定できません。列: {', '.join(row.keys())}")


def _jyo_cd_from_row(row: dict[str, Any]) -> str:
    code = _str_or_none(_pick(row, _JYO_COLUMNS))
    if code and code.isdigit():
        return code.zfill(2)[-2:]
    name = code or _str_or_none(_pick(row, _JYO_NAME_COLUMNS)) or ""
    for jyo_name, jyo_cd in _PLACE_CODES.items():
        if jyo_name in name:
            return jyo_cd
    raise RuntimeError(f"競馬場コードを特定できません。列: {', '.join(row.keys())}")


def _track_type(value: Any) -> str:
    s = _str_or_none(value) or ""
    return _TRACK_TYPES.get(s, _TRACK_TYPES.get(s[:1], s or "芝"))


def _pick(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {_normalize_name(k): v for k, v in row.items()}
    for candidate in candidates:
        key = _normalize_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _first_value(row: dict[str, Any]) -> str:
    return str(next(iter(row.values())))


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _int_or_none(value: Any) -> int | None:
    s = _str_or_none(value)
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None
