"""
Unit tests for Phase 3 — Fulfillment service.

No network, no database, no Docker containers required.

Covers:
    - LabelResult dataclass
    - CarrierError exception
    - ManualCarrierAdapter.create_label
    - DhlAdapter: init, _label_format_to_dhl, _build_dhl_payload,
      _extract_label_from_response, create_label
    - build_dhl_adapter factory
    - StorageError exception
    - MinioStorageAdapter: upload, download, ensure_bucket
    - build_minio_adapter factory
    - OutboxStatus enum
    - enqueue_label_job
    - _extract_carrier_args
"""

import base64
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from app.services.admin.functions.order_context import OrderContext
from app.services.fulfillment.adapters.dhl_adapter import (
    DhlAdapter,
    _build_dhl_payload,
    _extract_label_from_response,
    _label_format_to_dhl,
    build_dhl_adapter,
)
from app.services.fulfillment.adapters.interface import (
    CarrierAdapter,
    CarrierError,
    LabelResult,
)
from app.services.fulfillment.adapters.manual_adapter import ManualCarrierAdapter
from app.services.fulfillment.jobs.create_label_job import _extract_carrier_args
from app.services.fulfillment.outbox.models.outbox_db_models import (
    OutboxEventDB,
    OutboxStatus,
)
from app.services.fulfillment.outbox.services.outbox_enqueue import (
    CREATE_LABEL_EVENT,
    enqueue_label_job,
)
from app.shared.exceptions.enums import ErrorCategory, ErrorCode
from app.shared.storage.interface import StorageError
from app.shared.storage.minio_adapter import MinioStorageAdapter, build_minio_adapter


# ---------------------------------------------------------------------------
# Mock factories — reused across multiple test classes
# ---------------------------------------------------------------------------


def _make_order(status: str = "ready_to_ship") -> MagicMock:
    """Return a mock that behaves like an OrderDB row."""
    now = datetime.now(UTC)
    o = MagicMock()
    o.id = uuid4()
    o.customer_id = uuid4()
    o.status = status
    o.total_amount = 4999
    o.currency = "EUR"
    o.created_at = now
    o.updated_at = now
    o.deleted_at = None
    return o


def _make_customer(first_name: str = "Jane", last_name: str = "Doe") -> MagicMock:
    """Return a mock that behaves like a CustomerDB row."""
    now = datetime.now(UTC)
    c = MagicMock()
    c.id = uuid4()
    c.first_name = first_name
    c.last_name = last_name
    c.email = "jane@example.com"
    c.created_at = now
    c.updated_at = now
    return c


def _make_address() -> MagicMock:
    """Return a mock that behaves like an AddressDB row."""
    now = datetime.now(UTC)
    a = MagicMock()
    a.id = uuid4()
    a.street = "Musterstraße 1"
    a.city = "Berlin"
    a.postal_code = "10115"
    a.country_code = "DE"
    a.is_default = True
    a.created_at = now
    a.updated_at = now
    return a


def _make_shipment(carrier: str = "dhl") -> MagicMock:
    """Return a mock that behaves like a ShipmentDB row."""
    now = datetime.now(UTC)
    s = MagicMock()
    s.id = uuid4()
    s.order_id = uuid4()
    s.carrier = carrier
    s.tracking_number = None
    s.label_url = None
    s.label_format = None
    s.status = "pending"
    s.created_at = now
    s.updated_at = now
    return s


def _make_order_context(
    customer=None,
    shipping_address=None,
    shipment=None,
) -> OrderContext:
    """Return an OrderContext with optional overrides."""
    return OrderContext(
        order=_make_order(),
        items=[],
        customer=customer if customer is not None else _make_customer(),
        shipping_address=shipping_address
        if shipping_address is not None
        else _make_address(),
        payment=None,
        shipment=shipment if shipment is not None else _make_shipment(),
    )


def _make_dhl_response(tracking_number: str, label_bytes: bytes) -> dict:
    """Build a minimal DHL POST /orders response dict."""
    return {
        "items": [
            {
                "shipmentTrackingNumber": tracking_number,
                "label": {"b64": base64.b64encode(label_bytes).decode()},
            }
        ]
    }


