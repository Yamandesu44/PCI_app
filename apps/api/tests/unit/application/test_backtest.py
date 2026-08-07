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
    DEFAULT_PAI_WEIGHT_PROFILES,
    DEFAULT_RULE_WEIGHT_PROFILES,
    DEFAULT_RULE_WEIGHTS,
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
    build_actual_style_advantage_breakdown,
    collect_actual_style_advantage_samples,
    collect_pace_style_matrix,
    compare_ability_weight_reports,
    compare_pai_weight_reports,
    compare_rule_weight_reports,
    compare_style_advantage_profiles,
    format_ability_weight_comparison,
    format_actual_style_advantage_breakdown,
    format_actual_style_advantage_validation,
    format_clamp_impact,
    format_fit_label_shares,
    format_pace_style_matrix,
    format_pai_by_style,
    format_pai_weight_comparison,
    format_report,
    format_rule_weight_comparison,
    format_style_advantage_attribution,
    format_style_advantage_profile_comparison,
    group_races_by_track,
    pai_weight_comparisons_to_dict,
    report_to_dict,
    rule_weight_comparisons_to_dict,
    style_advantage_attribution_to_dict,
    style_advantage_breakdown_to_dict,
    style_advantage_lift_to_dict,
    summarize_clamp_impact,
    summarize_fit_crowding,
    summarize_fit_label_shares,
    summarize_integrated_accuracy,
    summarize_pace_centering,
    summarize_pai_lift,
    summarize_pai_within_style,
    summarize_rpci,
    summarize_style_advantage,
)
from pci.domain.pace.adaptability import DEFAULT_WEIGHTS as DEFAULT_PAI_WEIGHTS
from pci.domain.pace.adaptability import pace_center, pace_half_band
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


class TestSummarizePaiWithinStyle:
    """脚質を固定した PAI の効き。pai-v3 は脚質内の相対量なので、これが唯一の性能軸。"""

    @staticmethod
    def _h(style: str, pai: float, good: bool, track: str = "芝") -> HorseSample:
        return HorseSample(
            race_key="2026010105010101",
            horse_no=1,
            pai=pai,
            good_run=good,
            track_type=track,
            running_style=style,
        )

    def test_empty_returns_empty(self) -> None:
        assert summarize_pai_within_style([]) == []

    def test_style_with_fewer_than_three_horses_is_skipped(self) -> None:
        samples = [self._h("逃げ", 40.0, False), self._h("逃げ", 60.0, True)]
        assert summarize_pai_within_style(samples) == []

    def test_splits_into_terciles_and_measures_spread(self) -> None:
        # PAI昇順で9頭。上位1/3だけが好走 → 差は +100%。
        samples = [
            self._h("逃げ", pai, pai >= 70.0)
            for pai in (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0)
        ]
        rows = summarize_pai_within_style(samples)
        assert len(rows) == 1
        row = rows[0]
        assert row.n == 9
        assert row.group_n == 3
        assert row.low_mean_pai == 20.0
        assert row.high_mean_pai == 80.0
        assert row.low_rate == 0.0
        assert row.high_rate == 1.0
        assert row.spread == pytest.approx(1.0)
        assert row.pai_spread == pytest.approx(60.0)

    def test_flat_pai_reports_no_discriminating_width(self) -> None:
        # 感応度0の脚質は基準点に張り付き、PAI に幅が無い。差が出ても偶然。
        samples = [self._h("追込", 50.0, i < 2) for i in range(9)]
        rows = summarize_pai_within_style(samples)
        assert rows[0].pai_spread == 0.0

    def test_sorted_by_spread_descending(self) -> None:
        samples = [self._h("逃げ", pai, pai >= 70.0) for pai in (10.0, 40.0, 70.0)]
        samples += [self._h("追込", pai, pai < 70.0) for pai in (10.0, 40.0, 70.0)]
        rows = summarize_pai_within_style(samples)
        assert [r.style for r in rows] == ["逃げ", "追込"]

    def test_tiny_groups_are_not_significant(self) -> None:
        """片側1頭では 0% 対 100% でも偶然と区別できない。"""
        samples = [self._h("逃げ", pai, pai >= 70.0) for pai in (10.0, 40.0, 70.0)]
        row = summarize_pai_within_style(samples)[0]
        assert row.spread == pytest.approx(1.0)
        assert row.is_significant is False

    @staticmethod
    def _terciles(low_good: int, high_good: int) -> list[HorseSample]:
        """1/3が100頭ちょうどになる300頭。中位帯は判定に使われない。"""
        h = TestSummarizePaiWithinStyle._h
        return (
            [h("逃げ", 20.0, i < low_good) for i in range(100)]
            + [h("逃げ", 50.0, False) for _ in range(100)]
            + [h("逃げ", 80.0, i < high_good) for i in range(100)]
        )

    def test_large_consistent_difference_is_significant(self) -> None:
        # 下位10% 対 上位40%。誤差の2倍を大きく超える。
        row = summarize_pai_within_style(self._terciles(low_good=10, high_good=40))[0]
        assert row.group_n == 100
        assert row.spread == pytest.approx(0.3)
        assert row.is_significant is True

    def test_flat_rates_are_not_significant(self) -> None:
        row = summarize_pai_within_style(self._terciles(low_good=20, high_good=20))[0]
        assert row.spread == 0.0
        assert row.is_significant is False

    def test_small_difference_is_within_noise(self) -> None:
        # 20% 対 24%。差 +4% に対し誤差の2倍は約11%。
        row = summarize_pai_within_style(self._terciles(low_good=20, high_good=24))[0]
        assert row.spread == pytest.approx(0.04)
        assert row.is_significant is False


