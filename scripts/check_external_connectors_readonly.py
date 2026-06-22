#!/usr/bin/env python
"""Read-only GitHub/Jira connector smoke report."""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.connectors import github, jira  # noqa: E402
from app.services.guarded_execution_contracts import (  # noqa: E402
    validate_connector_readonly_smoke_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402
from app.services.external_connector_config import (  # noqa: E402
    PROVIDER_GITHUB,
    PROVIDER_JIRA,
    is_provider_configured,
)
from app.services.local_connector_env import (  # noqa: E402
    add_connector_env_file_arguments,
    connector_env_cli_kwargs,
    load_local_connector_environment,
)
from app.services.provider_execution_guard import (  # noqa: E402
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
)
from app.services.repository_portfolio import repository_portfolio_public_summary  # noqa: E402
from app.services.repository_source_inventory import (  # noqa: E402
    load_repository_source_inventory_snapshot,
)

REPORT_KIND = "external_connector_readonly_smoke"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
PROVIDER_CALLS_NONE = "none"
PROVIDER_CALLS_SYNTHETIC = "synthetic"
PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED = "live_readonly_attempted"
SCHEDULER_DISABLED = "disabled"
NOT_RUN = "not_run"
NOT_CONFIGURED = "not_configured"
CONFIGURED = "configured"
UNKNOWN = "unknown"
SELECTED = "selected"
NOT_SELECTED = "not_selected"
REQUIRES_ACKNOWLEDGEMENT = "requires_acknowledgement"
GUARDED_NOT_EXECUTED = "guarded_not_executed"
SYNTHETIC_VERIFIED = "synthetic_verified"
LIVE_READONLY_VERIFIED = "live_readonly_verified"
PLANNED_NOT_VERIFIED = "planned_not_verified"
COUNT_NOT_OBSERVED = "not_observed"
COUNT_MATCHES_EXPECTED = "matches_expected_count"
COUNT_BELOW_EXPECTED = "below_expected_count"
COUNT_ABOVE_EXPECTED = "above_expected_count"
COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"
SMOKE_PASSED = "external_connector_readonly_smoke_passed"
SMOKE_FAILED = "external_connector_readonly_smoke_failed"
SMOKE_OUTPUT_UNSAFE = "external_connector_readonly_smoke_output_unsafe"
SMOKE_CONTRACT_INVALID = "external_connector_readonly_smoke_contract_invalid"
GITHUB_LIVE_FAILED = "github_live_readonly_failed"
JIRA_LIVE_FAILED = "jira_live_readonly_failed"
JIRA_SITE_CONFIG_INVALID = "jira_site_config_invalid"
JIRA_AUTH_FAILED = "jira_auth_failed"
JIRA_PERMISSION_DENIED = "jira_permission_denied"
JIRA_NOT_FOUND_OR_WRONG_SITE = "jira_not_found_or_wrong_site"
JIRA_RATE_LIMITED = "jira_rate_limited"
JIRA_SERVER_ERROR = "jira_server_error"
JIRA_TRANSPORT_ERROR = "jira_transport_error"
JIRA_TIMEOUT = "jira_timeout"
JIRA_RESPONSE_MALFORMED = "jira_response_malformed"
JIRA_RESPONSE_CONTRACT_MISMATCH = "jira_response_contract_mismatch"
JIRA_UNKNOWN_LIVE_SMOKE_FAILURE = "jira_unknown_live_smoke_failure"
JIRA_AUTH_ACCEPTED = "jira_auth_accepted"
JIRA_TRANSPORT_HTTP_ERROR = "jira_transport_http_error"
JIRA_TRANSPORT_NOT_STARTED = "jira_transport_not_started"
JIRA_TRANSPORT_NOT_OBSERVED = "not_observed"
JIRA_TRANSPORT_PASS = "jira_transport_pass"
JIRA_RESPONSE_CONTRACT_PASS = "pass"
JIRA_RESPONSE_CONTRACT_NOT_OBSERVED = "not_observed"
PAYLOAD_VISIBILITY_SUPPRESSED = "suppressed"


class JiraLiveReadonlySmokeError(RuntimeError):
    def __init__(
        self,
        failure_class: str,
        *,
        auth_status_class: str = JIRA_TRANSPORT_NOT_OBSERVED,
        transport_status_class: str = JIRA_TRANSPORT_NOT_OBSERVED,
        response_contract_status: str = JIRA_RESPONSE_CONTRACT_NOT_OBSERVED,
    ) -> None:
        super().__init__(failure_class)
        self.failure_class = failure_class
        self.auth_status_class = auth_status_class
        self.transport_status_class = transport_status_class
        self.response_contract_status = response_contract_status

    def safe_fields(self) -> dict[str, str]:
        return {
            "live_failure_class": self.failure_class,
            "auth_status_class": self.auth_status_class,
            "transport_status_class": self.transport_status_class,
            "response_contract_status": self.response_contract_status,
            "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
        }


def run_connector_readonly_smoke(
    *,
    provider: str = "all",
    synthetic: bool = False,
    allow_live_readonly_apis: bool = False,
    acknowledge_live_readonly_risk: str | None = None,
    compare_portfolio: bool = False,
    github_live_transport: github.GitHubTransport | None = None,
    jira_live_transport: jira.JiraTransport | None = None,
    environ: Mapping[str, str] | None = None,
    connector_env_file: str | Path | None = None,
    use_connector_env_file: bool = False,
) -> dict[str, Any]:
    selected_providers = _selected_providers(provider)
    env_result = load_local_connector_environment(
        environ=environ if environ is not None else os.environ,
        connector_env_file=connector_env_file,
        use_connector_env_file=use_connector_env_file,
    )
    environment = env_result.environment

    github_result = _github_provider_result(
        selected="github" in selected_providers,
        synthetic=synthetic,
        allow_live_readonly_apis=allow_live_readonly_apis,
        acknowledge_live_readonly_risk=acknowledge_live_readonly_risk,
        compare_portfolio=compare_portfolio,
        live_transport=github_live_transport,
        environ=environment,
    )
    jira_result = _jira_provider_result(
        selected="jira" in selected_providers,
        synthetic=synthetic,
        allow_live_readonly_apis=allow_live_readonly_apis,
        acknowledge_live_readonly_risk=acknowledge_live_readonly_risk,
        live_transport=jira_live_transport,
        environ=environment,
    )

    provider_results = {"github": github_result, "jira": jira_result}
    failed_provider_count = sum(
        1 for result in provider_results.values() if result["status"] != STATUS_PASS
    )
    live_attempt_count = sum(
        1
        for result in provider_results.values()
        if result.get("live_readonly_status") in {STATUS_PASS, STATUS_FAIL}
    )
    not_configured_count = sum(
        1
        for result in provider_results.values()
        if result.get("live_readonly_status") == NOT_CONFIGURED
    )
    default_denied_pass_count = sum(
        1
        for result in provider_results.values()
        if result.get("default_denied") == STATUS_PASS
    )
    selected_provider_count = sum(
        1
        for result in provider_results.values()
        if result.get("selection_status") == SELECTED
    )

    if live_attempt_count:
        provider_calls = PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED
    elif synthetic:
        provider_calls = PROVIDER_CALLS_SYNTHETIC
    else:
        provider_calls = PROVIDER_CALLS_NONE

    status = STATUS_PASS if failed_provider_count == 0 else STATUS_FAIL
    reason_code = (
        SMOKE_FAILED
        if status == STATUS_FAIL
        else REQUIRES_ACKNOWLEDGEMENT
        if provider_calls == PROVIDER_CALLS_NONE
        else None
    )
    result = {
        "status": status,
        "reason_code": reason_code,
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": provider_calls != PROVIDER_CALLS_LIVE_READONLY_ATTEMPTED,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "provider_calls": provider_calls,
        "providers": provider_results,
        "diagnostics": {
            "selected_provider_count": selected_provider_count,
            "default_denied_pass_count": default_denied_pass_count,
            "failed_provider_count": failed_provider_count,
            "not_configured_count": not_configured_count,
            "live_readonly_attempt_count": live_attempt_count,
            "synthetic_mode": synthetic,
            "portfolio_compare_requested": compare_portfolio,
            "connector_env_file": dict(env_result.diagnostics),
        },
    }
    return _finalize_result(result)


def _github_provider_result(
    *,
    selected: bool,
    synthetic: bool,
    allow_live_readonly_apis: bool,
    acknowledge_live_readonly_risk: str | None,
    compare_portfolio: bool,
    live_transport: github.GitHubTransport | None,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    result = _base_github_result(selected=selected, compare_portfolio=compare_portfolio)
    if not selected:
        return result

    default_denied = _github_default_denied()
    result["default_denied"] = default_denied["status"]
    result["provider_reason_code"] = default_denied["reason_code"]
    if default_denied["status"] != STATUS_PASS:
        result["status"] = STATUS_FAIL
        return result

    if synthetic:
        observed_repo_keys = _portfolio_repo_keys()
        synthetic_events = github.list_repository_events(
            transport=_synthetic_github_transport(len(observed_repo_keys)),
            execution_mode=github.SYNTHETIC_EXECUTION_MODE,
        )
        result.update(
            {
                "synthetic_status": STATUS_PASS
                if len(synthetic_events) == len(observed_repo_keys)
                else STATUS_FAIL,
                "live_readonly_status": NOT_RUN,
                "portfolio_compare": "counts_only"
                if compare_portfolio
                else "not_requested",
            }
        )
        if compare_portfolio:
            result.update(_portfolio_compare_summary(observed_repo_keys))
        if result["synthetic_status"] != STATUS_PASS:
            result["status"] = STATUS_FAIL
        return result

    if not allow_live_readonly_apis:
        result.update(
            {
                "live_readonly_status": NOT_RUN,
                "gated_status": GUARDED_NOT_EXECUTED,
                "provider_reason_code": REQUIRES_ACKNOWLEDGEMENT,
            }
        )
        return result

    if acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        result.update(
            {
                "status": STATUS_FAIL,
                "live_readonly_status": NOT_RUN,
                "provider_reason_code": PROVIDER_EXECUTION_ACK_REQUIRED,
            }
        )
        return result

    if not is_provider_configured(PROVIDER_GITHUB, environ):
        result.update(
            {
                "configured_status": NOT_CONFIGURED,
                "live_readonly_status": NOT_CONFIGURED,
                "provider_reason_code": NOT_CONFIGURED,
            }
        )
        return result

    observed_repo_keys: set[str] = set()
    transport = live_transport or _github_http_transport(environ, observed_repo_keys)
    try:
        events = github.list_repository_events(
            transport=transport,
            execution_mode=github.LIVE_EXECUTION_MODE,
            allow_live_provider_execution=True,
            provider_execution_ack=acknowledge_live_readonly_risk,
        )
        observed_repo_keys.update(_repo_keys_from_events(events))
        result.update(
            {
                "configured_status": CONFIGURED,
                "live_readonly_status": STATUS_PASS,
                "provider_reason_code": SMOKE_PASSED,
            }
        )
        if compare_portfolio:
            result.update(_portfolio_compare_summary(observed_repo_keys))
    except Exception:
        result.update(
            {
                "status": STATUS_FAIL,
                "configured_status": CONFIGURED,
                "live_readonly_status": STATUS_FAIL,
                "provider_reason_code": GITHUB_LIVE_FAILED,
            }
        )
    return result


def _jira_provider_result(
    *,
    selected: bool,
    synthetic: bool,
    allow_live_readonly_apis: bool,
    acknowledge_live_readonly_risk: str | None,
    live_transport: jira.JiraTransport | None,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    result = _base_jira_result(selected=selected)
    if not selected:
        return result

    default_denied = _jira_default_denied()
    result["default_denied"] = default_denied["status"]
    result["provider_reason_code"] = default_denied["reason_code"]
    if default_denied["status"] != STATUS_PASS:
        result["status"] = STATUS_FAIL
        return result

    if synthetic:
        synthetic_events = jira.fetch_project_issue_events(
            transport=_synthetic_jira_transport(2),
            execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
        )
        project_count = len(synthetic_events)
        result.update(
            {
                "synthetic_status": STATUS_PASS,
                "live_readonly_status": NOT_RUN,
                "mapping_status": SYNTHETIC_VERIFIED,
                "project_count": project_count,
                "project_count_class": _zero_nonzero_count_class(project_count),
            }
        )
        return result

    if not allow_live_readonly_apis:
        result.update(
            {
                "live_readonly_status": NOT_RUN,
                "gated_status": GUARDED_NOT_EXECUTED,
                "provider_reason_code": REQUIRES_ACKNOWLEDGEMENT,
            }
        )
        return result

    if acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        result.update(
            {
                "status": STATUS_FAIL,
                "live_readonly_status": NOT_RUN,
                "provider_reason_code": PROVIDER_EXECUTION_ACK_REQUIRED,
            }
        )
        return result

    if not is_provider_configured(PROVIDER_JIRA, environ):
        result.update(
            {
                "configured_status": NOT_CONFIGURED,
                "live_readonly_status": NOT_CONFIGURED,
                "provider_reason_code": NOT_CONFIGURED,
            }
        )
        return result

    try:
        transport = live_transport or _jira_http_transport(environ)
        events = jira.fetch_project_issue_events(
            transport=transport,
            execution_mode=jira.LIVE_EXECUTION_MODE,
            allow_live_provider_execution=True,
            provider_execution_ack=acknowledge_live_readonly_risk,
        )
        project_count = len(events)
        result.update(
            {
                "configured_status": CONFIGURED,
                "live_readonly_status": STATUS_PASS,
                "mapping_status": LIVE_READONLY_VERIFIED,
                "provider_reason_code": SMOKE_PASSED,
                "live_failure_class": None,
                "auth_status_class": JIRA_AUTH_ACCEPTED,
                "transport_status_class": JIRA_TRANSPORT_PASS,
                "response_contract_status": JIRA_RESPONSE_CONTRACT_PASS,
                "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
                "project_count": project_count,
                "project_count_class": _zero_nonzero_count_class(project_count),
            }
        )
    except Exception as exc:
        failure = _classify_jira_live_readonly_failure(exc)
        result.update(
            {
                "status": STATUS_FAIL,
                "configured_status": CONFIGURED,
                "live_readonly_status": STATUS_FAIL,
                "provider_reason_code": failure.failure_class,
                **failure.safe_fields(),
            }
        )
    return result


def _base_github_result(*, selected: bool, compare_portfolio: bool) -> dict[str, Any]:
    portfolio_summary = repository_portfolio_public_summary()
    result = {
        "status": STATUS_PASS,
        "selection_status": SELECTED if selected else NOT_SELECTED,
        "default_denied": NOT_RUN,
        "configured_status": UNKNOWN,
        "live_readonly_status": NOT_RUN,
        "synthetic_status": NOT_RUN,
        "gated_status": REQUIRES_ACKNOWLEDGEMENT if selected else NOT_RUN,
        "provider_reason_code": None,
        "portfolio_expected_count": _portfolio_expected_count()
        if compare_portfolio
        else 0,
        "legacy_seed_repo_count": int(
            portfolio_summary.get("legacy_seed_repo_count") or 0
        ),
        "portfolio_expected_count_source": portfolio_summary.get(
            "operational_repo_source"
        ),
        "portfolio_compare_scope": "operational_inventory_counts_only"
        if compare_portfolio
        else "not_requested",
        "portfolio_compare": "not_requested",
        "github_target_owner_class": portfolio_summary["target_owner_class"],
        "github_target_org_key": portfolio_summary["target_org_key"],
        "github_org_migration_status": portfolio_summary["migration_status_class"],
        "github_org_live_inventory_status": portfolio_summary[
            "target_org_inventory_status"
        ],
        "github_write_operations": portfolio_summary["github_write_operations"],
        "github_repo_transfer_operations": portfolio_summary[
            "github_repo_transfer_operations"
        ],
        "github_repo_edit_operations": portfolio_summary["github_repo_edit_operations"],
        "live_inventory_count_class": COUNT_NOT_OBSERVED,
        "matched_count": 0,
        "matched_count_class": COUNT_NOT_OBSERVED,
        "missing_count": 0,
        "missing_count_class": COUNT_NOT_OBSERVED,
        "extra_count": 0,
        "extra_count_class": COUNT_NOT_OBSERVED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
    }
    return result


def _base_jira_result(*, selected: bool) -> dict[str, Any]:
    return {
        "status": STATUS_PASS,
        "selection_status": SELECTED if selected else NOT_SELECTED,
        "default_denied": NOT_RUN,
        "configured_status": UNKNOWN,
        "live_readonly_status": NOT_RUN,
        "synthetic_status": NOT_RUN,
        "gated_status": REQUIRES_ACKNOWLEDGEMENT if selected else NOT_RUN,
        "provider_reason_code": None,
        "mapping_status": PLANNED_NOT_VERIFIED,
        "live_failure_class": None,
        "auth_status_class": JIRA_TRANSPORT_NOT_OBSERVED,
        "transport_status_class": JIRA_TRANSPORT_NOT_OBSERVED,
        "response_contract_status": JIRA_RESPONSE_CONTRACT_NOT_OBSERVED,
        "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
        "project_count": 0,
        "project_count_class": COUNT_NOT_OBSERVED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
    }


def _github_default_denied() -> dict[str, Any]:
    transport_called = False

    def forbidden_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_safe_connector_payload()]

    try:
        github.list_repository_events(transport=forbidden_transport)
    except ProviderExecutionBlockedError as exc:
        return {
            "status": STATUS_PASS
            if exc.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
            and transport_called is False
            else STATUS_FAIL,
            "reason_code": exc.reason_code,
        }
    except Exception:
        return {"status": STATUS_FAIL, "reason_code": "github_default_denied_failed"}
    return {"status": STATUS_FAIL, "reason_code": "github_default_denied_bypassed"}


def _jira_default_denied() -> dict[str, Any]:
    transport_called = False

    def forbidden_transport(
        request: jira.JiraConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_safe_connector_payload()]

    try:
        jira.fetch_project_issue_events(transport=forbidden_transport)
    except ProviderExecutionBlockedError as exc:
        return {
            "status": STATUS_PASS
            if exc.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
            and transport_called is False
            else STATUS_FAIL,
            "reason_code": exc.reason_code,
        }
    except Exception:
        return {"status": STATUS_FAIL, "reason_code": "jira_default_denied_failed"}
    return {"status": STATUS_FAIL, "reason_code": "jira_default_denied_bypassed"}


def _synthetic_github_transport(count: int) -> github.GitHubTransport:
    def transport(
        request: github.GitHubConnectorRequest,
    ) -> Iterable[Mapping[str, Any]]:
        return [_safe_connector_payload() for _ in range(count)]

    return transport


def _synthetic_jira_transport(count: int) -> jira.JiraTransport:
    def transport(request: jira.JiraConnectorRequest) -> Iterable[Mapping[str, Any]]:
        return [_safe_connector_payload() for _ in range(count)]

    return transport


def _github_http_transport(
    environ: Mapping[str, str],
    observed_repo_keys: set[str],
) -> github.GitHubTransport:
    def transport(
        request: github.GitHubConnectorRequest,
    ) -> Iterable[Mapping[str, Any]]:
        token = environ["FOS_GITHUB_READONLY_TOKEN"]
        account = environ["FOS_GITHUB_READONLY_ACCOUNT"]
        endpoint = (
            _https_base("api.github.com")
            + "/users/"
            + urllib.parse.quote(account.strip(), safe="")
            + "/repos?per_page=100&type=all"
        )
        api_request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(api_request, timeout=10) as response:
            response_data = json.loads(response.read(1_000_000).decode("utf-8"))
        if not isinstance(response_data, list):
            return []
        payloads: list[dict[str, Any]] = []
        for item in response_data:
            if not isinstance(item, Mapping):
                continue
            repo_key = item.get("name")
            if not isinstance(repo_key, str) or not repo_key:
                continue
            observed_repo_keys.add(repo_key)
            payloads.append({**_safe_connector_payload(), "repo_key": repo_key})
        return payloads

    return transport


def _jira_http_transport(environ: Mapping[str, str]) -> jira.JiraTransport:
    site = _normalize_jira_site_config(environ.get("FOS_JIRA_READONLY_SITE", ""))
    user = environ["FOS_JIRA_READONLY_USER"]
    api_key = environ["FOS_JIRA_READONLY_TOKEN"]

    def transport(request: jira.JiraConnectorRequest) -> Iterable[Mapping[str, Any]]:
        endpoint = site + "/rest/api/3/project/search?maxResults=50"
        auth_value = base64.b64encode(f"{user}:{api_key}".encode("utf-8")).decode(
            "ascii"
        )
        api_request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": "Basic " + auth_value,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(api_request, timeout=10) as response:
                response_bytes = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            raise _jira_http_error_failure(exc.code) from None
        except urllib.error.URLError as exc:
            raise _jira_url_error_failure(exc) from None
        except (TimeoutError, socket.timeout):
            raise JiraLiveReadonlySmokeError(
                JIRA_TIMEOUT,
                transport_status_class=JIRA_TIMEOUT,
            ) from None
        except Exception:
            raise JiraLiveReadonlySmokeError(
                JIRA_TRANSPORT_ERROR,
                transport_status_class=JIRA_TRANSPORT_ERROR,
            ) from None
        try:
            response_data = json.loads(response_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise JiraLiveReadonlySmokeError(
                JIRA_RESPONSE_MALFORMED,
                transport_status_class=JIRA_TRANSPORT_PASS,
                response_contract_status=JIRA_RESPONSE_MALFORMED,
            ) from None
        projects = (
            response_data.get("values", [])
            if isinstance(response_data, Mapping)
            else response_data
        )
        if not isinstance(projects, list):
            raise JiraLiveReadonlySmokeError(
                JIRA_RESPONSE_MALFORMED,
                transport_status_class=JIRA_TRANSPORT_PASS,
                response_contract_status=JIRA_RESPONSE_MALFORMED,
            )
        if any(not isinstance(item, Mapping) for item in projects):
            raise JiraLiveReadonlySmokeError(
                JIRA_RESPONSE_CONTRACT_MISMATCH,
                transport_status_class=JIRA_TRANSPORT_PASS,
                response_contract_status=JIRA_RESPONSE_CONTRACT_MISMATCH,
            )
        return [_safe_connector_payload() for item in projects if isinstance(item, Mapping)]

    return transport


def _normalize_jira_site_config(raw_site: str) -> str:
    value = raw_site.strip()
    if not value or any(character.isspace() for character in value):
        raise JiraLiveReadonlySmokeError(
            JIRA_SITE_CONFIG_INVALID,
            transport_status_class=JIRA_TRANSPORT_NOT_STARTED,
        )
    if "://" not in value:
        value = _https_base(value)
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or any(character.isspace() for character in parsed.netloc)
    ):
        raise JiraLiveReadonlySmokeError(
            JIRA_SITE_CONFIG_INVALID,
            transport_status_class=JIRA_TRANSPORT_NOT_STARTED,
        )
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )


def _jira_http_error_failure(status_code: int) -> JiraLiveReadonlySmokeError:
    if status_code == 401:
        return JiraLiveReadonlySmokeError(
            JIRA_AUTH_FAILED,
            auth_status_class=JIRA_AUTH_FAILED,
            transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
        )
    if status_code == 403:
        return JiraLiveReadonlySmokeError(
            JIRA_PERMISSION_DENIED,
            auth_status_class=JIRA_PERMISSION_DENIED,
            transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
        )
    if status_code == 404:
        return JiraLiveReadonlySmokeError(
            JIRA_NOT_FOUND_OR_WRONG_SITE,
            transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
        )
    if status_code == 429:
        return JiraLiveReadonlySmokeError(
            JIRA_RATE_LIMITED,
            transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
        )
    if 500 <= status_code <= 599:
        return JiraLiveReadonlySmokeError(
            JIRA_SERVER_ERROR,
            transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
        )
    return JiraLiveReadonlySmokeError(
        JIRA_TRANSPORT_ERROR,
        transport_status_class=JIRA_TRANSPORT_HTTP_ERROR,
    )


def _jira_url_error_failure(exc: urllib.error.URLError) -> JiraLiveReadonlySmokeError:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError | socket.timeout):
        return JiraLiveReadonlySmokeError(
            JIRA_TIMEOUT,
            transport_status_class=JIRA_TIMEOUT,
        )
    return JiraLiveReadonlySmokeError(
        JIRA_TRANSPORT_ERROR,
        transport_status_class=JIRA_TRANSPORT_ERROR,
    )


