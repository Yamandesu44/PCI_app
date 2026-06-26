"""mykeibadb MySQL から JRA-VAN データを読むクライアント。"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ingestion.models import EntryRecord, HorseRecord, RaceEntriesRecord
from ingestion.parser.jv_spec import RA_RECORD_BYTES, SE_RECORD_BYTES

_RACE_TABLE_CANDIDATES = ("TOKUBETSU_TOROKUBA", "tokubetsu_torokuba")
_ENTRY_TABLE_CANDIDATES = (
    "TOKUBETSU_TOROKUBAGOTO_JOHO",
    "tokubetsu_torokubagoto_joho",
)
_RA_TABLE_CANDIDATES = (
    "RA",
    "JV_RA",
    "JVRA",
    "RACE",
    "RACE_DETAIL",
    "race_shosai",
    "レース詳細",
)
_SE_TABLE_CANDIDATES = (
    "SE",
    "JV_SE",
    "JVSE",
    "UMA_RACE",
    "HORSE_RACE",
    "umagoto_race_joho",
    "馬毎レース情報",
)
_UM_TABLE_CANDIDATES = (
    "UM",
    "JV_UM",
    "JVUM",
    "HORSE_MASTER",
    "kyosoba_master2",
    "競走馬マスタ",
)
_KS_TABLE_CANDIDATES = (
    "KS",
    "JV_KS",
    "JVKS",
    "JOCKEY_MASTER",
    "kishu_master",
    "騎手マスタ",
)
_CH_TABLE_CANDIDATES = (
    "CH",
    "JV_CH",
    "JVCH",
    "TRAINER_MASTER",
    "chokyoshi_master",
    "調教師マスタ",
)

_DEFAULT_EXCLUDED_RACE_KEYS = {
    # 2026/06/28 は TARGET の特別登録上、阪神開催がないため除外する。
    "2026062809011111",
}
_FETCH_MANY_SIZE = 1000

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
    excluded_race_keys: frozenset[str] = frozenset(_DEFAULT_EXCLUDED_RACE_KEYS)

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
        excluded = os.environ.get("MYKEIBADB_EXCLUDE_RACE_KEYS", "")
        return cls(
            host=os.environ.get("MYKEIBADB_HOST", "localhost"),
            port=int(os.environ.get("MYKEIBADB_PORT", "3306")),
            user=os.environ.get("MYKEIBADB_USER", "root"),
            password=os.environ.get("MYKEIBADB_PASSWORD", ""),
            database=os.environ.get("MYKEIBADB_DATABASE", "mykeibadb"),
            charset=os.environ.get("MYKEIBADB_CHARSET", "utf8mb4"),
            excluded_race_keys=frozenset(_parse_excluded_race_keys(excluded)),
        )


class MyKeibaDbClient:
    """mykeibadb の MySQL テーブルを PCI_app の取り込みモデルへ変換する。

    wmykeibadb の出力は環境により「固定長レコードそのもの」または
    「列分解済みテーブル」になり得るため、raw レコード列があればそのまま返し、
    なければ既存の JV-Data パーサが読める固定長レコードを合成する。
    """

    def __init__(
        self,
        config: MyKeibaDbConfig | None = None,
        connection: Any | None = None,
    ) -> None:
        self._config = config or MyKeibaDbConfig.from_env()
        self._connection = connection

    @property
    def excluded_race_keys(self) -> frozenset[str]:
        return self._config.excluded_race_keys

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
            if (
                date_from <= race.race_date.strftime("%Y%m%d") <= date_to
                and race.race_key not in self._config.excluded_race_keys
            ):
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

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """mykeibadb の RA テーブルから指定期間のレース詳細レコードを返す。"""
        connection = self._connection or self._connect()
        table = self._find_table(connection, _RA_TABLE_CANDIDATES)
        for row in self._iter_table_by_date_range(connection, table, date_from, date_to):
            if not _row_in_date_range(row, date_from, date_to):
                continue
            yield _raw_record(row) or _build_ra_record(row)

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """mykeibadb の SE テーブルから指定期間の馬毎レース情報レコードを返す。"""
        connection = self._connection or self._connect()
        table = self._find_table(connection, _SE_TABLE_CANDIDATES)
        for row in self._iter_table_by_date_range(connection, table, date_from, date_to):
            if not _row_in_date_range(row, date_from, date_to):
                continue
            yield _raw_record(row) or _build_se_record(row)

    def iter_um_records(self) -> Iterator[str]:
        """mykeibadb の UM テーブルから競走馬マスタレコードを返す。"""
        connection = self._connection or self._connect()
        table = self._find_table(connection, _UM_TABLE_CANDIDATES)
        for row in self._iter_table(connection, table):
            yield _raw_record(row) or _build_um_record(row)

    def iter_ks_records(self) -> Iterator[str]:
        """mykeibadb の KS テーブルから騎手マスタレコードを返す。"""
        connection = self._connection or self._connect()
        table = self._find_table(connection, _KS_TABLE_CANDIDATES)
        for row in self._iter_table(connection, table):
            yield _raw_record(row) or _build_ks_record(row)

    def iter_ch_records(self) -> Iterator[str]:
        """mykeibadb の CH テーブルから調教師マスタレコードを返す。"""
        connection = self._connection or self._connect()
        table = self._find_table(connection, _CH_TABLE_CANDIDATES)
        for row in self._iter_table(connection, table):
            yield _raw_record(row) or _build_ch_record(row)

    def _connect(self) -> Any:
        try:
            import pymysql
            from pymysql.cursors import SSDictCursor
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
            # 通常の DictCursor は execute() 時点で全件をクライアントメモリへ読む。
            # 1年分の mykeibadb では大きすぎるため、サーバーサイドカーソルで逐次読む。
            cursorclass=SSDictCursor,
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
        return list(self._iter_table(connection, table))

    def _iter_table(self, connection: Any, table: str) -> Iterator[dict[str, Any]]:
        """大きなテーブルを一括でメモリに載せず、一定件数ずつ読み出す。"""
        with connection.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}`")
            fetchmany = getattr(cur, "fetchmany", None)
            if fetchmany is None:
                yield from cur.fetchall()
                return
            while True:
                rows = fetchmany(_FETCH_MANY_SIZE)
                if not rows:
                    break
                yield from rows

    def _iter_table_by_date_range(
        self,
        connection: Any,
        table: str,
        date_from: str,
        date_to: str,
    ) -> Iterator[dict[str, Any]]:
        """開催日列があるテーブルは MySQL 側で対象チャンクだけに絞る。"""
        if self._table_has_columns(connection, table, ("KAISAI_NEN", "KAISAI_GAPPI")):
            ymd_expr = "CAST(CONCAT(`KAISAI_NEN`, LPAD(`KAISAI_GAPPI`, 4, '0')) AS UNSIGNED)"
            yield from self._iter_query(
                connection,
                f"SELECT * FROM `{table}` WHERE {ymd_expr} BETWEEN %s AND %s",
                (int(date_from), int(date_to)),
            )
            return
        if self._table_has_columns(connection, table, ("KAISAI_NENGAPPI",)):
            yield from self._iter_query(
                connection,
                f"SELECT * FROM `{table}` WHERE `KAISAI_NENGAPPI` BETWEEN %s AND %s",
                (date_from, date_to),
            )
            return
        yield from self._iter_table(connection, table)

    def _table_has_columns(self, connection: Any, table: str, columns: tuple[str, ...]) -> bool:
        try:
            with connection.cursor() as cur:
                cur.execute(f"SHOW COLUMNS FROM `{table}`")
                rows = cur.fetchall()
        except Exception:
            return False
        existing = {_normalize_name(_first_value(row)) for row in rows}
        return all(_normalize_name(column) in existing for column in columns)

    def _iter_query(
        self,
        connection: Any,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> Iterator[dict[str, Any]]:
        with connection.cursor() as cur:
            if params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)
            fetchmany = getattr(cur, "fetchmany", None)
            if fetchmany is None:
                yield from cur.fetchall()
                return
            while True:
                rows = fetchmany(_FETCH_MANY_SIZE)
                if not rows:
                    break
                yield from rows


_RACE_DATE_COLUMNS = (
    "KAISAI_NENGAPPI",
    "KAISAI_GAPPI",
    "race_date",
    "kaisai_date",
    "ymd",
    "kaisai_nengetsuhi",
    "kaisai_ymd",
    "年月日",
    "開催年月日",
    "月日",
    "kaisai_gappi",
    "kaisai_nengappi",
)
_RACE_YEAR_COLUMNS = ("year", "nen", "kaisai_nen", "開催年")
_JYO_COLUMNS = (
    "KEIBAJO_CODE",
    "jyo_cd",
    "jyo_code",
    "keibajo_code",
    "keibajo_cd",
    "場コード",
    "競馬場コード",
    "場所",
)
_JYO_NAME_COLUMNS = ("jyo_name", "keibajo_name", "競馬場", "場所名")
_KAiji_COLUMNS = ("kaiji", "回次", "開催回")
_NICHiji_COLUMNS = ("nichiji", "日次", "開催日次")
_RACE_NO_COLUMNS = ("race_no", "race_bango", "race_num", "race_number", "レース番号", "r")
_DISTANCE_COLUMNS = ("distance_m", "kyori", "kyori_m", "距離")
_TRACK_COLUMNS = ("track_type", "track_code", "track_cd", "トラックコード", "芝ダ")
_RACE_NAME_COLUMNS = (
    "KYOSOMEI_HONDAI",
    "KYOSOMEI_RYAKUSHO_10",
    "race_name",
    "kyosomei_hondai",
    "kyoso_mei_hondai",
    "hondai",
    "レース名",
    "競走名",
    "名称",
)
_GRADE_COLUMNS = ("grade", "grade_code", "グレード", "重賞区分")
_CONDITION_NAME_COLUMNS = (
    "KYOSO_JOKEN_MEISHO",
    "condition_name",
    "jyoken_name",
    "kyoso_joken_name",
    "条件名",
    "競走条件名称",
    "クラス",
)
_RAW_RECORD_COLUMNS = ("raw_record", "jv_record", "record", "line", "data", "レコード", "固定長")
_DATA_KUBUN_COLUMNS = ("data_kubun", "datakubun", "データ区分")
_RACE_S3F_COLUMNS = ("race_s3f", "haron_s3", "harontimes3", "前半3f", "前3f")
_RACE_L3F_COLUMNS = ("race_l3f", "haron_l3", "harontimel3", "後半3f", "後3f")

# wmykeibadb が作成する MySQL テーブルは JV-Data の英字列名を大文字で持つ。
_RACE_YEAR_COLUMNS = ("KAISAI_NEN",) + _RACE_YEAR_COLUMNS
_KAiji_COLUMNS = ("KAISAI_KAI",) + _KAiji_COLUMNS
_NICHiji_COLUMNS = ("KAISAI_NICHIME",) + _NICHiji_COLUMNS
_RACE_NO_COLUMNS = ("RACE_BANGO",) + _RACE_NO_COLUMNS
_DISTANCE_COLUMNS = ("KYORI",) + _DISTANCE_COLUMNS
_TRACK_COLUMNS = ("TRACK_CODE",) + _TRACK_COLUMNS
_GRADE_COLUMNS = ("GRADE_CODE",) + _GRADE_COLUMNS
_DATA_KUBUN_COLUMNS = ("DATA_KUBUN",) + _DATA_KUBUN_COLUMNS
_RACE_S3F_COLUMNS = ("ZENHAN_3F",) + _RACE_S3F_COLUMNS
_RACE_L3F_COLUMNS = ("KOHAN_3F",) + _RACE_L3F_COLUMNS

_ENTRY_RACE_DATE_COLUMNS = _RACE_DATE_COLUMNS
_FRAME_NO_COLUMNS = ("frame_no", "wakuban", "枠番")
_ENTRY_HORSE_NO_COLUMNS = ("horse_no", "umaban", "馬番")
_KETTO_COLUMNS = (
    "ketto_num",
    "ketto_toroku_bango",
    "ketto_toroku_no",
    "kettobango",
    "血統登録番号",
)
_HORSE_NAME_COLUMNS = ("horse_name", "bamei", "馬名")
_SEX_COLUMNS = ("sex", "seibetsu", "seibetsu_code", "性別")
_BIRTH_YEAR_COLUMNS = ("birth_year", "seinengappi", "birth", "birth_date", "生年", "生年月日")
# wmykeibadb の umagoto_race_joho は成績列を JV-Data 英字名（大文字）で持つ。
# _normalize_name で小文字化されるため、実列名を各候補へ追加する。
_WEIGHT_COLUMNS = ("BATAIJU", "weight", "bataijyu", "馬体重")
_JOCKEY_COLUMNS = ("jockey_code", "kisyu_code", "kishu_code", "騎手コード")
_TRAINER_COLUMNS = ("trainer_code", "chokyoshi_code", "chokyosi_code", "調教師コード")
_FINISH_POS_COLUMNS = (
    "KAKUTEI_CHAKUJUN",
    "finish_pos",
    "kakutei_jyuni",
    "chakujun",
    "着順",
    "確定着順",
)
_RACE_TIME_COLUMNS = ("SOHA_TIME", "race_time_s", "time", "走破タイム", "タイム")
# 秒単位の上り3F列（"34.5"=34.5秒）。_put_tenths で 1/10 秒へ変換する。
_AGARI_3F_COLUMNS = ("agari_3f_s", "harontimel3", "上り3f", "上がり3f", "後3f")
# 生値の上り3F列（KOHAN_3F は 1/10 秒単位の3桁 "345"=34.5秒）。出力と同形式のため直接書く。
_AGARI_3F_RAW_COLUMNS = ("KOHAN_3F", "kohan_3f")
_CORNER_1_COLUMNS = ("CORNER1_JUNI", "corner_1", "jyuni1c", "1角", "第1コーナー")
_CORNER_2_COLUMNS = ("CORNER2_JUNI", "corner_2", "jyuni2c", "2角", "第2コーナー")
_CORNER_3_COLUMNS = ("CORNER3_JUNI", "corner_3", "jyuni3c", "3角", "第3コーナー")
_CORNER_4_COLUMNS = ("CORNER4_JUNI", "corner_4", "jyuni4c", "4角", "第4コーナー")
_MASTER_CODE_COLUMNS = (
    "code",
    "master_code",
    "kishu_code",
    "chokyoshi_code",
    "騎手コード",
    "調教師コード",
)
_MASTER_NAME_COLUMNS = (
    "name",
    "master_name",
    "kishu_name",
    "chokyoshi_name",
    "shimei",
    "氏名",
    "名前",
    "騎手名",
    "調教師名",
)


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
    kaiji = _code_or_none(_pick(row, _KAiji_COLUMNS), 2) or "01"
    nichiji = _code_or_none(_pick(row, _NICHiji_COLUMNS), 2) or "01"
    race_no = _code_or_none(_pick(row, _RACE_NO_COLUMNS), 2) or "00"
    return f"{date}{jyo}{kaiji}{nichiji}{race_no}"


def _loose_race_key(row: dict[str, Any]) -> str:
    date = _date_from_row(row).strftime("%Y%m%d")
    jyo = _jyo_cd_from_row(row)
    race_no = _code_or_none(_pick(row, _RACE_NO_COLUMNS), 2) or "00"
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
    raw_code = _pick(row, _JYO_COLUMNS)
    code = _code_or_none(raw_code, 2)
    if code:
        return code
    name = _str_or_none(raw_code) or _str_or_none(_pick(row, _JYO_NAME_COLUMNS)) or ""
    for jyo_name, jyo_cd in _PLACE_CODES.items():
        if jyo_name in name:
            return jyo_cd
    raise RuntimeError(f"競馬場コードを特定できません。列: {', '.join(row.keys())}")


def _track_type(value: Any) -> str:
    s = _str_or_none(value) or ""
    return _TRACK_TYPES.get(s, _TRACK_TYPES.get(s[:1], s or "芝"))


def _track_code(value: Any) -> str:
    track_type = _track_type(value)
    if track_type == "ダート":
        return "24"
    if track_type == "障害":
        return "30"
    return "17"


def _row_in_date_range(row: dict[str, Any], date_from: str, date_to: str) -> bool:
    try:
        ymd = _date_from_row(row).strftime("%Y%m%d")
    except RuntimeError:
        return True
    return date_from <= ymd <= date_to


def _raw_record(row: dict[str, Any]) -> str | None:
    raw = _str_or_none(_pick(row, _RAW_RECORD_COLUMNS))
    if not raw:
        return None
    return raw.rstrip("\r\n")


def _build_ra_record(row: dict[str, Any]) -> str:
    race_date = _date_from_row(row)
    nen = f"{race_date.year:04d}"
    month_day = f"{race_date.month:02d}{race_date.day:02d}"
    data_kubun = (_str_or_none(_pick(row, _DATA_KUBUN_COLUMNS)) or "1")[:1]
    race_name = _str_or_none(_pick(row, _RACE_NAME_COLUMNS)) or "@"
    condition_name = _str_or_none(_pick(row, _CONDITION_NAME_COLUMNS)) or ""

    buf = bytearray(b" " * RA_RECORD_BYTES)
    _put_cp932(buf, 0, "RA")
    _put_cp932(buf, 2, data_kubun)
    _put_cp932(buf, 3, dt.date.today().strftime("%Y%m%d"))
    _put_cp932(buf, 11, f"{nen}{month_day}")
    _put_cp932(buf, 19, _jyo_cd_from_row(row))
    _put_cp932(buf, 21, _code_or_none(_pick(row, _KAiji_COLUMNS), 2) or "01")
    _put_cp932(buf, 23, _code_or_none(_pick(row, _NICHiji_COLUMNS), 2) or "01")
    _put_cp932(buf, 25, _code_or_none(_pick(row, _RACE_NO_COLUMNS), 2) or "00")
    _put_cp932(buf, 27, "00")
    _put_cp932(buf, 29, "0000")
    _put_cp932(buf, 33, race_name, 60)
    _put_cp932(buf, 623, condition_name, 60)
    _put_cp932(buf, 697, f"{(_int_or_none(_pick(row, _DISTANCE_COLUMNS)) or 0):04d}")
    _put_cp932(buf, 705, _track_code(_pick(row, _TRACK_COLUMNS)))
    _put_tenths(buf, 969, _float_or_none(_pick(row, _RACE_S3F_COLUMNS)))
    _put_tenths(buf, 975, _float_or_none(_pick(row, _RACE_L3F_COLUMNS)))
    return buf.decode("cp932")


def _build_se_record(row: dict[str, Any]) -> str:
    race_date = _date_from_row(row)
    nen = f"{race_date.year:04d}"
    month_day = f"{race_date.month:02d}{race_date.day:02d}"
    finish_pos = _int_or_none(_pick(row, _FINISH_POS_COLUMNS))
    race_time = _race_time_to_mssf(_pick(row, _RACE_TIME_COLUMNS))
    # 上り3F は2系統: KOHAN_3F(1/10秒の生値) と "上がり3F"(秒)。前者を優先する。
    agari_raw = _str_or_none(_pick(row, _AGARI_3F_RAW_COLUMNS))
    agari_seconds = _float_or_none(_pick(row, _AGARI_3F_COLUMNS))
    has_agari = bool(agari_raw and agari_raw.isdigit()) or bool(agari_seconds)
    data_kubun = _str_or_none(_pick(row, _DATA_KUBUN_COLUMNS))
    if not data_kubun:
        data_kubun = "7" if finish_pos and race_time and has_agari else "1"

    buf = bytearray(b" " * SE_RECORD_BYTES)
    _put_cp932(buf, 0, "SE")
    _put_cp932(buf, 2, data_kubun[:1])
    _put_cp932(buf, 3, dt.date.today().strftime("%Y%m%d"))
    _put_cp932(buf, 11, f"{nen}{month_day}")
    _put_cp932(buf, 19, _jyo_cd_from_row(row))
    _put_cp932(buf, 21, _code_or_none(_pick(row, _KAiji_COLUMNS), 2) or "01")
    _put_cp932(buf, 23, _code_or_none(_pick(row, _NICHiji_COLUMNS), 2) or "01")
    _put_cp932(buf, 25, _code_or_none(_pick(row, _RACE_NO_COLUMNS), 2) or "00")
    _put_cp932(buf, 27, str(_int_or_none(_pick(row, _FRAME_NO_COLUMNS)) or 0)[-1:])
    _put_cp932(buf, 28, f"{(_int_or_none(_pick(row, _ENTRY_HORSE_NO_COLUMNS)) or 0):02d}"[-2:])
    _put_cp932(buf, 30, (_str_or_none(_pick(row, _KETTO_COLUMNS)) or "").zfill(10)[-10:])
    _put_cp932(buf, 40, _str_or_none(_pick(row, _HORSE_NAME_COLUMNS)) or "", 36)
    _put_cp932(buf, 78, _sex_code(_pick(row, _SEX_COLUMNS)))
    _put_cp932(buf, 85, (_str_or_none(_pick(row, _TRAINER_COLUMNS)) or "").zfill(5)[-5:])
    _put_cp932(buf, 296, (_str_or_none(_pick(row, _JOCKEY_COLUMNS)) or "").zfill(5)[-5:])
    _put_cp932(buf, 324, f"{(_int_or_none(_pick(row, _WEIGHT_COLUMNS)) or 0):03d}"[-3:])
    if finish_pos:
        _put_cp932(buf, 334, f"{finish_pos:02d}"[-2:])
    if race_time:
        _put_cp932(buf, 338, race_time)
    _put_corner(buf, 356, _int_or_none(_pick(row, _CORNER_1_COLUMNS)))
    _put_corner(buf, 358, _int_or_none(_pick(row, _CORNER_2_COLUMNS)))
    _put_corner(buf, 360, _int_or_none(_pick(row, _CORNER_3_COLUMNS)))
    _put_corner(buf, 362, _int_or_none(_pick(row, _CORNER_4_COLUMNS)))
    # KOHAN_3F(1/10秒3桁)は出力[390:393]と同形式のため直接書く。秒単位列は _put_tenths で変換。
    if agari_raw and agari_raw.isdigit():
        _put_cp932(buf, 390, agari_raw.zfill(3)[-3:])
    else:
        _put_tenths(buf, 390, agari_seconds)
    return buf.decode("cp932")


def _build_um_record(row: dict[str, Any]) -> str:
    buf = bytearray(b" " * 200)
    _put_cp932(buf, 0, "UM")
    _put_cp932(buf, 2, (_str_or_none(_pick(row, _DATA_KUBUN_COLUMNS)) or "1")[:1])
    _put_cp932(buf, 3, dt.date.today().strftime("%Y%m%d"))
    _put_cp932(buf, 12, (_str_or_none(_pick(row, _KETTO_COLUMNS)) or "").zfill(10)[-10:])
    birth_year = _int_or_none(_pick(row, _BIRTH_YEAR_COLUMNS)) or 0
    if birth_year > 10000:
        birth_year = int(str(birth_year)[:4])
    _put_cp932(buf, 38, f"{birth_year:04d}0101" if birth_year else "00000000")
    _put_cp932(buf, 46, _str_or_none(_pick(row, _HORSE_NAME_COLUMNS)) or "", 36)
    _put_cp932(buf, 182, _sex_code(_pick(row, _SEX_COLUMNS)))
    return buf.decode("cp932")


def _build_ks_record(row: dict[str, Any]) -> str:
    return _build_person_record(
        row,
        "KS",
        ("jockey_code", "kisyu_code", "騎手コード"),
        ("jockey_name", "kisyu_name", "騎手名"),
    )


def _build_ch_record(row: dict[str, Any]) -> str:
    return _build_person_record(
        row,
        "CH",
        ("trainer_code", "chokyoshi_code", "調教師コード"),
        ("trainer_name", "chokyoshi_name", "調教師名"),
    )


def _build_person_record(
    row: dict[str, Any],
    spec: str,
    code_columns: tuple[str, ...],
    name_columns: tuple[str, ...],
) -> str:
    buf = bytearray(b" " * 100)
    _put_cp932(buf, 0, spec)
    _put_cp932(buf, 2, (_str_or_none(_pick(row, _DATA_KUBUN_COLUMNS)) or "1")[:1])
    _put_cp932(buf, 3, dt.date.today().strftime("%Y%m%d"))
    code = _str_or_none(_pick(row, code_columns + _MASTER_CODE_COLUMNS)) or ""
    name = _str_or_none(_pick(row, name_columns + _MASTER_NAME_COLUMNS)) or code
    _put_cp932(buf, 11, code.zfill(5)[-5:])
    _put_cp932(buf, 41, name[:17])
    return buf.decode("cp932")


def _put_cp932(buf: bytearray, offset: int, value: str, length: int | None = None) -> None:
    raw = value.encode("cp932", errors="replace")
    if length is not None:
        raw = raw[:length].ljust(length, b" ")
    end = offset + len(raw)
    buf[offset:end] = raw


def _put_tenths(buf: bytearray, offset: int, value: float | None) -> None:
    if value is None:
        return
    _put_cp932(buf, offset, f"{round(value * 10):03d}"[-3:])


def _put_corner(buf: bytearray, offset: int, value: int | None) -> None:
    if value is None:
        return
    _put_cp932(buf, offset, f"{value:02d}"[-2:])


def _sex_code(value: Any) -> str:
    sex = _str_or_none(value) or ""
    if sex in {"1", "牡"}:
        return "1"
    if sex in {"2", "牝"}:
        return "2"
    if sex in {"3", "騸", "セ"}:
        return "3"
    return ""


def _race_time_to_mssf(value: Any) -> str | None:
    s = _str_or_none(value)
    if not s:
        return None
    if ":" in s:
        minute, rest = s.split(":", 1)
        sec = float(rest)
        return f"{int(minute)}{int(sec):02d}{round((sec - int(sec)) * 10)}"
    digits = "".join(ch for ch in s if ch.isdigit())
    # SOHA_TIME(char4)は MSSf 形式（分1+秒2+1/10秒1）。小数を含まない4桁はそのまま返す。
    # "0594"(0:59.4)のように分が0でも MSSf として扱う（>=1000 判定では取りこぼすため）。
    if "." not in s and len(digits) == 4 and digits != "0000":
        return digits
    seconds = _float_or_none(value)
    if seconds is None:
        return None
    minute = int(seconds // 60)
    sec = int(seconds % 60)
    tenth = round((seconds - int(seconds)) * 10)
    return f"{minute}{sec:02d}{tenth}"


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


def _parse_excluded_race_keys(value: str) -> set[str]:
    specified = {item.strip() for item in value.split(",") if item.strip()}
    return _DEFAULT_EXCLUDED_RACE_KEYS | specified


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _code_or_none(value: Any, width: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return f"{value:0{width}d}"[-width:]
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):0{width}d}"[-width:]
    s = _str_or_none(value)
    if not s:
        return None
    try:
        as_float = float(s.replace(",", ""))
    except ValueError:
        as_float = None
    if as_float is not None and as_float.is_integer():
        return f"{int(as_float):0{width}d}"[-width:]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(width)[-width:] if digits else None


def _int_or_none(value: Any) -> int | None:
    s = _str_or_none(value)
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None


def _float_or_none(value: Any) -> float | None:
    s = _str_or_none(value)
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None
