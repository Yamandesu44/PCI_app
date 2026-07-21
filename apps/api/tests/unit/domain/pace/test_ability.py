"""ability-v1（能力指数）の単体テスト。"""

from __future__ import annotations

from pci.domain.pace.ability import (
    MODEL_VERSION,
    AbilityRaceResult,
    AbilityScorer,
)


def _run(
    finish_pos: int | None,
    field_size: int,
    days_ago: int,
    race_class: str | None = None,
    popularity: int | None = None,
    prize_money: int | None = None,
    grade: str | None = None,
) -> AbilityRaceResult:
    return AbilityRaceResult(
        finish_pos=finish_pos,
        field_size=field_size,
        race_class=race_class,
        days_ago=days_ago,
        grade=grade,
        popularity=popularity,
        prize_money=prize_money,
    )


class TestAbilityScorer:
    def test_no_data_returns_zero_and_reason(self) -> None:
        result = AbilityScorer().score(3, ())
        assert result.score == 0.0
        assert result.sample_size == 0
        assert result.model_version == MODEL_VERSION
        assert any(r.code == "ability_no_data" for r in result.reasons)

    def test_winner_scores_higher_than_last(self) -> None:
        winner = AbilityScorer().score(1, (_run(1, 10, 30), _run(2, 12, 60)))
        loser = AbilityScorer().score(2, (_run(9, 10, 30), _run(11, 12, 60)))
        assert winner.score > loser.score

    def test_field_size_normalizes_finish(self) -> None:
        """同じ着順でも、頭数が多いほど価値が高い（相対的な着順評価）。"""
        big_field = AbilityScorer().score(1, (_run(3, 18, 30),))
        small_field = AbilityScorer().score(2, (_run(3, 6, 30),))
        assert big_field.score > small_field.score

    def test_higher_class_scores_higher(self) -> None:
        """同じ相対着順なら、上のクラスの方が高評価。"""
        g1 = AbilityScorer().score(1, (_run(3, 10, 30, "天皇賞・秋(G1)"),))
        maiden = AbilityScorer().score(2, (_run(3, 10, 30, "3歳未勝利"),))
        assert g1.score > maiden.score

    def test_recency_weighting(self) -> None:
        """新しい好走の方が古い好走より効く。"""
        fresh = AbilityScorer().score(1, (_run(1, 10, 20), _run(10, 10, 400)))
        stale = AbilityScorer().score(2, (_run(10, 10, 20), _run(1, 10, 400)))
        assert fresh.score > stale.score

    def test_score_bounded_0_100(self) -> None:
        best = AbilityScorer().score(1, (_run(1, 18, 10, "G1"),))
        worst = AbilityScorer().score(2, (_run(18, 18, 10, "3歳未勝利"),))
        assert 0.0 <= worst.score <= best.score <= 100.0

    def test_invalid_finish_ignored(self) -> None:
        """着順が頭数を超える等の不正データは無視される。"""
        result = AbilityScorer().score(1, (_run(20, 10, 30), _run(1, 10, 30)))
        assert result.sample_size == 1

    def test_recent_races_cap(self) -> None:
        """対象は直近 recent_races 走まで（既定5走）。"""
        runs = tuple(_run(1, 10, d) for d in (10, 20, 30, 40, 50, 60, 70))
        result = AbilityScorer().score(1, runs)
        assert result.sample_size == 5

    def test_reasons_have_no_raw_numbers_leak(self) -> None:
        """根拠は言葉ベース（内部scoreの数値をそのまま出さない）。"""
        result = AbilityScorer().score(1, (_run(2, 10, 30, "2勝クラス"),))
        assert all(str(result.score) not in r.description for r in result.reasons)

    def test_v3_falls_back_to_form_when_no_prize_or_popularity(self) -> None:
        """旧データ（人気・賞金なし）は form のみへ安全に縮退する。"""
        result = AbilityScorer().score(1, (_run(1, 10, 30, "2勝クラス"),))
        assert result.model_version == "ability-v3"
        assert not any("賞金" in r.description or "人気" in r.description for r in result.reasons)

    def test_v2_prize_lifts_score(self) -> None:
        """同じ着順内容でも、高額賞金の入着があれば地力評価が上がる。"""
        with_prize = AbilityScorer().score(
            1, (_run(3, 10, 30, "オープン", prize_money=30_000_000),)
        )
        without = AbilityScorer().score(2, (_run(3, 10, 30, "オープン"),))
        assert with_prize.score > without.score
        assert any("賞金" in r.description for r in with_prize.reasons)

    def test_v2_popularity_support_lifts_score(self) -> None:
        """人気（市場の支持）が高い近走があれば地力評価が上がる。"""
        backed = AbilityScorer().score(1, (_run(3, 10, 30, "2勝クラス", popularity=1),))
        unbacked = AbilityScorer().score(2, (_run(3, 10, 30, "2勝クラス", popularity=16),))
        assert backed.score > unbacked.score

    def test_v2_higher_prize_scores_higher(self) -> None:
        big = AbilityScorer().score(1, (_run(2, 12, 40, "G3", prize_money=50_000_000),))
        small = AbilityScorer().score(2, (_run(2, 12, 40, "G3", prize_money=1_000_000),))
        assert big.score > small.score

    def test_v3_grade_takes_priority_over_race_name(self) -> None:
        """競走名にG表記がなくても、正式gradeがあればクラス補正へ使う。"""
        graded = AbilityScorer().score(1, (_run(3, 10, 30, "共同通信杯", grade="G3"),))
        unknown = AbilityScorer().score(2, (_run(3, 10, 30, "共同通信杯"),))
        assert graded.score > unknown.score
        assert any("G3級" in reason.description for reason in graded.reasons)
