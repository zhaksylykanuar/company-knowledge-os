#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical local-runtime smoke command."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.smoke_local import (  # noqa: E402
    API_KEY_HEADER_NAME,
    FORBIDDEN_PATH_MARKERS,
    OPTIONAL_LOCAL_MUTATION_STEPS,
    READ_ONLY_WORKSPACE_STEPS,
    SmokeCheckError,
    SmokeConfig,
    SmokeConfigError,
    SmokeStep,
    _build_request,
    config_from_env_and_args,
    main,
    run_smoke,
)

WORKSPACE_STEPS = READ_ONLY_WORKSPACE_STEPS + OPTIONAL_LOCAL_MUTATION_STEPS

__all__ = [
    "API_KEY_HEADER_NAME",
    "FORBIDDEN_PATH_MARKERS",
    "OPTIONAL_LOCAL_MUTATION_STEPS",
    "READ_ONLY_WORKSPACE_STEPS",
    "SmokeCheckError",
    "SmokeConfig",
    "SmokeConfigError",
    "SmokeStep",
    "WORKSPACE_STEPS",
    "_build_request",
    "config_from_env_and_args",
    "run_smoke",
]


if __name__ == "__main__":
    raise SystemExit(main())
