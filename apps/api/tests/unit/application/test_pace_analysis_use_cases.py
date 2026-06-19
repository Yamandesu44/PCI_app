"""GetPaceAnalysisUseCase 単体テスト（FakeRepository 使用）。"""

from __future__ import annotations

import datetime

import pytest

from pci.application.dto import EntryInput, RaceInfo, ResultInput
from pci.application.errors import RaceNotConfirmedError
from pci.application.race_query_use_cases import GetPaceAnalysisUseCase
from pci.application.race_use_cases import RecordRaceResultUseCase, RegisterRaceEntriesUseCase
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_repository import FakeRaceRepository

CONFIRMED = "2026061705010101"
UPCOMING = "2026062005010101"


def _seed_confirmed(repo: FakeRaceRepository) -> None:
    info = RaceInfo(
        race_key=CONFIRMED,
        race_date=datetime.date(2026, 6, 17),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=3,
        track_condition="良",
    )
    entries = [
        EntryInput(
            horse_no=i,
            frame_no=i,
            ketto_num=f"202110000{i}",
            weight=480.0,
            jockey_code=f"J10{i}",
            trainer_code=f"T10{i}",
        )
        for i in range(1, 4)
    ]
    RegisterRaceEntriesUseCase(repo).execute(info, entries)
    results = [
        ResultInput(horse_no=1, finish_pos=1, race_time_s=94.4, agari_3f_s=34.0, corner_4=2),
        ResultInput(horse_no=2, finish_pos=2, race_time_s=94.6, agari_3f_s=34.2, corner_4=1),
        ResultInput(horse_no=3, finish_pos=3, race_time_s=95.0, agari_3f_s=34.5, corner_4=4),
    ]
    RecordRaceResultUseCase(repo).execute(CONFIRMED, results, track_condition="良")


class TestGetPaceAnalysisUseCase:
    def test_race_not_found_raises(self) -> None:
        with pytest.raises(ValueError, match="見つかりません"):
            GetPaceAnalysisUseCase(FakeRaceRepository()).execute(CONFIRMED)

    def test_unconfirmed_race_raises(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(
            Race(
                race_key=RaceKey(UPCOMING),
                race_date=datetime.date(2026, 6, 20),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=0,
                status=RaceStatus.ENTRIES,
            )
        )
        with pytest.raises(RaceNotConfirmedError, match="確定していません"):
            GetPaceAnalysisUseCase(repo).execute(UPCOMING)

    def test_confirmed_returns_pci_metrics(self) -> None:
        repo = FakeRaceRepository()
        _seed_confirmed(repo)
        out = GetPaceAnalysisUseCase(repo).execute(CONFIRMED)

        assert out.race_key == CONFIRMED
        assert out.formula_version == "pci-v1"
        assert out.field_size == 3
        assert out.sample_size == 3
        assert out.rpci_actual is not None
        assert out.pci3_actual is not None
        assert len(out.horses) == 3
        for h in out.horses:
            assert h.pci is not None
        assert out.reasons  # 説明可能性

    def test_horses_sorted_by_finish_and_marked_pci3(self) -> None:
        repo = FakeRaceRepository()
        _seed_confirmed(repo)
        out = GetPaceAnalysisUseCase(repo).execute(CONFIRMED)

        assert [h.finish_pos for h in out.horses] == [1, 2, 3]
        # 全馬が3着以内 → 全頭が PCI3 寄与
        assert all(h.is_pci3_contributor for h in out.horses)

    def test_rpci_matches_aggregate_of_entry_pcis(self) -> None:
        repo = FakeRaceRepository()
        _seed_confirmed(repo)
        out = GetPaceAnalysisUseCase(repo).execute(CONFIRMED)

        pcis = [h.pci for h in out.horses if h.pci is not None]
        expected = round(sum(pcis) / len(pcis), 1)
        assert out.rpci_actual == pytest.approx(expected)

    def test_includes_review_comment(self) -> None:
        """確定後ペース分析に自然文の回顧コメント（comment-v1）が付く。"""
        repo = FakeRaceRepository()
        _seed_confirmed(repo)
        out = GetPaceAnalysisUseCase(repo).execute(CONFIRMED)

        assert out.comment is not None
        assert out.comment.headline
        assert out.comment.body
        assert out.comment.model_version == "comment-v1"
        assert out.comment.reasons
