import pytest


@pytest.fixture
def anyio_backend() -> str:
    # The service only runs on asyncio; without this, anyio would also run
    # every async test on trio if it were installed.
    return "asyncio"
