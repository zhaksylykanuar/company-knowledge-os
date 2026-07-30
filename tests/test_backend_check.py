from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import backend_check


TEST_URL = "postgresql+asyncpg://checker:dummy-password@127.0.0.1:5433/founderos_test"
PRODUCT_URL = "postgresql+asyncpg://founder:product-dummy-password@localhost:5432/founderos"
SAFE_PROXY_URL = "http://127.0.0.1:8888"
CREDENTIALED_PROXY_URL = "http://proxy-user:p@127.0.0.1:8888"
PRODUCT_SECRET_SENTINEL = "product-secret-sentinel"
SETTINGS_PROBE = """
import json
import os

from app.core.config import Settings, settings

print(json.dumps({
    "database_matches_process_env": settings.database_url == os.environ.get("DATABASE_URL"),
    "database_is_product_file": settings.database_url.endswith("/product_database"),
    "dotenv_disabled": Settings.model_config.get("env_file") is None,
    "llm_enabled": settings.enable_llm,
    "provider_credentials_in_runtime_settings": any(
        name in Settings.model_fields
        for name in ("openai_api_key", "github_app_private_key")
    ),
    "real_connectors_enabled": settings.enable_real_connectors,
    "write_actions_enabled": settings.enable_write_actions,
}))
"""


