"""Failed uploads and dry runs cannot publish catalogue URLs."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.media.cli import run_import
from app.media.manifest import MediaEntry


@pytest.mark.parametrize("dry_run", [True, False])
def test_dry_run_or_upload_failure_never_writes_database(tmp_path, dry_run):
    factory = MagicMock()
    session = AsyncMock()
    factory.return_value.__aenter__.return_value = session
    upload_error = ClientError(
        {"Error": {"Code": "403", "Message": "Denied"}}, "HeadObject"
    )
    with (
        patch(
            "app.media.cli.load_manifest",
            return_value=[MediaEntry(1, "Test", "1-test", {})],
        ),
        patch("app.media.cli.validate_files"),
        patch("app.media.cli.MediaStorageSettings"),
        patch("app.media.cli.get_session_factory", return_value=factory),
        patch("app.media.cli.load_targets", new=AsyncMock(return_value={1: ()})),
        patch("app.media.cli.upload_manifest", side_effect=upload_error) as upload,
        patch("app.media.cli.create_client") as client,
        patch("app.media.cli.save_urls", new=AsyncMock()) as save,
        patch("app.media.cli.dispose_engine", new=AsyncMock()),
    ):
        if dry_run:
            asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=True))
            client.assert_not_called()
            upload.assert_not_called()
        else:
            with pytest.raises(ClientError):
                asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=False))
            client.return_value.close.assert_called_once()
        save.assert_not_called()
        session.commit.assert_not_called()
