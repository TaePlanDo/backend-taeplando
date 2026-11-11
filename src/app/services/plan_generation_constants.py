"""Tunable genetic-algorithm knobs for training-plan generation."""

INITIAL_POPULATION_SIZE = 50
MAX_GENERATIONS = 100
CXPB = 0.7
MUTPB = 0.35
TOURNAMENT_K = 4
MUTATION_DURATION_DELTA = 5

# Distances 1..N-1 come from the group's newest plans; N means unused.
RECENT_USAGE_MAX_DISTANCE = 4
RECENT_USAGE_PLAN_COUNT = RECENT_USAGE_MAX_DISTANCE - 1
