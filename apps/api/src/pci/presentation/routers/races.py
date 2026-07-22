"""レース関連エンドポイント。"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from pci.presentation.dependencies import (
    ForecastUseCaseDep,
    ListRaceBoardUseCaseDep,
    ListRaceDatesUseCaseDep,
    ListRacesUseCaseDep,
    PaceAnalysisUseCaseDep,
    RaceDetailUseCaseDep,
)
from pci.presentation.schemas import (
    ForecastSchema,
    PaceAnalysisSchema,
    RaceBoardItemSchema,
    RaceDetailSchema,
    RaceSummarySchema,
)

router = APIRouter(prefix="/api/v1/races", tags=["races"])

# レースキーは16桁数字。境界で検証し、不正値は 422 を返す（use case へ到達させない）。
RaceKeyPath = Annotated[str, Path(pattern=r"^\d{16}$", description="16桁のレースキー")]
LimitQuery = Annotated[int, Query(ge=1, le=1000, description="取得件数の上限")]
DateQuery = Annotated[datetime.date | None, Query(description="絞り込む開催日（YYYY-MM-DD）")]
RequiredDateQuery = Annotated[datetime.date, Query(description="開催日（YYYY-MM-DD）")]


@router.get("/dates", response_model=list[str])
def list_race_dates(use_case: ListRaceDatesUseCaseDep) -> list[str]:
    """全開催日を昇順で返す（カレンダー表示用）。"""
    return use_case.execute()


@router.get("", response_model=list[RaceSummarySchema])
def list_races(
    use_case: ListRacesUseCaseDep,
    limit: LimitQuery = 50,
    date: DateQuery = None,
) -> list[RaceSummarySchema]:
    """新しい順にレース一覧を返す。date 指定時はその日のレースのみ返す。"""
    return [RaceSummarySchema.from_dto(r) for r in use_case.execute(limit, date)]


@router.get("/board", response_model=list[RaceBoardItemSchema])
def list_race_board(
    use_case: ListRaceBoardUseCaseDep,
    date: RequiredDateQuery,
) -> list[RaceBoardItemSchema]:
    """指定日の一覧情報と軽量な展開予想を一括で返す。"""
    return [RaceBoardItemSchema.from_dto(item) for item in use_case.execute(date)]


@router.get("/{race_key}/forecast", response_model=ForecastSchema)
def get_race_forecast(race_key: RaceKeyPath, use_case: ForecastUseCaseDep) -> ForecastSchema:
    """未確定レースの展開予想（想定RPCI・展開シナリオ・各馬 PAI）を返す。"""
    return ForecastSchema.from_dto(use_case.execute(race_key))


@router.get("/{race_key}/pace-analysis", response_model=PaceAnalysisSchema)
def get_race_pace_analysis(
    race_key: RaceKeyPath, use_case: PaceAnalysisUseCaseDep
) -> PaceAnalysisSchema:
    """確定後レースの各馬PCI・実績RPCI・PCI3（formula_version 付き）を返す。"""
    return PaceAnalysisSchema.from_dto(use_case.execute(race_key))


@router.get("/{race_key}", response_model=RaceDetailSchema)
def get_race_detail(race_key: RaceKeyPath, use_case: RaceDetailUseCaseDep) -> RaceDetailSchema:
    """レースの基本情報・出走馬・確定指標を返す。"""
    return RaceDetailSchema.from_dto(use_case.execute(race_key))