@pytest.fixture
def dhl_adapter() -> DhlAdapter:
    """DhlAdapter configured with placeholder credentials."""
    return DhlAdapter(
        base_url="https://api-sandbox.dhl.com/parcel/de/shipping/v2",
        client_id="test-client-id",
        client_secret="test-client-secret",
        billing_number="33333333330102",
    )


@pytest.fixture
def minio_adapter() -> MinioStorageAdapter:
    """MinioStorageAdapter configured with placeholder credentials."""
    return MinioStorageAdapter(
        endpoint_url="http://localhost:9000",
        access_key="opentaberna",
        secret_key="opentaberna_secret",
    )


@pytest.fixture
def mock_s3_client() -> AsyncMock:
    """Async mock that behaves like an aiobotocore S3 client."""
    client = AsyncMock()
    client.put_object = AsyncMock(return_value={})
    client.get_object = AsyncMock(
        return_value={"Body": AsyncMock(read=AsyncMock(return_value=b"label-pdf-data"))}
    )
    client.create_bucket = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_aio_session(mock_s3_client: AsyncMock) -> MagicMock:
    """Mock aiobotocore session that yields mock_s3_client from create_client."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_s3_client)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.create_client.return_value = cm
    return session


# ---------------------------------------------------------------------------
# LabelResult dataclass
# ---------------------------------------------------------------------------


class TestLabelResult:
    def test_stores_all_fields(self):
        result = LabelResult(
            tracking_number="DE123456789",
            label_data=b"pdf-bytes",
            label_format="pdf",
        )
        assert result.tracking_number == "DE123456789"
        assert result.label_data == b"pdf-bytes"
        assert result.label_format == "pdf"

    def test_is_immutable(self):
        """frozen=True must prevent field mutation."""
        result = LabelResult(
            tracking_number="DE123", label_data=b"x", label_format="pdf"
        )
        with pytest.raises(Exception):
            result.tracking_number = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CarrierError exception
# ---------------------------------------------------------------------------


class TestCarrierError:
    def test_error_code_is_external_service_error(self):
        exc = CarrierError(message="DHL down")
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR

    def test_category_is_external_service(self):
        exc = CarrierError(message="DHL down")
        assert exc.category == ErrorCategory.EXTERNAL_SERVICE

    def test_message_is_preserved(self):
        exc = CarrierError(message="timeout after 30s")
        assert exc.message == "timeout after 30s"

    def test_context_is_stored(self):
        exc = CarrierError(message="err", context={"carrier": "dhl"})
        assert exc.context["carrier"] == "dhl"

    def test_wraps_original_exception(self):
        cause = ValueError("connection refused")
        exc = CarrierError(message="err", original_exception=cause)
        assert exc.original_exception is cause

    def test_is_server_error(self):
        exc = CarrierError(message="err")
        assert exc.category.is_server_error()


# ---------------------------------------------------------------------------
# ManualCarrierAdapter
# ---------------------------------------------------------------------------


class TestManualCarrierAdapter:
    def test_is_carrier_adapter(self):
        assert isinstance(ManualCarrierAdapter(), CarrierAdapter)

    async def test_create_label_always_raises_carrier_error(self):
        """Manual carrier never supports automated label creation."""
        adapter = ManualCarrierAdapter()
        with pytest.raises(CarrierError):
            await adapter.create_label(
                shipment_id=uuid4(),
                order_id=uuid4(),
                recipient_name="Jane Doe",
                street="Musterstraße 1",
                city="Berlin",
                postal_code="10115",
                country_code="DE",
                weight_kg=1.0,
                label_format="pdf",
            )

    async def test_error_message_references_manual_carrier(self):
        adapter = ManualCarrierAdapter()
        with pytest.raises(CarrierError) as exc_info:
            await adapter.create_label(
                shipment_id=uuid4(),
                order_id=uuid4(),
                recipient_name="X",
                street="X",
                city="X",
                postal_code="X",
                country_code="DE",
                weight_kg=1.0,
                label_format="pdf",
            )
        assert "manual" in exc_info.value.message.lower()

    async def test_error_context_contains_shipment_id(self):
        adapter = ManualCarrierAdapter()
        shipment_id = uuid4()
        with pytest.raises(CarrierError) as exc_info:
            await adapter.create_label(
                shipment_id=shipment_id,
                order_id=uuid4(),
                recipient_name="X",
                street="X",
                city="X",
                postal_code="X",
                country_code="DE",
                weight_kg=1.0,
                label_format="pdf",
            )
        assert str(shipment_id) in exc_info.value.context["shipment_id"]


# ---------------------------------------------------------------------------
# DhlAdapter — initialisation
# ---------------------------------------------------------------------------


class TestDhlAdapterInit:
    def test_is_carrier_adapter(self, dhl_adapter):
        assert isinstance(dhl_adapter, CarrierAdapter)

    def test_auth_header_is_basic_base64(self, dhl_adapter):
        """Authorization header must be Basic <base64(client_id:client_secret)>."""
        expected = base64.b64encode(b"test-client-id:test-client-secret").decode()
        assert dhl_adapter._auth_header == f"Basic {expected}"

    def test_billing_number_is_stored(self, dhl_adapter):
        assert dhl_adapter._billing_number == "33333333330102"

    def test_trailing_slash_stripped_from_base_url(self):
        adapter = DhlAdapter(
            base_url="https://api.dhl.com/v2/",
            client_id="id",
            client_secret="secret",
            billing_number="123",
        )
        assert not adapter._base_url.endswith("/")


# ---------------------------------------------------------------------------
# _label_format_to_dhl helper
# ---------------------------------------------------------------------------


class TestLabelFormatToDhl:
    def test_pdf_maps_to_PDF(self):
        assert _label_format_to_dhl("pdf") == "PDF"

    def test_zpl_maps_to_ZPL2(self):
        assert _label_format_to_dhl("zpl") == "ZPL2"

    def test_is_case_insensitive(self):
        assert _label_format_to_dhl("PDF") == "PDF"
        assert _label_format_to_dhl("ZPL") == "ZPL2"

    def test_unknown_format_raises_carrier_error(self):
        with pytest.raises(CarrierError) as exc_info:
            _label_format_to_dhl("png")
        assert "png" in exc_info.value.message

    def test_error_includes_supported_formats(self):
        with pytest.raises(CarrierError) as exc_info:
            _label_format_to_dhl("gif")
        assert "supported" in exc_info.value.context


# ---------------------------------------------------------------------------
# _build_dhl_payload helper
# ---------------------------------------------------------------------------


class TestBuildDhlPayload:
    def setup_method(self):
        self.billing_number = "33333333330102"
        self.shipment_id = uuid4()
        self.order_id = uuid4()

    def _build(self, **kwargs) -> dict:
        defaults = dict(
            billing_number=self.billing_number,
            shipment_id=self.shipment_id,
            order_id=self.order_id,
            recipient_name="Jane Doe",
            street="Musterstraße 1",
            city="Berlin",
            postal_code="10115",
            country_code="de",
            weight_kg=1.5,
        )
        defaults.update(kwargs)
        return _build_dhl_payload(**defaults)

    def test_has_shipments_key(self):
        payload = self._build()
        assert "shipments" in payload
        assert len(payload["shipments"]) == 1

    def test_product_is_V01PAK(self):
        shipment = self._build()["shipments"][0]
        assert shipment["product"] == "V01PAK"

    def test_billing_number_is_set(self):
        shipment = self._build()["shipments"][0]
        assert shipment["billingNumber"] == self.billing_number

    def test_customer_reference_is_shipment_id(self):
        shipment = self._build()["shipments"][0]
        assert shipment["customerReference"] == str(self.shipment_id)

    def test_customer_reference2_is_order_id(self):
        shipment = self._build()["shipments"][0]
        assert shipment["customerReference2"] == str(self.order_id)

    def test_consignee_name(self):
        consignee = self._build()["shipments"][0]["consignee"]
        assert consignee["name1"] == "Jane Doe"

    def test_consignee_address_fields(self):
        consignee = self._build()["shipments"][0]["consignee"]
        assert consignee["addressStreet"] == "Musterstraße 1"
        assert consignee["postalCode"] == "10115"
        assert consignee["city"] == "Berlin"

    def test_country_code_is_uppercased(self):
        """DHL requires uppercase country code."""
        consignee = self._build(country_code="de")["shipments"][0]["consignee"]
        assert consignee["country"] == "DE"

    def test_weight_uom_is_kg(self):
        details = self._build()["shipments"][0]["details"]
        assert details["weight"]["uom"] == "kg"

    def test_weight_value_is_preserved(self):
        details = self._build(weight_kg=2.3)["shipments"][0]["details"]
        assert details["weight"]["value"] == 2.3


# ---------------------------------------------------------------------------
# _extract_label_from_response helper
# ---------------------------------------------------------------------------


class TestExtractLabelFromResponse:
    def test_happy_path_returns_tracking_and_bytes(self):
        raw_bytes = b"pdf-content"
        response = _make_dhl_response("DE987654321", raw_bytes)
        tracking, label_data = _extract_label_from_response(response, "pdf", uuid4())
        assert tracking == "DE987654321"
        assert label_data == raw_bytes

    def test_empty_items_raises_carrier_error(self):
        with pytest.raises(CarrierError) as exc_info:
            _extract_label_from_response({"items": []}, "pdf", uuid4())
        assert "Unexpected" in exc_info.value.message

    def test_missing_items_key_raises_carrier_error(self):
        with pytest.raises(CarrierError):
            _extract_label_from_response({}, "pdf", uuid4())

    def test_missing_tracking_number_raises_carrier_error(self):
        response = {"items": [{"label": {"b64": base64.b64encode(b"x").decode()}}]}
        with pytest.raises(CarrierError):
            _extract_label_from_response(response, "pdf", uuid4())

    def test_invalid_base64_raises_carrier_error(self):
        response = {
            "items": [
                {
                    "shipmentTrackingNumber": "DE123",
                    "label": {"b64": "!!!not-base64!!!"},
                }
            ]
        }
        with pytest.raises(CarrierError) as exc_info:
            _extract_label_from_response(response, "pdf", uuid4())
        assert "decode" in exc_info.value.message.lower()

    def test_shipment_id_in_error_context(self):
        shipment_id = uuid4()
        with pytest.raises(CarrierError) as exc_info:
            _extract_label_from_response({"items": []}, "pdf", shipment_id)
        assert str(shipment_id) in exc_info.value.context["shipment_id"]


# ---------------------------------------------------------------------------
# DhlAdapter.create_label
# ---------------------------------------------------------------------------


class TestDhlAdapterCreateLabel:
    async def test_happy_path_returns_label_result(self, dhl_adapter):
        """Successful API call returns a LabelResult with tracking number and bytes."""
        raw_bytes = b"pdf-label-content"
        fake_response = _make_dhl_response("DE111222333", raw_bytes)

        with patch(
            "app.services.fulfillment.adapters.dhl_adapter._post_dhl_order",
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            result = await dhl_adapter.create_label(
                shipment_id=uuid4(),
                order_id=uuid4(),
                recipient_name="Jane Doe",
                street="Musterstraße 1",
                city="Berlin",
                postal_code="10115",
                country_code="DE",
                weight_kg=1.0,
                label_format="pdf",
            )

        assert isinstance(result, LabelResult)
        assert result.tracking_number == "DE111222333"
        assert result.label_data == raw_bytes
        assert result.label_format == "pdf"

    async def test_zpl_format_is_preserved(self, dhl_adapter):
        """label_format="zpl" must appear in the returned LabelResult."""
        fake_response = _make_dhl_response("DE999", b"zpl-data")

        with patch(
            "app.services.fulfillment.adapters.dhl_adapter._post_dhl_order",
            new_callable=AsyncMock,
            return_value=fake_response,
        ):
            result = await dhl_adapter.create_label(
                shipment_id=uuid4(),
                order_id=uuid4(),
                recipient_name="X",
                street="X",
                city="X",
                postal_code="X",
                country_code="DE",
                weight_kg=1.0,
                label_format="zpl",
            )

        assert result.label_format == "zpl"

    async def test_unknown_format_raises_before_http_call(self, dhl_adapter):
        """An unsupported label_format must raise CarrierError before any HTTP call."""
        with patch(
            "app.services.fulfillment.adapters.dhl_adapter._post_dhl_order",
            new_callable=AsyncMock,
        ) as mock_post:
            with pytest.raises(CarrierError):
                await dhl_adapter.create_label(
                    shipment_id=uuid4(),
                    order_id=uuid4(),
                    recipient_name="X",
                    street="X",
                    city="X",
                    postal_code="X",
                    country_code="DE",
                    weight_kg=1.0,
                    label_format="bmp",
                )
            mock_post.assert_not_called()

    async def test_dhl_api_error_propagates_carrier_error(self, dhl_adapter):
        """CarrierError raised inside _post_dhl_order must propagate unchanged."""
        with patch(
            "app.services.fulfillment.adapters.dhl_adapter._post_dhl_order",
            new_callable=AsyncMock,
            side_effect=CarrierError(message="DHL returned 500"),
        ):
            with pytest.raises(CarrierError) as exc_info:
                await dhl_adapter.create_label(
                    shipment_id=uuid4(),
                    order_id=uuid4(),
                    recipient_name="X",
                    street="X",
                    city="X",
                    postal_code="X",
                    country_code="DE",
                    weight_kg=1.0,
                    label_format="pdf",
                )
        assert "DHL returned 500" in exc_info.value.message


# ---------------------------------------------------------------------------
# build_dhl_adapter factory
# ---------------------------------------------------------------------------


class TestBuildDhlAdapter:
    def test_returns_dhl_adapter_instance(self):
        adapter = build_dhl_adapter(
            base_url="https://api.dhl.com",
            client_id="id",
            client_secret="secret",
            billing_number="123",
        )
        assert isinstance(adapter, DhlAdapter)
        assert isinstance(adapter, CarrierAdapter)

    def test_billing_number_is_forwarded(self):
        adapter = build_dhl_adapter(
            base_url="https://api.dhl.com",
            client_id="id",
            client_secret="secret",
            billing_number="MYEKP",
        )
        assert adapter._billing_number == "MYEKP"


# ---------------------------------------------------------------------------
# StorageError exception
# ---------------------------------------------------------------------------


class TestStorageError:
    def test_error_code_is_external_service_error(self):
        exc = StorageError(message="bucket unreachable")
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR

    def test_category_is_external_service(self):
        exc = StorageError(message="bucket unreachable")
        assert exc.category == ErrorCategory.EXTERNAL_SERVICE

    def test_message_is_preserved(self):
        exc = StorageError(message="upload failed")
        assert exc.message == "upload failed"

    def test_context_is_stored(self):
        exc = StorageError(message="err", context={"bucket": "labels", "key": "x.pdf"})
        assert exc.context["bucket"] == "labels"

    def test_wraps_original_exception(self):
        cause = RuntimeError("connection reset")
        exc = StorageError(message="err", original_exception=cause)
        assert exc.original_exception is cause


# ---------------------------------------------------------------------------
# MinioStorageAdapter — upload
# ---------------------------------------------------------------------------


class TestMinioStorageAdapterUpload:
    async def test_returns_storage_url(self, minio_adapter, mock_aio_session):
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            url = await minio_adapter.upload(
                bucket="shipping-labels",
                key="labels/abc.pdf",
                data=b"pdf-bytes",
                content_type="application/pdf",
            )

        assert url == "http://localhost:9000/shipping-labels/labels/abc.pdf"

    async def test_calls_put_object_with_correct_args(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            await minio_adapter.upload(
                bucket="shipping-labels",
                key="labels/abc.pdf",
                data=b"pdf-bytes",
                content_type="application/pdf",
            )

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="shipping-labels",
            Key="labels/abc.pdf",
            Body=b"pdf-bytes",
            ContentType="application/pdf",
        )

    async def test_client_error_raises_storage_error(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "bucket gone"}},
            "PutObject",
        )
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            with pytest.raises(StorageError) as exc_info:
                await minio_adapter.upload(
                    bucket="missing-bucket",
                    key="labels/x.pdf",
                    data=b"x",
                    content_type="application/pdf",
                )
        assert "upload" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# MinioStorageAdapter — download
# ---------------------------------------------------------------------------


class TestMinioStorageAdapterDownload:
    async def test_returns_bytes(self, minio_adapter, mock_aio_session):
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            result = await minio_adapter.download(
                bucket="shipping-labels", key="labels/abc.pdf"
            )

        assert result == b"label-pdf-data"

    async def test_calls_get_object_with_correct_args(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            await minio_adapter.download(bucket="shipping-labels", key="labels/abc.pdf")

        mock_s3_client.get_object.assert_called_once_with(
            Bucket="shipping-labels", Key="labels/abc.pdf"
        )

    async def test_client_error_raises_storage_error(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "key not found"}},
            "GetObject",
        )
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            with pytest.raises(StorageError) as exc_info:
                await minio_adapter.download(
                    bucket="shipping-labels", key="labels/missing.pdf"
                )
        assert "download" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# MinioStorageAdapter — ensure_bucket
# ---------------------------------------------------------------------------


class TestMinioStorageAdapterEnsureBucket:
    async def test_calls_create_bucket(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            await minio_adapter.ensure_bucket("shipping-labels")

        mock_s3_client.create_bucket.assert_called_once_with(Bucket="shipping-labels")

    async def test_already_owned_is_silenced(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        """BucketAlreadyOwnedByYou must not raise — ensure_bucket is idempotent."""
        mock_s3_client.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": ""}},
            "CreateBucket",
        )
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            await minio_adapter.ensure_bucket("shipping-labels")  # must not raise

    async def test_bucket_already_exists_is_silenced(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        """BucketAlreadyExists must not raise — ensure_bucket is idempotent."""
        mock_s3_client.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketAlreadyExists", "Message": ""}},
            "CreateBucket",
        )
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            await minio_adapter.ensure_bucket("shipping-labels")  # must not raise

    async def test_other_client_error_raises_storage_error(
        self, minio_adapter, mock_aio_session, mock_s3_client
    ):
        """Unexpected ClientError codes must become StorageError."""
        mock_s3_client.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "forbidden"}},
            "CreateBucket",
        )
        with patch(
            "app.shared.storage.minio_adapter.aiobotocore.session.get_session",
            return_value=mock_aio_session,
        ):
            with pytest.raises(StorageError):
                await minio_adapter.ensure_bucket("forbidden-bucket")


# ---------------------------------------------------------------------------
# build_minio_adapter factory
# ---------------------------------------------------------------------------


class TestBuildMinioAdapter:
    def test_returns_minio_storage_adapter_instance(self):
        adapter = build_minio_adapter(
            endpoint_url="http://localhost:9000",
            access_key="user",
            secret_key="password",
        )
        assert isinstance(adapter, MinioStorageAdapter)

    def test_credentials_are_forwarded(self):
        adapter = build_minio_adapter(
            endpoint_url="http://minio:9000",
            access_key="mykey",
            secret_key="mysecret",
            region="eu-west-1",
        )
        assert adapter._endpoint_url == "http://minio:9000"
        assert adapter._access_key == "mykey"
        assert adapter._secret_key == "mysecret"
        assert adapter._region == "eu-west-1"

    def test_region_defaults_to_us_east_1(self):
        adapter = build_minio_adapter(
            endpoint_url="http://localhost:9000",
            access_key="k",
            secret_key="s",
        )
        assert adapter._region == "us-east-1"


# ---------------------------------------------------------------------------
# OutboxStatus enum
# ---------------------------------------------------------------------------


class TestOutboxStatus:
    def test_pending_value(self):
        assert OutboxStatus.PENDING == "pending"

    def test_enqueued_value(self):
        assert OutboxStatus.ENQUEUED == "enqueued"

    def test_done_value(self):
        assert OutboxStatus.DONE == "done"

    def test_dead_value(self):
        assert OutboxStatus.DEAD == "dead"

    def test_all_four_members_exist(self):
        assert len(OutboxStatus) == 4


# ---------------------------------------------------------------------------
# enqueue_label_job
# ---------------------------------------------------------------------------


class TestEnqueueLabelJob:
    async def test_event_type_is_create_label(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        assert event.event_type == CREATE_LABEL_EVENT

    async def test_status_is_pending(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        assert event.status == OutboxStatus.PENDING.value

    async def test_attempts_is_zero(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        assert event.attempts == 0

    async def test_payload_contains_shipment_id(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        shipment_id = uuid4()

        event = await enqueue_label_job(
            session=session,
            shipment_id=shipment_id,
            order_id=uuid4(),
            label_format="pdf",
        )

        payload = json.loads(event.payload)
        assert payload["shipment_id"] == str(shipment_id)

    async def test_payload_contains_order_id(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        order_id = uuid4()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=order_id,
            label_format="pdf",
        )

        payload = json.loads(event.payload)
        assert payload["order_id"] == str(order_id)

    async def test_payload_contains_label_format(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="zpl",
        )

        payload = json.loads(event.payload)
        assert payload["label_format"] == "zpl"

    async def test_session_add_is_called(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        session.add.assert_called_once_with(event)

    async def test_session_flush_is_called(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        session.flush.assert_called_once()

    async def test_returns_outbox_event_db_instance(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        event = await enqueue_label_job(
            session=session,
            shipment_id=uuid4(),
            order_id=uuid4(),
            label_format="pdf",
        )

        assert isinstance(event, OutboxEventDB)


# ---------------------------------------------------------------------------
# _extract_carrier_args
# ---------------------------------------------------------------------------


class TestExtractCarrierArgs:
    def test_happy_path_returns_all_fields(self):
        customer = _make_customer("Ada", "Lovelace")
        address = _make_address()
        address.street = "Unter den Linden 1"
        address.city = "Berlin"
        address.postal_code = "10117"
        address.country_code = "DE"
        shipment = _make_shipment(carrier="dhl")
        ctx = _make_order_context(
            customer=customer, shipping_address=address, shipment=shipment
        )

        args = _extract_carrier_args(ctx, shipment.id)

        assert args["carrier"] == "dhl"
        assert args["recipient_name"] == "Ada Lovelace"
        assert args["street"] == "Unter den Linden 1"
        assert args["city"] == "Berlin"
        assert args["postal_code"] == "10117"
        assert args["country_code"] == "DE"

    def test_recipient_name_is_first_space_last(self):
        customer = _make_customer("Hans", "Müller")
        ctx = _make_order_context(customer=customer)

        args = _extract_carrier_args(ctx, uuid4())

        assert args["recipient_name"] == "Hans Müller"

    def test_weight_kg_is_provided(self):
        ctx = _make_order_context()
        args = _extract_carrier_args(ctx, uuid4())
        assert "weight_kg" in args
        assert args["weight_kg"] > 0

    def test_missing_customer_raises_carrier_error(self):
        ctx = OrderContext(
            order=_make_order(),
            items=[],
            customer=None,
            shipping_address=_make_address(),
            payment=None,
            shipment=_make_shipment(),
        )
        with pytest.raises(CarrierError) as exc_info:
            _extract_carrier_args(ctx, uuid4())
        assert (
            "customer" in exc_info.value.message.lower()
            or "address" in exc_info.value.message.lower()
        )

    def test_missing_address_raises_carrier_error(self):
        ctx = OrderContext(
            order=_make_order(),
            items=[],
            customer=_make_customer(),
            shipping_address=None,
            payment=None,
            shipment=_make_shipment(),
        )
        with pytest.raises(CarrierError):
            _extract_carrier_args(ctx, uuid4())

    def test_carrier_value_comes_from_shipment(self):
        shipment = _make_shipment(carrier="dhl")
        ctx = _make_order_context(shipment=shipment)
        args = _extract_carrier_args(ctx, shipment.id)
        assert args["carrier"] == "dhl"
