from pathlib import Path

import pytest

from app.config import Settings


def test_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.cache_ttl_seconds == 60.0
    assert settings.fetch_timeout_seconds == 5.0
    assert settings.db_path == Path("usage.db")


def test_env_vars_override_defaults() -> None:
    settings = Settings.from_env(
        {
            "HN_CACHE_TTL_SECONDS": "90",
            "HN_FETCH_TIMEOUT_SECONDS": "2.5",
            "HN_DB_PATH": "/tmp/other.db",
        }
    )
    assert settings.cache_ttl_seconds == 90.0
    assert settings.fetch_timeout_seconds == 2.5
    assert settings.db_path == Path("/tmp/other.db")


def test_ttl_floor_is_inclusive() -> None:
    assert Settings.from_env({"HN_CACHE_TTL_SECONDS": "30"}).cache_ttl_seconds == 30


def test_ttl_below_floor_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 30"):
        Settings.from_env({"HN_CACHE_TTL_SECONDS": "29.9"})


def test_ttl_floor_applies_to_direct_construction() -> None:
    with pytest.raises(ValueError, match="at least 30"):
        Settings(cache_ttl_seconds=10)
