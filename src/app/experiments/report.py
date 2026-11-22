"""Human-readable summary of an experiment session."""

from typing import Any

FITNESS_LABELS = {
    "duration_time": "Dopasowanie czasu",
    "physical_difficulty": "Trudność fizyczna",
    "technical_difficulty": "Trudność techniczna",
    "body_balance": "Równowaga obciążenia ciała",
    "age_coverage": "Dopasowanie wieku",
    "training_type": "Typ treningu",
    "equipment_usage": "Sprzęt",
    "recent_usage": "Niedawne użycie ćwiczeń",
}


def cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def metric(w: dict[str, Any], key: str, multiplier: int = 1, suffix: str = "") -> str:
    return f"{w[key]['srednia'] * multiplier:.2f}{suffix}" if key in w else "—"


def render_report(data: dict[str, Any]) -> str:
    candidates = ", ".join(map(cell, data["kandydaci_do_oceny"])) or "brak"
    lines = [
        "# Wyniki eksperymentu",
        "",
        f"Data: {data['data']}  ",
        f"Kandydaci do oceny: {candidates}",
        "",
        "## Porównanie konfiguracji",
        "",
        "| Konfiguracja | Poprawne / próby | Błędy | Limit czasu "
        "| Odchylenie czasu (min) | Powtórki | Generowanie (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in data["wyniki"]:
        w = result["wyniki"]

        lines.append(
            f"| {cell(result['konfiguracja']['name'])} "
            f"| {w['poprawne']} / {w['proby']} "
            f"| {w['bledy']} | {w['przekroczony_limit_czasu']} "
            f"| {metric(w, 'duration_deviation_minutes')} "
            f"| {metric(w, 'repeat_1', 100, '%')} "
            f"| {metric(w, 'duration_seconds')} |"
        )
    lines += [
        "",
        "W tabeli podano średnie dla poprawnych planów. Powtórki oznaczają udział "
        "wystąpień ćwiczeń z ostatniego treningu w syntetycznej historii.",
        "",
        "Kandydaci mają najmniej błędów; spośród nich pominięto konfiguracje "
        "zdominowane jednocześnie pod względem średniego odchylenia czasu i powtórek. "
        "To wskazówka do oceny, a nie dowód statystyczny.",
        "",
        "## Przykładowe plany",
        "",
        "Dla każdej konfiguracji i scenariusza wybrano poprawny plan o najmniejszej "
        "sumie kwadratów różnic między jego ośmioma ocenami fitness a średnimi "
        "ocenami w tym scenariuszu. Wszystkie składowe mają równą wagę. "
        "Plan bliski średniej nie musi być najlepszy.",
    ]
    for result in data["wyniki"]:
        lines += ["", f"### {cell(result['konfiguracja']['name'])}"]
        for scenario in result["scenariusze"]:
            lines += ["", f"#### {cell(scenario['scenariusz'])}", ""]
            plan = scenario["przykladowy_plan"]
            if plan is None:
                lines.append("Brak poprawnego planu w tym scenariuszu.")
                continue
            lines += [
                "| Segment | Ćwiczenie | Minuty | Ostatnio |",
                "|---|---|---:|---:|",
            ]
            for exercise in plan["cwiczenia"]:
                lines.append(
                    f"| {cell(exercise['segment'])} | {cell(exercise['nazwa'])} "
                    f"| {exercise['minuty']} | {exercise['ostatnio']} |"
                )
            lines += [
                "",
                "Oceny fitness tego planu (0–1):",
                "",
                "| Składowa | Ocena |",
                "|---|---:|",
            ]
            for key, value in plan["fitness"].items():
                lines.append(f"| {FITNESS_LABELS.get(key, key)} | {value:.4f} |")
    lines += [
        "",
        "Oceny fitness są średnimi segmentów ważonymi czasem. Wartość 1 dla "
        "typu treningu lub sprzętu może oznaczać brak preferencji albo sprzętu, "
        "a nie faktyczne dopasowanie. Ostatnio 4 oznacza brak ćwiczenia w trzech "
        "ostatnich planach syntetycznej historii.",
        "",
    ]
    return "\n".join(lines)
