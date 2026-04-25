from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SourceSystem = Literal[
    "drive", "gmail", "jira", "github", "gitlab",
    "bitbucket", "telegram", "internal",
]


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    event_type: str
    source_system: SourceSystem
    source_object_id: str
    source_event_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    received_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid4().hex}")
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex}")
    raw_object_ref: str
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0"
