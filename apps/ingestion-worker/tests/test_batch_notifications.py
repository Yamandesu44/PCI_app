"""取り込み失敗通知の回帰テスト。"""

from __future__ import annotations

import logging

import httpx

from ingestion import batch


def test_wrapper_owner_skips_python_notification(monkeypatch) -> None:
    """PowerShellラッパー配下ではリトライごとの重複通知を送らない。"""
    monkeypatch.setenv("INGEST_NOTIFICATION_OWNER", "wrapper")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.invalid/secret")

    def unexpected_post(*args, **kwargs):
        raise AssertionError("httpx.post should not be called")

    monkeypatch.setattr(batch.httpx, "post", unexpected_post)

    batch._notify_failure("entries", "20260725", "test error")


def test_notification_redacts_url_and_restores_httpx_log_level(
    monkeypatch,
    caplog,
) -> None:
    """通知失敗時もWebhook URLをログへ残さず、ロガー設定を復元する。"""
    url = "https://example.invalid/services/secret-token"
    monkeypatch.delenv("INGEST_NOTIFICATION_OWNER", raising=False)
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", url)

    def failing_post(*args, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(500, request=request)
        return response

    monkeypatch.setattr(batch.httpx, "post", failing_post)
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level

    with caplog.at_level(logging.WARNING):
        batch._notify_failure("results", "20260725", "test error")

    assert url not in caplog.text
    assert "<redacted>" in caplog.text
    assert httpx_logger.level == previous_level
