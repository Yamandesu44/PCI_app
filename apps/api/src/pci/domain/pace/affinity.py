"""馬ごとの得意なレース質を、過去好走時のペースから推定する。"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from pci.domain.pace.running_style import RunningStyleLabel
from pci.domain.shared.race_key import RaceKey


class PaceSpeedLevel(StrEnum):
    """PCI/RPCI 系の値を5段階のレース質に丸めた内部表現。"""

    VERY_HIGH = "veryHigh"
    HIGH = "high"
    AVERAGE = "average"
    SLOW = "slow"
    VERY_SLOW = "verySlow"


@dataclass(frozen=True)
class PaceAffinityEvidence:
    race_key: RaceKey
    finish_pos: int
    pace_level: PaceSpeedLevel
    weight: float
    reason: str


@dataclass(frozen=True)
class HorsePaceAffinityProfile:
    horse_id: str
    sample_size: int
    preferred_level: PaceSpeedLevel | None
    scores: dict[PaceSpeedLevel, int]
    evidence: tuple[PaceAffinityEvidence, ...]
    confidence: float
    is_fallback: bool = False


@dataclass(frozen=True)
class PaceAffinityRaceResult:
    race_key: RaceKey
    race_date: datetime.date
    finish_pos: int | None
    grade: str | None
    rpci_actual: float | None
    pci3_actual: float | None
    pci_actual: float | None


def pace_level_from_index(value: float) -> PaceSpeedLevel:
    """PCI/RPCI/PCI3の値を5段階のペースレベルへ変換する。"""
    if value < 47.0:
        return PaceSpeedLevel.VERY_HIGH
    if value < 50.0:
        return PaceSpeedLevel.HIGH
    if value <= 52.0:
        return PaceSpeedLevel.AVERAGE
    if value <= 55.0:
        return PaceSpeedLevel.SLOW
    return PaceSpeedLevel.VERY_SLOW


def build_horse_pace_affinity_profile(
    horse_id: str,
    running_style: RunningStyleLabel,
    results: tuple[PaceAffinityRaceResult, ...],
    *,
    as_of: datetime.date,
) -> HorsePaceAffinityProfile:
    evidence_items: list[PaceAffinityEvidence] = []
    for result in results:
        if not _is_good_run(result):
            continue
        evidence = _evidence_from_result(result, as_of)
        if evidence is not None:
            evidence_items.append(evidence)
    evidence = tuple(evidence_items)
    if not evidence:
        return _fallback_profile(horse_id, running_style)

    weighted_count = {level: 0.0 for level in PaceSpeedLevel}
    for item in evidence:
        weighted_count[item.pace_level] += item.weight

    max_weight = max(weighted_count.values())
    scores = {
        level: round((value / max_weight) * 100) if value > 0 else 0
        for level, value in weighted_count.items()
    }
    preferred_level = max(scores, key=lambda level: scores[level])
    sample_size = len(evidence)
    return HorsePaceAffinityProfile(
        horse_id=horse_id,
        sample_size=sample_size,
        preferred_level=preferred_level,
        scores=scores,
        evidence=evidence,
        confidence=_confidence(sample_size),
    )


def level_display(level: PaceSpeedLevel | None) -> str:
    return {
        PaceSpeedLevel.VERY_HIGH: "かなり速い流れ",
        PaceSpeedLevel.HIGH: "速い流れ",
        PaceSpeedLevel.AVERAGE: "平均的な流れ",
        PaceSpeedLevel.SLOW: "落ち着いた流れ",
        PaceSpeedLevel.VERY_SLOW: "かなり落ち着いた流れ",
        None: "判断材料が少ない流れ",
    }[level]


def affinity_label(score: int) -> str:
    if score >= 75:
        return "高相性"
    if score >= 55:
        return "合致"
    if score >= 40:
        return "中立"
    return "不安"


def _evidence_from_result(
    result: PaceAffinityRaceResult, as_of: datetime.date
) -> PaceAffinityEvidence | None:
    value = _pace_index_value(result)
    if value is None or result.finish_pos is None:
        return None
    level = pace_level_from_index(value)
    weight = _base_weight(result.finish_pos) * _recency_weight((as_of - result.race_date).days)
    return PaceAffinityEvidence(
        race_key=result.race_key,
        finish_pos=result.finish_pos,
        pace_level=level,
        weight=weight,
        reason=f"{level_display(level)}で好走",
    )


def _pace_index_value(result: PaceAffinityRaceResult) -> float | None:
    if result.rpci_actual is not None:
        return result.rpci_actual
    if result.pci3_actual is not None:
        return result.pci3_actual
    return result.pci_actual


def _is_good_run(result: PaceAffinityRaceResult) -> bool:
    if result.finish_pos is None:
        return False
    if result.finish_pos <= 3:
        return True
    return _is_graded(result.grade) and result.finish_pos <= 5


def _is_graded(grade: str | None) -> bool:
    if not grade:
        return False
    normalized = grade.upper()
    return "G1" in normalized or "G2" in normalized or "G3" in normalized or "JPN" in normalized


def _base_weight(finish_pos: int) -> float:
    return {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.65, 5: 0.65}.get(finish_pos, 0.0)


def _recency_weight(days: int) -> float:
    if days <= 180:
        return 1.0
    if days <= 365:
        return 0.9
    if days <= 730:
        return 0.75
    return 0.6


def _confidence(sample_size: int) -> float:
    if sample_size >= 5:
        return 1.0
    if sample_size >= 3:
        return 0.8
    return 0.6


def _fallback_profile(
    horse_id: str, running_style: RunningStyleLabel
) -> HorsePaceAffinityProfile:
    scores = _fallback_scores(running_style)
    preferred_level = max(scores, key=lambda level: scores[level])
    return HorsePaceAffinityProfile(
        horse_id=horse_id,
        sample_size=0,
        preferred_level=preferred_level,
        scores=scores,
        evidence=(),
        confidence=0.4,
        is_fallback=True,
    )


def _fallback_scores(running_style: RunningStyleLabel) -> dict[PaceSpeedLevel, int]:
    if running_style == RunningStyleLabel.ESCAPE:
        return {
            PaceSpeedLevel.SLOW: 55,
            PaceSpeedLevel.VERY_SLOW: 60,
            PaceSpeedLevel.AVERAGE: 45,
            PaceSpeedLevel.HIGH: 35,
            PaceSpeedLevel.VERY_HIGH: 25,
        }
    if running_style == RunningStyleLabel.FRONT:
        return {
            PaceSpeedLevel.SLOW: 55,
            PaceSpeedLevel.AVERAGE: 55,
            PaceSpeedLevel.VERY_SLOW: 50,
            PaceSpeedLevel.HIGH: 40,
            PaceSpeedLevel.VERY_HIGH: 30,
        }
    if running_style == RunningStyleLabel.STALKER:
        return {
            PaceSpeedLevel.HIGH: 55,
            PaceSpeedLevel.AVERAGE: 50,
            PaceSpeedLevel.VERY_HIGH: 50,
            PaceSpeedLevel.SLOW: 40,
            PaceSpeedLevel.VERY_SLOW: 30,
        }
    if running_style == RunningStyleLabel.CLOSER:
        return {
            PaceSpeedLevel.VERY_HIGH: 60,
            PaceSpeedLevel.HIGH: 55,
            PaceSpeedLevel.AVERAGE: 40,
            PaceSpeedLevel.SLOW: 30,
            PaceSpeedLevel.VERY_SLOW: 20,
        }
    return {level: 40 for level in PaceSpeedLevel}
