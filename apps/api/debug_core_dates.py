"""アプリ core DB（Postgres の races テーブル）の日付カバレッジを診断する。

「4/5以前のレースが表示されない」原因が
  - core DB にデータが入っていない（取り込み未実行）なのか
  - それとも表示側の問題なのか
を切り分けるための読み取り専用スクリプト。

使い方:
    cd apps/api
    python debug_core_dates.py

接続先は settings.database_url（.env の DATABASE_URL で上書き可）。
フロント/API と同じ DB を見るので、ここに出ない日付は画面にも出ない。
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from sqlalchemy import func, select

from pci.config.settings import get_settings
from pci.infrastructure.database.models import RaceModel
from pci.infrastructure.database.session import build_engine, build_session_maker


def main() -> None:
    settings = get_settings()
    # パスワードを伏せて接続先を表示
    shown = settings.database_url
    if "@" in shown:
        shown = shown.split("@", 1)[0].rsplit(":", 1)[0] + ":***@" + shown.split("@", 1)[1]
    print(f"\n=== core DB: {shown} ===\n")

    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    total = session.scalar(select(func.count()).select_from(RaceModel)) or 0
    if total == 0:
        print("races テーブルが空です。--step entries / results を実行してください。")
        return

    min_date = session.scalar(select(func.min(RaceModel.race_date)))
    max_date = session.scalar(select(func.max(RaceModel.race_date)))
    print(f"総レース数 : {total}")
    print(f"最古の開催日: {min_date}")
    print(f"最新の開催日: {max_date}")

    # status 内訳
    print("\n--- status 内訳 ---")
    for status, cnt in session.execute(
        select(RaceModel.status, func.count()).group_by(RaceModel.status)
    ).all():
        print(f"  {status:10s}: {cnt}")

    # 年月ごとの件数（どの月までDBに入っているか一目で分かる）
    month = func.to_char(RaceModel.race_date, "YYYY-MM")
    print("\n--- 年月別レース数 ---")
    rows = session.execute(
        select(month.label("ym"), func.count())
        .group_by(month)
        .order_by(month)
    ).all()
    for ym, cnt in rows:
        print(f"  {ym}: {cnt}")

    print(
        "\nヒント: 4月より前の行がここに無ければ DB 未取り込みです。"
        "\n  例) 2026年1月以降を取り込む:"
        "\n  python -m ingestion.batch --mode mykeibadb "
        "--date 20260101 --date-to 20260405 --step entries --chunk-days 30"
        "\n  python -m ingestion.batch --mode mykeibadb "
        "--date 20260101 --date-to 20260405 --step results --chunk-days 30"
    )


if __name__ == "__main__":
    main()
