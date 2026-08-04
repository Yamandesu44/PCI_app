"""rpci_actual 移行スクリプトの閾値提案ロジックのテスト。

式を入れ替えると分布が動くため、閾値をそのままにすると「ハイ」「スロー」の
珍しさ（運用上の意味）が変わってしまう。構成比を保つ閾値を提示できることを固定する。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

_SCRIPT = pathlib.Path(__file__).resolve().parents[1].parent / "scripts" / "recompute_rpci.py"


def _load() -> Any:
    sys.path.insert(0, "src")
    spec = importlib.util.spec_from_file_location("recompute_rpci_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_rc = _load()


class TestLabelShares:
    def test_turf_shares_use_the_turf_thresholds(self) -> None:
        # 芝: <49.0 ハイ / >51.0 スロー
        shares = _rc._label_shares([40.0, 50.0, 60.0, 60.0], "芝")

        assert shares["ハイ"] == 0.25
        assert shares["平均"] == 0.25
        assert shares["スロー"] == 0.5

    def test_dirt_shares_use_the_dirt_thresholds(self) -> None:
        # ダート: <40.0 ハイ / >46.0 スロー
        shares = _rc._label_shares([35.0, 43.0, 50.0, 50.0], "ダート")

        assert shares["ハイ"] == 0.25
        assert shares["平均"] == 0.25
        assert shares["スロー"] == 0.5


class TestSuggestThresholds:
    def test_shifted_distribution_keeps_the_label_mix(self) -> None:
        """分布が一律にずれても、構成比を保つ閾値なら同じ割合を再現する。"""
        old = [float(v) for v in range(30, 70)]
        old_shares = _rc._label_shares(old, "芝")
        new = [v + 5.0 for v in old]  # 式の入れ替えで一律+5ずれた想定

        high, slow = _rc._suggest_thresholds(new, old_shares)

        assert high > _rc.DEFAULT_WEIGHTS.high_threshold
        assert slow > _rc.DEFAULT_WEIGHTS.slow_threshold
        reproduced = {
            "ハイ": sum(1 for v in new if v < high) / len(new),
            "スロー": sum(1 for v in new if v > slow) / len(new),
        }
        assert abs(reproduced["ハイ"] - old_shares["ハイ"]) <= 0.05
        assert abs(reproduced["スロー"] - old_shares["スロー"]) <= 0.05

    def test_unchanged_distribution_reproduces_current_thresholds(self) -> None:
        """分布が動かなければ、提案も現行閾値の近傍に落ち着く。"""
        values = [float(v) for v in range(30, 70)]
        shares = _rc._label_shares(values, "芝")

        high, slow = _rc._suggest_thresholds(values, shares)

        assert abs(high - _rc.DEFAULT_WEIGHTS.high_threshold) <= 1.5
        assert abs(slow - _rc.DEFAULT_WEIGHTS.slow_threshold) <= 1.5


class TestDryRunIsTheDefault:
    def test_apply_defaults_to_false(self, monkeypatch: Any) -> None:
        """既定でDBを書き換えないこと（誤操作で本番データを壊さない）。"""
        monkeypatch.setattr(sys, "argv", ["recompute_rpci"])

        assert _rc._parse_args().apply is False

    def test_apply_flag_is_explicit(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(sys, "argv", ["recompute_rpci", "--apply"])

        assert _rc._parse_args().apply is True
