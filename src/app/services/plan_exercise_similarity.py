"""Label-similarity scoring for plan-exercise alternatives."""

from collections.abc import Collection, Hashable
from dataclasses import dataclass
from uuid import UUID

from app.services.plan_generation_domain import PlanExerciseCandidate

_SCALAR_RANGE = 4  # values live on 1..5 inclusive


@dataclass(frozen=True)
class SimilarityLabels:
    """Planning labels used to compare a replaced slot with a candidate."""

    equipment_ids: frozenset[UUID]
    training_type_ids: frozenset[UUID]
    segment_ids: frozenset[int]
    physical_difficulty: int
    technical_difficulty: int
    upper_body_load: int
    lower_body_load: int
    core_load: int


def labels_from_candidate(candidate: PlanExerciseCandidate) -> SimilarityLabels:
    """Map a generation candidate into the similarity feature set."""
    return SimilarityLabels(
        equipment_ids=frozenset(candidate.equipment_ids),
        training_type_ids=frozenset(candidate.training_type_ids),
        segment_ids=frozenset(candidate.segment_ids),
        physical_difficulty=candidate.physical_difficulty,
        technical_difficulty=candidate.technical_difficulty,
        upper_body_load=candidate.upper_body_load,
        lower_body_load=candidate.lower_body_load,
        core_load=candidate.core_load,
    )


def jaccard_similarity(
    left: Collection[Hashable], right: Collection[Hashable]
) -> float:
    """Return Jaccard index; empty∩empty counts as a perfect match."""
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


def scalar_similarity(left: int, right: int) -> float:
    """Map absolute distance on the 1..5 scale into [0, 1]."""
    return 1.0 - abs(left - right) / _SCALAR_RANGE


def label_similarity(reference: SimilarityLabels, candidate: SimilarityLabels) -> float:
    """Average equal-weight feature-group similarities into one [0, 1] score."""
    equipment = jaccard_similarity(reference.equipment_ids, candidate.equipment_ids)
    training_types = jaccard_similarity(
        reference.training_type_ids, candidate.training_type_ids
    )
    segments = jaccard_similarity(reference.segment_ids, candidate.segment_ids)
    difficulties = (
        scalar_similarity(reference.physical_difficulty, candidate.physical_difficulty)
        + scalar_similarity(
            reference.technical_difficulty, candidate.technical_difficulty
        )
    ) / 2
    body_loads = (
        scalar_similarity(reference.upper_body_load, candidate.upper_body_load)
        + scalar_similarity(reference.lower_body_load, candidate.lower_body_load)
        + scalar_similarity(reference.core_load, candidate.core_load)
    ) / 3
    return (equipment + training_types + segments + difficulties + body_loads) / 5
