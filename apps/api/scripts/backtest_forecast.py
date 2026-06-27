"""想定RPCI / PAI のバックテストを実DBに対して実行する CLI。

確定済みレースを「予測時点」に巻き戻して ForecastRaceUseCase を再現し、
実績RPCI・好走と突き合わせて精度を出力する（評価ロジックは
pci.application.backtest に集約。本スクリプトは DB 配線と対象選定のみ）。

使い方:
    cd apps/api
    python -m scripts.backtest_forecast --limit 200
    python -m scripts.backtest_forecast --date-from 2024-01-01 --date-to 2024-12-31
    python -m scripts.backtest_forecast --limit 2000 --sample-every 5

対象は status="result" かつ rpci_actual を持つレース。1レースの予測は
数百クエリを伴うため、既定は新しい順 200 レースに絞る（--limit で調整）。
lookahead は backtest 側でレース当日カットオフして防止する。
"""

from __future__ import annotations

import argparse
import datetime
import sys

sys.path.insert(0, "src")

from sqlalchemy import select

from pci.application.backtest import ForecastBacktester, format_report
from pci.config.settings import get_settings
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.shared.race_key import RaceKey
from pci.infrastructure.database.models import RaceModel
from pci.infrastructure.database.session import build_engine, build_session_maker
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
    print(f"対象 {len(targets)} レースでバックテストを実行します…\n")

    repo = SqlAlchemyRaceRepository(session)
    report = ForecastBacktester(repo).run(targets)
    print(format_report(report))


if __name__ == "__main__":
    main()
