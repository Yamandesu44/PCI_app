"""add ingest_log table

Revision ID: 002
Revises: 001
Create Date: 2026-06-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("batch_date", sa.Date(), nullable=False),
        sa.Column("step", sa.String(30), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(10), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
    )
    op.create_index("ix_ingest_log_batch_date", "ingest_log", ["batch_date"])


def downgrade() -> None:
    op.drop_index("ix_ingest_log_batch_date", table_name="ingest_log")
    op.drop_table("ingest_log")
