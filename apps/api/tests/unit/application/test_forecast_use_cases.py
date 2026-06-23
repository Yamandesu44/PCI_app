"""ForecastRaceUseCase 単体テスト（FakeRepository 使用）。"""

from __future__ import annotations

import datetime

import pytest

from pci.application.dto import EntryInput, RaceInfo
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_use_cases import RegisterRaceEntriesUseCase
from pci.domain.racing.master import Horse
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_mart_repository import FakeMartRepository
from tests.unit.application.fake_repository import FakeRaceRepository

UPCOMING = "2026062005010101"
RACE_DATE = datetime.date(2026, 6, 20)


def _register_upcoming(repo: FakeRaceRepository, n: int = 6, distance_m: int = 1600) -> None:
    info = RaceInfo(
        race_key=UPCOMING,
        race_date=RACE_DATE,
        jyo_cd="05",
        distance_m=distance_m,
        track_type="芝",
        field_size=n,
        track_condition="良",
    )
    entries = [
        EntryInput(
            horse_no=i,
            frame_no=i,
            ketto_num=f"202010000{i}",
            weight=480.0,
            jockey_code=f"J00{i}",
            trainer_code=f"T00{i}",
        )
        for i in range(1, n + 1)
    ]
    RegisterRaceEntriesUseCase(repo).execute(info, entries)


def _seed_history(repo: FakeRaceRepository, ketto_num: str, corner4: int, count: int = 3) -> None:
    """指定馬に、確定済みの過去走（4角通過順位 corner4）を count 走分与える。"""
    for i in range(count):
        rk = f"202605{i + 1:02d}05010101"
        repo.save_race(
            Race(
                race_key=RaceKey(rk),
                race_date=datetime.date(2026, 5, i + 1),
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(rk),
                horse_no=1,
                frame_no=1,
                ketto_num=ketto_num,
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=3,
                corner_4=corner4,
            )
        )


class TestForecastRaceUseCase:
    def test_race_not_found_raises(self) -> None:
        with pytest.raises(ValueError, match="レースが見つかりません"):
            ForecastRaceUseCase(FakeRaceRepository()).execute(UPCOMING)

    def test_no_entries_raises(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(
            Race(
                race_key=RaceKey(UPCOMING),
                race_date=RACE_DATE,
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=0,
                status=RaceStatus.ENTRIES,
            )
        )
        with pytest.raises(ValueError, match="出走馬が登録されていません"):
            ForecastRaceUseCase(repo).execute(UPCOMING)

    def test_forecast_returns_complete_output(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.race_key == UPCOMING
        assert output.model_version == "rule-v1"
        assert 35.0 <= output.predicted_rpci <= 65.0
        assert output.pace_label in ("ハイ", "平均", "スロー")
        assert output.scenario_headline
        assert output.scenario_detail
        assert len(output.horses) == 6

    def test_each_horse_has_pai_and_reasons(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=4)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        for h in output.horses:
            assert 0.0 <= h.pai <= 100.0
            assert h.fit_label in ("合致", "中立", "不利")
            assert h.reasons  # 説明可能性

    def test_forecast_includes_horse_names(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=2)
        repo.save_horse(Horse(ketto_num="2020100001", name="サンプルホース"))

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.horses[0].horse_name == "サンプルホース"

    def test_styles_derived_from_history(self) -> None:
        """過去走の4角順位から脚質が反映され、展開予想に効く。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6)
        # 全馬を逃げ（4角1番手）に仕立てる → ハイペース予測
        for i in range(1, 7):
            _seed_history(repo, f"202010000{i}", corner4=1)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert output.pace_label == "ハイ"

    def test_closers_field_predicts_slow(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6)
        # 全馬を追込（4角12番手）に仕立てる → スローペース予測
        for i in range(1, 7):
            _seed_history(repo, f"202010000{i}", corner4=12)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert output.pace_label == "スロー"

    def test_no_history_defaults_to_flexible(self) -> None:
        """履歴がない馬は自在扱いでもエラーにならない。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=5)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert all(h.running_style == "自在" for h in output.horses)

    def test_mart_saved_when_repo_injected(self) -> None:
        """mart_repo が注入された場合、predicted_pace と pace_fit が保存される。"""
        repo = FakeRaceRepository()
        mart_repo = FakeMartRepository()
        _register_upcoming(repo, n=4)

        ForecastRaceUseCase(repo, mart_repo=mart_repo).execute(UPCOMING)

        assert (UPCOMING, "rule-v1") in mart_repo.predicted_pace
        assert len(mart_repo.pace_fit) == 4
        assert all(key[2] == "pai-v1" for key in mart_repo.pace_fit)

    def test_mart_not_called_when_no_repo(self) -> None:
        """mart_repo が None の場合、永続化なしで算出結果を返す。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=3)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert len(output.horses) == 3

    def test_forecast_includes_natural_language_comment(self) -> None:
        """展開予想に自然文コメント（comment-v1）が付与される。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.comment is not None
        assert output.comment.headline
        assert output.comment.body  # 段落本文あり
        assert output.comment.model_version == "comment-v1"
        assert output.comment.reasons  # 説明可能性
