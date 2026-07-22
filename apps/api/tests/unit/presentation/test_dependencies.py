"""コメント生成器を選択するDIの単体テスト。"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from pci.config.settings import Settings
from pci.domain.pace.commentary import RuleBasedCommentGenerator
from pci.infrastructure.llm_comment_generator import GeminiCommentGenerator
from pci.presentation import dependencies


@pytest.fixture(autouse=True)
def _clear_comment_generator_cache() -> Iterator[None]:
    dependencies._get_comment_generator.cache_clear()
    yield
    dependencies._get_comment_generator.cache_clear()


def _select_generator(monkeypatch: MonkeyPatch, settings: Settings) -> object:
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    return dependencies._get_comment_generator()


def test_rule_mode_does_not_use_gemini_when_api_key_exists(monkeypatch: MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        comment_generator_mode="rule",
        gemini_api_key="stored-key",
    )

    generator = _select_generator(monkeypatch, settings)

    assert isinstance(generator, RuleBasedCommentGenerator)


def test_gemini_requires_explicit_mode_and_api_key(monkeypatch: MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        comment_generator_mode="gemini",
        gemini_api_key="test-key",
    )

    generator = _select_generator(monkeypatch, settings)

    assert isinstance(generator, GeminiCommentGenerator)


def test_gemini_mode_without_api_key_falls_back(
    monkeypatch: MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    settings = Settings(_env_file=None, comment_generator_mode="gemini")

    with caplog.at_level(logging.WARNING):
        generator = _select_generator(monkeypatch, settings)

    assert isinstance(generator, RuleBasedCommentGenerator)
    assert "GEMINI_API_KEYが未設定" in caplog.text
