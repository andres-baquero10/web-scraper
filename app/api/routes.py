"""HTTP endpoints."""

import asyncio
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import EntriesResponse, EntryPublic, UsageRecordPublic
from app.cache import CacheStatus, Clock, NoDataError, SnapshotCache
from app.filters import Filter, apply_filter
from app.usage import UsageCacheStatus, UsageRecord, UsageRepository


async def _record_usage(
    usage: UsageRepository,
    *,
    requested_at: datetime,
    started: float,
    filter: Filter,
    result_count: int,
    cache_status: UsageCacheStatus,
    data_fetched_at: datetime | None,
    status_code: int,
    error: str | None = None,
) -> None:
    """Save one /entries request; ``started`` is a ``time.perf_counter()`` value."""
    rec = UsageRecord(
        requested_at=requested_at,
        filter=filter,
        result_count=result_count,
        cache_status=cache_status,
        data_fetched_at=data_fetched_at,
        # Microsecond resolution: cache hits take well under 1 ms.
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        status_code=status_code,
        error=error,
    )
    # Off the event loop: a locked database slows this request only.
    # record() never raises, so usage tracking can't fail the request.
    await asyncio.to_thread(usage.record, rec)


def create_router(
    cache: SnapshotCache, usage: UsageRepository, clock: Clock
) -> APIRouter:
    """Build the API routes around the given collaborators."""
    router = APIRouter()

    @router.get(
        "/entries",
        response_model=EntriesResponse,
        responses={
            503: {"description": "Hacker News is unavailable and nothing is cached"}
        },
    )
    async def get_entries(filter: Filter = Filter.ALL) -> EntriesResponse:
        """Front-page entries, filtered and ordered by ``filter``."""
        requested_at = clock()
        started = time.perf_counter()

        try:
            result = await cache.get()
        except NoDataError as exc:
            await _record_usage(
                usage,
                requested_at=requested_at,
                started=started,
                filter=filter,
                result_count=0,
                cache_status=UsageCacheStatus.EMPTY,
                data_fetched_at=None,
                status_code=503,
                error=str(exc),
            )
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        snapshot = result.snapshot
        entries = apply_filter(snapshot.entries, filter)
        await _record_usage(
            usage,
            requested_at=requested_at,
            started=started,
            filter=filter,
            result_count=len(entries),
            cache_status=UsageCacheStatus(result.status.value),
            data_fetched_at=snapshot.fetched_at,
            status_code=200,
        )
        return EntriesResponse(
            fetched_at=snapshot.fetched_at,
            stale=result.status is CacheStatus.STALE,
            complete=snapshot.complete,
            entries=[EntryPublic.model_validate(entry) for entry in entries],
        )

    @router.get("/usage", response_model=list[UsageRecordPublic])
    def get_usage(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[UsageRecordPublic]:
        """Usage records for /entries requests, newest first."""
        return [
            UsageRecordPublic.model_validate(rec)
            for rec in usage.recent(limit=limit, offset=offset)
        ]

    return router