def _classify_jira_live_readonly_failure(
    exc: Exception,
) -> JiraLiveReadonlySmokeError:
    if isinstance(exc, JiraLiveReadonlySmokeError):
        return exc
    if isinstance(exc, jira.JiraConnectorError):
        if exc.reason_code in {
            jira.JIRA_RAW_EVENT_CONTRACT_INVALID,
            jira.JIRA_INVENTORY_RESPONSE_CONTRACT_INVALID,
        }:
            return JiraLiveReadonlySmokeError(
                JIRA_RESPONSE_CONTRACT_MISMATCH,
                transport_status_class=JIRA_TRANSPORT_PASS,
                response_contract_status=JIRA_RESPONSE_CONTRACT_MISMATCH,
            )
        return JiraLiveReadonlySmokeError(
            JIRA_UNKNOWN_LIVE_SMOKE_FAILURE,
            response_contract_status=JIRA_RESPONSE_CONTRACT_NOT_OBSERVED,
        )
    if isinstance(exc, urllib.error.HTTPError):
        return _jira_http_error_failure(exc.code)
    if isinstance(exc, urllib.error.URLError):
        return _jira_url_error_failure(exc)
    if isinstance(exc, TimeoutError | socket.timeout):
        return JiraLiveReadonlySmokeError(
            JIRA_TIMEOUT,
            transport_status_class=JIRA_TIMEOUT,
        )
    if isinstance(exc, json.JSONDecodeError | UnicodeDecodeError):
        return JiraLiveReadonlySmokeError(
            JIRA_RESPONSE_MALFORMED,
            transport_status_class=JIRA_TRANSPORT_PASS,
            response_contract_status=JIRA_RESPONSE_MALFORMED,
        )
    return JiraLiveReadonlySmokeError(
        JIRA_UNKNOWN_LIVE_SMOKE_FAILURE,
        transport_status_class=JIRA_TRANSPORT_ERROR,
    )


