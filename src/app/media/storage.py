"""S3-compatible uploads with deterministic keys and content-based retries."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.media.manifest import MEDIA_URL_FILES, MediaEntry, asset_path

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

UPLOAD_WORKERS = 8
CACHE_CONTROL = "public, max-age=3600"


class MediaPublicSettings(BaseSettings):
    """Public catalogue-media location without upload credentials."""

    model_config = SettingsConfigDict(
        env_prefix="EXERCISE_MEDIA_", env_file=".env", extra="ignore"
    )

    public_base_url: HttpUrl

    @field_validator("public_base_url")
    @classmethod
    def validate_public_base(cls, value: HttpUrl) -> HttpUrl:
        """Object keys must be appended to a public path, never a signed query."""
        if value.query or value.fragment or value.username or value.password:
            raise ValueError(
                "Public media base must not contain credentials, query or fragment"
            )
        return value

    def public_url(self, key: str) -> str:
        return f"{str(self.public_base_url).rstrip('/')}/{quote(key, safe='/')}"

    def exercise_urls(self, source_id: int) -> dict[str, str]:
        """Build the canonical API fields for one stable catalogue object prefix."""
        return {
            field: self.public_url(f"exercises/{source_id}/{filename}")
            for field, filename in MEDIA_URL_FILES.items()
        }


class MediaStorageSettings(MediaPublicSettings):
    """Import-only credentials; application startup does not require storage."""

    s3_endpoint: HttpUrl
    s3_region: str = "auto"
    s3_bucket: str = Field(min_length=1)
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr


def create_client(settings: MediaStorageSettings) -> S3Client:
    """Use explicit scoped credentials and R2-compatible request checksums."""
    return boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint),
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            retries={"mode": "standard", "max_attempts": 3},
            connect_timeout=10,
            read_timeout=60,
            max_pool_connections=UPLOAD_WORKERS,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def upload_file(
    client: S3Client,
    settings: MediaStorageSettings,
    root: Path,
    entry: MediaEntry,
    filename: str,
) -> bool:
    """Add missing or replace changed objects; propagate permission/network errors."""
    body = asset_path(root, entry, filename).read_bytes()
    checksum = hashlib.sha256(body).hexdigest()
    if checksum != entry.digests[filename]:
        raise ValueError(f"Media changed during import: {entry.directory}/{filename}")
    key = entry.key(filename)
    content_type = "image/svg+xml" if filename.endswith(".svg") else "image/webp"
    try:
        head = client.head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
            raise
    else:
        if (
            head.get("Metadata", {}).get("sha256") == checksum
            and head.get("ContentLength") == len(body)
            and head.get("ContentType") == content_type
            and head.get("CacheControl") == CACHE_CONTROL
        ):
            return False
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
        CacheControl=CACHE_CONTROL,
        Metadata={"sha256": checksum},
    )
    return True


def upload_manifest(
    client: S3Client,
    settings: MediaStorageSettings,
    root: Path,
    entries: list[MediaEntry],
) -> tuple[int, int]:
    """Bound upload concurrency and finish uploads before updating database URLs."""
    jobs = [(entry, filename) for entry in entries for filename in entry.digests]
    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as executor:
        futures = [
            executor.submit(upload_file, client, settings, root, *job) for job in jobs
        ]
        try:
            uploaded = sum(future.result() for future in as_completed(futures))
        finally:
            # Stop queued requests on failure; wait only for already active uploads.
            for future in futures:
                future.cancel()
    return uploaded, len(jobs) - uploaded
