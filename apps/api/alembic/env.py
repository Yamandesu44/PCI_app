from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import pci.infrastructure.database.models  # noqa: F401 – モデル登録
from pci.infrastructure.database.base import Base
from pci.infrastructure.database.session import prepare_connection, resolve_migration_url

config = context.config

if config.config_file_name is not None:
    # テストや管理CLIから同一プロセスで実行しても、既存のアプリロガーを無効化しない。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """接続先の決定は `resolve_migration_url` に委ねる（そちらでテストしている）。"""
    return resolve_migration_url(config.get_main_option("sqlalchemy.url", ""))


def run_migrations_offline() -> None:
    url, _ = prepare_connection(_database_url())
    context.configure(
        # パスワードを伏せない形で渡す。str(URL) は伏字になり接続できない。
        url=url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # アプリと同じ経路で接続文字列を整える。ここで独自にエンジンを組むと、
    # マネージドDBの `sslmode` が pg8000 へそのまま渡り、
    # 「アプリは繋がるのにマイグレーションだけ落ちる」状態になる。
    prepared_url, connect_args = prepare_connection(_database_url())
    # マイグレーションは一度きりなのでプールを持たない。
    connectable = create_engine(prepared_url, poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