class TestPaceCentering:
    """ペース補正が0を中心に振れているか。ずれれば脚質の定数効果を埋め込む。"""

    @staticmethod
    def _h(track: str, forecast: float) -> HorseSample:
        return HorseSample(
            race_key="R1",
            horse_no=1,
            pai=50.0,
            good_run=False,
            track_type=track,
            running_style="逃げ",
            forecast_rpci=forecast,
        )

    def test_empty_returns_empty(self) -> None:
        assert summarize_pace_centering([]) == []

    def test_forecast_at_neutral_is_centered(self) -> None:
        rows = summarize_pace_centering([self._h("芝", pace_center("芝")) for _ in range(10)])
        assert len(rows) == 1
        assert rows[0].mean_deviation == 0.0
        assert rows[0].mean_bonus_at_full_sensitivity == 0.0
        assert rows[0].is_centered is True

    def test_symmetric_spread_around_neutral_is_centered(self) -> None:
        n = pace_center("芝")
        half = pace_half_band("芝")
        rows = summarize_pace_centering(
            [self._h("芝", n - half / 2) for _ in range(10)]
            + [self._h("芝", n + half / 2) for _ in range(10)]
        )
        assert rows[0].mean_deviation == 0.0
        assert rows[0].is_centered is True

    def test_offset_forecast_shifts_high_sensitivity_styles(self) -> None:
        """予測が中立値からずれると、感応度1.0の脚質だけが系統的に底上げされる。"""
        n = pace_center("ダート")
        half = pace_half_band("ダート")
        rows = summarize_pace_centering([self._h("ダート", n + half / 2) for _ in range(10)])
        assert rows[0].mean_deviation == pytest.approx(0.5)
        # 感応度1.0なら平均 0.5×pace_swing 点。脚質間の相対位置が動く。
        assert rows[0].mean_bonus_at_full_sensitivity == pytest.approx(
            0.5 * DEFAULT_PAI_WEIGHTS.pace_swing
        )
        assert rows[0].is_centered is False

    def test_recommended_offset_zeroes_the_mean_deviation(self) -> None:
        """推奨offset を入れ直すと平均ずれが0になること。

        deviation は±1で頭打ちになるため、予測平均を中心へ置くだけでは足りない。
        ダートは予測平均46.55・中立46.50とほぼ一致しているのに平均ずれ +0.172 だった。
        """
        n = pace_center("ダート")
        half = pace_half_band("ダート")
        # 上側へ非対称にばらけさせる（頭打ちの効果が出る形）。
        samples = [self._h("ダート", n + half * d) for d in (-3.0, -0.2, 0.1, 0.4, 2.0, 3.0)]

        row = summarize_pace_centering(samples)[0]
        assert row.mean_deviation > 0
        assert row.recommended_offset > 0

        recentered = replace(DEFAULT_PAI_WEIGHTS, pace_center_offset_dirt=row.recommended_offset)
        assert summarize_pace_centering(samples, recentered)[0].mean_deviation == pytest.approx(
            0.0, abs=0.01
        )

    def test_offset_is_unchanged_when_no_solution_exists(self) -> None:
        """全頭が同じ側へ振り切れていれば解が無い。現行値を返して壊れない。"""
        n = pace_center("ダート")
        half = pace_half_band("ダート")
        samples = [self._h("ダート", n + half * 50) for _ in range(5)]

        assert (
            summarize_pace_centering(samples)[0].recommended_offset
            == DEFAULT_PAI_WEIGHTS.pace_center_offset_dirt
        )

    def test_ignores_samples_without_a_forecast(self) -> None:
        """forecast_rpci 未設定のサンプルを 0 として平均に混ぜない。"""
        rows = summarize_pace_centering([self._h("芝", pace_center("芝")), self._h("芝", 0.0)])
        assert rows[0].n == 1


