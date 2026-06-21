"""SQLAlchemy ORM モデル（core / mart 層）。

domain エンティティとは分離し、infrastructure 層の詳細として扱う（ADR-0001）。
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pci.infrastructure.database.base import Base


class HorseModel(Base):
    __tablename__ = "horses"

    ketto_num: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sex: Mapped[str | None] = mapped_column(String(2))
    birth_year: Mapped[int | None] = mapped_column(Integer)


class JockeyModel(Base):
    __tablename__ = "jockeys"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class TrainerModel(Base):
    __tablename__ = "trainers"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class RaceModel(Base):
    __tablename__ = "races"
    __table_args__ = (Index("ix_races_date_jyo", "race_date", "jyo_cd"),)

    race_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    race_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    jyo_cd: Mapped[str] = mapped_column(String(2), nullable=False)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    track_type: Mapped[str] = mapped_column(String(10), nullable=False)
    field_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="entries")
    track_condition: Mapped[str | None] = mapped_column(String(10))
    weather: Mapped[str | None] = mapped_column(String(10))
    grade: Mapped[str | None] = mapped_column(String(20))
    race_class: Mapped[str | None] = mapped_column(String(100))
    rpci_actual: Mapped[float | None] = mapped_column(Float)
    pci3_actual: Mapped[float | None] = mapped_column(Float)

    # 親子関係を明示し、flush 時に races → race_entries の INSERT 順序を保証する
    # （未設定だと UoW が FK 依存を解決できず FK 違反になる）。
    entries: Mapped[list[RaceEntryModel]] = relationship(back_populates="race")


class RaceEntryModel(Base):
    __tablename__ = "race_entries"
    __table_args__ = (Index("ix_race_entries_ketto_num", "ketto_num"),)

    race_key: Mapped[str] = mapped_column(
        String(16), ForeignKey("races.race_key"), primary_key=True
    )
    race: Mapped[RaceModel] = relationship(back_populates="entries")
    horse_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    frame_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ketto_num: Mapped[str] = mapped_column(
        String(10), ForeignKey("horses.ketto_num"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    jockey_code: Mapped[str] = mapped_column(String(8), ForeignKey("jockeys.code"), nullable=False)
    trainer_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("trainers.code"), nullable=False
    )
    # 確定後
    finish_pos: Mapped[int | None] = mapped_column(Integer)
    race_time_s: Mapped[float | None] = mapped_column(Float)
    agari_3f_s: Mapped[float | None] = mapped_column(Float)
    corner_1: Mapped[int | None] = mapped_column(Integer)
    corner_2: Mapped[int | None] = mapped_column(Integer)
    corner_3: Mapped[int | None] = mapped_column(Integer)
    corner_4: Mapped[int | None] = mapped_column(Integer)
    pci_actual: Mapped[float | None] = mapped_column(Float)
    running_style: Mapped[str | None] = mapped_column(String(10))


class PredictedPaceModel(Base):
    """mart 層: 想定 RPCI 予測結果。model_version で世代管理（ADR-0006）。"""

    __tablename__ = "predicted_pace"

    race_key: Mapped[str] = mapped_column(
        String(16), ForeignKey("races.race_key"), primary_key=True
    )
    model_version: Mapped[str] = mapped_column(String(20), primary_key=True)
    predicted_rpci: Mapped[float] = mapped_column(Float, nullable=False)
    pace_label: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class PaceFitModel(Base):
    """mart 層: PAI・展開合致判定。model_version で世代管理（ADR-0006）。"""

    __tablename__ = "pace_fit"

    race_key: Mapped[str] = mapped_column(
        String(16), ForeignKey("races.race_key"), primary_key=True
    )
    horse_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(20), primary_key=True)
    pai: Mapped[float] = mapped_column(Float, nullable=False)
    fit_label: Mapped[str] = mapped_column(String(10), nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
