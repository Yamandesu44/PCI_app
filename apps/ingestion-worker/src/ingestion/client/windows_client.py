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
import time
from collections.abc import Iterator
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # 型チェック時のみ参照（実行時は import しない）

# COM 定数（pythoncom.VT_* / PARAMFLAG_* に対応）
_VT_I4: int = 3
_VT_BSTR: int = 8
_VT_BYREF: int = 0x4000
_PARAMFLAG_FIN: int = 1
_PARAMFLAG_FOUT: int = 2
_DISPATCH_METHOD: int = 1
_LCID: int = 0


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

    _dispatch: Any  # pythoncom IDispatch (生オブジェクト)

    def __init__(self, sid: str, software_id: str = "UNKNOWN") -> None:
        if sys.platform != "win32":
            raise RuntimeError(
                "WindowsJvLinkClient は Windows 環境でのみ動作します。"
                " 開発環境では FixtureJvLinkClient を使用してください。"
            )
        self._sid = sid
        self._software_id = software_id
        self._open_com()

    def _open_com(self) -> None:
        """JV-Link COM オブジェクトを初期化する。"""
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "pywin32 がインストールされていません。`pip install pci-ingestion-worker[win]` を実行してください。"
            ) from exc

        jv = win32com.client.Dispatch("JVDTLab.JVLink.1")
        # JV-Link 4.9.x のタイプライブラリには Long 型パラメータのデフォルト値が
        # 空文字列で定義されているバグがある。win32com の _ApplyTypes_ / InvokeTypes が
        # int('') を呼び出してクラッシュするため、生の IDispatch を直接使う。
        self._dispatch = jv._oleobj_  # type: ignore[attr-defined]

        # JVInit(SoftwareCode As String) As Long
        dispid = self._dispatch.GetIDsOfNames("JVInit")
        result: int = self._dispatch.InvokeTypes(
            dispid, _LCID, _DISPATCH_METHOD,
            (_VT_I4, 0),
            ((_VT_BSTR, _PARAMFLAG_FIN, None),),
            self._software_id,
        )
        if result != 0:
            raise RuntimeError(f"JVInit 失敗: エラーコード {result}")

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の RA レコードを JV-Link から取得する。"""
        yield from self._iter_records("RACE", date_from, date_to, record_types={"RA"})

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の SE レコードを JV-Link から取得する。"""
        yield from self._iter_records("RACE", date_from, date_to, record_types={"SE"})

    def iter_race_records_raw(self, date_from: str, date_to: str) -> Iterator[str]:
        """RACE データスペックの全レコード（RA/SE 混在）を1回の JVOpen で返す。

        デバッグ用。RA と SE を別々に JVOpen すると option=1 の再取得挙動に
        左右されるため、フィールド位置調査時は本メソッドで一括取得する。
        """
        yield from self._iter_records("RACE", date_from, date_to, record_types=None)

    def iter_um_records(self) -> Iterator[str]:
        """競走馬マスタ UM レコードを取得する（DIFF データ種別）。"""
        yield from self._iter_records("DIFF", record_types={"UM"})

    def iter_ks_records(self) -> Iterator[str]:
        """騎手マスタ KS レコードを取得する（DIFF データ種別）。"""
        yield from self._iter_records("DIFF", record_types={"KS"})

    def iter_ch_records(self) -> Iterator[str]:
        """調教師マスタ CH レコードを取得する（DIFF データ種別）。"""
        yield from self._iter_records("DIFF", record_types={"CH"})

    def _iter_records(
        self,
        data_spec: str,
        date_from: str = "",
        date_to: str = "",
        record_types: set[str] | None = None,
    ) -> Iterator[str]:
        """JV-Link の JVOpen → JVRead → JVClose を実行してレコードを返す。"""
        option = 4 if data_spec == "DIFF" else 1  # DIFF(マスタ)=4:セットアップ全量
        # fromtime は 14 桁(YYYYMMDDHHMMSS)。日付未指定(マスタ)は基準日で全件取得
        fromtime = (date_from + "000000") if date_from else "20000101000000"
        buf_size = 110000  # JV-Data 1 レコード最大長に余裕を持たせる

        # JVOpen(DataSpec, FromTime, Option,
        #        ByRef ReadCount, ByRef DownloadCount, ByRef LastFileTimestamp) As Long
        dispid_open = self._dispatch.GetIDsOfNames("JVOpen")
        ret_open: Any = self._dispatch.InvokeTypes(
            dispid_open, _LCID, _DISPATCH_METHOD,
            (_VT_I4, 0),
            (
                (_VT_BSTR, _PARAMFLAG_FIN, None),                   # DataSpec
                (_VT_BSTR, _PARAMFLAG_FIN, None),                   # FromTime
                (_VT_I4, _PARAMFLAG_FIN, None),                     # Option
                (_VT_BYREF | _VT_I4, _PARAMFLAG_FOUT, None),       # ReadCount (out)
                (_VT_BYREF | _VT_I4, _PARAMFLAG_FOUT, None),       # DownloadCount (out)
                (_VT_BYREF | _VT_BSTR, _PARAMFLAG_FOUT, None),     # LastFileTimestamp (out)
            ),
            data_spec, fromtime, option, 0, 0, "",
        )
        open_code: int = ret_open[0] if isinstance(ret_open, tuple) else ret_open
        if open_code < 0:
            raise RuntimeError(f"JVOpen 失敗: エラーコード {open_code}")

        dispid_read = self._dispatch.GetIDsOfNames("JVRead")
        dispid_close = self._dispatch.GetIDsOfNames("JVClose")

        # -3(ダウンロード中)の連続再試行上限。0.5s × 1200 = 最大 10 分待機
        max_download_wait = 1200
        download_wait = 0

        try:
            while True:
                # JVRead(ByRef Buff, ByRef Size, ByRef FileName) As Long
                # Size は入力バッファサイズ。戻り値タプル=(retcode, buff, filename)
                ret_read: Any = self._dispatch.InvokeTypes(
                    dispid_read, _LCID, _DISPATCH_METHOD,
                    (_VT_I4, 0),
                    (
                        (_VT_BYREF | _VT_BSTR, _PARAMFLAG_FIN | _PARAMFLAG_FOUT, None),  # Buff
                        (_VT_BYREF | _VT_I4, _PARAMFLAG_FIN, None),                       # Size (in)
                        (_VT_BYREF | _VT_BSTR, _PARAMFLAG_FOUT, None),                    # FileName (out)
                    ),
                    " " * buf_size, buf_size, "",
                )
                if isinstance(ret_read, tuple):
                    read_code: int = ret_read[0]
                    buf: str = ret_read[1] if len(ret_read) > 1 else ""
                else:
                    read_code = ret_read
                    buf = ""
                if read_code == 0:
                    break  # 全レコード取得完了
                if read_code == -1:
                    continue  # ファイル切り替わり。次のレコードへ
                if read_code == -3:
                    # 該当ファイルがまだダウンロード中。少し待って再試行する
                    download_wait += 1
                    if download_wait > max_download_wait:
                        raise RuntimeError("JVRead: ダウンロード待機がタイムアウトしました(-3)")
                    time.sleep(0.5)
                    continue
                if read_code < 0:
                    raise RuntimeError(f"JVRead エラー: {read_code}")
                download_wait = 0  # 正常読込でリセット
                record = buf[:read_code].rstrip("\r\n")
                rec_spec = record[:2]
                if record_types is None or rec_spec in record_types:
                    yield record
        finally:
            self._dispatch.InvokeTypes(
                dispid_close, _LCID, _DISPATCH_METHOD,
                (_VT_I4, 0), (),
            )
