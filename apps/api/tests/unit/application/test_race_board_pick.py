"""レースボードの「展開に合う馬」の選び方と、適性カテゴリの丸め方のテスト。

一覧に出る1頭は PAI 最大では選ばない。PAI は脚質内の相対量なので、脚質を
またいだ最大値は「最も展開が向く馬」を意味しない。実測ではダートの追込が
好走率 0.47x でありながら高い PAI を取りうる（docs/DECISIONS.md ADR-2026-08-04）。
"""

from __future__ import annotations

from pci.application.dto import (
    ForecastOutput,
    HorseFitOutput,
    StyleAdvantageEntryOutput,
    StyleAdvantageOutput,
)
from pci.application.race_board_use_cases import _fit_strength, _pick_pace_benefiting_horse
from pci.domain.pace.adaptability import DEFAULT_WEIGHTS as PAI_WEIGHTS
from pci.domain.pace.running_style import RunningStyleLabel


def _horse(horse_no: int, style: str, pai: float) -> HorseFitOutput:
    return HorseFitOutput(
        horse_no=horse_no,
        frame_no=horse_no,
        horse_name=f"馬{horse_no}",
        running_style=style,
        pai=pai,
        fit_label="中立",
    )


def _forecast(
    horses: list[HorseFitOutput],
    style_scores: dict[str, float] | None = None,
) -> ForecastOutput:
    advantage = (
        StyleAdvantageOutput(
            model_version="style-advantage-v4",
            entries=[
                StyleAdvantageEntryOutput(style=style, score=score)
                for style, score in style_scores.items()
            ],
        )
        if style_scores is not None
        else None
    )
    return ForecastOutput(
        race_key="2026060105010101",
        predicted_rpci=50.0,
        pace_label="平均",
        confidence=0.7,
        model_version="test",
        scenario_headline="h",
        scenario_detail="d",
        horses=horses,
        style_advantage=advantage,
    )


class TestPickPaceBenefitingHorse:
    def test_returns_none_without_horses(self) -> None:
        assert _pick_pace_benefiting_horse(_forecast([])) is None

    def test_does_not_pick_the_highest_pai_when_its_style_is_unfavoured(self) -> None:
        """PAIが最大でも、脚質が不利なら選ばない。"""
        out = _pick_pace_benefiting_horse(
            _forecast(
                [_horse(1, "追込", 78.0), _horse(2, "逃げ", 52.0)],
                {"逃げ": 72.0, "追込": 38.0},
            )
        )

        assert out is not None
        assert out.horse_no == 2

    def test_uses_pai_within_the_same_style(self) -> None:
        out = _pick_pace_benefiting_horse(
            _forecast([_horse(1, "逃げ", 48.0), _horse(2, "逃げ", 62.0)], {"逃げ": 72.0})
        )

        assert out is not None
        assert out.horse_no == 2

    def test_missing_style_score_counts_as_even(self) -> None:
        """有利度が取れない脚質は互角(50)。不利な脚質より上に置く。"""
        out = _pick_pace_benefiting_horse(
            _forecast([_horse(1, "自在", 55.0), _horse(2, "追込", 90.0)], {"追込": 38.0})
        )

        assert out is not None
        assert out.horse_no == 1

    def test_falls_back_to_pai_without_style_advantage(self) -> None:
        out = _pick_pace_benefiting_horse(
            _forecast([_horse(1, "追込", 40.0), _horse(2, "逃げ", 70.0)], None)
        )

        assert out is not None
        assert out.horse_no == 2


class TestFitStrength:
    """閾値はドメインの合致ラベルから引く。実数を直書きするとスケール変更で壊れる。"""

    def test_below_the_matched_threshold_is_normal(self) -> None:
        matched = PAI_WEIGHTS.matched_threshold_for("芝", RunningStyleLabel.ESCAPE)
        assert _fit_strength(matched - 0.1, "芝", "逃げ") == "normal"

    def test_at_the_matched_threshold_is_notable(self) -> None:
        matched = PAI_WEIGHTS.matched_threshold_for("芝", RunningStyleLabel.ESCAPE)
        assert _fit_strength(matched, "芝", "逃げ") == "notable"

    def test_uses_the_threshold_of_the_horses_own_style(self) -> None:
        """pai-v5: 同じ PAI でも脚質が違えば判定が変わる。

        芝の自在は合致 49.5、芝の先行は 68.5。PAI 60 は自在なら合致、先行なら中立。
        **共通の代表値で代用すると、脚質によって当たり外れのある基準を黙って当てる。**
        """
        assert _fit_strength(60.0, "芝", "自在") != "normal"
        assert _fit_strength(60.0, "芝", "先行") == "normal"

    def test_unknown_style_falls_back_to_normal(self) -> None:
        """脚質が取れないなら強調しない。代表値で埋めない。"""
        assert _fit_strength(99.0, "芝", "") == "normal"

    def test_strong_is_reachable_for_every_course_and_style(self) -> None:
        """到達不可能な閾値を置かない。**全10セルで確かめる。**

        pai-v4 で振れ幅を 25 → 10 へ下げた際、旧値の 80 はほぼ到達しなくなり
        「注目」が黙って出なくなるところだった。pai-v5 で合致閾値を脚質別へ上げた
        ときも、固定幅 +10点 のままなら10セル中3セルで到達不能になっていた
        （ダート先行は合致72.0に対し上限78.25で、余地が6.25点しかない）。
        """
        for track in ("芝", "ダート"):
            for style in RunningStyleLabel:
                max_pai = PAI_WEIGHTS.max_pai_for(style)
                assert _fit_strength(max_pai, track, style.value) == "strong", (
                    f"{track}{style.value} で「注目」に到達できない"
                )

    def test_notable_is_reachable_for_every_course_and_style(self) -> None:
        for track in ("芝", "ダート"):
            for style in RunningStyleLabel:
                matched = PAI_WEIGHTS.matched_threshold_for(track, style)
                assert matched <= PAI_WEIGHTS.max_pai_for(style), (
                    f"{track}{style.value} の合致閾値が PAI 上限を超えている"
                )
