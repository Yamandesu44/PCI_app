"""build_pace_scenario 単体テスト。"""

from __future__ import annotations

from pci.domain.pace.adaptability import FitLabel, HorsePaceProfile, PaiResult
from pci.domain.pace.rpci_forecast import PaceLabel, RpciForecast
from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.pace.scenario import build_pace_scenario

ESCAPE = RunningStyleLabel.ESCAPE
FRONT = RunningStyleLabel.FRONT
CLOSER = RunningStyleLabel.CLOSER


def _forecast(label: PaceLabel, value: float = 50.0) -> RpciForecast:
    return RpciForecast(
        value=value, label=label, confidence=0.7, model_version="rule-v1", reasons=()
    )


def _pai(horse_no: int, pai: float, label: FitLabel) -> PaiResult:
    return PaiResult(
        horse_no=horse_no, pai=pai, fit_label=label, model_version="pai-v1", reasons=()
    )


def test_headline_reflects_pace_label() -> None:
    for label in PaceLabel:
        scenario = build_pace_scenario(
            _forecast(label), [], [], horse_numbers_confirmed=True
        )
        assert scenario.pace_label == label
        assert scenario.headline


def test_front_runners_listed() -> None:
    profiles = [
        HorsePaceProfile(1, ESCAPE),
        HorsePaceProfile(2, FRONT),
        HorsePaceProfile(3, CLOSER),
    ]
    scenario = build_pace_scenario(
        _forecast(PaceLabel.HIGH), [], profiles, horse_numbers_confirmed=True
    )
    assert scenario.front_runners == (1, 2)


def test_beneficiaries_sorted_by_pai_desc() -> None:
    fit_results = [
        _pai(1, 72.0, FitLabel.MATCHED),
        _pai(2, 90.0, FitLabel.MATCHED),
        _pai(3, 30.0, FitLabel.UNFAVORABLE),
    ]
    scenario = build_pace_scenario(
        _forecast(PaceLabel.HIGH), fit_results, [], horse_numbers_confirmed=True
    )
    assert scenario.beneficiaries == (2, 1)


def test_no_beneficiaries_handled() -> None:
    fit_results = [_pai(1, 50.0, FitLabel.NEUTRAL)]
    scenario = build_pace_scenario(
        _forecast(PaceLabel.AVERAGE), fit_results, [], horse_numbers_confirmed=True
    )
    assert scenario.beneficiaries == ()
    assert "該当なし" in scenario.detail or "少なく" in scenario.detail


def test_reasons_present() -> None:
    scenario = build_pace_scenario(
        _forecast(PaceLabel.SLOW), [], [], horse_numbers_confirmed=True
    )
    codes = {r.code for r in scenario.reasons}
    assert "scenario_pace" in codes
    assert "scenario_beneficiaries" in codes


def test_detail_mentions_top_beneficiary() -> None:
    fit_results = [_pai(7, 88.0, FitLabel.MATCHED)]
    profiles = [HorsePaceProfile(7, CLOSER)]
    scenario = build_pace_scenario(
        _forecast(PaceLabel.HIGH),
        fit_results,
        profiles,
        horse_numbers_confirmed=True,
    )
    assert "7" in scenario.detail
    assert "88" in scenario.detail


def test_detail_uses_registration_order_before_draw_confirmation() -> None:
    fit_results = [_pai(7, 88.0, FitLabel.MATCHED)]
    profiles = [HorsePaceProfile(7, ESCAPE)]

    scenario = build_pace_scenario(
        _forecast(PaceLabel.HIGH),
        fit_results,
        profiles,
        horse_numbers_confirmed=False,
    )

    assert "登録順 7（馬番未確定）" in scenario.detail
    assert "7番" not in scenario.detail
    beneficiary_reason = next(r for r in scenario.reasons if r.code == "scenario_beneficiaries")
    assert "登録順 7（馬番未確定）" in beneficiary_reason.description


def test_detail_uses_official_horse_number_after_draw_confirmation() -> None:
    fit_results = [_pai(7, 88.0, FitLabel.MATCHED)]
    profiles = [HorsePaceProfile(7, ESCAPE)]

    scenario = build_pace_scenario(
        _forecast(PaceLabel.HIGH),
        fit_results,
        profiles,
        horse_numbers_confirmed=True,
    )

    assert "7番" in scenario.detail
    assert "登録順" not in scenario.detail
