"""
Unit tests for product image handling.

Covers detect_image_format, assert_within_size_limit, image_key, mime_type and
public_image_url. No network and no object store.
"""

from uuid import uuid4

import pytest

from app.services.crud_item_store.functions.item_images import (
    assert_within_size_limit,
    detect_image_format,
    image_key,
    mime_type,
    public_image_url,
)
from app.shared.exceptions.errors import BusinessRuleError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF87 = b"GIF87a" + b"\x00" * 32
GIF89 = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


class TestDetectImageFormat:
    def test_detects_png(self):
        assert detect_image_format(PNG) == "png"

    def test_detects_jpeg(self):
        assert detect_image_format(JPEG) == "jpeg"

    def test_detects_gif87(self):
        assert detect_image_format(GIF87) == "gif"

    def test_detects_gif89(self):
        assert detect_image_format(GIF89) == "gif"

    def test_detects_webp(self):
        assert detect_image_format(WEBP) == "webp"

    def test_rejects_a_script_claiming_to_be_an_image(self):
        # The declared Content-Type is client-controlled. Storing this and
        # later serving it from our own origin is the actual risk.
        with pytest.raises(BusinessRuleError):
            detect_image_format(b"<?php system($_GET['c']); ?>")

    def test_rejects_a_riff_container_that_is_not_webp(self):
        # RIFF also fronts WAV and AVI; only the WEBP payload is an image.
        wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 32
        with pytest.raises(BusinessRuleError):
            detect_image_format(wav)

    def test_rejects_empty_content(self):
        with pytest.raises(BusinessRuleError):
            detect_image_format(b"")

    def test_rejects_a_png_signature_that_is_only_partial(self):
        with pytest.raises(BusinessRuleError):
            detect_image_format(b"\x89PN")

    def test_error_names_the_accepted_formats(self):
        with pytest.raises(BusinessRuleError) as exc:
            detect_image_format(b"nonsense")
        assert "JPEG" in exc.value.message and "WebP" in exc.value.message


class TestSizeLimit:
    def test_accepts_content_under_the_limit(self):
        assert_within_size_limit(b"x" * 100, 1000)

    def test_accepts_content_exactly_at_the_limit(self):
        assert_within_size_limit(b"x" * 1000, 1000)

    def test_rejects_content_over_the_limit(self):
        with pytest.raises(BusinessRuleError):
            assert_within_size_limit(b"x" * 1001, 1000)

    def test_error_reports_both_sizes(self):
        with pytest.raises(BusinessRuleError) as exc:
            assert_within_size_limit(b"x" * 4096, 2048)
        assert "4 kB" in exc.value.message and "2 kB" in exc.value.message


class TestKeysAndUrls:
    def test_key_uses_the_item_uuid_and_format_extension(self):
        uid = uuid4()
        assert image_key(uid, "jpeg") == f"items/{uid}.jpg"

    def test_key_is_stable_for_the_same_item_and_format(self):
        # One image per item: a re-upload must overwrite rather than leave an
        # orphan nothing points at.
        uid = uuid4()
        assert image_key(uid, "png") == image_key(uid, "png")

    def test_png_and_webp_keep_their_own_extensions(self):
        uid = uuid4()
        assert image_key(uid, "png").endswith(".png")
        assert image_key(uid, "webp").endswith(".webp")

    def test_mime_types_match_the_formats(self):
        assert mime_type("jpeg") == "image/jpeg"
        assert mime_type("png") == "image/png"
        assert mime_type("gif") == "image/gif"
        assert mime_type("webp") == "image/webp"

    def test_public_url_points_at_the_api_not_the_object_store(self):
        # Keeps MinIO private and lets it move without invalidating stored URLs.
        uid = uuid4()
        url = public_image_url(uid)
        assert url == f"/v1/items/{uid}/image"
        assert "minio" not in url and "9000" not in url
