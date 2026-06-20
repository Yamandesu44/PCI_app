"""Windows JV-Link COM クライアント（Windows 専用）。

このファイルは Windows 環境（pywin32 インストール済み）でのみ動作する。
Linux/CI 環境では import しないこと。

ADR-0002: JV-Link は Windows 専用 COM コンポーネント。
本番バッチは Windows PC / VM 上で `pci-ingest --mode jvlink` として実行する。

依存: pywin32 (extras: win) — `pip install pci-ingestion-worker[win]`

JV-Link API リファレンス:
  https://jra-van.jp/dlb/sdm/index.html (JRA-VAN DataLab 開発者向け)
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # 型チェック時のみ参照（実行時は import しない）


class WindowsJvLinkClient:
    """JV-Link COM を通じて JV-Data を取得するクライアント（Windows 専用）。

    NOTE: このクラスは Windows 環境でのみ import・実行可能。
          Linux / CI 環境では FixtureJvLinkClient を使うこと。

    使い方 (Windows):
        from ingestion.client.windows_client import WindowsJvLinkClient
        client = WindowsJvLinkClient(sid="YOUR_SID")
        for record in client.iter_ra_records("20260619", "20260619"):
            ...
    """

    def __init__(self, sid: str, software_id: str = "") -> None:
        if sys.platform != "win32":
            raise RuntimeError(
                "WindowsJvLinkClient は Windows 環境でのみ動作します。"
                " 開発環境では FixtureJvLinkClient を使用してください。"
            )
        self._sid = sid
        self._software_id = software_id
        self._jv = self._open_com()

    def _open_com(self) -> object:
        """JV-Link COM オブジェクトを初期化する。"""
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "pywin32 がインストールされていません。`pip install pci-ingestion-worker[win]` を実行してください。"
            ) from exc

        jv = win32com.client.Dispatch("JVDTLab.JVLink.1")
        # 利用キー（サービスキー）を設定してから初期化する
        sk_result = jv.JVSetServiceKey(self._sid)
        if sk_result != 0:
            raise RuntimeError(f"JVSetServiceKey 失敗: エラーコード {sk_result}")
        result = jv.JVInit(self._software_id)
        if result != 0:
            raise RuntimeError(f"JVInit 失敗: エラーコード {result}")
        return jv

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の RA レコードを JV-Link から取得する。"""
        yield from self._iter_records("RACE", date_from, date_to, record_types={"RA"})

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の SE レコードを JV-Link から取得する。"""
        yield from self._iter_records("RACE", date_from, date_to, record_types={"SE"})

    def iter_um_records(self) -> Iterator[str]:
        """競走馬マスタ UM レコードを取得する。"""
        yield from self._iter_records("MAST", record_types={"UM"})

    def iter_ks_records(self) -> Iterator[str]:
        """騎手マスタ KS レコードを取得する。"""
        yield from self._iter_records("MAST", record_types={"KS"})

    def iter_ch_records(self) -> Iterator[str]:
        """調教師マスタ CH レコードを取得する。"""
        yield from self._iter_records("MAST", record_types={"CH"})

    def _iter_records(
        self,
        data_spec: str,
        date_from: str = "",
        date_to: str = "",
        record_types: set[str] | None = None,
    ) -> Iterator[str]:
        """JV-Link の JVOpen → JVRead → JVClose を実行してレコードを返す。"""
        # JVOpen
        option = 4 if data_spec == "MAST" else 1  # 1=差分, 4=全量
        result = self._jv.JVOpen(
            data_spec,
            date_from + "000000",
            option,
            0,
            "",
            "",
        )
        if result < 0:
            raise RuntimeError(f"JVOpen 失敗: エラーコード {result}")

        try:
            while True:
                buf = " " * 20000
                nread = 0
                filename = ""
                ret = self._jv.JVRead(buf, nread, filename)
                if ret == 0:
                    break  # 全レコード取得完了
                if ret < 0:
                    raise RuntimeError(f"JVRead エラー: {ret}")
                record = buf[:ret].rstrip("\r\n")
                rec_spec = record[:2]
                if record_types is None or rec_spec in record_types:
                    yield record
        finally:
            self._jv.JVClose()
