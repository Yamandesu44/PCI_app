"""APIが利用するデータベース構造のreadiness検査。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import String, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.schema import Column

from pci.infrastructure.database import models as _models  # noqa: F401
from pci.infrastructure.database.base import Base

DatabaseState = Literal["ok", "unavailable", "schema_outdated"]


@dataclass(frozen=True)
class DatabaseReadiness:
    ready: bool
    database: DatabaseState


def check_database_readiness(session: Session) -> DatabaseReadiness:
    """接続可否と、現在のORMが必要とするテーブル・列定義を確認する。"""
    try:
        inspector = inspect(session.connection())
        actual_tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in actual_tables:
                return DatabaseReadiness(ready=False, database="schema_outdated")
            actual_columns = {
                column["name"]: column for column in inspector.get_columns(table.name)
            }
            for expected_column in table.columns:
                actual_column = actual_columns.get(expected_column.name)
                if actual_column is None or not _is_compatible_column(
                    expected_column, actual_column
                ):
                    return DatabaseReadiness(ready=False, database="schema_outdated")
    except SQLAlchemyError:
        return DatabaseReadiness(ready=False, database="unavailable")
    return DatabaseReadiness(ready=True, database="ok")


def _is_compatible_column(
    expected: Column[Any],
    actual: Mapping[str, Any],
) -> bool:
    """長さ付き文字列について、実DBがORMの必要長を満たすか確認する。"""

    if not isinstance(expected.type, String) or expected.type.length is None:
        return True
    actual_length = getattr(actual.get("type"), "length", None)
    # TEXTなど長さ無制限の型は不足扱いにしない。
    return actual_length is None or actual_length >= expected.type.length
