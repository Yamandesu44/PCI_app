"""batch.py の E2E テスト。

fixture ファイル → パーサ → IngestApiClient（モック）の全パスを検証する。
DB / JV-Link なしで実行可能。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.batch import (
    _to_iso_date,
    ingest_entries,
    ingest_masters,
    ingest_results,
    iter_date_chunks,
)
from ingestion.client.fixture_client import (
    FixtureJvLinkClient,
    _json_result_to_se,
    _json_to_ra,
)
from ingestion.ingest_api import IngestApiClient

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_RACE_KEY = "2026061805010101"


def _client() -> FixtureJvLinkClient:
    return FixtureJvLinkClient(fixtures_dir=_FIXTURES)


def _mock_api() -> MagicMock:
    api = MagicMock(spec=IngestApiClient)
    api.upsert_horses.return_value = 3
    api.upsert_jockeys.return_value = 2
    api.upsert_trainers.return_value = 2
    api.register_entries.return_value = 3
    api.record_results.return_value = {
        "race_key": _RACE_KEY,
        "rpci": 52.0,
        "pci3": 52.0,
        "formula_version": "pci-v1",
        "entry_pcis": {1: 52.7, 2: 49.7, 3: 53.5},
    }
    return api


class TestDateChunks:
    def test_returns_single_range_when_disabled(self) -> None:
        assert iter_date_chunks("20000101", "20000131", 0) == [("20000101", "20000131")]

    def test_splits_range_by_chunk_days(self) -> None:
        assert iter_date_chunks("20000101", "20000110", 4) == [
            ("20000101", "20000104"),
            ("20000105", "20000108"),
            ("20000109", "20000110"),
        ]

    def test_rejects_reversed_range(self) -> None:
        with pytest.raises(ValueError):
            iter_date_chunks("20000110", "20000101", 4)


class TestToIsoDate:
    def test_converts_yyyymmdd_to_iso(self) -> None:
        """ingest_log API 送信用に YYYYMMDD → ISO 8601 (date_from_datetime_inexact 対策)。"""
        assert _to_iso_date("20260706") == "2026-07-06"

    def test_rejects_malformed_input(self) -> None:
        with pytest.raises(ValueError):
            _to_iso_date("2026-07-06")


# ---------------------------------------------------------------------------
# FixtureJvLinkClient デフォルトパス
# ---------------------------------------------------------------------------


class TestFixtureClientDefaultPath:
    def test_default_fixtures_dir_exists(self) -> None:
        """デフォルトパスのバグ修正（parents[4] → parents[3]）を確認。"""
        client = FixtureJvLinkClient()  # fixtures_dir 未指定
        records = list(client.iter_ra_records("20260618", "20260618"))
        assert len(records) >= 1, "デフォルトパスで RA レコードが見つからない"

    def test_se_records_available_from_default_path(self) -> None:
        client = FixtureJvLinkClient()
        records = list(client.iter_se_records("20260618", "20260618"))
        assert len(records) >= 6, "JSON から 6 レコード（entry×3 + result×3）が必要"


# ---------------------------------------------------------------------------
# マスタデータ取り込み
# ---------------------------------------------------------------------------


class TestIngestMasters:
    def test_calls_upsert_horses(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        assert api.upsert_horses.called

    def test_horses_have_ketto_num(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        horses = api.upsert_horses.call_args[0][0]
        ketto_nums = {h.ketto_num for h in horses}
        assert ketto_nums == {"2023100001", "2023100002", "2023100003"}

    def test_calls_upsert_jockeys(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        assert api.upsert_jockeys.called

    def test_jockeys_have_codes(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        jockeys = api.upsert_jockeys.call_args[0][0]
        codes = {j.code for j in jockeys}
        assert len(codes) >= 1

    def test_calls_upsert_trainers(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        assert api.upsert_trainers.called

    def test_trainers_have_codes(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        trainers = api.upsert_trainers.call_args[0][0]
        codes = {t.code for t in trainers}
        assert len(codes) >= 1

    def test_does_not_call_race_endpoints(self) -> None:
        api = _mock_api()
        ingest_masters(_client(), api)
        api.register_entries.assert_not_called()
        api.record_results.assert_not_called()


# ---------------------------------------------------------------------------
# 出走表取り込み
# ---------------------------------------------------------------------------


class TestIngestEntries:
    def test_register_entries_called_once(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        assert api.register_entries.call_count == 1

    def test_race_key_correct(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        assert record.race_key == _RACE_KEY

    def test_three_entries_registered(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        assert len(record.entries) == 3

    def test_entry_ketto_nums_match_fixture(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        ketto_nums = {e.ketto_num for e in record.entries}
        assert ketto_nums == {"2023100001", "2023100002", "2023100003"}

    def test_entry_horse_numbers_sequential(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        horse_nos = sorted(e.horse_no for e in record.entries)
        assert horse_nos == [1, 2, 3]

    def test_entry_weights_positive(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        for e in record.entries:
            assert e.weight > 0

    def test_race_distance_correct(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        assert record.distance_m == 1600

    def test_race_track_type_correct(self) -> None:
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        record = api.register_entries.call_args[0][0]
        assert record.track_type == "芝"

    def test_horse_supplement_upsert_called(self) -> None:
        """SE エントリから馬マスタ補完が行われること。"""
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        assert api.upsert_horses.called


# ---------------------------------------------------------------------------
# 確定成績取り込み
# ---------------------------------------------------------------------------


class TestIngestResults:
    def test_record_results_called_once(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        assert api.record_results.call_count == 1

    def test_race_key_correct(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        assert record.race_key == _RACE_KEY

    def test_three_results_registered(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        assert len(record.results) == 3

    def test_finish_positions_are_1_2_3(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        finish_positions = sorted(r.finish_pos for r in record.results)
        assert finish_positions == [1, 2, 3]

    def test_race_times_positive(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        for r in record.results:
            assert r.race_time_s > 0

    def test_agari_3f_positive(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        for r in record.results:
            assert r.agari_3f_s > 0

    def test_winner_horse_no_is_3(self) -> None:
        """フィクスチャでは 3番馬が1着。"""
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        winner = next(r for r in record.results if r.finish_pos == 1)
        assert winner.horse_no == 3

    def test_winner_race_time_matches_fixture(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        winner = next(r for r in record.results if r.finish_pos == 1)
        assert abs(winner.race_time_s - 94.4) < 0.1

    def test_corners_unresolved_are_none(self) -> None:
        # コーナー通過順位の実バイト位置は未特定のため、現状は None（2レコード目で要校正）。
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        record = api.record_results.call_args[0][0]
        for r in record.results:
            assert r.corner_4 is None


# ---------------------------------------------------------------------------
# フルパイプライン
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_full_pipeline_calls_all_api_methods(self) -> None:
        """masters → entries → results の全ステップが API を呼び出す。"""
        api = _mock_api()
        client = _client()

        ingest_masters(client, api)
        ingest_entries(client, api, "20260618", "20260618")
        ingest_results(client, api, "20260618", "20260618")

        assert api.upsert_horses.called
        assert api.upsert_jockeys.called
        assert api.upsert_trainers.called
        assert api.register_entries.called
        assert api.record_results.called

    def test_entries_and_results_share_race_key(self) -> None:
        """出走表と成績が同じ race_key を使うこと。"""
        api = _mock_api()
        client = _client()

        ingest_entries(client, api, "20260618", "20260618")
        ingest_results(client, api, "20260618", "20260618")

        entry_race = api.register_entries.call_args[0][0]
        result_race = api.record_results.call_args[0][0]
        assert entry_race.race_key == result_race.race_key == _RACE_KEY


# ---------------------------------------------------------------------------
# 確定のみ取り込み（過去レースの実データ模擬）
# ---------------------------------------------------------------------------


class _ConfirmedOnlyClient:
    """RA + 確定SE(DataKubun=7)のみを返すクライアント（過去レースの実データ模擬）。

    過去レースは出走前(1/2)レコードが既に確定(7)へ置き換わっており、JV-Link は
    確定レコードしか返さない。確定から出走表を再構成できないと「出走馬なし」で
    レース未登録 → 成績送信が 404 になる（実際に発生した回帰）。
    """

    _PAST_KEY = "2026061302010101"

    def __init__(self) -> None:
        self._race_info = {
            "race_key": self._PAST_KEY,
            "distance_m": 1600,
            "track_type": "芝",
            "race_class": "3歳未勝利",
        }
        # 確定 SE に埋め込む出走情報（枠番・血統・騎手・調教師・馬体重）。
        self._entries = [
            {"horse_no": 1, "frame_no": 1, "ketto_num": "2023200001", "weight": 472.0,
             "jockey_code": "01001", "trainer_code": "01001", "sex": "牡", "horse_name": "カコウマ1"},
            {"horse_no": 2, "frame_no": 2, "ketto_num": "2023200002", "weight": 456.0,
             "jockey_code": "01002", "trainer_code": "01002", "sex": "牝", "horse_name": "カコウマ2"},
            {"horse_no": 3, "frame_no": 3, "ketto_num": "2023200003", "weight": 484.0,
             "jockey_code": "01003", "trainer_code": "01001", "sex": "牡", "horse_name": "カコウマ3"},
        ]
        self._results = [
            {"horse_no": 3, "finish_pos": 1, "race_time_s": 94.4, "agari_3f_s": 33.9},
            {"horse_no": 1, "finish_pos": 2, "race_time_s": 94.6, "agari_3f_s": 34.2},
            {"horse_no": 2, "finish_pos": 3, "race_time_s": 94.9, "agari_3f_s": 34.8},
        ]

    def iter_ra_records(self, date_from: str, date_to: str):  # type: ignore[no-untyped-def]
        yield _json_to_ra(self._race_info)

    def iter_se_records(self, date_from: str, date_to: str):  # type: ignore[no-untyped-def]
        index = {int(e["horse_no"]): e for e in self._entries}
        for result in self._results:
            yield _json_result_to_se(
                {"race_key": self._PAST_KEY}, result, index.get(int(result["horse_no"]))
            )

    def iter_um_records(self):  # type: ignore[no-untyped-def]
        return iter(())

    def iter_ks_records(self):  # type: ignore[no-untyped-def]
        return iter(())

    def iter_ch_records(self):  # type: ignore[no-untyped-def]
        return iter(())


class TestConfirmedOnlyIngest:
    _PAST_KEY = "2026061302010101"

    def test_entries_registered_from_confirmed_records(self) -> None:
        """確定のみでも出走表が登録される（「出走馬なし」回帰の防止）。"""
        api = _mock_api()
        ingest_entries(_ConfirmedOnlyClient(), api, "20260613", "20260613")
        assert api.register_entries.call_count == 1
        record = api.register_entries.call_args[0][0]
        assert record.race_key == self._PAST_KEY
        assert len(record.entries) == 3

    def test_entries_have_ketto_from_confirmed(self) -> None:
        """確定レコードから血統番号が取れている（空にならない）。"""
        api = _mock_api()
        ingest_entries(_ConfirmedOnlyClient(), api, "20260613", "20260613")
        record = api.register_entries.call_args[0][0]
        ketto_nums = {e.ketto_num for e in record.entries}
        assert ketto_nums == {"2023200001", "2023200002", "2023200003"}

    def test_entries_have_real_weight_from_bataijyu(self) -> None:
        """確定レコードの BaTaijyu から実馬体重が取れている。"""
        api = _mock_api()
        ingest_entries(_ConfirmedOnlyClient(), api, "20260613", "20260613")
        record = api.register_entries.call_args[0][0]
        weights = {e.horse_no: e.weight for e in record.entries}
        assert weights == {1: 472.0, 2: 456.0, 3: 484.0}

    def test_no_duplicate_entries(self) -> None:
        """馬番が重複しない（確定レコードを二重カウントしない）。"""
        api = _mock_api()
        ingest_entries(_ConfirmedOnlyClient(), api, "20260613", "20260613")
        record = api.register_entries.call_args[0][0]
        horse_nos = sorted(e.horse_no for e in record.entries)
        assert horse_nos == [1, 2, 3]

    def test_results_recorded_from_confirmed_records(self) -> None:
        """確定成績が記録される（レース未登録による 404 回帰の防止）。"""
        api = _mock_api()
        ingest_results(_ConfirmedOnlyClient(), api, "20260613", "20260613")
        assert api.record_results.call_count == 1
        record = api.record_results.call_args[0][0]
        assert record.race_key == self._PAST_KEY
        assert len(record.results) == 3
