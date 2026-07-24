"""レース登録・確定ユースケース。"""

from __future__ import annotations

import datetime

from pci.application.dto import EntryInput, RaceInfo, RaceResultOutput, ResultInput
from pci.domain.pace.pci import aggregate_rpci, calculate_pci, calculate_rpci_from_lap
from pci.domain.pace.running_style import classify_running_style
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import (
    DuplicateRaceKeyAudit,
    RaceCompletenessRepository,
    RaceRepository,
)
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.domain.shared.race_key import RaceKey


class RegisterRaceEntriesUseCase:
    """出走表登録ユースケース。

    レース情報と出走馬リストを受け取り、core 層に保存する。
    ingestion-worker（またはテスト）から呼ばれる。
    """

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self, race_info: RaceInfo, entries: list[EntryInput]) -> int:
        key = RaceKey(race_info.race_key)
        existing_race = self._repo.find_by_key(key)
        existing_entries = {entry.horse_no: entry for entry in self._repo.find_entries(key)}
        is_preliminary = bool(entries) and all(entry.frame_no == 0 for entry in entries)

        # 特別登録の仮順は、確定済みの馬番・枠番・成績を上書きしてはならない。
        if is_preliminary and existing_race is not None:
            has_final_entries = any(entry.frame_no > 0 for entry in existing_entries.values())
            if existing_race.status == RaceStatus.RESULT or has_final_entries:
                return 0

        snapshot_unchanged = _entry_snapshot_matches(existing_entries, entries)
        preserve_result = (
            existing_race is not None
            and existing_race.status == RaceStatus.RESULT
            and snapshot_unchanged
        )
        race = Race(
            race_key=key,
            race_date=race_info.race_date,
            jyo_cd=race_info.jyo_cd,
            distance_m=race_info.distance_m,
            track_type=race_info.track_type,
            field_size=len(entries) if entries else race_info.field_size,
            status=RaceStatus.RESULT if preserve_result else RaceStatus.ENTRIES,
            track_condition=(
                race_info.track_condition
                or (existing_race.track_condition if existing_race is not None else None)
            ),
            weather=(
                race_info.weather
                or (existing_race.weather if existing_race is not None else None)
            ),
            grade=race_info.grade or (existing_race.grade if existing_race is not None else None),
            race_class=(
                race_info.race_class
                or (existing_race.race_class if existing_race is not None else None)
            ),
            rpci_actual=(
                existing_race.rpci_actual
                if preserve_result and existing_race is not None
                else None
            ),
            pci3_actual=(
                existing_race.pci3_actual
                if preserve_result and existing_race is not None
                else None
            ),
            race_s3f=(
                existing_race.race_s3f
                if preserve_result and existing_race is not None
                else None
            ),
            race_l3f=(
                existing_race.race_l3f
                if preserve_result and existing_race is not None
                else None
            ),
        )
        self._repo.save_race(race)

        # FK 整合の自己修復: 参照される馬/騎手/調教師マスタが未取得でも
        # 出走表を登録できるよう、欠損マスタをプレースホルダで補完する。
        self._repo.ensure_horses(e.ketto_num for e in entries)
        self._repo.ensure_jockeys(e.jockey_code for e in entries)
        self._repo.ensure_trainers(e.trainer_code for e in entries)
        self._repo.delete_entries_not_in(key, {entry.horse_no for entry in entries})

        for e in entries:
            previous = existing_entries.get(e.horse_no)
            keep_result = (
                preserve_result
                and previous is not None
                and previous.ketto_num == e.ketto_num
            )
            preserved = previous if keep_result else None
            entry = RaceEntry(
                race_key=key,
                horse_no=e.horse_no,
                frame_no=e.frame_no,
                ketto_num=e.ketto_num,
                weight=e.weight,
                jockey_code=e.jockey_code,
                trainer_code=e.trainer_code,
                finish_pos=preserved.finish_pos if preserved is not None else None,
                race_time_s=preserved.race_time_s if preserved is not None else None,
                agari_3f_s=preserved.agari_3f_s if preserved is not None else None,
                corner_1=preserved.corner_1 if preserved is not None else None,
                corner_2=preserved.corner_2 if preserved is not None else None,
                corner_3=preserved.corner_3 if preserved is not None else None,
                corner_4=preserved.corner_4 if preserved is not None else None,
                pci_actual=preserved.pci_actual if preserved is not None else None,
                running_style=(
                    preserved.running_style if preserved is not None else None
                ),
                popularity=preserved.popularity if preserved is not None else None,
                prize_money=preserved.prize_money if preserved is not None else None,
            )
            self._repo.save_entry(entry)
        return len(entries)


