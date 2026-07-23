"""取り込み状況（鮮度・失敗履歴）エンドポイント。

`/internal/ingest/*`（ingestion-worker 専用・Bearer トークン保護）とは異なり、
こちらは web フロントエンドがトップ画面の更新状況表示に使う公開 GET エンドポイント。
"""

from __future__ import annotations

import enum
from typing import Literal

from fastapi import APIRouter, Query

from pci.presentation.dependencies import (
    ForecastMissesUseCaseDep,
    ForecastPerformanceUseCaseDep,
    IngestStatusUseCaseDep,
)
from pci.presentation.schemas import (
    ForecastMissesSchema,
    ForecastPerformanceSchema,
    IngestStatusSchema,
)

router = APIRouter(prefix="/api/v1", tags=["status"])


class ForecastPerformancePeriod(enum.IntEnum):
    """画面で選択できる予想検証期間。"""

    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180


@router.get("/ingest-status", response_model=IngestStatusSchema)
def get_ingest_status(use_case: IngestStatusUseCaseDep) -> IngestStatusSchema:
    """直近の取り込みバッチの鮮度・失敗有無を返す（トップ画面の更新状況表示用）。"""
    return IngestStatusSchema.from_dto(use_case.execute())


@router.get("/forecast-performance", response_model=ForecastPerformanceSchema)
def get_forecast_performance(
    use_case: ForecastPerformanceUseCaseDep,
    days: ForecastPerformancePeriod = ForecastPerformancePeriod.DAYS_90,
) -> ForecastPerformanceSchema:
    """指定期間の保存済み事前予想について、展開ラベル的中率を返す。"""
    return ForecastPerformanceSchema.from_dto(use_case.execute(period_days=int(days)))


@router.get("/forecast-performance/misses", response_model=ForecastMissesSchema)
def get_forecast_misses(
    use_case: ForecastMissesUseCaseDep,
    days: ForecastPerformancePeriod = ForecastPerformancePeriod.DAYS_90,
    track_type: Literal["芝", "ダート"] | None = None,
    predicted_label: Literal["ハイ", "平均", "スロー"] | None = None,
    actual_label: Literal["ハイ", "平均", "スロー"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> ForecastMissesSchema:
    """不一致レースを期間・コース・展開区分で絞り込んで返す。"""
    return ForecastMissesSchema.from_dto(
        use_case.execute(
            period_days=int(days),
            track_type=track_type,
            predicted_label=predicted_label,
            actual_label=actual_label,
            offset=offset,
            limit=limit,
        )
    )
