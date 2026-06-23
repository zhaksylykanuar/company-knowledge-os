import ast
import importlib
from pathlib import Path

from app.db.base import Base


EXPECTED_ALEMBIC_TABLES = {
    "agent_proposals",
    "metric_snapshots",
    "agent_run_logs",
    "data_availability",
    "second_opinion_findings",
    "founder_declarations",
    "users",
    "workspaces",
    "memberships",
    "integration_connections",
    "sync_jobs",
    "action_proposals",
    "action_executions",
}

EXPECTED_ALEMBIC_MODEL_MODULES = {
    "app.db.action_models",
    "app.db.agent_models",
    "app.db.second_opinion_models",
    "app.db.declaration_models",
    "app.db.identity_models",
    "app.db.integration_models",
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
