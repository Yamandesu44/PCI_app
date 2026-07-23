"""LightGBM学習データ定義の回帰テスト。"""

import numpy as np
import pytest
from scripts.train_rpci_lgbm import _QUERY_TEMPLATE, _print_label_recall

from pci.domain.pace.rpci_forecast import PaceLabel


def test_training_query_uses_canonical_running_style_labels() -> None:
    assert "e.running_style = '逃げ'" in _QUERY_TEMPLATE
    assert "('逃げ','先行')" in _QUERY_TEMPLATE
    assert "('差し','追込')" in _QUERY_TEMPLATE
    assert "e.running_style = '逃'" not in _QUERY_TEMPLATE
    assert "('逃','先')" not in _QUERY_TEMPLATE
    assert "('差','追')" not in _QUERY_TEMPLATE


def test_training_query_selects_latest_races_for_temporal_split() -> None:
    assert "ORDER BY r.race_date DESC, r.race_key DESC" in _QUERY_TEMPLATE


def test_label_recall_uses_track_specific_thresholds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    features = np.array(
        [
            [1600.0, 0.0, 5.0, 1.0, 0.3, 0.4, 0.1, 0.0],
            [1600.0, 1.0, 5.0, 1.0, 0.3, 0.4, 0.1, 0.0],
        ]
    )

    _print_label_recall(
        np.array([50.0, 39.0]),
        np.array([50.0, 39.0]),
        features,
        "all",
    )

    output = capsys.readouterr().out
    assert f"芝「{PaceLabel.AVERAGE}」: 100.0% (1/1)" in output
    assert f"ダート「{PaceLabel.HIGH}」: 100.0% (1/1)" in output
