from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.prepare_github_local_snapshot import (
    SnapshotPreparationError,
    load_and_normalize_repositories,
    write_discovery_snapshot,
    write_repository_env_snippet,
)


def test_prepare_github_local_snapshot_normalizes_and_writes_outputs(tmp_path: Path) -> None:
    source = tmp_path / "repos.json"
    source.write_text(
        json.dumps(
            [
                {
                    "full_name": "qtwin-io/service-api",
                    "name": "service-api",
                    "owner": "qtwin-io",
                    "private": True,
                    "archived": False,
                    "fork": False,
                    "default_branch": "main",
                    "html_url": "https://github.com/qtwin-io/service-api",
                    "updated_at": "2026-06-30T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    repositories = load_and_normalize_repositories(source)
    raw_path = write_discovery_snapshot(
        workspace=tmp_path / ".local",
        snapshot_id="test-snap",
        repositories=repositories,
    )
    env_path = write_repository_env_snippet(
        workspace=tmp_path / ".local",
        repositories=repositories,
    )

    written = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw_path == tmp_path / ".local" / "discovery" / "github" / "test-snap" / "raw" / "repos.json"
    assert written[0]["full_name"] == "qtwin-io/service-api"
    assert written[0]["owner"] == {"login": "qtwin-io"}
    assert written[0]["visibility"] == "private"
    env_text = env_path.read_text(encoding="utf-8")
    assert "FOUNDEROS_GITHUB_REPOS=qtwin-io/service-api" in env_text
    assert "FOS_GITHUB_SYNC_ALLOWED_REPOS=qtwin-io/service-api" in env_text
    assert "TOKEN" not in env_text


def test_prepare_github_local_snapshot_refuses_sensitive_keys(tmp_path: Path) -> None:
    source = tmp_path / "repos.json"
    source.write_text(
        json.dumps(
            [
                {
                    "full_name": "qtwin-io/service-api",
                    "name": "service-api",
                    "owner": "qtwin-io",
                    "access_token": "should-not-copy",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SnapshotPreparationError, match="sensitive-looking key"):
        load_and_normalize_repositories(source)
