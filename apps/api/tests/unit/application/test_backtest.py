"""バックテスト検証基盤の単体テスト。

純粋集計（summarize_rpci / summarize_pai_lift）と、FakeRepository を使った
エンドツーエンド（lookahead 防止を含む）を検証する。
"""

from __future__ import annotations

import datetime

from pci.application.backtest import (
    BacktestReport,
    ForecastBacktester,
    HorseSample,
    PaiBand,
    PaiLift,
    RpciAccuracy,
    RpciSample,
    _AsOfRaceRepository,
    format_report,
    group_races_by_track,
    summarize_pai_lift,
    summarize_rpci,
)
from pci.domain.pace.rpci_forecast import PaceLabel
from pci.domain.racing.master import Horse, Jockey, Trainer
from pci.domain.racing.race import Race, RaceStatus
from pci.domain.racing.race_entry import RaceEntry
from pci.domain.shared.race_key import RaceKey
from tests.unit.application.fake_repository import FakeRaceRepository

HIGH = PaceLabel.HIGH
AVERAGE = PaceLabel.AVERAGE
SLOW = PaceLabel.SLOW


def _rpci(predicted: float, actual: float, pl: PaceLabel, al: PaceLabel) -> RpciSample:
    return RpciSample(
        race_key="2026010105010101",
        predicted=predicted,
        actual=actual,
        predicted_label=pl,
        actual_label=al,
    )


class TestSummarizeRpci:
    def test_empty_returns_none(self) -> None:
        assert summarize_rpci([]) is None

    def test_error_metrics(self) -> None:
        samples = [
            _rpci(52.0, 50.0, SLOW, AVERAGE),  # error +2
            _rpci(48.0, 50.0, HIGH, AVERAGE),  # error -2
            _rpci(50.0, 50.0, AVERAGE, AVERAGE),  # error 0
        ]
        acc = summarize_rpci(samples)
        assert acc is not None
        assert acc.n == 3
        assert acc.mae == round(4 / 3, 3)  # (2+2+0)/3
        assert acc.bias == 0.0  # (+2-2+0)/3
        assert acc.rmse == round((8 / 3) ** 0.5, 3)

    def test_label_accuracy(self) -> None:
        samples = [
            _rpci(48.0, 48.0, HIGH, HIGH),  # 的中
            _rpci(52.0, 48.0, SLOW, HIGH),  # 外し
        ]
        acc = summarize_rpci(samples)
        assert acc is not None
        assert acc.label_accuracy == 0.5
        # 実績「ハイ」2件中1件を再現
        assert acc.per_label_accuracy[str(HIGH)] == 0.5


class TestSummarizePaiLift:
    @staticmethod
    def _h(pai: float, good: bool) -> HorseSample:
        return HorseSample(race_key="2026010105010101", horse_no=1, pai=pai, good_run=good)

    def test_empty_returns_none(self) -> None:
        assert summarize_pai_lift([]) is None

    def test_bands_and_baseline(self) -> None:
        samples = [
            self._h(10.0, False),
            self._h(30.0, False),
            self._h(90.0, True),
            self._h(95.0, True),
        ]
        lift = summarize_pai_lift(samples, band_edges=(0, 50, 100))
        assert lift is not None
        assert lift.baseline_rate == 0.5
        assert len(lift.bands) == 2
        low, high = lift.bands
        assert low.n == 2 and low.good_runs == 0
        assert high.n == 2 and high.good_runs == 2
        assert high.good_rate == 1.0
        # 最上位帯の好走率/ベースライン = 1.0/0.5
        assert lift.top_band_lift == 2.0

    def test_pai_100_lands_in_last_band(self) -> None:
        lift = summarize_pai_lift([self._h(100.0, True)], band_edges=(0, 50, 100))
        assert lift is not None
        assert lift.bands[-1].n == 1

    def test_positive_correlation_when_high_pai_good(self) -> None:
        samples = [self._h(p, p >= 50) for p in (10.0, 20.0, 80.0, 90.0)]
        lift = summarize_pai_lift(samples)
        assert lift is not None
        assert lift.point_biserial > 0


