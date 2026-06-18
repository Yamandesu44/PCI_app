from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def build_session_maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, autocommit=False, autoflush=False)