def _write_product_dotenv(root: Path) -> None:
    (root / ".env.local").write_text(
        "\n".join(
            (
                "APP_ENV=production",
                "DATABASE_URL=postgresql+asyncpg://product:dummy@localhost/product_database",
                "ENABLE_LLM=true",
                "ENABLE_WRITE_ACTIONS=true",
                "FOUNDEROS_ENABLE_REAL_CONNECTORS=true",
                f"OPENAI_API_KEY={PRODUCT_SECRET_SENTINEL}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _run_settings_probe(root: Path, environment: dict[str, str]) -> dict[str, bool]:
    repo_root = Path(__file__).resolve().parents[1]
    probe_environment = {**environment, "PYTHONPATH": str(repo_root)}
    completed = subprocess.run(
        [sys.executable, "-c", SETTINGS_PROBE],
        cwd=root,
        env=probe_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert PRODUCT_SECRET_SENTINEL not in completed.stdout
    assert PRODUCT_SECRET_SENTINEL not in completed.stderr
    return json.loads(completed.stdout)


def test_backend_check_requires_explicit_test_database_url(tmp_path: Path) -> None:
    with pytest.raises(backend_check.BackendCheckError, match="is required"):
        backend_check.validated_test_database_url(root=tmp_path, environ={})


def test_pytest_guard_requires_explicit_test_environment(tmp_path: Path) -> None:
    environment = {
        backend_check.TEST_DATABASE_ENV: TEST_URL,
    }

    with pytest.raises(backend_check.BackendCheckError, match=r"APP_ENV=test"):
        backend_check.apply_pytest_database_guard(
            root=tmp_path,
            environ=environment,
        )

    assert "DATABASE_URL" not in environment


def test_pytest_guard_installs_only_the_validated_test_target(tmp_path: Path) -> None:
    environment = {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_URL,
        backend_check.TEST_DATABASE_ENV: TEST_URL,
        "ENABLE_LLM": "true",
        "ENABLE_WRITE_ACTIONS": "true",
        "FOUNDEROS_DISABLE_DOTENV": "false",
        "FOUNDEROS_ENABLE_REAL_CONNECTORS": "true",
    }

    result = backend_check.apply_pytest_database_guard(
        root=tmp_path,
        environ=environment,
    )

    assert result == TEST_URL
    assert environment["DATABASE_URL"] == TEST_URL
    assert environment["APP_ENV"] == "test"
    assert environment["ENABLE_LLM"] == "false"
    assert environment["ENABLE_WRITE_ACTIONS"] == "false"
    assert environment["FOUNDEROS_DISABLE_DOTENV"] == "true"
    assert environment["FOUNDEROS_ENABLE_REAL_CONNECTORS"] == "false"


def test_pytest_guard_rejects_product_dotenv_even_with_ambient_test_alias(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.local").write_text(
        f"DATABASE_URL={TEST_URL}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        backend_check.BackendCheckError,
        match="product database endpoint",
    ):
        backend_check.apply_pytest_database_guard(
            root=tmp_path,
            environ={
                "APP_ENV": "test",
                "DATABASE_URL": TEST_URL,
                backend_check.TEST_DATABASE_ENV: TEST_URL,
            },
        )


def test_bare_pytest_process_fails_before_application_import() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    for key in (
        "APP_ENV",
        "DATABASE_URL",
        backend_check.TEST_DATABASE_ENV,
    ):
        environment.pop(key, None)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/test_backend_check.py",
        ],
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "Unsafe pytest database configuration" in output
    assert "pytest requires APP_ENV=test before application import" in output
    assert "app/db/base.py" not in output


@pytest.mark.parametrize(
    "unsafe_url, expected_message",
    (
        (
            "postgresql+asyncpg://checker:dummy-password@db.example/founderos_test",
            "loopback",
        ),
        (
            "sqlite:///founderos_test.db",
            "PostgreSQL",
        ),
        (
            "postgresql+asyncpg://checker:dummy-password@localhost/founderos",
            "standalone test marker",
        ),
        (
            "postgresql+asyncpg://checker:dummy-password@localhost/founderos_test?host=db.example",
            "only in the URL endpoint",
        ),
        (
            "postgresql://checker:dummy-password@localhost/founderos_test",
            r"postgresql\+asyncpg runtime driver",
        ),
    ),
)
def test_backend_check_rejects_unsafe_test_targets(
    tmp_path: Path,
    unsafe_url: str,
    expected_message: str,
) -> None:
    with pytest.raises(backend_check.BackendCheckError, match=expected_message):
        backend_check.validated_test_database_url(
            root=tmp_path,
            environ={backend_check.TEST_DATABASE_ENV: unsafe_url},
        )


@pytest.mark.parametrize("product_source", ("ambient", ".env", ".env.local"))
def test_backend_check_rejects_product_endpoint_aliases(
    tmp_path: Path,
    product_source: str,
) -> None:
    test_url = "postgresql+asyncpg://checker:test-only-password@localhost:5432/founderos_test"
    product_url = "postgresql://founder:different-password@127.0.0.1/founderos_test"
    environment = {backend_check.TEST_DATABASE_ENV: test_url}
    if product_source == "ambient":
        environment["DATABASE_URL"] = product_url
    else:
        (tmp_path / product_source).write_text(
            f'export DATABASE_URL="{product_url}" # product database\n',
            encoding="utf-8",
        )

    with pytest.raises(backend_check.BackendCheckError) as exc_info:
        backend_check.validated_test_database_url(
            root=tmp_path,
            environ=environment,
        )

    message = str(exc_info.value)
    assert "matches the product database endpoint" in message
    assert test_url not in message
    assert product_url not in message
    assert "test-only-password" not in message
    assert "different-password" not in message


@pytest.mark.parametrize(
    "unsafe_url",
    (
        "postgresql+asyncpg://checker%2Basyncpg:dummy@localhost/founderos_test_target",
        "postgresql+asyncpg://checker:dummy%2Basyncpg@localhost/founderos_test_target",
        "postgresql+asyncpg://checker:dummy@localhost/founderos_test_target%2Basyncpg",
        "postgresql+asyncpg://checker:dummy@localhost/founderos_test_target?label=%2Basyncpg",
    ),
)
def test_backend_check_rejects_asyncpg_marker_outside_driver_scheme(
    tmp_path: Path,
    unsafe_url: str,
) -> None:
    with pytest.raises(
        backend_check.BackendCheckError,
        match="outside the driver scheme",
    ):
        backend_check.validated_test_database_url(
            root=tmp_path,
            environ={backend_check.TEST_DATABASE_ENV: unsafe_url},
        )


def test_backend_check_compares_global_alembic_transformed_product_endpoint(
    tmp_path: Path,
) -> None:
    test_url = "postgresql+asyncpg://checker:dummy@localhost/founderos_test_target+psycopg"
    product_url = "postgresql+asyncpg://founder:other@127.0.0.1/founderos_test_target+asyncpg"

    with pytest.raises(backend_check.BackendCheckError, match="product database endpoint"):
        backend_check.validated_test_database_url(
            root=tmp_path,
            environ={
                backend_check.TEST_DATABASE_ENV: test_url,
                "DATABASE_URL": product_url,
            },
        )


def test_backend_check_runs_exact_gates_in_sanitized_test_environment(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.local").write_text(
        f"DATABASE_URL={PRODUCT_URL}\n",
        encoding="utf-8",
    )
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    ambient = {
        backend_check.TEST_DATABASE_ENV: TEST_URL,
        "APP_ENV": "production",
        "ENABLE_LLM": "true",
        "ENABLE_WRITE_ACTIONS": "true",
        "FOUNDEROS_ENABLE_REAL_CONNECTORS": "true",
        "FOUNDEROS_CORS_ALLOWED_ORIGINS": "https://product.example.test",
        "FOUNDEROS_DISABLE_DOTENV": "false",
        "CORS_ORIGINS": "https://legacy-product.example.test",
        "FOUNDEROS_SECRET_ENCRYPTION_KEY": "ambient-product-secret",
        "GITHUB_TOKEN": "ambient-provider-token",
        "OPENAI_API_KEY": "ambient-provider-key",
        "PATH": "/safe/bin",
        "HOME": "/safe/home",
        "TMPDIR": "/safe/tmp",
        "LC_MONETARY": "en_US.UTF-8",
        "LC_SECRET_TOKEN": "must-not-pass",
        "HTTPS_PROXY": SAFE_PROXY_URL,
        "SSL_CERT_FILE": "/safe/cert.pem",
    }

    result = backend_check.run_backend_check(
        root=tmp_path,
        environ=ambient,
        runner=fake_run,
    )

    assert result == 0
    assert [command for command, _kwargs in calls] == [
        command for _label, command in backend_check.CHECK_COMMANDS
    ]
    for _command, kwargs in calls:
        child_environment = kwargs["env"]
        assert isinstance(child_environment, dict)
        assert child_environment["DATABASE_URL"] == TEST_URL
        assert child_environment["APP_ENV"] == "test"
        assert child_environment["ENABLE_LLM"] == "false"
        assert child_environment["ENABLE_WRITE_ACTIONS"] == "false"
        assert child_environment["FOUNDEROS_ENABLE_REAL_CONNECTORS"] == "false"
        assert child_environment["FOUNDEROS_CORS_ALLOWED_ORIGINS"] == (
            backend_check.TEST_CORS_ALLOWED_ORIGINS
        )
        assert child_environment["FOUNDEROS_DISABLE_DOTENV"] == "true"
        assert "CORS_ORIGINS" not in child_environment
        assert child_environment["UV_NO_SYNC"] == "1"
        assert child_environment[backend_check.TEST_DATABASE_ENV] == TEST_URL
        assert child_environment["PATH"] == "/safe/bin"
        assert child_environment["HOME"] == "/safe/home"
        assert child_environment["TMPDIR"] == "/safe/tmp"
        assert child_environment["LC_MONETARY"] == "en_US.UTF-8"
        assert child_environment["HTTPS_PROXY"] == SAFE_PROXY_URL
        assert child_environment["SSL_CERT_FILE"] == "/safe/cert.pem"
        assert "LC_SECRET_TOKEN" not in child_environment
        assert "FOUNDEROS_SECRET_ENCRYPTION_KEY" not in child_environment
        assert "GITHUB_TOKEN" not in child_environment
        assert "OPENAI_API_KEY" not in child_environment
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True


def test_checker_environment_disables_dotenv_before_settings_import(
    tmp_path: Path,
) -> None:
    _write_product_dotenv(tmp_path)
    checker_environment = backend_check._child_environment(
        environ={
            backend_check.TEST_DATABASE_ENV: TEST_URL,
            "FOUNDEROS_DISABLE_DOTENV": "false",
        },
        test_url=TEST_URL,
    )

    payload = _run_settings_probe(tmp_path, checker_environment)

    assert payload == {
        "database_matches_process_env": True,
        "database_is_product_file": False,
        "dotenv_disabled": True,
        "llm_enabled": False,
        "provider_credentials_in_runtime_settings": False,
        "real_connectors_enabled": False,
        "write_actions_enabled": False,
    }


def test_settings_preserve_normal_dotenv_loading_without_disable_flag(
    tmp_path: Path,
) -> None:
    _write_product_dotenv(tmp_path)

    payload = _run_settings_probe(tmp_path, {})

    assert payload == {
        "database_matches_process_env": False,
        "database_is_product_file": True,
        "dotenv_disabled": False,
        "llm_enabled": True,
        "provider_credentials_in_runtime_settings": False,
        "real_connectors_enabled": True,
        "write_actions_enabled": True,
    }


@pytest.mark.parametrize("proxy_key", ("HTTPS_PROXY", "https_proxy"))
def test_backend_check_rejects_credentialed_proxy_before_any_command(
    tmp_path: Path,
    proxy_key: str,
) -> None:
    called = False

    def unexpected_run(
        _command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        raise AssertionError("runner must not be called")

    with pytest.raises(backend_check.BackendCheckError) as exc_info:
        backend_check.run_backend_check(
            root=tmp_path,
            environ={
                backend_check.TEST_DATABASE_ENV: TEST_URL,
                proxy_key: CREDENTIALED_PROXY_URL,
            },
            runner=unexpected_run,
        )

    message = str(exc_info.value)
    assert proxy_key in message
    assert CREDENTIALED_PROXY_URL not in message
    assert "proxy-user" not in message
    assert called is False


def test_backend_check_redacts_database_url_and_short_query_passwords(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".env.local").write_text(
        f"DATABASE_URL={PRODUCT_URL}\n",
        encoding="utf-8",
    )
    test_url = f"{TEST_URL}?password=%78&sslpassword=y%7A"

    def failing_run(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            7,
            stdout=(
                f"target={test_url} product={PRODUCT_URL} "
                "password=%78 sslpassword=y%7A decoded=x/yz execution=exit\n"
            ),
            stderr=(
                "password=dummy-password product-password=product-dummy-password "
                "short-values: x, yz\n"
            ),
        )

    result = backend_check.run_backend_check(
        root=tmp_path,
        environ={
            backend_check.TEST_DATABASE_ENV: test_url,
        },
        runner=failing_run,
    )
    captured = capsys.readouterr()

    assert result == 7
    assert test_url not in captured.out
    assert test_url not in captured.err
    assert PRODUCT_URL not in captured.out
    assert PRODUCT_URL not in captured.err
    assert "dummy-password" not in captured.out
    assert "dummy-password" not in captured.err
    assert "product-dummy-password" not in captured.out
    assert "product-dummy-password" not in captured.err
    assert "password=%78" not in captured.out
    assert "sslpassword=y%7A" not in captured.out
    assert "decoded=x/yz" not in captured.out
    assert "short-values: x, yz" not in captured.err
    assert "execution=exit" in captured.out
    assert "[redacted]" in captured.out
    assert "[redacted]" in captured.err


def test_make_and_local_docs_require_dedicated_backend_check_database() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    runbook = (root / "docs" / "operations" / "local-runtime.md").read_text(encoding="utf-8")

    assert "python3 scripts/backend_check.py" in makefile
    assert "npm install" not in runbook
    assert "npm ci" in runbook
    for document in (readme, runbook):
        assert backend_check.TEST_DATABASE_ENV in document
        assert "dedicated" in document.casefold()
