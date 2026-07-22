"""環境変数から読み込むAPI設定の単体テスト。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from pci.config.settings import DEFAULT_GEMINI_MODEL, Settings


def test_comment_generator_defaults_to_rule_even_with_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("COMMENT_GENERATOR_MODE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "stored-key")

    settings = Settings(_env_file=None)

    assert settings.comment_generator_mode == "rule"


def test_comment_generator_mode_can_enable_gemini(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("COMMENT_GENERATOR_MODE", "gemini")

    settings = Settings(_env_file=None)

    assert settings.comment_generator_mode == "gemini"


def test_comment_generator_mode_rejects_unknown_value(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("COMMENT_GENERATOR_MODE", "auto")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_gemini_model_defaults_to_current_flash(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.gemini_model == DEFAULT_GEMINI_MODEL == "gemini-3.5-flash"


def test_gemini_model_can_be_overridden_by_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-2.5-flash-lite"
