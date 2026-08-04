"""RPCI式の比較で使う「S3・L3・走破タイムの整合チェック」のテスト。

式の乖離を測る前提は、3者が同じレースの値であること。前提が崩れたレースを混ぜると
式の差ではなくデータ不整合を測ってしまうため、切り分けロジックを固定する。

2026-08-04: 全15,332件の実測で絶対差の中央値1.10に対し90%点16.20という二峰性が出た。
差16には中間区間が15.5秒/F必要（両端は11.7秒/F）で、競走としては起こらない。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

_SCRIPT = pathlib.Path(__file__).resolve().parents[1].parent / "scripts" / "diagnose_rpci.py"


def _load() -> Any:
    sys.path.insert(0, "src")
    spec = importlib.util.spec_from_file_location("diagnose_rpci_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_dr = _load()

# 2026-08-02 札幌11R 芝1800m（TARGET実測: LAP合計106.1 / S3 35.2 / L3 35.0）
_REAL = _dr._LapRow("2026080201010411", "2026-08-02", "芝", 1800, 35.2, 35.0, 106.1)


class TestImpliedMidPace:
    def test_real_race_middle_matches_both_ends(self) -> None:
        """実レースでは中間区間が両端(11.73/11.67秒/F)と揃う。"""
        assert _REAL.implied_mid_pace is not None
        assert round(_REAL.implied_mid_pace, 2) == 11.97

    def test_short_race_is_not_checkable(self) -> None:
        """1200m以下は中間区間が無く検査できない。"""
        row = _dr._LapRow("k", "2026-08-02", "芝", 1200, 34.5, 35.8, 70.3)

        assert row.implied_mid_pace is None

    def test_odd_distance_s3_covers_500m(self) -> None:
        """1300m = 100m + 200m×6 なので、先頭3区間は600mではなく500m。"""
        row = _dr._LapRow("k", "2023-02-04", "ダート", 1300, 31.3, 36.8, 81.5)

        assert row.s3_distance_m == 500

    def test_even_distance_s3_covers_600m(self) -> None:
        assert _REAL.s3_distance_m == 600

    def test_real_odd_distance_race_is_consistent(self) -> None:
        """東京ダート1300mの実データは、S3=500mとして扱えば整合する。

        S3を600mと誤って扱うと逆算中間が26.8秒/Fになり、正常なレースを
        「データ不整合」と誤判定する（2026-08-04にこの誤判定を出した）。
        """
        row = _dr._LapRow("2023020405010302", "2023-02-04", "ダート", 1300, 31.3, 36.8, 81.5)

        assert row.implied_mid_pace is not None
        assert round(row.implied_mid_pace, 2) == 13.40
        assert _dr._PLAUSIBLE_MID_LO <= row.implied_mid_pace <= _dr._PLAUSIBLE_MID_HI

    def test_inflated_race_time_shows_an_impossible_middle(self) -> None:
        """走破タイムだけずれると、中間区間が競走としてあり得ない値になる。"""
        row = _dr._LapRow("k", "2026-08-02", "芝", 1800, 35.2, 35.0, 116.7)

        assert row.implied_mid_pace is not None
        assert round(row.implied_mid_pace, 2) == 15.50
        assert row.implied_mid_pace > _dr._PLAUSIBLE_MID_HI


class TestIntegrityGate:
    def test_keeps_consistent_races(self) -> None:
        kept = _dr._print_lap_integrity([_REAL])

        assert [r.race_key for r in kept] == ["2026080201010411"]

    def test_drops_inconsistent_races(self) -> None:
        broken = _dr._LapRow("bad", "2026-08-02", "芝", 1800, 35.2, 35.0, 116.7)

        kept = _dr._print_lap_integrity([_REAL, broken])

        assert [r.race_key for r in kept] == ["2026080201010411"]

    def test_keeps_real_odd_distance_races(self) -> None:
        """端数距離の正常レースを不整合として捨てない。"""
        odd = _dr._LapRow("odd", "2023-02-04", "ダート", 1300, 31.3, 36.8, 81.5)

        kept = _dr._print_lap_integrity([_REAL, odd])

        assert {r.race_key for r in kept} == {"2026080201010411", "odd"}

    def test_keeps_short_races_that_cannot_be_checked(self) -> None:
        """検査できないものを不整合扱いにしない。"""
        short = _dr._LapRow("short", "2026-08-02", "芝", 1200, 34.5, 35.8, 70.3)

        kept = _dr._print_lap_integrity([_REAL, short])

        assert {r.race_key for r in kept} == {"2026080201010411", "short"}


class TestFormulaSamples:
    def test_real_race_reproduces_the_target_gap(self) -> None:
        samples, skipped = _dr._build_samples([_REAL])

        assert skipped == 0
        assert samples[0].current == 50.6
        assert samples[0].target == 51.6
        assert round(samples[0].diff, 1) == 1.0

    def test_label_change_is_detected(self) -> None:
        """芝は>51.0でスロー。50.6=平均 → 51.6=スロー で区分が変わる。"""
        samples, _ = _dr._build_samples([_REAL])

        assert samples[0].current_label == "平均"
        assert samples[0].target_label == "スロー"
        assert samples[0].label_changed is True

    def test_invalid_values_are_skipped_not_counted(self) -> None:
        """上がり3F ≧ 走破タイム のような値は比較へ混ぜない。"""
        bad = _dr._LapRow("bad", "2026-08-02", "芝", 1800, 35.2, 200.0, 106.1)

        samples, skipped = _dr._build_samples([bad])

        assert samples == []
        assert skipped == 1


class TestOddDistanceFormulaGap:
    """端数距離では現行式が前半3Fの距離を誤り、距離帯とは別要因で大きく外れる。"""

    def test_current_formula_misreads_the_front_pace_on_1300m(self) -> None:
        odd = _dr._LapRow("2023020405010302", "2023-02-04", "ダート", 1300, 31.3, 36.8, 81.5)

        samples, skipped = _dr._build_samples([odd])

        assert skipped == 0
        # 現行式はS3(500m)を600m扱いし、前半を実際より速い＝ハイ寄りと誤認する。
        assert samples[0].current == 35.1
        assert samples[0].target == 54.1
        assert samples[0].label_changed is True
