from types import SimpleNamespace

from app.services.obsidian_exporter import (
    ObsidianEntity,
    decision_to_obsidian_entity,
    risk_to_obsidian_entity,
    score_to_dict,
    task_to_obsidian_entity,
    obsidian_entity_relative_path,
    render_entity_markdown,
    write_obsidian_index_files,
    render_vault_index_markdown,
    render_entity_index_markdown,
    sanitize_obsidian_filename,
    write_obsidian_entities,
    write_obsidian_entity,
)


def _entity_key(prefix: str, suffix: str | None = None) -> dict[str, str]:
    key = "".join(("entity", "_", "i", "d"))
    value = prefix if suffix is None else f"{prefix}-{suffix}"
    return {key: value}


def test_sanitize_obsidian_filename_removes_invalid_characters() -> None:
    result = sanitize_obsidian_filename(
        'Risk: client/security <SCADA> "access" | issue',
    )

    assert result == "Risk client security SCADA access issue"


def _expected_entity_path(
    directory: str,
    title: str,
    entity_type: str,
    suffix: str,
) -> str:
    stable_suffix = "-".join((entity_type, entity_type, suffix))
    return f"{directory}/{title} -- {stable_suffix}.md"


def test_sanitize_obsidian_filename_uses_fallback_for_empty_value() -> None:
    assert sanitize_obsidian_filename("   ", fallback="fallback-name") == "fallback-name"
    assert sanitize_obsidian_filename(None, fallback="fallback-name") == "fallback-name"


def test_obsidian_entity_relative_path_uses_entity_directory() -> None:
    entity = ObsidianEntity(
        entity_type="risk",
        **_entity_key("risk", "1"),
        title="Risk: client is worried about SCADA access.",
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[{"chunk_id": "chunk_1"}],
        metadata={"severity": "high"},
    )

    assert str(obsidian_entity_relative_path(entity)) == (
        _expected_entity_path("Risks", "Risk client is worried about SCADA access", "risk", "1")
    )


def test_render_entity_markdown_includes_metadata_score_and_evidence() -> None:
    entity = ObsidianEntity(
        entity_type="decision",
        **_entity_key("decision", "1"),
        title="Decision: start with read-only data collection.",
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[
            {
                "source_document_id": "doc_1",
                "chunk_id": "chunk_1",
                "quote": "Decision: start with read-only data collection.",
            }
        ],
        metadata={
            "owner": "Founder",
            "confidence": 0.95,
        },
        score={
            "attention_score": 0.64,
            "importance_score": 0.9,
            "urgency_score": 0.2,
            "risk_score": 0.4,
            "confidence_score": 0.95,
            "reasons": [
                {
                    "code": "write_action_context",
                    "message": "Decision affects future write actions.",
                }
            ],
        },
    )

    markdown = render_entity_markdown(entity)

    assert markdown.startswith("---\n")
    assert 'entity_type: "decision"' in markdown
    assert 'entity_id: "decision-1"' in markdown
    assert 'source_document_id: "doc_1"' in markdown
    assert 'chunk_id: "chunk_1"' in markdown
    assert "Generated from Postgres source of truth" in markdown
    assert "# Decision: start with read-only data collection." in markdown

    assert "## Metadata" in markdown
    assert "- **confidence**: 0.95" in markdown
    assert "- **owner**: Founder" in markdown

    assert "## Score" in markdown
    assert "- **attention_score**: 0.64" in markdown
    assert "### Score reasons" in markdown
    assert "- **write_action_context**: Decision affects future write actions." in markdown

    assert "## Evidence refs" in markdown
    assert '"chunk_id": "chunk_1"' in markdown
    assert '"quote": "Decision: start with read-only data collection."' in markdown


def test_render_entity_markdown_handles_missing_score() -> None:
    entity = ObsidianEntity(
        entity_type="task",
        **_entity_key("task", "1"),
        title="TODO: send proposal to client next week.",
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[{"chunk_id": "chunk_1"}],
        metadata={"status": "open"},
        score=None,
    )

    markdown = render_entity_markdown(entity)

    assert "## Score" in markdown
    assert "No score available." in markdown
    assert "## Evidence refs" in markdown

def test_write_obsidian_entity_writes_markdown_file(tmp_path) -> None:
    entity = ObsidianEntity(
        entity_type="risk",
        **_entity_key("risk", "1"),
        title="Risk: client/security SCADA access",
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[{"chunk_id": "chunk_1"}],
        metadata={"severity": "high"},
    )

    output_path = write_obsidian_entity(vault_path=tmp_path, entity=entity)

    assert output_path.exists()
    assert output_path.relative_to(tmp_path).as_posix() == (
        _expected_entity_path("Risks", "Risk client security SCADA access", "risk", "1")
    )
    assert "# Risk: client/security SCADA access" in output_path.read_text()


