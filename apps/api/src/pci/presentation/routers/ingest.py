"""内部 Ingest API — ingestion-worker（Windows）からのデータ投入専用エンドポイント。

ADR-0002: Bearer トークン（X-Ingest-Token ヘッダー）で保護する内部 API。
外部公開不可。CORS は適用されない（CORSMiddleware は GET のみ許可）。
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from pci.application.dto import EntryInput, RaceInfo, ResultInput
from pci.application.ingest_use_cases import (
    HorseInput,
    JockeyInput,
    SaveMasterDataUseCase,
    TrainerInput,
)
from pci.application.race_use_cases import RecordRaceResultUseCase, RegisterRaceEntriesUseCase
from pci.config.settings import get_settings
from pci.domain.shared.race_key import RaceKey
from pci.presentation.dependencies import (
    PrecomputeForecastsUseCaseDep,
    RaceCompletenessRepositoryDep,
    RepositoryDep,
    SessionDep,
)

router = APIRouter(prefix="/internal/ingest", tags=["ingest"])


# ----- 認証 -----

def _verify_token(x_ingest_token: Annotated[str | None, Header()] = None) -> None:
    settings = get_settings()
    if settings.ingest_token is None:
        return  # 未設定時は開発モード（認証スキップ）
    if x_ingest_token != settings.ingest_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Ingest-Token",
        )


AuthDep = Annotated[None, Depends(_verify_token)]


@router.get("/incomplete-race-keys", response_model=list[str])
def get_incomplete_race_keys(
    repo: RaceCompletenessRepositoryDep,
    _auth: AuthDep,
) -> list[str]:
    """再同期対象となる成績未取り込みのJRA平地レースキーを全件返す。"""
    races = repo.find_incomplete_past_races(datetime.date.today(), limit=10_000)
    return [str(race.race_key) for race in races]


# ----- リクエストスキーマ -----

class HorseBody(BaseModel):
    ketto_num: str = Field(min_length=10, max_length=10)
    name: str
    sex: str | None = None
    birth_year: int | None = None


class JockeyBody(BaseModel):
    code: str
    name: str


class TrainerBody(BaseModel):
    code: str
    name: str


class EntryItem(BaseModel):
    horse_no: int
    frame_no: int
    ketto_num: str = Field(min_length=10, max_length=10)
    weight: float
    jockey_code: str
    trainer_code: str


class EntriesBody(BaseModel):
    race_key: str = Field(pattern=r"^\d{16}$")
    race_date: datetime.date
    jyo_cd: str = Field(min_length=2, max_length=2)
    distance_m: int = Field(gt=0)
    track_type: str
    field_size: int = Field(gt=0)
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_class: str | None = None
    entries: list[EntryItem]


class ResultItem(BaseModel):
    horse_no: int
    finish_pos: int = Field(ge=1)
    race_time_s: float = Field(gt=0)
    agari_3f_s: float = Field(gt=0)
    corner_1: int | None = None
    corner_2: int | None = None
    corner_3: int | None = None
    corner_4: int | None = None
    body_weight: float | None = Field(default=None, ge=300, le=700)
    popularity: int | None = None  # 単勝人気順（能力指数の補助成分）
    prize_money: int | None = None  # 獲得本賞金（円・能力指数の補助成分）


class ResultBody(BaseModel):
    race_key: str = Field(pattern=r"^\d{16}$")
    track_condition: str | None = None
    weather: str | None = None
    grade: str | None = None
    race_s3f: float | None = None  # RA HaronTimeS3（前半3ハロン秒）。TARGET 準拠 RPCI に使用
    race_l3f: float | None = None  # RA HaronTimeL3（後半3ハロン秒）。TARGET 準拠 RPCI に使用
    results: list[ResultItem]


# ----- レスポンス -----

class IngestResponse(BaseModel):
    accepted: int
    message: str = "ok"


class ResultResponse(BaseModel):
    race_key: str
    rpci: float | None
    pci3: float | None
    formula_version: str
    entry_pcis: dict[int, float] = {}


class IngestLogBody(BaseModel):
    """バッチ実行ログの記録リクエスト。"""

    batch_date: datetime.date
    step: str
    mode: str
    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None
    status: str | None = None  # 'running' | 'ok' | 'error'
    error_msg: str | None = None


class IngestLogResponse(BaseModel):
    id: int


class ForecastPrecomputeBody(BaseModel):
    date_from: datetime.date
    date_to: datetime.date


class ForecastPrecomputeResponse(BaseModel):
    scanned: int
    generated: int
    skipped: int


# ----- エンドポイント -----

@router.post("/horses", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_horses(
    body: list[HorseBody],
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestResponse:
    """馬マスタ一括 Upsert。"""
    uc = SaveMasterDataUseCase(repo)
    n = uc.save_horses([HorseInput(**h.model_dump()) for h in body])
    session.commit()
    return IngestResponse(accepted=n)


@router.post("/jockeys", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_jockeys(
    body: list[JockeyBody],
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestResponse:
    """騎手マスタ一括 Upsert。"""
    uc = SaveMasterDataUseCase(repo)
    n = uc.save_jockeys([JockeyInput(**j.model_dump()) for j in body])
    session.commit()
    return IngestResponse(accepted=n)


@router.post("/trainers", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_trainers(
    body: list[TrainerBody],
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestResponse:
    """調教師マスタ一括 Upsert。"""
    uc = SaveMasterDataUseCase(repo)
    n = uc.save_trainers([TrainerInput(**t.model_dump()) for t in body])
    session.commit()
    return IngestResponse(accepted=n)


@router.post("/entries", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_entries(
    body: EntriesBody,
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestResponse:
    """出走表登録（RegisterRaceEntriesUseCase を呼び出す）。"""
    uc = RegisterRaceEntriesUseCase(repo)
    race_info = RaceInfo(
        race_key=body.race_key,
        race_date=body.race_date,
        jyo_cd=body.jyo_cd,
        distance_m=body.distance_m,
        track_type=body.track_type,
        field_size=body.field_size,
        track_condition=body.track_condition,
        weather=body.weather,
        grade=body.grade,
        race_class=body.race_class,
    )
    entries = [
        EntryInput(
            horse_no=e.horse_no,
            frame_no=e.frame_no,
            ketto_num=e.ketto_num,
            weight=e.weight,
            jockey_code=e.jockey_code,
            trainer_code=e.trainer_code,
        )
        for e in body.entries
    ]
    accepted = uc.execute(race_info, entries)
    session.commit()
    return IngestResponse(accepted=accepted)


@router.post("/results", response_model=ResultResponse, status_code=status.HTTP_200_OK)
def ingest_results(
    body: ResultBody,
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> ResultResponse:
    """確定成績登録（RecordRaceResultUseCase を呼び出す）。"""
    uc = RecordRaceResultUseCase(repo)
    results = [
        ResultInput(
            horse_no=r.horse_no,
            finish_pos=r.finish_pos,
            race_time_s=r.race_time_s,
            agari_3f_s=r.agari_3f_s,
            corner_1=r.corner_1,
            corner_2=r.corner_2,
            corner_3=r.corner_3,
            corner_4=r.corner_4,
            body_weight=r.body_weight,
            popularity=r.popularity,
            prize_money=r.prize_money,
        )
        for r in body.results
    ]
    out = uc.execute(
        body.race_key,
        results,
        track_condition=body.track_condition,
        weather=body.weather,
        grade=body.grade,
        race_s3f=body.race_s3f,
        race_l3f=body.race_l3f,
    )
    session.commit()
    return ResultResponse(
        race_key=out.race_key,
        rpci=out.rpci,
        pci3=out.pci3,
        formula_version=out.formula_version,
        entry_pcis=out.entry_pcis,
    )


@router.post("/log", response_model=IngestLogResponse, status_code=status.HTTP_200_OK)
def write_ingest_log(
    body: IngestLogBody,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestLogResponse:
    """バッチ取り込みの実行ログを記録する（監査証跡・再実行判定用）。"""
    from pci.infrastructure.database.models import IngestLogModel

    log = IngestLogModel(
        batch_date=body.batch_date,
        step=body.step,
        mode=body.mode,
        started_at=body.started_at,
        finished_at=body.finished_at,
        status=body.status,
        error_msg=body.error_msg,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return IngestLogResponse(id=log.id)


@router.post(
    "/forecasts/precompute",
    response_model=ForecastPrecomputeResponse,
    status_code=status.HTTP_200_OK,
)
def precompute_forecasts(
    body: ForecastPrecomputeBody,
    use_case: PrecomputeForecastsUseCaseDep,
    session: SessionDep,
    _auth: AuthDep,
) -> ForecastPrecomputeResponse:
    """今後の出走前レースの予想martを、画面表示より先に生成する。"""
    if body.date_from > body.date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from は date_to 以前にしてください。",
        )
    if (body.date_to - body.date_from).days > 31:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="事前生成は32日以内の範囲を指定してください。",
        )

    output = use_case.execute(body.date_from, body.date_to)
    session.commit()
    return ForecastPrecomputeResponse(
        scanned=output.scanned,
        generated=output.generated,
        skipped=output.skipped,
    )


@router.delete("/races/{race_key}", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def delete_ingested_race(
    race_key: str,
    repo: RepositoryDep,
    session: SessionDep,
    _auth: AuthDep,
) -> IngestResponse:
    """取り込み対象外になったレースを、関連する予想データごと削除する。"""
    try:
        key = RaceKey(race_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    deleted = repo.delete_race(key)
    session.commit()
    return IngestResponse(accepted=1 if deleted else 0)