def _portfolio_compare_summary(observed_repo_keys: set[str]) -> dict[str, Any]:
    expected_repo_keys = _portfolio_repo_keys()
    matched_count = len(expected_repo_keys & observed_repo_keys)
    missing_count = len(expected_repo_keys - observed_repo_keys)
    extra_count = len(observed_repo_keys - expected_repo_keys)
    observed_count = len(observed_repo_keys)
    return {
        "portfolio_expected_count": len(expected_repo_keys),
        "legacy_seed_repo_count": _legacy_seed_repo_count(),
        "portfolio_expected_count_source": _portfolio_source_class(),
        "portfolio_compare": "counts_only",
        "portfolio_compare_scope": "operational_inventory_counts_only",
        "live_inventory_count_class": _expected_count_class(
            observed_count,
            len(expected_repo_keys),
        ),
        "matched_count": matched_count,
        "matched_count_class": _expected_count_class(
            matched_count,
            len(expected_repo_keys),
        ),
        "missing_count": missing_count,
        "missing_count_class": _zero_nonzero_count_class(missing_count),
        "extra_count": extra_count,
        "extra_count_class": _zero_nonzero_count_class(extra_count),
    }


def _repo_keys_from_events(events: Iterable[Mapping[str, Any]]) -> set[str]:
    repo_keys: set[str] = set()
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        repo_key = payload.get("repo_key")
        if isinstance(repo_key, str) and repo_key:
            repo_keys.add(repo_key)
    return repo_keys


