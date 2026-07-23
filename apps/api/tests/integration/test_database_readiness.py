"""マイグレーション済みPostgreSQLに対するreadiness統合テスト。"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy.orm import Session

from pci.infrastructure.database.readiness import check_database_readiness

pytestmark = pytest.mark.integration
_APP_LOGGER = logging.getLogger("pci.tests.database_readiness")


def test_migrated_database_is_ready(db_session: Session) -> None:
    result = check_database_readiness(db_session)

    assert result.ready is True
    assert result.database == "ok"


def test_migration_keeps_existing_application_loggers_enabled(db_session: Session) -> None:
    assert db_session.is_active
    assert _APP_LOGGER.disabled is False
