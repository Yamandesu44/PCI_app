"""mart 層 Repository Protocol（ADR-0006）。

predicted_pace / pace_fit の読み書きを担う戦略インターフェース。
実装は infrastructure 層（SqlAlchemyMartRepository）。
アプリケーション層はこの Protocol のみ参照し、SQLAlchemy 詳細を知らない。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Protocol

from pci.domain.pace.adaptability import PaiResult
from pci.domain.pace.rpci_forecast import RpciForecast


@dataclass(frozen=True)
class PredictedPaceRecord:
    """mart 層から読み出した想定RPCI（確定後の回顧・答え合わせ用）。"""

    race_key: str
    model_version: str
    predicted_rpci: float
    pace_label: str
    confidence: float


@dataclass(frozen=True)
class RaceBoardForecastRecord:
    """レース一覧向けに絞った保存済み予想の読取モデル。"""

    race_key: str
    pace_label: str
    confidence: float
    top_horse_no: int
    top_horse_name: str | None
    top_pai: float
    top_fit_label: str


@dataclass(frozen=True)
class PredictionEvaluationRecord:
    """確定結果との集計評価に使う、レース単位の最新事前予想。"""

    race_key: str
    race_date: datetime.date
    track_type: str
    predicted_label: str
    actual_rpci: float
    confidence: float
    model_version: str


class MartRepository(Protocol):
    """mart 層（predicted_pace / pace_fit）の読み書きインターフェース（ADR-0006）。

    model_version をプライマリキーの一部として保持するため、
    同一レースを再予測しても既存レコードを安全に上書きできる。
    """

    def save_predicted_pace(
        self,
        race_key: str,
        forecast: RpciForecast,
    ) -> None: ...

    def save_pace_fit(
        self,
        race_key: str,
        horse_no: int,
        result: PaiResult,
    ) -> None: ...

    def find_predicted_pace(self, race_key: str) -> PredictedPaceRecord | None: ...

    def find_race_board_forecasts(
        self, race_keys: list[str]
    ) -> dict[str, RaceBoardForecastRecord]: ...

    def find_prediction_evaluations(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> list[PredictionEvaluationRecord]: ...

    def count_prediction_evaluation_candidates(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> int: ...
