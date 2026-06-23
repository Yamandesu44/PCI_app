"""ingestion-worker 内部データモデル。

JV-Link レコードをパースした結果として得られる中間表現。
Ingest API のリクエストボディに対応する。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HorseRecord:
    """UM レコード（競走馬マスタ）から抽出したデータ。"""

    ketto_num: str          # 血統登録番号 10桁
    name: str
    sex: str | None = None      # 牡/牝/騸
    birth_year: int | None = None


@dataclass(frozen=True)
class JockeyRecord:
    """KS レコード（騎手マスタ）から抽出したデータ。"""

    code: str
    name: str


@dataclass(frozen=True)
class TrainerRecord:
    """CH レコード（調教師マスタ）から抽出したデータ。"""

    code: str
    name: str


@dataclass(frozen=True)
class EntryRecord:
    """SE レコード（出走前）から抽出した1頭分の出走情報。"""

    horse_no: int
    frame_no: int
    ketto_num: str
    weight: float
    jockey_code: str
    trainer_code: str


@dataclass(frozen=True)
class ResultRecord:
    """SE レコード（確定後）から抽出した1頭分の成績。"""

    horse_no: int
    finish_pos: int
    race_time_s: float
    agari_3f_s: float
    corner_1: int | None = None
    corner_2: int | None = None
    corner_3: int | None = None
    corner_4: int | None = None


@dataclass
class RaceEntriesRecord:
    """RA レコード（出走前）から抽出したレース情報 + 出走馬リスト。"""

    race_key: str
    race_date: datetime.date
    jyo_cd: str
    distance_m: int
    track_type: str          # 芝/ダート/障害
    field_size: int
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None
    race_s3f: float | None = None  # HaronTimeS3（前半3F秒）。確定後RAのみ値あり
    race_l3f: float | None = None  # HaronTimeL3（後半3F秒）。確定後RAのみ値あり
    entries: list[EntryRecord] = field(default_factory=list)


@dataclass
class RaceResultRecord:
    """SE レコード（確定後）から抽出したレース情報 + 成績リスト。"""

    race_key: str
    track_condition: str | None = None
    weather: str | None = None
    race_s3f: float | None = None  # RA の HaronTimeS3（前半3F秒）。RPCI 算出に使用
    race_l3f: float | None = None  # RA の HaronTimeL3（後半3F秒）。RPCI 算出に使用
    results: list[ResultRecord] = field(default_factory=list)
