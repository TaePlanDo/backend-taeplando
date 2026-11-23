"""Failed uploads and dry runs cannot publish catalogue URLs."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.media.cli import run_import
from app.media.manifest import MediaEntry


@pytest.fixture
def import_case():
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = AsyncMock()
    factory.begin.return_value.__aenter__.return_value = AsyncMock()
    with (
        patch(
            "app.media.cli.load_manifest",
            return_value=[MediaEntry(1, "Test", "1-test", {})],
        ),
        patch("app.media.cli.validate_files"),
        patch("app.media.cli.MediaStorageSettings") as settings,
        patch("app.media.cli.get_session_factory", return_value=factory),
        patch("app.media.cli.load_targets", new=AsyncMock(return_value={1: ()})),
        patch("app.media.cli.upload_manifest", return_value=(1, 0)) as upload,
        patch("app.media.cli.create_client") as client,
        patch("app.media.cli.save_urls", new=AsyncMock(return_value=1)) as save,
        patch("app.media.cli.dispose_engine", new=AsyncMock()) as dispose,
    ):
        yield factory, settings, upload, client, save, dispose


@pytest.mark.parametrize("dry_run", [True, False])
def test_dry_run_or_upload_failure_never_writes_database(
    tmp_path, import_case, dry_run
):
    factory, settings, upload, client, save, dispose = import_case
    upload.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Denied"}}, "HeadObject"
    )
    if dry_run:
        asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=True))
        settings.assert_not_called()
        client.assert_not_called()
        upload.assert_not_called()
    else:
        with pytest.raises(ClientError):
            asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=False))
        client.return_value.close.assert_called_once()
    factory.begin.assert_not_called()
    save.assert_not_called()
    dispose.assert_awaited_once()


@pytest.mark.parametrize("write_fails", [False, True])
def test_publish_owns_transaction_after_upload(tmp_path, import_case, write_fails):
    factory, _, upload, client, save, dispose = import_case
    transaction = factory.begin.return_value
    write_session = transaction.__aenter__.return_value

    def upload_files(*args):
        factory.begin.assert_not_called()
        return 1, 0

    async def write_urls(*args):
        upload.assert_called_once()
        client.return_value.close.assert_called_once()
        assert args[0] is write_session
        if write_fails:
            raise RuntimeError("Database write failed")
        return 1

    upload.side_effect = upload_files
    save.side_effect = write_urls
    if write_fails:
        with pytest.raises(RuntimeError, match="Database write failed"):
            asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=False))
    else:
        asyncio.run(run_import(tmp_path, tmp_path / "media.csv", dry_run=False))
    factory.begin.assert_called_once()
    transaction.__aexit__.assert_awaited_once()
    assert transaction.__aexit__.await_args.args[0] is (
        RuntimeError if write_fails else None
    )
    write_session.commit.assert_not_called()
    dispose.assert_awaited_once()
