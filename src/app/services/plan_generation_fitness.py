"""Fitness criteria scoring one segment individual in the range [0, 1]."""

from collections.abc import Callable
from uuid import UUID

from app.services.plan_generation_constants import RECENT_USAGE_MAX_DISTANCE
from app.services.plan_generation_domain import (
    GenerationContext,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_fitness_constants import (
    AGE_COVERAGE_WEIGHT,
    BODY_BALANCE_WEIGHT,
    DURATION_WEIGHT,
    EQUIPMENT_USAGE_WEIGHT,
    PHYSICAL_DIFFICULTY_WEIGHT,
    RECENT_USAGE_WEIGHT,
    TECHNICAL_DIFFICULTY_WEIGHT,
    TRAINING_TYPE_WEIGHT,
)
from app.services.plan_generation_fitness_math import (
    gaussian,
    time_weighted_means,
    time_weighted_score,
    windowed_score,
)

FitnessCriterion = Callable[[GenerationContext, PlanIndividual], float]


def evaluate_duration_time(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Penalize overtime more harshly than undertime."""
    relative_deviation = _relative_duration_deviation(context, individual)
    sigma = (
        context.fitness_parameters.duration_over_sigma_ratio
        if relative_deviation > 0
        else context.fitness_parameters.duration_under_sigma_ratio
    )
    return gaussian(relative_deviation, sigma)


def evaluate_training_type(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Reward the share of exercises matching the preferred training type."""
    preferred = context.preferred_training_type_id
    if preferred is None or not individual.selections:
        return 1.0
    return time_weighted_score(
        individual,
        lambda selection: float(preferred in selection.candidate.training_type_ids),
    )


def evaluate_equipment_usage(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Reward the share of available equipment used in the segment."""
    available_equipment = set(context.available_equipment_ids)
    if not available_equipment:
        return 1.0
    used_equipment: set[UUID] = set()
    for selection in individual.selections:
        used_equipment.update(selection.candidate.equipment_ids)
    return len(used_equipment & available_equipment) / len(available_equipment)


def evaluate_age_coverage(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Reward exercises that both cover and fit the group's age band."""
    group_years = context.group_max_age - context.group_min_age + 1

    def score_selection(selection: PlanExerciseSelection) -> float:
        candidate = selection.candidate
        overlap_years = max(
            0,
            min(candidate.max_age, context.group_max_age)
            - max(candidate.min_age, context.group_min_age)
            + 1,
        )
        exercise_years = candidate.max_age - candidate.min_age + 1
        coverage = overlap_years / group_years
        specificity = overlap_years / exercise_years if exercise_years else 0.0
        return coverage * specificity

    return time_weighted_score(individual, score_selection)


def evaluate_physical_difficulty(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Keep physical difficulty near its demand in every time window."""
    return _evaluate_windowed_difficulty(
        individual,
        lambda candidate: candidate.physical_difficulty,
        context.fitness_parameters.physical_difficulty_demand,
        context.fitness_parameters.difficulty_sigma,
        context.fitness_parameters.window_time_size,
    )


def evaluate_technical_difficulty(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Keep technical difficulty near its demand in every time window."""
    return _evaluate_windowed_difficulty(
        individual,
        lambda candidate: candidate.technical_difficulty,
        context.fitness_parameters.technical_difficulty_demand,
        context.fitness_parameters.difficulty_sigma,
        context.fitness_parameters.window_time_size,
    )


def evaluate_body_balance(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Blend local body-part balance with segment intensity near demand."""
    segment_means = time_weighted_means(individual, _body_loads)
    if segment_means is None:
        return 0.0

    params = context.fitness_parameters
    window_balance = windowed_score(
        individual,
        _body_loads,
        lambda means: _body_part_gap_score(means, params.body_load_sigma),
        params.window_time_size,
    )
    segment_demand = (
        sum(
            gaussian(mean - demand, params.body_load_sigma)
            for mean, demand in zip(
                segment_means,
                (
                    params.body_upper_demand,
                    params.body_lower_demand,
                    params.body_core_demand,
                ),
                strict=True,
            )
        )
        / 3
    )
    return (window_balance + segment_demand) / 2


def evaluate_recent_usage(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    """Reward exercises that were not used in the group's most recent plans."""
    return time_weighted_score(
        individual,
        lambda selection: (
            selection.candidate.recent_usage_distance / RECENT_USAGE_MAX_DISTANCE
        ),
    )


FITNESS_CRITERIA: tuple[tuple[FitnessCriterion, float], ...] = (
    (evaluate_duration_time, DURATION_WEIGHT),
    (evaluate_physical_difficulty, PHYSICAL_DIFFICULTY_WEIGHT),
    (evaluate_technical_difficulty, TECHNICAL_DIFFICULTY_WEIGHT),
    (evaluate_body_balance, BODY_BALANCE_WEIGHT),
    (evaluate_age_coverage, AGE_COVERAGE_WEIGHT),
    (evaluate_training_type, TRAINING_TYPE_WEIGHT),
    (evaluate_equipment_usage, EQUIPMENT_USAGE_WEIGHT),
    (evaluate_recent_usage, RECENT_USAGE_WEIGHT),
)


def evaluate(context: GenerationContext, individual: PlanIndividual) -> float:
    """Combine all criteria into one weighted fitness score in [0, 1]."""
    total_weight = sum(weight for _, weight in FITNESS_CRITERIA)
    weighted_scores = sum(
        weight * criterion(context, individual)
        for criterion, weight in FITNESS_CRITERIA
    )
    return weighted_scores / total_weight


def _relative_duration_deviation(
    context: GenerationContext, individual: PlanIndividual
) -> float:
    target = context.segment_duration_minutes
    total = sum(item.allocated_duration_minutes for item in individual.selections)
    return (total - target) / target


def _evaluate_windowed_difficulty(
    individual: PlanIndividual,
    difficulty: Callable[[PlanExerciseCandidate], int],
    demand: float,
    sigma: float,
    window_size: int,
) -> float:
    return windowed_score(
        individual,
        lambda candidate: (difficulty(candidate),),
        lambda means: gaussian(means[0] - demand, sigma),
        window_size,
    )


def _body_loads(candidate: PlanExerciseCandidate) -> tuple[int, ...]:
    return (candidate.upper_body_load, candidate.lower_body_load, candidate.core_load)


def _body_part_gap_score(means: tuple[float, ...], sigma: float = 1.0) -> float:
    """Score the gap between the most and least loaded body parts."""
    return gaussian(max(means) - min(means), sigma)
