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
    RaceMetadataRecord,
    RaceResultRecord,
    TrainerRecord,
)

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_FORECAST_PRECOMPUTE_TIMEOUT = 300.0
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

    def _post(
        self,
        path: str,
        payload: Any,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        request_options: dict[str, Any] = {}
        if timeout is not None:
            request_options["timeout"] = timeout
        resp = self._http.post(
            url,
            json=payload,
            headers=self._headers(),
            **request_options,
        )
        if resp.is_error:
            # エラー時はレスポンスボディ(detail)を含めて原因を明示する
            raise RuntimeError(f"Ingest API エラー {resp.status_code} {path}: {resp.text[:1000]}")
        result: dict[str, Any] = resp.json()
        return result

    def _delete(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        resp = self._http.delete(url, headers=self._headers())
        if resp.is_error:
            raise RuntimeError(f"Ingest API エラー {resp.status_code} {path}: {resp.text[:1000]}")
        result: dict[str, Any] = resp.json()
        return result

    def incomplete_race_keys(self) -> set[str]:
        """APIが検出した成績未取り込みのJRA平地レースキーを返す。"""
        path = "/internal/ingest/incomplete-race-keys"
        resp = self._http.get(f"{self._base_url}{path}", headers=self._headers())
        if resp.is_error:
            raise RuntimeError(f"Ingest API エラー {resp.status_code} {path}: {resp.text[:1000]}")
        payload: list[str] = resp.json()
        return set(payload)

    def duplicate_race_audit(
        self, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        """指定期間の重複レースdry-run情報を取得する。"""
        path = "/internal/ingest/duplicate-race-audit"
        resp = self._http.get(
            f"{self._base_url}{path}",
            params={"date_from": date_from, "date_to": date_to, "limit": 10_000},
            headers=self._headers(),
        )
        if resp.is_error:
            raise RuntimeError(
                f"Ingest API エラー {resp.status_code} {path}: {resp.text[:1000]}"
            )
        payload: list[dict[str, Any]] = resp.json()
        return payload

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
            "grade": record.grade,
            "race_s3f": record.race_s3f,
            "race_l3f": record.race_l3f,
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
                    "body_weight": r.body_weight,
                    "popularity": r.popularity,
                    "prize_money": r.prize_money,
                }
                for r in record.results
            ],
        }
        result = self._post("/internal/ingest/results", payload)
        _log.info(
            "成績登録 %s: RPCI=%.1f PCI3=%s%s",
            record.race_key,
            result.get("rpci") or 0.0,
            result.get("pci3"),
            (
                " (S3/L3ラップ由来)"
                if (record.race_s3f and record.race_l3f)
                else " (平均フォールバック)"
            ),
        )
        return result

    def update_race_metadata(self, records: list[RaceMetadataRecord]) -> int:
        """既存レースへコース種別・馬場状態・天候を一括反映する。"""
        total = 0
        for i in range(0, len(records), _BATCH_SIZE):
            batch = records[i : i + _BATCH_SIZE]
            payload = [
                {
                    "race_key": record.race_key,
                    "track_type": record.track_type,
                    "track_condition": record.track_condition,
                    "weather": record.weather,
                }
                for record in batch
            ]
            result = self._post("/internal/ingest/race-metadata", payload)
            total += int(result.get("accepted", 0))
        _log.info("レース補足情報更新: %d / %d 件", total, len(records))
        return total

    def delete_race(self, race_key: str) -> int:
        """取り込み対象外になったレースをAPI側DBから削除する。"""
        result = self._delete(f"/internal/ingest/races/{race_key}")
        accepted = int(result.get("accepted", 0))
        _log.info("レース削除 %s: %d 件", race_key, accepted)
        return accepted

    def precompute_forecasts(self, date_from: str, date_to: str) -> dict[str, int]:
        """今後のレース予想をAPI側で事前生成する。"""
        result = self._post(
            "/internal/ingest/forecasts/precompute",
            {"date_from": date_from, "date_to": date_to},
            timeout=_FORECAST_PRECOMPUTE_TIMEOUT,
        )
        summary = {
            "scanned": int(result.get("scanned", 0)),
            "generated": int(result.get("generated", 0)),
            "skipped": int(result.get("skipped", 0)),
        }
        _log.info(
            "予想事前生成: 対象 %d / 生成 %d / スキップ %d",
            summary["scanned"],
            summary["generated"],
            summary["skipped"],
        )
        return summary

    def log_batch(
        self,
        *,
        batch_date: str,
        step: str,
        mode: str,
        started_at: str,
        finished_at: str | None,
        status: str,
        error_msg: str | None = None,
    ) -> int:
        """バッチ実行ログを API に記録し、ログ ID を返す。失敗は警告のみでバッチを止めない。"""
        payload = {
            "batch_date": batch_date,
            "step": step,
            "mode": mode,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "error_msg": error_msg,
        }
        try:
            result = self._post("/internal/ingest/log", payload)
            log_id = int(result.get("id", 0))
            _log.info("取り込みログ記録: id=%d step=%s status=%s", log_id, step, status)
            return log_id
        except Exception as exc:
            _log.warning("取り込みログ記録失敗（バッチは継続）: %s", exc)
            return 0
