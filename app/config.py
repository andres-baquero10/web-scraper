"""Service settings, read from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# HN's robots.txt asks crawlers to wait 30 seconds between requests.
MIN_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class Settings:
    cache_ttl_seconds: float = 60.0
    fetch_timeout_seconds: float = 5.0
    db_path: Path = Path("usage.db")

    def __post_init__(self) -> None:

        if self.cache_ttl_seconds < MIN_CACHE_TTL_SECONDS:
            raise ValueError(
                f"cache TTL must be at least {MIN_CACHE_TTL_SECONDS:g}s "
                f"(HN's crawl delay), got {self.cache_ttl_seconds:g}s"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Build settings from env vars; unset vars keep the default."""
        return cls(
            cache_ttl_seconds=float(
                env.get("HN_CACHE_TTL_SECONDS", cls.cache_ttl_seconds)
            ),
            fetch_timeout_seconds=float(
                env.get("HN_FETCH_TIMEOUT_SECONDS", cls.fetch_timeout_seconds)
            ),
            db_path=Path(env.get("HN_DB_PATH", cls.db_path)),
        )