class TestGroupRacesByTrack:
    @staticmethod
    def _race(key: str, track_type: str) -> Race:
        return Race(
            race_key=RaceKey(key),
            race_date=datetime.date(2026, 6, 28),
            jyo_cd="05",
            distance_m=1600,
            track_type=track_type,
            field_size=1,
            status=RaceStatus.RESULT,
        )

    def test_groups_by_track_type(self) -> None:
        turf = self._race("2026062805010101", "芝")
        dirt1 = self._race("2026062805010102", "ダート")
        dirt2 = self._race("2026062805010103", "ダート")

        grouped = group_races_by_track([turf, dirt1, dirt2])

        assert set(grouped) == {"芝", "ダート"}
        assert grouped["芝"] == [turf]
        assert grouped["ダート"] == [dirt1, dirt2]

    def test_empty_input_returns_empty_dict(self) -> None:
        assert group_races_by_track([]) == {}


def _seed_result_race(
    repo: FakeRaceRepository,
    race_key: str,
    day: int,
    *,
    rpci_actual: float | None,
    horses: list[tuple[int, str, int | None]],  # (horse_no, ketto_num, finish_pos)
    grade: str | None = None,
) -> Race:
    race = Race(
        race_key=RaceKey(race_key),
        race_date=datetime.date(2026, 1, day),
        jyo_cd="05",
        distance_m=1600,
        track_type="芝",
        field_size=len(horses),
        status=RaceStatus.RESULT,
        grade=grade,
        rpci_actual=rpci_actual,
    )
    repo.save_race(race)
    for horse_no, ketto, finish in horses:
        repo.save_entry(
            RaceEntry(
                race_key=RaceKey(race_key),
                horse_no=horse_no,
                frame_no=horse_no,
                ketto_num=ketto,
                weight=55.0,
                jockey_code="00001",
                trainer_code="00001",
                finish_pos=finish,
                corner_4=horse_no,
                pci_actual=50.0,
            )
        )
    return race


class TestAsOfRepositoryPassthroughs:
    """_AsOfRaceRepository の素通しメソッドが inner に委譲することを確認する。"""

    def _make(self) -> tuple[FakeRaceRepository, _AsOfRaceRepository]:
        inner = FakeRaceRepository()
        return inner, _AsOfRaceRepository(inner, datetime.date(2026, 6, 28))

    def test_read_passthroughs(self) -> None:
        _, as_of = self._make()
        assert as_of.list_recent_races(5) == []
        assert as_of.list_race_dates() == []
        assert as_of.list_races_by_date(datetime.date(2026, 6, 28)) == []

    def test_race_write_passthroughs(self) -> None:
        inner, as_of = self._make()
        key = RaceKey("2026062805010101")
        race = Race(
            race_key=key,
            race_date=datetime.date(2026, 6, 28),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=1,
            status=RaceStatus.RESULT,
        )
        as_of.save_race(race)
        assert inner.find_by_key(key) is not None

        entry = RaceEntry(
            race_key=key,
            horse_no=1,
            frame_no=1,
            ketto_num="H001",
            weight=480.0,
            jockey_code="J001",
            trainer_code="T001",
        )
        as_of.save_entry(entry)
        assert len(inner.find_entries(key)) == 1

        assert as_of.delete_race(key) is True
        assert inner.find_by_key(key) is None

    def test_master_write_passthroughs(self) -> None:
        inner, as_of = self._make()
        as_of.save_horse(Horse(ketto_num="H001", name="テスト"))
        as_of.save_jockey(Jockey(code="J001", name="騎手"))
        as_of.save_trainer(Trainer(code="T001", name="調教師"))
        as_of.ensure_horses(["H002"])
        as_of.ensure_jockeys(["J002"])
        as_of.ensure_trainers(["T002"])
        assert "H001" in inner._horses
        assert "J001" in inner._jockeys
        assert "T001" in inner._trainers
        assert "H002" in inner._horses
        assert "J002" in inner._jockeys
        assert "T002" in inner._trainers


