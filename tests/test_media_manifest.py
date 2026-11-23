"""Media manifests must cover the catalogue and pin the exact delivered bytes."""

import csv
import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.media import manifest


@pytest.fixture
def media_package(tmp_path, monkeypatch):
    monkeypatch.setattr(
        manifest,
        "load_exercise_catalog",
        lambda: (SimpleNamespace(source_id=1, name="Bieg między liniami"),),
    )
    for directory, files in (
        ("0-empty", manifest.FALLBACK_FILES),
        ("1-bieg-miedzy-liniami", manifest.MEDIA_FILES),
    ):
        folder = tmp_path / directory
        folder.mkdir()
        for filename in files:
            (folder / filename).write_bytes(filename.encode())
    return tmp_path


def test_delivered_manifest_covers_catalogue_and_all_variants():
    entries = manifest.load_manifest()
    assert len(entries) == 319
    assert sum(len(e.digests) for e in entries) == 1910
    assert entries[0].source_id == 0
    assert entries[-1].source_id == 318


def test_manifest_round_trip_and_deterministic_keys(media_package):
    output = media_package.parent / "media.csv"
    entries = manifest.build_manifest(media_package, output)
    assert manifest.load_manifest(output) == entries
    manifest.validate_files(media_package, entries)
    assert entries[1].key("anim-light.webp") == "exercises/1/anim-light.webp"
    assert replace(entries[1], directory="1-renamed").key("anim-light.webp") == entries[
        1
    ].key("anim-light.webp")


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "unknown", "name", "traversal", "digest", "variant"],
)
def test_manifest_rejects_invalid_mapping(media_package, change):
    entries = manifest.build_manifest(media_package, media_package.parent / "media.csv")
    if change == "missing":
        entries.pop()
    elif change == "duplicate":
        entries.append(entries[1])
    elif change == "unknown":
        entries[1] = replace(entries[1], source_id=999)
    elif change == "name":
        entries[1] = replace(entries[1], name="Other exercise")
    elif change == "traversal":
        entries[1] = replace(entries[1], directory="1-../../outside")
    elif change == "digest":
        entries[1].digests["thumb-dark.webp"] = "bad"
    else:
        entries[1].digests.pop("anim-light.webp")
    with pytest.raises(ValueError):
        manifest.validate_entries(entries)


def test_preflight_rejects_modified_or_missing_asset(media_package):
    entries = manifest.build_manifest(media_package, media_package.parent / "media.csv")
    path = media_package / entries[1].directory / "anim-dark.webp"
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum"):
        manifest.validate_files(media_package, entries)
    path.unlink()
    with pytest.raises(ValueError, match="Missing"):
        manifest.validate_files(media_package, entries)


def test_builder_rejects_incomplete_asset_set(media_package):
    (media_package / "1-bieg-miedzy-liniami" / "anim-light.webp").unlink()
    with pytest.raises(ValueError, match="file set"):
        manifest.build_manifest(media_package, media_package.parent / "media.csv")


def test_asset_resolution_rejects_escape(tmp_path):
    outside = tmp_path.parent / "outside-media.webp"
    outside.write_bytes(b"outside")
    entry = manifest.MediaEntry(
        1, "Name", "..", {outside.name: hashlib.sha256(b"outside").hexdigest()}
    )
    with pytest.raises(ValueError, match="unsafe"):
        manifest.asset_path(tmp_path, entry, outside.name)


def test_invalid_manifest_columns_fail(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("source_id,directory\n1,1-test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        manifest.load_manifest(path)


@pytest.mark.parametrize(
    "change", ["missing_directory", "missing_digest", "extra_cell"]
)
def test_manifest_rejects_wrong_row_width(media_package, change):
    path = media_package.parent / "media.csv"
    manifest.build_manifest(media_package, path)
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    if change == "missing_directory":
        rows[1] = rows[1][:2]
    elif change == "missing_digest":
        rows[1].pop()
    else:
        rows[1].append("ignored data")
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    with pytest.raises(ValueError, match="column count.*row 2"):
        manifest.load_manifest(path)


def test_manifest_rejects_unclosed_csv_quote(media_package):
    path = media_package.parent / "media.csv"
    manifest.build_manifest(media_package, path)
    prefix, last_digest = path.read_text(encoding="utf-8").rstrip().rsplit(",", 1)
    path.write_text(f'{prefix},"{last_digest}', encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed.*CSV"):
        manifest.load_manifest(path)
