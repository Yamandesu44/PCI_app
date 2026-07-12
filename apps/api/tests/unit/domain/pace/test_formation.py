"""枠順確定後の隊列予想テスト。"""

import pytest

from pci.domain.pace.formation import (
    FormationHorseInput,
    FormationWeights,
    FormationZone,
    has_confirmed_draw,
    predict_formation,
)
from pci.domain.pace.running_style import RunningStyleLabel


def _horse(
    horse_no: int,
    frame_no: int,
    style: RunningStyleLabel,
    *,
    style_confidence: float = 0.8,
    recent_position: float | None = None,
    sample_size: int = 3,
) -> FormationHorseInput:
    return FormationHorseInput(
        horse_no=horse_no,
        frame_no=frame_no,
        running_style=style,
        style_confidence=style_confidence,
        recent_early_position=recent_position,
        recent_sample_size=sample_size,
    )


def test_special_registration_is_not_draw_confirmed() -> None:
    horses = (_horse(1, 0, RunningStyleLabel.ESCAPE),)
    assert has_confirmed_draw(horses) is False
    assert predict_formation(horses) is None


def test_duplicate_or_invalid_horse_numbers_are_rejected() -> None:
    duplicate = (
        _horse(1, 1, RunningStyleLabel.ESCAPE),
        _horse(1, 2, RunningStyleLabel.FRONT),
    )
    invalid = (_horse(0, 1, RunningStyleLabel.ESCAPE),)
    assert has_confirmed_draw(duplicate) is False
    assert has_confirmed_draw(invalid) is False


def test_styles_are_placed_in_four_zones() -> None:
    prediction = predict_formation(
        (
            _horse(1, 1, RunningStyleLabel.ESCAPE),
            _horse(2, 2, RunningStyleLabel.FRONT),
            _horse(3, 3, RunningStyleLabel.STALKER),
            _horse(4, 4, RunningStyleLabel.CLOSER),
        )
    )
    assert prediction is not None
    assert prediction.model_version == "formation-v1"
    assert [group.zone for group in prediction.groups] == list(FormationZone)
    assert [group.horses[0].horse_no for group in prediction.groups] == [1, 2, 3, 4]


def test_recent_early_position_can_move_flexible_horse_forward() -> None:
    prediction = predict_formation(
        (
            _horse(
                5,
                2,
                RunningStyleLabel.FLEXIBLE,
                style_confidence=0.0,
                recent_position=1.0,
            ),
        )
    )
    assert prediction is not None
    front = next(group for group in prediction.groups if group.zone == FormationZone.FRONT)
    assert front.horses[0].horse_no == 5
    assert any(reason.code == "recent_early_position" for reason in front.horses[0].reasons)


def test_horses_are_ordered_by_frame_within_zone() -> None:
    prediction = predict_formation(
        (
            _horse(8, 8, RunningStyleLabel.FRONT),
            _horse(2, 2, RunningStyleLabel.FRONT),
        )
    )
    assert prediction is not None
    front = next(group for group in prediction.groups if group.zone == FormationZone.FRONT)
    assert [horse.horse_no for horse in front.horses] == [2, 8]


def test_confidence_and_frame_reasons_are_explainable() -> None:
    prediction = predict_formation(
        (
            _horse(1, 1, RunningStyleLabel.ESCAPE),
            _horse(8, 8, RunningStyleLabel.CLOSER, style_confidence=0.2, sample_size=0),
        )
    )
    assert prediction is not None
    lead = prediction.groups[0].horses[0]
    rear = prediction.groups[-1].horses[0]
    assert lead.confidence_label == "高"
    assert rear.confidence_label == "参考"
    assert any(reason.code == "inner_frame" for reason in lead.reasons)
    assert any(reason.code == "outer_frame" for reason in rear.reasons)


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="合計は1.0"):
        FormationWeights(style_weight=0.8, recent_position_weight=0.3)
