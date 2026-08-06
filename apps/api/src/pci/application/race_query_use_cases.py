"""レース照会ユースケース（読み取り専用）。"""

from __future__ import annotations

import datetime

from pci.application.dto import (
    CommentOutput,
    EntryDetailOutput,
    ForecastAccuracyOutput,
    HorsePaceAnalysisOutput,
    PaceAnalysisOutput,
    RaceDetailOutput,
    RaceSummaryOutput,
    ReasonOutput,
)
from pci.application.errors import RaceNotConfirmedError
from pci.domain.pace.commentary import (
    CommentGenerator,
    ReviewCommentInput,
    ReviewHorseRef,
    RuleBasedCommentGenerator,
)
from pci.domain.pace.mart_repository import MartRepository
from pci.domain.pace.pci import (
    FORMULA_VERSION,
    aggregate_rpci,
    calculate_rpci_target,
)
from pci.domain.pace.rpci_forecast import PaceLabel, classify_pace
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.racing.repository import RaceRepository
from pci.domain.shared.measurements import Distance, Furlong3Time, RaceTime
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason

_PCI3_POSITIONS = (1, 2, 3)

# JV-Data の空欄プレースホルダ。DBに残った旧データを API 出力前に除去する。
_JV_PLACEHOLDERS: frozenset[str] = frozenset({"@", "＠", "...", "…", "-", "－"})


def _clean_race_label(value: str | None) -> str | None:
    """レース名・グレードの JV-Data プレースホルダを None に正規化する。

    DB内の固定長フィールドは "@" + スペースパディングが CP932 で文字化けした形で
    残っているため、先頭文字が "@"/"＠" の場合もプレースホルダとして除去する。
    """
    if not value:
        return None
    name = value.strip()
    if not name or name in _JV_PLACEHOLDERS:
        return None
    # 固定長パディング残留: "@縲縲縲..." のように先頭が @ の場合もプレースホルダ
    if name[0] in {"@", "＠"}:
        return None
    return name


class ListRacesUseCase:
    """新しい順にレース一覧を取得する（トップ画面のレース選択用）。"""

    _MAX_LIMIT = 1000

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(
        self, limit: int = 50, date: datetime.date | None = None
    ) -> list[RaceSummaryOutput]:
        if date is not None:
            races = self._repo.list_races_by_date(date)
        else:
            # 上限を超える要求はクランプし、過大なクエリを防ぐ。
            capped = max(1, min(limit, self._MAX_LIMIT))
            races = self._repo.list_recent_races(capped)
        return [
            RaceSummaryOutput(
                race_key=str(r.race_key),
                race_date=r.race_date.isoformat(),
                jyo_cd=r.jyo_cd,
                distance_m=r.distance_m,
                track_type=r.track_type,
                status=str(r.status),
                field_size=r.field_size,
                grade=_clean_race_label(r.grade),
                race_class=_clean_race_label(r.race_class),
            )
            for r in races
        ]


