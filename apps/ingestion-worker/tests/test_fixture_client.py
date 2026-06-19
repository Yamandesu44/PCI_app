"""FixtureJvLinkClient のユニットテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.client.fixture_client import FixtureJvLinkClient

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class TestFixtureClientFromJson:
    """JSON フィクスチャファイルから生成するケース。"""

    def _client(self) -> FixtureJvLinkClient:
        return FixtureJvLinkClient(fixtures_dir=_FIXTURES)

    def test_iter_ra_records_returns_at_least_one(self) -> None:
        records = list(self._client().iter_ra_records("20260618", "20260618"))
        assert len(records) >= 1

    def test_ra_record_starts_with_ra(self) -> None:
        records = list(self._client().iter_ra_records("20260618", "20260618"))
        assert all(r.startswith("RA") for r in records)

    def test_iter_se_records_returns_entries_and_results(self) -> None:
        records = list(self._client().iter_se_records("20260618", "20260618"))
        assert len(records) >= 1

    def test_se_records_start_with_se(self) -> None:
        records = list(self._client().iter_se_records("20260618", "20260618"))
        assert all(r.startswith("SE") for r in records)

    def test_iter_um_records_returns_horses(self) -> None:
        records = list(self._client().iter_um_records())
        assert len(records) >= 1

    def test_um_records_start_with_um(self) -> None:
        records = list(self._client().iter_um_records())
        assert all(r.startswith("UM") for r in records)

    def test_iter_ks_records_returns_jockeys(self) -> None:
        records = list(self._client().iter_ks_records())
        assert len(records) >= 1

    def test_ks_records_start_with_ks(self) -> None:
        records = list(self._client().iter_ks_records())
        assert all(r.startswith("KS") for r in records)

    def test_iter_ch_records_returns_trainers(self) -> None:
        records = list(self._client().iter_ch_records())
        assert len(records) >= 1

    def test_ch_records_start_with_ch(self) -> None:
        records = list(self._client().iter_ch_records())
        assert all(r.startswith("CH") for r in records)

    def test_ra_record_length_sufficient_for_parser(self) -> None:
        records = list(self._client().iter_ra_records("20260618", "20260618"))
        assert all(len(r) >= 91 for r in records), "RA レコードが解析に必要な最小長を満たさない"

    def test_se_entry_parseable(self) -> None:
        from ingestion.parser.se_parser import parse_se_entry
        records = list(self._client().iter_se_records("20260618", "20260618"))
        entries = [parse_se_entry(r) for r in records if r[2] in ("1", "2")]
        assert any(e is not None for e in entries)

    def test_um_parseable(self) -> None:
        from ingestion.parser.master_parsers import parse_um
        records = list(self._client().iter_um_records())
        horses = [parse_um(r) for r in records]
        assert any(h is not None for h in horses)


class TestFixtureClientFromTxt:
    """TXT フィクスチャファイルから読み込むケース（RA/KS/CH サンプルが存在する場合）。"""

    def _client(self) -> FixtureJvLinkClient:
        return FixtureJvLinkClient(fixtures_dir=_FIXTURES)

    def test_ks_txt_file_parseable(self) -> None:
        from ingestion.parser.master_parsers import parse_ks
        records = list(self._client().iter_ks_records())
        jockeys = [parse_ks(r) for r in records]
        assert any(j is not None for j in jockeys)

    def test_ch_txt_file_parseable(self) -> None:
        from ingestion.parser.master_parsers import parse_ch
        records = list(self._client().iter_ch_records())
        trainers = [parse_ch(r) for r in records]
        assert any(t is not None for t in trainers)
