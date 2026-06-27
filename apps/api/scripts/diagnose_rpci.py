"""rpci_actual / pci_actual のデータ品質診断スクリプト。

バックテストで MAE が 47〜116 という異常値が出た原因を特定するため、
DB に格納された値の分布と外れ値を表示する。

使い方:
    cd apps/api
    python -m scripts.diagnose_rpci
    python -m scripts.diagnose_rpci --show-outliers   # 外れ値の詳細表示
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from sqlalchemy import func, select, text

from pci.config.settings import get_settings
from pci.infrastructure.database.models import RaceEntryModel, RaceModel
from pci.infrastructure.database.session import build_engine, build_session_maker


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="rpci_actual / pci_actual 品質診断")
    p.add_argument("--show-outliers", action="store_true", help="外れ値レースを一覧表示")
    p.add_argument("--rpci-min", type=float, default=20.0, help="正常範囲の下限 (default: 20)")
    p.add_argument("--rpci-max", type=float, default=90.0, help="正常範囲の上限 (default: 90)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session = build_session_maker(engine)()

    # ── 1. races.rpci_actual の分布 ──────────────────────────────────
    print("=" * 60)
    print("■ races.rpci_actual の分布")
    print("=" * 60)

    total_stmt = select(func.count()).select_from(RaceModel).where(
        RaceModel.rpci_actual.is_not(None)
    )
    total = session.scalar(total_stmt) or 0
    print(f"  rpci_actual 非NULL レース数: {total:,}")

    if total == 0:
        print("  データなし。")
        return

    # min/max/avg
    stats_stmt = select(
        func.min(RaceModel.rpci_actual),
        func.max(RaceModel.rpci_actual),
        func.avg(RaceModel.rpci_actual),
    ).where(RaceModel.rpci_actual.is_not(None))
    mn, mx, avg = session.execute(stats_stmt).one()
    print(f"  最小: {mn:.2f}  最大: {mx:.2f}  平均: {avg:.2f}")

    # 分位数（PostgreSQL）
    try:
        pct_result = session.execute(
            text(
                """
                SELECT
                    percentile_cont(0.05) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.25) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.50) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.75) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY rpci_actual),
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY rpci_actual)
                FROM races
                WHERE rpci_actual IS NOT NULL
                """
            )
        ).one()
        p5, p25, p50, p75, p95, p99 = pct_result
        print(f"  5%  : {p5:.2f}")
        print(f"  25% : {p25:.2f}")
        print(f"  中央: {p50:.2f}")
        print(f"  75% : {p75:.2f}")
        print(f"  95% : {p95:.2f}")
        print(f"  99% : {p99:.2f}")
    except Exception as exc:
        print(f"  分位数取得エラー（PostgreSQL 未接続？）: {exc}")

    # 外れ値件数
    outlier_count_stmt = select(func.count()).select_from(RaceModel).where(
        RaceModel.rpci_actual.is_not(None),
        (RaceModel.rpci_actual < args.rpci_min) | (RaceModel.rpci_actual > args.rpci_max),
    )
    outliers = session.scalar(outlier_count_stmt) or 0
    pct_out = outliers / total * 100
    print(
        f"\n  ── 外れ値: {outliers:,} レース（{pct_out:.1f}%）"
        f"が {args.rpci_min}〜{args.rpci_max} 範囲外"
    )

    # 年別集計
    print("\n  ── 年別 外れ値率")
    year_stmt = text(
        f"""
        SELECT
            EXTRACT(YEAR FROM race_date)::int AS yr,
            COUNT(*) AS total,
            SUM(CASE
                WHEN rpci_actual < {args.rpci_min}
                  OR rpci_actual > {args.rpci_max}
                THEN 1 ELSE 0 END) AS outliers,
            MIN(rpci_actual), MAX(rpci_actual), AVG(rpci_actual)
        FROM races
        WHERE rpci_actual IS NOT NULL
        GROUP BY yr
        ORDER BY yr
        """
    )
    try:
        for row in session.execute(year_stmt):
            yr, tot, out, mn_y, mx_y, avg_y = row
            pct = out / tot * 100 if tot else 0
            print(
                f"    {yr}年: {tot:5d}件 外れ値{out:5d}({pct:5.1f}%) "
                f"min={mn_y:.1f} max={mx_y:.1f} avg={avg_y:.1f}"
            )
    except Exception as exc:
        print(f"    年別集計エラー: {exc}")

    # ── 2. コース種別別の rpci_actual 分布 ──────────────────────────────
    print("\n  ── コース種別別 rpci_actual 分布")
    track_stmt = text(
        """
        SELECT
            track_type,
            COUNT(*)                                                AS cnt,
            ROUND(MIN(rpci_actual)::numeric, 1)                    AS mn,
            ROUND(MAX(rpci_actual)::numeric, 1)                    AS mx,
            ROUND(AVG(rpci_actual)::numeric, 1)                    AS avg,
            ROUND(percentile_cont(0.50)
                  WITHIN GROUP (ORDER BY rpci_actual)::numeric, 1) AS p50,
            SUM(CASE
                WHEN rpci_actual < :lo OR rpci_actual > :hi
                THEN 1 ELSE 0 END)                                 AS outliers
        FROM races
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
        GROUP BY track_type
        ORDER BY track_type
        """
    )
    try:
        hdr = f"  {'種別':6s} {'件数':>7s} {'最小':>7s} {'最大':>7s}"
        hdr += f" {'平均':>7s} {'中央':>7s} {'外れ値':>8s}"
        print(hdr)
        for row in session.execute(track_stmt, {"lo": args.rpci_min, "hi": args.rpci_max}):
            tt, cnt, mn_t, mx_t, avg_t, p50_t, out_t = row
            out_pct = out_t / cnt * 100 if cnt else 0
            print(
                f"  {tt:6s} {cnt:7,d} {mn_t:7.1f} {mx_t:7.1f} "
                f"{avg_t:7.1f} {p50_t:7.1f} {out_t:5,d}({out_pct:4.1f}%)"
            )
    except Exception as exc:
        print(f"    種別集計エラー: {exc}")

    # ── 4. race_entries.pci_actual の分布 ────────────────────────────
    print("\n" + "=" * 60)
    print("■ race_entries.pci_actual の分布")
    print("=" * 60)

    entry_stats = select(
        func.count(),
        func.min(RaceEntryModel.pci_actual),
        func.max(RaceEntryModel.pci_actual),
        func.avg(RaceEntryModel.pci_actual),
    ).where(RaceEntryModel.pci_actual.is_not(None))
    n_entries, mn_e, mx_e, avg_e = session.execute(entry_stats).one()
    print(f"  pci_actual 非NULL エントリ: {n_entries:,}")
    if n_entries:
        print(f"  最小: {mn_e:.2f}  最大: {mx_e:.2f}  平均: {avg_e:.2f}")
        try:
            pct_e = session.execute(
                text(
                    """
                    SELECT
                        percentile_cont(0.05) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY pci_actual),
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY pci_actual)
                    FROM race_entries
                    WHERE pci_actual IS NOT NULL
                    """
                )
            ).one()
            ep5, ep25, ep50, ep75, ep95 = pct_e
            print(
                f"  5%:  {ep5:.2f}  25%: {ep25:.2f}  中央: {ep50:.2f}"
                f"  75%: {ep75:.2f}  95%: {ep95:.2f}"
            )
        except Exception as exc:
            print(f"  分位数取得エラー: {exc}")

    # ── 5. 外れ値レース詳細 ──────────────────────────────────────────
    if args.show_outliers:
        print("\n" + "=" * 60)
        print(f"■ rpci_actual が {args.rpci_min} 未満 / {args.rpci_max} 超のレース（上位 50 件）")
        print("=" * 60)
        detail_stmt = (
            select(
                RaceModel.race_key,
                RaceModel.race_date,
                RaceModel.distance_m,
                RaceModel.track_type,
                RaceModel.rpci_actual,
            )
            .where(
                RaceModel.rpci_actual.is_not(None),
                (RaceModel.rpci_actual < args.rpci_min) | (RaceModel.rpci_actual > args.rpci_max),
            )
            .order_by(func.abs(RaceModel.rpci_actual - 50).desc())
            .limit(50)
        )
        rows = session.execute(detail_stmt).all()
        if not rows:
            print("  外れ値なし。")
        else:
            print(f"  {'レースキー':18s} {'日付':12s} {'距離':6s} {'馬場':6s} {'rpci_actual':>12s}")
            for rk, rd, dist, tt, rv in rows:
                print(f"  {rk:18s} {str(rd):12s} {dist:6d} {tt:6s} {rv:12.2f}")

    # ── 6. バックテスト有効サンプル数の推定 ───────────────────────────
    print("\n" + "=" * 60)
    print(f"■ バックテスト有効範囲（{args.rpci_min}〜{args.rpci_max}）のみで推定精度")
    print("=" * 60)
    valid_stmt = text(
        f"""
        SELECT COUNT(*)
        FROM races
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
          AND rpci_actual >= {args.rpci_min}
          AND rpci_actual <= {args.rpci_max}
        """
    )
    try:
        valid_count = session.execute(valid_stmt).scalar() or 0
        invalid_count = session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM races
                WHERE status = 'result'
                  AND rpci_actual IS NOT NULL
                  AND (rpci_actual < {args.rpci_min} OR rpci_actual > {args.rpci_max})
                """
            )
        ).scalar() or 0
        print(f"  有効: {valid_count:,} / 外れ値: {invalid_count:,}")
        if valid_count + invalid_count > 0:
            ratio = invalid_count / (valid_count + invalid_count) * 100
            print(f"  外れ値は全確定レースの {ratio:.1f}% を占める")
    except Exception as exc:
        print(f"  集計エラー: {exc}")

    print()


if __name__ == "__main__":
    main()
