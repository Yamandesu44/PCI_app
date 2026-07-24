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

    # 少数の展開区分を穏やかに補正する検証用学習
    python -m scripts.train_rpci_lgbm --track-type dirt --label-balance sqrt-inverse \
        --output models/rpci_lgbm_dirt_balanced_candidate.txt

    # 頭数・逃げ競合・距離帯・競馬場を追加したv2特徴量候補
    python -m scripts.train_rpci_lgbm --track-type turf --feature-set v2 \
        --output models/rpci_lgbm_turf_v2_candidate.txt

特徴量 (FEATURE_NAMES / FEATURE_NAMES_V2 参照, lgbm_forecaster.py と一致):
    distance_m, is_dirt, jyo_cd, escape_count,
    front_ratio, closer_ratio, style_balance, track_cond

学習後に 20% テスト分割で MAE / RMSE / バイアスを表示する。
"""

from __future__ import annotations

import argparse
import datetime
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, "src")

from sqlalchemy import text

from pci.config.settings import get_settings
from pci.domain.pace.rpci_forecast import PaceLabel, classify_pace
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.pace.lgbm_forecaster import (
    FEATURE_NAMES,
    FEATURE_NAMES_V2,
    FEATURE_NAMES_V3,
    FEATURE_NAMES_V4,
)

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
        SUM(CASE WHEN e.running_style = '逃げ' THEN 1 ELSE 0 END)      AS escape_count,
        SUM(CASE WHEN e.running_style IN ('逃げ','先行') THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                             AS front_ratio,
        SUM(CASE WHEN e.running_style IN ('差し','追込') THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                             AS closer_ratio,
        (
            SUM(CASE WHEN e.running_style IN ('差し','追込') THEN 1 ELSE 0 END)
          - SUM(CASE WHEN e.running_style IN ('逃げ','先行') THEN 1 ELSE 0 END)
        )::float / NULLIF(COUNT(e.horse_no), 0)                        AS style_balance,
        CASE r.track_condition
            WHEN '稍重' THEN 1
            WHEN '重'   THEN 2
            WHEN '不良' THEN 3
            ELSE 0
        END                                                             AS track_cond,
        COUNT(e.horse_no)                                                AS field_size,
        SUM(CASE WHEN e.running_style = '逃げ' THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                              AS escape_ratio,
        SUM(CASE WHEN e.running_style IN ('逃げ','先行') THEN 1 ELSE 0 END)
                                                                        AS front_count,
        SUM(CASE WHEN e.running_style = '自在' THEN 1 ELSE 0 END)::float
            / NULLIF(COUNT(e.horse_no), 0)                              AS flexible_ratio,
        GREATEST(
            SUM(CASE WHEN e.running_style = '逃げ' THEN 1 ELSE 0 END) - 1,
            0
        )::float / NULLIF(COUNT(e.horse_no), 0)                         AS escape_competition,
        CASE WHEN r.distance_m <= 1400 THEN 1.0 ELSE 0.0 END            AS distance_short,
        CASE WHEN r.distance_m > 1400 AND r.distance_m <= 1800
             THEN 1.0 ELSE 0.0 END                                     AS distance_mile,
        CASE WHEN r.distance_m > 1800 AND r.distance_m <= 2200
             THEN 1.0 ELSE 0.0 END                                     AS distance_middle,
        CASE WHEN r.distance_m > 2200 THEN 1.0 ELSE 0.0 END             AS distance_long,
        CASE WHEN r.jyo_cd = '01' THEN 1.0 ELSE 0.0 END                 AS venue_01,
        CASE WHEN r.jyo_cd = '02' THEN 1.0 ELSE 0.0 END                 AS venue_02,
        CASE WHEN r.jyo_cd = '03' THEN 1.0 ELSE 0.0 END                 AS venue_03,
        CASE WHEN r.jyo_cd = '04' THEN 1.0 ELSE 0.0 END                 AS venue_04,
        CASE WHEN r.jyo_cd = '05' THEN 1.0 ELSE 0.0 END                 AS venue_05,
        CASE WHEN r.jyo_cd = '06' THEN 1.0 ELSE 0.0 END                 AS venue_06,
        CASE WHEN r.jyo_cd = '07' THEN 1.0 ELSE 0.0 END                 AS venue_07,
        CASE WHEN r.jyo_cd = '08' THEN 1.0 ELSE 0.0 END                 AS venue_08,
        CASE WHEN r.jyo_cd = '09' THEN 1.0 ELSE 0.0 END                 AS venue_09,
        CASE WHEN r.jyo_cd = '10' THEN 1.0 ELSE 0.0 END                 AS venue_10,
        {history_features}
        {lap_features}
        r.rpci_actual                                                   AS target
    FROM races r
    JOIN race_entries e ON e.race_key = r.race_key
    {history_join}
    {lap_join}
    WHERE r.status = 'result'
      AND r.rpci_actual IS NOT NULL
      AND r.rpci_actual BETWEEN :lo AND :hi
      AND e.running_style IS NOT NULL
      {track_filter}
      {date_filter}
    GROUP BY r.race_key,
             r.distance_m, r.track_type, r.jyo_cd, r.track_condition, r.rpci_actual
    HAVING COUNT(e.horse_no) > 0
    ORDER BY r.race_date DESC, r.race_key DESC
    LIMIT :lim
"""

