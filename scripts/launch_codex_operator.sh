#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "${REPO_ROOT}"

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

if [[ -f ".env" ]]; then
  set -a
  if ! source ".env" >/dev/null 2>&1; then
    set +a
    echo "Failed to load .env. Check shell syntax." >&2
    exit 1
  fi
  set +a
fi

if [[ "${1:-}" == "--check-only" ]]; then
  "${PYTHON_BIN}" scripts/operator_env_health.py --mode fos036
  exit $?
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "codex command not found. Install Codex or add it to PATH." >&2
  exit 127
fi

"${PYTHON_BIN}" scripts/operator_env_health.py --mode fos036

exec codex "$@"
