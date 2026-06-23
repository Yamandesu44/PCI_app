"""JV-Link RACE option の取得可否を調べる診断コマンド。"""

from __future__ import annotations

import argparse
import os
from collections import Counter

from dotenv import load_dotenv

from ingestion.client.windows_client import WindowsJvLinkClient


def _race_date(record: str) -> str:
    return record[11:19] if len(record) >= 19 else ""


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="JV-Link RACE option 1-4 のどれでレースデータが返るか確認します。"
    )
    parser.add_argument("--date", required=True, help="取得開始日 YYYYMMDD")
    parser.add_argument("--date-to", default=None, help="取得終了日 YYYYMMDD（表示フィルタ用）")
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="各optionで読む最大レコード数。診断用なので既定は300件。",
    )
    args = parser.parse_args()

    sid = os.environ.get("JV_LINK_SID", "")
    if not sid:
        raise RuntimeError("JV_LINK_SID が未設定です。.env を確認してください。")

    date_to = args.date_to or args.date
    client = WindowsJvLinkClient(sid=sid)

    for option in (1, 2, 3, 4):
        counts: Counter[str] = Counter()
        dates: Counter[str] = Counter()
        error: str | None = None
        try:
            for idx, record in enumerate(
                client.iter_race_records_raw(args.date, date_to, option=option),
                start=1,
            ):
                counts[record[:2]] += 1
                d = _race_date(record)
                if d:
                    dates[d] += 1
                if idx >= args.limit:
                    break
        except Exception as exc:
            error = str(exc)

        if error:
            print(f"option={option}: ERROR {error}")
            continue

        total = sum(counts.values())
        date_summary = ", ".join(f"{date}:{count}" for date, count in dates.most_common(5))
        spec_summary = ", ".join(f"{spec}:{count}" for spec, count in counts.most_common())
        print(f"option={option}: total={total} specs=[{spec_summary}] dates=[{date_summary}]")


if __name__ == "__main__":
    main()