class TestFormatPaiByStyle:
    def test_empty_returns_empty_string(self) -> None:
        assert format_pai_by_style([]) == ""

    def test_includes_the_centering_check(self) -> None:
        samples = [
            HorseSample(
                race_key="R1",
                horse_no=i,
                pai=float(i),
                good_run=i > 1,
                track_type="芝",
                running_style="逃げ",
                forecast_rpci=pace_center("芝"),
            )
            for i in range(3)
        ]
        out = format_pai_by_style(samples)
        assert "ペース補正の中心ずれ" in out
        assert "中心一致" in out

    def test_drops_cross_style_verdict_and_warns_instead(self) -> None:
        """pai-v3 では脚質をまたいだ PAI 平均の順位比較は何も主張しない。"""
        samples = [
            TestSummarizePaiWithinStyle._h("逃げ", pai, pai >= 70.0) for pai in (10.0, 40.0, 70.0)
        ]
        out = format_pai_by_style(samples)
        assert "不一致" not in out
        assert "PAI順" not in out
        assert "脚質間で比較できない" in out
        assert "脚質内でのPAIの効き" in out

    def test_marks_underpowered_rows_as_noise(self) -> None:
        """頭数が少なければ、差の大きさに関わらず「誤差内」と出す。"""
        samples = [
            TestSummarizePaiWithinStyle._h("逃げ", pai, pai >= 70.0) for pai in (10.0, 40.0, 70.0)
        ]
        out = format_pai_by_style(samples)
        assert "判定" in out  # 見出し
        assert "誤差内" in out

    def test_marks_a_real_difference_as_significant(self) -> None:
        out = format_pai_by_style(TestSummarizePaiWithinStyle._terciles(10, 40))
        assert "有意" in out


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
            "bands": [
                {"label": "不利", "lo": 0.0, "hi": 35.0, "n": 1, "good_runs": 0, "good_rate": 0.0},
                {
                    "label": "やや不利",
                    "lo": 35.0,
                    "hi": 45.0,
                    "n": 1,
                    "good_runs": 0,
                    "good_rate": 0.0,
                },
                {"label": "互角", "lo": 45.0, "hi": 55.0, "n": 0, "good_runs": 0, "good_rate": 0.0},
                {
                    "label": "やや有利",
                    "lo": 55.0,
                    "hi": 65.0,
                    "n": 1,
                    "good_runs": 1,
                    "good_rate": 1.0,
                },
                {
                    "label": "有利",
                    "lo": 65.0,
                    "hi": 100.0,
                    "n": 1,
                    "good_runs": 1,
                    "good_rate": 1.0,
                },
            ],
            # 脚質を持たないサンプルは脚質グループ集計の対象外。
            "style_groups": [],
        }

    def test_style_groups_split_front_runners_from_closers(self) -> None:
        """同じ帯でも前付けと差し追込を分けて集計することを検証する。

        「有利」帯にはスロー想定で加点された前付け馬とハイ想定で加点された
        差し追込馬が混ざるため、分けないと相殺されて非単調の原因を追えない。
        """
        samples = [
            # 前付けの「有利」は好走、差し追込の「有利」は凡走という食い違いを作る
            StyleAdvantageSample("R1", 1, 70.0, True, RunningStyleLabel.ESCAPE),
            StyleAdvantageSample("R1", 2, 70.0, True, RunningStyleLabel.FRONT),
            StyleAdvantageSample("R1", 3, 70.0, False, RunningStyleLabel.STALKER),
            StyleAdvantageSample("R1", 4, 70.0, False, RunningStyleLabel.CLOSER),
            StyleAdvantageSample("R1", 5, 20.0, False, RunningStyleLabel.FLEXIBLE),
        ]

        result = summarize_style_advantage(samples)

        assert result is not None
        by_label = {group.label: group for group in result.style_groups}
        assert set(by_label) == {"前付け（逃げ・先行）", "差し追込", "自在"}
        # 自在は前付けにも差し追込にも入らず、独立したグループになる
        assert by_label["前付け（逃げ・先行）"].n == 2
        assert by_label["差し追込"].n == 2
        assert by_label["自在"].n == 1
        assert by_label["前付け（逃げ・先行）"].baseline_rate == 1.0
        assert by_label["差し追込"].baseline_rate == 0.0
        # 全体の帯では両者が混ざり、有利帯の好走率は50%に相殺される
        overall_advantage = next(band for band in result.bands if band.label == "有利")
        assert overall_advantage.n == 4
        assert overall_advantage.good_rate == 0.5

    def test_bands_use_the_same_boundaries_as_the_web_labels(self) -> None:
        """帯の境界が web の`styleVerdict`と一致することを固定する。

        ここがずれると「画面で有利と出ている馬の実績」を測っていることに
        ならなくなるため、境界値そのものを検証する。
        """
        # styleVerdict: >=65 有利 / >=55 やや有利 / >45 互角 / >35 やや不利 / それ以下 不利
        boundary_samples = [
            StyleAdvantageSample("R1", 1, 65.0, False),  # 有利（下端を含む）
            StyleAdvantageSample("R1", 2, 55.0, False),  # やや有利（下端を含む）
            StyleAdvantageSample("R1", 3, 45.1, False),  # 互角（45ちょうどは含まない）
            StyleAdvantageSample("R1", 4, 45.0, False),  # やや不利（45ちょうどはこちら）
            StyleAdvantageSample("R1", 5, 35.1, False),  # やや不利
            StyleAdvantageSample("R1", 6, 35.0, False),  # 不利（35ちょうどはこちら）
        ]

        result = summarize_style_advantage(boundary_samples)

        assert result is not None
        by_label = {band.label: band.n for band in result.bands}
        assert by_label == {"有利": 1, "やや有利": 1, "互角": 1, "やや不利": 2, "不利": 1}

    def test_band_totals_match_overall_sample_count(self) -> None:
        samples = [
            StyleAdvantageSample("R1", i, float(score), score > 50)
            for i, score in enumerate((5, 20, 36, 44, 50, 58, 64, 70, 95), start=1)
        ]

        result = summarize_style_advantage(samples)

        assert result is not None
        assert sum(band.n for band in result.bands) == result.n
        assert sum(band.good_runs for band in result.bands) == sum(1 for s in samples if s.good_run)

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