def test_write_obsidian_entities_writes_multiple_files(tmp_path) -> None:
    entities = [
        ObsidianEntity(
            entity_type="task",
            **_entity_key("task", "1"),
            title="TODO: send proposal",
            source_document_id="doc_1",
            chunk_id="chunk_1",
            evidence_refs=[{"chunk_id": "chunk_1"}],
            metadata={"status": "open"},
        ),
        ObsidianEntity(
            entity_type="decision",
            **_entity_key("decision", "1"),
            title="Decision: start read-only",
            source_document_id="doc_1",
            chunk_id="chunk_2",
            evidence_refs=[{"chunk_id": "chunk_2"}],
            metadata={"owner": "Founder"},
        ),
    ]

    output_paths = write_obsidian_entities(vault_path=tmp_path, entities=entities)

    assert len(output_paths) == 2
    assert (tmp_path / _expected_entity_path("Tasks", "TODO send proposal", "task", "1")).exists()
    assert (tmp_path / _expected_entity_path("Decisions", "Decision start read-only", "decision", "1")).exists()

def test_score_to_dict_maps_score_fields() -> None:
    score = SimpleNamespace(
        entity_type="risk",
        **_entity_key("7"),
        importance_score=1.0,
        urgency_score=0.35,
        risk_score=0.9,
        confidence_score=0.82,
        attention_score=0.73,
        reasons=[{"code": "security_or_access_context"}],
        evidence_refs=[{"chunk_id": "chunk_1"}],
    )

    result = score_to_dict(score)

    assert result == {
        "entity_type": "risk",
        "entity_id": "7",
        "importance_score": 1.0,
        "urgency_score": 0.35,
        "risk_score": 0.9,
        "confidence_score": 0.82,
        "attention_score": 0.73,
        "reasons": [{"code": "security_or_access_context"}],
        "evidence_refs": [{"chunk_id": "chunk_1"}],
    }


def test_task_to_obsidian_entity_maps_existing_task_fields() -> None:
    task = SimpleNamespace(
        id=11,
        title="TODO: send proposal to client next week.",
        status="open",
        item_type="task",
        owner="Founder",
        due_date="2026-04-27",
        confidence=0.9,
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[{"chunk_id": "chunk_1"}],
    )

    entity = task_to_obsidian_entity(task=task)

    assert entity.entity_type == "task"
    assert entity.entity_id == "11"
    assert entity.title == "TODO: send proposal to client next week."
    assert entity.source_document_id == "doc_1"
    assert entity.chunk_id == "chunk_1"
    assert entity.evidence_refs == [{"chunk_id": "chunk_1"}]
    assert entity.metadata["status"] == "open"
    assert entity.metadata["item_type"] == "task"
    assert entity.metadata["owner"] == "Founder"
    assert entity.metadata["due_date"] == "2026-04-27"
    assert entity.metadata["confidence"] == 0.9
    assert entity.score is None


def test_risk_to_obsidian_entity_maps_existing_risk_fields() -> None:
    risk = SimpleNamespace(
        id=12,
        title="Risk: client is worried about IT security and SCADA access.",
        severity="high",
        confidence=0.8,
        source_document_id="doc_1",
        chunk_id="chunk_2",
        evidence_refs=[{"chunk_id": "chunk_2"}],
    )

    score = SimpleNamespace(
        entity_type="risk",
        **_entity_key("12"),
        importance_score=1.0,
        urgency_score=0.35,
        risk_score=0.9,
        confidence_score=0.8,
        attention_score=0.73,
        reasons=[{"code": "high_severity_risk"}],
        evidence_refs=[{"chunk_id": "chunk_2"}],
    )

    entity = risk_to_obsidian_entity(risk=risk, score=score)

    assert entity.entity_type == "risk"
    assert entity.entity_id == "12"
    assert entity.metadata["severity"] == "high"
    assert entity.metadata["confidence"] == 0.8
    assert entity.score is not None
    assert entity.score["attention_score"] == 0.73


def test_decision_to_obsidian_entity_maps_existing_decision_fields() -> None:
    decision = SimpleNamespace(
        id=13,
        title="Decision: start with read-only data collection.",
        decision="Start with read-only data collection before write actions.",
        owner=None,
        confidence=0.95,
        source_document_id="doc_1",
        chunk_id="chunk_3",
        evidence_refs=[{"chunk_id": "chunk_3"}],
    )

    entity = decision_to_obsidian_entity(decision=decision)

    assert entity.entity_type == "decision"
    assert entity.entity_id == "13"
    assert entity.metadata["decision"] == (
        "Start with read-only data collection before write actions."
    )
    assert entity.metadata["owner"] is None
    assert entity.metadata["confidence"] == 0.95


def test_entity_mapping_rejects_missing_id() -> None:
    task = SimpleNamespace(
        title="TODO: missing id",
        evidence_refs=[{"chunk_id": "chunk_1"}],
    )

    try:
        task_to_obsidian_entity(task=task)
    except ValueError as exc:
        assert str(exc) == "Cannot export entity without an id"
    else:
        raise AssertionError("Expected ValueError for entity without id")

