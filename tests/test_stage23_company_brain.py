from __future__ import annotations

import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.company_brain_preview import (
    EXCLUDED_PERSON_IDS,
    load_company_brain_preview,
    load_people,
    load_second_opinion,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_WORKSPACE = _REPO_ROOT / ".local"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _has_real_preview() -> bool:
    return (
        _REAL_WORKSPACE
        / "company-brain"
        / "stage22"
        / "stage22-proposed-graph-nodes.json"
    ).exists()


def _write_stage22(tmp_path: Path, files: dict[str, str]) -> Path:
    stage_dir = tmp_path / "company-brain" / "stage22"
    stage_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (stage_dir / name).write_text(content, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# Loader tests
# --------------------------------------------------------------------------


def test_loader_reads_real_preview_safely() -> None:
    if not _has_real_preview():
        return  # local preview not present in this checkout; nothing to assert
    preview = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)

    assert preview["status"] == "local_preview_only"
    assert preview["source_status"]["available"] is True

    # exactly the 16-person working roster
    people = preview["people"]
    assert len(people) == 16

    # second opinion feed carries the 8 mandatory cards
    assert len(preview["second_opinion_feed"]) == 8


def test_loader_guardrails_never_claim_confirmed() -> None:
    if not _has_real_preview():
        return
    g = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)["guardrails"]
    assert g["preview_only"] is True
    assert g["db_written"] is False
    assert g["production_graph"] is False
    assert g["raci_confirmed"] is False
    assert g["jira_hint_is_verified_account_id"] is False
    assert g["no_raw_email"] is True
    assert g["raw_email_detected"] is False


def test_excluded_people_not_active_recommendation_targets() -> None:
    if not _has_real_preview():
        return
    people = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)["people"]
    excluded = [p for p in people if p["person_id"] in EXCLUDED_PERSON_IDS]
    assert {p["person_id"] for p in excluded} == set(EXCLUDED_PERSON_IDS)
    for person in excluded:
        assert person["excluded_for_now"] is True
        assert person["identity"] is None
        assert person["areas"] == []


def test_jira_hint_never_verified_account_id() -> None:
    if not _has_real_preview():
        return
    people = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)["people"]
    for person in people:
        identity = person.get("identity")
        if identity is None:
            continue
        assert identity["jira_is_verified_account_id"] is False
        assert identity["jira_identity_status"] in {
            "founder_hint_not_connector_verified",
            "unknown",
        }


def test_areas_are_not_ownership() -> None:
    if not _has_real_preview():
        return
    people = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)["people"]
    for person in people:
        assert person["areas_are_ownership"] is False


def test_no_raw_email_in_real_preview() -> None:
    if not _has_real_preview():
        return
    preview = load_company_brain_preview(workspace_path=_REAL_WORKSPACE)
    assert "@" not in json.dumps(preview, ensure_ascii=False)


def test_missing_files_handled_gracefully(tmp_path: Path) -> None:
    # empty workspace: no stage22 files at all
    preview = load_company_brain_preview(workspace_path=tmp_path)
    assert preview["source_status"]["available"] is False
    assert preview["provenance"]["mode_label_ru"] == "Предпросмотр"
    assert preview["provenance"]["computed_facts_label_ru"] == "Вычисленные факты"
    assert preview["provenance"]["production_graph"] is False
    assert preview["people"] == []
    assert preview["second_opinion_feed"] == []
    # still returns a coherent guardrail block, never raises
    assert preview["guardrails"]["preview_only"] is True
    assert preview["source_status"]["artifact_provenance"]["mode"] == "static_local_preview"
    assert all(
        item["status"] == "missing"
        for item in preview["source_status"]["artifact_provenance"]["artifacts"]
    )