class TestClampImpact:
    """予測値クランプが系統バイアスの原因かを切り分ける診断。

    2026-08-02: ダートのバイアス+2.5がv4/v5どちらでも動かなかった。モデルではなく
    クランプ下限35.0（旧フォールバック式時代の値）が原因という仮説を測るために追加。
    """

    @staticmethod
    def _sample(predicted: float, actual: float) -> RpciSample:
        return RpciSample(
            race_key="2026060105010101",
            predicted=predicted,
            actual=actual,
            predicted_label=HIGH,
            actual_label=HIGH,
        )

    def test_empty_returns_none(self) -> None:
        assert summarize_clamp_impact([]) is None

    def test_separates_clamped_and_interior_groups(self) -> None:
        impact = summarize_clamp_impact(
            [
                self._sample(35.0, 28.0),  # 下限張付き（実績が下限より低い）
                self._sample(35.0, 30.0),  # 同上
                self._sample(50.0, 50.0),  # 内側・誤差なし
                self._sample(65.0, 68.0),  # 上限張付き
            ]
        )

        assert impact is not None
        assert impact.at_lower_n == 2
        assert impact.at_upper_n == 1
        assert impact.interior_n == 1
        assert impact.at_lower_bias == 6.0  # ((35-28)+(35-30))/2
        assert impact.interior_bias == 0.0
        assert impact.at_lower_actual_mean == 29.0

    def test_quantifies_how_much_of_the_total_bias_the_clamp_explains(self) -> None:
        """内側が無バイアスでも、下限張付きだけで全体が偏ることを示せる。"""
        samples = [self._sample(50.0, 50.0) for _ in range(8)]
        samples += [self._sample(35.0, 25.0) for _ in range(2)]

        impact = summarize_clamp_impact(samples)

        assert impact is not None
        assert impact.interior_bias == 0.0
        # 全体バイアス = 2件×10.0 / 10件 = +2.0。これを下限群が全部説明する。
        assert impact.bias_from_lower == pytest.approx(2.0)
        assert impact.bias_from_upper == 0.0
        assert impact.at_lower_share == pytest.approx(0.2)

    def test_format_is_empty_when_nothing_is_clamped(self) -> None:
        """端に張り付きが無ければ通常出力を汚さない。"""
        impact = summarize_clamp_impact([self._sample(50.0, 49.0)])

        assert format_clamp_impact(impact) == ""
        assert format_clamp_impact(None) == ""

    def test_format_reports_the_contribution(self) -> None:
        samples = [self._sample(50.0, 50.0) for _ in range(8)]
        samples += [self._sample(35.0, 25.0) for _ in range(2)]

        text = format_clamp_impact(summarize_clamp_impact(samples))

        assert "下限張付き" in text
        assert "全体バイアスへの寄与" in text
        assert "原因はモデルではなくクランプ幅" in text

    def test_uses_the_domain_clamp_bounds(self) -> None:
        """境界値はドメインのRuleWeightsを正とする（infra側の重複定義に追随しない）。"""
        impact = summarize_clamp_impact([self._sample(50.0, 50.0)])

        assert impact is not None
        assert impact.lower == DEFAULT_RULE_WEIGHTS.rpci_min
        assert impact.upper == DEFAULT_RULE_WEIGHTS.rpci_max

    def test_explicit_clamp_overrides_the_default_bounds(self) -> None:
        """安全弁を広げて実測するとき、判定境界も同じ値へ合わせる必要がある。"""
        samples = [self._sample(28.0, 27.0), self._sample(50.0, 50.0)]

        impact = summarize_clamp_impact(samples, clamp=(28.0, 90.0))

        assert impact is not None
        assert (impact.lower, impact.upper) == (28.0, 90.0)
        assert impact.at_lower_n == 1
        assert impact.interior_n == 1

    def test_widened_clamp_reports_nothing_pinned(self) -> None:
        """境界を広げれば張り付きが消え、診断セクション自体が出なくなる。"""
        samples = [self._sample(35.0, 28.0), self._sample(50.0, 50.0)]

        impact = summarize_clamp_impact(samples, clamp=(20.0, 90.0))

        assert impact is not None
        assert impact.at_lower_n == 0
        assert impact.at_upper_n == 0
        assert format_clamp_impact(impact) == ""

    def test_format_report_stays_silent_without_an_explicit_clamp(self) -> None:
        """安全弁が不明なまま推測で判定するくらいなら、内訳を出さない。"""
        samples = [self._sample(35.0, 28.0), self._sample(50.0, 50.0)]
        report = BacktestReport(
            model_version="test",
            n_races=2,
            n_horses=0,
            skipped=0,
            rpci=summarize_rpci(samples),
            pai=None,
            rpci_samples=samples,
        )

        assert "予測値クランプ" not in format_report(report)
        assert "予測値クランプ" in format_report(report, clamp=(35.0, 65.0))

    def test_format_report_honours_the_clamp_argument(self) -> None:
        """レポート整形も実際に適用した安全弁で判定する。"""
        report = BacktestReport(
            model_version="test",
            n_races=2,
            n_horses=0,
            skipped=0,
            rpci=summarize_rpci([self._sample(35.0, 28.0), self._sample(50.0, 50.0)]),
            pai=None,
            rpci_samples=[self._sample(35.0, 28.0), self._sample(50.0, 50.0)],
        )

        assert "予測値クランプ" in format_report(report, clamp=(35.0, 65.0))
        assert "予測値クランプ" not in format_report(report, clamp=(20.0, 90.0))


class TestStyleAdvantageProfileComparison:
    @staticmethod
    def _seed(repo: FakeRaceRepository, race_key: str, rpci_actual: float) -> Race:
        race = Race(
            race_key=RaceKey(race_key),
            race_date=datetime.date(2026, 1, 15),
            jyo_cd="05",
            distance_m=1600,
            track_type="芝",
            field_size=5,
            status=RaceStatus.RESULT,
            rpci_actual=rpci_actual,
        )
        repo.save_race(race)
        styles = (
            RunningStyleLabel.ESCAPE,
            RunningStyleLabel.FRONT,
            RunningStyleLabel.STALKER,
            RunningStyleLabel.CLOSER,
            RunningStyleLabel.FLEXIBLE,
        )
        for horse_no, style in enumerate(styles, start=1):
            repo.save_entry(
                RaceEntry(
                    race_key=race.race_key,
                    horse_no=horse_no,
                    frame_no=horse_no,
                    ketto_num=f"H{race_key}{horse_no}",
                    weight=480.0,
                    jockey_code="J001",
                    trainer_code="T001",
                    finish_pos=horse_no,
                    running_style=str(style),
                )
            )
        return race

    def test_current_profile_leaves_flexible_unscored(self) -> None:
        repo = FakeRaceRepository()
        race = self._seed(repo, "2026011505010101", 55.0)

        results = compare_style_advantage_profiles([race], repo)

        by_name = {r.profile.name: r for r in results}
        current = by_name["current"].lift
        assert current is not None
        # 自在は現行では採点されないため、サンプルに現れない。
        assert all(s.label != "自在" for s in current.style_groups)
        assert current.n == 4

    def test_flexible_profile_scores_the_extra_style(self) -> None:
        repo = FakeRaceRepository()
        race = self._seed(repo, "2026011505010102", 55.0)

        results = compare_style_advantage_profiles([race], repo)

        by_name = {r.profile.name: r for r in results}
        flexible = by_name["flexible-only"].lift
        assert flexible is not None
        # 自在の1頭が加わり、現行の4頭から5頭になる。
        assert flexible.n == 5

    def test_comparison_output_lists_every_candidate(self) -> None:
        repo = FakeRaceRepository()
        races = [
            self._seed(repo, "2026011505010103", 55.0),
            self._seed(repo, "2026011505010104", 45.0),
        ]

        text = format_style_advantage_profile_comparison(
            compare_style_advantage_profiles(races, repo)
        )

        for name in ("current", "closer-weak", "flexible-only", "measured"):
            assert name in text
        assert "自動採用しません" in text


