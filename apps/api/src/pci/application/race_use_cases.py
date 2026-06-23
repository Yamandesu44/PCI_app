"""レース登録・確定ユースケース。"""

from __future__ import annotations

from pci.application.dto import EntryInput, RaceInfo, RaceResultOutput, ResultInput
from pci.domain.pace.pci import aggregate_rpci, calculate_pci, calculate_rpci_from_lap
from pci.domain.pace.running_style import classify_running_style
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.domain.shared.race_key import RaceKey


class RegisterRaceEntriesUseCase:
    """出走表登録ユースケース。

    レース情報と出走馬リストを受け取り、core 層に保存する。
    ingestion-worker（またはテスト）から呼ばれる。
    """

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self, race_info: RaceInfo, entries: list[EntryInput]) -> None:
        key = RaceKey(race_info.race_key)
        race = Race(
            race_key=key,
            race_date=race_info.race_date,
            jyo_cd=race_info.jyo_cd,
            distance_m=race_info.distance_m,
            track_type=race_info.track_type,
            field_size=race_info.field_size,
            status=RaceStatus.ENTRIES,
            track_condition=race_info.track_condition,
            weather=race_info.weather,
            grade=race_info.grade,
            race_class=race_info.race_class,
        )
        self._repo.save_race(race)

        # FK 整合の自己修復: 参照される馬/騎手/調教師マスタが未取得でも
        # 出走表を登録できるよう、欠損マスタをプレースホルダで補完する。
        self._repo.ensure_horses(e.ketto_num for e in entries)
        self._repo.ensure_jockeys(e.jockey_code for e in entries)
        self._repo.ensure_trainers(e.trainer_code for e in entries)

        for e in entries:
            entry = RaceEntry(
                race_key=key,
                horse_no=e.horse_no,
                frame_no=e.frame_no,
                ketto_num=e.ketto_num,
                weight=e.weight,
                jockey_code=e.jockey_code,
                trainer_code=e.trainer_code,
            )
            self._repo.save_entry(entry)


class RecordRaceResultUseCase:
    """レース確定結果記録ユースケース。

    確定成績を受け取り、各馬の PCI を算出したうえで
    RPCI・PCI3 を集計し、Race / RaceEntry を更新する。
    脚質（過去5走 4角通過順位ベース）も同時に更新する。
    """

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(
        self,
        race_key_str: str,
        results: list[ResultInput],
        track_condition: str | None = None,
        weather: str | None = None,
        race_l3f: float | None = None,
    ) -> RaceResultOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")

        existing = {e.horse_no: e for e in self._repo.find_entries(key)}
        distance = Distance(race.distance_m)

        pci_values: list[float] = []
        finish_positions: list[int] = []
        entries_to_save: list[RaceEntry] = []

        for r in results:
            pci_val = calculate_pci(
                RaceTime(r.race_time_s),
                Furlong3Time(r.agari_3f_s),
                distance,
            ).value

            base = existing.get(r.horse_no)
            entries_to_save.append(
                RaceEntry(
                    race_key=key,
                    horse_no=r.horse_no,
                    frame_no=base.frame_no if base else r.horse_no,
                    ketto_num=base.ketto_num if base else "",
                    weight=base.weight if base else 0.0,
                    jockey_code=base.jockey_code if base else "",
                    trainer_code=base.trainer_code if base else "",
                    finish_pos=r.finish_pos,
                    race_time_s=r.race_time_s,
                    agari_3f_s=r.agari_3f_s,
                    corner_1=r.corner_1,
                    corner_2=r.corner_2,
                    corner_3=r.corner_3,
                    corner_4=r.corner_4,
                    pci_actual=pci_val,
                )
            )
            pci_values.append(pci_val)
            finish_positions.append(r.finish_pos)

        # TARGET 準拠 RPCI: RA の HaronTimeL3（レース後半3F）が得られた場合は
        # 勝ち馬の走破タイムと組み合わせてラップから算出する。未取得時は全馬平均にフォールバック。
        race_rpci: float | None = None
        if race_l3f is not None:
            winner = next((r for r in results if r.finish_pos == 1), None)
            if winner is not None:
                race_rpci = calculate_rpci_from_lap(
                    RaceTime(winner.race_time_s),
                    Furlong3Time(race_l3f),
                    distance,
                )

        rpci_result = aggregate_rpci(pci_values, finish_positions, race_rpci=race_rpci)

        # FK 整合の自己修復（成績側でも保険）。出走表が先に登録済みなら no-op。
        self._repo.ensure_horses(e.ketto_num for e in entries_to_save)
        self._repo.ensure_jockeys(e.jockey_code for e in entries_to_save)
        self._repo.ensure_trainers(e.trainer_code for e in entries_to_save)

        for entry in entries_to_save:
            running_style = _resolve_running_style(entry, self._repo)
            self._repo.save_entry(
                RaceEntry(
                    race_key=entry.race_key,
                    horse_no=entry.horse_no,
                    frame_no=entry.frame_no,
                    ketto_num=entry.ketto_num,
                    weight=entry.weight,
                    jockey_code=entry.jockey_code,
                    trainer_code=entry.trainer_code,
                    finish_pos=entry.finish_pos,
                    race_time_s=entry.race_time_s,
                    agari_3f_s=entry.agari_3f_s,
                    corner_1=entry.corner_1,
                    corner_2=entry.corner_2,
                    corner_3=entry.corner_3,
                    corner_4=entry.corner_4,
                    pci_actual=entry.pci_actual,
                    running_style=running_style,
                )
            )

        self._repo.save_race(
            Race(
                race_key=race.race_key,
                race_date=race.race_date,
                jyo_cd=race.jyo_cd,
                distance_m=race.distance_m,
                track_type=race.track_type,
                field_size=race.field_size,
                status=RaceStatus.RESULT,
                track_condition=track_condition or race.track_condition,
                weather=weather or race.weather,
                grade=race.grade,
                race_class=race.race_class,
                rpci_actual=rpci_result.rpci,
                pci3_actual=rpci_result.pci3,
            )
        )

        return RaceResultOutput(
            race_key=race_key_str,
            rpci=rpci_result.rpci,
            pci3=rpci_result.pci3,
            formula_version=rpci_result.formula_version,
            entry_pcis={
                e.horse_no: e.pci_actual for e in entries_to_save if e.pci_actual is not None
            },
        )


def _resolve_running_style(entry: RaceEntry, repo: RaceRepository) -> str | None:
    """直近5走の4角通過順位から脚質ラベルを返す。データ不足時は None。"""
    if not entry.ketto_num:
        return None
    recent = repo.find_horse_recent_entries(entry.ketto_num, limit=5)
    c4_positions = tuple(e.corner_4 for e in recent if e.corner_4 is not None)
    if not c4_positions:
        return None
    return str(classify_running_style(c4_positions).label)
