"""ForecastRaceUseCase 単体テスト（FakeRepository 使用）。"""

from __future__ import annotations

import datetime
import re

import pytest

from pci.application.dto import EntryInput, RaceInfo
from pci.application.forecast_use_cases import ForecastRaceUseCase
from pci.application.race_use_cases import RegisterRaceEntriesUseCase
from pci.domain.pace.ability import AbilityScorer, AbilityWeights
from pci.domain.pace.rpci_forecast import PaceLabel, RaceContext, RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.racing.master import Horse
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from pci.domain.shared.reason import Reason
from tests.unit.application.fake_mart_repository import FakeMartRepository
from tests.unit.application.fake_repository import FakeRaceRepository


class _RepoWithSuppressedPastRace(FakeRaceRepository):
    """_build_affinity_profile の past_race is None ブランチを叩くための偽実装。

    find_horse_recent_entries は過去走を返すが、find_by_key がその race_key に対して
    None を返すシナリオをシミュレートする（削除済みレースなど）。
    """

    def __init__(self, suppress_key: str) -> None:
        super().__init__()
        self._suppress_key = suppress_key

    def find_by_key(self, key: RaceKey) -> Race | None:
        if str(key) == self._suppress_key:
            return None
        return super().find_by_key(key)


UPCOMING = "2026062005010101"
RACE_DATE = datetime.date(2026, 6, 20)