class TestPaceStyleMatrix:
    @staticmethod
    def _seed(
        repo: FakeRaceRepository,
        race_key: str,
        rpci_actual: float,
        entries: tuple[tuple[int, RunningStyleLabel, int], ...],
        track_type: str = "芝",
    ) -> Race:
        race = Race(
            race_key=RaceKey(race_key),
            race_date=datetime.date(2026, 1, 15),
            jyo_cd="05",
            distance_m=1600,
            track_type=track_type,
            field_size=len(entries),
            status=RaceStatus.RESULT,
            rpci_actual=rpci_actual,
        )
        repo.save_race(race)
        for horse_no, style, finish in entries:
            repo.save_entry(
                RaceEntry(
                    race_key=race.race_key,
                    horse_no=horse_no,
                    frame_no=horse_no,
                    ketto_num=f"H{race_key}{horse_no}",
                    weight=480.0,
                    jockey_code="J001",
                    trainer_code="T001",
                    finish_pos=finish,
                    running_style=str(style),
                )
            )
        return race

    def test_empty_returns_none(self) -> None:
        assert collect_pace_style_matrix([], FakeRaceRepository()) is None

    def test_splits_good_run_rate_by_pace_and_style(self) -> None:
        """有利度スコアを介さず、素の「脚質×ペース」好走率を集計する。"""
        repo = FakeRaceRepository()
        # 芝の閾値は 49.0/51.0。55.0=スロー、45.0=ハイ。
        slow = self._seed(
            repo,
            "2026011505010101",
            55.0,
            ((1, RunningStyleLabel.ESCAPE, 1), (2, RunningStyleLabel.CLOSER, 8)),
        )
        high = self._seed(
            repo,
            "2026011505010102",
            45.0,
            ((1, RunningStyleLabel.ESCAPE, 9), (2, RunningStyleLabel.CLOSER, 2)),
        )

        matrix = collect_pace_style_matrix([slow, high], repo)

        assert matrix is not None
        assert matrix.n_races == 2
        assert matrix.n_horses == 4
        by_style = {row.style: row for row in matrix.rows}
        escape_cells = {cell.pace_label: cell for cell in by_style["逃げ"].cells}
        closer_cells = {cell.pace_label: cell for cell in by_style["追込"].cells}
        # 逃げはスローで好走、ハイで凡走。追込はその逆。
        assert escape_cells["スロー"].good_rate == 1.0
        assert escape_cells["ハイ"].good_rate == 0.0
        assert closer_cells["スロー"].good_rate == 0.0
        assert closer_cells["ハイ"].good_rate == 1.0

    def test_includes_flexible_style_excluded_from_advantage_scoring(self) -> None:
        """自在は有利度スコアの対象外だが、この一次集計には含める。

        出走の3割超を占め、前が苦しくなった分の受け皿になっている可能性があるため、
        ルールを作り直す際の判断材料として欠かせない。
        """
        repo = FakeRaceRepository()
        race = self._seed(
            repo,
            "2026011505010103",
            45.0,
            ((1, RunningStyleLabel.FLEXIBLE, 1), (2, RunningStyleLabel.ESCAPE, 5)),
        )

        matrix = collect_pace_style_matrix([race], repo)

        assert matrix is not None
        by_style = {row.style: row for row in matrix.rows}
        assert by_style["自在"].n == 1
        assert by_style["自在"].good_rate == 1.0

    def test_uses_dirt_thresholds_for_dirt_races(self) -> None:
        """ペース区分はコース別閾値（classify_pace）に従う。

        芝閾値(49/51)を流用するとダートの大半がハイに寄り、集計が無意味になる。
        """
        repo = FakeRaceRepository()
        # 45.0 は芝ならハイだが、ダート閾値(40/46)では平均。
        race = self._seed(
            repo,
            "2026011505010104",
            45.0,
            ((1, RunningStyleLabel.ESCAPE, 1),),
            track_type="ダート",
        )

        matrix = collect_pace_style_matrix([race], repo)

        assert matrix is not None
        by_style = {row.style: row for row in matrix.rows}
        cells = {cell.pace_label: cell for cell in by_style["逃げ"].cells}
        assert cells["平均"].n == 1
        assert cells["ハイ"].n == 0

    def test_format_renders_all_styles_and_pace_columns(self) -> None:
        repo = FakeRaceRepository()
        race = self._seed(
            repo,
            "2026011505010105",
            55.0,
            ((1, RunningStyleLabel.ESCAPE, 1), (2, RunningStyleLabel.CLOSER, 8)),
        )

        text = format_pace_style_matrix(collect_pace_style_matrix([race], repo))

        assert "逃げ" in text
        assert "追込" in text
        assert "ハイ" in text
        assert "スロー" in text
        assert format_pace_style_matrix(None) == "実績ペース×脚質: 有効サンプルなし"


class TestActualStyleAdvantageBreakdown:
    @staticmethod
    def _register_race(
        repo: FakeRaceRepository,
        race_key: str,
        race_date: datetime.date,
        distance_m: int,
        track_condition: str | None,
    ) -> Race:
        race = Race(
            race_key=RaceKey(race_key),
            race_date=race_date,
            jyo_cd="10",
            distance_m=distance_m,
            track_type="芝",
            field_size=2,
            status=RaceStatus.RESULT,
            track_condition=track_condition,
            rpci_actual=55.0,
        )
        repo.save_race(race)
        for horse_no, style, finish_pos in (
            (1, RunningStyleLabel.ESCAPE, 1),
            (2, RunningStyleLabel.CLOSER, 8),
        ):
            repo.save_entry(
                RaceEntry(
                    race_key=race.race_key,
                    horse_no=horse_no,
                    frame_no=horse_no,
                    ketto_num=f"H{horse_no}",
                    weight=55.0,
                    jockey_code="00001",
                    trainer_code="00001",
                    finish_pos=finish_pos,
                    running_style=str(style),
                )
            )
        return race

    def test_groups_by_year_distance_and_track_condition(self) -> None:
        repo = FakeRaceRepository()
        targets = [
            self._register_race(
                repo,
                "2025070110020101",
                datetime.date(2025, 7, 1),
                1200,
                "良",
            ),
            self._register_race(
                repo,
                "2026070110020101",
                datetime.date(2026, 7, 1),
                1800,
                "稍重",
            ),
            self._register_race(
                repo,
                "2026070210020101",
                datetime.date(2026, 7, 2),
                1200,
                None,
            ),
        ]

        by_year = build_actual_style_advantage_breakdown(targets, repo, "year")
        by_distance = build_actual_style_advantage_breakdown(targets, repo, "distance")
        by_condition = build_actual_style_advantage_breakdown(targets, repo, "track-condition")
        by_distance_condition = build_actual_style_advantage_breakdown(
            targets,
            repo,
            "distance-track-condition",
        )

        assert [(group.label, group.n_races) for group in by_year] == [
            ("2025", 1),
            ("2026", 2),
        ]
        assert [(group.label, group.n_races) for group in by_distance] == [
            ("1200m", 2),
            ("1800m", 1),
        ]
        assert [group.label for group in by_condition] == ["良", "稍重", "不明"]
        assert [group.label for group in by_distance_condition] == [
            "1200m / 良",
            "1200m / 不明",
            "1800m / 稍重",
        ]
        assert all(group.lift is not None for group in by_year)

        payload = style_advantage_breakdown_to_dict(by_distance)
        assert payload["1200m"]["n_races"] == 2
        assert "好走率差" in format_actual_style_advantage_breakdown("distance", by_distance)
        assert "距離×馬場状態" in format_actual_style_advantage_breakdown(
            "distance-track-condition",
            by_distance_condition,
        )


