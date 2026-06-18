"""FastAPI 依存性注入（DI）。

リクエストごとに DB セッションを払い出し、Repository → UseCase を組み立てる。
予測戦略（RpciForecaster）は ADR-0005 に従い既定で rule-v1 を注入する。
Annotated 形式で定義し、ruff B008（デフォルト引数での関数呼び出し）を回避する。
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_query_use_cases import GetRaceDetailUseCase
from pci.config.settings import get_settings
from pci.domain.pace.mart_repository import MartRepository
from pci.domain.racing.repository import RaceRepository
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.repositories.mart_repository import SqlAlchemyMartRepository
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository


@lru_cache
def _session_maker() -> sessionmaker[Session]:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    return build_session_maker(engine)


def get_session() -> Iterator[Session]:
    session = _session_maker()()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def get_race_repository(session: SessionDep) -> RaceRepository:
    return SqlAlchemyRaceRepository(session)


RepositoryDep = Annotated[RaceRepository, Depends(get_race_repository)]


def get_mart_repository(session: SessionDep) -> MartRepository:
    return SqlAlchemyMartRepository(session)


MartRepositoryDep = Annotated[MartRepository, Depends(get_mart_repository)]


def get_forecast_use_case(repo: RepositoryDep, mart_repo: MartRepositoryDep) -> ForecastRaceUseCase:
    return ForecastRaceUseCase(repo, mart_repo=mart_repo)


def get_race_detail_use_case(repo: RepositoryDep) -> GetRaceDetailUseCase:
    return GetRaceDetailUseCase(repo)


ForecastUseCaseDep = Annotated[ForecastRaceUseCase, Depends(get_forecast_use_case)]
RaceDetailUseCaseDep = Annotated[GetRaceDetailUseCase, Depends(get_race_detail_use_case)]
