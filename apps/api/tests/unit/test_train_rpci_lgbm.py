"""LightGBM学習データ定義の回帰テスト。"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scripts.train_rpci_lgbm import (
    _HISTORY_FEATURES,
    _HISTORY_JOIN,
    _LAP_FEATURES,
    _LAP_JOIN,
    _QUERY_TEMPLATE,
    _build_label_sample_weights,
    _parse_args,
    _print_label_recall,
    _write_training_provenance,
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


def test_training_query_supports_independent_period_cutoff() -> None:
    assert "{date_filter}" in _QUERY_TEMPLATE


def test_training_query_contains_v2_features() -> None:
    assert "AS field_size" in _QUERY_TEMPLATE
    assert "AS escape_competition" in _QUERY_TEMPLATE
    assert "AS distance_middle" in _QUERY_TEMPLATE
    assert "AS venue_10" in _QUERY_TEMPLATE


def test_v3_history_query_uses_only_prior_races() -> None:
    assert "pr.race_date < r.race_date" in _HISTORY_JOIN
    assert "LIMIT 10" in _HISTORY_JOIN
    assert "COALESCE(pe.corner_1, pe.corner_4) <= 2" in _HISTORY_JOIN
    assert "AS history_front_coverage" in _HISTORY_FEATURES


def test_v4_lap_query_uses_only_prior_races_and_last_ten_runs() -> None:
    assert "pr.race_date < r.race_date" in _LAP_JOIN
    assert "pr.race_l3f - pr.race_s3f AS lap_delta" in _LAP_JOIN
    assert "LIMIT 10" in _LAP_JOIN
    assert "COUNT(prior.lap_delta) AS sample_size" in _LAP_JOIN
    assert "AS history_lap_coverage" in _LAP_FEATURES


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


def test_v2_feature_set_requires_explicit_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["train_rpci_lgbm", "--track-type", "turf", "--feature-set", "v2"],
    )

    with pytest.raises(SystemExit):
        _parse_args()

    assert "本番モデルの上書きを防ぐため" in capsys.readouterr().err


def test_v3_feature_set_requires_explicit_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["train_rpci_lgbm", "--track-type", "dirt", "--feature-set", "v3"],
    )

    with pytest.raises(SystemExit):
        _parse_args()

    assert "本番モデルの上書きを防ぐため" in capsys.readouterr().err


def test_v4_feature_set_requires_explicit_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["train_rpci_lgbm", "--track-type", "dirt", "--feature-set", "v4"],
    )

    with pytest.raises(SystemExit):
        _parse_args()

    assert "本番モデルの上書きを防ぐため" in capsys.readouterr().err


class TestTrainingProvenance:
    """モデルの隣に残す学習来歴の回帰テスト。

    2026-08-02: `rpci_actual`の算出式が旧フォールバックからラップ由来へ
    切り替わっていたのに、モデル側は何も知らず系統的にずれ続けていた
    （HANDOFF 2026-07-26 (12)）。同じ見落としを繰り返さないための記録。
    """

    @staticmethod
    def _rows(feature_count: int, lap_flags: list[int]) -> list[tuple[object, ...]]:
        # [特徴量..., target, race_date, has_lap] の並びを模す
        return [
            tuple([0.0] * feature_count)
            + (50.0, datetime.date(2026, 1, index + 1), flag)
            for index, flag in enumerate(lap_flags)
        ]

    def _write(self, tmp_path: Path, lap_flags: list[int]) -> dict[str, object]:
        feature_count = 3
        args = argparse.Namespace(
            feature_set="v4",
            label_balance="none",
            model_version="lgbm-dirt-v5-lap-history",
            before_date=datetime.date(2026, 6, 1),
            limit=2000,
            rpci_min=20.0,
            rpci_max=90.0,
        )
        meta_path = _write_training_provenance(
            tmp_path / "model.txt",
            rows=self._rows(feature_count, lap_flags),
            feature_count=feature_count,
            args=args,
            track_type="dirt",
            metrics={"mae": 4.5289, "rmse": 5.4, "bias": 3.3731},
        )
        result: dict[str, object] = json.loads(meta_path.read_text(encoding="utf-8"))
        return result

    def test_records_lap_derived_ratio_and_date_range(self, tmp_path: Path) -> None:
        payload = self._write(tmp_path, [1, 1, 1, 1])

        assert payload["lap_derived_ratio"] == 1.0
        assert payload["n_races"] == 4
        assert payload["date_from"] == "2026-01-01"
        assert payload["date_to"] == "2026-01-04"
        assert payload["track_type"] == "dirt"
        assert payload["model_version"] == "lgbm-dirt-v5-lap-history"

    def test_flags_training_data_that_still_contains_the_old_formula(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = self._write(tmp_path, [1, 1, 0, 0])

        assert payload["lap_derived_ratio"] == 0.5
        assert "旧フォールバック式" in capsys.readouterr().out

    def test_sidecar_sits_next_to_the_model(self, tmp_path: Path) -> None:
        self._write(tmp_path, [1])

        assert (tmp_path / "model.txt.meta.json").exists()

    def test_metrics_are_rounded_for_readability(self, tmp_path: Path) -> None:
        payload = self._write(tmp_path, [1])

        assert payload["test_metrics"] == {"mae": 4.5289, "rmse": 5.4, "bias": 3.3731}
