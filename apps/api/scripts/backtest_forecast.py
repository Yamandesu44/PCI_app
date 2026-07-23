"""想定RPCI / PAI のバックテストを実DBに対して実行する CLI。

確定済みレースを「予測時点」に巻き戻して ForecastRaceUseCase を再現し、
実績RPCI・好走と突き合わせて精度を出力する（評価ロジックは
pci.application.backtest に集約。本スクリプトは DB 配線と対象選定のみ）。

使い方:
    cd apps/api
    python -m scripts.backtest_forecast --limit 200
    python -m scripts.backtest_forecast --date-from 2024-01-01 --date-to 2024-12-31
    python -m scripts.backtest_forecast --limit 2000 --sample-every 5

    # 外れ値を除いた正常 rpci_actual のみで評価（データ品質診断後に使用）
    python -m scripts.backtest_forecast --limit 200 --rpci-min 20 --rpci-max 90

    # 結果をJSONに保存し、的中率の推移を後日比較できるようにする
    python -m scripts.backtest_forecast --limit 200 --output results/2026-07-12.json

    # 能力指数の重み候補を同じ対象レースで比較する
    python -m scripts.backtest_forecast --limit 200 --compare-ability-weights

    # ルールベース想定RPCIの重み候補を芝・ダート別にも比較する
    python -m scripts.backtest_forecast --limit 200 --compare-rule-weights

    # PAIの重み候補を芝・ダート別にも比較する
    python -m scripts.backtest_forecast --limit 200 --compare-pai-weights

    # ペース予測と脚質予測のどちらが脚質別有利度を悪化させるか切り分ける
    python -m scripts.backtest_forecast --track-type 芝 --diagnose-style-advantage

対象は status="result" かつ rpci_actual を持つレース。1レースの予測は
数百クエリを伴うため、既定は新しい順 200 レースに絞る（--limit で調整）。
lookahead は backtest 側でレース当日カットオフして防止する。

--track-type 未指定時は、混合集計に加えて芝/ダート別の内訳も自動で追加表示する。
混合のみだと PAI の point-biserial 相関が希釈されて見える落とし穴があるため
（docs/adr/0005-rpci-forecast-strategy.md §5.4）、常に track 別の数値も確認できるようにしている。

rpci_actual の有効範囲について:
    予測器の出力は [35, 65] にクランプされる。しかし取り込みバグや S3F/L3F
    バイト位置の誤読により rpci_actual に数百〜数千の異常値が混入する場合がある。
    --rpci-min / --rpci-max でこれらを除外すると、正常データでの精度が得られる。
    異常値の割合は scripts/diagnose_rpci.py で確認できる。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections.abc import Mapping

sys.path.insert(0, "src")

from sqlalchemy import select
from sqlalchemy.orm import Session

from pci.application.backtest import (
    DEFAULT_ABILITY_WEIGHT_PROFILES,
    DEFAULT_PAI_WEIGHT_PROFILES,
    DEFAULT_RULE_WEIGHT_PROFILES,
    AbilityWeightComparison,
    BacktestReport,
    ForecastBacktester,
    PaiWeightComparison,
    RuleWeightComparison,
    ability_weight_comparisons_to_dict,
    build_actual_style_advantage_breakdown,
    collect_actual_style_advantage_samples,
    compare_ability_weight_reports,
    compare_pai_weight_reports,
    compare_rule_weight_reports,
    format_ability_weight_comparison,
    format_actual_style_advantage_breakdown,
    format_actual_style_advantage_validation,
    format_pai_weight_comparison,
    format_report,
    format_rule_weight_comparison,
    format_style_advantage_attribution,
    group_races_by_track,
    pai_weight_comparisons_to_dict,
    report_to_dict,
    rule_weight_comparisons_to_dict,
    style_advantage_attribution_to_dict,
    style_advantage_breakdown_to_dict,
    style_advantage_lift_to_dict,
    summarize_style_advantage,
)
from pci.config.settings import get_settings
from pci.domain.pace.ability import AbilityScorer
from pci.domain.pace.adaptability import PaceAdaptabilityScorer
from pci.domain.pace.rpci_forecast import (
    RpciForecaster,
    RuleBasedRpciForecaster,
)
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import RaceModel
from pci.infrastructure.database.session import build_engine, build_session_maker
from pci.infrastructure.pace.lgbm_forecaster import load_best_forecaster
from pci.infrastructure.repositories.race_repository import SqlAlchemyRaceRepository


def _parse_date(value: str) -> datetime.date:
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="想定RPCI / PAI バックテスト")
    p.add_argument("--limit", type=int, default=200, help="対象レース数の上限（新しい順）")
    p.add_argument("--date-from", type=_parse_date, default=None, help="開催日の下限 YYYY-MM-DD")
    p.add_argument("--date-to", type=_parse_date, default=None, help="開催日の上限 YYYY-MM-DD")
    p.add_argument(
        "--sample-every",
        type=int,
        default=1,
        help="新しい順に N 件ごとに1件サンプリング（期間全体へ薄く広げる）",
    )
    p.add_argument(
        "--rpci-min",
        type=float,
        default=None,
        help="rpci_actual の下限フィルター（異常値除外用。例: 20）",
    )
    p.add_argument(
        "--rpci-max",
        type=float,
        default=None,
        help="rpci_actual の上限フィルター（異常値除外用。例: 90）",
    )
    p.add_argument(
        "--track-type",
        choices=["芝", "ダート", "障害"],
        default=None,
        help="コース種別フィルター（芝/ダート/障害）。未指定=全種別",
    )
    p.add_argument(
        "--venue-code",
        type=str,
        default=None,
        help="競馬場コードフィルター（例: 函館=02、福島=03、小倉=10）",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        help="結果をJSONファイルへ保存するパス（print出力は維持）",
    )
    p.add_argument(
        "--compare-ability-weights",
        action="store_true",
        help="能力指数の検証用重み4候補を同一対象で比較する",
    )
    p.add_argument(
        "--compare-rule-weights",
        action="store_true",
        help="想定RPCIのルール重み5候補を全体・芝・ダートで比較する",
    )
    p.add_argument(
        "--compare-pai-weights",
        action="store_true",
        help="PAIの検証用重み5候補を全体・芝・ダートで比較する",
    )
    diagnostic_mode = p.add_mutually_exclusive_group()
    diagnostic_mode.add_argument(
        "--validate-style-advantage",
        action="store_true",
        help="実績ペース・確定脚質で脚質別有利度ルールだけを高速検証する",
    )
    diagnostic_mode.add_argument(
        "--diagnose-style-advantage",
        action="store_true",
        help="予測/実績ペースと予測/確定脚質の4パターンで誤差要因を診断する",
    )
    p.add_argument(
        "--style-breakdown",
        action="append",
        choices=["year", "distance", "track-condition", "distance-track-condition"],
        default=[],
        help=(
            "確定値の脚質別有利度を年・実距離・馬場状態・距離×馬場状態で分割表示する"
            "（--validate-style-advantage専用、複数指定可）"
        ),
    )
    args = p.parse_args()
    if args.style_breakdown and not args.validate_style_advantage:
        p.error("--style-breakdown は --validate-style-advantage と組み合わせてください")
    return args


def _select_targets(session: Session, args: argparse.Namespace) -> list[Race]:
    stmt = select(RaceModel.race_key).where(
        RaceModel.status == str(RaceStatus.RESULT),
        RaceModel.rpci_actual.is_not(None),
    )
    if args.date_from is not None:
        stmt = stmt.where(RaceModel.race_date >= args.date_from)
    if args.date_to is not None:
        stmt = stmt.where(RaceModel.race_date <= args.date_to)
    if args.rpci_min is not None:
        stmt = stmt.where(RaceModel.rpci_actual >= args.rpci_min)
    if args.rpci_max is not None:
        stmt = stmt.where(RaceModel.rpci_actual <= args.rpci_max)
    if args.track_type is not None:
        stmt = stmt.where(RaceModel.track_type == args.track_type)
    if args.venue_code is not None:
        stmt = stmt.where(RaceModel.jyo_cd == args.venue_code.zfill(2))
    stmt = stmt.order_by(RaceModel.race_date.desc(), RaceModel.race_key.desc())

    keys = list(session.scalars(stmt).all())
    if args.sample_every > 1:
        keys = keys[:: args.sample_every]
    keys = keys[: args.limit]

    repo = SqlAlchemyRaceRepository(session)
    races = [repo.find_by_key(RaceKey(k)) for k in keys]
    return [r for r in races if r is not None]


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    targets = _select_targets(session, args)
    if not targets:
        print("対象レースがありません（status=result かつ rpci_actual を持つレース）。")
        return
    filter_note = ""
    notes: list[str] = []
    if args.rpci_min is not None or args.rpci_max is not None:
        lo = args.rpci_min or "-∞"
        hi = args.rpci_max or "+∞"
        notes.append(f"rpci_actual: {lo}〜{hi}")
    if args.track_type is not None:
        notes.append(f"コース種別: {args.track_type}")
    if args.venue_code is not None:
        notes.append(f"競馬場コード: {args.venue_code.zfill(2)}")
    if notes:
        filter_note = f" （{' / '.join(notes)}）"
    print(f"対象 {len(targets)} レースでバックテストを実行します{filter_note}…\n")

    repo = SqlAlchemyRaceRepository(session)
    if args.validate_style_advantage:
        samples = collect_actual_style_advantage_samples(targets, repo)
        summary = summarize_style_advantage(samples)
        print(format_actual_style_advantage_validation(summary))
        breakdowns: dict[str, object] = {}
        for dimension in args.style_breakdown:
            groups = build_actual_style_advantage_breakdown(targets, repo, dimension)
            print(format_actual_style_advantage_breakdown(dimension, groups))
            breakdowns[dimension] = style_advantage_breakdown_to_dict(groups)
        if args.output:
            payload = {
                "mode": "actual_pace_confirmed_style_diagnostic",
                "style_advantage": style_advantage_lift_to_dict(summary),
            }
            if breakdowns:
                payload["breakdowns"] = breakdowns
            _write_diagnostic_output(args.output, payload)
        return

    forecaster = load_best_forecaster()
    backtester = ForecastBacktester(repo, forecaster=forecaster)
    if args.diagnose_style_advantage:
        diagnosis = backtester.diagnose_style_advantage(targets)
        print(format_style_advantage_attribution(diagnosis))
        if args.output:
            _write_diagnostic_output(
                args.output,
                {
                    "mode": "style_advantage_error_attribution",
                    "style_advantage": style_advantage_attribution_to_dict(diagnosis),
                },
            )
        return

    report = backtester.run(targets)
    print(format_report(report))

    track_reports: dict[str, BacktestReport] = {}
    if args.track_type is None:
        track_reports = _print_track_breakdown(backtester, targets)

    weight_comparisons: list[AbilityWeightComparison] = []
    if args.compare_ability_weights:
        weight_comparisons = _run_ability_weight_comparison(
            repo,
            forecaster,
            targets,
            current_report=report,
        )
        print(f"\n{format_ability_weight_comparison(weight_comparisons)}")

    rule_weight_comparisons: list[RuleWeightComparison] = []
    if args.compare_rule_weights:
        rule_weight_comparisons = _run_rule_weight_comparison(repo, targets)
        print(f"\n{format_rule_weight_comparison(rule_weight_comparisons)}")

    pai_weight_comparisons: list[PaiWeightComparison] = []
    if args.compare_pai_weights:
        pai_weight_comparisons = _run_pai_weight_comparison(
            repo,
            forecaster,
            targets,
            current_report=report,
        )
        print(f"\n{format_pai_weight_comparison(pai_weight_comparisons)}")

    if args.output:
        _write_output(
            args.output,
            report,
            track_reports,
            weight_comparisons=weight_comparisons,
            rule_weight_comparisons=rule_weight_comparisons,
            pai_weight_comparisons=pai_weight_comparisons,
        )


def _run_ability_weight_comparison(
    repo: SqlAlchemyRaceRepository,
    forecaster: RpciForecaster | None,
    targets: list[Race],
    *,
    current_report: BacktestReport,
) -> list[AbilityWeightComparison]:
    """現行レポートを再利用し、残りの候補だけを同一対象で実行する。"""
    reports = {"current": current_report}
    for profile in DEFAULT_ABILITY_WEIGHT_PROFILES:
        if profile.name == "current":
            continue
        print(f"\n能力重み候補「{profile.name}」を検証中…")
        candidate_backtester = ForecastBacktester(
            repo,
            forecaster=forecaster,
            ability_scorer=AbilityScorer(profile.weights),
        )
        reports[profile.name] = candidate_backtester.run(targets)
    return compare_ability_weight_reports(reports)


def _run_rule_weight_comparison(
    repo: SqlAlchemyRaceRepository,
    targets: list[Race],
) -> list[RuleWeightComparison]:
    """各候補を同一対象で実行し、本番設定を変更せずに比較する。"""
    reports: dict[str, BacktestReport] = {}
    for profile in DEFAULT_RULE_WEIGHT_PROFILES:
        print(f"\nルール重み候補「{profile.name}」を検証中…")
        candidate_backtester = ForecastBacktester(
            repo,
            forecaster=RuleBasedRpciForecaster(profile.weights),
        )
        reports[profile.name] = candidate_backtester.run(targets)
    return compare_rule_weight_reports(reports)


def _run_pai_weight_comparison(
    repo: SqlAlchemyRaceRepository,
    forecaster: RpciForecaster | None,
    targets: list[Race],
    *,
    current_report: BacktestReport,
) -> list[PaiWeightComparison]:
    """現行レポートを再利用し、残りのPAI候補だけを同一対象で実行する。"""
    reports = {"current": current_report}
    for profile in DEFAULT_PAI_WEIGHT_PROFILES:
        if profile.name == "current":
            continue
        print(f"\nPAI重み候補「{profile.name}」を検証中…")
        candidate_backtester = ForecastBacktester(
            repo,
            forecaster=forecaster,
            pai_scorer=PaceAdaptabilityScorer(profile.weights),
        )
        reports[profile.name] = candidate_backtester.run(targets)
    return compare_pai_weight_reports(reports)


def _print_track_breakdown(
    backtester: ForecastBacktester, targets: list[Race]
) -> dict[str, BacktestReport]:
    """--track-type 未指定時、芝/ダート別の内訳も追加表示する。戻り値は --output 保存用。

    コース混合のみの集計だと PAI の point-biserial 相関が希釈されて見える落とし穴があるため
    （docs/adr/0005-rpci-forecast-strategy.md §5.4）、常に track 別内訳も併記して誤読を防ぐ。
    """
    by_track = group_races_by_track(targets)
    if len(by_track) <= 1:
        return {}
    reports: dict[str, BacktestReport] = {}
    for track_type in sorted(by_track):
        races = by_track[track_type]
        print(f"\n{'#' * 60}\nコース別内訳: {track_type}（{len(races)}レース）\n{'#' * 60}")
        track_report = backtester.run(races)
        print(format_report(track_report))
        reports[track_type] = track_report
    return reports


def _write_output(
    path: str,
    report: BacktestReport,
    track_reports: dict[str, BacktestReport],
    *,
    weight_comparisons: list[AbilityWeightComparison] | None = None,
    rule_weight_comparisons: list[RuleWeightComparison] | None = None,
    pai_weight_comparisons: list[PaiWeightComparison] | None = None,
) -> None:
    payload: dict[str, object] = {"combined": report_to_dict(report)}
    if track_reports:
        payload["by_track"] = {
            track: report_to_dict(track_report) for track, track_report in track_reports.items()
        }
    if weight_comparisons:
        payload["ability_weight_comparison"] = ability_weight_comparisons_to_dict(
            weight_comparisons
        )
    if rule_weight_comparisons:
        payload["rule_weight_comparison"] = rule_weight_comparisons_to_dict(
            rule_weight_comparisons
        )
    if pai_weight_comparisons:
        payload["pai_weight_comparison"] = pai_weight_comparisons_to_dict(
            pai_weight_comparisons
        )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n結果を {path} に保存しました。")


def _write_diagnostic_output(path: str, payload: Mapping[str, object]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n診断結果を保存しました: {path}")


if __name__ == "__main__":
    main()
