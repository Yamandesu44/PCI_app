"""レースボード用の一括照会ユースケース。"""

from __future__ import annotations

import datetime

from pci.application.dto import (
    ForecastOutput,
    HorseFitOutput,
    RaceBoardForecastOutput,
    RaceBoardItemOutput,
)
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_query_use_cases import ListRacesUseCase
from pci.domain.pace.adaptability import DEFAULT_WEIGHTS as PAI_WEIGHTS
from pci.domain.pace.mart_repository import MartRepository, RaceBoardForecastRecord
from pci.domain.racing.race import RaceStatus
from pci.domain.racing.repository import RaceRepository

# 「注目」まで押し上げる、合致閾値からの上積み分（PAI点）。
# 合致の中でも特に振れている馬だけを拾うための幅。
_STRONG_MARGIN = 10.0


class ListRaceBoardUseCase:
    """指定日のレースと一覧用予想をまとめて返す。"""

    def __init__(
        self,
        repo: RaceRepository,
        mart_repo: MartRepository,
        forecast_use_case: ForecastRaceUseCase,
    ) -> None:
        self._repo = repo
        self._mart_repo = mart_repo
        self._forecast_use_case = forecast_use_case

    def execute(self, date: datetime.date) -> list[RaceBoardItemOutput]:
        races = ListRacesUseCase(self._repo).execute(date=date)
        forecast_keys = [r.race_key for r in races if r.status == str(RaceStatus.ENTRIES)]
        cached = self._mart_repo.find_race_board_forecasts(forecast_keys)

        items: list[RaceBoardItemOutput] = []
        for race in races:
            if race.status != str(RaceStatus.ENTRIES):
                items.append(RaceBoardItemOutput(race=race))
                continue

            record = cached.get(race.race_key)
            if record is not None:
                items.append(RaceBoardItemOutput(race=race, forecast=_from_record(record)))
                continue

            try:
                forecast = self._forecast_use_case.execute(race.race_key)
            except ValueError:
                items.append(RaceBoardItemOutput(race=race))
                continue

            top = _pick_pace_benefiting_horse(forecast)
            preview = (
                RaceBoardForecastOutput(
                    pace_label=forecast.pace_label,
                    confidence=forecast.confidence,
                    top_horse_no=top.horse_no,
                    top_horse_name=top.horse_name,
                    top_fit_label=top.fit_label,
                    top_fit_strength=_fit_strength(top.pai),
                )
                if top is not None
                else None
            )
            items.append(RaceBoardItemOutput(race=race, forecast=preview))
        return items


def _from_record(record: RaceBoardForecastRecord) -> RaceBoardForecastOutput:
    return RaceBoardForecastOutput(
        pace_label=record.pace_label,
        confidence=record.confidence,
        top_horse_no=record.top_horse_no,
        top_horse_name=record.top_horse_name,
        top_fit_label=record.top_fit_label,
        top_fit_strength=_fit_strength(record.top_pai),
    )


def _pick_pace_benefiting_horse(forecast: ForecastOutput) -> HorseFitOutput | None:
    """今回の流れの恩恵を受ける馬を1頭選ぶ。

    **PAI の最大値では選ばない。** PAI は脚質内の相対量なので、脚質をまたいだ
    最大値は「最も展開が向く馬」を意味しない。実測ではダートの追込が好走率
    0.47x でありながら高い PAI を取りうる（docs/DECISIONS.md ADR-2026-08-04）。

    脚質をまたいで比較できるのは検証済みの脚質別有利度の方（有利−不利で
    芝+2.8% / ダート+6.5%）。まず有利な脚質へ絞り、その中で PAI を使う。
    """
    if not forecast.horses:
        return None
    scores = {
        entry.style: entry.score
        for entry in (forecast.style_advantage.entries if forecast.style_advantage else ())
    }
    # 有利度が無い脚質は互角(50)扱い。同点は PAI で割る。
    return max(
        forecast.horses,
        key=lambda horse: (scores.get(horse.running_style, 50.0), horse.pai),
    )


def _fit_strength(pai: float) -> str:
    """内部適性指数を一覧向けのカテゴリへ丸める。

    閾値はドメインの合致ラベルと同じものを使う。ここへ実数を直書きすると
    PAI のスケール変更に追随できない（pai-v4 で振れ幅を 25 → 10 へ下げた際、
    旧値の 80/70 はほぼ到達しなくなり「注目」が黙って出なくなるところだった）。
    """
    if pai >= PAI_WEIGHTS.matched_threshold + _STRONG_MARGIN:
        return "strong"
    if pai >= PAI_WEIGHTS.matched_threshold:
        return "notable"
    return "normal"
