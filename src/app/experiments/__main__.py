"""CLI entry point: python -m app.experiments run --config ..."""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.db.session import dispose_engine
from app.experiments.catalog import load_catalog
from app.experiments.lab import Settings, run_lab, shortlist
from app.experiments.report import render_report


def suggest(path: Path, name: str, step: float) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    matches = [r for r in data["wyniki"] if r["konfiguracja"]["name"] == name]
    if len(matches) != 1:
        raise ValueError("Nie znaleziono wybranej konfiguracji w raporcie")
    selected = matches[0]["konfiguracja"]
    probability = selected["mutation_probability"]
    variants = []
    for value in sorted(
        {
            round(max(0, min(1, probability + offset * step)), 4)
            for offset in (-2, -1, 0, 1, 2)
        }
    ):
        variants.append(
            {**selected, "name": f"mutacja-{value:.4f}", "mutation_probability": value}
        )
    new_settings = {**data["ustawienia"], "variants": variants}
    print("Propozycja kolejnej rundy (skopiuj do pliku konfiguracji):")
    print(json.dumps(new_settings, ensure_ascii=False, indent=2))


async def run(path: Path) -> Path:
    settings = Settings.model_validate_json(path.read_text(encoding="utf-8-sig"))
    try:
        catalog = await load_catalog(settings.trainer_id)
        print(
            f"Katalog: {len(catalog.candidates)} ćwiczeń, trener {catalog.trainer_id}",
            flush=True,
        )
        results = run_lab(catalog, settings)
    finally:
        await dispose_engine()
    output = Path(settings.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = output / f"eksperyment-{timestamp}-{uuid4().hex[:8]}.json"
    comparison = []
    for result in results:
        worst = max(result["scenariusze"], key=lambda s: s["wyniki"]["bledy"])
        comparison.append(
            {
                "nazwa": result["konfiguracja"]["name"],
                "wyniki": result["wyniki"],
                "najwiecej_bledow": {
                    "scenariusz": worst["scenariusz"],
                    "bledy": worst["wyniki"]["bledy"],
                },
            }
        )
    data = {
        "opis": (
            "Oceny fitness są średnimi ważonymi czasem segmentów. "
            "Powtórzenia liczone są po wystąpieniach ćwiczeń. "
            "Ostatnio=4 oznacza brak w trzech mockowanych planach."
        ),
        "data": datetime.now().astimezone().isoformat(),
        "trainer_id": str(catalog.trainer_id),
        "ustawienia": settings.model_dump(mode="json"),
        "kandydaci_do_oceny": shortlist(results),
        "porownanie": comparison,
        "wyniki": results,
    }
    destination.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readable = destination.with_suffix(".md")
    readable.write_text(render_report(data), encoding="utf-8")
    print(f"Czytelny raport: {readable}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Laboratorium generatora planów")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Uruchom sesję")
    run_parser.add_argument("--config", default="experiments/session.json")
    suggest_parser = commands.add_parser(
        "suggest", help="Zaproponuj wartości mutacji wokół wybranej konfiguracji"
    )
    suggest_parser.add_argument("--report", required=True)
    suggest_parser.add_argument("--name", required=True)
    suggest_parser.add_argument("--step", type=float, default=0.01)
    args = parser.parse_args()
    try:
        if args.command == "run":
            print(f"Raport: {asyncio.run(run(Path(args.config)))}")
        else:
            if args.step <= 0:
                raise ValueError("Krok musi być dodatni")
            suggest(Path(args.report), args.name, args.step)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
