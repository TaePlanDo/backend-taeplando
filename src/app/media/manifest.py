"""Validate the artist's files and their explicit catalogue mapping."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.db.exercise_catalog import load_exercise_catalog

MEDIA_URL_FILES = {
    "image_url": "thumb-dark.webp",
    "image_url_light": "thumb-light.webp",
    "animation_url": "anim-dark.webp",
    "animation_url_light": "anim-light.webp",
}
MEDIA_FILES = (
    *MEDIA_URL_FILES.values(),
    "thumb-dark.svg",
    "thumb-light.svg",
)
FALLBACK_FILES = ("thumb-dark.svg", "thumb-light.svg")
MANIFEST_PATH = Path(__file__).with_name("exercise_media.csv")
_COLUMNS = ("source_id", "name", "directory", *MEDIA_FILES)


@dataclass(frozen=True)
class MediaEntry:
    """One exercise (or source 0 placeholder), with per-file SHA-256 digests."""

    source_id: int
    name: str
    directory: str
    digests: dict[str, str]

    def key(self, filename: str) -> str:
        """Keep object identities stable even when a display name changes."""
        return f"exercises/{self.source_id}/{filename}"


def digest(path: Path) -> str:
    """Hash the file contents without relying on timestamps or multipart ETags."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset_path(root: Path, entry: MediaEntry, filename: str) -> Path:
    """Reject escaping paths and symbolic links pointing outside the package."""
    path = (root / entry.directory / filename).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe media file: {entry.directory}/{filename}")
    return path


def validate_entries(entries: list[MediaEntry]) -> None:
    """Require exactly the known catalogue and one explicitly named placeholder."""
    catalog = {
        exercise.source_id: exercise.name for exercise in load_exercise_catalog()
    }
    expected_names = {0: "Placeholder", **catalog}
    if len(entries) != len(expected_names) or {e.source_id for e in entries} != set(
        expected_names
    ):
        raise ValueError(
            "Manifest must contain each catalogue source ID once and placeholder 0"
        )
    for entry in entries:
        expected_files = FALLBACK_FILES if entry.source_id == 0 else MEDIA_FILES
        if entry.name != expected_names[entry.source_id]:
            raise ValueError(f"Catalogue name mismatch for source {entry.source_id}")
        if (
            not entry.directory.startswith(f"{entry.source_id}-")
            or Path(entry.directory).name != entry.directory
            or "/" in entry.directory
            or "\\" in entry.directory
        ):
            raise ValueError(f"Invalid directory for source {entry.source_id}")
        if set(entry.digests) != set(expected_files) or any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in entry.digests.values()
        ):
            raise ValueError(f"Invalid media digests for source {entry.source_id}")


def load_manifest(path: Path = MANIFEST_PATH) -> list[MediaEntry]:
    """Read and validate a portable, reviewable manifest without absolute paths."""
    with path.open(encoding="utf-8", newline="") as stream:
        try:
            reader = csv.reader(stream, strict=True)
            if tuple(next(reader, ())) != _COLUMNS:
                raise ValueError("Unexpected media manifest columns")
            entries = []
            for row in reader:
                if not row:
                    continue
                if len(row) != len(_COLUMNS):
                    raise ValueError(
                        f"Unexpected column count in manifest row {reader.line_num}"
                    )
                source_id, name, directory, *digests = row
                entries.append(
                    MediaEntry(
                        source_id=int(source_id),
                        name=name,
                        directory=directory,
                        digests={
                            filename: value
                            for filename, value in zip(
                                MEDIA_FILES, digests, strict=True
                            )
                            if value
                        },
                    )
                )
        except csv.Error as exc:
            raise ValueError(f"Malformed media manifest CSV: {exc}") from exc
    validate_entries(entries)
    return entries


def validate_files(root: Path, entries: list[MediaEntry]) -> None:
    """Finish all local checks before allowing uploads or database writes."""
    validate_entries(entries)
    for entry in entries:
        for filename, expected_digest in entry.digests.items():
            path = asset_path(root, entry, filename)
            if path.stat().st_size == 0 or digest(path) != expected_digest:
                raise ValueError(
                    f"Media checksum mismatch: {entry.directory}/{filename}"
                )


def build_manifest(root: Path, output: Path) -> list[MediaEntry]:
    """Generate the manifest from the delivered, numbered artist directories."""
    names = {0: "Placeholder", **{e.source_id: e.name for e in load_exercise_catalog()}}
    entries: list[MediaEntry] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            raise ValueError(f"Unexpected media root entry: {directory.name}")
        source_id = int(directory.name.split("-", 1)[0])
        if source_id not in names:
            raise ValueError(f"Unknown catalogue source ID: {source_id}")
        filenames = FALLBACK_FILES if source_id == 0 else MEDIA_FILES
        if {p.name for p in directory.iterdir()} != set(filenames):
            raise ValueError(f"Unexpected file set: {directory.name}")
        entry = MediaEntry(source_id, names[source_id], directory.name, {})
        entry.digests.update(
            {
                filename: digest(asset_path(root, entry, filename))
                for filename in filenames
            }
        )
        entries.append(entry)
    entries.sort(key=lambda entry: entry.source_id)
    validate_files(root, entries)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {
                "source_id": e.source_id,
                "name": e.name,
                "directory": e.directory,
                **e.digests,
            }
            for e in entries
        )
    return entries
