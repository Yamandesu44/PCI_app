"""LightGBMRpciForecaster / SplitLightGBMRpciForecaster ユニットテスト。モデル不要で動作する。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pci.domain.pace.rpci_forecast import PaceLabel, RaceContext
from pci.domain.pace.running_style import RunningStyleLabel
from pci.infrastructure.pace.lgbm_forecaster import (
    FEATURE_NAMES,
    MODEL_VERSION,
    MODEL_VERSION_DIRT,
    MODEL_VERSION_TURF,
    LightGBMRpciForecaster,
    SplitLightGBMRpciForecaster,
    build_features,
)

FRONT = RunningStyleLabel.FRONT
ESCAPE = RunningStyleLabel.ESCAPE
STALKER = RunningStyleLabel.STALKER
CLOSER = RunningStyleLabel.CLOSER


def _ctx(
    styles: tuple[RunningStyleLabel, ...],
    distance_m: int = 1600,
    track_type: str = "芝",
    venue_code: str | None = "05",
    cond: str | None = None,
) -> RaceContext:
    return RaceContext(
        distance_m=distance_m,
        track_type=track_type,
        running_styles=styles,
        track_condition=cond,
        venue_code=venue_code,
    )


class TestBuildFeatures:
    """build_features() の出力が FEATURE_NAMES と一致することを確認する。"""

    def test_feature_count_matches_names(self) -> None:
        ctx = _ctx((FRONT,) * 5 + (STALKER,) * 5)
        feats = build_features(ctx)
        assert len(feats) == len(FEATURE_NAMES)

    def test_dirt_flag(self) -> None:
        turf = build_features(_ctx((FRONT,) * 10, track_type="芝"))
        dirt = build_features(_ctx((FRONT,) * 10, track_type="ダート"))
        # FEATURE_NAMES[1] == "is_dirt"
        assert turf[1] == 0.0
        assert dirt[1] == 1.0

    def test_venue_code_parsed(self) -> None:
        ctx = _ctx((FRONT,) * 10, venue_code="05")
        # FEATURE_NAMES[2] == "jyo_cd"
        assert build_features(ctx)[2] == 5.0

    def test_invalid_venue_code_becomes_zero(self) -> None:
        ctx = _ctx((FRONT,) * 10, venue_code="XX")
        assert build_features(ctx)[2] == 0.0

    def test_track_cond_ordinal(self) -> None:
        ctx_heavy = _ctx((FRONT,) * 10, cond="重")
        # FEATURE_NAMES[7] == "track_cond"
        assert build_features(ctx_heavy)[7] == 2.0

    def test_style_balance_all_front(self) -> None:
        ctx = _ctx((ESCAPE,) * 5 + (FRONT,) * 5, venue_code=None)
        feats = build_features(ctx)
        # front_ratio=1.0, closer_ratio=0.0, style_balance=-1.0
        assert feats[4] == pytest.approx(1.0)  # front_ratio
        assert feats[5] == pytest.approx(0.0)  # closer_ratio
        assert feats[6] == pytest.approx(-1.0)  # style_balance


def _mock_predict(value: float):  # type: ignore[return]
    """fixed value を返す predict 関数を生成する。"""
    m = MagicMock()
    m.predict.return_value = [value]
    return m.predict


class TestLightGBMRpciForecaster:
    """統合モデル（後方互換）の動作検証。"""

    @staticmethod
    def _make_forecaster(predict_value: float = 52.0) -> LightGBMRpciForecaster:
        with (
            patch.dict("sys.modules", {"lightgbm": MagicMock()}),
            patch(
                "pci.infrastructure.pace.lgbm_forecaster.LightGBMRpciForecaster.__init__",
                return_value=None,
            ),
        ):
            forecaster = LightGBMRpciForecaster.__new__(LightGBMRpciForecaster)
            forecaster._predict = _mock_predict(predict_value)  # type: ignore[attr-defined]
        return forecaster

    def test_model_version_constant(self) -> None:
        assert MODEL_VERSION == "lgbm-v1"

    def test_returns_rpci_forecast(self) -> None:
        forecaster = self._make_forecaster(52.0)
        result = forecaster.forecast(_ctx((FRONT,) * 5 + (STALKER,) * 5))
        assert result.model_version == "lgbm-v1"
        assert result.value == 52.0

    def test_label_correct_for_turf(self) -> None:
        forecaster = self._make_forecaster(53.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.label == PaceLabel.SLOW

    def test_label_correct_for_dirt(self) -> None:
        forecaster = self._make_forecaster(43.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.AVERAGE

    def test_rpci_clamped_at_max(self) -> None:
        forecaster = self._make_forecaster(99.0)
        result = forecaster.forecast(_ctx((CLOSER,) * 10))
        assert result.value == 65.0

    def test_rpci_clamped_at_min(self) -> None:
        forecaster = self._make_forecaster(10.0)
        result = forecaster.forecast(_ctx((ESCAPE,) * 10))
        assert result.value == 35.0

    def test_reasons_present(self) -> None:
        forecaster = self._make_forecaster(50.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10))
        codes = {r.code for r in result.reasons}
        assert "lgbm_features" in codes
        assert "forecast" in codes

    def test_empty_field_raises(self) -> None:
        forecaster = self._make_forecaster()
        with pytest.raises(ValueError, match="脚質情報がありません"):
            forecaster.forecast(_ctx(()))

    def test_import_error_on_missing_lightgbm(self) -> None:
        import sys

        original = sys.modules.get("lightgbm")
        sys.modules["lightgbm"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="lightgbm"):
                LightGBMRpciForecaster("dummy_path.txt")
        finally:
            if original is None:
                sys.modules.pop("lightgbm", None)
            else:
                sys.modules["lightgbm"] = original


class TestSplitLightGBMRpciForecaster:
    """芝/ダート別モデルの動作検証。"""

    @staticmethod
    def _make_split_forecaster(
        turf_value: float = 52.0,
        dirt_value: float = 43.0,
    ) -> SplitLightGBMRpciForecaster:
        with (
            patch.dict("sys.modules", {"lightgbm": MagicMock()}),
            patch(
                "pci.infrastructure.pace.lgbm_forecaster.SplitLightGBMRpciForecaster.__init__",
                return_value=None,
            ),
        ):
            forecaster = SplitLightGBMRpciForecaster.__new__(SplitLightGBMRpciForecaster)
            forecaster._turf_predict = _mock_predict(turf_value)  # type: ignore[attr-defined]
            forecaster._dirt_predict = _mock_predict(dirt_value)  # type: ignore[attr-defined]
        return forecaster

    def test_turf_version(self) -> None:
        assert MODEL_VERSION_TURF == "lgbm-turf-v1"

    def test_dirt_version(self) -> None:
        assert MODEL_VERSION_DIRT == "lgbm-dirt-v1"

    def test_turf_uses_turf_model(self) -> None:
        forecaster = self._make_split_forecaster(turf_value=54.0, dirt_value=41.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.value == 54.0
        assert result.model_version == MODEL_VERSION_TURF

    def test_dirt_uses_dirt_model(self) -> None:
        forecaster = self._make_split_forecaster(turf_value=54.0, dirt_value=41.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 41.0
        assert result.model_version == MODEL_VERSION_DIRT

    def test_turf_label(self) -> None:
        forecaster = self._make_split_forecaster(turf_value=53.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.label == PaceLabel.SLOW

    def test_dirt_label_average(self) -> None:
        forecaster = self._make_split_forecaster(dirt_value=43.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.AVERAGE

    def test_dirt_label_high(self) -> None:
        forecaster = self._make_split_forecaster(dirt_value=38.0)
        result = forecaster.forecast(_ctx((ESCAPE,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.HIGH

    def test_empty_field_raises(self) -> None:
        forecaster = self._make_split_forecaster()
        with pytest.raises(ValueError, match="脚質情報がありません"):
            forecaster.forecast(_ctx((), track_type="芝"))
