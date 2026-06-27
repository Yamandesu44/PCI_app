"""rpci_actual 異常値修復スクリプト（2フェーズ）。

フェーズ1: race_entries.pci_actual が存在するレースの rpci_actual を
          全出走馬 pci_actual 平均（aggregate_rpci フォールバック式）で上書きする。

フェーズ2: pci_actual が一切ない（フェーズ1で補完できなかった）レースの
          rpci_actual を NULL に設定し、バックテストから除外する。

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

    # ── フェーズ1: pci_actual で補完可能な外れ値 ─────────────────────
    p1_count_stmt = text(
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
    p1_count = session.execute(p1_count_stmt, params).scalar() or 0

    # ── フェーズ2: pci_actual なし → NULL化（補完不能）───────────────
    p2_count_stmt = text(
        """
        SELECT COUNT(DISTINCT r.race_key)
        FROM races r
        WHERE r.status = 'result'
          AND r.rpci_actual IS NOT NULL
          AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
          AND NOT EXISTS (
              SELECT 1 FROM race_entries e
              WHERE e.race_key = r.race_key
                AND e.pci_actual IS NOT NULL
          )
        """
    )
    p2_count = session.execute(p2_count_stmt, params).scalar() or 0

    print(f"対象範囲: {range_info}")
    print(f"フェーズ1（pci_actual 平均で補完可能）: {p1_count:,} レース")
    print(f"フェーズ2（pci_actual なし → NULL化）: {p2_count:,} レース")
    total = p1_count + p2_count

    if total == 0:
        print("\n修復対象なし。処理を終了します。")
        return

    if not args.execute:
        print("\n（dry-run モード: DB は変更しません。--execute で実際に適用）")
        _print_breakdown(session, params)
        return

    # ── フェーズ1 実行: pci_actual 平均で上書き ───────────────────────
    if p1_count > 0:
        p1_stmt = text(
            """
            WITH to_fix AS (
                SELECT
                    r.race_key,
                    ROUND(AVG(e.pci_actual)::numeric, 1)::float8          AS new_rpci,
                    ROUND(
                        AVG(CASE WHEN e.finish_pos IN (1, 2, 3)
                            THEN e.pci_actual END)::numeric,
                        1
                    )::float8                                              AS new_pci3
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
        p1_result = session.execute(p1_stmt, params)
        session.commit()
        print(f"\nフェーズ1 完了: {p1_result.rowcount:,} レースを pci_actual 平均で更新")

    # ── フェーズ2 実行: 補完不能な外れ値を NULL 化 ────────────────────
    # pci_actual データが存在しないため horse-PCI 平均での補完が不可能。
    # 誤ったバイト位置由来の外れ値をそのままにするとバックテストの MAE を大きく歪めるため
    # NULL 化してバックテスト除外対象にする（再取り込みで正しい値が入れば上書きされる）。
    if p2_count > 0:
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
        print(
            f"フェーズ2 完了: {p2_result.rowcount:,} レースの rpci_actual を"
            " NULL に設定（バックテスト除外）"
        )

    print(
        "\n  再取り込み後は HaronTime 由来の正確な RPCI で上書きされます。"
        "（芝は既存バイト位置で正確、ダートは位置確定後に再取り込み）"
    )


def _print_breakdown(session: object, params: dict) -> None:  # type: ignore[type-arg]
    """dry-run 時にコース種別・年別の内訳を表示する。"""
    track_stmt = text(
        """
        SELECT
            r.track_type,
            COUNT(DISTINCT r.race_key) AS cnt,
            ROUND(MIN(r.rpci_actual)::numeric, 1) AS mn,
            ROUND(MAX(r.rpci_actual)::numeric, 1) AS mx,
            SUM(CASE WHEN e.pci_actual IS NOT NULL THEN 1 ELSE 0 END) > 0
                AS has_pci
        FROM races r
        LEFT JOIN race_entries e ON e.race_key = r.race_key
        WHERE r.status = 'result'
          AND r.rpci_actual IS NOT NULL
          AND (r.rpci_actual < :mn OR r.rpci_actual > :mx)
        GROUP BY r.race_key, r.track_type
        """
    )
    try:
        from collections import defaultdict

        summary: dict[str, dict] = defaultdict(
            lambda: {"cnt": 0, "mn": float("inf"), "mx": float("-inf"), "fixable": 0}
        )
        for tt, _cnt, mn_r, mx_r, has_pci in session.execute(track_stmt, params):
            d = summary[tt]
            d["cnt"] += 1
            d["mn"] = min(d["mn"], float(mn_r))
            d["mx"] = max(d["mx"], float(mx_r))
            if has_pci:
                d["fixable"] += 1
        print("\n  コース種別内訳:")
        for tt, d in sorted(summary.items()):
            nullify = d["cnt"] - d["fixable"]
            print(
                f"    {tt:6s}: {d['cnt']:5d} 件 "
                f"（フェーズ1補完: {d['fixable']}件 / フェーズ2NULL化: {nullify}件）"
                f"  rpci [{d['mn']:.1f}, {d['mx']:.1f}]"
            )
    except Exception as exc:
        print(f"  内訳取得エラー: {exc}")


if __name__ == "__main__":
    main()
