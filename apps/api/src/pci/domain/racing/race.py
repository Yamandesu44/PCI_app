from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import StrEnum

from pci.domain.shared.race_key import RaceKey


class RaceStatus(StrEnum):
    ENTRIES = "entries"  # 出馬表確定（結果待ち）
    RESULT = "result"  # レース確定後


class TrackType(StrEnum):
    TURF = "芝"
    DIRT = "ダート"
    HURDLE = "障害"


@dataclass
class Race:
    """レース集約ルート。出走前（entries）と確定後（result）の両状態を持つ（ADR-0006）。"""

    race_key: RaceKey
    race_date: datetime.date
    jyo_cd: str  # 競馬場コード
    distance_m: int  # 距離(m)
    track_type: str  # TrackType の値
    field_size: int  # 出走頭数
    status: RaceStatus = field(default=RaceStatus.ENTRIES)
    track_condition: str | None = None  # 良/稍重/重/不良
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None
    rpci_actual: float | None = None  # 実績RPCI（確定後）
    pci3_actual: float | None = None  # PCI3（確定後）
