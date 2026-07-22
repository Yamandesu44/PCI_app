"""APIが利用するデータベース構造のreadiness検査。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pci.infrastructure.database import models as _models  # noqa: F401
from pci.infrastructure.database.base import Base

DatabaseState = Literal["ok", "unavailable", "schema_outdated"]


@dataclass(frozen=True)
class DatabaseReadiness:
    ready: bool
    database: DatabaseState


def check_database_readiness(session: Session) -> DatabaseReadiness:
    """接続可否と、現在のORMが必要とするテーブル・列の存在を確認する。"""
    try:
        inspector = inspect(session.connection())
        actual_tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in actual_tables:
                return DatabaseReadiness(ready=False, database="schema_outdated")
            actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
            expected_columns = {column.name for column in table.columns}
            if not expected_columns.issubset(actual_columns):
                return DatabaseReadiness(ready=False, database="schema_outdated")
    except SQLAlchemyError:
        return DatabaseReadiness(ready=False, database="unavailable")
    return DatabaseReadiness(ready=True, database="ok")
