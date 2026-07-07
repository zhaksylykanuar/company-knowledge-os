.PHONY: backend-check check frontend-check release-handoff smoke secret-scan

smoke:
	UV_NO_SYNC=1 uv run python scripts/smoke_private_beta.py

release-handoff:
	UV_NO_SYNC=1 uv run python scripts/private_beta_release_handoff.py

secret-scan:
	bash scripts/check_no_secrets.sh --tracked

backend-check:
	uv sync --frozen
	uv run ruff check .
	uv run alembic upgrade head
	uv run alembic check
	uv run pytest -q
	bash scripts/check_no_secrets.sh --tracked

frontend-check:
	cd web && npm test && npm run build && npm run typecheck && npm run lint

check: backend-check frontend-check
