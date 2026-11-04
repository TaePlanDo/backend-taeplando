"""Coverage for the checked-in source exercise catalog."""

from app.db.exercise_catalog import equipment_names, load_exercise_catalog
from app.models.enums import EquipmentRequirementMode


def test_catalog_contains_all_source_exercises_and_normalized_equipment() -> None:
    """Keep the complete source catalog and its equipment rules stable."""

    exercises = load_exercise_catalog()

    assert len(exercises) == 318
    assert equipment_names(exercises) == (
        "Balony",
        "Drabinka koordynacyjna",
        "Gumy oporowe",
        "Kaski",
        "Materace",
        "Obręcze",
        "Packi",
        "Pałki",
        "Piłeczki",
        "Piłki",
        "Poduchy",
        "Płotki",
        "Woreczki",
        "Znaczniki",
    )

    alternative_equipment = next(
        exercise
        for exercise in exercises
        if exercise.equipment_requirement_mode == EquipmentRequirementMode.ANY
    )
    assert alternative_equipment.equipment_names == ("Packi", "Poduchy")


def test_catalog_retains_the_incomplete_source_record() -> None:
    """Use the source record even when its optional catalog columns are blank."""

    incomplete = next(
        exercise for exercise in load_exercise_catalog() if exercise.source_id == 159
    )

    assert incomplete.name == "Ubieranie sprzętu"
    assert incomplete.max_participants == incomplete.min_participants == 2
    assert incomplete.equipment_names == ()
    assert incomplete.training_type_names == ()
    assert incomplete.segment_codes == ()
