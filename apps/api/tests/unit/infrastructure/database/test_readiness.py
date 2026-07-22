"""データベースreadiness検査の単体テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from pci.infrastructure.database.base import Base
from pci.infrastructure.database.readiness import check_database_readiness


def test_ready_when_all_mapped_columns_exist() -> None:
    session = MagicMock(spec=Session)
    inspector = MagicMock()
    inspector.get_table_names.return_value = [table.name for table in Base.metadata.sorted_tables]
    inspector.get_columns.side_effect = lambda table_name: [
        {"name": column.name} for column in Base.metadata.tables[table_name].columns
    ]

    with patch("pci.infrastructure.database.readiness.inspect", return_value=inspector):
        result = check_database_readiness(session)

    assert result.ready is True
    assert result.database == "ok"


def test_outdated_when_mapped_column_is_missing() -> None:
    session = MagicMock(spec=Session)
    inspector = MagicMock()
    inspector.get_table_names.return_value = [table.name for table in Base.metadata.sorted_tables]

    def columns_without_generated_at(table_name: str) -> list[dict[str, str]]:
        return [
            {"name": column.name}
            for column in Base.metadata.tables[table_name].columns
            if not (table_name == "predicted_pace" and column.name == "generated_at")
        ]

    inspector.get_columns.side_effect = columns_without_generated_at
    with patch("pci.infrastructure.database.readiness.inspect", return_value=inspector):
        result = check_database_readiness(session)

    assert result.ready is False
    assert result.database == "schema_outdated"


def test_unavailable_when_database_connection_fails() -> None:
    session = MagicMock(spec=Session)
    session.connection.side_effect = OperationalError("SELECT 1", {}, Exception("offline"))

    result = check_database_readiness(session)

    assert result.ready is False
    assert result.database == "unavailable"
