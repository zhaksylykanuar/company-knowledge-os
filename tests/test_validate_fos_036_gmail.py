import asyncio
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from pydantic import SecretStr


def _load_runner() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_fos_036_gmail.py"
    spec = importlib.util.spec_from_file_location("validate_fos_036_gmail", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class FakeSettings:
    api_auth_enabled: bool = True
    api_auth_key: SecretStr | str | None = SecretStr("PRIVATE_AUTH_VALUE")
    api_auth_header_name: str = "X-PRIVATE-HEADER"
    google_gmail_backfill_enabled: bool = True
    google_gmail_backfill_query: str | None = "PRIVATE_GMAIL_QUERY"
    api_base_url: str = "http://localhost:8000"
    raw_storage_dir: str = "unused"


async def _matching_counts(config: FakeSettings) -> dict:
    runner = _load_runner()
    return {
        "db_status": "ok",
        "counts": {
            **runner.EXPECTED_GMAIL_COUNTS,
            "gmail_ingested_events": 3,
        },
    }


async def _mismatched_counts(config: FakeSettings) -> dict:
    result = await _matching_counts(config)
    result["counts"]["gmail_chunks"] = 21
    return result


def _fail_request(config: FakeSettings) -> dict:
    raise AssertionError("network sender must not be called")


def test_readiness_mode_does_not_make_network_call() -> None:
    runner = _load_runner()

    result = asyncio.run(
        runner.run_validation(
            live=False,
            config=FakeSettings(),
            count_reader=_matching_counts,
            request_sender=_fail_request,
        )
    )

    assert result["request_attempted"] is False
    assert result["validation_result"] == "ready_for_live"


def test_live_mode_missing_config_aborts_before_network() -> None:
    runner = _load_runner()
    config = FakeSettings(
        api_auth_enabled=False,
        api_auth_key=None,
        google_gmail_backfill_enabled=False,
        google_gmail_backfill_query=None,
    )

    result = asyncio.run(
        runner.run_validation(
            live=True,
            config=config,
            count_reader=_matching_counts,
            request_sender=_fail_request,
        )
    )

    assert result["request_attempted"] is False
    assert result["validation_result"] == "blocked_missing_config"
    assert "API_AUTH_KEY" in result["missing_config_keys"]
    assert "GOOGLE_GMAIL_BACKFILL_QUERY" in result["missing_config_keys"]


def test_live_mode_baseline_mismatch_aborts_before_network() -> None:
    runner = _load_runner()

    result = asyncio.run(
        runner.run_validation(
            live=True,
            config=FakeSettings(),
            count_reader=_mismatched_counts,
            request_sender=_fail_request,
        )
    )

    assert result["request_attempted"] is False
    assert result["validation_result"] == "blocked_baseline_mismatch"


def test_safe_output_does_not_expose_secret_or_config_values() -> None:
    runner = _load_runner()

    result = asyncio.run(
        runner.run_validation(
            live=False,
            config=FakeSettings(),
            count_reader=_matching_counts,
            request_sender=_fail_request,
        )
    )
    payload = json.dumps(result, sort_keys=True)

    assert "PRIVATE_AUTH_VALUE" not in payload
    assert "X-PRIVATE-HEADER" not in payload
    assert "PRIVATE_GMAIL_QUERY" not in payload


def test_request_runtime_error_returns_safe_metadata(monkeypatch) -> None:
    runner = _load_runner()

    def fail_urlopen(*args: object, **kwargs: object) -> object:
        raise RuntimeError("PRIVATE_AUTH_VALUE")

    monkeypatch.setattr(runner, "urlopen", fail_urlopen)

    result = runner.send_gmail_validation_request(FakeSettings())
    payload = json.dumps(result, sort_keys=True)

    assert result == {
        "request_attempted": True,
        "http_status": None,
        "avoided_http_500": None,
        "transport_error": True,
    }
    assert "PRIVATE_AUTH_VALUE" not in payload
