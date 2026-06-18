"""OpenAPI スキーマを packages/api-client/openapi.json へエクスポートする。

型共有フロー（設計書 04 §4）の起点:
    FastAPI → openapi.json → packages/api-client（openapi-typescript）→ apps/web

決定的な出力（キーソート・インデント2）にすることで、差分を最小化し
契約テスト（test_openapi_snapshot.py）でのドリフト検知を安定させる。

使い方:
    cd apps/api && python scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pci.presentation.app import create_app

# apps/api/scripts/export_openapi.py → リポジトリルートは parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_OUTPUT_PATH = _REPO_ROOT / "packages" / "api-client" / "openapi.json"


def render_openapi() -> str:
    """現在の FastAPI アプリから決定的な OpenAPI JSON 文字列を生成する。"""
    spec = create_app().openapi()
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(render_openapi(), encoding="utf-8")
    print(f"wrote {_OUTPUT_PATH.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
