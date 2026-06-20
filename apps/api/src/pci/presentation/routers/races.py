"""レース関連エンドポイント。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from pci.presentation.dependencies import (
    ForecastUseCaseDep,
    ListRacesUseCaseDep,
    PaceAnalysisUseCaseDep,
    RaceDetailUseCaseDep,
)
from pci.presentation.schemas import (
    ForecastSchema,
    PaceAnalysisSchema,
    RaceDetailSchema,
    RaceSummarySchema,
)

router = APIRouter(prefix="/api/v1/races", tags=["races"])

# レースキーは16桁数字。境界で検証し、不正値は 422 を返す（use case へ到達させない）。
RaceKeyPath = Annotated[str, Path(pattern=r"^\d{16}$", description="16桁のレースキー")]
LimitQuery = Annotated[int, Query(ge=1, le=100, description="取得件数の上限")]


@router.get("", response_model=list[RaceSummarySchema])
def list_races(use_case: ListRacesUseCaseDep, limit: LimitQuery = 50) -> list[RaceSummarySchema]:
    """新しい順にレース一覧を返す（トップ画面のレース選択用）。"""
    return [RaceSummarySchema.from_dto(r) for r in use_case.execute(limit)]


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
