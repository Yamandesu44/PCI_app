"""鮮度確認スクリプトが読むキーが、APIの返す形と合っているか。

このスクリプトの存在意義は「何が失敗したか」を出すこと。キー名を間違えると
**例外にならず、黙って空を出す**。実際 `error_summary` を `error_msg` と書いており、
失敗の内容が一切表示されないまま「3件」とだけ報告していた。

スクリプトは依存を入れずに動かすため `pci` を import しない。その代わりに、
読んでいるキーをソースから拾い、スキーマの項目と突き合わせる。
"""

from __future__ import annotations

import re
from pathlib import Path

from pci.presentation.schemas import IngestFailureSchema, IngestStatusSchema

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_ingest_freshness.py"


def _keys_read_from(variable: str) -> set[str]:
    """`<variable>.get("キー"` の形で読んでいるキーを集める。"""
    source = _SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(rf"{variable}\.get\(\s*[\"']([^\"']+)[\"']", source))


class TestKeysMatchTheSchema:
    def test_status_keys_exist(self) -> None:
        keys = _keys_read_from("status")

        assert keys, "status からキーを読んでいないはずがない（正規表現の破損を疑う）"
        assert keys <= set(IngestStatusSchema.model_fields)

    def test_failure_keys_exist(self) -> None:
        keys = _keys_read_from("failure")

        assert keys, "failure からキーを読んでいないはずがない（正規表現の破損を疑う）"
        assert keys <= set(IngestFailureSchema.model_fields)

    def test_the_error_text_is_actually_read(self) -> None:
        """失敗の中身を出していること。件数だけでは何も分からない。"""
        assert "error_summary" in _keys_read_from("failure")