class TestAsOfRepository:
    def test_excludes_races_on_or_after_cutoff(self) -> None:
        repo = FakeRaceRepository()
        # 過去走（1/5）と未来走（1/20）を同じ馬に用意する。
        _seed_result_race(repo, "2026010505010101", 5, rpci_actual=50.0, horses=[(1, "H1", 1)])
        _seed_result_race(repo, "2026012005010101", 20, rpci_actual=50.0, horses=[(1, "H1", 1)])

        as_of = _AsOfRaceRepository(repo, datetime.date(2026, 1, 10))
        recent = as_of.find_horse_recent_entries("H1", limit=10)
        # 1/10 より前の 1/5 のみが見え、未来の 1/20 は除外される。
        assert len(recent) == 1
        assert str(recent[0].race_key) == "2026010505010101"


class TestForecastBacktesterEndToEnd:
    def test_runs_and_collects_samples(self) -> None:
        repo = FakeRaceRepository()
        target = _seed_result_race(
            repo,
            "2026011505010101",
            15,
            rpci_actual=50.0,
            horses=[(1, "H1", 1), (2, "H2", 8), (3, "H3", 2)],
        )
        report = ForecastBacktester(repo).run([target])

        assert report.n_races == 1
        assert report.n_horses == 3
        assert report.skipped == 0
        assert report.model_version == "rule-v4"
        assert report.rpci is not None
        # 好走馬は1着(H1)と2着(H3)の2頭。
        assert report.pai is not None
        good = sum(1 for s in report.horse_samples if s.good_run)
        assert good == 2

    def test_skips_race_without_actual_rpci(self) -> None:
        repo = FakeRaceRepository()
        target = _seed_result_race(
            repo, "2026011505010101", 15, rpci_actual=None, horses=[(1, "H1", 1)]
        )
        report = ForecastBacktester(repo).run([target])
        assert report.n_races == 0
        assert report.skipped == 1
        assert report.rpci is None

    def test_exception_in_predict_increments_skipped(self) -> None:
        """_predict_as_of で例外が起きたレースは skipped カウントされる。"""
        repo = FakeRaceRepository()
        # リポジトリに保存せず targets に渡す → predict 時に ValueError
        phantom = Race(
            race_key=RaceKey("2026062805010101"),
            race_date=datetime.date(2026, 6, 28),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=0,
            status=RaceStatus.RESULT,
            rpci_actual=50.0,
        )
        report = ForecastBacktester(repo).run([phantom])
        assert report.n_races == 0
        assert report.skipped == 1


class TestFormatReport:
    def test_full_report_contains_all_sections(self) -> None:
        """rpci + pai が両方ある場合、全セクションが出力される。"""
        report = BacktestReport(
            model_version="rule-v1",
            n_races=10,
            n_horses=80,
            skipped=2,
            rpci=RpciAccuracy(
                n=10,
                mae=2.5,
                rmse=3.1,
                bias=0.5,
                label_accuracy=0.7,
                per_label_accuracy={"PaceLabel.SLOW": 0.8},
            ),
            pai=PaiLift(
                n=80,
                baseline_rate=0.3,
                bands=[PaiBand(0, 50, 40, 10), PaiBand(50, 100, 40, 20)],
                point_biserial=0.25,
                top_band_lift=1.67,
            ),
        )
        text = format_report(report)
        assert "バックテスト結果" in text
        assert "rule-v1" in text
        assert "MAE" in text
        assert "point-biserial" in text
        assert "リフト" in text

    def test_no_samples_shows_fallback_sections(self) -> None:
        """rpci = None / pai = None のとき「有効サンプルなし」が出力される。"""
        report = BacktestReport(
            model_version="",
            n_races=0,
            n_horses=0,
            skipped=5,
            rpci=None,
            pai=None,
        )
        text = format_report(report)
        assert "(不明)" in text
        assert "有効サンプルなし" in text
