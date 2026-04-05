"""
Shared Storage Package

Provides the StorageAdapter interface and the MinIO/S3 implementation.
Import `get_storage_adapter` to obtain a configured adapter via FastAPI Depends.
"""

from .interface import StorageAdapter, StorageError
from .minio_adapter import MinioStorageAdapter, build_minio_adapter

__all__ = [
    "StorageAdapter",
    "StorageError",
    "MinioStorageAdapter",
    "build_minio_adapter",
]
