"""Unit coverage for plan-exercise label similarity scoring."""

from uuid import UUID

from app.services.plan_exercise_similarity import (
    SimilarityLabels,
    jaccard_similarity,
    label_similarity,
    scalar_similarity,
)

EQ_A = UUID("410327de-b35a-4dcf-8b99-5249e159ce06")
EQ_B = UUID("510327de-b35a-4dcf-8b99-5249e159ce06")


def test_jaccard_empty_sets_are_a_perfect_match() -> None:
    assert jaccard_similarity(set(), set()) == 1.0


def test_jaccard_identical_and_disjoint_sets() -> None:
    assert jaccard_similarity({EQ_A}, {EQ_A}) == 1.0
    assert jaccard_similarity({EQ_A}, {EQ_B}) == 0.0
    assert jaccard_similarity({EQ_A, EQ_B}, {EQ_A}) == 0.5


def test_scalar_similarity_bounds_on_one_to_five_scale() -> None:
    assert scalar_similarity(3, 3) == 1.0
    assert scalar_similarity(1, 5) == 0.0
    assert scalar_similarity(2, 4) == 0.5


def test_label_similarity_identical_labels_score_one() -> None:
    labels = SimilarityLabels(
        equipment_ids=frozenset({EQ_A}),
        training_type_ids=frozenset(),
        segment_ids=frozenset({3}),
        physical_difficulty=3,
        technical_difficulty=4,
        upper_body_load=2,
        lower_body_load=5,
        core_load=3,
    )
    assert label_similarity(labels, labels) == 1.0


def test_label_similarity_averages_feature_groups() -> None:
    reference = SimilarityLabels(
        equipment_ids=frozenset({EQ_A}),
        training_type_ids=frozenset(),
        segment_ids=frozenset({3}),
        physical_difficulty=1,
        technical_difficulty=1,
        upper_body_load=1,
        lower_body_load=1,
        core_load=1,
    )
    opposite = SimilarityLabels(
        equipment_ids=frozenset({EQ_B}),
        training_type_ids=frozenset(),
        segment_ids=frozenset({9}),
        physical_difficulty=5,
        technical_difficulty=5,
        upper_body_load=5,
        lower_body_load=5,
        core_load=5,
    )
    # equipment 0, types 1, segments 0, difficulties 0, body loads 0 → 0.2
    assert label_similarity(reference, opposite) == 0.2
