import pytest

from app.db.base import engine


@pytest.fixture(autouse=True)
async def dispose_async_engine_between_tests() -> None:
    yield
    await engine.dispose()