class TestAbilityWeightComparison:
    @staticmethod
    def _report(win_rate: float, good_rate: float, capture_rate: float) -> BacktestReport:
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


class TestRuleWeightComparison:
    @staticmethod
    def _sample(
        race_key: str,
        track_type: str,
        predicted: float,
        actual: float,
        predicted_label: PaceLabel,
        actual_label: PaceLabel,
    ) -> RpciSample:
        return RpciSample(
            race_key=race_key,
            predicted=predicted,
            actual=actual,
            predicted_label=predicted_label,
            actual_label=actual_label,
            track_type=track_type,
        )

    def _report(self, samples: list[RpciSample]) -> BacktestReport:
        return BacktestReport(
            model_version="rule-v4",
            n_races=len(samples),
            n_horses=0,
            skipped=0,
            rpci=summarize_rpci(samples),
            pai=None,
            rpci_samples=samples,
        )

    def test_compares_overall_turf_and_dirt_with_current(self) -> None:
        baseline_samples = [
            self._sample("R1", "芝", 52.0, 50.0, SLOW, AVERAGE),
            self._sample("R2", "ダート", 44.0, 44.0, AVERAGE, AVERAGE),
        ]
        candidate_samples = [
            self._sample("R1", "芝", 50.0, 50.0, AVERAGE, AVERAGE),
            self._sample("R2", "ダート", 46.0, 44.0, SLOW, AVERAGE),
        ]
        reports = {
            profile.name: self._report(baseline_samples) for profile in DEFAULT_RULE_WEIGHT_PROFILES
        }
        reports["style-light"] = self._report(candidate_samples)

        comparisons = compare_rule_weight_reports(reports)

        candidate = next(item for item in comparisons if item.profile.name == "style-light")
        assert candidate.combined.delta_mae == 0.0
        assert candidate.combined.delta_label_accuracy == 0.0
        assert candidate.turf.delta_mae == -2.0
        assert candidate.turf.delta_label_accuracy == 1.0
        assert candidate.dirt.delta_mae == 2.0
        assert candidate.dirt.delta_label_accuracy == -1.0

    def test_missing_baseline_and_different_races_raise(self) -> None:
        with pytest.raises(ValueError, match="基準プロファイル"):
            compare_rule_weight_reports({})

        baseline = self._report([self._sample("R1", "芝", 50.0, 50.0, AVERAGE, AVERAGE)])
        reports = {profile.name: baseline for profile in DEFAULT_RULE_WEIGHT_PROFILES}
        reports["evidence-heavy"] = self._report(
            [self._sample("R2", "芝", 50.0, 50.0, AVERAGE, AVERAGE)]
        )
        with pytest.raises(ValueError, match="比較対象レース"):
            compare_rule_weight_reports(reports)

    def test_json_and_text_include_weights_track_metrics_and_deltas(self) -> None:
        report = self._report([self._sample("R1", "芝", 50.0, 50.0, AVERAGE, AVERAGE)])
        reports = {profile.name: report for profile in DEFAULT_RULE_WEIGHT_PROFILES}

        comparisons = compare_rule_weight_reports(reports)
        payload = rule_weight_comparisons_to_dict(comparisons)

        assert payload[0]["name"] == "current"
        assert payload[0]["weights"] == {
            "style_balance": 8.0,
            "evidence_per_sample": 0.1,
            "evidence_cap": 0.7,
        }
        assert payload[0]["turf"]["rpci"]["n"] == 1
        assert payload[0]["dirt"]["rpci"] is None
        assert payload[0]["combined"]["delta_vs_current"]["mae"] == 0.0
        text = format_rule_weight_comparison(comparisons)
        assert "候補は自動採用しません" in text
        assert "全体" in text
        assert "ダート" in text


