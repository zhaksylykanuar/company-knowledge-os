import ast
import importlib
from pathlib import Path

from app.db.base import Base


# Canonical lineage after the Lineage-2 purge (DEC-029). The temporary substrate
# (source_events / normalized_activity_items / ingested_events) stays until
# FOS-009 (DEC-030); the entities graph and other Lineage-2 tables are gone.
EXPECTED_ALEMBIC_TABLES = {
    "users",
    "workspaces",
    "memberships",
    "integration_connections",
    "sync_jobs",
    "action_proposals",
    "action_executions",
    "action_execution_events",
    "audit_logs",
    "source_records",
    "evidence_refs",
    "repositories",
    "pull_requests",
    "tasks",
}

EXPECTED_ALEMBIC_MODEL_MODULES = {
    "app.db.action_models",
    "app.db.canonical_models",
    "app.db.identity_models",
    "app.db.integration_models",
    "app.db.models",
    "app.db.event_models",
}


def _env_model_imports() -> set[str]:
    env_path = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
    tree = ast.parse(env_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.db."):
                    imports.add(alias.name)
    return imports


def test_alembic_env_imports_new_model_modules() -> None:
    assert EXPECTED_ALEMBIC_MODEL_MODULES <= _env_model_imports()


def test_alembic_env_imports_register_new_tables_in_metadata() -> None:
    for module_name in _env_model_imports():
        importlib.import_module(module_name)

    assert EXPECTED_ALEMBIC_TABLES <= set(Base.metadata.tables)