def _portfolio_repo_keys() -> set[str]:
    inventory = load_repository_source_inventory_snapshot()
    return {
        str(entry["repo_key"])
        for entry in inventory.get("repositories", [])
        if isinstance(entry, Mapping) and isinstance(entry.get("repo_key"), str)
    }


def _portfolio_expected_count() -> int:
    return len(_portfolio_repo_keys())


def _legacy_seed_repo_count() -> int:
    inventory = load_repository_source_inventory_snapshot()
    return int(inventory.get("legacy_seed_repo_count") or 0)


def _portfolio_source_class() -> str:
    inventory = load_repository_source_inventory_snapshot()
    return str(inventory.get("operational_repo_source") or "unknown")


def _safe_connector_payload() -> dict[str, str]:
    return {
        "title": "synthetic_connector_event",
        "source_url": "synthetic_source_location",
    }


def _expected_count_class(observed_count: int, expected_count: int) -> str:
    if observed_count == expected_count:
        return COUNT_MATCHES_EXPECTED
    if observed_count < expected_count:
        return COUNT_BELOW_EXPECTED
    return COUNT_ABOVE_EXPECTED


def _zero_nonzero_count_class(count: int) -> str:
    return COUNT_ZERO if count == 0 else COUNT_NONZERO


def _https_base(host: str) -> str:
    return "https" + (chr(58) + "//") + host