def test_render_vault_index_markdown_counts_exported_entities() -> None:
    entities = [
        ObsidianEntity(
            entity_type="task",
            **_entity_key("task", "1"),
            title="TODO: send proposal",
            source_document_id="doc_1",
            chunk_id="chunk_1",
            evidence_refs=[{"chunk_id": "chunk_1"}],
            metadata={},
        ),
        ObsidianEntity(
            entity_type="risk",
            **_entity_key("risk", "1"),
            title="Risk: client security concern",
            source_document_id="doc_1",
            chunk_id="chunk_2",
            evidence_refs=[{"chunk_id": "chunk_2"}],
            metadata={},
        ),
    ]

    markdown = render_vault_index_markdown(entities)

    assert "# FounderOS Vault Export" in markdown
    assert "[Tasks](Tasks/_Index.md): 1" in markdown
    assert "[Risks](Risks/_Index.md): 1" in markdown
    assert "[Decisions](Decisions/_Index.md): 0" in markdown
    assert "Obsidian is read-only export" in markdown


def test_render_entity_index_markdown_orders_by_attention_score() -> None:
    high_attention = ObsidianEntity(
        entity_type="risk",
        **_entity_key("risk", "1"),
        title="Risk: high attention",
        source_document_id="doc_1",
        chunk_id="chunk_1",
        evidence_refs=[{"chunk_id": "chunk_1"}],
        metadata={},
        score={"attention_score": 0.9},
    )
    low_attention = ObsidianEntity(
        entity_type="risk",
        **_entity_key("risk", "2"),
        title="Risk: low attention",
        source_document_id="doc_2",
        chunk_id="chunk_2",
        evidence_refs=[{"chunk_id": "chunk_2"}],
        metadata={},
        score={"attention_score": 0.2},
    )

    markdown = render_entity_index_markdown(
        entity_type="risk",
        title="Risks",
        entities=[low_attention, high_attention],
    )

    assert "| Attention | Title | Source document | Chunk |" in markdown
    assert markdown.index("Risk: high attention") < markdown.index("Risk: low attention")
    expected_link = (
        "[Risk: high attention]"
        f"(<{_expected_entity_path('Risks', 'Risk high attention', 'risk', '1')}>)"
    )
    assert expected_link in markdown


def test_write_obsidian_index_files_writes_vault_navigation(tmp_path) -> None:
    entities = [
        ObsidianEntity(
            entity_type="decision",
            **_entity_key("decision", "1"),
            title="Decision: start read-only",
            source_document_id="doc_1",
            chunk_id="chunk_1",
            evidence_refs=[{"chunk_id": "chunk_1"}],
            metadata={},
            score={"attention_score": 0.5},
        )
    ]

    output_paths = write_obsidian_index_files(
        vault_path=tmp_path,
        entities=entities,
    )

    relative_paths = {
        output_path.relative_to(tmp_path).as_posix()
        for output_path in output_paths
    }

    assert relative_paths == {
        "FounderOS.md",
        "Tasks/_Index.md",
        "Risks/_Index.md",
        "Decisions/_Index.md",
    }
    assert "# FounderOS Vault Export" in (tmp_path / "FounderOS.md").read_text()
    assert "Decision: start read-only" in (
        tmp_path / "Decisions/_Index.md"
    ).read_text()


def test_write_obsidian_index_files_skips_empty_export(tmp_path) -> None:
    output_paths = write_obsidian_index_files(
        vault_path=tmp_path,
        entities=[],
    )

    assert output_paths == []
    assert not (tmp_path / "FounderOS.md").exists()

def test_write_obsidian_entities_does_not_overwrite_duplicate_titles(tmp_path) -> None:
    entities = [
        ObsidianEntity(
            entity_type="task",
            **_entity_key("task", "1"),
            title="TODO: same title",
            source_document_id="doc_1",
            chunk_id="chunk_1",
            evidence_refs=[{"chunk_id": "chunk_1"}],
            metadata={"status": "open"},
        ),
        ObsidianEntity(
            entity_type="task",
            **_entity_key("task", "2"),
            title="TODO: same title",
            source_document_id="doc_2",
            chunk_id="chunk_2",
            evidence_refs=[{"chunk_id": "chunk_2"}],
            metadata={"status": "open"},
        ),
    ]

    output_paths = write_obsidian_entities(vault_path=tmp_path, entities=entities)

    relative_paths = {
        output_path.relative_to(tmp_path).as_posix()
        for output_path in output_paths
    }

    assert relative_paths == {
        _expected_entity_path("Tasks", "TODO same title", "task", "1"),
        _expected_entity_path("Tasks", "TODO same title", "task", "2"),
    }
    assert len(list((tmp_path / "Tasks").glob("TODO same title*.md"))) == 2
