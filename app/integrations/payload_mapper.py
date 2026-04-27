from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.integrations.source_registry import validate_source_event_contract


REQUIRED_CONNECTOR_PAYLOAD_FIELDS = frozenset(
    {
        "source_system",
        "source_object_type",
        "source_object_id",
        "event_type",
        "idempotency_key",
        "raw_object_ref",
        "payload",
    }
)


class ConnectorPayloadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class IngestedEventReadyPayload:
    event_id: str
    event_type: str
    source_system: str
    source_object_id: str
    idempotency_key: str
    raw_object_ref: str
    payload: dict[str, Any]
    correlation_id: str | None = None
    trace_id: str | None = None

    def to_ingested_event_kwargs(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_system": self.source_system,
            "source_object_id": self.source_object_id,
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "raw_object_ref": self.raw_object_ref,
            "payload": self.payload,
        }


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise ConnectorPayloadValidationError(
            f"missing required connector payload field: {field_name}"
        )

    return value.strip()


def _optional_string(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)

    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():
        raise ConnectorPayloadValidationError(
            f"invalid optional connector payload field: {field_name}"
        )

    return value.strip()


def _required_payload_dict(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("payload")

    if not isinstance(value, dict):
        raise ConnectorPayloadValidationError(
            "missing required connector payload field: payload"
        )

    return value


def build_connector_event_id(
    *,
    source_system: str,
    event_type: str,
    source_object_id: str,
    idempotency_key: str,
) -> str:
    stable_key = ":".join(
        [
            source_system,
            event_type,
            source_object_id,
            idempotency_key,
        ]
    )
    digest = sha256(stable_key.encode("utf-8")).hexdigest()
    return f"evt_{digest[:32]}"


def map_connector_payload_to_ingested_event(
    connector_payload: dict[str, Any],
) -> IngestedEventReadyPayload:
    missing_fields = sorted(REQUIRED_CONNECTOR_PAYLOAD_FIELDS - connector_payload.keys())
    if missing_fields:
        raise ConnectorPayloadValidationError(
            f"missing connector payload fields: {', '.join(missing_fields)}"
        )

    source_system = _required_string(connector_payload, "source_system")
    source_object_type = _required_string(connector_payload, "source_object_type")
    source_object_id = _required_string(connector_payload, "source_object_id")
    event_type = _required_string(connector_payload, "event_type")
    idempotency_key = _required_string(connector_payload, "idempotency_key")
    raw_object_ref = _required_string(connector_payload, "raw_object_ref")
    payload = _required_payload_dict(connector_payload)

    contract_errors = validate_source_event_contract(
        source_system=source_system,
        source_object_type=source_object_type,
        event_type=event_type,
        payload=payload,
    )
    if contract_errors:
        raise ConnectorPayloadValidationError("; ".join(contract_errors))

    event_id = build_connector_event_id(
        source_system=source_system,
        event_type=event_type,
        source_object_id=source_object_id,
        idempotency_key=idempotency_key,
    )

    return IngestedEventReadyPayload(
        event_id=event_id,
        event_type=event_type,
        source_system=source_system,
        source_object_id=source_object_id,
        idempotency_key=idempotency_key,
        correlation_id=_optional_string(connector_payload, "correlation_id") or f"corr_{event_id}",
        trace_id=_optional_string(connector_payload, "trace_id") or f"trace_{event_id}",
        raw_object_ref=raw_object_ref,
        payload=payload,
    )
