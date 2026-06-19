"""testcontainers-postgres を使った統合テスト共通フィクスチャ。"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]


@pytest.fixture(scope="session")
def pg_container() -> PostgresContainer:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(pg_container: PostgresContainer):  # type: ignore[no-untyped-def]
    url = pg_container.get_connection_url().replace("psycopg2", "psycopg")
    engine = create_engine(url)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):  # type: ignore[no-untyped-def]
    """各テストはロールバックで隔離。"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
