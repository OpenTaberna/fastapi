"""
Storefront Analytics Database Service

Writing anonymous events, and reading the browse portion of the funnel back out.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.logger import get_logger

from ..models import StorefrontEventDB, StorefrontEventInput, StorefrontEventType

logger = get_logger(__name__)

# How far out of step with the server a browser's clock may be before its
# events are discarded. Client clocks are wrong often enough that rejecting all
# skew would lose real data, and trusting all of it would let anyone write to
# any point in history — including into a period an administrator has already
# reported on.
MAX_CLOCK_SKEW = timedelta(hours=24)


class StorefrontEventRepository:
    """Persistence for storefront events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, events: list[StorefrontEventInput]) -> tuple[int, int]:
        """
        Store a batch, discarding events whose timestamp is not plausible.

        Returns:
            (accepted, rejected)
        """
        now = datetime.now(UTC)
        earliest = now - MAX_CLOCK_SKEW
        latest = now + MAX_CLOCK_SKEW

        rows: list[StorefrontEventDB] = []
        rejected = 0

        for event in events:
            occurred = event.occurred_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)

            if not (earliest <= occurred <= latest):
                rejected += 1
                continue

            rows.append(
                StorefrontEventDB(
                    session_id=event.session_id,
                    event_type=event.event_type.value,
                    path=event.path,
                    sku=event.sku,
                    order_id=event.order_id,
                    occurred_at=occurred,
                )
            )

        if rows:
            self._session.add_all(rows)
            await self._session.commit()

        if rejected:
            logger.info(
                "Discarded storefront events with implausible timestamps",
                extra={"rejected": rejected, "accepted": len(rows)},
            )

        return len(rows), rejected

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @staticmethod
    def _in_period(start: datetime, end: datetime):
        return and_(
            StorefrontEventDB.occurred_at >= start,
            StorefrontEventDB.occurred_at < end,
        )

    async def _sessions_with(
        self, start: datetime, end: datetime, event_type: StorefrontEventType | None
    ) -> int:
        """Distinct sessions that produced at least one event of this type."""
        statement: Select = select(
            func.count(distinct(StorefrontEventDB.session_id))
        ).where(self._in_period(start, end))
        if event_type is not None:
            statement = statement.where(
                StorefrontEventDB.event_type == event_type.value
            )
        result = await self._session.execute(statement)
        return int(result.scalar_one_or_none() or 0)

    async def browse_funnel(self, start: datetime, end: datetime) -> dict[str, int]:
        """
        Session counts at each pre-order step.

        Counted by distinct session rather than by event: ten product views from
        one shopper is one person considering a purchase, not ten.
        """
        return {
            "sessions": await self._sessions_with(start, end, None),
            "viewed_product": await self._sessions_with(
                start, end, StorefrontEventType.PRODUCT_VIEW
            ),
            "added_to_cart": await self._sessions_with(
                start, end, StorefrontEventType.ADD_TO_CART
            ),
            "started_checkout": await self._sessions_with(
                start, end, StorefrontEventType.CHECKOUT_STARTED
            ),
        }

    async def page_views(self, start: datetime, end: datetime) -> int:
        result = await self._session.execute(
            select(func.count(StorefrontEventDB.id)).where(
                self._in_period(start, end),
                StorefrontEventDB.event_type == StorefrontEventType.PAGE_VIEW.value,
            )
        )
        return int(result.scalar_one_or_none() or 0)

    async def top_paths(
        self, start: datetime, end: datetime, limit: int = 10
    ) -> list[dict]:
        """Most-viewed routes, with how many distinct sessions saw each."""
        statement: Select = (
            select(
                StorefrontEventDB.path,
                func.count(StorefrontEventDB.id).label("views"),
                func.count(distinct(StorefrontEventDB.session_id)).label("sessions"),
            )
            .where(
                self._in_period(start, end),
                StorefrontEventDB.event_type == StorefrontEventType.PAGE_VIEW.value,
                StorefrontEventDB.path.is_not(None),
            )
            .group_by(StorefrontEventDB.path)
            .order_by(func.count(StorefrontEventDB.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [
            {"path": row.path, "views": int(row.views), "sessions": int(row.sessions)}
            for row in result
        ]

    async def product_interest(
        self, start: datetime, end: datetime, limit: int = 10
    ) -> list[dict]:
        """
        Views and cart adds per SKU, and the ratio between them.

        A product viewed often and added rarely is the interesting case: the
        listing attracts people and something about the page, price or stock
        turns them away. That is invisible in sales figures, which only ever
        show what did sell.
        """
        views = func.count(distinct(StorefrontEventDB.session_id)).filter(
            StorefrontEventDB.event_type == StorefrontEventType.PRODUCT_VIEW.value
        )
        adds = func.count(distinct(StorefrontEventDB.session_id)).filter(
            StorefrontEventDB.event_type == StorefrontEventType.ADD_TO_CART.value
        )

        statement: Select = (
            select(
                StorefrontEventDB.sku,
                views.label("sessions_viewed"),
                adds.label("sessions_added"),
            )
            .where(self._in_period(start, end), StorefrontEventDB.sku.is_not(None))
            .group_by(StorefrontEventDB.sku)
            .order_by(views.desc())
            .limit(limit)
        )

        result = await self._session.execute(statement)
        rows = []
        for row in result:
            viewed = int(row.sessions_viewed or 0)
            added = int(row.sessions_added or 0)
            rows.append(
                {
                    "sku": row.sku,
                    "sessions_viewed": viewed,
                    "sessions_added": added,
                    "add_to_cart_rate": round(added / viewed, 4) if viewed else None,
                }
            )
        return rows

    async def checkout_order_ids(self, start: datetime, end: datetime) -> list:
        """Orders that a browser reported starting checkout for."""
        result = await self._session.execute(
            select(distinct(StorefrontEventDB.order_id)).where(
                self._in_period(start, end),
                StorefrontEventDB.event_type
                == StorefrontEventType.CHECKOUT_STARTED.value,
                StorefrontEventDB.order_id.is_not(None),
            )
        )
        return [row[0] for row in result]


def get_storefront_event_repository(session: AsyncSession) -> StorefrontEventRepository:
    return StorefrontEventRepository(session)
