"""FastAPI 依存性注入（DI）。

リクエストごとに DB セッションを払い出し、Repository → UseCase を組み立てる。
予測戦略（RpciForecaster）は ADR-0005 に従い既定で rule-v2 を注入する。
Annotated 形式で定義し、ruff B008（デフォルト引数での関数呼び出し）を回避する。
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_query_use_cases import (
    GetPaceAnalysisUseCase,
    GetRaceDetailUseCase,
    ListRaceDatesUseCase,
    ListRacesUseCase,
)
from pci.config.settings import get_settings
from pci.domain.pace.commentary import CommentGenerator, RuleBasedCommentGenerator
from pci.domain.pace.mart_repository import MartRepository
from pci.domain.racing.repository import RaceRepository
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.repositories.mart_repository import SqlAlchemyMartRepository
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository


@lru_cache
def _get_comment_generator() -> CommentGenerator:
    """GEMINI_API_KEY が設定されていれば Gemini 、なければルールベースを返す。"""
    settings = get_settings()
    if settings.gemini_api_key:
        try:
            from pci.infrastructure.llm_comment_generator import GeminiCommentGenerator

            return GeminiCommentGenerator(api_key=settings.gemini_api_key)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "GeminiCommentGenerator 初期化失敗 → rule-based にフォールバック: %s", exc
            )
    return RuleBasedCommentGenerator()


@lru_cache
def _session_maker() -> sessionmaker[Session]:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    return build_session_maker(engine)


def get_session() -> Iterator[Session]:
    session = _session_maker()()
    try:
        yield session
    except Exception:
        # 失敗したトランザクションを巻き戻し、コネクションをクリーンにプールへ返す。
        # これを怠ると後続リクエストが壊れたセッションを掴み接続リセットになり得る。
        session.rollback()
        raise
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
    return ForecastRaceUseCase(
        repo, mart_repo=mart_repo, comment_generator=_get_comment_generator()
    )


def get_list_races_use_case(repo: RepositoryDep) -> ListRacesUseCase:
    return ListRacesUseCase(repo)


def get_list_race_dates_use_case(repo: RepositoryDep) -> ListRaceDatesUseCase:
    return ListRaceDatesUseCase(repo)


def get_race_detail_use_case(repo: RepositoryDep) -> GetRaceDetailUseCase:
    return GetRaceDetailUseCase(repo)


def get_pace_analysis_use_case(repo: RepositoryDep) -> GetPaceAnalysisUseCase:
    return GetPaceAnalysisUseCase(repo, comment_generator=_get_comment_generator())


ForecastUseCaseDep = Annotated[ForecastRaceUseCase, Depends(get_forecast_use_case)]
RaceDetailUseCaseDep = Annotated[GetRaceDetailUseCase, Depends(get_race_detail_use_case)]
PaceAnalysisUseCaseDep = Annotated[GetPaceAnalysisUseCase, Depends(get_pace_analysis_use_case)]
ListRacesUseCaseDep = Annotated[ListRacesUseCase, Depends(get_list_races_use_case)]
ListRaceDatesUseCaseDep = Annotated[ListRaceDatesUseCase, Depends(get_list_race_dates_use_case)]
