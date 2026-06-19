"""Ingest API クライアント。

FastAPI の POST /internal/ingest/* エンドポイントへデータを送信する。
ingestion-worker → API → PostgreSQL のデータフローを担う。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ingestion.models import (
    HorseRecord,
    JockeyRecord,
    RaceEntriesRecord,
    RaceResultRecord,
    TrainerRecord,
)

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_BATCH_SIZE = 100  # マスタデータの一括送信サイズ


class IngestApiClient:
    """POST /internal/ingest/* を呼び出す HTTP クライアント。

    全エンドポイントで X-Ingest-Token ヘッダーを送信する（未設定時は空文字）。
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["X-Ingest-Token"] = self._token
        return h

    def _post(self, path: str, payload: Any) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        resp = self._http.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    # ----- マスタデータ -----

    def upsert_horses(self, horses: list[HorseRecord]) -> int:
        """馬マスタを一括 Upsert する。accepted 件数を返す。"""
        total = 0
        for i in range(0, len(horses), _BATCH_SIZE):
            batch = horses[i : i + _BATCH_SIZE]
            payload = [
                {
                    "ketto_num": h.ketto_num,
                    "name": h.name,
                    "sex": h.sex,
                    "birth_year": h.birth_year,
                }
                for h in batch
            ]
            result = self._post("/internal/ingest/horses", payload)
            total += result.get("accepted", 0)
        _log.info("馬マスタ upsert: %d 件", total)
        return total

    def upsert_jockeys(self, jockeys: list[JockeyRecord]) -> int:
        """騎手マスタを一括 Upsert する。"""
        total = 0
        for i in range(0, len(jockeys), _BATCH_SIZE):
            batch = jockeys[i : i + _BATCH_SIZE]
            payload = [{"code": j.code, "name": j.name} for j in batch]
            result = self._post("/internal/ingest/jockeys", payload)
            total += result.get("accepted", 0)
        _log.info("騎手マスタ upsert: %d 件", total)
        return total

    def upsert_trainers(self, trainers: list[TrainerRecord]) -> int:
        """調教師マスタを一括 Upsert する。"""
        total = 0
        for i in range(0, len(trainers), _BATCH_SIZE):
            batch = trainers[i : i + _BATCH_SIZE]
            payload = [{"code": t.code, "name": t.name} for t in batch]
            result = self._post("/internal/ingest/trainers", payload)
            total += result.get("accepted", 0)
        _log.info("調教師マスタ upsert: %d 件", total)
        return total

    # ----- レースデータ -----

    def register_entries(self, record: RaceEntriesRecord) -> int:
        """出走表を登録する。accepted 件数（出走馬数）を返す。"""
        payload: dict[str, Any] = {
            "race_key": record.race_key,
            "race_date": record.race_date.isoformat(),
            "jyo_cd": record.jyo_cd,
            "distance_m": record.distance_m,
            "track_type": record.track_type,
            "field_size": record.field_size,
            "track_condition": record.track_condition,
            "weather": record.weather,
            "grade": record.grade,
            "race_class": record.race_class,
            "entries": [
                {
                    "horse_no": e.horse_no,
                    "frame_no": e.frame_no,
                    "ketto_num": e.ketto_num,
                    "weight": e.weight,
                    "jockey_code": e.jockey_code,
                    "trainer_code": e.trainer_code,
                }
                for e in record.entries
            ],
        }
        result = self._post("/internal/ingest/entries", payload)
        n: int = result.get("accepted", 0)
        _log.info("出走表登録 %s: %d 頭", record.race_key, n)
        return n

    def record_results(self, record: RaceResultRecord) -> dict[str, Any]:
        """確定成績を送信し、RPCI / PCI3 等の算出結果を返す。"""
        payload: dict[str, Any] = {
            "race_key": record.race_key,
            "track_condition": record.track_condition,
            "weather": record.weather,
            "results": [
                {
                    "horse_no": r.horse_no,
                    "finish_pos": r.finish_pos,
                    "race_time_s": r.race_time_s,
                    "agari_3f_s": r.agari_3f_s,
                    "corner_1": r.corner_1,
                    "corner_2": r.corner_2,
                    "corner_3": r.corner_3,
                    "corner_4": r.corner_4,
                }
                for r in record.results
            ],
        }
        result = self._post("/internal/ingest/results", payload)
        _log.info(
            "成績登録 %s: RPCI=%.1f PCI3=%s",
            record.race_key,
            result.get("rpci") or 0.0,
            result.get("pci3"),
        )
        return result