_EMPTY_HISTORY_FEATURES = """\
        0.0 AS history_front_horses,
        0.0 AS history_front_samples,
        0.0 AS history_front_avg_pci,
        0.0 AS history_front_min_pci,
        0.0 AS history_front_spread,
        0.0 AS history_front_coverage,
"""

_HISTORY_FEATURES = """\
        COUNT(*) FILTER (WHERE hist.sample_size > 0)                    AS history_front_horses,
        COALESCE(SUM(hist.sample_size), 0)                              AS history_front_samples,
        COALESCE(AVG(hist.avg_pci) FILTER (WHERE hist.sample_size > 0), 0.0)
                                                                        AS history_front_avg_pci,
        COALESCE(MIN(hist.avg_pci) FILTER (WHERE hist.sample_size > 0), 0.0)
                                                                        AS history_front_min_pci,
        COALESCE(
            MAX(hist.avg_pci) FILTER (WHERE hist.sample_size > 0)
          - MIN(hist.avg_pci) FILTER (WHERE hist.sample_size > 0),
            0.0
        )                                                               AS history_front_spread,
        COUNT(*) FILTER (WHERE hist.sample_size > 0)::float
            / NULLIF(COUNT(e.horse_no), 0)                              AS history_front_coverage,
"""

_HISTORY_JOIN = """\
    LEFT JOIN LATERAL (
        SELECT
            AVG(prior.pace) AS avg_pci,
            COUNT(*)       AS sample_size
        FROM (
            SELECT COALESCE(pe.pci_actual, pr.rpci_actual) AS pace
            FROM race_entries pe
            JOIN races pr ON pr.race_key = pe.race_key
            WHERE pe.ketto_num = e.ketto_num
              AND pr.status = 'result'
              AND pr.race_date < r.race_date
              AND COALESCE(pe.corner_1, pe.corner_4) <= 2
              AND COALESCE(pe.pci_actual, pr.rpci_actual) IS NOT NULL
            ORDER BY pr.race_date DESC, pr.race_key DESC
            LIMIT 10
        ) prior
    ) hist ON TRUE
"""

_EMPTY_LAP_FEATURES = """\
        0.0 AS history_lap_horses,
        0.0 AS history_lap_samples,
        0.0 AS history_lap_avg_delta,
        0.0 AS history_lap_min_delta,
        0.0 AS history_lap_spread,
        0.0 AS history_lap_coverage,
"""

_LAP_FEATURES = """\
        COUNT(*) FILTER (WHERE lap_hist.sample_size > 0)                AS history_lap_horses,
        COALESCE(SUM(lap_hist.sample_size), 0)                          AS history_lap_samples,
        COALESCE(
            AVG(lap_hist.avg_lap_delta) FILTER (WHERE lap_hist.sample_size > 0),
            0.0
        )                                                               AS history_lap_avg_delta,
        COALESCE(
            MIN(lap_hist.avg_lap_delta) FILTER (WHERE lap_hist.sample_size > 0),
            0.0
        )                                                               AS history_lap_min_delta,
        COALESCE(
            MAX(lap_hist.avg_lap_delta) FILTER (WHERE lap_hist.sample_size > 0)
          - MIN(lap_hist.avg_lap_delta) FILTER (WHERE lap_hist.sample_size > 0),
            0.0
        )                                                               AS history_lap_spread,
        COUNT(*) FILTER (WHERE lap_hist.sample_size > 0)::float
            / NULLIF(COUNT(e.horse_no), 0)                              AS history_lap_coverage,
"""

