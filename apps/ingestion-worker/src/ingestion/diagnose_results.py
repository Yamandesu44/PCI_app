"""確定成績が取り込まれない原因を切り分けるための診断ツール（mykeibadb 専用）。

背景（2026-07-20）:
    sync が exit 0 なのに確定成績が1週間以上反映されない事象が発生した。
    「exit 0 で0件」だけでは、
      (A) mykeibadb の SE テーブルに確定データ（着順・タイム・上り3F）が
          そもそも入っていない（＝ mykeibadb.exe / JV-Link 側の未取得。本リポジトリ外）
      (B) 確定データは入っているが、列名がパーサの候補と一致せず拾えていない
          （＝ mykeibadb_client._pick の列候補不足。本リポジトリのバグ）
    のどちらなのか区別できない。本ツールは実データを読み、(A) と (B) を切り分ける。

使い方（Windows / mykeibadb の MySQL が見える環境）:
    cd apps\\ingestion-worker
    python -m ingestion.diagnose_results --date 20260712 --date-to 20260719

    # .env の MYKEIBADB_* / MYKEIBADB_DSN をそのまま使う（batch.py と同じ接続）。

出力は件数と「列が存在するか」の真偽が中心で、馬名等の個人データは既定で伏せる。
JRA-VAN 生データのコミットは禁止のため、貼り付ける際も件数・列名・DATA_KUBUN 分布までに
留めること（--show-values を付けない限り値は表示しない）。
"""

from __future__ import annotations

import argparse
import collections
import datetime
from typing import Any

from dotenv import load_dotenv

from ingestion.client.mykeibadb_client import (
    _AGARI_3F_COLUMNS,
    _AGARI_3F_RAW_COLUMNS,
    _DATA_KUBUN_COLUMNS,
    _FINISH_POS_COLUMNS,
    _RACE_TIME_COLUMNS,
    _SE_TABLE_CANDIDATES,
    MyKeibaDbClient,
    _build_se_record,
    _int_or_none,
    _pick,
    _raw_record,
    _row_in_date_range,
    _str_or_none,
)
from ingestion.parser.se_parser import parse_se_result

# 値を伏せる列（個人・馬名系）。--show-values 未指定時はサンプル表示から除外する。
_SENSITIVE_HINTS = ("name", "bamei", "馬名", "氏名", "shimei", "kisyu", "chokyo")


def _is_sensitive(column: str) -> bool:
    low = column.lower()
    return any(hint in low for hint in _SENSITIVE_HINTS)


def _fmt_present(value: Any) -> str:
    return "あり" if _str_or_none(value) else "なし"


