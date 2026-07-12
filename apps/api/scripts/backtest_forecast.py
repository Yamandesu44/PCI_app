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

sys.path.insert(0, "src")

from sqlalchemy import select

from pci.application.backtest import (
    BacktestReport,
    ForecastBacktester,
    format_report,
    group_races_by_track,
    report_to_dict,
)
from pci.config.settings import get_settings
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
        "--output",
        type=str,
        default=None,
        help="結果をJSONファイルへ保存するパス（print出力は維持）",
    )
    return p.parse_args()


def _select_targets(session, args: argparse.Namespace) -> list[Race]:
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
    if notes:
        filter_note = f" （{' / '.join(notes)}）"
    print(f"対象 {len(targets)} レースでバックテストを実行します{filter_note}…\n")

    repo = SqlAlchemyRaceRepository(session)
    forecaster = load_best_forecaster()
    backtester = ForecastBacktester(repo, forecaster=forecaster)
    report = backtester.run(targets)
    print(format_report(report))

    track_reports: dict[str, BacktestReport] = {}
    if args.track_type is None:
        track_reports = _print_track_breakdown(backtester, targets)

    if args.output:
        _write_output(args.output, report, track_reports)


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
    path: str, report: BacktestReport, track_reports: dict[str, BacktestReport]
) -> None:
    payload: dict[str, object] = {"combined": report_to_dict(report)}
    if track_reports:
        payload["by_track"] = {
            track: report_to_dict(track_report) for track, track_report in track_reports.items()
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n結果を {path} に保存しました。")


if __name__ == "__main__":
    main()
