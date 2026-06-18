"""Current agent-run id, for tracing what a run touched.

The pipeline sets the run id once at the start of a run; finding upserts
and proposal creations stamp it so the evidence trail can answer not
just "what evidence" but "which agent run created or updated this".
"""

from __future__ import annotations

from contextvars import ContextVar

_current_run_id: ContextVar[str | None] = ContextVar(
    "founderos_current_run_id", default=None
)


def set_run_id(run_id: str | None) -> None:
    _current_run_id.set(run_id)


def get_run_id() -> str | None:
    return _current_run_id.get()
