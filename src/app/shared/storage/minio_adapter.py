"""
MinIO / S3 Storage Adapter

Concrete implementation of StorageAdapter backed by aiobotocore, which
provides a fully async S3-compatible client.  Works with both self-hosted
MinIO and AWS S3 — the only difference is the endpoint_url.

Configuration:
    Build via build_minio_adapter() and inject with FastAPI Depends.
    Credentials are read from application Settings — never hard-coded.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiobotocore.session
from botocore.exceptions import BotoCoreError, ClientError

from app.shared.logger import get_logger

from .interface import StorageAdapter, StorageError

logger = get_logger(__name__)


class MinioStorageAdapter(StorageAdapter):
    """
    StorageAdapter implementation for MinIO / S3-compatible object stores.

    Uses aiobotocore to make fully async S3 API calls without blocking the
    FastAPI event loop.  A new aiobotocore session is opened per operation
    to avoid shared state across requests.

    Attributes:
        _endpoint_url:  Full URL of the S3-compatible endpoint.
        _access_key:    Access key ID.
        _secret_key:    Secret access key.
        _region:        AWS region name (MinIO accepts any value here).
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        """
        Initialise the adapter with connection credentials.

        Args:
            endpoint_url: Full S3 endpoint URL (e.g. "http://localhost:9000").
            access_key:   Access key ID (MinIO root user or AWS IAM key).
            secret_key:   Secret access key (MinIO root password or AWS secret).
            region:       Region string — MinIO ignores this, AWS requires it.
        """
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator:
        """
        Async context manager that yields a configured aiobotocore S3 client.

        Opens a fresh session per call so the adapter remains stateless and
        there are no connection-pool conflicts between concurrent requests.

        Returns:
            Async generator yielding the aiobotocore S3 client.
        """
        session = aiobotocore.session.get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as client:
            yield client

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload bytes to a bucket and return the storage URL for the object.

        The returned URL is the direct S3/MinIO path.  For public access,
        configure the bucket ACL or use a pre-signed URL instead.

        Args:
            bucket:       Destination bucket name.
            key:          Object key within the bucket (e.g. "labels/uuid.pdf").
            data:         Raw bytes to store.
            content_type: MIME type string (e.g. "application/pdf").

        Returns:
            String URL in the form "{endpoint_url}/{bucket}/{key}".

        Raises:
            StorageError: If the S3 PutObject call fails.
        """
        logger.info(
            "Uploading object to storage",
            extra={"bucket": bucket, "key": key, "size_bytes": len(data)},
        )
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(
                message="Failed to upload object to storage",
                context={"bucket": bucket, "key": key},
                original_exception=exc,
            ) from exc

        url = f"{self._endpoint_url}/{bucket}/{key}"
        logger.info("Object uploaded", extra={"url": url})
        return url

    async def download(
        self,
        bucket: str,
        key: str,
    ) -> bytes:
        """
        Download an object from storage and return its raw bytes.

        Args:
            bucket: Source bucket name.
            key:    Object key to retrieve.

        Returns:
            Raw bytes of the stored object.

        Raises:
            StorageError: If the object is missing or the download fails.
        """
        logger.debug(
            "Downloading object from storage",
            extra={"bucket": bucket, "key": key},
        )
        try:
            async with self._client() as client:
                response = await client.get_object(Bucket=bucket, Key=key)
                body: bytes = await response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(
                message="Failed to download object from storage",
                context={"bucket": bucket, "key": key},
                original_exception=exc,
            ) from exc

        logger.debug(
            "Object downloaded",
            extra={"bucket": bucket, "key": key, "size_bytes": len(body)},
        )
        return body

    async def ensure_bucket(self, bucket: str) -> None:
        """
        Create the bucket if it does not already exist.

        MinIO and S3 both return a 409 BucketAlreadyOwnedByYou error when the
        bucket exists and belongs to the caller — that response is silently
        ignored so this method stays idempotent.

        Args:
            bucket: Name of the bucket to create/verify.

        Returns:
            None

        Raises:
            StorageError: If the bucket creation fails for any reason other
                          than the bucket already existing.
        """
        logger.info("Ensuring storage bucket exists", extra={"bucket": bucket})
        try:
            async with self._client() as client:
                await client.create_bucket(Bucket=bucket)
                logger.info("Storage bucket created", extra={"bucket": bucket})
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                logger.debug("Storage bucket already exists", extra={"bucket": bucket})
                return
            raise StorageError(
                message="Failed to ensure storage bucket exists",
                context={"bucket": bucket},
                original_exception=exc,
            ) from exc
        except BotoCoreError as exc:
            raise StorageError(
                message="Failed to ensure storage bucket exists",
                context={"bucket": bucket},
                original_exception=exc,
            ) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_minio_adapter(
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
) -> MinioStorageAdapter:
    """
    Construct a MinioStorageAdapter from explicit credentials.

    Intended for use with FastAPI Depends:

        async def get_storage_adapter(
            settings: Annotated[Settings, Depends(get_settings)],
        ) -> MinioStorageAdapter:
            return build_minio_adapter(
                endpoint_url=settings.storage_endpoint_url,
                access_key=settings.storage_access_key,
                secret_key=settings.storage_secret_key,
                region=settings.storage_region,
            )

    Args:
        endpoint_url: Full S3-compatible endpoint URL.
        access_key:   Access key ID.
        secret_key:   Secret access key.
        region:       Region string (default "us-east-1").

    Returns:
        Configured MinioStorageAdapter instance.
    """
    return MinioStorageAdapter(
        endpoint_url=endpoint_url,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )
