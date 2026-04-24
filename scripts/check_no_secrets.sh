#!/usr/bin/env bash
set -euo pipefail

for file in $(git diff --cached --name-only); do
  if [[ "$file" == ".env.example" ]]; then
    continue
  fi

  if [[ "$file" == ".env" || "$file" == .env.* || "$file" == secrets/* || "$file" == raw_storage/* ]]; then
    echo "ERROR: staged secrets or raw data detected: $file" >&2
    exit 1
  fi
done

echo 'No obvious staged secrets found'
