"""統合順位と市場（単勝人気）の比較のテスト。

利用者が比べる相手は「全馬平均」ではなく「1番人気を買った場合」。
この比較が無いままでは、順位予想が製品価値を持つか判断できない。
`ability-v3` は成分に単勝人気を含むため、市場情報を使いながら市場を上回れて
いるかという意味でも重要。
"""

from __future__ import annotations

from pci.application.backtest import (
    IntegratedSample,
    compare_with_market,
    format_ranking_comparison,
)


def _sample(race: str, horse_no: int, rank: int, finish: int | None) -> IntegratedSample:
    return IntegratedSample(
        race_key=race,
        horse_no=horse_no,
        rank=rank,
        finish_pos=finish,
        good_run=finish is not None and finish <= 3,
    )


class TestCompareWithMarket:
    def test_returns_none_without_market_data(self) -> None:
        integrated = [_sample("R1", 1, 1, 1)]

        assert compare_with_market(integrated, [], 1) is None

    def test_returns_none_when_no_race_overlaps(self) -> None:
        """人気データが別レースにしか無ければ比較できない。"""
        integrated = [_sample("R1", 1, 1, 1)]
        market = [_sample("R2", 1, 1, 1)]

        assert compare_with_market(integrated, market, 2) is None

    def test_restricts_both_sides_to_the_shared_races(self) -> None:
        """人気が欠けたレースを統合順位側にだけ残すと比較が歪む。

        R1 は両方にあり、R2 は統合順位にしかない。R2 を混ぜると統合順位だけが
        1レース分多い母数になり、勝率の比較が成立しない。
        """
        integrated = [
            _sample("R1", 1, 1, 5),  # 外し
            _sample("R2", 1, 1, 1),  # 的中（人気データ無し）
        ]
        market = [_sample("R1", 2, 1, 1)]  # R1の1番人気は勝った

        result = compare_with_market(integrated, market, 2)

        assert result is not None
        assert result.n_races == 1
        assert result.n_races_total == 2
        assert result.coverage == 0.5
        # R2 を除外しているので統合順位の勝率は 0%、市場は 100%。
        assert result.integrated.top1_win_rate == 0.0
        assert result.market.top1_win_rate == 1.0

    def test_market_uses_popularity_as_rank(self) -> None:
        """1番人気＝rank1 として、統合順位と同じ指標で測る。"""
        integrated = [_sample("R1", 1, 1, 1)]
        market = [
            _sample("R1", 5, 1, 4),  # 1番人気は4着
            _sample("R1", 1, 2, 1),  # 2番人気が勝った
        ]

        result = compare_with_market(integrated, market, 1)

        assert result is not None
        assert result.market.top1_win_rate == 0.0
        assert result.integrated.top1_win_rate == 1.0
        assert result.win_rate_delta == 1.0


class TestBeatsMarket:
    def test_true_only_when_no_metric_is_worse(self) -> None:
        """1指標でも下回れば「市場以上」とは呼ばない。

        捕捉率の分母は「そのレースで好走した馬」全体なので、上位3位圏外で
        好走した馬まで含めて初めて差が出る。
        """
        # 3着馬を統合順位は4位、市場は3位に置いている。
        integrated = [
            _sample("R1", 1, 1, 1),
            _sample("R1", 2, 2, 2),
            _sample("R1", 3, 3, 9),
            _sample("R1", 4, 4, 3),
        ]
        market = [
            _sample("R1", 1, 1, 1),
            _sample("R1", 2, 2, 2),
            _sample("R1", 4, 3, 3),
            _sample("R1", 3, 4, 9),
        ]

        result = compare_with_market(integrated, market, 1)

        assert result is not None
        # 1位は同じ馬なので勝率・好走率は互角、TOP3捕捉率だけ市場が上。
        assert result.win_rate_delta == 0.0
        assert result.good_rate_delta == 0.0
        assert result.capture_rate_delta < 0
        assert result.beats_market is False

    def test_true_when_all_metrics_match_or_exceed(self) -> None:
        samples = [_sample("R1", 1, 1, 1), _sample("R1", 2, 2, 2), _sample("R1", 3, 3, 3)]

        result = compare_with_market(samples, samples, 1)

        assert result is not None
        assert result.beats_market is True


class TestFormat:
    def test_empty_when_nothing_to_compare(self) -> None:
        assert format_ranking_comparison(None) == ""

    def test_marks_metrics_that_fall_short(self) -> None:
        integrated = [_sample("R1", 1, 1, 5)]
        market = [_sample("R1", 2, 1, 1)]

        text = format_ranking_comparison(compare_with_market(integrated, market, 1))

        assert "市場（単勝人気）との比較" in text
        assert "!" in text  # 下回った指標に印が付く
        assert "再検討" in text

    def test_states_when_the_ranking_wins(self) -> None:
        integrated = [_sample("R1", 1, 1, 1)]
        market = [_sample("R1", 2, 1, 8)]

        text = format_ranking_comparison(compare_with_market(integrated, market, 1))

        assert "3指標すべてで市場以上" in text
