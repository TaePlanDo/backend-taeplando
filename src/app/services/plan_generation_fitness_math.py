"""Shared math helpers for plan-generation fitness criteria."""

import math
from collections.abc import Callable

from app.services.plan_generation_domain import (
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)

WINDOW_TIME_SIZE = 5


def gaussian(deviation: float, sigma: float) -> float:
    """Map a deviation to (0, 1], where zero deviation scores 1."""
    return math.exp(-(deviation**2) / (2 * sigma**2))


def time_weighted_score(
    individual: PlanIndividual,
    score: Callable[[PlanExerciseSelection], float],
) -> float:
    """Average a per-selection score weighted by allocated minutes."""
    total_minutes = 0
    weighted = 0.0
    for selection in individual.selections:
        minutes = selection.allocated_duration_minutes
        weighted += minutes * score(selection)
        total_minutes += minutes
    if not total_minutes:
        return 0.0
    return weighted / total_minutes


def time_weighted_means(
    individual: PlanIndividual,
    values: Callable[[PlanExerciseCandidate], tuple[int, ...]],
) -> tuple[float, ...] | None:
    """Return minute-weighted means of candidate values, or None if empty."""
    total_minutes = 0
    load: tuple[int, ...] = ()
    for selection in individual.selections:
        minutes = selection.allocated_duration_minutes
        load = _add_load(load, values(selection.candidate), minutes)
        total_minutes += minutes
    if not total_minutes:
        return None
    return _means(load, total_minutes)


def windowed_score(
    individual: PlanIndividual,
    values: Callable[[PlanExerciseCandidate], tuple[int, ...]],
    window_score: Callable[[tuple[float, ...]], float],
) -> float:
    """Average window scores, weighting each window by its minutes."""
    total_minutes = 0
    weighted_scores = 0.0
    open_minutes = 0
    open_load: tuple[int, ...] = ()
    for selection in individual.selections:
        value = values(selection.candidate)
        remaining = selection.allocated_duration_minutes
        total_minutes += remaining

        if open_minutes:
            taken = min(remaining, WINDOW_TIME_SIZE - open_minutes)
            open_minutes += taken
            open_load = _add_load(open_load, value, taken)
            remaining -= taken
            if open_minutes == WINDOW_TIME_SIZE:
                weighted_scores += open_minutes * window_score(
                    _means(open_load, open_minutes)
                )
                open_minutes, open_load = 0, ()

        full_windows, remaining = divmod(remaining, WINDOW_TIME_SIZE)
        if full_windows:
            weighted_scores += (
                full_windows * WINDOW_TIME_SIZE * window_score(_means(value, 1))
            )
        if remaining:
            open_minutes += remaining
            open_load = _add_load(open_load, value, remaining)

    if open_minutes:
        weighted_scores += open_minutes * window_score(_means(open_load, open_minutes))
    if not total_minutes:
        return 0.0
    return weighted_scores / total_minutes


def _means(load: tuple[int, ...], minutes: int) -> tuple[float, ...]:
    """Convert accumulated load totals into per-minute means."""
    return tuple(total / minutes for total in load)


def _add_load(
    load: tuple[int, ...], value: tuple[int, ...], minutes: int
) -> tuple[int, ...]:
    """Add minutes of one exercise's values to an accumulated load."""
    if not load:
        return tuple(item * minutes for item in value)
    return tuple(
        total + item * minutes for total, item in zip(load, value, strict=True)
    )
