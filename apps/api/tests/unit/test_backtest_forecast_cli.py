"""バックテストCLIのRPCI監視オプション回帰テスト。"""

import datetime
import sys

import pytest
from scripts.backtest_forecast import _parse_args


def test_monitoring_uses_safe_dirt_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["backtest_forecast", "--monitor-dirt-v4"])

    args = _parse_args()

    assert args.track_type == "ダート"
    assert args.date_from == datetime.date(2026, 7, 25)
    assert args.sample_every == 1


def test_monitoring_keeps_explicit_start_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["backtest_forecast", "--monitor-dirt-v4", "--date-from", "2026-08-01"],
    )

    args = _parse_args()

    assert args.date_from == datetime.date(2026, 8, 1)


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--track-type", "芝"],
        ["--sample-every", "2"],
        ["--dirt-model-path", "models/rpci_lgbm_dirt_v4.txt"],
    ],
)
def test_monitoring_rejects_non_production_conditions(
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["backtest_forecast", "--monitor-dirt-v4", *extra_args],
    )

    with pytest.raises(SystemExit):
        _parse_args()


def test_fail_on_review_requires_monitoring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["backtest_forecast", "--fail-on-monitoring-review"])

    with pytest.raises(SystemExit):
        _parse_args()
