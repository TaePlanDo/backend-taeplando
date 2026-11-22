"""Build manifests or import validated media into S3/R2 and the catalogue DB."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from app.db.session import dispose_engine, get_session_factory
from app.media.database import load_targets, save_urls
from app.media.manifest import (
    MANIFEST_PATH,
    build_manifest,
    load_manifest,
    validate_files,
)
from app.media.storage import MediaStorageSettings, create_client, upload_manifest


async def run_import(root: Path, manifest: Path, *, dry_run: bool) -> None:
    """Perform preflight checks, finish uploads, then commit URLs in one transaction."""
    entries = load_manifest(manifest)
    validate_files(root, entries)
    try:
        async with get_session_factory()() as session:
            targets = await load_targets(session, entries)
        file_count = sum(len(entry.digests) for entry in entries)
        print(
            f"Validated {len(targets)} catalogue exercises and {file_count} files.",
            flush=True,
        )
        if dry_run:
            print("Dry run: no storage or database writes.")
            return
        settings = MediaStorageSettings()
        client = create_client(settings)
        try:
            uploaded, skipped = await asyncio.to_thread(
                upload_manifest, client, settings, root, entries
            )
        finally:
            client.close()
        async with get_session_factory().begin() as session:
            count = await save_urls(session, entries, settings)
        print(f"Uploaded {uploaded}; unchanged {skipped}; linked {count} exercises.")
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-manifest")
    build.add_argument("--media-root", type=Path, required=True)
    build.add_argument("--output", type=Path, default=MANIFEST_PATH)
    upload = commands.add_parser("import")
    upload.add_argument("--media-root", type=Path, required=True)
    upload.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    upload.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "build-manifest":
            entries = build_manifest(args.media_root, args.output)
            print(f"Wrote {len(entries)} manifest entries to {args.output}")
        else:
            asyncio.run(
                run_import(args.media_root, args.manifest, dry_run=args.dry_run)
            )
    except ValidationError:
        # Pydantic error details may contain supplied credential values.
        parser.exit(
            1,
            "Invalid media storage configuration; check EXERCISE_MEDIA_* variables.\n",
        )
    except (BotoCoreError, ClientError):
        parser.exit(
            1,
            "Media storage request failed; check endpoint, bucket and credentials. "
            "No database URLs were committed.\n",
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Media import failed: {exc}\n")


if __name__ == "__main__":
    main()
