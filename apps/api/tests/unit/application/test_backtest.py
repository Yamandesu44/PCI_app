"""バックテスト検証基盤の単体テスト。

純粋集計（summarize_rpci / summarize_pai_lift）と、FakeRepository を使った
エンドツーエンド（lookahead 防止を含む）を検証する。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import replace

import pytest

from pci.application.backtest import (
    DEFAULT_ABILITY_WEIGHT_PROFILES,
    BacktestReport,
    ForecastBacktester,
    HorseSample,
    IntegratedAccuracy,
    IntegratedSample,
    PaiBand,
    PaiLift,
    RpciAccuracy,
    RpciSample,
    StyleAdvantageAttribution,
    StyleAdvantageLift,
    StyleAdvantageSample,
    _AsOfRaceRepository,
    ability_weight_comparisons_to_dict,
    collect_actual_style_advantage_samples,
    compare_ability_weight_reports,
    format_ability_weight_comparison,
    format_actual_style_advantage_validation,
    format_report,
    format_style_advantage_attribution,
    group_races_by_track,
    report_to_dict,
    style_advantage_attribution_to_dict,
    style_advantage_lift_to_dict,
    summarize_integrated_accuracy,
    summarize_pai_lift,
    summarize_rpci,
    summarize_style_advantage,
)
from pci.domain.pace.rpci_forecast import PaceLabel
from pci.domain.pace.running_style import RunningStyleLabel
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


class TestSummarizeIntegratedAccuracy:
    def test_empty_returns_none(self) -> None:
        assert summarize_integrated_accuracy([]) is None

    def test_top_rank_and_capture_metrics(self) -> None:
        samples = [
            IntegratedSample("R1", 1, 1, 1, True),
            IntegratedSample("R1", 2, 2, 4, False),
            IntegratedSample("R1", 3, 3, 2, True),
            IntegratedSample("R2", 1, 1, 3, True),
            IntegratedSample("R2", 2, 2, 1, True),
            IntegratedSample("R2", 3, 3, 8, False),
        ]

        result = summarize_integrated_accuracy(samples)

        assert result is not None
        assert result.n_races == 2
        assert result.top1_win_rate == 0.5
        assert result.top1_good_rate == 1.0
        assert result.top3_good_capture_rate == 1.0


class TestSummarizeStyleAdvantage:
    def test_empty_returns_none(self) -> None:
        assert summarize_style_advantage([]) is None

    def test_advantaged_and_disadvantaged_lift(self) -> None:
        samples = [
            StyleAdvantageSample("R1", 1, 70.0, True),
            StyleAdvantageSample("R1", 2, 60.0, True),
            StyleAdvantageSample("R1", 3, 40.0, False),
            StyleAdvantageSample("R1", 4, 30.0, False),
        ]

        result = summarize_style_advantage(samples)

        assert result is not None
        assert result.baseline_rate == 0.5
        assert result.advantaged_n == 2
        assert result.advantaged_rate == 1.0
        assert result.advantaged_lift == 2.0
        assert result.disadvantaged_n == 2
        assert result.disadvantaged_rate == 0.0
        assert result.rate_gap == 1.0
        assert result.point_biserial > 0
        assert style_advantage_lift_to_dict(result) == {
            "n": 4,
            "baseline_rate": 0.5,
            "advantaged_n": 2,
            "advantaged_rate": 1.0,
            "advantaged_lift": 2.0,
            "disadvantaged_n": 2,
            "disadvantaged_rate": 0.0,
            "disadvantaged_lift": 0.0,
            "rate_gap": 1.0,
            "point_biserial": result.point_biserial,
        }

    def test_collects_actual_pace_and_confirmed_styles(self) -> None:
        repo = FakeRaceRepository()
        race = Race(
            race_key=RaceKey("2026011505010101"),
            race_date=datetime.date(2026, 1, 15),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=2,
            status=RaceStatus.RESULT,
            rpci_actual=55.0,
        )
        repo.save_race(race)
        for horse_no, style, finish in (
            (1, RunningStyleLabel.ESCAPE, 1),
            (2, RunningStyleLabel.CLOSER, 8),
        ):
            repo.save_entry(
                RaceEntry(
                    race_key=race.race_key,
                    horse_no=horse_no,
                    frame_no=horse_no,
                    ketto_num=f"H{horse_no}",
                    weight=480.0,
                    jockey_code="J001",
                    trainer_code="T001",
                    finish_pos=finish,
                    running_style=str(style),
                )
            )

        samples = collect_actual_style_advantage_samples([race], repo)
        result = summarize_style_advantage(samples)

        assert len(samples) == 2
        assert result is not None
        assert result.advantaged_rate == 1.0
        assert result.disadvantaged_rate == 0.0
        assert "診断専用" in format_actual_style_advantage_validation(result)


class TestAbilityWeightComparison:
    @staticmethod
    def _report(
        win_rate: float, good_rate: float, capture_rate: float
    ) -> BacktestReport:
        return BacktestReport(
            model_version="rule-v4",
            n_races=100,
            n_horses=1200,
            skipped=0,
            rpci=None,
            pai=None,
            integrated=IntegratedAccuracy(
                n_races=100,
                n_horses=1200,
                top1_win_rate=win_rate,
                top1_good_rate=good_rate,
                top3_good_capture_rate=capture_rate,
            ),
        )

    def test_compares_each_profile_with_current(self) -> None:
        reports = {
            profile.name: self._report(0.20, 0.45, 0.60)
            for profile in DEFAULT_ABILITY_WEIGHT_PROFILES
        }
        reports["form-heavy"] = self._report(0.23, 0.44, 0.65)

        comparisons = compare_ability_weight_reports(reports)

        form_heavy = next(item for item in comparisons if item.profile.name == "form-heavy")
        assert form_heavy.delta_top1_win_rate == 0.03
        assert form_heavy.delta_top1_good_rate == -0.01
        assert form_heavy.delta_top3_good_capture_rate == 0.05

    def test_missing_baseline_raises(self) -> None:
        with pytest.raises(ValueError, match="基準プロファイル"):
            compare_ability_weight_reports({})

    def test_rejects_different_sample_sizes(self) -> None:
        reports = {
            profile.name: self._report(0.20, 0.45, 0.60)
            for profile in DEFAULT_ABILITY_WEIGHT_PROFILES
        }
        reports["market-aware"] = BacktestReport(
            model_version="rule-v4",
            n_races=99,
            n_horses=1188,
            skipped=1,
            rpci=None,
            pai=None,
            integrated=IntegratedAccuracy(99, 1188, 0.20, 0.45, 0.60),
        )

        with pytest.raises(ValueError, match="比較サンプル数"):
            compare_ability_weight_reports(reports)

    def test_json_and_text_include_weights_and_deltas(self) -> None:
        reports = {
            profile.name: self._report(0.20, 0.45, 0.60)
            for profile in DEFAULT_ABILITY_WEIGHT_PROFILES
        }
        comparisons = compare_ability_weight_reports(reports)

        payload = ability_weight_comparisons_to_dict(comparisons)
        assert payload[0]["name"] == "current"
        assert payload[0]["weights"] == {"form": 0.55, "prize": 0.30, "popularity": 0.15}
        assert payload[0]["delta_vs_current"]["top1_win_rate"] == 0.0
        assert "候補は自動採用しません" in format_ability_weight_comparison(comparisons)


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
        assert report.integrated is not None
        assert report.integrated.n_races == 1
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

    def test_diagnoses_pace_and_style_on_same_horses(self) -> None:
        repo = FakeRaceRepository()
        horses = [(1, "H1", 1), (3, "H3", 6), (6, "H6", 2), (10, "H10", 10)]
        _seed_result_race(
            repo,
            "2026010105010101",
            1,
            rpci_actual=50.0,
            horses=horses,
        )
        target = _seed_result_race(
            repo,
            "2026011505010101",
            15,
            rpci_actual=55.0,
            horses=horses,
        )
        actual_styles = (
            RunningStyleLabel.ESCAPE,
            RunningStyleLabel.FRONT,
            RunningStyleLabel.STALKER,
            RunningStyleLabel.CLOSER,
        )
        for entry, style in zip(repo.find_entries(target.race_key), actual_styles, strict=True):
            repo.save_entry(replace(entry, running_style=str(style)))

        diagnosis = ForecastBacktester(repo).diagnose_style_advantage([target])

        assert diagnosis.n_races == 1
        assert diagnosis.n_horses == 4
        assert diagnosis.skipped == 0
        assert diagnosis.forecast is not None
        assert diagnosis.actual_pace is not None
        assert diagnosis.actual_style is not None
        assert diagnosis.oracle is not None
        assert {diagnosis.forecast.n, diagnosis.actual_pace.n, diagnosis.actual_style.n} == {4}
        payload = style_advantage_attribution_to_dict(diagnosis)
        assert payload["n_horses"] == 4
        assert "pace_recovery" in payload
        assert "予測ペース × 予測脚質" in format_style_advantage_attribution(diagnosis)


class TestStyleAdvantageAttributionFormat:
    def test_reports_larger_recovery_as_primary_factor(self) -> None:
        def _lift(gap: float) -> StyleAdvantageLift:
            return StyleAdvantageLift(
                n=100,
                baseline_rate=0.2,
                advantaged_n=30,
                advantaged_rate=0.2 + gap / 2,
                advantaged_lift=1.0,
                disadvantaged_n=30,
                disadvantaged_rate=0.2 - gap / 2,
                disadvantaged_lift=1.0,
                rate_gap=gap,
                point_biserial=0.0,
            )

        report = StyleAdvantageAttribution(
            n_races=10,
            n_horses=100,
            skipped=0,
            forecast=_lift(-0.10),
            actual_pace=_lift(0.10),
            actual_style=_lift(-0.05),
            oracle=_lift(0.20),
        )

        payload = style_advantage_attribution_to_dict(report)
        text = format_style_advantage_attribution(report)

        assert payload["pace_recovery"] == 0.2
        assert payload["style_recovery"] == 0.05
        assert "想定RPCI側の影響が相対的に大きい" in text


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
            style_advantage=StyleAdvantageLift(
                n=80,
                baseline_rate=0.3,
                advantaged_n=20,
                advantaged_rate=0.4,
                advantaged_lift=1.333,
                disadvantaged_n=20,
                disadvantaged_rate=0.2,
                disadvantaged_lift=0.667,
                rate_gap=0.2,
                point_biserial=0.15,
            ),
        )
        text = format_report(report)
        assert "バックテスト結果" in text
        assert "rule-v1" in text
        assert "MAE" in text
        assert "point-biserial" in text
        assert "リフト" in text
        assert "脚質別展開有利度" in text
        assert "やや不利以下" in text

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


class TestReportToDict:
    def _full_report(self) -> BacktestReport:
        return BacktestReport(
            model_version="rule-v1",
            n_races=1,
            n_horses=1,
            skipped=0,
            rpci=RpciAccuracy(
                n=1,
                mae=2.0,
                rmse=2.0,
                bias=2.0,
                label_accuracy=1.0,
                per_label_accuracy={"PaceLabel.SLOW": 1.0},
            ),
            pai=PaiLift(
                n=1,
                baseline_rate=1.0,
                bands=[PaiBand(0, 100, 1, 1)],
                point_biserial=0.5,
                top_band_lift=1.0,
            ),
            rpci_samples=[
                RpciSample(
                    race_key="2026010105010101",
                    predicted=52.0,
                    actual=50.0,
                    predicted_label=PaceLabel.SLOW,
                    actual_label=PaceLabel.AVERAGE,
                )
            ],
            horse_samples=[
                HorseSample(race_key="2026010105010101", horse_no=1, pai=80.0, good_run=True)
            ],
        )

    def test_full_report_round_trips_as_json(self) -> None:
        result = report_to_dict(self._full_report())

        assert result["model_version"] == "rule-v1"
        assert result["rpci"] == {
            "n": 1,
            "mae": 2.0,
            "rmse": 2.0,
            "bias": 2.0,
            "label_accuracy": 1.0,
            "per_label_accuracy": {"PaceLabel.SLOW": 1.0},
        }
        assert result["pai"] == {
            "n": 1,
            "baseline_rate": 1.0,
            "point_biserial": 0.5,
            "top_band_lift": 1.0,
            "bands": [{"lo": 0, "hi": 100, "n": 1, "good_runs": 1, "good_rate": 1.0}],
        }
        # error はプロパティなので、明示的に計算して含める（predicted - actual）。
        assert result["rpci_samples"] == [
            {
                "race_key": "2026010105010101",
                "predicted": 52.0,
                "actual": 50.0,
                "error": 2.0,
                "predicted_label": "スロー",
                "actual_label": "平均",
            }
        ]
        assert result["horse_samples"] == [
            {"race_key": "2026010105010101", "horse_no": 1, "pai": 80.0, "good_run": True}
        ]
        assert result["integrated"] is None
        assert result["style_advantage"] is None
        assert result["integrated_samples"] == []
        assert result["style_advantage_samples"] == []
        # PaceLabel(StrEnum) が生の値のまま紛れ込んでいないか、実際にJSON化して確認する。
        json.dumps(result)

    def test_empty_report_has_null_rpci_and_pai(self) -> None:
        report = BacktestReport(
            model_version="",
            n_races=0,
            n_horses=0,
            skipped=3,
            rpci=None,
            pai=None,
        )
        result = report_to_dict(report)
        assert result["rpci"] is None
        assert result["pai"] is None
        assert result["integrated"] is None
        assert result["style_advantage"] is None
        assert result["rpci_samples"] == []
        assert result["horse_samples"] == []
        assert result["integrated_samples"] == []
        assert result["style_advantage_samples"] == []
        json.dumps(result)
