#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'Not inside a git work tree; skipping staged-secret scan'
  exit 0
fi

for file in $(git diff --cached --name-only); do
  if [[ "$file" == ".env.example" ]]; then
    continue
  fi

  if [[ "$file" == ".env" || "$file" == .env.* || "$file" == secrets/* || "$file" == raw_storage/* ]]; then
    echo "ERROR: staged secrets or raw data detected: $file" >&2
    exit 1
  fi
done

# Real provider keys are long tokens; require a substantial run after the
# prefix so ordinary identifiers like "task-body" / "risk-review" (which
# contain the substring "sk-") do not trigger a false positive while real
# OpenAI / Slack / Google / GitHub / GitLab tokens still match.
if git diff --cached | grep -E 'sk-[A-Za-z0-9_-]{20,}|xoxb-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{10,}' ; then
  echo 'ERROR: possible secret pattern detected' >&2
  exit 1
fi

echo 'No obvious staged secrets found'
