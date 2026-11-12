"""Job-scoped hall of fame for timeout salvage across parallel segments."""

from __future__ import annotations

import threading

from app.services.plan_generation_domain import PlanIndividual


class BestSoFar:
    """Thread-safe per-segment hall of fame for timeout salvage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._required_positions: tuple[int, ...] = ()
        self._by_position: dict[int, PlanIndividual] = {}

    def set_required_positions(self, positions: tuple[int, ...]) -> None:
        with self._lock:
            self._required_positions = positions

    def publish(self, position: int, individual: PlanIndividual) -> None:
        with self._lock:
            self._by_position[position] = individual

    def snapshot(self) -> PlanIndividual | None:
        with self._lock:
            if not self._required_positions:
                return None
            if any(
                position not in self._by_position
                for position in self._required_positions
            ):
                return None
            selections = tuple(
                sorted(
                    (
                        selection
                        for position in self._required_positions
                        for selection in self._by_position[position].selections
                    ),
                    key=lambda item: item.schema_position,
                )
            )
            if not selections:
                return None
            return PlanIndividual(selections=selections)
