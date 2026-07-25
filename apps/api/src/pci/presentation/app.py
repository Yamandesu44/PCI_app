"""FastAPI アプリケーションファクトリ。"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from pci.application.errors import RaceNotConfirmedError
from pci.config.settings import get_settings
from pci.presentation.routers import health, ingest, races, status


def _has_valid_public_api_token(request: Request, expected_token: str) -> bool:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, credentials = authorization.partition(" ")
    return (
        separator == " "
        and scheme.lower() == "bearer"
        and hmac.compare_digest(credentials.encode(), expected_token.encode())
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="PCI App API",
        version="0.1.0",
        description="競馬展開予想 SaaS — 想定RPCI・PAI・展開シナリオを提供する REST API",
    )

    # MVP は個人利用。フロント（Vercel）からのアクセスを許可する。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _protect_public_api(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """設定時だけ公開参照APIをサーバー間トークンで保護する。"""
        expected_token = get_settings().public_api_token
        if (
            expected_token
            and request.url.path.startswith("/api/v1/")
            and not _has_valid_public_api_token(request, expected_token)
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API access token"},
                headers={
                    "Cache-Control": "no-store",
                    "WWW-Authenticate": "Bearer",
                },
            )
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        """use case の「見つからない」系 ValueError を 404 にマップする。"""
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RaceNotConfirmedError)
    async def _not_confirmed_handler(_request: Request, exc: RaceNotConfirmedError) -> JSONResponse:
        """確定前レースへの確定後分析要求を 409 Conflict にマップする。"""
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(health.router)
    app.include_router(races.router)
    app.include_router(ingest.router)
    app.include_router(status.router)
    return app


app = create_app()
