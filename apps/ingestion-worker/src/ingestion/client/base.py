"""JvLinkClient プロトコル（ADR-0002: Windows COM 実装の界面定義）。

実装クラス:
  - FixtureJvLinkClient: 開発用（fixtures/ JSON を読む）
  - WindowsJvLinkClient: 本番用（JV-Link COM 呼び出し、Windows 専用）
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from ingestion.models import RaceMetadataRecord


class JvLinkClient(Protocol):
    """JV-Link データソースの抽象界面。

    本番: JV-Link COM / 開発: fixture JSON を返す FixtureJvLinkClient。
    いずれも同じ Protocol を満たすことでバッチランナーから差し替え可能（ADR-0005 同様の戦略IF）。
    """

    def iter_ra_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の RA レコード（固定長文字列）を順に返す。

        date_from / date_to: "YYYYMMDD" 形式。
        """
        ...

    def iter_se_records(self, date_from: str, date_to: str) -> Iterator[str]:
        """指定期間の SE レコード（固定長文字列）を順に返す。"""
        ...

    def iter_um_records(self) -> Iterator[str]:
        """全競走馬マスタ UM レコードを返す（差分更新）。"""
        ...

    def iter_ks_records(self) -> Iterator[str]:
        """全騎手マスタ KS レコードを返す（差分更新）。"""
        ...

    def iter_ch_records(self) -> Iterator[str]:
        """全調教師マスタ CH レコードを返す（差分更新）。"""
        ...


@runtime_checkable
class RaceMetadataProvider(Protocol):
    """固定長位置を介さず、列分解済みのレース補足情報を提供する任意機能。"""

    def race_metadata(self, race_key: str) -> RaceMetadataRecord | None: ...

    def iter_race_metadata(self, date_from: str, date_to: str) -> Iterator[RaceMetadataRecord]: ...
