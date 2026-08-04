"""UI へ露出する reasons に PCI/RPCI/PCI3 の実数値が混ざっていないことを守る。

CLAUDE.md / PROJECT_RULES の「UI に PCI/RPCI 実数値を出さない（言葉・段階評価へ翻訳）」を
テストで固定する。reasons の description は ReasonList でそのまま描画されるため、
ここへ指数を書くと「算出の根拠」「予測の根拠」に生の数字が出る。

2026-08-04: 実際に両方から漏れていた（確定後 `RPCI=51.8` / 出走前 `想定RPCI=43.2`）。
JRA公式(TARGET)の値と桁が合わないため、利用者には誤差にしか見えない。
"""

from __future__ import annotations

import re

import pytest

from pci.domain.pace.pci import aggregate_rpci
from pci.domain.pace.rpci_forecast import RaceContext, RuleBasedRpciForecaster
from pci.domain.pace.running_style import RunningStyleLabel

# 「PCI=51.8」「想定RPCI = 43」「PCI3=53.9」等を捕まえる。
_INDEX_VALUE = re.compile(r"(?:R?PCI3?)\s*[=＝:：]\s*-?\d")

FRONT = RunningStyleLabel.FRONT
ESCAPE = RunningStyleLabel.ESCAPE
STALKER = RunningStyleLabel.STALKER


def _assert_no_index_value(descriptions: list[str]) -> None:
    leaked = [d for d in descriptions if _INDEX_VALUE.search(d)]
    assert not leaked, f"UIへ出る根拠に指数の実数値が含まれています: {leaked}"


class TestConfirmedAnalysisReasons:
    """確定後の「算出の根拠」に出る reasons。"""

    def test_lap_derived_reasons_hide_the_index(self) -> None:
        result = aggregate_rpci([52.0, 48.0, 55.0], [1, 2, 3], race_rpci=51.6)

        _assert_no_index_value([r.description for r in result.reasons])
        # 数値そのものは返り値で使えること（表示側が段階評価へ翻訳する）。
        assert result.rpci == 51.6

    def test_fallback_reasons_hide_the_index(self) -> None:
        result = aggregate_rpci([52.0, 48.0, 55.0], [1, 2, 3])

        _assert_no_index_value([r.description for r in result.reasons])
        assert result.rpci is not None

    def test_fallback_still_says_it_is_provisional(self) -> None:
        """暫定であることは伝え続ける（数値だけ隠す）。"""
        result = aggregate_rpci([52.0, 48.0, 55.0], [1, 2, 3])

        text = " ".join(r.description for r in result.reasons)
        assert "暫定" in text
        assert "レースラップ" in text

    def test_pci3_unavailable_reason_hides_the_index(self) -> None:
        result = aggregate_rpci([52.0, 48.0], [7, 8])

        assert result.pci3 is None
        _assert_no_index_value([r.description for r in result.reasons])


class TestForecastReasons:
    """出走前の「予測の根拠」に出る reasons。"""

    @pytest.mark.parametrize(
        "styles",
        [
            (ESCAPE,) * 3 + (FRONT,) * 5 + (STALKER,) * 2,
            (STALKER,) * 8 + (FRONT,) * 2,
        ],
    )
    def test_rule_based_forecast_reasons_hide_the_index(
        self, styles: tuple[RunningStyleLabel, ...]
    ) -> None:
        forecast = RuleBasedRpciForecaster().forecast(
            RaceContext(
                distance_m=1800,
                track_type="芝",
                running_styles=styles,
                track_condition="良",
                venue_code="01",
            )
        )

        _assert_no_index_value([r.description for r in forecast.reasons])
        assert forecast.value > 0  # 数値は value で返る

    def test_forecast_reason_still_states_the_pace(self) -> None:
        """流れの区分と信頼度は伝え続ける。"""
        forecast = RuleBasedRpciForecaster().forecast(
            RaceContext(
                distance_m=1800,
                track_type="芝",
                running_styles=(ESCAPE,) * 3 + (FRONT,) * 7,
                track_condition="良",
                venue_code="01",
            )
        )

        text = " ".join(r.description for r in forecast.reasons)
        assert str(forecast.label) in text
