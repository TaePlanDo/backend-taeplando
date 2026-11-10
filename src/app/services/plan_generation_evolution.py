"""DEAP-backed evolution for one training-plan segment."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from random import Random
from typing import Any

from deap import base, creator, tools

from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_constants import (
    CXPB,
    MAX_GENERATIONS,
    MUTATION_DURATION_DELTA,
    MUTPB,
    TOURNAMENT_K,
)
from app.services.plan_generation_domain import (
    GenerationContext,
    InitialPopulation,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import NoValidPlanError

logger = logging.getLogger(__name__)

INVALID_FITNESS = -1.0

if not hasattr(creator, "FitnessMax"):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if not hasattr(creator, "PlanGeneIndividual"):
    creator.create(
        "PlanGeneIndividual",
        list,
        fitness=creator.FitnessMax,
        context_seed=0,
    )


def temporary_fitness(
    individual: Any, *, context: GenerationContext
) -> tuple[float,]:
    """Placeholder score until SCRUM-237 supplies the real fitness function."""
    # TODO(SCRUM-237): replace this function; use context for duration/prefs grading
    _ = context
    seed = int(getattr(individual, "context_seed", 0)) ^ _hash_genes(individual)
    return (Random(seed).uniform(0, 100),)


def is_structurally_valid(
    context: GenerationContext, individual: PlanIndividual
) -> bool:
    """Hard GA-side checks; exact segment duration is a soft fitness concern."""
    if not individual.selections:
        return False
    candidate_ids = {
        candidate.trainer_exercise_id for candidate in context.candidates
    }
    for selection in individual.selections:
        if selection.schema_position != context.segment.position:
            return False
        if selection.allocated_duration_minutes < 1:
            return False
        if selection.candidate.trainer_exercise_id not in candidate_ids:
            return False
    return True


def evolve(
    context: GenerationContext,
    population: InitialPopulation,
    *,
    best: BestSoFar,
) -> PlanIndividual:
    """Run a seeded eaSimple-style GA for one segment and return the best valid plan.

    Stock ``algorithms.eaSimple`` / ``varAnd`` use the process-global ``random``
    module, which is unsafe across parallel segment threads. This loop mirrors
    eaSimple (select → varAnd → evaluate → replace) with a per-run ``Random``.
    """
    position = context.segment.position
    if not population.individuals:
        logger.info("segment %s: evolve rejected empty population", position)
        raise NoValidPlanError()

    rng = Random(context.random_seed)
    toolbox = _toolbox(context, rng)
    deap_population = [
        to_deap(individual, context.random_seed) for individual in population.individuals
    ]
    hall_of_fame = tools.HallOfFame(1)
    stats = tools.Statistics(lambda individual: individual.fitness.values[0])
    stats.register("avg", lambda values: sum(values) / len(values))
    stats.register("max", max)
    logbook = tools.Logbook()
    logbook.header = ["gen", "nevals", "avg", "max"]

    logger.info(
        "segment %s: evolve start pop=%d max_generations=%d cxpb=%.2f mutpb=%.2f",
        position,
        len(deap_population),
        MAX_GENERATIONS,
        CXPB,
        MUTPB,
    )

    nevals = _assign_fitness(deap_population, toolbox)
    hall_of_fame.update(deap_population)
    _publish_hall_of_fame(context, hall_of_fame, best)
    _record(logbook, stats, deap_population, gen=0, nevals=nevals)

    completed_generations = 0
    stopped_for_deadline = False
    for generation in range(1, MAX_GENERATIONS + 1):
        if datetime.now(UTC) >= context.deadline_at:
            stopped_for_deadline = True
            logger.info(
                "segment %s: stopping before generation %d (deadline reached)",
                position,
                generation,
            )
            break

        offspring = toolbox.select(deap_population, len(deap_population))
        offspring = _var_and(offspring, toolbox, CXPB, MUTPB, rng)
        nevals = _assign_fitness(offspring, toolbox)
        hall_of_fame.update(offspring)
        _publish_hall_of_fame(context, hall_of_fame, best)
        deap_population[:] = offspring
        completed_generations = generation
        _record(logbook, stats, deap_population, gen=generation, nevals=nevals)

    plan = _best_valid_plan(hall_of_fame)
    if plan is None:
        logger.info(
            "segment %s: evolve finished with no valid individual after %d generations",
            position,
            completed_generations,
        )
        raise NoValidPlanError()

    logger.info(
        "segment %s: evolve done generations=%d%s best_score=%.2f",
        position,
        completed_generations,
        " (deadline)" if stopped_for_deadline else "",
        float(hall_of_fame[0].fitness.values[0]),
    )
    return plan


def to_deap(individual: PlanIndividual, context_seed: int) -> Any:
    """Adapt a domain individual into a DEAP list chromosome."""
    gene_individual = creator.PlanGeneIndividual(individual.selections)
    gene_individual.context_seed = context_seed
    return gene_individual


def from_deap(individual: Any) -> PlanIndividual:
    """Adapt a DEAP chromosome back into the domain plan type."""
    return PlanIndividual(selections=tuple(individual))


def _toolbox(context: GenerationContext, random: Random) -> base.Toolbox:
    toolbox = base.Toolbox()
    toolbox.register("evaluate", _evaluate, context=context)
    toolbox.register("mate", _crossover, random=random)
    toolbox.register(
        "mutate",
        _mutate,
        candidates=context.candidates,
        random=random,
    )
    toolbox.register(
        "select",
        _tournament_select,
        tournsize=TOURNAMENT_K,
        random=random,
    )
    toolbox.register("clone", _clone)
    return toolbox


def _evaluate(individual: Any, *, context: GenerationContext) -> tuple[float,]:
    """Single validity gate: invalid chromosomes get a sentinel score."""
    if not is_structurally_valid(context, from_deap(individual)):
        return (INVALID_FITNESS,)
    return temporary_fitness(individual, context=context)


def _assign_fitness(individuals: list[Any], toolbox: base.Toolbox) -> int:
    invalid = [individual for individual in individuals if not individual.fitness.valid]
    for individual, fitness in zip(
        invalid, toolbox.map(toolbox.evaluate, invalid), strict=True
    ):
        individual.fitness.values = fitness
    return len(invalid)


def _var_and(
    population: list[Any],
    toolbox: base.Toolbox,
    cxpb: float,
    mutpb: float,
    random: Random,
) -> list[Any]:
    """Seeded clone of ``deap.algorithms.varAnd`` (avoids process-global RNG)."""
    offspring = [toolbox.clone(individual) for individual in population]
    for index in range(1, len(offspring), 2):
        if random.random() < cxpb:
            offspring[index - 1], offspring[index] = toolbox.mate(
                offspring[index - 1], offspring[index]
            )
            del offspring[index - 1].fitness.values, offspring[index].fitness.values
    for index, individual in enumerate(offspring):
        if random.random() < mutpb:
            (offspring[index],) = toolbox.mutate(individual)
            del offspring[index].fitness.values
    return offspring


def _record(
    logbook: tools.Logbook,
    stats: tools.Statistics,
    population: list[Any],
    *,
    gen: int,
    nevals: int,
) -> None:
    record = stats.compile(population)
    logbook.record(gen=gen, nevals=nevals, **record)
    logger.debug("evolution gen=%s", logbook.stream)


def _publish_hall_of_fame(
    context: GenerationContext,
    hall_of_fame: tools.HallOfFame,
    best: BestSoFar,
) -> None:
    plan = _best_valid_plan(hall_of_fame)
    if plan is None:
        return
    best.publish(context.segment.position, plan)
    logger.debug(
        "segment %s: published best score=%.2f genes=%d total_minutes=%d",
        context.segment.position,
        float(hall_of_fame[0].fitness.values[0]),
        len(plan.selections),
        sum(selection.allocated_duration_minutes for selection in plan.selections),
    )


def _best_valid_plan(hall_of_fame: tools.HallOfFame) -> PlanIndividual | None:
    """Return the HoF champion when evaluate already marked it structurally valid."""
    if not hall_of_fame:
        return None
    if float(hall_of_fame[0].fitness.values[0]) <= INVALID_FITNESS:
        return None
    return from_deap(hall_of_fame[0])


def _tournament_select(
    individuals: list[Any],
    k: int,
    *,
    tournsize: int,
    random: Random,
) -> list[Any]:
    """Seeded tournament selection that does not touch the process-global RNG."""
    selected: list[Any] = []
    for _ in range(k):
        if len(individuals) <= tournsize:
            aspirants = list(individuals)
        else:
            aspirants = random.sample(individuals, tournsize)
        selected.append(max(aspirants, key=lambda item: item.fitness.values))
    return selected


def _clone(individual: Any) -> Any:
    clone = creator.PlanGeneIndividual(list(individual))
    clone.context_seed = getattr(individual, "context_seed", 0)
    clone.fitness = creator.FitnessMax()
    if individual.fitness.valid:
        clone.fitness.values = individual.fitness.values
    return clone


def _crossover(first: Any, second: Any, *, random: Random) -> tuple[Any, Any]:
    """One-point crossover that preserves gene durations as-is."""
    if min(len(first), len(second)) < 2:
        return first, second
    point = random.randint(1, min(len(first), len(second)) - 1)
    first[point:], second[point:] = second[point:], first[point:]
    return first, second


def _mutate(
    individual: Any,
    *,
    candidates: tuple[PlanExerciseCandidate, ...],
    random: Random,
) -> tuple[Any]:
    """Mutate duration, replace a candidate, or shuffle gene order."""
    if not individual:
        return (individual,)

    mode = random.randint(0, 2)
    index = random.randrange(len(individual))
    selection: PlanExerciseSelection = individual[index]

    if mode == 0:
        delta = random.randint(1, MUTATION_DURATION_DELTA) * random.choice((-1, 1))
        individual[index] = replace(
            selection,
            allocated_duration_minutes=max(
                1, selection.allocated_duration_minutes + delta
            ),
        )
    elif mode == 1 and candidates:
        candidate = random.choice(candidates)
        individual[index] = replace(
            selection,
            candidate=candidate,
            allocated_duration_minutes=candidate.default_duration_minutes,
        )
    else:
        random.shuffle(individual)
    return (individual,)


def _hash_genes(individual: Any) -> int:
    digest = 0
    for selection in individual:
        digest ^= hash(
            (
                selection.candidate.trainer_exercise_id.int,
                selection.allocated_duration_minutes,
                selection.schema_position,
            )
        )
    return digest
