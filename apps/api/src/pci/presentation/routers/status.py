"""取り込み状況（鮮度・失敗履歴）エンドポイント。

`/internal/ingest/*`（ingestion-worker 専用・Bearer トークン保護）とは異なり、
こちらは web フロントエンドがトップ画面の更新状況表示に使う公開 GET エンドポイント。
"""

from __future__ import annotations

from fastapi import APIRouter

from pci.presentation.dependencies import IngestStatusUseCaseDep
from pci.presentation.schemas import IngestStatusSchema

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/ingest-status", response_model=IngestStatusSchema)
def get_ingest_status(use_case: IngestStatusUseCaseDep) -> IngestStatusSchema:
    """直近の取り込みバッチの鮮度・失敗有無を返す（トップ画面の更新状況表示用）。"""
    return IngestStatusSchema.from_dto(use_case.execute())
