"""add popularity and prize_money to race_entries (Phase2 ability-v2)

Revision ID: 003
Revises: 002
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 能力指数 ability-v2 用の確定後カラム。既存行は NULL（再取込で埋まる）。
    op.add_column("race_entries", sa.Column("popularity", sa.Integer(), nullable=True))
    op.add_column("race_entries", sa.Column("prize_money", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("race_entries", "prize_money")
    op.drop_column("race_entries", "popularity")
