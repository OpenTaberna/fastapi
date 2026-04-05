"""
Storage Adapter Interface

Defines the abstract contract every object-storage backend must implement.
New backends (AWS S3, GCS, Azure Blob) are added by subclassing StorageAdapter
— no calling code needs to change (Open/Closed Principle).

Design:
    - StorageAdapter is the only type callers depend on (DIP).
    - Each method has a single, clearly defined responsibility (SRP).
    - All methods are async and safe to call from the asyncio event loop.
"""

from abc import ABC, abstractmethod

from app.shared.exceptions.base import AppException
from app.shared.exceptions.enums import ErrorCategory, ErrorCode


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class StorageError(AppException):
    """
    Raised when an object-storage operation fails.

    Maps to HTTP 502 Bad Gateway at the router layer — the failure is
    in the external storage system, not in client input.
    """

    def __init__(
        self,
        message: str,
        context: dict | None = None,
        original_exception: Exception | None = None,
    ) -> None:
        """
        Args:
            message:            Human-readable description of the failure.
            context:            Extra data (e.g. bucket name, object key).
            original_exception: Underlying SDK exception, if any.
        """
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            category=ErrorCategory.EXTERNAL_SERVICE,
            context=context or {},
            original_exception=original_exception,
        )


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class StorageAdapter(ABC):
    """
    Abstract interface for object-storage backends.

    Implement this class to add support for a new storage provider.
    All implementations must be stateless and safe to reuse across requests.

    Implementations:
        MinioStorageAdapter — wraps aiobotocore with a MinIO/S3-compatible endpoint.
    """

    @abstractmethod
    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload bytes to the given bucket under the given key.

        Args:
            bucket:       Destination bucket name.
            key:          Object key (path within the bucket, e.g. "labels/uuid.pdf").
            data:         Raw bytes to store.
            content_type: MIME type for the object (e.g. "application/pdf").

        Returns:
            The public or pre-signed URL at which the object can be retrieved.

        Raises:
            StorageError: If the upload fails for any reason.
        """
        ...

    @abstractmethod
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
            StorageError: If the object does not exist or the download fails.
        """
        ...

    @abstractmethod
    async def ensure_bucket(self, bucket: str) -> None:
        """
        Create the bucket if it does not already exist.

        Idempotent — safe to call on application startup even if the bucket
        was created in a previous run.

        Args:
            bucket: Name of the bucket to create/verify.

        Returns:
            None

        Raises:
            StorageError: If the bucket cannot be created or checked.
        """
        ...
