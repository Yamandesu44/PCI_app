"""LightGBM RPCI 予測モデルの学習スクリプト。

確定済みレースを訓練データとして LightGBM 回帰モデルを学習し保存する。

使い方（Windows）:
    cd C:\\Users\\yuuta\\PCI_app\\apps\\api

    # 芝専用モデル（推奨）
    python -m scripts.train_rpci_lgbm --track-type turf

    # ダート専用モデル（推奨）
    python -m scripts.train_rpci_lgbm --track-type dirt

    # 統合モデル（後方互換）
    python -m scripts.train_rpci_lgbm --track-type all --output models/rpci_lgbm_v1.txt

    python -m scripts.train_rpci_lgbm --track-type turf --limit 5000 --early-stopping 50

特徴量 (FEATURE_NAMES 参照, lgbm_forecaster.py と一致):
    distance_m, is_dirt, jyo_cd, escape_count,
    front_ratio, closer_ratio, style_balance, track_cond

学習後に 20% テスト分割で MAE / RMSE / バイアスを表示する。
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")

try:
    import lightgbm as lgb  # type: ignore[import-untyped]
except ImportError:
    print("エラー: lightgbm が未インストールです。pip install lightgbm を実行してください。")
    sys.exit(1)

from sqlalchemy import text

from pci.config.settings import get_settings
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.pace.lgbm_forecaster import FEATURE_NAMES

# ── DB クエリ（FEATURE_NAMES と同じ順序で SELECT する）────────────────────
# :track_filter は "" (全件) or "AND r.track_type = '芝'" / "AND r.track_type = 'ダート'"
# SQLAlchemy text() では動的な条件を bindparam で渡せないため文字列結合で差し込む。
# 値はコード内部で生成するため SQL インジェクションのリスクはない。
_QUERY_TEMPLATE = """\
    SELECT
        r.distance_m                                                    AS distance_m,
        CASE WHEN r.track_type = 'ダート' THEN 1.0 ELSE 0.0 END        AS is_dirt,
        CASE
            WHEN r.jyo_cd ~ '^[0-9]+$' THEN r.jyo_cd::int
            ELSE 0
        END                                                             AS jyo_cd,
        SUM(CASE WHEN e.running_style = '逃' THEN 1 ELSE 0 END)        AS escape_count,
        SUM(CASE WHEN e.running_style IN ('逃','先') THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                             AS front_ratio,
        SUM(CASE WHEN e.running_style IN ('差','追') THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                             AS closer_ratio,
        (
            SUM(CASE WHEN e.running_style IN ('差','追') THEN 1 ELSE 0 END)
          - SUM(CASE WHEN e.running_style IN ('逃','先') THEN 1 ELSE 0 END)
        )::float / NULLIF(COUNT(e.horse_no), 0)                        AS style_balance,
        CASE r.track_condition
            WHEN '稍重' THEN 1
            WHEN '重'   THEN 2
            WHEN '不良' THEN 3
            ELSE 0
        END                                                             AS track_cond,
        r.rpci_actual                                                   AS target
    FROM races r
    JOIN race_entries e ON e.race_key = r.race_key
    WHERE r.status = 'result'
      AND r.rpci_actual IS NOT NULL
      AND r.rpci_actual BETWEEN :lo AND :hi
      AND e.running_style IS NOT NULL
      {track_filter}
    GROUP BY r.race_key,
             r.distance_m, r.track_type, r.jyo_cd, r.track_condition, r.rpci_actual
    HAVING COUNT(e.horse_no) > 0
    ORDER BY r.race_date DESC
    LIMIT :lim
"""

_TRACK_FILTER: dict[str, str] = {
    "turf": "AND r.track_type = '芝'",
    "dirt": "AND r.track_type = 'ダート'",
    "all": "",
}

# ダートはデータ数が少ないため過学習を抑制する小さめのパラメータを使う
_PARAMS_BY_TRACK: dict[str, dict[str, object]] = {
    "turf": {
        "objective": "regression",
        "metric": "mae",
        "num_leaves": 63,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": 42,
    },
    "dirt": {
        "objective": "regression",
        "metric": "mae",
        "num_leaves": 31,   # ダートはデータ少ないので小モデル
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "min_child_samples": 10,
        "verbose": -1,
        "seed": 42,
    },
    "all": {
        "objective": "regression",
        "metric": "mae",
        "num_leaves": 63,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": 42,
    },
}


_DEFAULT_OUTPUT: dict[str, str] = {
    "turf": "models/rpci_lgbm_turf_v1.txt",
    "dirt": "models/rpci_lgbm_dirt_v1.txt",
    "all":  "models/rpci_lgbm_v1.txt",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LightGBM RPCI 予測モデルの学習")
    p.add_argument(
        "--track-type",
        choices=["turf", "dirt", "all"],
        default="all",
        help="学習対象コース種別: turf=芝専用, dirt=ダート専用, all=統合（default: all）",
    )
    p.add_argument(
        "--output",
        default=None,
        help="モデル保存先（省略時は --track-type に応じて自動決定）",
    )
    p.add_argument(
        "--limit", type=int, default=20000, help="学習データの上限件数（default: 20000）"
    )
    p.add_argument("--rpci-min", type=float, default=20.0, help="target の下限フィルター")
    p.add_argument("--rpci-max", type=float, default=90.0, help="target の上限フィルター")
    p.add_argument(
        "--early-stopping",
        type=int,
        default=50,
        help="early stopping ラウンド数（default: 50）",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    track_type: str = args.track_type
    output = Path(args.output if args.output else _DEFAULT_OUTPUT[track_type])

    label_map = {"turf": "芝", "dirt": "ダート", "all": "全コース"}
    print(f"学習対象: {label_map[track_type]} / 上限 {args.limit:,} 件")

    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    track_filter = _TRACK_FILTER[track_type]
    query_sql = text(_QUERY_TEMPLATE.format(track_filter=track_filter))

    print("DB からデータ取得中…")
    rows = list(
        session.execute(
            query_sql, {"lo": args.rpci_min, "hi": args.rpci_max, "lim": args.limit}
        ).fetchall()
    )
    if not rows:
        print("学習データが見つかりません。DB の状態を確認してください。")
        return

    print(f"取得: {len(rows):,} レース")

    # 特徴量と目的変数を numpy 配列に変換（LightGBM 4.x は ndarray 必須）
    x_np = np.array(
        [[float(v) if v is not None else 0.0 for v in row[:-1]] for row in rows],
        dtype=np.float64,
    )
    y_np = np.array([float(row[-1]) for row in rows], dtype=np.float64)

    # 80/20 分割（時系列順のため先頭を訓練、後続をテストとしない）
    # ランダムシャッフルなし → 直近 20% をテストに使う（将来データ漏洩に注意）
    split = int(len(x_np) * 0.8)
    x_train, x_test = x_np[:split], x_np[split:]
    y_train, y_test = y_np[:split], y_np[split:]

    print(f"訓練: {len(x_train):,} / テスト: {len(x_test):,}")

    params = _PARAMS_BY_TRACK[track_type]

    lgb_train = lgb.Dataset(x_train, label=y_train, feature_name=FEATURE_NAMES)
    lgb_val = lgb.Dataset(x_test, label=y_test, reference=lgb_train)

    print("\nLightGBM 学習中…")
    callbacks = [lgb.early_stopping(args.early_stopping, verbose=False), lgb.log_evaluation(50)]
    model = lgb.train(
        params,
        lgb_train,
        num_boost_round=500,
        valid_sets=[lgb_val],
        callbacks=callbacks,
    )

    # ── テストセット評価 ──────────────────────────────────────────────
    preds = model.predict(x_test)
    n = len(y_test)
    mae = sum(abs(p - a) for p, a in zip(preds, y_test, strict=False)) / n
    bias = sum(p - a for p, a in zip(preds, y_test, strict=False)) / n
    rmse = math.sqrt(sum((p - a) ** 2 for p, a in zip(preds, y_test, strict=False)) / n)

    print(f"\n■ テストセット精度（直近 20% / {label_map[track_type]}）")
    print(f"  MAE  : {mae:.3f}")
    print(f"  RMSE : {rmse:.3f}")
    print(f"  バイアス: {bias:+.3f}")

    print("\n■ 特徴量重要度 (gain)")
    imp = model.feature_importance(importance_type="gain")
    for name, score in sorted(zip(FEATURE_NAMES, imp, strict=True), key=lambda x: -x[1]):
        print(f"  {name:20s}: {score:10.1f}")

    # ── モデル保存 ───────────────────────────────────────────────────
    output.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output))
    print(f"\nモデルを保存しました: {output.resolve()}")
    print(
        "次のステップ: 芝・ダート両方の学習が完了したら\n"
        "  git add models/rpci_lgbm_turf_v1.txt models/rpci_lgbm_dirt_v1.txt\n"
        "  git commit -m 'feat: 芝/ダート別 LightGBM モデル追加'\n"
        "  python -m scripts.backtest_forecast で精度を検証してください。"
    )


if __name__ == "__main__":
    main()
