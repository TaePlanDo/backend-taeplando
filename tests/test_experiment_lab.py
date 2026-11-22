"""Tests for experiment scenarios, repeatability and aggregation."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.experiments.catalog import Catalog
from app.experiments.lab import (
    GROUPS,
    Settings,
    Variant,
    prepare,
    representative,
    run_one,
    scenarios,
    shortlist,
    summarize,
)
from app.experiments.report import render_report
from app.services.plan_generation_constraints import duration_bounds
from app.services.plan_generation_domain import PlanExerciseSelection, PlanIndividual
from app.services.plan_generation_errors import InvalidGeneratedPlanError
from app.services.plan_generation_evolution import EvolutionConfig
from app.services.plan_generation_fitness import evaluate_physical_difficulty
from app.services.plan_generation_fitness_constants import FitnessParameters
from app.services.plan_generation_validation import validate_generated_plan
from test_plan_generation_evolution import _candidate, _context


def test_scenario_uses_middle_age_and_duration():
    items = list(scenarios())
    assert [
        (group.name, equipment, training_type, count)
        for group, equipment, training_type, count in items
    ] == [
        ("7-13", "pałki", "częsty", 15),
    ]
    assert [group.duration for group in GROUPS] == [45, 60, 75]
    assert all(sum(p for _, p in group.schema) == 100 for group in GROUPS)


def test_history_and_generation_repeat_for_same_seed():
    ids = [UUID(int=n) for n in range(1, 5)]
    candidates = tuple(
        replace(_candidate(str(identifier), duration=5), segment_ids=(1, 2, 3, 4))
        for identifier in ids
    )
    catalog = Catalog(candidates, {i: str(i) for i in ids}, {}, {}, UUID(int=99))
    settings = Settings(
        plans_per_scenario=1,
        history_exercises_per_plan=1,
        variants=[Variant(name="test", population_size=3, max_generations=1)],
    )
    first = prepare(catalog, GROUPS[1], "brak", "brak", 1, settings)
    assert first == prepare(catalog, GROUPS[1], "brak", "brak", 1, settings)
    available, preferred, pool, _ = first
    _, plan_a, _ = run_one(
        GROUPS[1], available, preferred, pool, 1, settings.variants[0], 99, 30
    )
    _, plan_b, _ = run_one(
        GROUPS[1], available, preferred, pool, 1, settings.variants[0], 99, 30
    )
    assert plan_a == plan_b


def test_aggregates_failures_and_successes_without_hiding_them():
    result = summarize(
        [{"error": "missing"}, {"metrics": {"exercises": 5, "deadline_reached": False}}]
    )
    assert result["proby"] == 2
    assert result["poprawne"] == result["bledy"] == 1
    assert result["przyczyny_bledow"] == {"missing": 1}
    assert result["exercises"]["srednia"] == 5


def test_invalid_probabilities_rejected():
    with pytest.raises(ValueError):
        EvolutionConfig(mutation_probability=1.1)


def test_duration_limit_is_shared_by_mutation_and_final_validation():
    from random import Random

    from app.services.plan_generation_evolution import _mutate, is_structurally_valid

    candidate = _candidate(str(UUID(int=12)), duration=10)
    context = _context(candidate)
    for seed in range(100):
        genes = [PlanExerciseSelection(1, candidate, 10)]
        _mutate(
            genes,
            candidates=(candidate,),
            schema_position=1,
            random=Random(seed),
            duration_delta=10,
            duration_deviation_percent=50,
            mode_weights=(1, 0, 0, 0),
        )
        if abs(genes[0].allocated_duration_minutes - 10) > 2:
            break
    plan = PlanIndividual(tuple(genes))
    assert abs(genes[0].allocated_duration_minutes - 10) > 2
    assert is_structurally_valid(context, plan, 50)
    assert not is_structurally_valid(context, plan, 20)
    args = dict(
        segment_by_position={1: 1},
        group_min_age=7,
        group_max_age=14,
        participant_count=12,
        available_equipment_ids=(),
        plan=plan,
    )
    validate_generated_plan(**args, duration_deviation_percent=50)
    with pytest.raises(InvalidGeneratedPlanError):
        validate_generated_plan(**args)
    assert duration_bounds(10, 0) == (10, 10)
    assert duration_bounds(1, 100) == (1, 1)
    assert all(
        duration_bounds(n) == (n, n)
        if n == 1
        else duration_bounds(n)
        == (max(1, n - max(1, (n + 2) // 5)), n + max(1, (n + 2) // 5))
        for n in range(1, 100)
    )


def test_fitness_configuration_changes_actual_criterion():
    candidate = _candidate(str(UUID(int=13)))
    context = _context(candidate)
    plan = PlanIndividual((PlanExerciseSelection(1, candidate, 10),))
    changed = replace(
        context, fitness_parameters=FitnessParameters(physical_difficulty_demand=3)
    )
    assert evaluate_physical_difficulty(changed, plan) > evaluate_physical_difficulty(
        context, plan
    )
    with pytest.raises(ValueError):
        Variant(name="bad", fitness={"difficulty_sigma": 0})
    with pytest.raises(ValueError):
        Variant(name="bad", mutation_mode_weights=(0, 0, 0, 0))


def test_shortlist_prefers_fewer_failures_then_keeps_tradeoffs():
    def result(name, failures, duration, repeats):
        return {
            "konfiguracja": {"name": name},
            "wyniki": {
                "poprawne": 5,
                "bledy": failures,
                "duration_deviation_minutes": {"srednia": duration},
                "repeat_1": {"srednia": repeats},
            },
        }

    results = [
        result("a", 0, 2, 0.3),
        result("b", 0, 3, 0.2),
        result("dominated", 0, 4, 0.4),
        result("failures", 1, 1, 0.1),
    ]
    assert shortlist(results) == ["a", "b"]


def test_representative_uses_all_fitness_scores_and_ignores_failures():
    from app.experiments.lab import FITNESS_KEYS

    def row(value):
        return {"metrics": dict.fromkeys(FITNESS_KEYS, value), "example": value}

    rows = [row(0), {"error": "failed"}, row(0.4), row(1)]
    assert representative(rows)["example"] == 0.4
    assert representative([{"error": "failed"}]) is None


def test_readable_report_contains_plan_fitness_and_failed_scenario():
    data = {
        "data": "today",
        "kandydaci_do_oceny": ["test"],
        "wyniki": [
            {
                "konfiguracja": {"name": "test"},
                "wyniki": {
                    "poprawne": 1,
                    "proby": 2,
                    "bledy": 1,
                    "przekroczony_limit_czasu": 0,
                    "repeat_1": {"srednia": 0.25},
                },
                "scenariusze": [
                    {
                        "scenariusz": "A",
                        "przykladowy_plan": {
                            "cwiczenia": [
                                {
                                    "segment": "Gra",
                                    "nazwa": "Skok",
                                    "minuty": 5,
                                    "ostatnio": 4,
                                }
                            ],
                            "fitness": {"duration_time": 0.75},
                        },
                    },
                    {"scenariusz": "B", "przykladowy_plan": None},
                ],
            }
        ],
    }
    report = render_report(data)
    assert "25.00%" in report
    assert "Skok" in report and "Dopasowanie czasu | 0.7500" in report
    assert "Brak poprawnego planu" in report
