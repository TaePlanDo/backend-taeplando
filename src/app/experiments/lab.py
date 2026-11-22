"""Run paired experiments using the production generator and synthetic contexts."""

from __future__ import annotations

import hashlib
import math
import statistics
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.experiments.catalog import Catalog
from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_constraints import satisfies_equipment_requirement
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
    PlanIndividual,
)
from app.services.plan_generation_evolution import EvolutionConfig, evolve
from app.services.plan_generation_fitness import FITNESS_CRITERIA
from app.services.plan_generation_fitness_constants import FitnessParameters
from app.services.plan_generation_population_service import (
    allocate_segment_durations,
    build_initial_population,
)
from app.services.plan_generation_validation import validate_generated_plan


class FitnessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    duration_over_sigma_ratio: float = Field(default=0.05, gt=0)
    duration_under_sigma_ratio: float = Field(default=0.2, gt=0)
    difficulty_sigma: float = Field(default=1.0, gt=0)
    body_load_sigma: float = Field(default=1.0, gt=0)
    physical_difficulty_demand: float = Field(default=2.5, ge=1, le=5)
    technical_difficulty_demand: float = Field(default=2.5, ge=1, le=5)
    body_upper_demand: float = Field(default=2.5, ge=1, le=5)
    body_lower_demand: float = Field(default=2.5, ge=1, le=5)
    body_core_demand: float = Field(default=2.5, ge=1, le=5)
    window_time_size: int = Field(default=5, ge=1)


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    population_size: int = Field(default=50, ge=1, le=1000)
    max_generations: int = Field(default=100, ge=0, le=10000)
    crossover_probability: float = Field(default=0.7, ge=0, le=1)
    mutation_probability: float = Field(default=0.35, ge=0, le=1)
    tournament_size: int = Field(default=4, ge=1)
    mutation_duration_delta: int = Field(default=5, ge=1)
    duration_deviation_percent: int = Field(default=20, ge=0, le=100)
    fitness: FitnessSettings = Field(default_factory=FitnessSettings)
    mutation_mode_weights: tuple[float, float, float, float] = (1, 1, 1, 1)

    @model_validator(mode="after")
    def valid_mutation_mode_weights(self) -> Variant:
        if (
            any(not math.isfinite(w) or w < 0 for w in self.mutation_mode_weights)
            or not sum(self.mutation_mode_weights) > 0
        ):
            raise ValueError(
                "Wagi rodzajów mutacji muszą być nieujemne i nie wszystkie zerowe"
            )
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trainer_id: UUID | None = None
    plans_per_scenario: int = Field(default=30, ge=1)
    seed: int = 42
    timeout_seconds: float = Field(default=30, gt=0)
    history_exercises_per_plan: int = Field(default=10, ge=1)
    output_dir: str = "experiments/results"
    variants: list[Variant] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_names(self) -> Settings:
        if len({v.name for v in self.variants}) != len(self.variants):
            raise ValueError("Nazwy konfiguracji muszą być unikalne")
        return self


@dataclass(frozen=True)
class Group:
    name: str
    age_min: int
    age_max: int
    duration: int
    # fixed segment codes: warmup, stretching, main, game
    schema: tuple[tuple[int, int], ...]


GROUPS = (
    Group("3-6", 3, 6, 45, ((1, 20), (4, 10), (3, 20), (2, 50))),
    Group("7-13", 7, 13, 60, ((1, 20), (4, 10), (3, 40), (2, 30))),
    Group("14-18", 14, 18, 75, ((1, 10), (4, 10), (3, 80))),
)
EQUIPMENT = {
    "brak": (),
    "pałki": ("Pałki",),
    "częsty": ("Packi", "Poduchy", "Pałki", "Znaczniki", "Drabinka koordynacyjna"),
    "rzadki": ("Piłki", "Obręcze", "Balony", "Płotki", "Kaski"),
}
TYPES = {"brak": None, "częsty": "Technika", "rzadki": "Siła grzbietu"}
SEGMENTS = {1: "Rozgrzewka", 4: "Rozciąganie", 3: "Ćwiczenia", 2: "Zabawa"}
FITNESS_KEYS = tuple(c.__name__.removeprefix("evaluate_") for c, _ in FITNESS_CRITERIA)


def scenarios() -> Iterator[tuple[Group, str, str, int]]:
    yield GROUPS[1], "pałki", "częsty", 15


def seed_for(*parts: object) -> int:
    return int.from_bytes(
        hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big"
    )


