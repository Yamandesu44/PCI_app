"""MartRepository の SQLAlchemy 実装（mart 層: predicted_pace / pace_fit）。

ADR-0006 の mart 層方針に従い、model_version をキーに upsert することで
再計算時も安全に上書きできる（session.merge() による primary key ベースの upsert）。
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.mart_repository import PredictedPaceRecord, RaceBoardForecastRecord
from pci.domain.pace.rpci_forecast import RpciForecast
from pci.infrastructure.database.models import (
    HorseModel,
    PaceFitModel,
    PredictedPaceModel,
    RaceEntryModel,
)


class SqlAlchemyMartRepository:
    """SQLAlchemy を使った MartRepository 実装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def save_predicted_pace(self, race_key: str, forecast: RpciForecast) -> None:
        factors = [
            {"code": r.code, "description": r.description, "contribution": r.contribution}
            for r in forecast.reasons
        ]
        self._s.merge(
            PredictedPaceModel(
                race_key=race_key,
                model_version=forecast.model_version,
                predicted_rpci=forecast.value,
                pace_label=str(forecast.label),
                confidence=forecast.confidence,
                factors=factors,
                generated_at=datetime.datetime.now(datetime.UTC),
            )
        )

    def find_predicted_pace(self, race_key: str) -> PredictedPaceRecord | None:
        """回顧比較用に想定RPCIを1件取得する。

        同一レースに複数 model_version が存在する場合は、最後に生成された世代を返す。
        """
        row = (
            self._s.execute(
                select(PredictedPaceModel)
                .where(PredictedPaceModel.race_key == race_key)
                .order_by(
                    PredictedPaceModel.generated_at.desc(),
                    PredictedPaceModel.model_version.desc(),
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        return PredictedPaceRecord(
            race_key=row.race_key,
            model_version=row.model_version,
            predicted_rpci=row.predicted_rpci,
            pace_label=row.pace_label,
            confidence=row.confidence,
        )

    def save_pace_fit(self, race_key: str, horse_no: int, result: PaiResult) -> None:
        reasons = [
            {"code": r.code, "description": r.description, "contribution": r.contribution}
            for r in result.reasons
        ]
        self._s.merge(
            PaceFitModel(
                race_key=race_key,
                horse_no=horse_no,
                model_version=result.model_version,
                pai=result.pai,
                fit_label=str(result.fit_label),
                reasons=reasons,
                generated_at=datetime.datetime.now(datetime.UTC),
            )
        )

    def find_race_board_forecasts(self, race_keys: list[str]) -> dict[str, RaceBoardForecastRecord]:
        """一覧対象の保存済み予想と最上位適性馬を一括取得する。"""
        if not race_keys:
            return {}

        pace_rows = self._s.execute(
            select(PredictedPaceModel)
            .where(PredictedPaceModel.race_key.in_(race_keys))
            .order_by(
                PredictedPaceModel.race_key,
                PredictedPaceModel.generated_at.desc(),
                PredictedPaceModel.model_version.desc(),
            )
        ).scalars()
        pace_by_race: dict[str, PredictedPaceModel] = {}
        for row in pace_rows:
            pace_by_race.setdefault(row.race_key, row)

        fit_rows = self._s.execute(
            select(PaceFitModel, HorseModel.name)
            .join(
                RaceEntryModel,
                (RaceEntryModel.race_key == PaceFitModel.race_key)
                & (RaceEntryModel.horse_no == PaceFitModel.horse_no),
            )
            .outerjoin(HorseModel, HorseModel.ketto_num == RaceEntryModel.ketto_num)
            .where(PaceFitModel.race_key.in_(race_keys))
        )
        fits_by_race_and_version: dict[str, dict[str, list[tuple[PaceFitModel, str | None]]]] = {}
        for fit, horse_name in fit_rows:
            versions = fits_by_race_and_version.setdefault(fit.race_key, {})
            versions.setdefault(fit.model_version, []).append((fit, horse_name))

        top_fit_by_race: dict[str, tuple[PaceFitModel, str | None]] = {}
        for race_key, versions in fits_by_race_and_version.items():
            _latest_version, latest_rows = max(
                versions.items(),
                key=lambda item: (
                    max(row.generated_at for row, _name in item[1]),
                    item[0],
                ),
            )
            top_fit_by_race[race_key] = max(latest_rows, key=lambda item: item[0].pai)

        result: dict[str, RaceBoardForecastRecord] = {}
        for race_key, pace in pace_by_race.items():
            top = top_fit_by_race.get(race_key)
            if top is None:
                continue
            fit, horse_name = top
            result[race_key] = RaceBoardForecastRecord(
                race_key=race_key,
                pace_label=pace.pace_label,
                confidence=pace.confidence,
                top_horse_no=fit.horse_no,
                top_horse_name=horse_name,
                top_pai=fit.pai,
                top_fit_label=fit.fit_label,
            )
        return result
