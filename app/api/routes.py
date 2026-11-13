"""HTTP endpoints."""

from fastapi import APIRouter, HTTPException

from app.api.schemas import EntriesResponse, EntryPublic
from app.cache import CacheStatus, NoDataError, SnapshotCache
from app.filters import Filter, apply_filter


def create_router(cache: SnapshotCache) -> APIRouter:
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
        try:
            result = await cache.get()
        except NoDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        snapshot = result.snapshot
        return EntriesResponse(
            fetched_at=snapshot.fetched_at,
            stale=result.status is CacheStatus.STALE,
            complete=snapshot.complete,
            entries=[
                EntryPublic.model_validate(entry)
                for entry in apply_filter(snapshot.entries, filter)
            ],
        )

    return router