class UpdateRaceMetadataUseCase:
    """既存レースのコース種別・馬場状態・天候だけを安全に更新する。"""

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(
        self,
        race_key_str: str,
        *,
        track_type: str | None = None,
        track_condition: str | None = None,
        weather: str | None = None,
    ) -> bool:
        key = RaceKey(race_key_str)
        races = self._find_target_races(key)
        if not races or (
            track_type is None and track_condition is None and weather is None
        ):
            return False

        for race in races:
            self._repo.save_race(
                Race(
                    race_key=race.race_key,
                    race_date=race.race_date,
                    jyo_cd=race.jyo_cd,
                    distance_m=race.distance_m,
                    track_type=track_type or race.track_type,
                    field_size=race.field_size,
                    status=race.status,
                    track_condition=track_condition or race.track_condition,
                    weather=weather or race.weather,
                    grade=race.grade,
                    race_class=race.race_class,
                    rpci_actual=race.rpci_actual,
                    pci3_actual=race.pci3_actual,
                    race_s3f=race.race_s3f,
                    race_l3f=race.race_l3f,
                )
            )
        return True

    def _find_target_races(self, source_key: RaceKey) -> list[Race]:
        """完全一致と、同じ日付・場・R番号を持つ旧形式キーを返す。"""
        value = source_key.value
        try:
            race_date = datetime.date(
                int(value[0:4]),
                int(value[4:6]),
                int(value[6:8]),
            )
        except ValueError:
            return []
        jyo_cd = value[8:10]
        race_no = value[14:16]
        candidates = [
            race
            for race in self._repo.list_races_by_date(race_date)
            if race.jyo_cd == jyo_cd and race.race_key.value[14:16] == race_no
        ]
        exact = next((race for race in candidates if race.race_key == source_key), None)
        if exact is not None:
            return candidates
        return candidates if len(candidates) == 1 else []


