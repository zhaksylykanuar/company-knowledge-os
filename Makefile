.PHONY: backend-check check frontend-check local local-backend local-backup local-doctor local-readiness local-smoke local-stop release-handoff smoke secret-scan

local:
	uv run python scripts/start_local.py run

local-backend:
	uv run python scripts/start_local.py backend

local-doctor:
	uv run python scripts/start_local.py doctor

local-backup:
	uv run python scripts/start_local.py backup

local-stop:
	uv run python scripts/start_local.py stop

local-smoke:
	UV_NO_SYNC=1 uv run python scripts/smoke_local.py --skip-workspace-checks

smoke: local-smoke

local-readiness:
	UV_NO_SYNC=1 uv run python scripts/local_readiness_report.py

release-handoff: local-readiness

secret-scan:
	bash scripts/check_no_secrets.sh --tracked

backend-check:
	python3 scripts/backend_check.py

frontend-check:
	cd web && npm test && npm run build && npm run typecheck && npm run lint

check: backend-check frontend-check