class ListRaceDatesUseCase:
    """全開催日一覧を取得する（カレンダー表示用）。"""

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def execute(self) -> list[str]:
        return [d.isoformat() for d in self._repo.list_race_dates()]


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
            grade=_clean_race_label(race.grade),
            race_class=_clean_race_label(race.race_class),
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
    自然文の回顧コメントは CommentGenerator（既定 comment-v2）で生成する。
    mart_repo を指定すると、出走前に保存された想定RPCIとの答え合わせ
    （forecast_accuracy）を合わせて返す（未指定・未保存時は None）。
    """

    def __init__(
        self,
        repo: RaceRepository,
        comment_generator: CommentGenerator | None = None,
        mart_repo: MartRepository | None = None,
    ) -> None:
        self._repo = repo
        self._commenter = comment_generator or RuleBasedCommentGenerator()
        self._mart_repo = mart_repo

    def execute(self, race_key_str: str) -> PaceAnalysisOutput:
        key = RaceKey(race_key_str)
        race = self._repo.find_by_key(key)
        if race is None:
            raise ValueError(f"レースが見つかりません: {race_key_str}")
        if race.status != RaceStatus.RESULT:
            raise RaceNotConfirmedError(f"レースはまだ確定していません: {race_key_str}")

        entries = self._repo.find_entries(key)
        rpci, pci3, sample_size, reasons = self._aggregate(entries, race)

        name_map = self._repo.find_horse_names(e.ketto_num for e in entries if e.ketto_num)
        horses = [
            HorsePaceAnalysisOutput(
                horse_no=e.horse_no,
                frame_no=e.frame_no,
                finish_pos=e.finish_pos,
                running_style=e.running_style,
                pci=e.pci_actual,
                agari_3f_s=e.agari_3f_s,
                is_pci3_contributor=e.finish_pos in _PCI3_POSITIONS,
                horse_name=name_map.get(e.ketto_num),
            )
            for e in sorted(entries, key=_result_order)
        ]

        predicted_label, actual_label, accuracy_output = self._forecast_accuracy(race, rpci)

        review_input = ReviewCommentInput(
            rpci_actual=rpci,
            pci3_actual=pci3,
            formula_version=FORMULA_VERSION,
            track_type=race.track_type,
            field_size=race.field_size,
            sample_size=sample_size,
            horses=tuple(
                ReviewHorseRef(
                    horse_no=h.horse_no,
                    finish_pos=h.finish_pos,
                    running_style=h.running_style,
                    pci=h.pci,
                )
                for h in horses
            ),
            predicted_rpci=accuracy_output.predicted_rpci if accuracy_output else None,
            predicted_label=predicted_label,
            actual_label=actual_label,
        )
        commentary = self._commenter.review_comment(review_input)
        comment = CommentOutput(
            headline=commentary.headline,
            body=list(commentary.body),
            model_version=commentary.model_version,
            reasons=[
                ReasonOutput(r.code, r.description, r.contribution) for r in commentary.reasons
            ],
        )

        return PaceAnalysisOutput(
            race_key=str(race.race_key),
            formula_version=FORMULA_VERSION,
            field_size=race.field_size,
            sample_size=sample_size,
            rpci_actual=rpci,
            pci3_actual=pci3,
            horses=horses,
            reasons=[ReasonOutput(r.code, r.description, r.contribution) for r in reasons],
            comment=comment,
            forecast_accuracy=accuracy_output,
        )

    def _forecast_accuracy(
        self, race: Race, rpci: float | None
    ) -> tuple[PaceLabel | None, PaceLabel | None, ForecastAccuracyOutput | None]:
        """出走前の想定RPCIを取得し、実績と答え合わせする（未保存・未確定時は None）。"""
        if self._mart_repo is None or rpci is None:
            return None, None, None
        predicted = self._mart_repo.find_predicted_pace(str(race.race_key))
        if predicted is None:
            return None, None, None

        predicted_label = PaceLabel(predicted.pace_label)
        actual_label = classify_pace(rpci, race.track_type)
        accuracy_output = ForecastAccuracyOutput(
            predicted_rpci=predicted.predicted_rpci,
            predicted_label=str(predicted_label),
            actual_rpci=rpci,
            actual_label=str(actual_label),
            error=round(rpci - predicted.predicted_rpci, 1),
            label_hit=predicted_label == actual_label,
            model_version=predicted.model_version,
        )
        return predicted_label, actual_label, accuracy_output

    def _aggregate(
        self, entries: list[RaceEntry], race: Race
    ) -> tuple[float | None, float | None, int, tuple[Reason, ...]]:
        completed = [
            (e.pci_actual, e.finish_pos)
            for e in entries
            if e.pci_actual is not None and e.finish_pos is not None
        ]
        if not completed:
            reason = Reason(
                code="insufficient",
                description="ペースを算出できる完走馬のデータがありません。",
            )
            return None, None, 0, (reason,)

        # レースラップを渡さないと常にフォールバック値になり、取り込み時に保存した
        # races.rpci_actual と食い違う（同じ画面でヘッダーと本文の流れが割れる）。
        # pci-v3: 個馬PCIと同じ式をレース自身へ適用する（取り込み側と同一の算出）。
        winner_time = next(
            (e.race_time_s for e in entries if e.finish_pos == 1 and e.race_time_s is not None),
            None,
        )
        race_rpci: float | None = None
        if race.race_l3f is not None and winner_time is not None:
            race_rpci = calculate_rpci_target(
                RaceTime(winner_time),
                Furlong3Time(race.race_l3f),
                Distance(race.distance_m),
            )

        pci_values = [pci for pci, _ in completed]
        finish_positions = [pos for _, pos in completed]
        result = aggregate_rpci(pci_values, finish_positions, race_rpci=race_rpci)
        return result.rpci, result.pci3, result.sample_size, result.reasons


def _result_order(entry: RaceEntry) -> tuple[int, int]:
    """着順昇順（未確定は末尾）→ 馬番昇順で並べる表示用キー。"""
    return (entry.finish_pos if entry.finish_pos is not None else 9999, entry.horse_no)
