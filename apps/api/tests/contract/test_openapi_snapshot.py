"""OpenAPI スナップショット（ドリフト検知）契約テスト。

packages/api-client/openapi.json はフロント型生成の入力（設計書 04 §4/§5）。
コミット済みスペックが現在の FastAPI アプリと一致することを CI で保証し、
破壊的変更を可視化する。失敗時は `python scripts/export_openapi.py` で更新する。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import render_openapi

_COMMITTED_SPEC = Path(__file__).resolve().parents[4] / "packages" / "api-client" / "openapi.json"


def test_committed_openapi_is_in_sync() -> None:
    assert _COMMITTED_SPEC.exists(), (
        "packages/api-client/openapi.json が存在しません。"
        " `cd apps/api && python scripts/export_openapi.py` を実行してください。"
    )
    committed = json.loads(_COMMITTED_SPEC.read_text(encoding="utf-8"))
    current = json.loads(render_openapi())
    assert committed == current, (
        "OpenAPI スペックがコードと乖離しています。"
        " `cd apps/api && python scripts/export_openapi.py` で再生成してください。"
    )


def test_committed_openapi_exposes_core_endpoints() -> None:
    committed = json.loads(_COMMITTED_SPEC.read_text(encoding="utf-8"))
    paths = committed["paths"]
    assert "/api/v1/races/{race_key}/forecast" in paths
    assert "/api/v1/races/{race_key}" in paths
    assert "/health" in paths
