"""Shared planning-attribute values for exercise API tests."""

from app.models.enums import EquipmentRequirementMode


def private_planning_attributes() -> dict[str, EquipmentRequirementMode | int]:
    """Build distinct values owned by a trainer."""
    return {
        "equipment_requirement_mode": EquipmentRequirementMode.ANY,
        "physical_difficulty": 2,
        "technical_difficulty": 4,
        "upper_body_load": 3,
        "lower_body_load": 5,
        "core_load": 1,
    }


def global_planning_attributes() -> dict[str, EquipmentRequirementMode | int]:
    """Build distinct values carried by a published exercise version."""
    return {
        "equipment_requirement_mode": EquipmentRequirementMode.ALL,
        "physical_difficulty": 4,
        "technical_difficulty": 2,
        "upper_body_load": 5,
        "lower_body_load": 2,
        "core_load": 3,
    }
