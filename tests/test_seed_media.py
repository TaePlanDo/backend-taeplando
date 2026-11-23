"""Media-enabled system seed orchestration."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, sentinel

from app.db.seed import main, seed_system_data


def test_seed_cli_accepts_include_animations() -> None:
    with (
        patch.object(sys, "argv", ["seed-system-data", "--include=animations"]),
        patch(
            "app.db.seed.run_seed_command",
            new=MagicMock(return_value=sentinel.command),
        ) as command,
        patch("app.db.seed.asyncio.run") as run,
    ):
        main()

    command.assert_called_once_with(include_animations=True)
    run.assert_called_once_with(sentinel.command)


def test_seed_system_data_passes_public_media_to_demo_rows() -> None:
    exercises = (SimpleNamespace(source_id=7),)
    urls = {
        "image_url": "https://cdn.example.com/exercises/7/thumb-dark.webp",
        "animation_url": "https://cdn.example.com/exercises/7/anim-dark.webp",
        "image_url_light": "https://cdn.example.com/exercises/7/thumb-light.webp",
        "animation_url_light": "https://cdn.example.com/exercises/7/anim-light.webp",
    }
    public_media = MagicMock()
    public_media.exercise_urls.return_value = urls
    session = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session

    with (
        patch("app.db.seed.load_exercise_catalog", return_value=exercises),
        patch("app.db.seed.MediaPublicSettings", return_value=public_media),
        patch("app.db.seed.get_session_factory", return_value=session_factory),
        patch("app.db.seed.seed_training_segments", new=AsyncMock()),
        patch("app.db.seed.seed_training_types", new=AsyncMock()),
        patch("app.db.seed.seed_demo_data", new=AsyncMock()) as seed_demo,
    ):
        asyncio.run(seed_system_data(include_animations=True))

    public_media.exercise_urls.assert_called_once_with(7)
    seed_demo.assert_awaited_once_with(session, exercises, {7: urls})
