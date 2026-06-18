"""FastAPI アプリケーションファクトリ。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pci.presentation.routers import health, races


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

    @app.exception_handler(ValueError)
    async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        """use case の「見つからない」系 ValueError を 404 にマップする。"""
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    app.include_router(health.router)
    app.include_router(races.router)
    return app


app = create_app()