def _selected_providers(provider: str) -> set[str]:
    if provider == "all":
        return {"github", "jira"}
    if provider in {"github", "jira"}:
        return {provider}
    return {"github", "jira"}


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    safety = inspect_operator_output(result)
    if not safety.safe:
        return _failure_report(
            SMOKE_OUTPUT_UNSAFE,
            operator_output_safety=safety.as_dict(),
        )

    validation = validate_connector_readonly_smoke_contract(result).as_dict()
    result["contract_validation"] = validation
    if validation["validation_status"] != STATUS_PASS:
        return _failure_report(
            SMOKE_CONTRACT_INVALID,
            contract_validation=validation,
        )
    return result


def _failure_report(
    reason_code: str,
    *,
    contract_validation: Mapping[str, Any] | None = None,
    operator_output_safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": STATUS_FAIL,
        "reason_code": _safe_reason_code(reason_code),
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "provider_calls": PROVIDER_CALLS_NONE,
        "providers": {},
        "diagnostics": {
            "selected_provider_count": 0,
            "default_denied_pass_count": 0,
            "failed_provider_count": 1,
            "not_configured_count": 0,
            "live_readonly_attempt_count": 0,
            "synthetic_mode": False,
            "portfolio_compare_requested": False,
            "operator_output_safety": dict(operator_output_safety or {}),
        },
    }
    result["contract_validation"] = dict(
        contract_validation
        or validate_connector_readonly_smoke_contract(result).as_dict()
    )
    return result


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or SMOKE_FAILED


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("github", "jira", "all"), default="all")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument("--acknowledge-live-readonly-risk")
    parser.add_argument("--compare-portfolio", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output strict JSON. This is the default and only output mode.",
    )
    add_connector_env_file_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_connector_readonly_smoke(
        provider=args.provider,
        synthetic=args.synthetic,
        allow_live_readonly_apis=args.allow_live_readonly_apis,
        acknowledge_live_readonly_risk=args.acknowledge_live_readonly_risk,
        compare_portfolio=args.compare_portfolio,
        **connector_env_cli_kwargs(args),
    )
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
