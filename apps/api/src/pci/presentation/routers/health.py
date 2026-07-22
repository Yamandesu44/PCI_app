"""ヘルスチェックエンドポイント。"""

from __future__ import annotations

from fastapi import APIRouter, Response

from pci.presentation.dependencies import DatabaseReadinessDep
from pci.presentation.schemas import HealthSchema, ReadinessSchema

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthSchema)
def health() -> HealthSchema:
    return HealthSchema()


@router.get(
    "/ready",
    response_model=ReadinessSchema,
    responses={503: {"model": ReadinessSchema}},
)
def readiness(state: DatabaseReadinessDep, response: Response) -> ReadinessSchema:
    """DB接続とマイグレーション適用状態を含む利用可能性を返す。"""
    if state.ready:
        return ReadinessSchema(status="ready", database="ok")

    response.status_code = 503
    if state.database == "schema_outdated":
        return ReadinessSchema(
            status="not_ready",
            database="schema_outdated",
            message="データベースの更新が必要です。",
            action="apps/api で python -m alembic upgrade head を実行してください。",
        )
    return ReadinessSchema(
        status="not_ready",
        database="unavailable",
        message="データベースに接続できません。",
        action="PostgreSQLの起動状態とDATABASE_URLを確認してください。",
    )