class TestPaiWeightComparison:
    @staticmethod
    def _sample(
        race_key: str,
        horse_no: int,
        track_type: str,
        pai: float,
        good_run: bool,
    ) -> HorseSample:
        return HorseSample(
            race_key=race_key,
            horse_no=horse_no,
            pai=pai,
            good_run=good_run,
            track_type=track_type,
        )

    def _report(self, samples: list[HorseSample]) -> BacktestReport:
        return BacktestReport(
            model_version="rule-v4",
            n_races=2,
            n_horses=len(samples),
            skipped=0,
            rpci=None,
            pai=summarize_pai_lift(samples),
            horse_samples=samples,
        )

    def test_compares_overall_turf_and_dirt_with_current(self) -> None:
        baseline_samples = [
            self._sample("R1", 1, "芝", 90.0, True),
            self._sample("R1", 2, "芝", 10.0, False),
            self._sample("R2", 1, "ダート", 80.0, True),
            self._sample("R2", 2, "ダート", 20.0, False),
        ]
        candidate_samples = [
            self._sample("R1", 1, "芝", 10.0, True),
            self._sample("R1", 2, "芝", 90.0, False),
            self._sample("R2", 1, "ダート", 80.0, True),
            self._sample("R2", 2, "ダート", 20.0, False),
        ]
        reports = {
            profile.name: self._report(baseline_samples) for profile in DEFAULT_PAI_WEIGHT_PROFILES
        }
        reports["swing5"] = self._report(candidate_samples)

        comparisons = compare_pai_weight_reports(reports)

        candidate = next(item for item in comparisons if item.profile.name == "swing5")
        assert candidate.turf.delta_point_biserial == -2.0
        assert candidate.turf.delta_top_band_lift == -2.0
        assert candidate.dirt.delta_point_biserial == 0.0
        assert candidate.dirt.delta_top_band_lift == 0.0

    def test_missing_baseline_and_different_horses_raise(self) -> None:
        with pytest.raises(ValueError, match="基準プロファイル"):
            compare_pai_weight_reports({})

        baseline = self._report([self._sample("R1", 1, "芝", 80.0, True)])
        reports = {profile.name: baseline for profile in DEFAULT_PAI_WEIGHT_PROFILES}
        reports["swing25"] = self._report([self._sample("R1", 2, "芝", 80.0, True)])
        with pytest.raises(ValueError, match="比較対象馬"):
            compare_pai_weight_reports(reports)

    def test_json_and_text_include_weights_track_metrics_and_deltas(self) -> None:
        report = self._report(
            [
                self._sample("R1", 1, "芝", 90.0, True),
                self._sample("R1", 2, "芝", 10.0, False),
            ]
        )
        reports = {profile.name: report for profile in DEFAULT_PAI_WEIGHT_PROFILES}

        comparisons = compare_pai_weight_reports(reports)
        payload = pai_weight_comparisons_to_dict(comparisons)

        assert payload[0]["name"] == "current"
        assert payload[0]["weights"]["pace_swing"] == DEFAULT_PAI_WEIGHTS.pace_swing
        assert payload[0]["weights"]["sensitivity_escape"] == 1.0
        assert payload[0]["turf"]["pai"]["n"] == 2
        assert payload[0]["dirt"]["pai"] is None
        assert payload[0]["combined"]["delta_vs_current"]["point_biserial"] == 0.0
        text = format_pai_weight_comparison(comparisons)
        assert "候補は自動採用しません" in text
        assert "全体" in text
        assert "ダート" in text
        assert "上位帯n=" in text  # 母数の減少でリフトが跳ねる候補を見分けるため

    def test_pace_off_is_available_as_the_null_hypothesis(self) -> None:
        """ペース補正を全て切った候補が常設されていること。

        current と並ぶなら、ペース補正は判別に寄与していない。
        """
        profile = next(p for p in DEFAULT_PAI_WEIGHT_PROFILES if p.name == "pace-off")

        w = profile.weights
        assert w.sensitivity_escape == 0.0
        assert w.sensitivity_front == 0.0
        assert w.sensitivity_flexible == 0.0
        # ペース以外は現行と同じでないと切り分けにならない。
        assert w.pace_swing == DEFAULT_PAI_WEIGHTS.pace_swing
        assert w.distance_weight_per_200m == DEFAULT_PAI_WEIGHTS.distance_weight_per_200m
        assert w.off_track_penalty == DEFAULT_PAI_WEIGHTS.off_track_penalty


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

    def test_progress_reports_every_race_including_skipped(self) -> None:
        """進捗は「集計に載った数」ではなく「見た数」を返す。

        飛ばされたレースを黙って数えないと、リモートDB相手に何分も無音のまま
        カウンタだけ止まって見える。止まっているのか進んでいるのかの区別が
        付かなくなるので、skip も1件として通知する。
        """
        repo = FakeRaceRepository()
        counted = _seed_result_race(
            repo,
            "2026011505010101",
            15,
            rpci_actual=50.0,
            horses=[(1, "H1", 1), (2, "H2", 8)],
        )
        skipped = _seed_result_race(
            repo, "2026011505010102", 15, rpci_actual=None, horses=[(1, "H3", 1)]
        )

        seen: list[int] = []
        report = ForecastBacktester(repo).run([counted, skipped], progress=seen.append)

        assert seen == [1, 2]
        assert report.n_races == 1
        assert report.skipped == 1

    def test_runs_without_progress_callback(self) -> None:
        repo = FakeRaceRepository()
        target = _seed_result_race(
            repo, "2026011505010101", 15, rpci_actual=50.0, horses=[(1, "H1", 1)]
        )
        assert ForecastBacktester(repo).run([target]).n_races == 1

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
                "track_type": "",
            }
        ]
        assert result["horse_samples"] == [
            {
                "race_key": "2026010105010101",
                "horse_no": 1,
                "pai": 80.0,
                "good_run": True,
                "track_type": "",
            }
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


class TestFitCrowding:
    """レース単位で見ないと「全頭合致」が見えない。

    全体の構成比が3割でも、一部のレースで全頭が合致していれば、そのレースでは
    展開が絞り込みの手がかりにならない。判断に使うのはレース単位の分布。
    """

    @staticmethod
    def _h(race_key: str, horse_no: int, label: str) -> HorseSample:
        return HorseSample(
            race_key=race_key,
            horse_no=horse_no,
            pai=50.0,
            good_run=False,
            track_type="芝",
            running_style="先行",
            fit_label=label,
        )

    def test_empty_returns_empty(self) -> None:
        assert summarize_fit_crowding([]) == []

    def test_counts_races_where_the_whole_field_is_suited(self) -> None:
        samples = [
            # 全頭合致のレース
            self._h("R1", 1, "合致"),
            self._h("R1", 2, "合致"),
            # 半数のレース
            self._h("R2", 1, "合致"),
            self._h("R2", 2, "中立"),
            # 合致なしのレース
            self._h("R3", 1, "中立"),
            self._h("R3", 2, "不利"),
        ]

        rows = summarize_fit_crowding(samples)

        assert len(rows) == 1
        row = rows[0]
        assert row.races == 3
        # R1(1.0) と R2(0.5) が「半数以上」に該当する。
        assert row.majority_race_share == pytest.approx(2 / 3, abs=1e-4)
        assert row.all_suited_race_share == pytest.approx(1 / 3, abs=1e-4)

    def test_median_share_reflects_the_middle_race(self) -> None:
        samples = [
            self._h("R1", 1, "中立"),
            self._h("R1", 2, "中立"),
            self._h("R2", 1, "合致"),
            self._h("R2", 2, "中立"),
            self._h("R3", 1, "合致"),
            self._h("R3", 2, "合致"),
        ]

        row = summarize_fit_crowding(samples)[0]

        assert row.median_share == pytest.approx(0.5, abs=1e-4)
        assert row.median_suited_count == pytest.approx(1.0, abs=1e-4)


class TestMatchedThresholdRecommendation:
    """閾値は測って決める。実測ではダートの中央値が53.8%で、芝の30.0%と揃わない。

    合致は単一の絶対閾値（55）だが、PAI の分布はコースで平均が5点ほどずれている。
    同じ物差しを別々の分布へ当てているので、ダートだけ過半数が合致になる。
    """

    @staticmethod
    def _race(race_key: str, pais: list[float], track: str = "ダート") -> list[HorseSample]:
        return [
            HorseSample(
                race_key=race_key,
                horse_no=i + 1,
                pai=pai,
                good_run=False,
                track_type=track,
                running_style="先行",
                fit_label="合致" if pai >= 55.0 else "中立",
            )
            for i, pai in enumerate(pais)
        ]

    def test_recommends_the_lowest_threshold_that_reaches_the_target(self) -> None:
        # 10頭中8頭が 55 以上。60 以上は3頭、62 以上は2頭。
        pais = [50.0, 52.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0, 63.0]
        row = summarize_fit_crowding(self._race("R1", pais))[0]

        assert row.median_share == pytest.approx(0.8, abs=1e-4)
        # 60.0 だと 60/61/62/63 の4頭で40%。0.5刻みの次の点 60.5 で3頭=30%に届く。
        assert row.recommended_threshold == pytest.approx(60.5, abs=1e-6)
        assert row.recommended_median_share == pytest.approx(0.3, abs=1e-4)

    def test_leaves_the_threshold_where_it_is_when_already_within_target(self) -> None:
        """既に目標以下なら走査の下端をそのまま返す——締め上げない。

        絞り込みは目的ではなく手段。届いている側まで動かすと、恩恵を受ける馬を
        理由なく落とすことになる。
        """
        pais = [40.0, 41.0, 42.0, 43.0, 56.0]
        row = summarize_fit_crowding(self._race("R1", pais))[0]

        assert row.recommended_threshold == pytest.approx(45.0, abs=1e-6)
        assert row.recommended_median_share == pytest.approx(0.2, abs=1e-4)

    def test_reports_unreachable_when_every_horse_stays_suited(self) -> None:
        """上限まで走査しても届かない場合は None。**黙って上限を返さない。**

        届かなかったことは、閾値では解けない（分布そのものが潰れている）という
        情報なので、成功と同じ形で返してはいけない。
        """
        row = summarize_fit_crowding(self._race("R1", [99.0, 99.0, 99.0]))[0]

        assert row.recommended_threshold is None
        assert row.recommended_median_share is None

    def test_solves_each_course_separately(self) -> None:
        turf = self._race("T1", [40.0, 41.0, 42.0, 56.0], track="芝")
        dirt = self._race("D1", [56.0, 57.0, 58.0, 59.0], track="ダート")

        rows = {row.track_type: row for row in summarize_fit_crowding(turf + dirt)}

        assert rows["芝"].recommended_threshold == pytest.approx(45.0, abs=1e-6)
        # 4頭で目標30%なら1頭まで。58.0 では 58/59 の2頭が残るので 58.5。
        assert rows["ダート"].recommended_threshold == pytest.approx(58.5, abs=1e-6)


class TestFitLabelShares:
    """ラベルの良し悪しは脚質を固定して判断する。

    脚質を跨いだ集計では「不利」が「中立」を上回ることがあるが、これは閾値の
    ずれではなく脚質構成の差（絶対的な好走率は脚質ごとに 0.47x〜1.43x）。
    """

    @staticmethod
    def _h(style: str, label: str, good: bool) -> HorseSample:
        return HorseSample(
            race_key="R1",
            horse_no=1,
            pai=50.0,
            good_run=good,
            track_type="芝",
            running_style=style,
            fit_label=label,
        )

    def test_empty_returns_empty(self) -> None:
        assert summarize_fit_label_shares([]) == []

    def test_emits_a_whole_track_row_and_one_row_per_style(self) -> None:
        samples = [self._h("逃げ", "合致", True), self._h("追込", "不利", False)]

        rows = summarize_fit_label_shares(samples)

        styles = {r.style for r in rows}
        assert styles == {"", "逃げ", "追込"}
        # 3ラベル × (全体 + 2脚質)
        assert len(rows) == 9

    def test_share_is_relative_to_its_own_group(self) -> None:
        samples = [
            self._h("逃げ", "合致", True),
            self._h("逃げ", "中立", False),
            self._h("追込", "不利", False),
        ]

        rows = {(r.style, r.label): r for r in summarize_fit_label_shares(samples)}

        # 逃げの中では合致が半分。全体では3頭中1頭。
        assert rows[("逃げ", "合致")].share == pytest.approx(0.5)
        assert rows[("", "合致")].share == pytest.approx(1 / 3, abs=1e-4)

    def test_format_marks_ordering_per_group(self) -> None:
        """脚質内で 合致 > 中立 > 不利 なら順当、崩れていれば逆転と出す。"""
        ordered = (
            [self._h("逃げ", "合致", True) for _ in range(10)]
            + [self._h("逃げ", "中立", i < 5) for i in range(10)]
            + [self._h("逃げ", "不利", False) for _ in range(10)]
        )
        assert "順当" in format_fit_label_shares(summarize_fit_label_shares(ordered))

        inverted = (
            [self._h("逃げ", "合致", False) for _ in range(10)]
            + [self._h("逃げ", "中立", i < 5) for i in range(10)]
            + [self._h("逃げ", "不利", True) for _ in range(10)]
        )
        assert "逆転" in format_fit_label_shares(summarize_fit_label_shares(inverted))

    def test_format_warns_against_judging_on_the_whole_track_row(self) -> None:
        out = format_fit_label_shares(summarize_fit_label_shares([self._h("逃げ", "合致", True)]))
        assert "「全体」行の逆転で閾値を判断しないこと" in out
