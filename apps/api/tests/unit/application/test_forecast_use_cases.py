"""ForecastRaceUseCase 単体テスト（FakeRepository 使用）。"""

from __future__ import annotations

import datetime
import re

import pytest

from pci.application.dto import EntryInput, RaceInfo
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_use_cases import RegisterRaceEntriesUseCase
from pci.domain.pace.rpci_forecast import PaceLabel, RaceContext, RpciForecast
from pci.domain.racing.master import Horse
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason
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


def _seed_history(
    repo: FakeRaceRepository,
    ketto_num: str,
    corner4: int,
    count: int = 3,
    *,
    rpci_actual: float | None = None,
    finish_pos: int = 3,
    grade: str | None = None,
    corner1: int | None = None,
    pci_actual: float | None = None,
) -> None:
    """指定馬に、確定済みの過去走（4角通過順位 corner4）を count 走分与える。"""
    # FakeRepository は (race_key, horse_no) でエントリを保持するため、複数馬を
    # 同一 race_key・同一 horse_no で seed すると相互に上書きされてしまう。
    # 馬ごとに血統番号末尾から異なる horse_no を割り当てて衝突を防ぐ。
    hist_horse_no = int(ketto_num[-2:]) if ketto_num[-2:].isdigit() else 1
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
                grade=grade,
                rpci_actual=rpci_actual,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(rk),
                horse_no=hist_horse_no,
                frame_no=hist_horse_no,
                ketto_num=ketto_num,
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=finish_pos,
                corner_1=corner1,
                corner_4=corner4,
                pci_actual=pci_actual,
            )
        )


class _FixedForecaster:
    def __init__(self, value: float, label: PaceLabel) -> None:
        self._forecast = RpciForecast(
            value=value,
            label=label,
            confidence=0.7,
            model_version="fixed-test",
            reasons=(Reason(code="fixed", description="テスト用の固定予想"),),
        )

    def forecast(self, context: RaceContext) -> RpciForecast:
        return self._forecast


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
        assert output.model_version == "rule-v3"
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

    def test_front_pace_history_shifts_prediction(self) -> None:
        """rule-v2: 同じ脚質構成でも、前付け時の実績ペースで想定RPCIが動く。

        全馬を逃げ（4角1番手）に仕立てた2レースで、前で運んだ過去走の個馬PCIだけを
        変える。緩める履歴（高PCI）の方が、飛ばす履歴（低PCI）よりスロー寄りになる。
        """
        repo_slow = FakeRaceRepository()
        repo_fast = FakeRaceRepository()
        _register_upcoming(repo_slow, n=4)
        _register_upcoming(repo_fast, n=4)
        for i in range(1, 5):
            ketto = f"202010000{i}"
            _seed_history(repo_slow, ketto, corner4=1, corner1=1, pci_actual=58.0, count=5)
            _seed_history(repo_fast, ketto, corner4=1, corner1=1, pci_actual=43.0, count=5)

        slow = ForecastRaceUseCase(repo_slow).execute(UPCOMING)
        fast = ForecastRaceUseCase(repo_fast).execute(UPCOMING)

        assert slow.predicted_rpci > fast.predicted_rpci
        assert any(r.code == "front_pace_evidence" for r in slow.forecast_reasons)

    def test_closer_history_does_not_build_front_evidence(self) -> None:
        """差し・追込馬の履歴は前付け証拠に使われない（rule-v1 相当へフォールバック）。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=4)
        for i in range(1, 5):
            # 4角12番手（追込）→ 前付けではない → front_pace_evidence は出ない
            _seed_history(repo, f"202010000{i}", corner4=12, pci_actual=44.0, count=5)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert not any(r.code == "front_pace_evidence" for r in output.forecast_reasons)

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

        assert (UPCOMING, "rule-v3") in mart_repo.predicted_pace
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

    def test_high_pace_good_run_gets_higher_fit_when_predicted_high(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=2)
        _seed_history(repo, "2020100001", corner4=10, rpci_actual=46.0, finish_pos=1)
        _seed_history(repo, "2020100002", corner4=1, rpci_actual=56.0, finish_pos=1)

        output = ForecastRaceUseCase(
            repo,
            forecaster=_FixedForecaster(46.0, PaceLabel.HIGH),
        ).execute(UPCOMING)

        by_no = {horse.horse_no: horse for horse in output.horses}
        assert by_no[1].pai > by_no[2].pai
        assert any("過去の好走" in reason.description for reason in by_no[1].reasons)

    def test_horse_reasons_hide_raw_pci_values(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        _seed_history(repo, "2020100001", corner4=10, rpci_actual=46.0, finish_pos=1)

        output = ForecastRaceUseCase(
            repo,
            forecaster=_FixedForecaster(46.0, PaceLabel.HIGH),
        ).execute(UPCOMING)

        descriptions = " ".join(reason.description for reason in output.horses[0].reasons)
        assert "PCI" not in descriptions
        assert "RPCI" not in descriptions
        assert re.search(r"\d+\.\d+", descriptions) is None
