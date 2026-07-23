"""LightGBM学習データ定義の回帰テスト。"""

import sys

import numpy as np
import pytest
from scripts.train_rpci_lgbm import (
    _QUERY_TEMPLATE,
    _build_label_sample_weights,
    _parse_args,
    _print_label_recall,
)

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


def test_no_label_balance_returns_unit_weights() -> None:
    weights = _build_label_sample_weights(
        np.array([39.0, 43.0]),
        np.array([[1600.0, 1.0], [1600.0, 1.0]]),
        "dirt",
        "none",
    )

    assert weights.tolist() == [1.0, 1.0]


def test_sqrt_inverse_balance_upweights_rare_label() -> None:
    actuals = np.array([39.0, 43.0, 43.0, 43.0, 43.0])
    features = np.array([[1600.0, 1.0]] * len(actuals))

    weights = _build_label_sample_weights(
        actuals,
        features,
        "dirt",
        "sqrt-inverse",
    )

    assert weights[0] > weights[1]
    assert float(weights.mean()) == pytest.approx(1.0)


def test_sqrt_inverse_balance_uses_track_specific_groups() -> None:
    actuals = np.array([50.0, 50.0, 43.0, 43.0])
    features = np.array(
        [
            [1600.0, 0.0],
            [1600.0, 0.0],
            [1600.0, 1.0],
            [1600.0, 1.0],
        ]
    )

    weights = _build_label_sample_weights(
        actuals,
        features,
        "all",
        "sqrt-inverse",
    )

    assert weights.tolist() == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_inverse_balance_equalizes_label_total_weights() -> None:
    actuals = np.array([39.0, 43.0, 43.0, 43.0])
    features = np.array([[1600.0, 1.0]] * len(actuals))

    weights = _build_label_sample_weights(
        actuals,
        features,
        "dirt",
        "inverse",
    )

    assert weights[0] == pytest.approx(sum(weights[1:]))
    assert float(weights.mean()) == pytest.approx(1.0)


def test_balanced_training_requires_explicit_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["train_rpci_lgbm", "--track-type", "dirt", "--label-balance", "inverse"],
    )

    with pytest.raises(SystemExit):
        _parse_args()

    assert "本番モデルの上書きを防ぐため" in capsys.readouterr().err
