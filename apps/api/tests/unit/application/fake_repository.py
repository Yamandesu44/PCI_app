"""テスト用インメモリ RaceRepository 実装。"""

from __future__ import annotations

from collections.abc import Iterable

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey


class FakeRaceRepository:
    """テスト専用インメモリ実装。RaceRepository Protocol を満たす。"""

    def __init__(self) -> None:
        self._races: dict[str, Race] = {}
        self._entries: dict[tuple[str, int], RaceEntry] = {}
        self._horses: dict[str, Horse] = {}
        self._jockeys: dict[str, Jockey] = {}
        self._trainers: dict[str, Trainer] = {}

    def find_by_key(self, key: RaceKey) -> Race | None:
        return self._races.get(str(key))

    def find_entries(self, key: RaceKey) -> list[RaceEntry]:
        return sorted(
            (e for (rk, _), e in self._entries.items() if rk == str(key)),
            key=lambda e: e.horse_no,
        )

    def list_recent_races(self, limit: int = 50) -> list[Race]:
        races = sorted(
            self._races.values(),
            key=lambda r: (r.race_date, str(r.race_key)),
            reverse=True,
        )
        return races[:limit]

    def find_horse_recent_entries(self, ketto_num: str, limit: int = 5) -> list[RaceEntry]:
        from pci.domain.racing.race import RaceStatus

        result = [
            e
            for e in self._entries.values()
            if e.ketto_num == ketto_num
            and self._races.get(str(e.race_key), None) is not None
            and self._races[str(e.race_key)].status == RaceStatus.RESULT
        ]
        result.sort(
            key=lambda e: self._races[str(e.race_key)].race_date,
            reverse=True,
        )
        return result[:limit]

    def save_race(self, race: Race) -> None:
        self._races[str(race.race_key)] = race

    def save_entry(self, entry: RaceEntry) -> None:
        self._entries[(str(entry.race_key), entry.horse_no)] = entry

    def delete_race(self, key: RaceKey) -> bool:
        race_key = str(key)
        existed = self._races.pop(race_key, None) is not None
        self._entries = {
            entry_key: entry
            for entry_key, entry in self._entries.items()
            if entry_key[0] != race_key
        }
        return existed

    def save_horse(self, horse: Horse) -> None:
        self._horses[horse.ketto_num] = horse

    def save_jockey(self, jockey: Jockey) -> None:
        self._jockeys[jockey.code] = jockey

    def save_trainer(self, trainer: Trainer) -> None:
        self._trainers[trainer.code] = trainer

    def find_horse_names(self, ketto_nums: Iterable[str]) -> dict[str, str]:
        wanted = set(ketto_nums)
        return {k: h.name for k, h in self._horses.items() if k in wanted}

    def ensure_horses(self, ketto_nums: Iterable[str]) -> None:
        for ketto in ketto_nums:
            if ketto and ketto not in self._horses:
                self._horses[ketto] = Horse(ketto_num=ketto, name=ketto)

    def ensure_jockeys(self, codes: Iterable[str]) -> None:
        for code in codes:
            if code and code not in self._jockeys:
                self._jockeys[code] = Jockey(code=code, name=code)

    def ensure_trainers(self, codes: Iterable[str]) -> None:
        for code in codes:
            if code and code not in self._trainers:
                self._trainers[code] = Trainer(code=code, name=code)
