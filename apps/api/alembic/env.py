from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import pci.infrastructure.database.models  # noqa: F401 – モデル登録
from pci.infrastructure.database.base import Base
from pci.infrastructure.database.session import prepare_connection

config = context.config

if config.config_file_name is not None:
    # テストや管理CLIから同一プロセスで実行しても、既存のアプリロガーを無効化しない。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("接続先が未設定です。DATABASE_URL を設定してください。")

    prepared_url, connect_args = prepare_connection(url)
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
