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
from pci.presentation.dependencies import RepositoryDep, SessionDep

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


class ResultBody(BaseModel):
    race_key: str = Field(pattern=r"^\d{16}$")
    track_condition: str | None = None
    weather: str | None = None
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
    uc.execute(race_info, entries)
    session.commit()
    return IngestResponse(accepted=len(entries))


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
        )
        for r in body.results
    ]
    out = uc.execute(
        body.race_key,
        results,
        track_condition=body.track_condition,
        weather=body.weather,
    )
    session.commit()
    return ResultResponse(
        race_key=out.race_key,
        rpci=out.rpci,
        pci3=out.pci3,
        formula_version=out.formula_version,
        entry_pcis=out.entry_pcis,
    )
