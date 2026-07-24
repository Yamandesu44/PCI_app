"""expand mart model version columns

Revision ID: 006
Revises: 005
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 特徴量を含むモデル世代名を省略せず保存できる長さへ広げる。
    op.alter_column(
        "predicted_pace",
        "model_version",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "pace_fit",
        "model_version",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "pace_fit",
        "model_version",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "predicted_pace",
        "model_version",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
