"""競馬マスタエンティティ（馬・騎手・調教師）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Horse:
    ketto_num: str  # 血統登録番号 10桁
    name: str
    sex: str | None = None  # 牡/牝/騸
    birth_year: int | None = None


@dataclass(frozen=True)
class Jockey:
    code: str  # 騎手コード
    name: str


@dataclass(frozen=True)
class Trainer:
    code: str  # 調教師コード
    name: str
