from __future__ import annotations

from typing import Protocol

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey


class RaceRepository(Protocol):
    """レースデータへのアクセスを抽象化するリポジトリ界面（ADR-0001）。

    domain 層に定義することで、infrastructure 実装を差し替え可能にする。
    """

    def find_by_key(self, key: RaceKey) -> Race | None: ...

    def find_entries(self, key: RaceKey) -> list[RaceEntry]: ...

    def list_recent_races(self, limit: int = 50) -> list[Race]: ...

    def save_race(self, race: Race) -> None: ...

    def save_entry(self, entry: RaceEntry) -> None: ...

    def find_horse_recent_entries(self, ketto_num: str, limit: int = 5) -> list[RaceEntry]: ...

    def save_horse(self, horse: Horse) -> None: ...

    def save_jockey(self, jockey: Jockey) -> None: ...

    def save_trainer(self, trainer: Trainer) -> None: ...
