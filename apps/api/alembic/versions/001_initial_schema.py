"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "horses",
        sa.Column("ketto_num", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("sex", sa.String(2), nullable=True),
        sa.Column("birth_year", sa.Integer(), nullable=True),
    )

    op.create_table(
        "jockeys",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
    )

    op.create_table(
        "trainers",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
    )

    op.create_table(
        "races",
        sa.Column("race_key", sa.String(16), primary_key=True),
        sa.Column("race_date", sa.Date(), nullable=False),
        sa.Column("jyo_cd", sa.String(2), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("track_type", sa.String(10), nullable=False),
        sa.Column("field_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="entries"),
        sa.Column("track_condition", sa.String(10), nullable=True),
        sa.Column("weather", sa.String(10), nullable=True),
        sa.Column("grade", sa.String(20), nullable=True),
        sa.Column("race_class", sa.String(100), nullable=True),
        sa.Column("rpci_actual", sa.Float(), nullable=True),
        sa.Column("pci3_actual", sa.Float(), nullable=True),
    )
    op.create_index("ix_races_date_jyo", "races", ["race_date", "jyo_cd"])

    op.create_table(
        "race_entries",
        sa.Column("race_key", sa.String(16), sa.ForeignKey("races.race_key"), primary_key=True),
        sa.Column("horse_no", sa.Integer(), primary_key=True),
        sa.Column("frame_no", sa.Integer(), nullable=False),
        sa.Column("ketto_num", sa.String(10), sa.ForeignKey("horses.ketto_num"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("jockey_code", sa.String(8), sa.ForeignKey("jockeys.code"), nullable=False),
        sa.Column("trainer_code", sa.String(8), sa.ForeignKey("trainers.code"), nullable=False),
        sa.Column("finish_pos", sa.Integer(), nullable=True),
        sa.Column("race_time_s", sa.Float(), nullable=True),
        sa.Column("agari_3f_s", sa.Float(), nullable=True),
        sa.Column("corner_1", sa.Integer(), nullable=True),
        sa.Column("corner_2", sa.Integer(), nullable=True),
        sa.Column("corner_3", sa.Integer(), nullable=True),
        sa.Column("corner_4", sa.Integer(), nullable=True),
        sa.Column("pci_actual", sa.Float(), nullable=True),
        sa.Column("running_style", sa.String(10), nullable=True),
    )
    op.create_index("ix_race_entries_ketto_num", "race_entries", ["ketto_num"])

    op.create_table(
        "predicted_pace",
        sa.Column("race_key", sa.String(16), sa.ForeignKey("races.race_key"), primary_key=True),
        sa.Column("model_version", sa.String(20), primary_key=True),
        sa.Column("predicted_rpci", sa.Float(), nullable=False),
        sa.Column("pace_label", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("factors", JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "pace_fit",
        sa.Column("race_key", sa.String(16), sa.ForeignKey("races.race_key"), primary_key=True),
        sa.Column("horse_no", sa.Integer(), primary_key=True),
        sa.Column("model_version", sa.String(20), primary_key=True),
        sa.Column("pai", sa.Float(), nullable=False),
        sa.Column("fit_label", sa.String(10), nullable=False),
        sa.Column("reasons", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("pace_fit")
    op.drop_table("predicted_pace")
    op.drop_index("ix_race_entries_ketto_num", table_name="race_entries")
    op.drop_table("race_entries")
    op.drop_index("ix_races_date_jyo", table_name="races")
    op.drop_table("races")
    op.drop_table("trainers")
    op.drop_table("jockeys")
    op.drop_table("horses")
