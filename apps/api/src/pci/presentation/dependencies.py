"""FastAPI 依存性注入（DI）。

リクエストごとに DB セッションを払い出し、Repository → UseCase を組み立てる。
予測戦略（RpciForecaster）は ADR-0005 に従いモデルファイルの有無で自動選択する:
  apps/api/models/rpci_lgbm_v1.txt が存在 → LightGBMRpciForecaster (lgbm-v1)
  存在しない                             → RuleBasedRpciForecaster (rule-v4, フォールバック)
Annotated 形式で定義し、ruff B008（デフォルト引数での関数呼び出し）を回避する。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.ingest_status_use_cases import GetIngestStatusUseCase
from pci.application.race_query_use_cases import (
    GetPaceAnalysisUseCase,
    GetRaceDetailUseCase,
    ListRaceDatesUseCase,
    ListRacesUseCase,
)
from pci.config.settings import get_settings
from pci.domain.ops.ingest_log import IngestLogRepository
from pci.domain.pace.commentary import CommentGenerator, RuleBasedCommentGenerator
from pci.domain.pace.mart_repository import MartRepository
from pci.domain.pace.rpci_forecast import RpciForecaster
from pci.domain.racing.repository import RaceCompletenessRepository, RaceRepository
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.pace.lgbm_forecaster import load_best_forecaster
from pci.infrastructure.repositories.ingest_log_repository import SqlAlchemyIngestLogRepository
from pci.infrastructure.repositories.mart_repository import SqlAlchemyMartRepository
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository

_logger = logging.getLogger(__name__)


@lru_cache
def _get_forecaster() -> RpciForecaster:
    """モデルファイルの有無に応じて予測器を選択する（lru_cache でプロセス起動時に1回評価）。"""
    forecaster = load_best_forecaster()
    _logger.info("予測器: %s", forecaster.__class__.__name__)
    return forecaster


@lru_cache
def _get_comment_generator() -> CommentGenerator:
    """明示的にGeminiを選択し、APIキーもある場合だけ外部API生成器を返す。"""
    settings = get_settings()
    if settings.comment_generator_mode == "gemini" and settings.gemini_api_key:
        try:
            from pci.infrastructure.llm_comment_generator import GeminiCommentGenerator

            return GeminiCommentGenerator(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "GeminiCommentGenerator 初期化失敗 → rule-based にフォールバック: %s", exc
            )
    elif settings.comment_generator_mode == "gemini":
        _logger.warning(
            "COMMENT_GENERATOR_MODE=gemini ですがGEMINI_API_KEYが未設定のため、"
            "rule-basedを使用します"
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


def get_race_completeness_repository(repo: RepositoryDep) -> RaceCompletenessRepository:
    return cast(RaceCompletenessRepository, repo)


RaceCompletenessRepositoryDep = Annotated[
    RaceCompletenessRepository, Depends(get_race_completeness_repository)
]


def get_mart_repository(session: SessionDep) -> MartRepository:
    return SqlAlchemyMartRepository(session)


MartRepositoryDep = Annotated[MartRepository, Depends(get_mart_repository)]


def get_forecast_use_case(repo: RepositoryDep, mart_repo: MartRepositoryDep) -> ForecastRaceUseCase:
    return ForecastRaceUseCase(
        repo,
        forecaster=_get_forecaster(),
        mart_repo=mart_repo,
        comment_generator=_get_comment_generator(),
    )


def get_list_races_use_case(repo: RepositoryDep) -> ListRacesUseCase:
    return ListRacesUseCase(repo)


def get_list_race_dates_use_case(repo: RepositoryDep) -> ListRaceDatesUseCase:
    return ListRaceDatesUseCase(repo)


def get_race_detail_use_case(repo: RepositoryDep) -> GetRaceDetailUseCase:
    return GetRaceDetailUseCase(repo)


def get_pace_analysis_use_case(
    repo: RepositoryDep, mart_repo: MartRepositoryDep
) -> GetPaceAnalysisUseCase:
    return GetPaceAnalysisUseCase(
        repo, comment_generator=_get_comment_generator(), mart_repo=mart_repo
    )


def get_ingest_log_repository(session: SessionDep) -> IngestLogRepository:
    return SqlAlchemyIngestLogRepository(session)


IngestLogRepositoryDep = Annotated[IngestLogRepository, Depends(get_ingest_log_repository)]


def get_ingest_status_use_case(
    repo: IngestLogRepositoryDep,
    race_repo: RaceCompletenessRepositoryDep,
) -> GetIngestStatusUseCase:
    return GetIngestStatusUseCase(repo, race_repo)


ForecastUseCaseDep = Annotated[ForecastRaceUseCase, Depends(get_forecast_use_case)]
RaceDetailUseCaseDep = Annotated[GetRaceDetailUseCase, Depends(get_race_detail_use_case)]
PaceAnalysisUseCaseDep = Annotated[GetPaceAnalysisUseCase, Depends(get_pace_analysis_use_case)]
ListRacesUseCaseDep = Annotated[ListRacesUseCase, Depends(get_list_races_use_case)]
ListRaceDatesUseCaseDep = Annotated[ListRaceDatesUseCase, Depends(get_list_race_dates_use_case)]
IngestStatusUseCaseDep = Annotated[GetIngestStatusUseCase, Depends(get_ingest_status_use_case)]
