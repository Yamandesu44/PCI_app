"""rpci_actual 異常値修復スクリプト。

RA HaronTime バイト位置誤読（ダートレース）により生じた outlier rpci_actual を
全出走馬 pci_actual の平均値（aggregate_rpci フォールバック式）で上書きする。

修復対象: status='result' かつ rpci_actual が正常範囲外（デフォルト: 20〜90 の外）
修復方法: race_entries.pci_actual の平均値（フォールバック算出と同じ式）に置換
         pci3_actual は上位3着馬の pci_actual 平均で更新

使い方:
    cd apps/api
    python -m scripts.repair_rpci                   # dry-run: 件数確認のみ
    python -m scripts.repair_rpci --execute         # 実際にDBを更新
    python -m scripts.repair_rpci --rpci-min 20 --rpci-max 90 --execute
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from sqlalchemy import text

from pci.config.settings import get_settings
from pci.infrastructure.database.session import build_engine, build_session_maker


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="rpci_actual 異常値修復")
    p.add_argument("--rpci-min", type=float, default=20.0, help="正常範囲の下限 (default: 20)")
    p.add_argument("--rpci-max", type=float, default=90.0, help="正常範囲の上限 (default: 90)")
    p.add_argument(
        "--execute",
        action="store_true",
        help="実際にDBを更新する（未指定時は dry-run で件数確認のみ）",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    params = {"mn": args.rpci_min, "mx": args.rpci_max}

    # ── 1. 修復対象の件数確認 ──────────────────────────────────────────
    count_stmt = text(
        """
        SELECT COUNT(DISTINCT r.race_key)
        FROM races r
        JOIN race_entries e ON e.race_key = r.race_key
        WHERE r.status = 'result'
          AND r.rpci_actual IS NOT NULL
          AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
          AND e.pci_actual IS NOT NULL
        """
    )
    target_count = session.execute(count_stmt, params).scalar() or 0
    range_info = f"rpci_actual が {args.rpci_min}〜{args.rpci_max} の範囲外"
    print(f"修復対象: {target_count:,} レース（{range_info}）")

    if target_count == 0:
        print("修復対象なし。処理を終了します。")
        return

    if not args.execute:
        print("（dry-run モード: DB は変更しません。--execute で実際に適用）")

        # 年別の内訳を表示
        year_stmt = text(
            """
            SELECT
                EXTRACT(YEAR FROM r.race_date)::int AS yr,
                COUNT(DISTINCT r.race_key) AS cnt,
                MIN(r.rpci_actual),
                MAX(r.rpci_actual)
            FROM races r
            JOIN race_entries e ON e.race_key = r.race_key
            WHERE r.status = 'result'
              AND r.rpci_actual IS NOT NULL
              AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
              AND e.pci_actual IS NOT NULL
            GROUP BY yr
            ORDER BY yr
            """
        )
        try:
            print("\n  年別内訳:")
            for yr, cnt, mn_r, mx_r in session.execute(year_stmt, params):
                print(f"    {yr}年: {cnt:5d} 件  rpci範囲 [{mn_r:.1f}, {mx_r:.1f}]")
        except Exception as exc:
            print(f"  年別集計エラー: {exc}")
        return

    # ── 2. 修復実行 ───────────────────────────────────────────────────
    # 全出走馬 pci_actual の平均 → rpci_actual に上書き（aggregate_rpci フォールバック式と同じ）
    # 上位3着馬 pci_actual の平均 → pci3_actual に上書き
    update_stmt = text(
        """
        WITH to_fix AS (
            SELECT
                r.race_key,
                ROUND(AVG(e.pci_actual)::numeric, 1)::float8         AS new_rpci,
                ROUND(
                    AVG(CASE WHEN e.finish_pos IN (1, 2, 3) THEN e.pci_actual END)::numeric,
                    1
                )::float8                                             AS new_pci3
            FROM races r
            JOIN race_entries e ON e.race_key = r.race_key
            WHERE r.status = 'result'
              AND r.rpci_actual IS NOT NULL
              AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
              AND e.pci_actual IS NOT NULL
            GROUP BY r.race_key
            HAVING COUNT(e.pci_actual) > 0
        )
        UPDATE races
        SET rpci_actual  = to_fix.new_rpci,
            pci3_actual  = to_fix.new_pci3
        FROM to_fix
        WHERE races.race_key = to_fix.race_key
        """
    )
    result = session.execute(update_stmt, params)
    session.commit()

    updated = result.rowcount
    print(f"修復完了: {updated:,} レースを更新しました。")
    print(
        "  ・rpci_actual → 全出走馬 pci_actual の平均（暫定値）"
        "  ・pci3_actual → 上位3着馬 pci_actual の平均"
    )
    print(
        "  ダート HaronTime の正確バイト位置が確定後は再取り込みで TARGET 準拠値に更新できます。"
    )


if __name__ == "__main__":
    main()
