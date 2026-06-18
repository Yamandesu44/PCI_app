"""アプリケーション層 DTO。

domain エンティティを外部（presentation / ingestion-worker）に露出させないための薄いラッパー。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntryInput:
    """1頭分の出走情報（RegisterRaceEntriesUseCase の入力）。"""

    horse_no: int
    frame_no: int
    ketto_num: str
    weight: float
    jockey_code: str
    trainer_code: str


@dataclass(frozen=True)
class ResultInput:
    """1頭分の確定成績（RecordRaceResultUseCase の入力）。"""

    horse_no: int
    finish_pos: int
    race_time_s: float
    agari_3f_s: float
    corner_1: int | None = None
    corner_2: int | None = None
    corner_3: int | None = None
    corner_4: int | None = None


@dataclass(frozen=True)
class RaceInfo:
    """レース基本情報（RegisterRaceEntriesUseCase の入力）。"""

    race_key: str
    race_date: datetime.date
    jyo_cd: str
    distance_m: int
    track_type: str
    field_size: int
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None


@dataclass
class RaceResultOutput:
    """RecordRaceResultUseCase の出力。"""

    race_key: str
    rpci: float
    pci3: float | None
    formula_version: str
    entry_pcis: dict[int, float] = field(default_factory=dict)
