"""
Product Image Handling

Validates an uploaded product image and works out where it lives in the object
store.

Validation is deliberately not "trust the Content-Type header". A browser sends
whatever the client claims, so the bytes are checked against the magic numbers
of the formats actually accepted. A file that says `image/png` but begins with
`<?php` would otherwise be stored and later served back to a customer's browser
from our own origin.
"""

from uuid import UUID

from app.shared.exceptions import operation_not_allowed
from app.shared.logger import get_logger

logger = get_logger(__name__)

# Object key pattern. One image per item, so a re-upload replaces the previous
# file rather than accumulating orphans nothing points at.
_IMAGE_KEY_TEMPLATE = "items/{item_uuid}.{ext}"

# Formats accepted, with the leading bytes that prove it. WebP needs a second
# check because its magic number is split across the RIFF container header.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
}

_EXTENSIONS = {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}

_MIME_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def detect_image_format(data: bytes) -> str:
    """
    Identify the image format from the bytes themselves.

    Args:
        data: Raw uploaded bytes.

    Returns:
        One of "jpeg", "png", "gif", "webp".

    Raises:
        BusinessRuleError (400): If the content is not a supported image.
    """
    for fmt, signatures in _SIGNATURES.items():
        if any(data.startswith(sig) for sig in signatures):
            if fmt == "webp" and data[8:12] != b"WEBP":
                # RIFF alone is a container; other RIFF payloads are not images.
                continue
            return fmt

    raise operation_not_allowed(
        operation="upload_item_image",
        reason=(
            "The file is not a supported image. Accepted formats are JPEG, PNG, "
            "GIF and WebP."
        ),
    )


def assert_within_size_limit(data: bytes, limit_bytes: int) -> None:
    """
    Reject an image larger than the configured limit.

    Args:
        data:        Raw uploaded bytes.
        limit_bytes: Largest accepted size.

    Raises:
        BusinessRuleError (400): If the upload is too large.
    """
    if len(data) > limit_bytes:
        raise operation_not_allowed(
            operation="upload_item_image",
            reason=(
                f"The image is {len(data) // 1024} kB, above the "
                f"{limit_bytes // 1024} kB limit."
            ),
        )


def image_key(item_uuid: UUID, image_format: str) -> str:
    """
    Build the object key for an item's image.

    Args:
        item_uuid:    The item the image belongs to.
        image_format: Result of detect_image_format.

    Returns:
        Object key, e.g. ``items/6f1e....jpg``.
    """
    return _IMAGE_KEY_TEMPLATE.format(
        item_uuid=item_uuid, ext=_EXTENSIONS[image_format]
    )


def mime_type(image_format: str) -> str:
    """
    Args:
        image_format: Result of detect_image_format.

    Returns:
        The MIME type to store and serve the image with.
    """
    return _MIME_TYPES[image_format]


def public_image_url(item_uuid: UUID) -> str:
    """
    The URL stored on the item and used by storefront and admin alike.

    Points at this API rather than at MinIO directly, so the object store stays
    private and can be moved or re-bucketed without touching stored data.

    Args:
        item_uuid: The item the image belongs to.

    Returns:
        API-relative image URL.
    """
    return f"/v1/items/{item_uuid}/image"