def prepare(
    catalog: Catalog,
    group: Group,
    equipment: str,
    training_type: str,
    participants: int,
    settings: Settings,
) -> tuple[tuple[UUID, ...], UUID | None, list[PlanExerciseCandidate], dict[UUID, int]]:
    available = tuple(catalog.equipment[name] for name in EQUIPMENT[equipment])
    preferred_name = TYPES[training_type]
    preferred = catalog.types[preferred_name] if preferred_name else None
    candidates = [
        c
        for c in catalog.candidates
        if c.max_age >= group.age_min
        and c.min_age <= group.age_max
        and c.min_participants <= participants <= c.max_participants
        and satisfies_equipment_requirement(
            mode=c.equipment_requirement_mode,
            required_equipment_ids=c.equipment_ids,
            available_equipment_ids=available,
        )
        and any(segment in c.segment_ids for segment, _ in group.schema)
    ]
    # Synthetic history uses eligible exercises; most recent occurrence wins.
    rng = Random(
        seed_for(
            settings.seed, group.name, equipment, training_type, participants, "history"
        )
    )
    distances: dict[UUID, int] = {}
    for distance in range(1, 4):
        for candidate in rng.sample(
            candidates, min(settings.history_exercises_per_plan, len(candidates))
        ):
            distances.setdefault(candidate.trainer_exercise_id, distance)
    candidates = [
        replace(c, recent_usage_distance=distances.get(c.trainer_exercise_id, 4))
        for c in candidates
    ]
    return available, preferred, candidates, distances


def run_one(
    group: Group,
    available: tuple[UUID, ...],
    preferred: UUID | None,
    candidates: list[PlanExerciseCandidate],
    participants: int,
    variant: Variant,
    seed: int,
    timeout: float,
) -> tuple[dict[str, Any], PlanIndividual, tuple[GenerationSchemaItem, ...]]:
    started = time.perf_counter()
    deadline = datetime.now(UTC) + timedelta(seconds=timeout)
    schema = tuple(
        GenerationSchemaItem(i, segment, Decimal(percent))
        for i, (segment, percent) in enumerate(group.schema, 1)
    )
    durations = allocate_segment_durations(group.duration, schema)
    contexts = []
    for item in schema:
        eligible = tuple(
            c
            for c in candidates
            if item.segment_id in c.segment_ids and c.default_duration_minutes > 0
        )
        if not eligible:
            raise ValueError(f"Brak ćwiczeń dla segmentu {SEGMENTS[item.segment_id]}")
        contexts.append(
            GenerationContext(
                participants,
                available,
                preferred,
                uuid5(NAMESPACE_URL, group.name),
                group.name,
                group.age_min,
                group.age_max,
                group.duration,
                deadline,
                item,
                durations[item.position],
                eligible,
                seed_for(seed, item.position),
                FitnessParameters(**variant.fitness.model_dump()),
            )
        )
    config = EvolutionConfig(
        variant.max_generations,
        variant.crossover_probability,
        variant.mutation_probability,
        variant.tournament_size,
        variant.mutation_duration_delta,
        variant.duration_deviation_percent,
        variant.mutation_mode_weights,
    )

    def generate(context: GenerationContext) -> PlanIndividual:
        population = build_initial_population(
            context, population_size=variant.population_size
        )
        return evolve(context, population, best=BestSoFar(), config=config)

    with ThreadPoolExecutor(max_workers=len(contexts)) as executor:
        segments = list(executor.map(generate, contexts))
    plan = PlanIndividual(
        tuple(selection for segment in segments for selection in segment.selections)
    )
    validate_generated_plan(
        segment_by_position={x.position: x.segment_id for x in schema},
        group_min_age=group.age_min,
        group_max_age=group.age_max,
        participant_count=participants,
        available_equipment_ids=available,
        plan=plan,
        duration_deviation_percent=variant.duration_deviation_percent,
    )
    metrics = {}
    for criterion, _ in FITNESS_CRITERIA:
        metrics[criterion.__name__.removeprefix("evaluate_")] = (
            sum(
                criterion(c, p) * c.segment_duration_minutes
                for c, p in zip(contexts, segments, strict=True)
            )
            / group.duration
        )
    counts = [
        sum(s.candidate.recent_usage_distance == n for s in plan.selections)
        for n in range(1, 5)
    ]
    total = len(plan.selections)
    metrics.update(
        exercises=total,
        duration_deviation_minutes=abs(
            sum(x.allocated_duration_minutes for x in plan.selections) - group.duration
        ),
        repeat_1=counts[0] / total,
        repeat_2_3=(counts[1] + counts[2]) / total,
        repeat_4_plus=counts[3] / total,
        duration_seconds=time.perf_counter() - started,
        deadline_reached=datetime.now(UTC) >= deadline,
    )
    return metrics, plan, schema


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [r for r in rows if "metrics" in r]
    result = {
        "proby": len(rows),
        "poprawne": len(successful),
        "bledy": len(rows) - len(successful),
        "przekroczony_limit_czasu": sum(
            r["metrics"]["deadline_reached"] for r in successful
        ),
    }
    if successful:
        for key in successful[0]["metrics"]:
            if key == "deadline_reached":
                continue
            values = [r["metrics"][key] for r in successful]
            ordered = sorted(values)
            result[key] = {
                "srednia": round(statistics.mean(values), 4),
                "mediana": round(statistics.median(values), 4),
                "p90": round(ordered[math.ceil(0.9 * len(ordered)) - 1], 4),
            }
    failures: dict[str, int] = {}
    for row in rows:
        if "error" in row:
            failures[row["error"]] = failures.get(row["error"], 0) + 1
    if failures:
        result["przyczyny_bledow"] = failures
    return result


