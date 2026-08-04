"""LightGBM 実装の想定 RPCI 予測器（ADR-0005: ML 疎結合 IF）。

RpciForecaster プロトコルを満たし、ForecastRaceUseCase に DI で注入される。

モデル選択の優先順位（load_best_forecaster 参照）:
  1. rpci_lgbm_turf_v1.txt + rpci_lgbm_dirt_v1.txt 両方あり → SplitLightGBMRpciForecaster
  2. rpci_lgbm_v1.txt あり                               → LightGBMRpciForecaster（統合）
  3. いずれも無し                                         → RuleBasedRpciForecaster（後退）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pci.domain.pace.rpci_forecast import (
    CLASSIFICATION_MARGIN_REASON_CODE,
    DEFAULT_WEIGHTS,
    RaceContext,
    RpciForecast,
    RpciForecaster,
    classify_pace,
)
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "lgbm-v1"          # 統合モデル（後方互換）
MODEL_VERSION_TURF = "lgbm-turf-v1"  # 芝専用モデル
MODEL_VERSION_DIRT = "lgbm-dirt-v1"  # ダート専用モデル
MODEL_VERSION_V2 = "lgbm-v2-features"
MODEL_VERSION_TURF_V2 = "lgbm-turf-v2-features"
MODEL_VERSION_DIRT_V2 = "lgbm-dirt-v2-features"
MODEL_VERSION_V3 = "lgbm-v3-history"
MODEL_VERSION_TURF_V3 = "lgbm-turf-v3-history"
MODEL_VERSION_DIRT_V3 = "lgbm-dirt-v3-history"
MODEL_VERSION_V4 = "lgbm-v4-lap-history"
MODEL_VERSION_TURF_V4 = "lgbm-turf-v4-lap-history"
MODEL_VERSION_DIRT_V4 = "lgbm-dirt-v4-lap-history"
MODEL_VERSION_DIRT_V5 = "lgbm-dirt-v5-lap-history"
MODEL_VERSION_V5_FEATURES = "lgbm-v5-month"
MODEL_VERSION_TURF_V5_FEATURES = "lgbm-turf-v5-month"
MODEL_VERSION_DIRT_V5_FEATURES = "lgbm-dirt-v5-month"

# Path(__file__) = src/pci/infrastructure/pace/lgbm_forecaster.py
# .parent × 5   = apps/api/
_MODELS_DIR = Path(__file__).parent.parent.parent.parent.parent / "models"
_DEFAULT_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_v1.txt"
_DEFAULT_TURF_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_turf_v1.txt"
_DEFAULT_DIRT_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_dirt_v4.txt"

_CONFIDENCE_MIN = 0.4
_CONFIDENCE_MAX = 0.9

# 特徴量名（学習スクリプトと inference で順序を完全に一致させること）
FEATURE_NAMES = [
    "distance_m",    # 距離（m）
    "is_dirt",       # ダート=1, 芝=0
    "jyo_cd",        # 競馬場コード（整数 1〜10、不明=0）
    "escape_count",  # 逃げ馬頭数
    "front_ratio",   # 逃先行比率 (ESCAPE+FRONT) / n
    "closer_ratio",  # 差追比率 (STALKER+CLOSER) / n
    "style_balance", # 差追比率 - 逃先行比率
    "track_cond",    # 馬場状態（良=0, 稍重=1, 重=2, 不良=3）
]

FEATURE_NAMES_V2 = FEATURE_NAMES + [
    "field_size",          # 出走頭数
    "escape_ratio",        # 逃げ馬比率
    "front_count",         # 逃げ・先行馬頭数
    "flexible_ratio",      # 自在馬比率
    "escape_competition",  # 2頭目以降の逃げ競合比率
    "distance_short",      # 1400m以下
    "distance_mile",       # 1401〜1800m
    "distance_middle",     # 1801〜2200m
    "distance_long",       # 2201m以上
    *(f"venue_{code:02d}" for code in range(1, 11)),
]

FEATURE_NAMES_V3 = FEATURE_NAMES_V2 + [
    "history_front_horses",   # 前付け履歴を持つ馬の頭数
    "history_front_samples",  # 前付け履歴の総レース数
    "history_front_avg_pci",  # 馬単位で平均した前付け時PCI
    "history_front_min_pci",  # 最も速い流れを作った馬の平均PCI
    "history_front_spread",   # 馬ごとの平均PCIの幅
    "history_front_coverage", # 全出走馬に対する履歴保有率
]

FEATURE_NAMES_V4 = FEATURE_NAMES_V3 + [
    "history_lap_horses",    # 前後半3F履歴を持つ馬の頭数
    "history_lap_samples",   # 前後半3F履歴の総レース数
    "history_lap_avg_delta", # 馬単位で平均した後半3F－前半3F
    "history_lap_min_delta", # 最も前傾傾向が強い馬の平均差
    "history_lap_spread",    # 馬ごとの平均差の幅
    "history_lap_coverage",  # 全出走馬に対する履歴保有率
]

FEATURE_NAMES_V5 = FEATURE_NAMES_V4 + [
    *(f"month_{month:02d}" for month in range(1, 13)),
]

_FRONT_STYLES = (RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT)
_CLOSER_STYLES = (RunningStyleLabel.STALKER, RunningStyleLabel.CLOSER)
_CONDITION_ORD: dict[str, int] = {"良": 0, "稍重": 1, "重": 2, "不良": 3}
# 下限は学習ラベルの下限（train_rpci_lgbm.py の --rpci-min 既定）に合わせる。
# 旧値35.0は ratio 由来の rpci_actual（平均が高い）時代のもので、レースラップ由来へ
# 統一した後のダート実分布（平均41.9・最小20.9）に対して高すぎ、2026-06以降の
# ダート予測の29.6〜44.0%を切り捨てて系統バイアス+2.5の大半を作っていた。
# 実測: v5でバイアス+2.508→+0.012 / MAE 3.835→2.356、芝は張り付きゼロで影響なし。
_RPCI_MIN = 20.0
_RPCI_MAX = 65.0
# 本番の安全弁。較正を実測する CLI から参照するため公開している。
DEFAULT_RPCI_CLAMP: tuple[float, float] = (_RPCI_MIN, _RPCI_MAX)
_logger = logging.getLogger(__name__)


def _load_lgb_booster(model_path: str | Path) -> Any:
    """改行をLFへ正規化してlightgbm.Boosterをロードする。"""
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError(
            "LightGBMRpciForecaster には lightgbm が必要です: pip install lightgbm"
        ) from exc
    path = Path(model_path)
    raw_model = path.read_bytes()
    if b"\r\n" in raw_model:
        _logger.warning(
            "LightGBMモデルのCRLF改行をLFへ補正して読み込みます: %s", path
        )
    model_text = raw_model.decode("utf-8").replace("\r\n", "\n")
    return lgb.Booster(model_str=model_text)


def _model_version_from_provenance(model_path: str | Path, fallback: str) -> str:
    """学習来歴に記録された世代を返し、旧モデルは特徴量世代へフォールバックする。"""
    meta_path = Path(model_path).with_suffix(Path(model_path).suffix + ".meta.json")
    if not meta_path.exists():
        return fallback
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("RPCIモデルの学習来歴を読み込めません: %s", exc)
        return fallback
    if not isinstance(payload, dict):
        _logger.warning("RPCIモデルの学習来歴がJSONオブジェクトではありません: %s", meta_path)
        return fallback
    version = payload.get("model_version")
    return version if isinstance(version, str) and version else fallback


def _make_forecast(
    predict_fn: Any,
    context: RaceContext,
    version: str,
    feature_names: list[str] = FEATURE_NAMES,
    clamp: tuple[float, float] = (_RPCI_MIN, _RPCI_MAX),
) -> RpciForecast:
    """特徴量ベクトルを渡して予測値・ラベル・reasons を組み立てる共通処理。"""
    styles = context.running_styles
    n = len(styles)
    if n == 0:
        raise ValueError("出走馬の脚質情報がありません。想定 RPCI を予測できません。")

    features = build_features(context, feature_names)
    raw = float(predict_fn([features])[0])
    lower, upper = clamp
    rpci = round(min(max(raw, lower), upper), 1)
    label = classify_pace(rpci, context.track_type)
    confidence = _classification_margin_confidence(rpci, context.track_type)

    escape = sum(1 for s in styles if s == RunningStyleLabel.ESCAPE)
    front = sum(1 for s in styles if s in _FRONT_STYLES)
    closer = sum(1 for s in styles if s in _CLOSER_STYLES)

    reasons: list[Reason] = [
        Reason(
            code="lgbm_features",
            description=(
                f"LightGBM({version}): {context.distance_m}m"
                f" / {context.track_type}"
                f" / 逃{escape}頭 / 前{front/n:.0%} 後{closer/n:.0%}"
                f" / 馬場「{context.track_condition or '良'}」"
            ),
        ),
        Reason(
            code="forecast",
            description=f"想定RPCI={rpci} → 展開「{label}」（ML予測）",
        ),
        Reason(
            code=CLASSIFICATION_MARGIN_REASON_CODE,
            description="展開区分の境界からの余裕を、予想の読みやすさとして評価",
        ),
    ]

    return RpciForecast(
        value=rpci,
        label=label,
        confidence=confidence,
        model_version=version,
        reasons=tuple(reasons),
    )


class LightGBMRpciForecaster:
    """統合 LightGBM モデル（芝/ダート共用）による想定 RPCI 予測器。

    rpci_lgbm_v1.txt が存在する場合に使用する後方互換クラス。
    芝/ダート別モデルは SplitLightGBMRpciForecaster を使うこと。
    """

    def __init__(
        self,
        model_path: str | Path,
        clamp: tuple[float, float] = (_RPCI_MIN, _RPCI_MAX),
    ) -> None:
        booster = _load_lgb_booster(model_path)
        self._predict = booster.predict
        self._clamp = clamp
        self._feature_names = _feature_names_for_booster(booster)
        fallback_version = _version_for_feature_names(
            self._feature_names,
            MODEL_VERSION,
            MODEL_VERSION_V2,
            MODEL_VERSION_V3,
            MODEL_VERSION_V4,
            MODEL_VERSION_V5_FEATURES,
        )
        self._model_version = _model_version_from_provenance(model_path, fallback_version)

    def forecast(self, context: RaceContext) -> RpciForecast:
        feature_names = getattr(self, "_feature_names", FEATURE_NAMES)
        return _make_forecast(
            self._predict,
            context,
            getattr(
                self,
                "_model_version",
                _version_for_feature_names(
                    feature_names,
                    MODEL_VERSION,
                    MODEL_VERSION_V2,
                    MODEL_VERSION_V3,
                    MODEL_VERSION_V4,
                    MODEL_VERSION_V5_FEATURES,
                ),
            ),
            feature_names,
            getattr(self, "_clamp", (_RPCI_MIN, _RPCI_MAX)),
        )


class SplitLightGBMRpciForecaster:
    """芝・ダート別 LightGBM モデルによる想定 RPCI 予測器。

    コース種別ごとに専用モデルをロードして予測することで、
    共通モデルよりも芝/ダート各固有のパターンを学習できる。
    """

    def __init__(
        self,
        turf_model_path: str | Path,
        dirt_model_path: str | Path,
        clamp: tuple[float, float] = (_RPCI_MIN, _RPCI_MAX),
    ) -> None:
        turf_booster = _load_lgb_booster(turf_model_path)
        dirt_booster = _load_lgb_booster(dirt_model_path)
        self._turf_predict = turf_booster.predict
        self._dirt_predict = dirt_booster.predict
        self._clamp = clamp
        self._turf_feature_names = _feature_names_for_booster(turf_booster)
        self._dirt_feature_names = _feature_names_for_booster(dirt_booster)
        self._turf_model_version = _model_version_from_provenance(
            turf_model_path,
            _version_for_feature_names(
                self._turf_feature_names,
                MODEL_VERSION_TURF,
                MODEL_VERSION_TURF_V2,
                MODEL_VERSION_TURF_V3,
                MODEL_VERSION_TURF_V4,
                MODEL_VERSION_TURF_V5_FEATURES,
            ),
        )
        self._dirt_model_version = _model_version_from_provenance(
            dirt_model_path,
            _version_for_feature_names(
                self._dirt_feature_names,
                MODEL_VERSION_DIRT,
                MODEL_VERSION_DIRT_V2,
                MODEL_VERSION_DIRT_V3,
                MODEL_VERSION_DIRT_V4,
                MODEL_VERSION_DIRT_V5_FEATURES,
            ),
        )

    def forecast(self, context: RaceContext) -> RpciForecast:
        if context.track_type == "ダート":
            feature_names = getattr(self, "_dirt_feature_names", FEATURE_NAMES)
            return _make_forecast(
                self._dirt_predict,
                context,
                getattr(
                    self,
                    "_dirt_model_version",
                    _version_for_feature_names(
                        feature_names,
                        MODEL_VERSION_DIRT,
                        MODEL_VERSION_DIRT_V2,
                        MODEL_VERSION_DIRT_V3,
                        MODEL_VERSION_DIRT_V4,
                        MODEL_VERSION_DIRT_V5_FEATURES,
                    ),
                ),
                feature_names,
                getattr(self, "_clamp", (_RPCI_MIN, _RPCI_MAX)),
            )
        feature_names = getattr(self, "_turf_feature_names", FEATURE_NAMES)
        return _make_forecast(
            self._turf_predict,
            context,
            getattr(
                self,
                "_turf_model_version",
                _version_for_feature_names(
                    feature_names,
                    MODEL_VERSION_TURF,
                    MODEL_VERSION_TURF_V2,
                    MODEL_VERSION_TURF_V3,
                    MODEL_VERSION_TURF_V4,
                    MODEL_VERSION_TURF_V5_FEATURES,
                ),
            ),
            feature_names,
            getattr(self, "_clamp", (_RPCI_MIN, _RPCI_MAX)),
        )


def _feature_names_for_booster(booster: Any) -> list[str]:
    """モデルの特徴量数から互換性のある特徴量定義を選択する。"""
    feature_count = int(booster.num_feature())
    if feature_count == len(FEATURE_NAMES):
        return FEATURE_NAMES
    if feature_count == len(FEATURE_NAMES_V2):
        return FEATURE_NAMES_V2
    if feature_count == len(FEATURE_NAMES_V3):
        return FEATURE_NAMES_V3
    if feature_count == len(FEATURE_NAMES_V4):
        return FEATURE_NAMES_V4
    if feature_count == len(FEATURE_NAMES_V5):
        return FEATURE_NAMES_V5
    raise ValueError(
        f"未対応のRPCIモデル特徴量数です: {feature_count} "
        f"（対応: {len(FEATURE_NAMES)}, {len(FEATURE_NAMES_V2)}, "
        f"{len(FEATURE_NAMES_V3)}, {len(FEATURE_NAMES_V4)}, "
        f"{len(FEATURE_NAMES_V5)}）"
    )


def _classification_margin_confidence(rpci: float, track_type: str) -> float:
    """展開区分の境界からの距離を、表示用の読みやすさへ変換する。

    的中確率の校正値ではない。区分境界では低く、平均区分の中央または
    外側区分で境界から十分離れた予測ほど高くする。
    """
    if track_type == "ダート":
        high = DEFAULT_WEIGHTS.dirt_high_threshold
        slow = DEFAULT_WEIGHTS.dirt_slow_threshold
    else:
        high = DEFAULT_WEIGHTS.high_threshold
        slow = DEFAULT_WEIGHTS.slow_threshold

    half_band = (slow - high) / 2
    if high <= rpci <= slow:
        boundary_margin = min(rpci - high, slow - rpci)
    else:
        boundary_margin = min(abs(rpci - high), abs(rpci - slow))

    normalized_margin = min(max(boundary_margin / half_band, 0.0), 1.0)
    confidence = _CONFIDENCE_MIN + normalized_margin * (
        _CONFIDENCE_MAX - _CONFIDENCE_MIN
    )
    return round(confidence, 2)


def _version_for_feature_names(
    feature_names: list[str],
    v1_version: str,
    v2_version: str,
    v3_version: str,
    v4_version: str,
    v5_version: str,
) -> str:
    """特徴量世代に対応するモデルバージョンを返す。"""
    if feature_names == FEATURE_NAMES_V5:
        return v5_version
    if feature_names == FEATURE_NAMES_V4:
        return v4_version
    if feature_names == FEATURE_NAMES_V3:
        return v3_version
    if feature_names == FEATURE_NAMES_V2:
        return v2_version
    return v1_version


def load_best_forecaster(
    model_path: Path | None = None,
    turf_model_path: Path | None = None,
    dirt_model_path: Path | None = None,
    clamp: tuple[float, float] = (_RPCI_MIN, _RPCI_MAX),
) -> RpciForecaster:
    """モデルファイルの有無に応じて最良の予測器を返す共通ファクトリ。

    優先順位:
      1. turf + dirt 別モデル両方あり → SplitLightGBMRpciForecaster (lgbm-turf-v1 / lgbm-dirt-v1)
      2. 統合モデルあり               → LightGBMRpciForecaster (lgbm-v1, 後方互換)
      3. いずれも無し                 → RuleBasedRpciForecaster (rule-v4)

    clamp は予測値の安全弁。既定は本番値で、較正の実測時だけ呼び出し側が広げる。
    """
    from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster

    turf_path = turf_model_path or _DEFAULT_TURF_MODEL_PATH
    dirt_path = dirt_model_path or _DEFAULT_DIRT_MODEL_PATH
    if turf_path.exists() and dirt_path.exists():
        try:
            forecaster: RpciForecaster = SplitLightGBMRpciForecaster(
                turf_path, dirt_path, clamp
            )
            return forecaster
        except Exception as exc:
            _logger.warning(
                "芝・ダート別LightGBMモデルを読み込めません。統合モデルへ切り替えます: %s",
                exc,
            )

    unified_path = model_path or _DEFAULT_MODEL_PATH
    if unified_path.exists():
        try:
            forecaster = LightGBMRpciForecaster(unified_path, clamp)
            return forecaster
        except Exception as exc:
            _logger.warning(
                "統合LightGBMモデルを読み込めません。ルールベースへ切り替えます: %s",
                exc,
            )

    return RuleBasedRpciForecaster()


def build_features(
    context: RaceContext,
    feature_names: list[str] = FEATURE_NAMES,
) -> list[float]:
    """RaceContext を指定した特徴量定義順のリストへ変換する。

    学習スクリプト（train_rpci_lgbm.py）と同じ特徴量・同じ順序を維持すること。
    """
    styles = context.running_styles
    n = len(styles)
    escape = sum(1 for s in styles if s == RunningStyleLabel.ESCAPE)
    front = sum(1 for s in styles if s in _FRONT_STYLES)
    closer = sum(1 for s in styles if s in _CLOSER_STYLES)
    flexible = sum(1 for s in styles if s == RunningStyleLabel.FLEXIBLE)

    try:
        jyo_cd = int(context.venue_code) if context.venue_code else 0
    except ValueError:
        jyo_cd = 0

    track_cond = _CONDITION_ORD.get(context.track_condition or "良", 0)

    base = [
        float(context.distance_m),
        1.0 if context.track_type == "ダート" else 0.0,
        float(jyo_cd),
        float(escape),
        float(front) / n,
        float(closer) / n,
        float(closer - front) / n,
        float(track_cond),
    ]
    if feature_names == FEATURE_NAMES:
        return base
    if feature_names not in (
        FEATURE_NAMES_V2,
        FEATURE_NAMES_V3,
        FEATURE_NAMES_V4,
        FEATURE_NAMES_V5,
    ):
        raise ValueError(f"未対応のRPCI特徴量定義です: {len(feature_names)}")

    distance = context.distance_m
    venue_one_hot = [1.0 if jyo_cd == code else 0.0 for code in range(1, 11)]
    v2 = base + [
        float(n),
        float(escape) / n,
        float(front),
        float(flexible) / n,
        float(max(escape - 1, 0)) / n,
        1.0 if distance <= 1400 else 0.0,
        1.0 if 1400 < distance <= 1800 else 0.0,
        1.0 if 1800 < distance <= 2200 else 0.0,
        1.0 if distance > 2200 else 0.0,
        *venue_one_hot,
    ]
    if feature_names == FEATURE_NAMES_V2:
        return v2

    history = [sample for sample in context.field_front_pace_samples if sample.sample_size > 0]
    history_horses = len(history)
    history_samples = sum(sample.sample_size for sample in history)
    history_paces = [sample.avg_pci for sample in history]
    history_avg = sum(history_paces) / history_horses if history_horses else 0.0
    history_min = min(history_paces, default=0.0)
    history_spread = max(history_paces, default=0.0) - history_min
    v3 = v2 + [
        float(history_horses),
        float(history_samples),
        float(history_avg),
        float(history_min),
        float(history_spread),
        float(history_horses) / n,
    ]
    if feature_names == FEATURE_NAMES_V3:
        return v3

    lap_history = [
        sample for sample in context.historical_lap_samples if sample.sample_size > 0
    ]
    lap_horses = len(lap_history)
    lap_samples = sum(sample.sample_size for sample in lap_history)
    lap_deltas = [sample.avg_lap_delta for sample in lap_history]
    lap_avg = sum(lap_deltas) / lap_horses if lap_horses else 0.0
    lap_min = min(lap_deltas, default=0.0)
    lap_spread = max(lap_deltas, default=0.0) - lap_min
    v4 = v3 + [
        float(lap_horses),
        float(lap_samples),
        float(lap_avg),
        float(lap_min),
        float(lap_spread),
        float(lap_horses) / n,
    ]
    if feature_names == FEATURE_NAMES_V4:
        return v4

    month = context.race_month if context.race_month in range(1, 13) else None
    return v4 + [1.0 if month == value else 0.0 for value in range(1, 13)]
