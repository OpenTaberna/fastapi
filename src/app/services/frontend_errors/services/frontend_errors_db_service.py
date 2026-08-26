"""
Frontend Error Database Service

Writing browser error reports, and reading them back grouped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.logger import get_logger

from ..models import FrontendErrorDB, FrontendErrorInput

logger = get_logger(__name__)

# Same reasoning as storefront events: a browser clock can be wrong, but it must
# not be able to write into a period already reviewed.
MAX_CLOCK_SKEW = timedelta(hours=24)


class FrontendErrorRepository:
    """Persistence for browser error reports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, errors: list[FrontendErrorInput], browser: str
    ) -> tuple[int, int]:
        """Store a batch, discarding implausible timestamps. Returns (accepted, rejected)."""
        now = datetime.now(UTC)
        earliest, latest = now - MAX_CLOCK_SKEW, now + MAX_CLOCK_SKEW

        rows: list[FrontendErrorDB] = []
        rejected = 0

        for error in errors:
            occurred = error.occurred_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            if not (earliest <= occurred <= latest):
                rejected += 1
                continue

            rows.append(
                FrontendErrorDB(
                    app=error.app.value,
                    name=error.name,
                    message=error.message,
                    stack=error.stack,
                    path=error.path,
                    browser=browser,
                    occurred_at=occurred,
                )
            )

        if rows:
            self._session.add_all(rows)
            await self._session.commit()

        return len(rows), rejected

    async def grouped(
        self, start: datetime, end: datetime, app: str | None, limit: int
    ) -> list[dict]:
        """
        Distinct errors with counts, ordered by how often they happen.

        Grouped by (app, name, message) rather than by stack: the same fault
        reached from two routes produces two stacks and is one bug.
        """
        conditions = [
            FrontendErrorDB.occurred_at >= start,
            FrontendErrorDB.occurred_at < end,
        ]
        if app:
            conditions.append(FrontendErrorDB.app == app)

        statement: Select = (
            select(
                FrontendErrorDB.app,
                FrontendErrorDB.name,
                FrontendErrorDB.message,
                func.count(FrontendErrorDB.id).label("occurrences"),
                func.count(distinct(FrontendErrorDB.path)).label("affected_paths"),
                func.array_agg(distinct(FrontendErrorDB.browser)).label("browsers"),
                func.min(FrontendErrorDB.occurred_at).label("first_seen"),
                func.max(FrontendErrorDB.occurred_at).label("last_seen"),
                # Any one stack is representative; they differ only by frame
                # addresses within a group.
                func.min(FrontendErrorDB.stack).label("sample_stack"),
            )
            .where(and_(*conditions))
            .group_by(
                FrontendErrorDB.app, FrontendErrorDB.name, FrontendErrorDB.message
            )
            .order_by(func.count(FrontendErrorDB.id).desc())
            .limit(limit)
        )

        result = await self._session.execute(statement)
        return [
            {
                "app": row.app,
                "name": row.name,
                "message": row.message,
                "occurrences": int(row.occurrences),
                "affected_paths": int(row.affected_paths),
                "browsers": sorted(b for b in (row.browsers or []) if b),
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "sample_stack": row.sample_stack,
            }
            for row in result
        ]

    async def total(self, start: datetime, end: datetime, app: str | None) -> int:
        conditions = [
            FrontendErrorDB.occurred_at >= start,
            FrontendErrorDB.occurred_at < end,
        ]
        if app:
            conditions.append(FrontendErrorDB.app == app)
        result = await self._session.execute(
            select(func.count(FrontendErrorDB.id)).where(and_(*conditions))
        )
        return int(result.scalar_one_or_none() or 0)


def get_frontend_error_repository(session: AsyncSession) -> FrontendErrorRepository:
    return FrontendErrorRepository(session)