def _register_upcoming(
    repo: FakeRaceRepository,
    n: int = 6,
    distance_m: int = 1600,
    *,
    draw_confirmed: bool = True,
    race_date: datetime.date = RACE_DATE,
    jyo_cd: str = "05",
    track_condition: str = "良",
) -> None:
    info = RaceInfo(
        race_key=UPCOMING,
        race_date=race_date,
        jyo_cd=jyo_cd,
        distance_m=distance_m,
        track_type="芝",
        field_size=n,
        track_condition=track_condition,
    )
    entries = [
        EntryInput(
            horse_no=i,
            frame_no=i if draw_confirmed else 0,
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
    race_s3f: float | None = None,
    race_l3f: float | None = None,
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
                race_s3f=race_s3f,
                race_l3f=race_l3f,
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


def _seed_mixed_distance_history(repo: FakeRaceRepository, ketto_num: str) -> None:
    """先行と差しが半々で、先行歴が対象より短距離にある履歴を作る。"""
    runs = ((4, 1200), (7, 1600), (4, 1200), (7, 1600))
    for index, (corner, distance) in enumerate(runs, start=1):
        race_key = RaceKey(f"202604{index:02d}05010188")
        repo.save_race(
            Race(
                race_key=race_key,
                race_date=datetime.date(2026, 4, index),
                jyo_cd="05",
                distance_m=distance,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=race_key,
                horse_no=1,
                frame_no=1,
                ketto_num=ketto_num,
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=3,
                corner_4=corner,
            )
        )


def _seed_course_history(
    repo: FakeRaceRepository,
    ketto_num: str,
    runs: tuple[tuple[int, str, int], ...],
) -> None:
    """距離・馬場状態・着順を指定したコース適性用の履歴を作る。"""
    for index, (distance_m, track_condition, finish_pos) in enumerate(runs, start=10):
        race_key = RaceKey(f"202604{index:02d}05010177")
        repo.save_race(
            Race(
                race_key=race_key,
                race_date=datetime.date(2026, 4, index),
                jyo_cd="05",
                distance_m=distance_m,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
                track_condition=track_condition,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=race_key,
                horse_no=1,
                frame_no=1,
                ketto_num=ketto_num,
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=finish_pos,
                corner_4=4,
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


class _CapturingForecaster(_FixedForecaster):
    def __init__(self) -> None:
        super().__init__(50.0, PaceLabel.AVERAGE)
        self.context: RaceContext | None = None

    def forecast(self, context: RaceContext) -> RpciForecast:
        self.context = context
        return super().forecast(context)


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
        assert output.model_version == "rule-v4"
        assert 35.0 <= output.predicted_rpci <= 65.0
        assert output.pace_label in ("ハイ", "平均", "スロー")
        assert output.scenario_headline
        assert output.scenario_detail
        assert len(output.horses) == 6
        assert output.formation is not None
        assert output.formation.model_version == "formation-v1"
        assert [group.label for group in output.formation.groups] == [
            "先頭",
            "好位",
            "中団",
            "後方",
        ]

    def test_ability_score_respects_configured_recent_races(self) -> None:
        """`AbilityWeights.recent_races`が呼び出し側の履歴切り詰めで無効化されない回帰テスト。

        以前は`_build_ability_score`が`history[:5]`と別途ハードコードしており、
        `recent_races`を10などへ変えてもドメイン層に渡る時点で既に5走に
        切り詰められ、設定が反映されない不具合があった。
        """
        target_race = Race(
            race_key=RaceKey(UPCOMING),
            race_date=RACE_DATE,
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=12,
            status=RaceStatus.ENTRIES,
        )
        # 直近5走（1〜5走前）は不振の未勝利戦、6〜8走前はG1好走という8走分の履歴。
        # 日数は最大56日前までに収め、新しさ減衰（180日以内=満額）の影響を排除する。
        history: list[tuple[RaceEntry, Race]] = []
        for i in range(8):
            is_old_good_run = i >= 5
            race_date = RACE_DATE - datetime.timedelta(days=(i + 1) * 7)
            past_race = Race(
                race_key=RaceKey(f"202601{i + 1:02d}05010101"),
                race_date=race_date,
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=12,
                status=RaceStatus.RESULT,
                grade="G1" if is_old_good_run else None,
            )
            entry = RaceEntry(
                race_key=past_race.race_key,
                horse_no=1,
                frame_no=1,
                ketto_num="2020000001",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=1 if is_old_good_run else 11,
            )
            history.append((entry, past_race))

        default_use_case = ForecastRaceUseCase(FakeRaceRepository())
        wider_use_case = ForecastRaceUseCase(
            FakeRaceRepository(),
            ability_scorer=AbilityScorer(AbilityWeights(recent_races=10)),
        )

        default_score = default_use_case._build_ability_score(
            1, "2020000001", target_race, tuple(history)
        )
        wider_score = wider_use_case._build_ability_score(
            1, "2020000001", target_race, tuple(history)
        )

        assert default_score.sample_size == 5
        assert wider_score.sample_size == 8
        assert wider_score.score > default_score.score

    def test_formation_is_hidden_before_draw_confirmation(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=2, draw_confirmed=False)
        _seed_history(repo, "2020100001", corner4=1, corner1=1)

        output = ForecastRaceUseCase(
            repo, forecaster=_FixedForecaster(55.0, PaceLabel.SLOW)
        ).execute(UPCOMING)

        assert output.formation is None
        assert "登録順 1（馬番未確定）" in output.scenario_detail
        assert output.comment is not None
        assert "登録順 1（馬番未確定）" in "".join(output.comment.body)
        assert "1番" not in output.scenario_detail

    def test_scenario_uses_official_number_after_draw_confirmation(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=2, draw_confirmed=True)
        _seed_history(repo, "2020100001", corner4=1, corner1=1)

        output = ForecastRaceUseCase(
            repo, forecaster=_FixedForecaster(55.0, PaceLabel.SLOW)
        ).execute(UPCOMING)

        assert output.formation is not None
        assert "1番" in output.scenario_detail
        assert output.comment is not None
        assert "1番" in "".join(output.comment.body)
        assert "登録順" not in output.scenario_detail

    def test_horse_fit_frame_no_reflects_draw_confirmation(self) -> None:
        """frame_no は枠順確定状態をそのまま反映する（未確定時は0、馬番を確定扱いしない）。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6, draw_confirmed=False)

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert all(h.frame_no == 0 for h in output.horses)

        repo_confirmed = FakeRaceRepository()
        _register_upcoming(repo_confirmed, n=6, draw_confirmed=True)
        confirmed_output = ForecastRaceUseCase(repo_confirmed).execute(UPCOMING)

        by_no = {h.horse_no: h.frame_no for h in confirmed_output.horses}
        assert by_no == {i: i for i in range(1, 7)}

    def test_style_advantage_reflects_pace_direction(self) -> None:
        """スロー想定なら前有利、ハイ想定なら後有利のスコアになる（50=互角）。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=4)

        slow_case = ForecastRaceUseCase(
            repo, forecaster=_FixedForecaster(55.0, PaceLabel.SLOW)
        ).execute(UPCOMING)
        assert slow_case.style_advantage is not None
        assert slow_case.style_advantage.model_version == "style-advantage-v3"
        assert slow_case.style_advantage.reliability == "standard"
        slow_scores = {entry.style: entry.score for entry in slow_case.style_advantage.entries}
        assert slow_scores["先行"] > 50 > slow_scores["差し"]
        assert slow_case.style_advantage.reasons

        high_case = ForecastRaceUseCase(
            repo, forecaster=_FixedForecaster(45.0, PaceLabel.HIGH)
        ).execute(UPCOMING)
        assert high_case.style_advantage is not None
        high_scores = {entry.style: entry.score for entry in high_case.style_advantage.entries}
        assert high_scores["差し"] > 50 > high_scores["先行"]

    def test_kokura_turf_in_july_marks_style_advantage_as_reference(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(
            repo,
            n=4,
            distance_m=1200,
            race_date=datetime.date(2026, 7, 19),
            jyo_cd="10",
        )

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.style_advantage is not None
        assert output.style_advantage.reliability == "reference"
        assert "小倉芝1200m" in (output.style_advantage.reliability_reason or "")

    def test_formation_uses_horse_names_and_frame_numbers(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=2)
        repo.save_horse(Horse(ketto_num="2020100001", name="隊列サンプル"))
        _seed_history(repo, "2020100001", corner4=1, corner1=1)

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.formation is not None
        formation_horses = [horse for group in output.formation.groups for horse in group.horses]
        target = next(horse for horse in formation_horses if horse.horse_no == 1)
        assert target.frame_no == 1
        assert target.horse_name == "隊列サンプル"
        assert target.running_style == "逃げ"
        assert target.reasons

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

    def test_mixed_style_is_resolved_for_target_distance(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        _seed_mixed_distance_history(repo, "2020100001")

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.horses[0].running_style == "先行"
        assert output.formation is not None
        formation_horse = next(
            horse
            for group in output.formation.groups
            for horse in group.horses
            if horse.horse_no == 1
        )
        assert formation_horse.running_style == "先行"

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

    def test_field_front_pace_evidence_uses_past_history_for_all_styles(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        _seed_history(
            repo,
            "2020100001",
            corner4=12,
            corner1=1,
            pci_actual=44.0,
            count=3,
        )
        forecaster = _CapturingForecaster()

        ForecastRaceUseCase(repo, forecaster=forecaster).execute(UPCOMING)

        assert forecaster.context is not None
        assert forecaster.context.running_styles == (RunningStyleLabel.CLOSER,)
        assert forecaster.context.front_pace_samples == ()
        assert len(forecaster.context.field_front_pace_samples) == 1
        sample = forecaster.context.field_front_pace_samples[0]
        assert sample.avg_pci == 44.0
        assert sample.sample_size == 3

    def test_historical_lap_evidence_uses_only_past_races_with_both_laps(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        _seed_history(
            repo,
            "2020100001",
            corner4=5,
            count=3,
            race_s3f=35.0,
            race_l3f=37.0,
        )
        forecaster = _CapturingForecaster()

        ForecastRaceUseCase(repo, forecaster=forecaster).execute(UPCOMING)

        assert forecaster.context is not None
        assert len(forecaster.context.historical_lap_samples) == 1
        sample = forecaster.context.historical_lap_samples[0]
        assert sample.horse_no == 1
        assert sample.avg_lap_delta == 2.0
        assert sample.sample_size == 3

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

        assert (UPCOMING, "rule-v4") in mart_repo.predicted_pace
        assert len(mart_repo.pace_fit) == 4
        assert all(key[2] == "pai-v2" for key in mart_repo.pace_fit)

    def test_mart_not_called_when_no_repo(self) -> None:
        """mart_repo が None の場合、永続化なしで算出結果を返す。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=3)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert len(output.horses) == 3

    def test_forecast_includes_natural_language_comment(self) -> None:
        """展開予想に自然文コメント（comment-v2）が付与される。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=6)
        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert output.comment is not None
        assert output.comment.headline
        assert output.comment.body  # 段落本文あり
        assert output.comment.model_version == "comment-v2"
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

    def test_empty_ketto_num_resolves_to_flexible(self) -> None:
        """ketto_num が空の出走馬は脚質「自在」として扱われる。"""
        repo = FakeRaceRepository()
        repo.save_race(
            Race(
                race_key=RaceKey(UPCOMING),
                race_date=RACE_DATE,
                jyo_cd="05",
                distance_m=1600,
                track_type="芝",
                field_size=1,
                status=RaceStatus.ENTRIES,
            )
        )
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(UPCOMING),
                horse_no=1,
                frame_no=1,
                ketto_num="",  # ← 空 ketto_num
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
            )
        )
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert output.horses[0].running_style == "自在"

    def test_front_style_entry_not_led_is_excluded_from_pace_sample(self) -> None:
        """逃げ・先行馬でも corner_1 が高い（前付けなし）エントリは pace sample に使わない。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        # 3 走 corner_1=1（前付け）→ ESCAPE 脚質確定 + front_pace_sample あり
        _seed_history(repo, "2020100001", corner4=1, corner1=1, pci_actual=52.0, count=3)
        # 1 走 corner_1=5（前付けなし）→ _led_from_front returns False → line 179 continue
        rk = "2026040105010101"
        repo.save_race(
            Race(
                race_key=RaceKey(rk),
                race_date=datetime.date(2026, 4, 1),
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
                ketto_num="2020100001",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=4,
                corner_1=5,  # 前付けなし
                corner_4=3,
                pci_actual=44.0,
            )
        )
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        # front_pace_sample は corner_1=1 の3走のみが採用される
        assert any(r.code == "front_pace_evidence" for r in output.forecast_reasons)

    def test_no_corner_data_not_counted_as_front_led(self) -> None:
        """corner_1 / corner_4 が共に None のエントリは前付けとみなさない。"""
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1)
        _seed_history(repo, "2020100001", corner4=1, corner1=1, pci_actual=52.0, count=3)
        # corner なし → _led_from_front returns False at line 233
        rk = "2026040205010101"
        repo.save_race(
            Race(
                race_key=RaceKey(rk),
                race_date=datetime.date(2026, 4, 2),
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
                ketto_num="2020100001",
                weight=480.0,
                jockey_code="J001",
                trainer_code="T001",
                finish_pos=1,
                corner_1=None,
                corner_4=None,
            )
        )
        # エラーなく予測が返ること
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert output.race_key == UPCOMING

    def test_affinity_profile_skips_entry_when_past_race_missing(self) -> None:
        """_build_affinity_profile: find_by_key が None を返す過去走はスキップする。"""
        suppressed_key = "2026050105010101"  # _seed_history が i=0 に使う race_key
        repo = _RepoWithSuppressedPastRace(suppress_key=suppressed_key)
        _register_upcoming(repo, n=1)
        _seed_history(repo, "2020100001", corner4=1, count=1, finish_pos=1, rpci_actual=48.0)
        # suppressed_key のレースは find_by_key が None → past_race is None → continue
        output = ForecastRaceUseCase(repo).execute(UPCOMING)
        assert output.race_key == UPCOMING

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

    def test_distance_aptitude_from_history_is_applied_to_pai(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1, distance_m=2000)
        _seed_course_history(
            repo,
            "2020100001",
            ((1200, "良", 1), (1200, "良", 2)),
        )

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        reason = next(r for r in output.horses[0].reasons if r.code == "distance_diff")
        assert "適性から外れる可能性" in reason.description

    def test_off_track_weakness_from_history_is_applied_to_pai(self) -> None:
        repo = FakeRaceRepository()
        _register_upcoming(repo, n=1, track_condition="重")
        _seed_course_history(
            repo,
            "2020100001",
            (
                (1600, "良", 1),
                (1800, "良", 2),
                (1400, "良", 1),
                (1600, "重", 9),
                (1800, "稍重", 10),
                (1400, "不良", 9),
            ),
        )

        output = ForecastRaceUseCase(repo).execute(UPCOMING)

        assert any(r.code == "off_track" for r in output.horses[0].reasons)
