"""MartRepository の SQLAlchemy 実装（mart 層: predicted_pace / pace_fit）。

ADR-0006 の mart 層方針に従い、model_version をキーに upsert することで
再計算時も安全に上書きできる（session.merge() による primary key ベースの upsert）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.mart_repository import PredictedPaceRecord
from pci.domain.pace.rpci_forecast import RpciForecast
from pci.infrastructure.database.models import PaceFitModel, PredictedPaceModel


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
            )
        )

    def find_predicted_pace(self, race_key: str) -> PredictedPaceRecord | None:
        """回顧比較用に想定RPCIを1件取得する。

        同一レースに複数 model_version が存在する場合の優先順位は定めていない
        （通常運用では1レース1 model_version のため実務上問題にならない）。
        """
        row = self._s.execute(
            select(PredictedPaceModel).where(PredictedPaceModel.race_key == race_key)
        ).scalars().first()
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
            )
        )