def test_source_status_includes_artifact_provenance(tmp_path: Path) -> None:
    nodes = {"nodes": [{"id": "p-x", "type": "Person", "name_ru": "Тест"}]}
    workspace = _write_stage22(
        tmp_path,
        {
            "stage22-proposed-graph-nodes.json": json.dumps(nodes, ensure_ascii=False),
            "stage22-proposed-graph-edges.json": json.dumps({"edges": []}),
            "second-opinion-feed-v0.json": json.dumps({"feed": []}),
            "stage22-unresolved-questions.md": "# ok\n",
        },
    )

    preview = load_company_brain_preview(workspace_path=workspace)
    source_status = preview["source_status"]
    provenance = source_status["artifact_provenance"]

    assert source_status["available"] is True
    assert source_status["generated_at"] == provenance["generated_at"]
    assert source_status["snapshot_id"] == provenance["snapshot_id"]
    assert provenance["source_label_ru"] == "Локальный preview snapshot"
    assert provenance["artifact_count"] == 4
    assert len(provenance["snapshot_id"]) == 64
    assert isinstance(provenance["artifact_age_seconds"], int)
    assert {
        item["name"]: item["status"]
        for item in provenance["artifacts"]
    } == {
        "stage22-proposed-graph-nodes.json": "available",
        "stage22-proposed-graph-edges.json": "available",
        "second-opinion-feed-v0.json": "available",
        "stage22-unresolved-questions.md": "available",
    }
    assert all(
        len(item["content_sha256"]) == 64
        for item in provenance["artifacts"]
        if item["status"] == "available"
    )


def test_invalid_json_handled_gracefully(tmp_path: Path) -> None:
    workspace = _write_stage22(
        tmp_path,
        {"stage22-proposed-graph-nodes.json": "{ this is not valid json "},
    )
    preview = load_company_brain_preview(workspace_path=workspace)
    assert preview["source_status"]["available"] is False
    assert "stage22-proposed-graph-nodes.json" in preview["source_status"]["invalid_files"]
    assert preview["people"] == []


def test_raw_email_is_blocked_and_flagged(tmp_path: Path) -> None:
    # craft a preview where a node accidentally carries a raw email address
    # The email is placed in a propagated field (name_ru) so the redaction
    # backstop must catch it; the loader copies name_ru verbatim into people.
    # Built at runtime so this source file never contains a literal address.
    leaked = "person" + "@" + "example.com"
    nodes = {
        "nodes": [
            {
                "id": "p-x",
                "type": "Person",
                "name_ru": f"Тест (связаться: {leaked})",
                "role_ru": "Инженер",
            },
            {
                "id": "idh-p-x",
                "type": "IdentityHint",
                "person_id": "p-x",
                "github": ["unknown"],
                "github_status": "unknown",
                "jira_hint": None,
                "jira_identity_status": "unknown",
                "email_status": "confirmed",
            },
        ]
    }
    workspace = _write_stage22(
        tmp_path,
        {"stage22-proposed-graph-nodes.json": json.dumps(nodes, ensure_ascii=False)},
    )
    preview = load_company_brain_preview(workspace_path=workspace)
    serialized = json.dumps(preview, ensure_ascii=False)
    assert "@" not in serialized
    assert leaked not in serialized
    assert preview["guardrails"]["raw_email_detected"] is True
    assert preview["guardrails"]["no_raw_email"] is False


def test_people_loader_shape(tmp_path: Path) -> None:
    # shape is stable even on an empty workspace
    payload = load_people(workspace_path=tmp_path)
    assert set(payload) >= {"stage", "status", "guardrails", "people", "ownership_gaps"}


def test_second_opinion_loader_shape(tmp_path: Path) -> None:
    payload = load_second_opinion(workspace_path=tmp_path)
    assert "second_opinion_feed" in payload


# --------------------------------------------------------------------------
# API tests (read-only endpoints, auth disabled by conftest)
# --------------------------------------------------------------------------


async def test_api_preview_endpoint_shape() -> None:
    async with _client() as client:
        resp = await client.get("/api/v1/founder/company-brain/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "local_preview_only"
    assert body["guardrails"]["db_written"] is False
    # russian founder-facing copy is present
    assert "Мозг компании" in body["overview"]["headline_ru"]
    # never leak an address in the response
    assert "@" not in resp.text


async def test_api_second_opinion_returns_eight_cards() -> None:
    if not _has_real_preview():
        return
    async with _client() as client:
        resp = await client.get("/api/v1/founder/company-brain/second-opinion")
    assert resp.status_code == 200
    feed = resp.json()["second_opinion_feed"]
    assert len(feed) == 8
    assert all(card.get("title_ru") for card in feed)


async def test_api_people_and_unresolved_endpoints() -> None:
    async with _client() as client:
        people_resp = await client.get("/api/v1/founder/company-brain/people")
        unresolved_resp = await client.get(
            "/api/v1/founder/company-brain/unresolved-questions"
        )
    assert people_resp.status_code == 200
    assert unresolved_resp.status_code == 200
    assert "people" in people_resp.json()
    assert "unresolved_questions" in unresolved_resp.json()
    assert "@" not in people_resp.text