_LAP_JOIN = """\
    LEFT JOIN LATERAL (
        SELECT
            AVG(prior.lap_delta) AS avg_lap_delta,
            COUNT(prior.lap_delta) AS sample_size
        FROM (
            SELECT pr.race_l3f - pr.race_s3f AS lap_delta
            FROM race_entries pe
            JOIN races pr ON pr.race_key = pe.race_key
            WHERE pe.ketto_num = e.ketto_num
              AND pr.status = 'result'
              AND pr.race_date < r.race_date
            ORDER BY pr.race_date DESC, pr.race_key DESC
            LIMIT 10
        ) prior
    ) lap_hist ON TRUE
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
    p.add_argument(
        "--before-date",
        type=datetime.date.fromisoformat,
        default=None,
        help="この日より前のレースだけで学習する YYYY-MM-DD（独立評価期間の分離用）",
    )
    p.add_argument("--rpci-min", type=float, default=20.0, help="target の下限フィルター")
    p.add_argument("--rpci-max", type=float, default=90.0, help="target の上限フィルター")
    p.add_argument(
        "--early-stopping",
        type=int,
        default=50,
        help="early stopping ラウンド数（default: 50）",
    )
    p.add_argument(
        "--label-balance",
        choices=["none", "sqrt-inverse", "inverse"],
        default="none",
        help=(
            "展開区分の学習重み。sqrt-inverseは穏やかな加重、inverseは"
            "区分ごとの総重みを均等化する（default: none）"
        ),
    )
    p.add_argument(
        "--feature-set",
        choices=["v1", "v2", "v3", "v4"],
        default="v1",
        help="特徴量定義。v4は対象日より前の前付けペース・前後半3F履歴も追加（default: v1）",
    )
    args = p.parse_args()
    if (args.label_balance != "none" or args.feature_set != "v1") and args.output is None:
        p.error(
            "検証用の学習設定を指定する場合は、本番モデルの上書きを防ぐため "
            "--output で候補モデルの保存先を指定してください"
        )
    return args


def main() -> None:
    try:
        import lightgbm as lgb
    except ImportError:
        print("エラー: lightgbm が未インストールです。pip install lightgbm を実行してください。")
        return

    args = _parse_args()
    track_type: str = args.track_type
    output = Path(args.output if args.output else _DEFAULT_OUTPUT[track_type])

    label_map = {"turf": "芝", "dirt": "ダート", "all": "全コース"}
    print(f"学習対象: {label_map[track_type]} / 上限 {args.limit:,} 件")

    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    track_filter = _TRACK_FILTER[track_type]
    date_filter = "AND r.race_date < :before_date" if args.before_date else ""
    uses_history = args.feature_set in {"v3", "v4"}
    uses_lap_history = args.feature_set == "v4"
    query_sql = text(
        _QUERY_TEMPLATE.format(
            track_filter=track_filter,
            date_filter=date_filter,
            history_features=(
                _HISTORY_FEATURES if uses_history else _EMPTY_HISTORY_FEATURES
            ),
            history_join=_HISTORY_JOIN if uses_history else "",
            lap_features=(
                _LAP_FEATURES if uses_lap_history else _EMPTY_LAP_FEATURES
            ),
            lap_join=_LAP_JOIN if uses_lap_history else "",
        )
    )

    print("DB からデータ取得中…")
    query_params: dict[str, object] = {
        "lo": args.rpci_min,
        "hi": args.rpci_max,
        "lim": args.limit,
    }
    if args.before_date is not None:
        query_params["before_date"] = args.before_date
    rows = list(session.execute(query_sql, query_params).fetchall())
    if not rows:
        print("学習データが見つかりません。DB の状態を確認してください。")
        return
    if len(rows) < 5:
        print("学習データが5レース未満です。期間または取り込み状況を確認してください。")
        return

    print(f"取得: {len(rows):,} レース")

    feature_names = {
        "v1": FEATURE_NAMES,
        "v2": FEATURE_NAMES_V2,
        "v3": FEATURE_NAMES_V3,
        "v4": FEATURE_NAMES_V4,
    }[args.feature_set]
    feature_count = len(feature_names)

    # 特徴量と目的変数を numpy 配列に変換（LightGBM 4.x は ndarray 必須）
    x_np = np.array(
        [
            [float(v) if v is not None else 0.0 for v in row[:feature_count]]
            for row in rows
        ],
        dtype=np.float64,
    )
    y_np = np.array([float(row[-1]) for row in rows], dtype=np.float64)

    # SQLは新しい順。直近20%を検証へ取り分け、残る古い80%だけで学習する。
    # LIMIT指定時も最新期間を保持しつつ、将来から過去を予測する漏洩を防ぐ。
    test_size = max(1, len(x_np) - int(len(x_np) * 0.8))
    x_test, x_train = x_np[:test_size], x_np[test_size:]
    y_test, y_train = y_np[:test_size], y_np[test_size:]

    print(f"訓練: {len(x_train):,} / テスト: {len(x_test):,}")

    params = _PARAMS_BY_TRACK[track_type]
    train_weights = _build_label_sample_weights(
        y_train,
        x_train,
        track_type,
        args.label_balance,
    )
    _print_label_balance(y_train, x_train, train_weights, track_type, args.label_balance)

    lgb_train = lgb.Dataset(
        x_train,
        label=y_train,
        weight=train_weights,
        feature_name=feature_names,
    )
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
    _print_label_recall(preds, y_test, x_test, track_type)

    print("\n■ 特徴量重要度 (gain)")
    imp = model.feature_importance(importance_type="gain")
    for name, score in sorted(zip(feature_names, imp, strict=True), key=lambda x: -x[1]):
        print(f"  {name:20s}: {score:10.1f}")

    # ── モデル保存 ───────────────────────────────────────────────────
    output.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output))
    print(f"\nモデルを保存しました: {output.resolve()}")
    if args.label_balance == "none":
        print(
            "次のステップ: 芝・ダート両方の学習が完了したら\n"
            "  python -m scripts.backtest_forecast で精度を検証してください。"
        )
    else:
        print(
            "候補モデルです。本番モデルへ置換せず、backtest_forecast.py の\n"
            "--turf-model-path / --dirt-model-path で独立検証してください。"
        )


def _print_label_recall(
    predictions: Any,
    actuals: Any,
    features: Any,
    configured_track_type: str,
) -> None:
    """検証セットの展開3分類再現率をコース種別ごとに表示する。"""
    grouped: dict[tuple[str, PaceLabel], list[bool]] = {}
    for prediction, actual, feature in zip(predictions, actuals, features, strict=True):
        track_type = (
            "ダート"
            if configured_track_type == "dirt"
            or (configured_track_type == "all" and float(feature[1]) == 1.0)
            else "芝"
        )
        actual_label = classify_pace(float(actual), track_type)
        predicted_label = classify_pace(float(prediction), track_type)
        grouped.setdefault((track_type, actual_label), []).append(
            predicted_label == actual_label
        )

    print("\n■ 展開3分類の再現率")
    for track_type in ("芝", "ダート"):
        for label in PaceLabel:
            hits = grouped.get((track_type, label), [])
            if hits:
                print(
                    f"  {track_type}「{label}」: "
                    f"{sum(hits) / len(hits):.1%} ({sum(hits)}/{len(hits)})"
                )


def _label_group(
    actual: float,
    feature: Any,
    configured_track_type: str,
) -> tuple[str, PaceLabel]:
    track_type = (
        "ダート"
        if configured_track_type == "dirt"
        or (configured_track_type == "all" and float(feature[1]) == 1.0)
        else "芝"
    )
    return track_type, classify_pace(float(actual), track_type)


def _build_label_sample_weights(
    actuals: Any,
    features: Any,
    configured_track_type: str,
    profile: str,
) -> np.ndarray:
    """展開区分の頻度から学習用サンプル重みを生成する。"""
    if profile == "none":
        return np.ones(len(actuals), dtype=np.float64)
    if profile not in {"sqrt-inverse", "inverse"}:
        raise ValueError(f"未対応のラベル重みプロファイルです: {profile}")

    groups = [
        _label_group(float(actual), feature, configured_track_type)
        for actual, feature in zip(actuals, features, strict=True)
    ]
    counts: dict[tuple[str, PaceLabel], int] = {}
    for group in groups:
        counts[group] = counts.get(group, 0) + 1

    if profile == "sqrt-inverse":
        raw = np.array(
            [1.0 / math.sqrt(counts[group]) for group in groups],
            dtype=np.float64,
        )
    else:
        raw = np.array([1.0 / counts[group] for group in groups], dtype=np.float64)
    return raw / float(raw.mean())


def _print_label_balance(
    actuals: Any,
    features: Any,
    weights: Any,
    configured_track_type: str,
    profile: str,
) -> None:
    """学習区分ごとの件数と適用重みを表示する。"""
    grouped: dict[tuple[str, PaceLabel], list[float]] = {}
    for actual, feature, weight in zip(actuals, features, weights, strict=True):
        group = _label_group(float(actual), feature, configured_track_type)
        grouped.setdefault(group, []).append(float(weight))

    print(f"\n■ 学習ラベル重み: {profile}")
    for track_type in ("芝", "ダート"):
        for label in PaceLabel:
            values = grouped.get((track_type, label), [])
            if values:
                print(
                    f"  {track_type}「{label}」: "
                    f"{len(values):,}件 / 重み {sum(values) / len(values):.3f}"
                )


if __name__ == "__main__":
    main()
