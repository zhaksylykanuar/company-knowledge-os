.PHONY: smoke

smoke:
	UV_NO_SYNC=1 uv run python scripts/smoke_private_beta.py
