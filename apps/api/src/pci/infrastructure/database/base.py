from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy ORM の基底クラス。全モデルはこれを継承する。"""
