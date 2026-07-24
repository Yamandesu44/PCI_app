"""add race lap times for internal forecast features

Revision ID: 005
Revises: 004
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # RPCI v4候補の履歴入力。既存行はresults再同期で補完する。
    op.add_column("races", sa.Column("race_s3f", sa.Float(), nullable=True))
    op.add_column("races", sa.Column("race_l3f", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("races", "race_l3f")
    op.drop_column("races", "race_s3f")