def shortlist(results: list[dict[str, Any]]) -> list[str]:
    """Show nondominated candidates after filtering for the fewest failures.

    This is a navigation aid, not a statistical test or trainer evaluation.
    """
    eligible = [r for r in results if r["wyniki"]["poprawne"]]
    if not eligible:
        return []
    fewest = min(r["wyniki"]["bledy"] for r in eligible)
    eligible = [r for r in eligible if r["wyniki"]["bledy"] == fewest]

    def values(result: dict[str, Any]) -> tuple[float, float]:
        metrics = result["wyniki"]
        return (
            metrics["duration_deviation_minutes"]["srednia"],
            metrics["repeat_1"]["srednia"],
        )

    selected = []
    for candidate in eligible:
        a = values(candidate)
        dominated = any(
            all(x <= y for x, y in zip(values(other), a, strict=True))
            and values(other) != a
            for other in eligible
            if other is not candidate
        )
        if not dominated:
            selected.append(candidate["konfiguracja"]["name"])
    return selected


def representative(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the successful plan closest to scenario means across fitness scores."""
    successful = [row for row in rows if "metrics" in row]
    if not successful:
        return None
    means = {
        key: statistics.mean(r["metrics"][key] for r in successful)
        for key in FITNESS_KEYS
    }
    return min(
        successful,
        key=lambda row: sum(
            (row["metrics"][key] - means[key]) ** 2 for key in FITNESS_KEYS
        ),
    )


def run_lab(catalog: Catalog, settings: Settings) -> list[dict[str, Any]]:
    results = []
    all_scenarios = list(scenarios())
    for variant in settings.variants:
        all_rows, details = [], []
        for group, equipment, training_type, participants in all_scenarios:
            label = (
                f"{group.name} / sprzęt: {equipment} / typ: {training_type} "
                f"/ uczestnicy: {participants}"
            )
            available, preferred, candidates, history = prepare(
                catalog, group, equipment, training_type, participants, settings
            )
            rows: list[dict[str, Any]] = []
            for index in range(settings.plans_per_scenario):
                try:
                    metrics, plan, schema = run_one(
                        group,
                        available,
                        preferred,
                        candidates,
                        participants,
                        variant,
                        seed_for(settings.seed, label, index),
                        settings.timeout_seconds,
                    )
                    segment_names = {x.position: SEGMENTS[x.segment_id] for x in schema}
                    example = {
                        "scenariusz": label,
                        "cwiczenia": [
                            {
                                "segment": segment_names[s.schema_position],
                                "nazwa": catalog.names[s.candidate.trainer_exercise_id],
                                "minuty": s.allocated_duration_minutes,
                                "ostatnio": s.candidate.recent_usage_distance,
                            }
                            for s in plan.selections
                        ],
                    }
                    rows.append({"metrics": metrics, "example": example})
                except Exception as exc:
                    rows.append({"error": f"{type(exc).__name__}: {exc}"})
            all_rows.extend(rows)
            chosen = representative(rows)
            if chosen:
                chosen["example"]["fitness"] = {
                    key: round(chosen["metrics"][key], 4) for key in FITNESS_KEYS
                }
            details.append(
                {
                    "scenariusz": label,
                    "kandydaci": len(candidates),
                    "historia_unikalne_cwiczenia": len(history),
                    "wyniki": summarize(rows),
                    "przykladowy_plan": chosen["example"] if chosen else None,
                }
            )
            success = sum("metrics" in r for r in rows)
            print(f"{variant.name}: {label}: {success}/{len(rows)}", flush=True)
        results.append(
            {
                "konfiguracja": variant.model_dump(),
                "wyniki": summarize(all_rows),
                "scenariusze": details,
                "ocena_trenera": {
                    "akceptowalne": None,
                    "ocena_1_5": None,
                    "komentarz": "",
                },
            }
        )
    return results
