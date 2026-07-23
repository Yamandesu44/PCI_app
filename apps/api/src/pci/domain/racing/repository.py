from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey


@dataclass(frozen=True)
class DuplicateRaceGroup:
    """同一開催日・競馬場・R番号に複数キーが存在するレース群。"""

    race_date: datetime.date
    jyo_cd: str
    race_no: str
    race_keys: tuple[str, ...]


@dataclass(frozen=True)
class MartVersionAudit:
    """予想martのモデル世代別行数。"""

    model_version: str
    row_count: int


@dataclass(frozen=True)
class DuplicateRaceKeyAudit:
    """重複レースキー1件に紐づく、統合判断用のデータ概要。"""

    race_key: str
    status: str
    field_size: int
    entry_count: int
    finished_count: int
    entry_signature: str
    result_signature: str
    predicted_pace_count: int
    pace_fit_count: int
    predicted_pace_models: tuple[MartVersionAudit, ...]
    pace_fit_models: tuple[MartVersionAudit, ...]


@dataclass(frozen=True)
class DuplicateRaceAuditGroup:
    """同一レースに属するキーと、キーごとの関連データ概要。"""

    race_date: datetime.date
    jyo_cd: str
    race_no: str
    keys: tuple[DuplicateRaceKeyAudit, ...]


class RaceRepository(Protocol):
    """レースデータへのアクセスを抽象化するリポジトリ界面（ADR-0001）。

    domain 層に定義することで、infrastructure 実装を差し替え可能にする。
    """

    def find_by_key(self, key: RaceKey) -> Race | None: ...

    def find_entries(self, key: RaceKey) -> list[RaceEntry]: ...

    def list_recent_races(self, limit: int = 50) -> list[Race]: ...

    def list_race_dates(self) -> list[datetime.date]: ...

    def list_races_by_date(self, date: datetime.date) -> list[Race]: ...

    def save_race(self, race: Race) -> None: ...

    def save_entry(self, entry: RaceEntry) -> None: ...

    def delete_entries_not_in(self, key: RaceKey, horse_nos: set[int]) -> int:
        """完全な出馬表に存在しない旧エントリを削除する。"""
        ...

    def delete_race(self, key: RaceKey) -> bool: ...

    def find_horse_recent_entries(
        self, ketto_num: str, limit: int = 5, before: datetime.date | None = None
    ) -> list[RaceEntry]:
        """馬の直近確定成績を新しい順に返す。

        before を指定すると、その日より前のレースだけを対象にする
        （バックテストで予測時点より未来のデータを参照しないため）。
        """
        ...

    def find_horse_names(self, ketto_nums: Iterable[str]) -> dict[str, str]:
        """ketto_num → 馬名 のマッピングを返す（一括取得）。存在しないキーは含まない。"""
        ...

    def save_horse(self, horse: Horse) -> None: ...

    def save_jockey(self, jockey: Jockey) -> None: ...

    def save_trainer(self, trainer: Trainer) -> None: ...

    def ensure_horses(self, ketto_nums: Iterable[str]) -> None:
        """参照される馬マスタが無ければプレースホルダを作成する（FK 整合の自己修復）。"""
        ...

    def ensure_jockeys(self, codes: Iterable[str]) -> None:
        """参照される騎手マスタが無ければプレースホルダを作成する（FK 整合の自己修復）。"""
        ...

    def ensure_trainers(self, codes: Iterable[str]) -> None:
        """参照される調教師マスタが無ければプレースホルダを作成する（FK 整合の自己修復）。"""
        ...


class RaceCompletenessRepository(Protocol):
    """JRA平地レースの結果・馬場情報の完全性を検出する読み取りポート。"""

    def count_incomplete_past_races(self, before: datetime.date) -> int: ...

    def find_oldest_incomplete_past_race_date(
        self, before: datetime.date
    ) -> datetime.date | None: ...

    def find_incomplete_past_races(
        self, before: datetime.date, limit: int = 20
    ) -> list[Race]: ...

    def count_missing_track_conditions(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int: ...

    def find_missing_track_conditions(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[Race]: ...

    def count_duplicate_race_groups(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int: ...

    def find_duplicate_race_groups(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[DuplicateRaceGroup]: ...

    def find_duplicate_race_audits(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 10_000,
    ) -> list[DuplicateRaceAuditGroup]: ...
