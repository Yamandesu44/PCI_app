"""LightGBM 実装の想定 RPCI 予測器（ADR-0005: ML 疎結合 IF）。

RpciForecaster プロトコルを満たし、ForecastRaceUseCase に DI で注入される。
モデルファイル（apps/api/models/rpci_lgbm_v1.txt）が存在する場合に使用可能。
モデルが存在しない場合、dependencies.py が RuleBasedRpciForecaster へフォールバックする。
"""

from __future__ import annotations

from pathlib import Path

from pci.domain.pace.rpci_forecast import (
    RaceContext,
    RpciForecast,
    RpciForecaster,
    classify_pace,
)
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "lgbm-v1"

# apps/api/models/rpci_lgbm_v1.txt
# Path(__file__) = src/pci/infrastructure/pace/lgbm_forecaster.py
# .parent × 5   = apps/api/
_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent.parent.parent.parent / "models" / "rpci_lgbm_v1.txt"
)

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


class LightGBMRpciForecaster:
    """LightGBM 回帰による想定 RPCI 予測器。

    説明可能性のため各特徴量の値を reasons に含める。
    confidence は固定値 0.75（将来はブートストラップ不確実性で計算）。
    """

    def __init__(self, model_path: str | Path) -> None:
        try:
            import lightgbm as lgb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "LightGBMRpciForecaster には lightgbm が必要です: pip install lightgbm"
            ) from exc
        booster: lgb.Booster = lgb.Booster(model_file=str(model_path))
        self._predict = booster.predict

    def forecast(self, context: RaceContext) -> RpciForecast:
        styles = context.running_styles
        n = len(styles)
        if n == 0:
            raise ValueError("出走馬の脚質情報がありません。想定 RPCI を予測できません。")

        features = build_features(context)
        raw = float(self._predict([features])[0])
        rpci = round(min(max(raw, _RPCI_MIN), _RPCI_MAX), 1)
        label = classify_pace(rpci, context.track_type)

        escape = sum(1 for s in styles if s == RunningStyleLabel.ESCAPE)
        front = sum(1 for s in styles if s in _FRONT_STYLES)
        closer = sum(1 for s in styles if s in _CLOSER_STYLES)

        reasons: list[Reason] = [
            Reason(
                code="lgbm_features",
                description=(
                    f"LightGBM({MODEL_VERSION}): {context.distance_m}m"
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
            model_version=MODEL_VERSION,
            reasons=tuple(reasons),
        )


def load_best_forecaster(model_path: Path | None = None) -> RpciForecaster:
    """モデルファイルの有無に応じて最良の予測器を返す共通ファクトリ。

    scripts/backtest_forecast.py や dependencies.py から呼ぶことで、
    モデルファイルが存在すれば lgbm-v1、なければ rule-v4 に自動切替する。
    """
    from pci.domain.pace.rpci_forecast import RuleBasedRpciForecaster

    path = model_path or _DEFAULT_MODEL_PATH
    if path.exists():
        try:
            forecaster: RpciForecaster = LightGBMRpciForecaster(path)
            return forecaster
        except Exception:
            pass
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
