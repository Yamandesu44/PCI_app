"""integrated-v1（統合順位予想・2軸分類）の単体テスト。"""

from __future__ import annotations

from pci.domain.pace.ability import MODEL_VERSION as ABILITY_VERSION
from pci.domain.pace.ability import AbilityScore
from pci.domain.pace.adaptability import FitLabel, PaiResult
from pci.domain.pace.integrated_ranking import (
    AbilityTier,
    Mark,
    build_integrated_ranking,
)


def _ability(horse_no: int, score: float, sample_size: int = 3) -> AbilityScore:
    return AbilityScore(
        horse_no=horse_no,
        score=score,
        sample_size=sample_size,
        model_version=ABILITY_VERSION,
        reasons=(),
    )


def _fit(horse_no: int, label: FitLabel) -> PaiResult:
    return PaiResult(
        horse_no=horse_no,
        pai=50.0,
        fit_label=label,
        model_version="pai-v1",
        reasons=(),
    )


class TestIntegratedRanking:
    def test_top_ability_and_matched_is_honmei(self) -> None:
        abilities = (_ability(1, 90), _ability(2, 50), _ability(3, 20))
        fits = (
            _fit(1, FitLabel.MATCHED),
            _fit(2, FitLabel.NEUTRAL),
            _fit(3, FitLabel.NEUTRAL),
        )
        ranking = build_integrated_ranking(abilities, fits)
        by_no = {e.horse_no: e for e in ranking.entries}
        assert by_no[1].mark == Mark.HONMEI
        assert by_no[1].ability_tier == AbilityTier.TOP

    def test_top_ability_but_unfavorable_is_kiken(self) -> None:
        """地力上位でも展開不利なら『危険』。"""
        abilities = (_ability(1, 90), _ability(2, 50), _ability(3, 20))
        fits = (
            _fit(1, FitLabel.UNFAVORABLE),
            _fit(2, FitLabel.NEUTRAL),
            _fit(3, FitLabel.NEUTRAL),
        )
        ranking = build_integrated_ranking(abilities, fits)
        by_no = {e.horse_no: e for e in ranking.entries}
        assert by_no[1].mark == Mark.KIKEN

    def test_middle_ability_matched_is_ana(self) -> None:
        """中位でも展開が向けば『穴』。"""
        abilities = (
            _ability(1, 90),
            _ability(2, 88),
            _ability(3, 50),
            _ability(4, 20),
            _ability(5, 18),
        )
        fits = (
            _fit(1, FitLabel.NEUTRAL),
            _fit(2, FitLabel.NEUTRAL),
            _fit(3, FitLabel.MATCHED),
            _fit(4, FitLabel.NEUTRAL),
            _fit(5, FitLabel.NEUTRAL),
        )
        ranking = build_integrated_ranking(abilities, fits)
        by_no = {e.horse_no: e for e in ranking.entries}
        assert by_no[3].ability_tier == AbilityTier.MIDDLE
        assert by_no[3].mark == Mark.ANA

    def test_no_data_horse_is_unknown_tier_and_no_mark(self) -> None:
        abilities = (_ability(1, 90), _ability(2, 0, sample_size=0))
        fits = (_fit(1, FitLabel.MATCHED), _fit(2, FitLabel.MATCHED))
        ranking = build_integrated_ranking(abilities, fits)
        by_no = {e.horse_no: e for e in ranking.entries}
        assert by_no[2].ability_tier == AbilityTier.UNKNOWN
        assert by_no[2].mark == Mark.NONE

    def test_ranks_are_unique_and_sequential(self) -> None:
        abilities = tuple(_ability(i, 100 - i * 10) for i in range(1, 6))
        fits = tuple(_fit(i, FitLabel.NEUTRAL) for i in range(1, 6))
        ranking = build_integrated_ranking(abilities, fits)
        ranks = sorted(e.rank for e in ranking.entries)
        assert ranks == [1, 2, 3, 4, 5]

    def test_honmei_ranks_above_kiken(self) -> None:
        """同じ上位（TOP）でも、展開が向く本命が向かない危険より上位表示。

        6頭立てなら top_n=2 なので、能力上位2頭(1・2番)がともに TOP になる。
        地力は 2番>1番 だが、展開が向く 1番(本命) を 2番(危険) より上位に置く。
        """
        abilities = (
            _ability(1, 80),
            _ability(2, 90),
            _ability(3, 50),
            _ability(4, 40),
            _ability(5, 30),
            _ability(6, 20),
        )
        fits = (
            _fit(1, FitLabel.MATCHED),  # 本命
            _fit(2, FitLabel.UNFAVORABLE),  # 危険（地力は上だが展開×）
            _fit(3, FitLabel.NEUTRAL),
            _fit(4, FitLabel.NEUTRAL),
            _fit(5, FitLabel.NEUTRAL),
            _fit(6, FitLabel.NEUTRAL),
        )
        ranking = build_integrated_ranking(abilities, fits)
        by_no = {e.horse_no: e for e in ranking.entries}
        assert by_no[1].mark == Mark.HONMEI
        assert by_no[2].mark == Mark.KIKEN
        assert by_no[1].rank < by_no[2].rank

    def test_summary_reasons_present(self) -> None:
        abilities = (_ability(1, 90), _ability(2, 50), _ability(3, 20))
        fits = (
            _fit(1, FitLabel.MATCHED),
            _fit(2, FitLabel.NEUTRAL),
            _fit(3, FitLabel.NEUTRAL),
        )
        ranking = build_integrated_ranking(abilities, fits)
        assert any(r.code == "integrated_honmei" for r in ranking.reasons)
