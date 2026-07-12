"""脚質判定テスト（ゴールデン + プロパティ）。"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pci.domain.pace.running_style import (
    DEFAULT_THRESHOLDS,
    MODEL_VERSION,
    PREDICTION_MODEL_VERSION,
    DistanceStyleWeights,
    RunningStyleHistory,
    RunningStyleLabel,
    RunningStyleThresholds,
    classify_running_style,
    predict_running_style_for_distance,
)

# ----- ゴールデンテスト -----

GOLDEN_CASES = [
    # (positions, expected_label)
    ((1, 2, 1, 1, 2), RunningStyleLabel.ESCAPE),  # 1-2番手率100% → 逃げ
    ((1, 1, 1, 1, 1), RunningStyleLabel.ESCAPE),  # 全走1番手 → 逃げ
    ((3, 4, 5, 3, 4), RunningStyleLabel.FRONT),  # 先行
    ((6, 7, 8, 7, 8), RunningStyleLabel.STALKER),  # 差し
    ((10, 12, 11, 15, 10), RunningStyleLabel.CLOSER),  # 追込
    ((1, 5, 9, 14, 3), RunningStyleLabel.FLEXIBLE),  # バラバラ → 自在
    ((2, 4, 7, 11, 6), RunningStyleLabel.FLEXIBLE),  # 自在
]


@pytest.mark.parametrize(
    "positions, expected_label",
    GOLDEN_CASES,
    ids=[f"{c[1].value}" for c in GOLDEN_CASES],
)
def test_running_style_golden(
    positions: tuple[int, ...], expected_label: RunningStyleLabel
) -> None:
    result = classify_running_style(positions)
    assert result.label == expected_label


def test_empty_positions_returns_flexible_with_zero_confidence() -> None:
    result = classify_running_style(())
    assert result.label == RunningStyleLabel.FLEXIBLE
    assert result.confidence == 0.0


def test_single_position_escape() -> None:
    result = classify_running_style((1,))
    assert result.label == RunningStyleLabel.ESCAPE
    assert result.confidence == pytest.approx(1.0)


def test_result_always_has_reasons() -> None:
    for positions, _ in GOLDEN_CASES:
        result = classify_running_style(positions)
        assert len(result.reasons) > 0, f"reasons が空: {positions}"


def test_result_has_model_version() -> None:
    result = classify_running_style((1, 1, 1, 1, 1))
    assert result.model_version == MODEL_VERSION


def test_only_first_5_races_used() -> None:
    """6走目以降は無視される（lookback_races=5）。"""
    all_escape = (1, 1, 1, 1, 1)
    # 後ろに追込的なデータを追加しても5走分だけ見る
    with_extra = (1, 1, 1, 1, 1, 14, 14, 14)
    assert (
        classify_running_style(all_escape).label
        == classify_running_style(with_extra).label
        == RunningStyleLabel.ESCAPE
    )


def test_confidence_reflects_rate() -> None:
    """confidence は対象番手率と一致する。"""
    positions = (1, 1, 1, 2, 5)  # 1-2番手: 4/5 = 0.80
    result = classify_running_style(positions)
    assert result.label == RunningStyleLabel.ESCAPE
    assert result.confidence == pytest.approx(0.80)


def test_custom_thresholds_applied() -> None:
    """カスタム閾値が正しく適用される。"""
    strict_th = RunningStyleThresholds(rate_threshold=0.80)
    # 3/5 = 60%: デフォルト閾値(60%)では逃げだがstrict(80%)では自在
    positions = (1, 1, 1, 10, 14)
    assert classify_running_style(positions).label == RunningStyleLabel.ESCAPE
    result_strict = classify_running_style(positions, thresholds=strict_th)
    assert result_strict.label == RunningStyleLabel.FLEXIBLE


def test_mixed_style_uses_shorter_distance_front_history_as_front() -> None:
    """先行と差しが半々なら、今回より短い距離での先行歴を優先する。"""
    histories = (
        RunningStyleHistory(corner_position=4, distance_m=1200),
        RunningStyleHistory(corner_position=7, distance_m=1600),
        RunningStyleHistory(corner_position=4, distance_m=1200),
        RunningStyleHistory(corner_position=7, distance_m=1600),
    )

    result = predict_running_style_for_distance(histories, target_distance_m=1600)

    assert result.label == RunningStyleLabel.FRONT
    assert result.model_version == PREDICTION_MODEL_VERSION
    assert result.reasons[0].code == "mixed_style_resolved"
    assert "短い距離" in result.reasons[0].description


def test_mixed_style_uses_longer_distance_front_history_as_stalker() -> None:
    """先行歴が今回より長い距離に偏る場合は、差し寄りに補正する。"""
    histories = (
        RunningStyleHistory(corner_position=4, distance_m=2000),
        RunningStyleHistory(corner_position=7, distance_m=1600),
        RunningStyleHistory(corner_position=4, distance_m=2000),
        RunningStyleHistory(corner_position=7, distance_m=1600),
    )

    result = predict_running_style_for_distance(histories, target_distance_m=1600)

    assert result.label == RunningStyleLabel.STALKER
    assert "長い距離" in result.reasons[0].description


def test_distance_prediction_preserves_decisive_style() -> None:
    histories = tuple(
        RunningStyleHistory(corner_position=1, distance_m=distance)
        for distance in (1200, 1400, 1600, 1800, 2000)
    )

    result = predict_running_style_for_distance(histories, target_distance_m=1600)

    assert result.label == RunningStyleLabel.ESCAPE
    assert result.model_version == MODEL_VERSION


def test_distance_prediction_without_history_stays_flexible() -> None:
    result = predict_running_style_for_distance((), target_distance_m=1600)
    assert result.label == RunningStyleLabel.FLEXIBLE
    assert result.confidence == 0.0


def test_distance_style_weights_validate_values() -> None:
    with pytest.raises(ValueError, match="距離スケール"):
        DistanceStyleWeights(distance_scale_m=0)


# ----- プロパティテスト -----


@given(st.integers(min_value=0, max_value=5))
def test_escape_rate_determines_classification(escape_count: int) -> None:
    """1〜2番手が threshold 以上の割合なら 逃げ と分類される。"""
    # 1番手 escape_count 走、残りを追込圏(14)に設定
    positions = tuple([1] * escape_count + [14] * (5 - escape_count))
    result = classify_running_style(positions)
    th = DEFAULT_THRESHOLDS
    escape_rate = escape_count / 5
    if escape_rate >= th.rate_threshold:
        assert result.label == RunningStyleLabel.ESCAPE
    else:
        assert result.label != RunningStyleLabel.ESCAPE


@given(
    n=st.integers(min_value=1, max_value=10),
    position=st.integers(min_value=1, max_value=20),
)
def test_result_label_is_always_valid(n: int, position: int) -> None:
    """任意の入力でも常に有効な RunningStyleLabel が返る。"""
    positions = tuple([position] * n)
    result = classify_running_style(positions)
    assert result.label in RunningStyleLabel


@given(
    positions=st.tuples(*[st.integers(min_value=1, max_value=20)] * 5),
)
def test_confidence_is_between_0_and_1(positions: tuple[int, ...]) -> None:
    """confidence は常に 0〜1 の範囲。"""
    result = classify_running_style(positions)
    assert 0.0 <= result.confidence <= 1.0


@given(
    positions=st.tuples(*[st.integers(min_value=1, max_value=20)] * 5),
)
def test_reasons_always_present(positions: tuple[int, ...]) -> None:
    """任意の入力でも reasons が必ず含まれる（説明可能性）。"""
    result = classify_running_style(positions)
    assert len(result.reasons) > 0
