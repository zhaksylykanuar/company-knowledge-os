import pytest

from scripts.backend_check import BackendCheckError, apply_pytest_database_guard

try:
    apply_pytest_database_guard()
except BackendCheckError as exc:
    raise pytest.UsageError(f"Unsafe pytest database configuration: {exc}") from exc

from app.core.config import settings
from app.db.base import engine


@pytest.fixture(autouse=True)
def disable_local_api_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", False)
    monkeypatch.setattr(settings, "api_auth_key", None)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


@pytest.fixture(autouse=True)
async def dispose_async_engine_between_tests() -> None:
    yield
    await engine.dispose()
