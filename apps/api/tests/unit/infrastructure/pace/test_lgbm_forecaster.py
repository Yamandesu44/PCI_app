"""LightGBMRpciForecaster / SplitLightGBMRpciForecaster ユニットテスト。モデル不要で動作する。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pci.domain.pace.rpci_forecast import (
    FrontRunnerPaceSample,
    HistoricalLapSample,
    PaceLabel,
    RaceContext,
)
from pci.domain.pace.running_style import RunningStyleLabel
from pci.infrastructure.pace.lgbm_forecaster import (
    DEFAULT_RPCI_CLAMP,
    FEATURE_NAMES,
    FEATURE_NAMES_V2,
    FEATURE_NAMES_V3,
    FEATURE_NAMES_V4,
    FEATURE_NAMES_V5,
    MODEL_VERSION,
    MODEL_VERSION_DIRT,
    MODEL_VERSION_DIRT_V2,
    MODEL_VERSION_DIRT_V3,
    MODEL_VERSION_DIRT_V4,
    MODEL_VERSION_DIRT_V5,
    MODEL_VERSION_TURF,
    MODEL_VERSION_TURF_V2,
    MODEL_VERSION_TURF_V3,
    MODEL_VERSION_TURF_V4,
    MODEL_VERSION_TURF_V5_FEATURES,
    LightGBMRpciForecaster,
    SplitLightGBMRpciForecaster,
    _classification_margin_confidence,
    _feature_names_for_booster,
    _version_for_feature_names,
    build_features,
    load_best_forecaster,
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
    field_front_pace_samples: tuple[FrontRunnerPaceSample, ...] = (),
    historical_lap_samples: tuple[HistoricalLapSample, ...] = (),
    race_month: int | None = None,
) -> RaceContext:
    return RaceContext(
        distance_m=distance_m,
        track_type=track_type,
        running_styles=styles,
        track_condition=cond,
        venue_code=venue_code,
        field_front_pace_samples=field_front_pace_samples,
        historical_lap_samples=historical_lap_samples,
        race_month=race_month,
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

    def test_v2_feature_count_matches_names(self) -> None:
        ctx = _ctx((ESCAPE,) * 2 + (FRONT,) * 3 + (STALKER,) * 4 + (RunningStyleLabel.FLEXIBLE,))

        feats = build_features(ctx, FEATURE_NAMES_V2)

        assert len(feats) == len(FEATURE_NAMES_V2)
        assert feats[8] == 10.0  # field_size
        assert feats[9] == pytest.approx(0.2)  # escape_ratio
        assert feats[10] == 5.0  # front_count
        assert feats[11] == pytest.approx(0.1)  # flexible_ratio
        assert feats[12] == pytest.approx(0.1)  # escape_competition

    def test_v2_distance_band_and_venue_one_hot(self) -> None:
        feats = build_features(
            _ctx((FRONT,) * 10, distance_m=1600, venue_code="05"),
            FEATURE_NAMES_V2,
        )

        assert feats[13:17] == [0.0, 1.0, 0.0, 0.0]
        assert feats[17:27] == [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def test_unknown_feature_definition_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="未対応のRPCI特徴量定義"):
            build_features(_ctx((FRONT,) * 10), ["unknown"])

    def test_v3_history_features_use_past_front_pace_samples(self) -> None:
        samples = (
            FrontRunnerPaceSample(1, ESCAPE, 42.0, 3),
            FrontRunnerPaceSample(2, STALKER, 48.0, 2),
        )

        feats = build_features(
            _ctx((FRONT,) * 4, field_front_pace_samples=samples),
            FEATURE_NAMES_V3,
        )

        assert len(feats) == len(FEATURE_NAMES_V3)
        assert feats[27:] == pytest.approx([2.0, 5.0, 45.0, 42.0, 6.0, 0.5])

    def test_v4_history_features_use_past_race_laps(self) -> None:
        samples = (
            HistoricalLapSample(1, 2.0, 3),
            HistoricalLapSample(2, -1.0, 2),
        )

        feats = build_features(
            _ctx((FRONT,) * 4, historical_lap_samples=samples),
            FEATURE_NAMES_V4,
        )

        assert len(feats) == len(FEATURE_NAMES_V4)
        assert feats[33:] == pytest.approx([2.0, 5.0, 0.5, -1.0, 3.0, 0.5])

    def test_v5_month_features_use_race_month(self) -> None:
        feats = build_features(
            _ctx((FRONT,) * 4, race_month=7),
            FEATURE_NAMES_V5,
        )

        assert len(feats) == len(FEATURE_NAMES_V5)
        assert feats[len(FEATURE_NAMES_V4) :] == [
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ]

    def test_v5_unknown_month_is_all_zero(self) -> None:
        feats = build_features(_ctx((FRONT,) * 4), FEATURE_NAMES_V5)

        assert feats[len(FEATURE_NAMES_V4) :] == [0.0] * 12


class TestFeatureSchemaSelection:
    """モデル内の特徴量数から互換スキーマを選択する。"""

    @pytest.mark.parametrize(
        "feature_names",
        [
            FEATURE_NAMES,
            FEATURE_NAMES_V2,
            FEATURE_NAMES_V3,
            FEATURE_NAMES_V4,
            FEATURE_NAMES_V5,
        ],
    )
    def test_supported_feature_counts(self, feature_names: list[str]) -> None:
        booster = MagicMock()
        booster.num_feature.return_value = len(feature_names)

        assert _feature_names_for_booster(booster) == feature_names

    def test_unknown_feature_count_is_rejected(self) -> None:
        booster = MagicMock()
        booster.num_feature.return_value = 99

        with pytest.raises(ValueError, match="未対応のRPCIモデル特徴量数"):
            _feature_names_for_booster(booster)

    def test_v2_feature_schema_uses_v2_model_version(self) -> None:
        assert (
            _version_for_feature_names(
                FEATURE_NAMES_V2,
                MODEL_VERSION_TURF,
                MODEL_VERSION_TURF_V2,
                MODEL_VERSION_TURF_V3,
                MODEL_VERSION_TURF_V4,
                MODEL_VERSION_TURF_V5_FEATURES,
            )
            == MODEL_VERSION_TURF_V2
        )

    def test_v5_feature_schema_uses_v5_model_version(self) -> None:
        assert (
            _version_for_feature_names(
                FEATURE_NAMES_V5,
                MODEL_VERSION_TURF,
                MODEL_VERSION_TURF_V2,
                MODEL_VERSION_TURF_V3,
                MODEL_VERSION_TURF_V4,
                MODEL_VERSION_TURF_V5_FEATURES,
            )
            == MODEL_VERSION_TURF_V5_FEATURES
        )


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
        forecaster = self._make_forecaster(55.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.label == PaceLabel.SLOW

    def test_label_correct_for_dirt(self) -> None:
        forecaster = self._make_forecaster(46.5)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.AVERAGE

    def test_rpci_clamped_at_max(self) -> None:
        forecaster = self._make_forecaster(99.0)
        result = forecaster.forecast(_ctx((CLOSER,) * 10))
        assert result.value == 65.0

    def test_rpci_clamped_at_min(self) -> None:
        forecaster = self._make_forecaster(10.0)
        result = forecaster.forecast(_ctx((ESCAPE,) * 10))
        assert result.value == 20.0

    def test_reasons_present(self) -> None:
        forecaster = self._make_forecaster(50.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10))
        codes = {r.code for r in result.reasons}
        assert "lgbm_features" in codes
        assert "forecast" in codes
        assert "classification_margin" in codes

    @pytest.mark.parametrize(
        ("rpci", "track_type", "expected"),
        [
            (49.7, "芝", 0.4),  # 境界
            (51.85, "芝", 0.9),  # 平均帯の中央
            (50.775, "芝", 0.65),  # 境界と中央の中間
            (44.8, "ダート", 0.4),
            (46.5, "ダート", 0.9),
            (43.95, "ダート", 0.65),
        ],
    )
    def test_confidence_uses_distance_from_pace_boundary(
        self,
        rpci: float,
        track_type: str,
        expected: float,
    ) -> None:
        assert _classification_margin_confidence(rpci, track_type) == expected

    def test_forecast_confidence_is_not_fixed(self) -> None:
        boundary = self._make_forecaster(49.7).forecast(_ctx((FRONT,) * 10, track_type="芝"))
        center = self._make_forecaster(51.85).forecast(_ctx((FRONT,) * 10, track_type="芝"))

        # 予測値は小数1桁へ丸められるため、平均帯の中央(51.85)はぴったり再現できない。
        # このテストの主旨は「信頼度が固定値でない」ことなので、境界との差で確認する。
        assert boundary.confidence == 0.4
        assert center.confidence >= 0.85
        assert center.confidence > boundary.confidence

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
        forecaster = self._make_split_forecaster(turf_value=55.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.label == PaceLabel.SLOW

    def test_dirt_label_average(self) -> None:
        forecaster = self._make_split_forecaster(dirt_value=46.5)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.AVERAGE

    def test_dirt_label_high(self) -> None:
        forecaster = self._make_split_forecaster(dirt_value=38.0)
        result = forecaster.forecast(_ctx((ESCAPE,) * 10, track_type="ダート"))
        assert result.label == PaceLabel.HIGH

    def test_v2_models_report_v2_versions(self) -> None:
        forecaster = self._make_split_forecaster()
        forecaster._turf_feature_names = FEATURE_NAMES_V2  # type: ignore[attr-defined]
        forecaster._dirt_feature_names = FEATURE_NAMES_V2  # type: ignore[attr-defined]

        turf = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        dirt = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))

        assert turf.model_version == MODEL_VERSION_TURF_V2
        assert dirt.model_version == MODEL_VERSION_DIRT_V2

    def test_v3_models_report_v3_versions(self) -> None:
        forecaster = self._make_split_forecaster()
        forecaster._turf_feature_names = FEATURE_NAMES_V3  # type: ignore[attr-defined]
        forecaster._dirt_feature_names = FEATURE_NAMES_V3  # type: ignore[attr-defined]

        turf = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        dirt = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))

        assert turf.model_version == MODEL_VERSION_TURF_V3
        assert dirt.model_version == MODEL_VERSION_DIRT_V3

    def test_v4_models_report_v4_versions(self) -> None:
        forecaster = self._make_split_forecaster()
        forecaster._turf_feature_names = FEATURE_NAMES_V4  # type: ignore[attr-defined]
        forecaster._dirt_feature_names = FEATURE_NAMES_V4  # type: ignore[attr-defined]

        turf = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        dirt = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))

        assert turf.model_version == MODEL_VERSION_TURF_V4
        assert dirt.model_version == MODEL_VERSION_DIRT_V4

    def test_training_provenance_overrides_feature_generation(self, tmp_path: Path) -> None:
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        dirt.with_suffix(".txt.meta.json").write_text(
            '{"model_version": "lgbm-dirt-v5-lap-history"}',
            encoding="utf-8",
        )
        mock_booster = MagicMock()
        mock_booster.predict.return_value = [43.0]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES_V4)

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            forecaster = SplitLightGBMRpciForecaster(turf, dirt)

        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.model_version == MODEL_VERSION_DIRT_V5

    def test_invalid_training_provenance_falls_back_to_feature_generation(
        self, tmp_path: Path
    ) -> None:
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        dirt.with_suffix(".txt.meta.json").write_text("[]", encoding="utf-8")
        mock_booster = MagicMock()
        mock_booster.predict.return_value = [43.0]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES_V4)

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            forecaster = SplitLightGBMRpciForecaster(turf, dirt)

        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.model_version == MODEL_VERSION_DIRT_V4

    def test_empty_field_raises(self) -> None:
        forecaster = self._make_split_forecaster()
        with pytest.raises(ValueError, match="脚質情報がありません"):
            forecaster.forecast(_ctx((), track_type="芝"))


class TestLoadBestForecaster:
    """load_best_forecaster() のモデル選択優先度を検証する。"""

    def test_no_models_returns_rule_based(self, tmp_path: Path) -> None:
        """モデルファイルが 1 つも無い場合は RuleBasedRpciForecaster を返す。"""
        from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster

        result = load_best_forecaster(
            model_path=tmp_path / "none.txt",
            turf_model_path=tmp_path / "turf_none.txt",
            dirt_model_path=tmp_path / "dirt_none.txt",
        )
        assert isinstance(result, RuleBasedRpciForecaster)

    def test_split_models_take_priority_over_unified(self, tmp_path: Path) -> None:
        """芝・ダート別モデルが揃っていれば統合モデルより優先される。"""
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        unified = tmp_path / "unified.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        unified.write_text("dummy")

        mock_booster = MagicMock()
        mock_booster.predict.return_value = [52.0]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES)

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            result = load_best_forecaster(
                model_path=unified,
                turf_model_path=turf,
                dirt_model_path=dirt,
            )
        assert isinstance(result, SplitLightGBMRpciForecaster)

    def test_unified_model_used_when_split_absent(self, tmp_path: Path) -> None:
        """芝・ダート別モデルが無く統合モデルがあれば LightGBMRpciForecaster を返す。"""
        unified = tmp_path / "unified.txt"
        unified.write_text("dummy")

        mock_booster = MagicMock()
        mock_booster.predict.return_value = [50.0]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES)

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            result = load_best_forecaster(
                model_path=unified,
                turf_model_path=tmp_path / "turf_none.txt",
                dirt_model_path=tmp_path / "dirt_none.txt",
            )
        assert isinstance(result, LightGBMRpciForecaster)

    def test_split_load_failure_falls_back_to_unified(self, tmp_path: Path) -> None:
        """芝モデルのロード失敗（SplitForecaster 初期化失敗）時に統合モデルへフォールバックする。

        SplitLightGBMRpciForecaster は turf を先にロードするため、
        turf のロード失敗時点で例外が発生し dirt は呼ばれない。
        その後 load_best_forecaster の except ブロックで統合モデルへ進む。
        """
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        unified = tmp_path / "unified.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        unified.write_text("dummy")

        call_count = 0

        def raise_on_turf(path: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # turf ロードだけ失敗 → SplitForecaster 初期化失敗
                raise RuntimeError("corrupt turf model")
            m = MagicMock()
            m.predict.return_value = [50.0]
            m.num_feature.return_value = len(FEATURE_NAMES)
            return m

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            side_effect=raise_on_turf,
        ):
            result = load_best_forecaster(
                model_path=unified,
                turf_model_path=turf,
                dirt_model_path=dirt,
            )
        assert isinstance(result, LightGBMRpciForecaster)

    def test_all_load_failures_fall_back_to_rule_based(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """全モデルのロードに失敗しても RuleBasedRpciForecaster で安全に動作する。"""
        from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster

        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        unified = tmp_path / "unified.txt"
        for p in (turf, dirt, unified):
            p.write_text("dummy")

        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            side_effect=RuntimeError("always fail"),
        ):
            result = load_best_forecaster(
                model_path=unified,
                turf_model_path=turf,
                dirt_model_path=dirt,
            )
        assert isinstance(result, RuleBasedRpciForecaster)
        assert "芝・ダート別LightGBMモデルを読み込めません" in caplog.text
        assert "統合LightGBMモデルを読み込めません" in caplog.text

    def test_rule_based_fallback_is_functional(self, tmp_path: Path) -> None:
        """フォールバック先の RuleBasedRpciForecaster が正常に予測できる。"""
        forecaster = load_best_forecaster(
            model_path=tmp_path / "none.txt",
            turf_model_path=tmp_path / "none_turf.txt",
            dirt_model_path=tmp_path / "none_dirt.txt",
        )
        ctx = _ctx((FRONT,) * 5 + (STALKER,) * 5, track_type="芝")
        result = forecaster.forecast(ctx)
        assert result.model_version == "rule-v4"
        assert result.value >= 35.0


class TestCommittedModels:
    """追跡中のモデルがcheckout後も実際にロード・予測できることを検証する。"""

    def test_split_models_are_loadable(self) -> None:
        models_dir = Path(__file__).resolve().parents[4] / "models"
        forecaster = load_best_forecaster(
            model_path=models_dir / "rpci_lgbm_v1.txt",
            turf_model_path=models_dir / "rpci_lgbm_turf_v1.txt",
            dirt_model_path=models_dir / "rpci_lgbm_dirt_v1.txt",
        )

        assert isinstance(forecaster, SplitLightGBMRpciForecaster)
        turf = forecaster.forecast(_ctx((FRONT,) * 5 + (STALKER,) * 5, track_type="芝"))
        dirt = forecaster.forecast(_ctx((FRONT,) * 5 + (STALKER,) * 5, track_type="ダート"))
        assert turf.model_version == MODEL_VERSION_TURF
        assert dirt.model_version == MODEL_VERSION_DIRT

    def test_crlf_model_is_normalized_before_loading(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        models_dir = Path(__file__).resolve().parents[4] / "models"
        source = models_dir / "rpci_lgbm_v1.txt"
        crlf_model = tmp_path / "rpci_lgbm_v1_crlf.txt"
        crlf_model.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))

        forecaster = LightGBMRpciForecaster(crlf_model)
        result = forecaster.forecast(_ctx((FRONT,) * 5 + (STALKER,) * 5))

        assert result.model_version == MODEL_VERSION
        assert "CRLF改行をLFへ補正" in caplog.text


class TestRpciClamp:
    """予測値の安全弁は既定で本番値。較正の実測時だけ呼び出し側が広げられる。"""

    def _forecaster(
        self, tmp_path: Path, raw: float, clamp: tuple[float, float] | None = None
    ) -> SplitLightGBMRpciForecaster:
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        mock_booster = MagicMock()
        mock_booster.predict.return_value = [raw]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES_V4)
        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            if clamp is None:
                return SplitLightGBMRpciForecaster(turf, dirt)
            return SplitLightGBMRpciForecaster(turf, dirt, clamp)

    def test_floor_matches_the_training_label_range(self) -> None:
        """下限は学習ラベル範囲の下端（train_rpci_lgbm.py の --rpci-min 既定）と一致させる。"""
        assert DEFAULT_RPCI_CLAMP == (20.0, 65.0)

    def test_production_floor_no_longer_truncates_realistic_dirt_pace(self, tmp_path: Path) -> None:
        """ダート実分布（最小20.9）に届く予測を、旧下限35.0のように切り捨てない。"""
        forecaster = self._forecaster(tmp_path, raw=28.4)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 28.4

    def test_production_floor_still_bounds_implausible_output(self, tmp_path: Path) -> None:
        forecaster = self._forecaster(tmp_path, raw=5.0)
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 20.0

    def test_widened_clamp_lets_the_model_predict_low(self, tmp_path: Path) -> None:
        forecaster = self._forecaster(tmp_path, raw=28.4, clamp=(20.0, 90.0))
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 28.4

    def test_widened_clamp_still_bounds_extreme_output(self, tmp_path: Path) -> None:
        forecaster = self._forecaster(tmp_path, raw=5.0, clamp=(20.0, 90.0))
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 20.0

    def test_clamp_applies_to_turf_branch_too(self, tmp_path: Path) -> None:
        forecaster = self._forecaster(tmp_path, raw=28.4, clamp=(20.0, 90.0))
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="芝"))
        assert result.value == 28.4

    def test_unified_forecaster_accepts_the_clamp(self, tmp_path: Path) -> None:
        model = tmp_path / "unified.txt"
        model.write_text("dummy")
        mock_booster = MagicMock()
        mock_booster.predict.return_value = [28.4]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES)
        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            forecaster = LightGBMRpciForecaster(model, (20.0, 90.0))
        assert forecaster.forecast(_ctx((FRONT,) * 10)).value == 28.4

    def test_load_best_forecaster_forwards_the_clamp(self, tmp_path: Path) -> None:
        turf = tmp_path / "turf.txt"
        dirt = tmp_path / "dirt.txt"
        turf.write_text("dummy")
        dirt.write_text("dummy")
        mock_booster = MagicMock()
        mock_booster.predict.return_value = [28.4]
        mock_booster.num_feature.return_value = len(FEATURE_NAMES_V4)
        with patch(
            "pci.infrastructure.pace.lgbm_forecaster._load_lgb_booster",
            return_value=mock_booster,
        ):
            forecaster = load_best_forecaster(
                turf_model_path=turf, dirt_model_path=dirt, clamp=(20.0, 90.0)
            )
        result = forecaster.forecast(_ctx((FRONT,) * 10, track_type="ダート"))
        assert result.value == 28.4


class TestProductionModelPaths:
    """本番既定モデルの世代を固定する（差し替え時にテストで気づけるように）。"""

    def test_default_dirt_model_is_v6(self) -> None:
        from pci.infrastructure.pace.lgbm_forecaster import _DEFAULT_DIRT_MODEL_PATH

        assert _DEFAULT_DIRT_MODEL_PATH.name == "rpci_lgbm_dirt_v6.txt"
        assert _DEFAULT_DIRT_MODEL_PATH.is_file()

    def test_default_dirt_model_declares_its_generation(self) -> None:
        """来歴JSONが無いと特徴量数(39)からv4へフォールバックし、mart層へ誤記録される。"""
        import json

        from pci.infrastructure.pace.lgbm_forecaster import _DEFAULT_DIRT_MODEL_PATH

        meta = _DEFAULT_DIRT_MODEL_PATH.with_suffix(".txt.meta.json")
        assert meta.is_file()
        payload = json.loads(meta.read_text(encoding="utf-8"))
        assert payload["model_version"] == "lgbm-dirt-v6-pci-v3"
        # 1.0未満は旧フォールバック式ラベルの混入を意味する。
        assert payload["lap_derived_ratio"] == 1.0
