"""レース照会ユースケース（読み取り専用）。"""

from __future__ import annotations

from pci.application.dto import (
    EntryDetailOutput,
    HorsePaceAnalysisOutput,
    PaceAnalysisOutput,
    RaceDetailOutput,
    ReasonOutput,
)
from pci.application.errors import RaceNotConfirmedError
from pci.domain.pace.pci import FORMULA_VERSION, aggregate_rpci
from pci.domain.racing.race import RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason

_PCI3_POSITIONS = (1, 2, 3)


class GetRaceDetailUseCase:
    """レースの基本情報・出走馬・確定指標を取得する。"""

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self, race_key_str: str) -> RaceDetailOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")

        entries = self._repo.find_entries(key)
        return RaceDetailOutput(
            race_key=str(race.race_key),
            race_date=race.race_date.isoformat(),
            jyo_cd=race.jyo_cd,
            distance_m=race.distance_m,
            track_type=race.track_type,
            status=str(race.status),
            field_size=race.field_size,
            track_condition=race.track_condition,
            weather=race.weather,
            grade=race.grade,
            race_class=race.race_class,
            rpci_actual=race.rpci_actual,
            pci3_actual=race.pci3_actual,
            entries=[
                EntryDetailOutput(
                    horse_no=e.horse_no,
                    frame_no=e.frame_no,
                    ketto_num=e.ketto_num,
                    running_style=e.running_style,
                    pci_actual=e.pci_actual,
                    finish_pos=e.finish_pos,
                )
                for e in entries
            ],
        )


class GetPaceAnalysisUseCase:
    """確定後レースのペース分析（各馬PCI・実績RPCI・PCI3）を取得する。

    RPCI/PCI3 は唯一の真実の場所 `aggregate_rpci`（ADR-0004）で再集計し、
    formula_version と説明可能性 reasons を付して返す。
    """

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self, race_key_str: str) -> PaceAnalysisOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")
        if race.status != RaceStatus.RESULT:
            raise RaceNotConfirmedError(f"レースはまだ確定していません: {race_key_str}")

        entries = self._repo.find_entries(key)
        rpci, pci3, sample_size, reasons = self._aggregate(entries)

        return PaceAnalysisOutput(
            race_key=str(race.race_key),
            formula_version=FORMULA_VERSION,
            field_size=race.field_size,
            sample_size=sample_size,
            rpci_actual=rpci,
            pci3_actual=pci3,
            horses=[
                HorsePaceAnalysisOutput(
                    horse_no=e.horse_no,
                    finish_pos=e.finish_pos,
                    running_style=e.running_style,
                    pci=e.pci_actual,
                    agari_3f_s=e.agari_3f_s,
                    is_pci3_contributor=e.finish_pos in _PCI3_POSITIONS,
                )
                for e in sorted(entries, key=_result_order)
            ],
            reasons=[ReasonOutput(r.code, r.description, r.contribution) for r in reasons],
        )

    def _aggregate(
        self, entries: list[RaceEntry]
    ) -> tuple[float | None, float | None, int, tuple[Reason, ...]]:
        completed = [
            (e.pci_actual, e.finish_pos)
            for e in entries
            if e.pci_actual is not None and e.finish_pos is not None
        ]
        if not completed:
            reason = Reason(code="insufficient", description="PCI算出済みの完走馬がいません")
            return None, None, 0, (reason,)

        pci_values = [pci for pci, _ in completed]
        finish_positions = [pos for _, pos in completed]
        result = aggregate_rpci(pci_values, finish_positions)
        return result.rpci, result.pci3, result.sample_size, result.reasons


def _result_order(entry: RaceEntry) -> tuple[int, int]:
    """着順昇順（未確定は末尾）→ 馬番昇順で並べる表示用キー。"""
    return (entry.finish_pos if entry.finish_pos is not None else 9999, entry.horse_no)
