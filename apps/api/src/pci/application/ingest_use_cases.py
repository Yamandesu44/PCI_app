"""取り込み（Ingest）ユースケース。ingestion-worker から呼ばれる内部 API 向け。"""

from __future__ import annotations

from dataclasses import dataclass

from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.repository import RaceRepository


@dataclass(frozen=True)
class HorseInput:
    ketto_num: str
    name: str
    sex: str | None = None
    birth_year: int | None = None


@dataclass(frozen=True)
class JockeyInput:
    code: str
    name: str


@dataclass(frozen=True)
class TrainerInput:
    code: str
    name: str


class SaveMasterDataUseCase:
    """馬・騎手・調教師マスタの一括 Upsert（ingestion-worker → API の内部処理）。"""

    def __init__(self, repo: RaceRepository) -> None:
        self._repo = repo

    def save_horses(self, inputs: list[HorseInput]) -> int:
        for h in inputs:
            self._repo.save_horse(
                Horse(
                    ketto_num=h.ketto_num,
                    name=h.name,
                    sex=h.sex,
                    birth_year=h.birth_year,
                )
            )
        return len(inputs)

    def save_jockeys(self, inputs: list[JockeyInput]) -> int:
        for j in inputs:
            self._repo.save_jockey(Jockey(code=j.code, name=j.name))
        return len(inputs)

    def save_trainers(self, inputs: list[TrainerInput]) -> int:
        for t in inputs:
            self._repo.save_trainer(Trainer(code=t.code, name=t.name))
        return len(inputs)
