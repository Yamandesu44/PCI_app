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
    body_weight: float | None = None  # 確定時の馬体重（kg）
    # Phase2（能力指数 ability-v2 用）。mykeibadb 由来。未取得は None。
    popularity: int | None = None  # 単勝人気順（1=1番人気）
    prize_money: int | None = None  # 獲得本賞金（円）


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
    grade: str | None = None
    race_s3f: float | None = None  # RA の HaronTimeS3（前半3F秒）。RPCI 算出に使用
    race_l3f: float | None = None  # RA の HaronTimeL3（後半3F秒）。RPCI 算出に使用
    results: list[ResultRecord] = field(default_factory=list)


@dataclass(frozen=True)
class RaceMetadataRecord:
    """列分解済みデータソースから得た、固定長位置に依存しないレース補足情報。"""

    race_key: str
    track_type: str | None = None
    track_condition: str | None = None
    weather: str | None = None


@dataclass(frozen=True)
class DuplicateDeleteGuard:
    """旧レースキー削除時にAPIで再検証する監査値。"""

    stale_race_key: str
    canonical_race_key: str
    stale_entry_signature: str
    stale_result_signature: str


@dataclass(frozen=True)
class IngestResultsSummary:
    """確定成績同期と旧キー整理の実行件数。"""

    sent_ok: int
    sent_fail: int
    deleted_stale: int
