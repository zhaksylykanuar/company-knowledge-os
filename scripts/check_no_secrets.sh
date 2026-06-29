#!/usr/bin/env bash
set -euo pipefail

mode="${1:---staged}"
secret_pattern='sk-[A-Za-z0-9_-]{20,}|xoxb-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{10,}'

is_sensitive_path() {
  local file="$1"
  [[ "$file" == ".env" || "$file" == .env.* || "$file" == secrets/* || "$file" == raw_storage/* || "$file" == obsidian_vault/* || "$file" == operator_outputs/* ]]
}

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'Not inside a git work tree; skipping secret scan'
  exit 0
fi

if [[ "$mode" != "--staged" && "$mode" != "--tracked" ]]; then
  echo "Usage: $0 [--staged|--tracked]" >&2
  exit 2
fi

if [[ "$mode" == "--staged" ]]; then
  while IFS= read -r -d '' file; do
    if [[ "$file" != ".env.example" ]] && is_sensitive_path "$file"; then
      echo "ERROR: staged secrets or raw data detected: $file" >&2
      exit 1
    fi
  done < <(git diff --cached --name-only -z)

  # Real provider keys are long tokens; require a substantial run after the
  # prefix so ordinary identifiers like "task-body" / "risk-review" (which
  # contain the substring "sk-") do not trigger a false positive while real
  # OpenAI / Slack / Google / GitHub / GitLab tokens still match. In staged
  # mode, scan added/resulting diff lines only so cleanup commits that remove
  # old token-shaped literals are not blocked. Keep grep quiet so a failing
  # scan never prints the matched secret value.
  if git diff --cached --no-ext-diff --unified=0 \
    | grep -E '^\+' \
    | grep -vE '^\+\+\+' \
    | grep -qE "$secret_pattern"; then
    echo 'ERROR: possible secret pattern detected in staged diff' >&2
    exit 1
  fi

  echo 'No obvious staged secrets found'
  exit 0
fi

while IFS= read -r -d '' file; do
  [[ -e "$file" ]] || continue

  if [[ "$file" != ".env.example" ]] && is_sensitive_path "$file"; then
    echo "ERROR: tracked secrets or raw data detected: $file" >&2
    exit 1
  fi

  if grep -IqE "$secret_pattern" "$file"; then
    echo "ERROR: possible secret pattern detected in tracked file: $file" >&2
    exit 1
  fi
done < <(git ls-files -z)

echo 'No obvious tracked secrets found'
