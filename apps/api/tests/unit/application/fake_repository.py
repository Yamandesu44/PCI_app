"""テスト用インメモリ RaceRepository 実装。"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections.abc import Iterable

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import (
    DuplicateRaceAuditGroup,
    DuplicateRaceGroup,
    DuplicateRaceKeyAudit,
)
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

    def list_race_dates(self) -> list[datetime.date]:
        return sorted({r.race_date for r in self._races.values()})

    def list_races_by_date(self, date: datetime.date) -> list[Race]:
        return sorted(
            [r for r in self._races.values() if r.race_date == date],
            key=lambda r: str(r.race_key),
        )

    def count_incomplete_past_races(self, before: datetime.date) -> int:
        return len(self.find_incomplete_past_races(before, limit=len(self._races)))

    def find_oldest_incomplete_past_race_date(
        self, before: datetime.date
    ) -> datetime.date | None:
        races = self.find_incomplete_past_races(before, limit=len(self._races))
        return min((race.race_date for race in races), default=None)

    def find_incomplete_past_races(
        self, before: datetime.date, limit: int = 20
    ) -> list[Race]:
        races = [
            race
            for race in self._races.values()
            if race.race_date < before and race.status == RaceStatus.ENTRIES
            and race.jyo_cd in _JRA_PLACE_CODES
            and race.track_type != "障害"
        ]
        races.sort(key=lambda race: (race.race_date, str(race.race_key)), reverse=True)
        return races[:limit]

    def count_missing_track_conditions(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int:
        return len(
            self.find_missing_track_conditions(
                on_or_after, before, limit=len(self._races)
            )
        )

    def find_missing_track_conditions(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[Race]:
        races = [
            race
            for race in self._races.values()
            if on_or_after <= race.race_date < before
            and race.status == RaceStatus.RESULT
            and race.jyo_cd in _JRA_PLACE_CODES
            and race.track_type != "障害"
            and race.track_condition is None
        ]
        races.sort(key=lambda race: (race.race_date, str(race.race_key)), reverse=True)
        return races[:limit]

    def count_duplicate_race_groups(
        self, on_or_after: datetime.date, before: datetime.date
    ) -> int:
        return len(
            self.find_duplicate_race_groups(
                on_or_after, before, limit=len(self._races)
            )
        )

    def find_duplicate_race_groups(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 20,
    ) -> list[DuplicateRaceGroup]:
        grouped: dict[tuple[datetime.date, str, str], list[str]] = {}
        for race in self._races.values():
            race_key = str(race.race_key)
            if (
                on_or_after <= race.race_date < before
                and race.jyo_cd in _JRA_PLACE_CODES
                and race.track_type != "障害"
                and len(race_key) == 16
            ):
                identity = (race.race_date, race.jyo_cd, race_key[-2:])
                grouped.setdefault(identity, []).append(race_key)
        duplicates = [
            DuplicateRaceGroup(
                race_date=identity[0],
                jyo_cd=identity[1],
                race_no=identity[2],
                race_keys=tuple(sorted(race_keys)),
            )
            for identity, race_keys in grouped.items()
            if len(race_keys) > 1
        ]
        duplicates.sort(
            key=lambda group: (group.race_date, group.jyo_cd, group.race_no),
            reverse=True,
        )
        return duplicates[:limit]

    def find_duplicate_race_audits(
        self,
        on_or_after: datetime.date,
        before: datetime.date,
        limit: int = 10_000,
    ) -> list[DuplicateRaceAuditGroup]:
        groups = self.find_duplicate_race_groups(on_or_after, before, limit=limit)
        return [
            DuplicateRaceAuditGroup(
                race_date=group.race_date,
                jyo_cd=group.jyo_cd,
                race_no=group.race_no,
                keys=tuple(self._duplicate_key_audit(key) for key in group.race_keys),
            )
            for group in groups
        ]

    def _duplicate_key_audit(self, race_key: str) -> DuplicateRaceKeyAudit:
        race = self._races[race_key]
        entries = self.find_entries(race.race_key)
        finished = [entry for entry in entries if entry.finish_pos is not None]
        entry_values = [
            (entry.horse_no, entry.frame_no, entry.ketto_num)
            for entry in entries
        ]
        result_values = [
            (
                entry.horse_no,
                entry.finish_pos,
                entry.race_time_s,
                entry.agari_3f_s,
                entry.corner_1,
                entry.corner_2,
                entry.corner_3,
                entry.corner_4,
            )
            for entry in finished
        ]
        return DuplicateRaceKeyAudit(
            race_key=race_key,
            status=str(race.status),
            field_size=race.field_size,
            entry_count=len(entries),
            finished_count=len(finished),
            entry_signature=self._signature(entry_values),
            result_signature=self._signature(result_values),
            predicted_pace_count=0,
            pace_fit_count=0,
        )

    @staticmethod
    def _signature(values: list[tuple[object, ...]]) -> str:
        payload = json.dumps(values, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("ascii")).hexdigest()

    def find_horse_recent_entries(
        self, ketto_num: str, limit: int = 5, before: datetime.date | None = None
    ) -> list[RaceEntry]:
        from pci.domain.racing.race import RaceStatus

        result = [
            e
            for e in self._entries.values()
            if e.ketto_num == ketto_num
            and self._races.get(str(e.race_key), None) is not None
            and self._races[str(e.race_key)].status == RaceStatus.RESULT
            and (before is None or self._races[str(e.race_key)].race_date < before)
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

    def delete_entries_not_in(self, key: RaceKey, horse_nos: set[int]) -> int:
        race_key = str(key)
        targets = [
            entry_key
            for entry_key in self._entries
            if entry_key[0] == race_key and entry_key[1] not in horse_nos
        ]
        for entry_key in targets:
            del self._entries[entry_key]
        return len(targets)

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


_JRA_PLACE_CODES = frozenset(f"{code:02d}" for code in range(1, 11))
