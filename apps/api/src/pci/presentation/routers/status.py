"""取り込み状況（鮮度・失敗履歴）エンドポイント。

`/internal/ingest/*`（ingestion-worker 専用・Bearer トークン保護）とは異なり、
こちらは web フロントエンドがトップ画面の更新状況表示に使う公開 GET エンドポイント。
"""

from __future__ import annotations

import enum

from fastapi import APIRouter

from pci.presentation.dependencies import (
    ForecastPerformanceUseCaseDep,
    IngestStatusUseCaseDep,
)
from pci.presentation.schemas import ForecastPerformanceSchema, IngestStatusSchema

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
