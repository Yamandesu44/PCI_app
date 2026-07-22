"""LightGBM 実装の想定 RPCI 予測器（ADR-0005: ML 疎結合 IF）。

RpciForecaster プロトコルを満たし、ForecastRaceUseCase に DI で注入される。

モデル選択の優先順位（load_best_forecaster 参照）:
  1. rpci_lgbm_turf_v1.txt + rpci_lgbm_dirt_v1.txt 両方あり → SplitLightGBMRpciForecaster
  2. rpci_lgbm_v1.txt あり                               → LightGBMRpciForecaster（統合）
  3. いずれも無し                                         → RuleBasedRpciForecaster（後退）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pci.domain.pace.rpci_forecast import (
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

# Path(__file__) = src/pci/infrastructure/pace/lgbm_forecaster.py
# .parent × 5   = apps/api/
_MODELS_DIR = Path(__file__).parent.parent.parent.parent.parent / "models"
_DEFAULT_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_v1.txt"
_DEFAULT_TURF_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_turf_v1.txt"
_DEFAULT_DIRT_MODEL_PATH = _MODELS_DIR / "rpci_lgbm_dirt_v1.txt"

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

_FRONT_STYLES = (RunningStyleLabel.ESCAPE, RunningStyleLabel.FRONT)
_CLOSER_STYLES = (RunningStyleLabel.STALKER, RunningStyleLabel.CLOSER)
_CONDITION_ORD: dict[str, int] = {"良": 0, "稍重": 1, "重": 2, "不良": 3}
_RPCI_MIN = 35.0
_RPCI_MAX = 65.0
_logger = logging.getLogger(__name__)


def _load_lgb_booster(model_path: str | Path) -> Any:
    """改行をLFへ正規化してlightgbm.Boosterをロードする。"""
    try:
        import lightgbm as lgb  # type: ignore[import-not-found]
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


def _make_forecast(
    predict_fn: Any,
    context: RaceContext,
    version: str,
) -> RpciForecast:
    """特徴量ベクトルを渡して予測値・ラベル・reasons を組み立てる共通処理。"""
    styles = context.running_styles
    n = len(styles)
    if n == 0:
        raise ValueError("出走馬の脚質情報がありません。想定 RPCI を予測できません。")

    features = build_features(context)
    raw = float(predict_fn([features])[0])
    rpci = round(min(max(raw, _RPCI_MIN), _RPCI_MAX), 1)
    label = classify_pace(rpci, context.track_type)

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
    ]

    return RpciForecast(
        value=rpci,
        label=label,
        confidence=0.75,
        model_version=version,
        reasons=tuple(reasons),
    )


class LightGBMRpciForecaster:
    """統合 LightGBM モデル（芝/ダート共用）による想定 RPCI 予測器。

    rpci_lgbm_v1.txt が存在する場合に使用する後方互換クラス。
    芝/ダート別モデルは SplitLightGBMRpciForecaster を使うこと。
    """

    def __init__(self, model_path: str | Path) -> None:
        booster = _load_lgb_booster(model_path)
        self._predict = booster.predict

    def forecast(self, context: RaceContext) -> RpciForecast:
        return _make_forecast(self._predict, context, MODEL_VERSION)


class SplitLightGBMRpciForecaster:
    """芝・ダート別 LightGBM モデルによる想定 RPCI 予測器。

    コース種別ごとに専用モデルをロードして予測することで、
    共通モデルよりも芝/ダート各固有のパターンを学習できる。
    """

    def __init__(
        self,
        turf_model_path: str | Path,
        dirt_model_path: str | Path,
    ) -> None:
        turf_booster = _load_lgb_booster(turf_model_path)
        dirt_booster = _load_lgb_booster(dirt_model_path)
        self._turf_predict = turf_booster.predict
        self._dirt_predict = dirt_booster.predict

    def forecast(self, context: RaceContext) -> RpciForecast:
        if context.track_type == "ダート":
            return _make_forecast(self._dirt_predict, context, MODEL_VERSION_DIRT)
        return _make_forecast(self._turf_predict, context, MODEL_VERSION_TURF)


def load_best_forecaster(
    model_path: Path | None = None,
    turf_model_path: Path | None = None,
    dirt_model_path: Path | None = None,
) -> RpciForecaster:
    """モデルファイルの有無に応じて最良の予測器を返す共通ファクトリ。

    優先順位:
      1. turf + dirt 別モデル両方あり → SplitLightGBMRpciForecaster (lgbm-turf-v1 / lgbm-dirt-v1)
      2. 統合モデルあり               → LightGBMRpciForecaster (lgbm-v1, 後方互換)
      3. いずれも無し                 → RuleBasedRpciForecaster (rule-v4)
    """
    from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster

    turf_path = turf_model_path or _DEFAULT_TURF_MODEL_PATH
    dirt_path = dirt_model_path or _DEFAULT_DIRT_MODEL_PATH
    if turf_path.exists() and dirt_path.exists():
        try:
            forecaster: RpciForecaster = SplitLightGBMRpciForecaster(turf_path, dirt_path)
            return forecaster
        except Exception as exc:
            _logger.warning(
                "芝・ダート別LightGBMモデルを読み込めません。統合モデルへ切り替えます: %s",
                exc,
            )

    unified_path = model_path or _DEFAULT_MODEL_PATH
    if unified_path.exists():
        try:
            forecaster = LightGBMRpciForecaster(unified_path)
            return forecaster
        except Exception as exc:
            _logger.warning(
                "統合LightGBMモデルを読み込めません。ルールベースへ切り替えます: %s",
                exc,
            )

    return RuleBasedRpciForecaster()


def build_features(context: RaceContext) -> list[float]:
    """RaceContext を FEATURE_NAMES 順の特徴量リストへ変換する。

    学習スクリプト（train_rpci_lgbm.py）と同じ特徴量・同じ順序を維持すること。
    """
    styles = context.running_styles
    n = len(styles)
    escape = sum(1 for s in styles if s == RunningStyleLabel.ESCAPE)
    front = sum(1 for s in styles if s in _FRONT_STYLES)
    closer = sum(1 for s in styles if s in _CLOSER_STYLES)

    try:
        jyo_cd = int(context.venue_code) if context.venue_code else 0
    except ValueError:
        jyo_cd = 0

    track_cond = _CONDITION_ORD.get(context.track_condition or "良", 0)

    return [
        float(context.distance_m),
        1.0 if context.track_type == "ダート" else 0.0,
        float(jyo_cd),
        float(escape),
        float(front) / n,
        float(closer) / n,
        float(closer - front) / n,
        float(track_cond),
    ]
