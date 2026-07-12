"""枠順確定後の序盤隊列を、脚質と過去の位置取りから予想する。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.reason import Reason

MODEL_VERSION = "formation-v1"


class FormationZone(StrEnum):
    """スタート後の想定位置。値はAPIで安定して扱う識別子。"""

    LEAD = "lead"
    FRONT = "front"
    MIDFIELD = "midfield"
    REAR = "rear"


_ZONE_ORDER: tuple[FormationZone, ...] = (
    FormationZone.LEAD,
    FormationZone.FRONT,
    FormationZone.MIDFIELD,
    FormationZone.REAR,
)
_ZONE_LABELS: dict[FormationZone, str] = {
    FormationZone.LEAD: "先頭",
    FormationZone.FRONT: "好位",
    FormationZone.MIDFIELD: "中団",
    FormationZone.REAR: "後方",
}
_STYLE_POSITION: dict[RunningStyleLabel, float] = {
    RunningStyleLabel.ESCAPE: 0.0,
    RunningStyleLabel.FRONT: 1.0,
    RunningStyleLabel.STALKER: 2.0,
    RunningStyleLabel.CLOSER: 3.0,
    RunningStyleLabel.FLEXIBLE: 2.0,
}


@dataclass(frozen=True)
class FormationWeights:
    """formation-v1 の仮係数。実データ検証後に更新可能にする。"""

    style_weight: float = 0.7
    recent_position_weight: float = 0.3

    def __post_init__(self) -> None:
        if self.style_weight < 0 or self.recent_position_weight < 0:
            raise ValueError("隊列予想の重みは0以上である必要があります")
        if not math.isclose(self.style_weight + self.recent_position_weight, 1.0):
            raise ValueError("隊列予想の重みの合計は1.0である必要があります")


@dataclass(frozen=True)
class FormationHorseInput:
    horse_no: int
    frame_no: int
    running_style: RunningStyleLabel
    style_confidence: float
    recent_early_position: float | None = None
    recent_sample_size: int = 0


@dataclass(frozen=True)
class FormationHorsePrediction:
    horse_no: int
    frame_no: int
    running_style: RunningStyleLabel
    zone: FormationZone
    confidence_label: str
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class FormationGroup:
    zone: FormationZone
    label: str
    horses: tuple[FormationHorsePrediction, ...]


@dataclass(frozen=True)
class FormationPrediction:
    model_version: str
    groups: tuple[FormationGroup, ...]


def has_confirmed_draw(horses: tuple[FormationHorseInput, ...]) -> bool:
    """特別登録の仮馬番を除き、全馬に実枠番がある場合だけ真を返す。"""
    if not horses:
        return False
    horse_numbers = [horse.horse_no for horse in horses]
    return (
        len(set(horse_numbers)) == len(horse_numbers)
        and all(horse_no > 0 for horse_no in horse_numbers)
        and all(1 <= horse.frame_no <= 8 for horse in horses)
    )


def predict_formation(
    horses: tuple[FormationHorseInput, ...],
    *,
    weights: FormationWeights | None = None,
) -> FormationPrediction | None:
    """枠順確定済みの場合のみ、4ゾーンの序盤隊列を返す。"""
    if not has_confirmed_draw(horses):
        return None

    config = weights or FormationWeights()
    predictions = tuple(_predict_horse(horse, config) for horse in horses)
    groups = tuple(
        FormationGroup(
            zone=zone,
            label=_ZONE_LABELS[zone],
            horses=tuple(
                sorted(
                    (horse for horse in predictions if horse.zone == zone),
                    key=lambda horse: (horse.frame_no, horse.horse_no),
                )
            ),
        )
        for zone in _ZONE_ORDER
    )
    return FormationPrediction(model_version=MODEL_VERSION, groups=groups)


def _predict_horse(
    horse: FormationHorseInput,
    weights: FormationWeights,
) -> FormationHorsePrediction:
    style_position = _STYLE_POSITION[horse.running_style]
    recent_position = _recent_position_zone(horse.recent_early_position)
    if recent_position is None:
        score = style_position
    else:
        score = (
            style_position * weights.style_weight + recent_position * weights.recent_position_weight
        )
    zone_index = min(3, max(0, math.floor(score + 0.5)))
    zone = _ZONE_ORDER[zone_index]

    reasons = [
        Reason(
            code="running_style",
            description=f"過去走から{horse.running_style}傾向と判定",
        )
    ]
    if recent_position is not None:
        reasons.append(
            Reason(
                code="recent_early_position",
                description="近走の序盤位置も加味",
            )
        )
    if horse.frame_no <= 2:
        reasons.append(Reason(code="inner_frame", description="内めの枠から位置を取りやすい想定"))
    elif horse.frame_no >= 7:
        reasons.append(Reason(code="outer_frame", description="外めの枠から周囲を見て運ぶ想定"))

    return FormationHorsePrediction(
        horse_no=horse.horse_no,
        frame_no=horse.frame_no,
        running_style=horse.running_style,
        zone=zone,
        confidence_label=_confidence_label(horse),
        reasons=tuple(reasons),
    )


def _recent_position_zone(position: float | None) -> float | None:
    if position is None:
        return None
    if position <= 2.0:
        return 0.0
    if position <= 5.0:
        return 1.0
    if position <= 9.0:
        return 2.0
    return 3.0


def _confidence_label(horse: FormationHorseInput) -> str:
    if horse.style_confidence >= 0.8 and horse.recent_sample_size >= 3:
        return "高"
    if horse.style_confidence >= 0.6 or horse.recent_sample_size >= 2:
        return "標準"
    return "参考"
