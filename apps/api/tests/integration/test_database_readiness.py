"""マイグレーション済みPostgreSQLに対するreadiness統合テスト。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pci.infrastructure.database.readiness import check_database_readiness


def test_migrated_database_is_ready(db_session: Session) -> None:
    result = check_database_readiness(db_session)

    assert result.ready is True
    assert result.database == "ok"
