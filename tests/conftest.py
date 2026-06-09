import pytest

from app.db.base import engine
from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_local_api_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", False)
    monkeypatch.setattr(settings, "api_auth_key", None)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


@pytest.fixture(autouse=True)
async def dispose_async_engine_between_tests() -> None:
    yield
    await engine.dispose()
