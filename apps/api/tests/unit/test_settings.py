"""環境変数から読み込むAPI設定の単体テスト。"""

from __future__ import annotations

from pytest import MonkeyPatch

from pci.config.settings import DEFAULT_GEMINI_MODEL, Settings


def test_gemini_model_defaults_to_current_flash(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.gemini_model == DEFAULT_GEMINI_MODEL == "gemini-3.5-flash"


def test_gemini_model_can_be_overridden_by_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-2.5-flash-lite"
