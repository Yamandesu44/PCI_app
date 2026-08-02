"""取り込み元 mykeibadb（MySQL）へ実際に接続できるかを事前確認する。

背景（2026-08-02）:
    MySQL80 サービスが停止した状態で sync を起動したところ、
      1. プリフライトは「API と PostgreSQL は ready」と表示して通過
      2. mykeibadb.exe は 7 秒で exit 0（MySQL が無いので何もできていない）
      3. batch.py が接続拒否で落ち、30 秒・60 秒待って 3 回リトライ
    という流れで、原因（MySQL が起動していない）に辿り着くまで数分かかった。
    プリフライトが確認していたのは「書き込み先」だけで、肝心の「読み取り元」を
    見ていなかったのが原因。ここで読み取り元も確認し、駄目なら即座に止める。

TCP ポートの疎通ではなく実際に接続するのは、サービス停止（6.1）だけでなく
認証失敗（6.2）も同じ入口で捕まえるため。batch.py と同じ `MyKeibaDbConfig.from_env()`
を使うので、設定の解釈がズレることもない。

使い方（Windows / mykeibadb の MySQL が見える環境）:
    cd apps\\ingestion-worker
    python -m ingestion.check_mykeibadb

終了コード: 0=接続できた / 1=接続できない（理由と対処を標準出力へ表示）
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from ingestion.client.mykeibadb_client import MyKeibaDbConfig

# MANUAL_SYNC_GUIDE.md §6 の見出しと対応させる。ここを直したら向こうも直すこと。
_FIX_SERVICE_DOWN = (
    "MySQL80 サービスが停止している可能性が高い（MANUAL_SYNC_GUIDE §6.1）。\n"
    "  1. Win+R → services.msc → MySQL80 を右クリック → 開始\n"
    "     （または管理者権限のコマンドプロンプトで: net start MySQL80）\n"
    "  2. WIN32_EXIT_CODE 1067 で起動しない場合は §6.4（my.ini の文字化け）を参照"
)
_FIX_AUTH = (
    "認証に失敗した（MANUAL_SYNC_GUIDE §6.2）。\n"
    "  .env の MYKEIBADB_PASSWORD を wmykeibadb.exe のパスワード欄と同じ値にする"
)
_FIX_DATABASE = (
    "接続はできたがデータベースが見つからない。\n"
    "  .env の MYKEIBADB_DATABASE と、wmykeibadb.exe の設定が一致しているか確認する"
)


def _classify(exc: Exception) -> str:
    """pymysql の例外を、対処が異なる3種類へ振り分ける。

    エラーコードで見る（メッセージは MySQL のバージョンや言語で変わるため）。
    """
    code = exc.args[0] if exc.args else None
    if code == 2003:  # Can't connect to MySQL server
        return _FIX_SERVICE_DOWN
    if code in (1045, 1698):  # Access denied
        return _FIX_AUTH
    if code == 1049:  # Unknown database
        return _FIX_DATABASE
    return (
        "想定外のエラー。MANUAL_SYNC_GUIDE §6 を確認するか、"
        "上のエラーメッセージで検索する。"
    )


def check() -> int:
    config = MyKeibaDbConfig.from_env()
    target = f"{config.user}@{config.host}:{config.port}/{config.database}"
    print(f"取り込み元 mykeibadb への接続を確認します: {target}")

    try:
        import pymysql  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: PyMySQL が入っていません。")
        print('  対処: python -m pip install -e ".[mysql]"')
        return 1

    try:
        connection = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset=config.charset,
            connect_timeout=10,
        )
    except Exception as exc:  # pymysql は複数の例外型を投げるため広く捕まえる
        print(f"ERROR: 接続できません: {exc}")
        print(_classify(exc))
        return 1

    try:
        # 接続だけでなく、実際にテーブルが見えるかまで確認する。
        # mykeibadb.exe が一度も走っていない空DBを「正常」と誤判定しないため。
        with connection.cursor() as cur:
            cur.execute("SHOW TABLES")
            table_count = len(cur.fetchall())
    finally:
        connection.close()

    if table_count == 0:
        print("ERROR: 接続はできましたが、テーブルが1つもありません。")
        print("  mykeibadb.exe（または wmykeibadb.exe）で初回取り込みを実行してください。")
        return 1

    print(f"OK: mykeibadb へ接続できました（テーブル {table_count} 件）。")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    load_dotenv()
    sys.exit(check())


if __name__ == "__main__":
    main()
