"""ListRacesUseCase 単体テスト（FakeRepository 使用）。"""

from __future__ import annotations

import datetime

from pci.application.race_query_use_cases import ListRacesUseCase
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_repository import FakeRaceRepository


def _race(race_key: str, day: int, status: RaceStatus = RaceStatus.ENTRIES) -> Race:
    return Race(
        race_key=RaceKey(race_key),
        race_date=datetime.date(2026, 6, day),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=12,
        status=status,
        grade="G1",
        race_class="テストステークス",
    )


class TestListRacesUseCase:
    def test_empty_repo_returns_empty_list(self) -> None:
        uc = ListRacesUseCase(FakeRaceRepository())
        assert uc.execute() == []

    def test_returns_summary_fields(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(_race("2026062005010111", day=20, status=RaceStatus.RESULT))
        out = ListRacesUseCase(repo).execute()
        assert len(out) == 1
        s = out[0]
        assert s.race_key == "2026062005010111"
        assert s.race_date == "2026-06-20"
        assert s.jyo_cd == "05"
        assert s.distance_m == 1600
        assert s.track_type == "芝"
        assert s.status == "result"
        assert s.field_size == 12
        assert s.grade == "G1"
        assert s.race_class == "テストステークス"

    def test_ordered_newest_first(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(_race("2026061705010101", day=17))
        repo.save_race(_race("2026062005010101", day=20))
        repo.save_race(_race("2026061805010101", day=18))
        out = ListRacesUseCase(repo).execute()
        dates = [s.race_date for s in out]
        assert dates == ["2026-06-20", "2026-06-18", "2026-06-17"]

    def test_respects_limit(self) -> None:
        repo = FakeRaceRepository()
        for d in range(1, 11):
            repo.save_race(_race(f"202606{d:02d}05010101", day=d))
        out = ListRacesUseCase(repo).execute(limit=3)
        assert len(out) == 3

    def test_limit_clamped_to_minimum_one(self) -> None:
        repo = FakeRaceRepository()
        repo.save_race(_race("2026062005010101", day=20))
        repo.save_race(_race("2026061705010101", day=17))
        out = ListRacesUseCase(repo).execute(limit=0)
        assert len(out) == 1  # 0 は 1 にクランプされる

    def test_jv_placeholder_grade_filtered_to_none(self) -> None:
        """grade が JV-Data プレースホルダ '@' の場合、API レスポンスで None になる。"""
        repo = FakeRaceRepository()
        race = Race(
            race_key=RaceKey("2026062005010111"),
            race_date=datetime.date(2026, 6, 20),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=12,
            status=RaceStatus.RESULT,
            grade="@",
            race_class="@",
        )
        repo.save_race(race)
        out = ListRacesUseCase(repo).execute()
        assert out[0].grade is None
        assert out[0].race_class is None

    def test_jv_placeholder_with_mojibake_padding_filtered_to_none(self) -> None:
        """'@' + 文字化けパディング（固定長フィールド残留）も None になる。"""
        repo = FakeRaceRepository()
        # DB実データ: "@" + CP932 パディングが文字化けした文字列
        mojibake_at = "@縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲縲・ｽ"
        race = Race(
            race_key=RaceKey("2026062005010112"),
            race_date=datetime.date(2026, 6, 20),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=12,
            status=RaceStatus.RESULT,
            grade=None,
            race_class=mojibake_at,
        )
        repo.save_race(race)
        out = ListRacesUseCase(repo).execute()
        assert out[0].race_class is None

    def test_limit_clamped_to_maximum(self) -> None:
        repo = FakeRaceRepository()
        for d in range(1, 11):
            repo.save_race(_race(f"202606{d:02d}05010101", day=d))
        # 上限 100 を超える指定でも例外にならず全件（10件）返る
        out = ListRacesUseCase(repo).execute(limit=9999)
        assert len(out) == 10
