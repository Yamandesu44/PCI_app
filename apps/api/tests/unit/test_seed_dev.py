"""seed_dev.py の PCI 計算・データ設計の単体テスト（DB 不要）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

# seed_dev は scripts/ を sys.path 挿入後に import するため通常のソート順を適用しない
from seed_dev import (  # type: ignore[import-not-found]  # noqa: I001
    CONFIRMED_RACE_KEY,
    UPCOMING_RACE_KEY,
    _CONFIRMED_DISTANCE_M,
    _CONFIRMED_HORSES,
    _CONFIRMED_RESULTS,
    _HISTORY_RACES,
    _UPCOMING_HORSES,
    _pci,
    aggregate_rpci,
)

from pci.domain.pace.running_style import classify_running_style


class TestSeedRaceKeys:
    def test_upcoming_key_length(self) -> None:
        assert len(UPCOMING_RACE_KEY) == 16

    def test_confirmed_key_length(self) -> None:
        assert len(CONFIRMED_RACE_KEY) == 16

    def test_upcoming_is_after_confirmed(self) -> None:
        """出走前レースが確定後レースより新しい日付である。"""
        upcoming_date = UPCOMING_RACE_KEY[4:8]   # MMDD 部分
        confirmed_date = CONFIRMED_RACE_KEY[4:8]
        assert upcoming_date > confirmed_date

    def test_history_races_are_before_confirmed(self) -> None:
        """過去レースはすべて確定後レースより前の日付である。"""
        confirmed_year = CONFIRMED_RACE_KEY[:4]
        confirmed_mmdd = CONFIRMED_RACE_KEY[4:8]
        for race_key, _ in _HISTORY_RACES:
            year = race_key[:4]
            mmdd = race_key[4:8]
            assert (year, mmdd) < (confirmed_year, confirmed_mmdd), (
                f"{race_key} は確定後レースより後の日付"
            )


class TestConfirmedPci:
    def _pci_list(self) -> list[float]:
        return [
            _pci(rt, a3f, _CONFIRMED_DISTANCE_M)
            for _, _, _, _, rt, a3f, *_ in _CONFIRMED_RESULTS
        ]

    def test_all_pci_values_are_positive(self) -> None:
        for pci in self._pci_list():
            assert pci > 0

    def test_rpci_is_measurable(self) -> None:
        """先週結果から RPCI を算出できること。"""
        pci_values = self._pci_list()
        finish_positions = [row[3] for row in _CONFIRMED_RESULTS]
        result = aggregate_rpci(pci_values, finish_positions)
        assert result.rpci is not None
        assert 40.0 <= result.rpci <= 70.0

    def test_pci3_is_measurable(self) -> None:
        """上位3頭 PCI3 を算出できること。"""
        pci_values = self._pci_list()
        finish_positions = [row[3] for row in _CONFIRMED_RESULTS]
        result = aggregate_rpci(pci_values, finish_positions)
        assert result.pci3 is not None
        assert 40.0 <= result.pci3 <= 70.0

    def test_sample_size(self) -> None:
        pci_values = self._pci_list()
        finish_positions = [row[3] for row in _CONFIRMED_RESULTS]
        result = aggregate_rpci(pci_values, finish_positions)
        assert result.sample_size == len(_CONFIRMED_RESULTS)

    def test_finish_positions_unique(self) -> None:
        positions = [row[3] for row in _CONFIRMED_RESULTS]
        assert len(set(positions)) == len(positions), "着順が重複している"

    def test_finish_positions_consecutive(self) -> None:
        positions = sorted(row[3] for row in _CONFIRMED_RESULTS)
        assert positions == list(range(1, len(_CONFIRMED_RESULTS) + 1))

    def test_horse_numbers_unique(self) -> None:
        horse_nos = [row[1] for row in _CONFIRMED_RESULTS]
        assert len(set(horse_nos)) == len(horse_nos)

    def test_winner_is_sashi(self) -> None:
        """先週結果の勝ち馬が差し脚質であること。"""
        winner = next(r for r in _CONFIRMED_RESULTS if r[3] == 1)
        assert winner[-1] == "差し", f"勝ち馬の脚質={winner[-1]}"

    def test_pci_formula_version(self) -> None:
        pci_values = self._pci_list()
        finish_positions = [row[3] for row in _CONFIRMED_RESULTS]
        result = aggregate_rpci(pci_values, finish_positions)
        assert result.formula_version == "pci-v3"


class TestUpcomingRunningStyles:
    def _classify(self, horse_idx: int) -> str:
        _, _, _, _, c4_history = _UPCOMING_HORSES[horse_idx]
        return str(classify_running_style(tuple(c4_history)).label)

    def test_horse1_is_nigeru(self) -> None:
        assert self._classify(0) == "逃げ"

    def test_horse2_is_senkou(self) -> None:
        assert self._classify(1) == "先行"

    def test_horse3_is_sashi(self) -> None:
        assert self._classify(2) == "差し"

    def test_horse4_is_oikomi(self) -> None:
        assert self._classify(3) == "追込"

    def test_horse5_is_sashi(self) -> None:
        assert self._classify(4) == "差し"

    def test_horse6_is_senkou(self) -> None:
        assert self._classify(5) == "先行"

    def test_horse7_is_senkou(self) -> None:
        assert self._classify(6) == "先行"

    def test_horse8_is_sashi(self) -> None:
        assert self._classify(7) == "差し"

    def test_horse10_is_oikomi(self) -> None:
        assert self._classify(9) == "追込"

    def test_history_race_count(self) -> None:
        """過去レースが5走分あること（running_style 判定の最大参照数）。"""
        assert len(_HISTORY_RACES) == 5

    def test_c4_history_length_matches_history_races(self) -> None:
        for _, name, _, _, c4_history in _UPCOMING_HORSES:
            assert len(c4_history) == len(_HISTORY_RACES), (
                f"{name} の c4_history が _HISTORY_RACES と長さが違う"
            )

    def test_field_size_consistency(self) -> None:
        """出走前レースの field_size とマスタデータ件数が一致。"""
        assert len(_UPCOMING_HORSES) == 10

    def test_confirmed_field_size_consistency(self) -> None:
        assert len(_CONFIRMED_RESULTS) == len(_CONFIRMED_HORSES)


class TestMasterDataIntegrity:
    def test_all_upcoming_ketto_nums_unique(self) -> None:
        kettos = [row[0] for row in _UPCOMING_HORSES]
        assert len(set(kettos)) == len(kettos)

    def test_all_confirmed_ketto_nums_unique(self) -> None:
        kettos = [row[0] for row in _CONFIRMED_HORSES]
        assert len(set(kettos)) == len(kettos)

    def test_no_overlap_between_upcoming_and_confirmed(self) -> None:
        """出走前と確定後で馬番号が重ならない（別レース・別馬）。"""
        upcoming_kettos = {row[0] for row in _UPCOMING_HORSES}
        confirmed_kettos = {row[0] for row in _CONFIRMED_HORSES}
        assert upcoming_kettos.isdisjoint(confirmed_kettos)

    def test_ketto_num_length(self) -> None:
        for ketto, *_ in _UPCOMING_HORSES:
            assert len(ketto) == 10, f"ketto_num {ketto} は10文字でない"
        for ketto, *_ in _CONFIRMED_HORSES:
            assert len(ketto) == 10, f"ketto_num {ketto} は10文字でない"