def diagnose(
    date_from: str,
    date_to: str,
    show_values: bool,
    sample_limit: int,
    client: MyKeibaDbClient | None = None,
) -> None:
    client = client or MyKeibaDbClient()
    connection = client._connection or client._connect()
    table = client._find_table(connection, _SE_TABLE_CANDIDATES)
    print(f"SE テーブル: {table}")

    total = 0
    used_raw = 0
    used_built = 0
    has_finish = 0
    has_time = 0
    has_agari = 0
    has_all_three = 0
    parsed_ok = 0
    dk_dist: collections.Counter[str] = collections.Counter()
    built_dk_dist: collections.Counter[str] = collections.Counter()
    samples_shown = 0
    column_names: list[str] | None = None

    for row in client._iter_table_by_date_range(connection, table, date_from, date_to):
        if not _row_in_date_range(row, date_from, date_to):
            continue
        total += 1
        if column_names is None:
            column_names = list(row.keys())

        raw = _raw_record(row)
        if raw is not None:
            used_raw += 1
            record = raw
        else:
            used_built += 1
            record = _build_se_record(row)

        # 生の DATA_KUBUN 列値（列自体が無ければ "(列なし)"）
        dk_raw = _str_or_none(_pick(row, _DATA_KUBUN_COLUMNS)) or "(列なし)"
        dk_dist[dk_raw] += 1
        # 合成レコードに実際に書き込まれた DataKubun（byte[2:3]）
        built_dk_dist[record[2:3]] += 1

        finish = _int_or_none(_pick(row, _FINISH_POS_COLUMNS))
        time_val = _pick(row, _RACE_TIME_COLUMNS)
        agari_raw = _str_or_none(_pick(row, _AGARI_3F_RAW_COLUMNS))
        agari_s = _str_or_none(_pick(row, _AGARI_3F_COLUMNS))
        f_ok = finish is not None and finish > 0
        t_ok = _str_or_none(time_val) is not None
        a_ok = bool(agari_raw and agari_raw.isdigit()) or bool(agari_s)
        has_finish += int(f_ok)
        has_time += int(t_ok)
        has_agari += int(a_ok)
        if f_ok and t_ok and a_ok:
            has_all_three += 1

        result = None
        try:
            result = parse_se_result(record)
        except Exception as exc:  # noqa: BLE001 - 診断目的で握りつぶす
            if samples_shown < sample_limit:
                print(f"  parse_se_result 例外: {exc}")
        if result is not None:
            parsed_ok += 1

        # 「結果列はあるのに解析できない」行をサンプル表示（原因究明の核心）。
        if f_ok and result is None and samples_shown < sample_limit:
            samples_shown += 1
            print(f"\n--- 未解析サンプル #{samples_shown}（結果列あり・parse None）---")
            print(f"  finish={_fmt_present(_pick(row, _FINISH_POS_COLUMNS))} "
                  f"time={_fmt_present(time_val)} "
                  f"agari_raw={_fmt_present(agari_raw)} agari_s={_fmt_present(agari_s)}")
            print(f"  DATA_KUBUN(生列)={dk_raw} / 合成レコードbyte[2:3]={record[2:3]!r}")
            print(f"  合成byte[334:336]着順={record[334:336]!r} "
                  f"[338:342]時計={record[338:342]!r} [390:393]上り={record[390:393]!r}")
            if show_values:
                shown = {k: v for k, v in row.items() if not _is_sensitive(k)}
                print(f"  行データ(名系マスク): {shown}")

    print("\n===== 集計 =====")
    print(f"対象期間: {date_from}→{date_to}")
    print(f"SE 行数: {total}")
    print(f"  raw_record 列使用: {used_raw} / 合成(_build_se_record): {used_built}")
    print(f"  着順あり: {has_finish} / タイムあり: {has_time} / 上り3Fあり: {has_agari}")
    print(f"  3項目すべてあり: {has_all_three}")
    print(f"  parse_se_result 成功: {parsed_ok}")
    print(f"生 DATA_KUBUN 分布: {dict(dk_dist)}")
    print(f"合成レコード DataKubun 分布: {dict(built_dk_dist)}")
    if column_names is not None:
        print(f"\nSE テーブルの列名（{len(column_names)}列）:")
        print("  " + ", ".join(column_names))

    print("\n===== 判定 =====")
    if total == 0:
        print("  ⚠ この期間の SE 行が0件。mykeibadb に該当開催のデータが未取得です。")
        print("    → mykeibadb.exe / JV-Link 側の取得設定・FROMTIME を確認（本リポジトリ外）。")
    elif has_all_three == 0:
        print("  ⚠ SE 行はあるが、着順・タイム・上り3F のいずれかが全行で欠落。")
        print("    → (A) mykeibadb に確定成績が未取得、または (B) 結果列の列名が")
        print("       パーサ候補（_FINISH_POS_COLUMNS 等）と不一致の可能性。")
        print("       上の『SE テーブルの列名』に着順/タイム/上り3F 相当の列があるのに")
        print("       『着順あり』等が0なら (B)＝列候補不足。列名を教えてください。")
    elif parsed_ok == 0:
        print("  ⚠ 結果3項目は揃っているのに parse_se_result が全件 None。")
        print("    → 合成レコードのバイト配置か値変換（時計/上り3Fの妥当範囲）に不整合。")
        print("       上の未解析サンプルの合成byte値を確認してください（本リポジトリのバグ）。")
    else:
        print(f"  ✓ {parsed_ok} 件の確定成績を解析可能。取り込み側は正常に動作するはずです。")


def main() -> None:
    load_dotenv()
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=(today - datetime.timedelta(days=10)).strftime("%Y%m%d"),
        help="診断開始日 YYYYMMDD（既定: 10日前）",
    )
    parser.add_argument(
        "--date-to",
        default=today.strftime("%Y%m%d"),
        help="診断終了日 YYYYMMDD（既定: 今日）",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=3,
        help="未解析サンプルの最大表示数（既定: 3）",
    )
    parser.add_argument(
        "--show-values",
        action="store_true",
        help="サンプル行の列値も表示する（馬名等の名系列はマスク）。JRA生データ扱いに注意。",
    )
    args = parser.parse_args()
    diagnose(args.date, args.date_to, args.show_values, args.sample_limit)


if __name__ == "__main__":
    main()
