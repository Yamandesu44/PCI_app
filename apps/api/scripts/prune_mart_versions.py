"""mart 層から、もう使われていない model_version の行を削除する。

`pace_fit` / `predicted_pace` は `model_version` が主キーの一部で、世代を上げると
行が**更新ではなく追加**される。放っておくと世代の数だけ積み上がり、コアデータより
速く容量を食う（docs/DECISIONS.md ADR-0006 / ADR-2026-08-04）。

**現役の世代を消さないことが最優先。** 判定を誤ると、アプリが参照する行が消えるか、
再生成されるまで表示が欠ける。そのため二重に守る:

  1. ドメインが持つ現行世代（`pai-v4` 等）は、生成時刻に関わらず必ず残す
  2. 直近 `--active-days` 日以内に書かれた世代は、残す対象から外れていても消さない

2 が要るのは `predicted_pace` の事情。芝とダートで別々の世代が**同時に現役**
（`lgbm-turf-v2-pci-v3` と `lgbm-dirt-v6-pci-v3`）なので、「新しいN世代」だけで
切ると、書き込み頻度の低い側を現役のまま消してしまう。

直前の世代を残すのは、世代を上げた直後に精度が落ちたと分かったときの比較対象。

既定は dry-run で、消える行数を示すだけで DB は変更しない。

使い方:
    cd apps/api
    python -m scripts.prune_mart_versions            # 影響を確認（DBは変更しない）
    python -m scripts.prune_mart_versions --apply    # 実際に削除する
    python -m scripts.prune_mart_versions --keep 1   # 現行世代だけ残す
"""

from __future__ import annotations

import argparse
import datetime
import sys

sys.path.insert(0, "src")

from sqlalchemy import text
from sqlalchemy.orm import Session

from pci.config.settings import get_settings
from pci.domain.pace.adaptability import MODEL_VERSION as PAI_MODEL_VERSION
from pci.infrastructure.database.session import build_engine

# 対象テーブルと、そこで「必ず残す」世代。
# `predicted_pace` は芝・ダートで世代が分かれ、単一の定数では表せないため None。
# その分は `--active-days` の保護で担保する。
_TARGETS: tuple[tuple[str, str | None], ...] = (
    ("pace_fit", PAI_MODEL_VERSION),
    ("predicted_pace", None),
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="実際に削除する。付けない限りDBは変更しない。",
    )
    p.add_argument(
        "--keep",
        type=int,
        default=2,
        help="残す世代数（既定2＝現行＋直前）。現役判定に該当する世代はこれと別に残る。",
    )
    p.add_argument(
        "--active-days",
        type=int,
        default=7,
        help="この日数以内に書かれた世代は現役とみなし、削除しない（既定7）。",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.keep < 1:
        raise SystemExit("--keep は1以上にしてください（現行世代は必ず残す必要があります）。")

    now = datetime.datetime.now(datetime.UTC)
    active_since = now - datetime.timedelta(days=args.active_days)
    engine = build_engine(get_settings().database_url)
    total_deleted = 0

    with Session(engine) as session:
        for table, pinned_version in _TARGETS:
            rows = session.execute(
                text(
                    f"""
                    SELECT model_version, count(*) AS n, max(generated_at) AS latest
                    FROM "{table}"
                    GROUP BY model_version
                    ORDER BY max(generated_at) DESC
                    """  # noqa: S608 - テーブル名はこのモジュール内の定数のみ
                )
            ).all()
            if not rows:
                print(f"■ {table}: 行がありません\n")
                continue

            keep: set[str] = {pinned_version} if pinned_version else set()
            for version, _n, latest in rows:
                if latest is not None and latest >= active_since:
                    keep.add(version)  # 現役。世代数の枠とは別に残す。
            for version, _n, _latest in rows:
                if len(keep) >= args.keep:
                    break
                keep.add(version)

            print(f"■ {table}" + (f"（現行: {pinned_version}）" if pinned_version else ""))
            print(f"  {'世代':<30}{'行数':>12}  {'最終生成':<28}判定")
            for version, n, latest in rows:
                if version in keep:
                    if version == pinned_version:
                        verdict = "残す（現行）"
                    elif latest is not None and latest >= active_since:
                        verdict = "残す（現役）"
                    else:
                        verdict = "残す"
                else:
                    verdict = "削除"
                print(f"  {version:<30}{n:>12,}  {str(latest):<28}{verdict}")

            doomed = [(v, n) for v, n, _ in rows if v not in keep]
            for version, n in doomed:
                total_deleted += n
                if args.apply:
                    session.execute(
                        text(f'DELETE FROM "{table}" WHERE model_version = :v'),  # noqa: S608
                        {"v": version},
                    )
            print()

        if args.apply:
            session.commit()

    if total_deleted == 0:
        print("削除対象はありませんでした。")
        return

    if args.apply:
        print(f"{total_deleted:,} 行を削除しました。")
        print("領域を実際に返すには VACUUM が要ります（autovacuum に任せてもよい）。")
    else:
        print(f"{total_deleted:,} 行が削除対象です。")
        print("DBは変更していません（dry-run）。削除するには --apply を付けて再実行してください。")


if __name__ == "__main__":
    main()
