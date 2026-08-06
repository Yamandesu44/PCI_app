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


class TestWarmUp:
    """起動時ウォームアップ。

    `_get_forecaster` は lru_cache なので、何もしなければ最初の予想リクエストが
    LightGBM の読み込みを負担する。Cloud Run のようにゼロスケールする環境では
    起動のたびに起きるため、待たされるのは常に「その時の最初の利用者」になる。
    """

    def test_populates_the_forecaster_cache(self) -> None:
        from pci.presentation import dependencies

        dependencies._get_forecaster.cache_clear()
        assert dependencies._get_forecaster.cache_info().currsize == 0

        dependencies.warm_up()

        assert dependencies._get_forecaster.cache_info().currsize == 1

    def test_does_not_raise_when_loading_fails(self) -> None:
        """起動を止めない。予想以外の機能は動くので、落とすほうが損。"""
        from unittest.mock import patch

        from pci.presentation import dependencies

        dependencies._get_forecaster.cache_clear()
        with patch.object(dependencies, "load_best_forecaster", side_effect=RuntimeError("boom")):
            dependencies.warm_up()  # 例外が漏れないこと

        dependencies._get_forecaster.cache_clear()
