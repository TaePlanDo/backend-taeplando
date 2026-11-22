"""Tunable weights, demands, and sigmas for plan-generation fitness."""

from dataclasses import dataclass

# Weights for each fitness criterion
DURATION_WEIGHT = 3.0
PHYSICAL_DIFFICULTY_WEIGHT = 2.0
TECHNICAL_DIFFICULTY_WEIGHT = 1.5
BODY_BALANCE_WEIGHT = 2.0
AGE_COVERAGE_WEIGHT = 1.5
TRAINING_TYPE_WEIGHT = 1.0
EQUIPMENT_USAGE_WEIGHT = 1.5
RECENT_USAGE_WEIGHT = 3.0

# Standard deviations for each fitness criterion
DURATION_OVER_SIGMA_RATIO = 0.05
DURATION_UNDER_SIGMA_RATIO = 0.2
DIFFICULTY_SIGMA = 1.0
BODY_LOAD_SIGMA = 1.0

# Demands for each fitness criterion
PHYSICAL_DIFFICULTY_DEMAND = 2.5
TECHNICAL_DIFFICULTY_DEMAND = 2.5
BODY_UPPER_DEMAND = 2.5
BODY_LOWER_DEMAND = 2.5
BODY_CORE_DEMAND = 2.5
BODY_LOAD_DEMANDS = (BODY_UPPER_DEMAND, BODY_LOWER_DEMAND, BODY_CORE_DEMAND)

# Window size for each fitness criterion (minutes)
WINDOW_TIME_SIZE = 5


@dataclass(frozen=True)
class FitnessParameters:
    duration_over_sigma_ratio: float = DURATION_OVER_SIGMA_RATIO
    duration_under_sigma_ratio: float = DURATION_UNDER_SIGMA_RATIO
    difficulty_sigma: float = DIFFICULTY_SIGMA
    body_load_sigma: float = BODY_LOAD_SIGMA
    physical_difficulty_demand: float = PHYSICAL_DIFFICULTY_DEMAND
    technical_difficulty_demand: float = TECHNICAL_DIFFICULTY_DEMAND
    body_upper_demand: float = BODY_UPPER_DEMAND
    body_lower_demand: float = BODY_LOWER_DEMAND
    body_core_demand: float = BODY_CORE_DEMAND
    window_time_size: int = WINDOW_TIME_SIZE
