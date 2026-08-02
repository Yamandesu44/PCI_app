"""batch.py の E2E テスト。

fixture ファイル → パーサ → IngestApiClient（モック）の全パスを検証する。
DB / JV-Link なしで実行可能。
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.batch import (
    _to_iso_date,
    includes_race_metadata,
    ingest_entries,
    ingest_masters,
    ingest_race_metadata,
    ingest_results,
    iter_date_chunks,
    main,
    precompute_forecasts,
)
from ingestion.client.fixture_client import (
    FixtureJvLinkClient,
    _json_result_to_se,
    _json_to_ra,
)
from ingestion.ingest_api import IngestApiClient
from ingestion.models import DuplicateDeleteGuard, RaceMetadataRecord

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_RACE_KEY = "2026061805010101"


def _client() -> FixtureJvLinkClient:
    return FixtureJvLinkClient(fixtures_dir=_FIXTURES)


class _MetadataFixtureClient(FixtureJvLinkClient):
    def race_metadata(self, race_key: str) -> RaceMetadataRecord | None:
        if race_key != _RACE_KEY:
            return None
        return RaceMetadataRecord(
            race_key=race_key,
            track_condition="稍重",
            weather="小雨",
        )

    def iter_race_metadata(self, date_from: str, date_to: str) -> Iterator[RaceMetadataRecord]:
        del date_from, date_to
        metadata = self.race_metadata(_RACE_KEY)
        assert metadata is not None
        yield metadata


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


class TestMetadataStepSelection:
    def test_all_includes_metadata_for_mykeibadb(self) -> None:
        assert includes_race_metadata("all", "mykeibadb") is True

    def test_all_does_not_require_metadata_for_other_sources(self) -> None:
        assert includes_race_metadata("all", "fixture") is False
        assert includes_race_metadata("all", "jvlink") is False

    def test_explicit_metadata_step_is_always_selected(self) -> None:
        assert includes_race_metadata("race-metadata", "mykeibadb") is True


class TestToIsoDate:
    def test_converts_yyyymmdd_to_iso(self) -> None:
        """ingest_log API 送信用に YYYYMMDD → ISO 8601 (date_from_datetime_inexact 対策)。"""
        assert _to_iso_date("20260706") == "2026-07-06"

    def test_rejects_malformed_input(self) -> None:
        with pytest.raises(ValueError):
            _to_iso_date("2026-07-06")


class TestPrecomputeForecasts:
    def test_clamps_start_to_today(self) -> None:
        api = _mock_api()
        api.precompute_forecasts.return_value = {
            "scanned": 12,
            "generated": 10,
            "skipped": 2,
        }

        result = precompute_forecasts(
            api,
            "20260701",
            "20260726",
            today=__import__("datetime").date(2026, 7, 22),
        )

        assert result["generated"] == 10
        api.precompute_forecasts.assert_called_once_with("2026-07-22", "2026-07-26")

    def test_skips_range_entirely_in_past(self) -> None:
        api = _mock_api()

        result = precompute_forecasts(
            api,
            "20260701",
            "20260702",
            today=__import__("datetime").date(2026, 7, 22),
        )

        assert result == {"scanned": 0, "generated": 0, "skipped": 0}
        api.precompute_forecasts.assert_not_called()


class _MetadataClient:
    def iter_race_metadata(self, date_from: str, date_to: str) -> Iterator[RaceMetadataRecord]:
        del date_from, date_to
        yield RaceMetadataRecord(
            race_key=_RACE_KEY,
            track_condition="稍重",
            weather="小雨",
        )

    def race_metadata(self, race_key: str) -> RaceMetadataRecord | None:
        del race_key
        return None


class TestIngestRaceMetadata:
    def test_sends_source_metadata_to_api(self) -> None:
        api = _mock_api()
        api.update_race_metadata.return_value = 1

        accepted = ingest_race_metadata(
            _MetadataClient(),
            api,
            "20260618",
            "20260618",
        )

        assert accepted == 1
        records = api.update_race_metadata.call_args.args[0]
        assert records == [
            RaceMetadataRecord(
                race_key=_RACE_KEY,
                track_condition="稍重",
                weather="小雨",
            )
        ]


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

    def test_applies_structured_source_metadata(self) -> None:
        api = _mock_api()
        client = _MetadataFixtureClient(fixtures_dir=_FIXTURES)

        ingest_entries(client, api, "20260618", "20260618")

        record = api.register_entries.call_args.args[0]
        assert record.track_condition == "稍重"
        assert record.weather == "小雨"

    def test_horse_supplement_upsert_called(self) -> None:
        """SE エントリから馬マスタ補完が行われること。"""
        api = _mock_api()
        ingest_entries(_client(), api, "20260618", "20260618")
        assert api.upsert_horses.called


# ---------------------------------------------------------------------------
# 確定成績取り込み
# ---------------------------------------------------------------------------


class TestIngestResults:
    def test_refreshes_final_entry_snapshot_before_results(self) -> None:
        api = _mock_api()

        ingest_results(_client(), api, "20260618", "20260618")

        api.register_entries.assert_called_once()
        snapshot = api.register_entries.call_args.args[0]
        assert snapshot.race_key == _RACE_KEY
        assert snapshot.field_size == 3
        assert [entry.horse_no for entry in snapshot.entries] == [1, 2, 3]

    def test_limits_results_to_requested_race_keys(self) -> None:
        api = _mock_api()

        ingest_results(
            _client(),
            api,
            "20260618",
            "20260618",
            race_keys={"2099010101010101"},
        )

        api.register_entries.assert_not_called()
        api.record_results.assert_not_called()

    def test_replaces_stale_key_with_authoritative_race_key(self) -> None:
        api = _mock_api()
        stale_key = "2026061805999901"

        ingest_results(
            _client(),
            api,
            "20260618",
            "20260618",
            race_keys={stale_key},
        )

        api.delete_race.assert_called_once_with(stale_key)
        assert api.register_entries.call_args.args[0].race_key == _RACE_KEY
        assert api.record_results.call_args.args[0].race_key == _RACE_KEY
        method_names = [call[0] for call in api.method_calls]
        assert method_names.index("register_entries") < method_names.index("record_results")
        assert method_names.index("record_results") < method_names.index("delete_race")

    def test_keeps_stale_key_when_authoritative_result_sync_fails(self) -> None:
        api = _mock_api()
        api.record_results.side_effect = RuntimeError("result sync failed")
        stale_key = "2026061805999901"

        summary = ingest_results(
            _client(),
            api,
            "20260618",
            "20260618",
            race_keys={stale_key},
        )

        api.delete_race.assert_not_called()
        assert summary.sent_fail == 1
        assert summary.deleted_stale == 0

    def test_uses_guarded_delete_after_authoritative_result_sync(self) -> None:
        api = _mock_api()
        stale_key = "2026061805999901"
        guard = DuplicateDeleteGuard(
            stale_race_key=stale_key,
            canonical_race_key=_RACE_KEY,
            stale_entry_signature="e" * 64,
            stale_result_signature="r" * 64,
        )
        api.delete_duplicate_race.return_value = 1

        summary = ingest_results(
            _client(),
            api,
            "20260618",
            "20260618",
            race_keys={stale_key},
            duplicate_guards={_RACE_KEY: (guard,)},
        )

        api.delete_race.assert_not_called()
        api.delete_duplicate_race.assert_called_once_with(
            stale_race_key=stale_key,
            canonical_race_key=_RACE_KEY,
            expected_entry_count=3,
            expected_finished_count=3,
            stale_entry_signature="e" * 64,
            stale_result_signature="r" * 64,
        )
        assert summary.deleted_stale == 1

    def test_record_results_called_once(self) -> None:
        api = _mock_api()
        ingest_results(_client(), api, "20260618", "20260618")
        assert api.record_results.call_count == 1

    def test_applies_structured_source_metadata(self) -> None:
        api = _mock_api()
        client = _MetadataFixtureClient(fixtures_dir=_FIXTURES)

        ingest_results(client, api, "20260618", "20260618")

        record = api.record_results.call_args.args[0]
        assert record.track_condition == "稍重"
        assert record.weather == "小雨"

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

    def test_main_exits_nonzero_when_result_delivery_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        api = _mock_api()
        api.record_results.side_effect = RuntimeError("result sync failed")
        monkeypatch.setattr("ingestion.batch.IngestApiClient", lambda **_: api)
        monkeypatch.setattr("ingestion.batch._build_client", lambda *_args, **_kwargs: _client())
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "batch.py",
                "--mode",
                "fixture",
                "--date",
                "20260618",
                "--step",
                "results",
            ],
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert api.log_batch.call_args.kwargs["status"] == "error"
        assert "失敗 1 レース" in api.log_batch.call_args.kwargs["error_msg"]


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
            {
                "horse_no": 1,
                "frame_no": 1,
                "ketto_num": "2023200001",
                "weight": 472.0,
                "jockey_code": "01001",
                "trainer_code": "01001",
                "sex": "牡",
                "horse_name": "カコウマ1",
            },
            {
                "horse_no": 2,
                "frame_no": 2,
                "ketto_num": "2023200002",
                "weight": 456.0,
                "jockey_code": "01002",
                "trainer_code": "01002",
                "sex": "牝",
                "horse_name": "カコウマ2",
            },
            {
                "horse_no": 3,
                "frame_no": 3,
                "ketto_num": "2023200003",
                "weight": 484.0,
                "jockey_code": "01003",
                "trainer_code": "01001",
                "sex": "牡",
                "horse_name": "カコウマ3",
            },
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
