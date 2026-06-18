"""ヘルスチェックエンドポイント。"""

from __future__ import annotations

from fastapi import APIRouter

from pci.presentation.schemas import HealthSchema

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthSchema)
def health() -> HealthSchema:
    return HealthSchema()