class DeleteDuplicateRaceUseCase:
    """再同期済み正規キーを検証してから旧キーだけを削除する。"""

    def __init__(
        self,
        repo: RaceRepository,
        audit_repo: RaceCompletenessRepository,
    ) -> None:
        self._repo = repo
        self._audit_repo = audit_repo

    def execute(
        self,
        *,
        stale_race_key: str,
        canonical_race_key: str,
        expected_entry_count: int,
        expected_finished_count: int,
        stale_entry_signature: str,
        stale_result_signature: str,
    ) -> bool:
        if stale_race_key == canonical_race_key:
            raise ValueError("旧キーと正規キーには異なる値を指定してください")
        race_date = _race_date_from_key(canonical_race_key)
        if (
            stale_race_key[:10] != canonical_race_key[:10]
            or stale_race_key[-2:] != canonical_race_key[-2:]
        ):
            raise ValueError("旧キーと正規キーの開催日・競馬場・R番号が一致しません")

        groups = self._audit_repo.find_duplicate_race_audits(
            race_date,
            race_date + datetime.timedelta(days=1),
        )
        group = next(
            (
                candidate
                for candidate in groups
                if {key.race_key for key in candidate.keys}
                >= {stale_race_key, canonical_race_key}
            ),
            None,
        )
        if group is None:
            raise ValueError("指定されたキーを含む重複レースが見つかりません")

        keys = {key.race_key: key for key in group.keys}
        stale = keys[stale_race_key]
        canonical = keys[canonical_race_key]
        if (
            stale.entry_signature != stale_entry_signature
            or stale.result_signature != stale_result_signature
        ):
            raise ValueError("監査後に旧キーデータが変更されたため削除を中止しました")
        if canonical.status != RaceStatus.RESULT:
            raise ValueError("正規キーの確定成績が登録されていません")
        if (
            canonical.entry_count != expected_entry_count
            or canonical.field_size != expected_entry_count
            or canonical.finished_count != expected_finished_count
        ):
            raise ValueError("正規キーの再同期件数がmykeibadbと一致しません")
        if canonical.result_signature != stale.result_signature:
            raise ValueError("旧キーと正規キーの中核成績が一致しません")
        if (
            stale.predicted_pace_count > 0 or stale.pace_fit_count > 0
        ) and not _canonical_mart_covers_stale(stale, canonical):
            raise ValueError("旧キーの予想martを正規キー側で完全に代替できません")
        return self._repo.delete_race(RaceKey(stale_race_key))


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
        grade: str | None = None,
        race_s3f: float | None = None,
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
                    weight=(
                        r.body_weight
                        if r.body_weight is not None
                        else base.weight if base else 0.0
                    ),
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
                    popularity=r.popularity,
                    prize_money=r.prize_money,
                )
            )
            pci_values.append(pci_val)
            finish_positions.append(r.finish_pos)

        # TARGET 準拠 RPCI: RA の S3(前半3F)/L3(後半3F) 比から算出。
        # RPCI = S3/L3 × 100 − 50（距離非依存の前後ペース指数）。
        # S3/L3 どちらか未取得時は全馬 PCI 平均にフォールバックする。
        stored_s3f = race_s3f if race_s3f is not None else race.race_s3f
        stored_l3f = race_l3f if race_l3f is not None else race.race_l3f
        race_rpci: float | None = None
        if stored_s3f is not None and stored_l3f is not None:
            race_rpci = calculate_rpci_from_lap(
                Furlong3Time(stored_s3f),
                Furlong3Time(stored_l3f),
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
                    popularity=entry.popularity,
                    prize_money=entry.prize_money,
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
                grade=grade or race.grade,
                race_class=race.race_class,
                rpci_actual=rpci_result.rpci,
                pci3_actual=rpci_result.pci3,
                race_s3f=stored_s3f,
                race_l3f=stored_l3f,
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


def _entry_snapshot_matches(
    existing: dict[int, RaceEntry],
    incoming: list[EntryInput],
) -> bool:
    if set(existing) != {entry.horse_no for entry in incoming}:
        return False
    return all(
        (current := existing.get(entry.horse_no)) is not None
        and current.frame_no == entry.frame_no
        and current.ketto_num == entry.ketto_num
        for entry in incoming
    )


def _race_date_from_key(race_key: str) -> datetime.date:
    """16桁レースキーの先頭8桁を開催日に変換する。"""
    try:
        return datetime.date(
            int(race_key[0:4]),
            int(race_key[4:6]),
            int(race_key[6:8]),
        )
    except (ValueError, IndexError) as exc:
        raise ValueError("レースキーから開催日を取得できません") from exc


def _canonical_mart_covers_stale(
    stale: DuplicateRaceKeyAudit,
    canonical: DuplicateRaceKeyAudit,
) -> bool:
    """正規キーの同一モデル世代が旧martを全件代替できるか判定する。"""
    if (
        sum(item.row_count for item in stale.predicted_pace_models)
        != stale.predicted_pace_count
        or sum(item.row_count for item in stale.pace_fit_models)
        != stale.pace_fit_count
    ):
        return False
    canonical_predicted = {
        item.model_version: item.row_count
        for item in canonical.predicted_pace_models
    }
    canonical_fit = {
        item.model_version: item.row_count for item in canonical.pace_fit_models
    }
    predicted_covered = all(
        canonical_predicted.get(item.model_version, 0) >= item.row_count
        for item in stale.predicted_pace_models
    )
    fit_covered = all(
        canonical_fit.get(item.model_version, 0) >= canonical.entry_count
        for item in stale.pace_fit_models
    )
    return predicted_covered and fit_covered
