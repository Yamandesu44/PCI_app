"""rpci_actual 異常値修復スクリプト（2フェーズ）。

フェーズ1: race_entries.pci_actual の平均が正常範囲内のレースを補完する。
          （aggregate_rpci フォールバック式と同じ式で置換）

フェーズ2: フェーズ1実行後も rpci_actual が範囲外のままのレースを
          NULL に設定してバックテストから除外する。
          pci_actual 自体も壊れているケース（SE レコードの同種バグ等）が
          該当し、NULL 化が唯一の安全な対処となる。
          再取り込み後は正しい値で上書きされる。

修復対象: status='result' かつ rpci_actual が正常範囲外（デフォルト: 20〜90 の外）

使い方:
    cd apps/api
    python -m scripts.repair_rpci                   # dry-run: 件数確認のみ
    python -m scripts.repair_rpci --execute         # 実際にDBを更新（両フェーズ）
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
    p = argparse.ArgumentParser(description="rpci_actual 異常値修復（2フェーズ）")
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
    range_info = f"rpci_actual が {args.rpci_min}〜{args.rpci_max} の範囲外"

    # ── 外れ値総数 ────────────────────────────────────────────────────
    total_stmt = text(
        """
        SELECT COUNT(*)
        FROM races
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
          AND (rpci_actual < :mn OR rpci_actual > :mx)
        """
    )
    total_count = session.execute(total_stmt, params).scalar() or 0

    # ── フェーズ1: pci_actual 平均が正常範囲内のレース（本当に補完できる件数）──
    p1_fixable_stmt = text(
        """
        WITH candidates AS (
            SELECT r.race_key, AVG(e.pci_actual) AS avg_pci
            FROM races r
            JOIN race_entries e ON e.race_key = r.race_key
            WHERE r.status = 'result'
              AND r.rpci_actual IS NOT NULL
              AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
              AND e.pci_actual IS NOT NULL
            GROUP BY r.race_key
            HAVING COUNT(e.pci_actual) > 0
        )
        SELECT COUNT(*) FROM candidates WHERE avg_pci >= :mn AND avg_pci <= :mx
        """
    )
    p1_fixable = session.execute(p1_fixable_stmt, params).scalar() or 0
    p2_null_est = total_count - p1_fixable

    print(f"対象範囲: {range_info}")
    print(f"外れ値総数: {total_count:,} レース")
    print(f"フェーズ1（pci_actual 平均で正常範囲に補完できる）: {p1_fixable:,} レース")
    print(f"フェーズ2（補完後も範囲外 / pci_actual も壊れている → NULL化）: {p2_null_est:,} レース")

    if total_count == 0:
        print("\n修復対象なし。処理を終了します。")
        return

    if not args.execute:
        print("\n（dry-run モード: DB は変更しません。--execute で実際に適用）")
        _print_breakdown(session, params)
        return

    # ── フェーズ1 実行: pci_actual 平均で上書き ───────────────────────
    if p1_fixable > 0:
        p1_stmt = text(
            """
            WITH to_fix AS (
                SELECT
                    r.race_key,
                    ROUND(AVG(e.pci_actual)::numeric, 1)::float8         AS new_rpci,
                    ROUND(
                        AVG(CASE WHEN e.finish_pos IN (1, 2, 3)
                            THEN e.pci_actual END)::numeric,
                        1
                    )::float8                                             AS new_pci3
                FROM races r
                JOIN race_entries e ON e.race_key = r.race_key
                WHERE r.status = 'result'
                  AND r.rpci_actual IS NOT NULL
                  AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
                  AND e.pci_actual IS NOT NULL
                GROUP BY r.race_key
                HAVING AVG(e.pci_actual) >= :mn AND AVG(e.pci_actual) <= :mx
            )
            UPDATE races
            SET rpci_actual  = to_fix.new_rpci,
                pci3_actual  = to_fix.new_pci3
            FROM to_fix
            WHERE races.race_key = to_fix.race_key
            """
        )
        p1_result = session.execute(p1_stmt, params)
        session.commit()
        print(f"\nフェーズ1 完了: {p1_result.rowcount:,} レースを pci_actual 平均で更新")
    else:
        print("\nフェーズ1: 補完対象なし（スキップ）")

    # ── フェーズ2 実行: フェーズ1後も残った外れ値を NULL 化 ───────────
    # pci_actual 自体が壊れているため horse-PCI 平均でも正常範囲に入れられない。
    # NULL 化してバックテストから除外する（再取り込みで正しい値に更新可能）。
    p2_stmt = text(
        """
        UPDATE races
        SET rpci_actual = NULL,
            pci3_actual = NULL
        WHERE status = 'result'
          AND rpci_actual IS NOT NULL
          AND (rpci_actual < :mn OR rpci_actual > :mx)
        """
    )
    p2_result = session.execute(p2_stmt, params)
    session.commit()
    if p2_result.rowcount > 0:
        print(
            f"フェーズ2 完了: {p2_result.rowcount:,} レースの rpci_actual を NULL に設定"
            "（バックテスト除外）"
        )
    else:
        print("フェーズ2: NULL化対象なし")

    print(
        "\n  再取り込み後は HaronTime 由来の正確な RPCI で上書きされます。"
        "（芝は既存バイト位置で正確、ダートは位置確定後に再取り込み）"
    )


def _print_breakdown(session: object, params: dict) -> None:  # type: ignore[type-arg]
    """dry-run 時にコース種別別の内訳を表示する。"""
    stmt = text(
        """
        WITH status AS (
            SELECT
                r.race_key,
                r.track_type,
                r.rpci_actual,
                (
                    SELECT AVG(e.pci_actual)
                    FROM race_entries e
                    WHERE e.race_key = r.race_key
                      AND e.pci_actual IS NOT NULL
                ) AS avg_pci
            FROM races r
            WHERE r.status = 'result'
              AND r.rpci_actual IS NOT NULL
              AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
        )
        SELECT
            track_type,
            COUNT(*)                                          AS total,
            SUM(CASE WHEN avg_pci >= :mn AND avg_pci <= :mx
                THEN 1 ELSE 0 END)                           AS p1_fix,
            ROUND(MIN(rpci_actual)::numeric, 1)              AS mn,
            ROUND(MAX(rpci_actual)::numeric, 1)              AS mx
        FROM status
        GROUP BY track_type
        ORDER BY track_type
        """
    )
    try:
        print("\n  コース種別内訳:")
        for tt, total, p1, mn_r, mx_r in session.execute(stmt, params):
            p2 = (total or 0) - (p1 or 0)
            print(
                f"    {tt:6s}: {total:5d}件 "
                f"（フェーズ1補完: {p1 or 0}件 / フェーズ2NULL化: {p2}件）"
                f"  rpci [{mn_r}, {mx_r}]"
            )
    except Exception as exc:
        print(f"  内訳取得エラー: {exc}")


if __name__ == "__main__":
    main()
