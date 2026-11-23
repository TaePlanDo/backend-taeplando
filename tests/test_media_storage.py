"""Exercise S3 requests without network access or real credentials."""

import hashlib

import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from pydantic import ValidationError

from app.media.manifest import MediaEntry
from app.media.storage import (
    CACHE_CONTROL,
    MediaPublicSettings,
    MediaStorageSettings,
    create_client,
    upload_file,
)


@pytest.fixture
def storage_settings():
    return MediaStorageSettings(
        _env_file=None,
        s3_endpoint="https://storage.example.com",
        s3_bucket="media",
        s3_access_key_id="test-access",
        s3_secret_access_key="test-secret",
        public_base_url="https://cdn.example.com/assets",
    )


@pytest.fixture
def upload_case(tmp_path, storage_settings):
    folder = tmp_path / "1-test"
    folder.mkdir()
    body = b"webp contents"
    (folder / "thumb-light.webp").write_bytes(body)
    checksum = hashlib.sha256(body).hexdigest()
    entry = MediaEntry(1, "Test", "1-test", {"thumb-light.webp": checksum})
    client = create_client(storage_settings)
    with Stubber(client) as stub:
        yield tmp_path, entry, client, stub, body, checksum
        stub.assert_no_pending_responses()
    client.close()


def test_upload_missing_file_and_repeat_skips(storage_settings, upload_case):
    root, entry, client, stub, body, checksum = upload_case
    params = {"Bucket": "media", "Key": "exercises/1/thumb-light.webp"}
    stub.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params=params,
    )
    stub.add_response(
        "put_object",
        {},
        {
            **params,
            "Body": body,
            "Metadata": {"sha256": checksum},
            "ContentType": "image/webp",
            "CacheControl": CACHE_CONTROL,
        },
    )
    assert upload_file(client, storage_settings, root, entry, "thumb-light.webp")
    stub.add_response(
        "head_object",
        {
            "Metadata": {"sha256": checksum},
            "ContentLength": len(body),
            "ContentType": "image/webp",
            "CacheControl": CACHE_CONTROL,
        },
        params,
    )
    assert not upload_file(client, storage_settings, root, entry, "thumb-light.webp")


def test_changed_file_overwrites_same_key(storage_settings, upload_case):
    root, entry, client, stub, body, checksum = upload_case
    params = {"Bucket": "media", "Key": "exercises/1/thumb-light.webp"}
    stub.add_response("head_object", {"Metadata": {"sha256": "old"}}, params)
    stub.add_response(
        "put_object",
        {},
        {
            **params,
            "Body": body,
            "Metadata": {"sha256": checksum},
            "ContentType": "image/webp",
            "CacheControl": CACHE_CONTROL,
        },
    )
    assert upload_file(client, storage_settings, root, entry, "thumb-light.webp")


def test_permission_error_never_attempts_write(storage_settings, upload_case):
    root, entry, client, stub, _, _ = upload_case
    stub.add_client_error(
        "head_object",
        service_error_code="403",
        http_status_code=403,
        expected_params={"Bucket": "media", "Key": entry.key("thumb-light.webp")},
    )
    with pytest.raises(ClientError):
        upload_file(client, storage_settings, root, entry, "thumb-light.webp")


def test_changed_local_file_fails_before_network(storage_settings, upload_case):
    root, entry, client, _, _, _ = upload_case
    (root / "1-test/thumb-light.webp").write_bytes(b"changed after preflight")
    with pytest.raises(ValueError, match="changed during import"):
        upload_file(client, storage_settings, root, entry, "thumb-light.webp")


def test_public_url_and_credentials_are_safe(storage_settings):
    assert (
        storage_settings.public_url("exercises/1/thumb-dark.webp")
        == "https://cdn.example.com/assets/exercises/1/thumb-dark.webp"
    )
    assert "test-secret" not in repr(storage_settings)
    assert "test-access" not in repr(storage_settings)
    with pytest.raises(ValidationError, match="must not contain"):
        MediaStorageSettings(
            **{
                **storage_settings.model_dump(),
                "public_base_url": "https://cdn.example.com/?token=secret",
            }
        )


def test_public_settings_build_all_exercise_media_without_upload_credentials():
    settings = MediaPublicSettings(
        _env_file=None,
        public_base_url="https://cdn.example.com/assets",
    )

    assert settings.exercise_urls(7) == {
        "image_url": "https://cdn.example.com/assets/exercises/7/thumb-dark.webp",
        "image_url_light": (
            "https://cdn.example.com/assets/exercises/7/thumb-light.webp"
        ),
        "animation_url": "https://cdn.example.com/assets/exercises/7/anim-dark.webp",
        "animation_url_light": (
            "https://cdn.example.com/assets/exercises/7/anim-light.webp"
        ),
    }
