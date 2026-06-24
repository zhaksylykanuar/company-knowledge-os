"""drop Lineage-2 legacy tables (entities graph + knowledge-graph generation)

Revision ID: e1a2b3c4d5f6
Revises: f6b7c8d9e0a1
Create Date: 2026-06-24 00:00:00.000000

Purge of the frozen Lineage-2 substrate (DEC-029). Drops the entities graph,
identity satellites, knowledge/RAG, attention, second-opinion, gmail, share-pack,
source-control, declaration, status, and extraction tables. The temporary
read-substrate (source_events, normalized_activity_items, ingested_events) is
intentionally retained until FOS-009 (DEC-030); audit_logs and the canonical
tables are retained.

DROP ... CASCADE is order-independent; no retained/canonical table has a foreign
key into any dropped table (verified by the purge import-graph audit). This
migration is intentionally irreversible: the deleted ORM models live only in git
history (recovery tag `pre-purge-20260624`), so a precise downgrade cannot be
reconstructed here.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "f6b7c8d9e0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TABLES = (
    # entities graph + identity satellites
    "entity_links",
    "entity_aliases",
    "entity_source_accounts",
    "entities",
    # knowledge / RAG
    "knowledge_scores",
    "document_chunks",
    "source_documents",
    # second opinion
    "second_opinion_findings",
    # gmail
    "gmail_attachments",
    "gmail_messages",
    "email_thread_states",
    "gmail_threads",
    # agent foundation
    "agent_proposals",
    "metric_snapshots",
    "agent_run_logs",
    "data_availability",
    # attention triage
    "attention_triage_feedback",
    "attention_triage_results",
    # declarations / status / share packs
    "founder_declarations",
    "status_snapshots",
    "share_packs",
    # source control center
    "source_run_requests",
    "source_control_states",
    # extraction outputs
    "extracted_tasks",
    "extracted_decisions",
    "extracted_risks",
    "agent_runs",
)


def upgrade() -> None:
    """Drop all frozen Lineage-2 tables."""

    for table in LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def downgrade() -> None:
    """Irreversible: legacy models were deleted in the purge.

    Restore from git (tag ``pre-purge-20260624``) to recover the models and a
    matching schema, then re-run the original creating migrations.
    """

    raise NotImplementedError(
        "Lineage-2 purge (e1a2b3c4d5f6) is irreversible; restore from tag "
        "pre-purge-20260624 to recover the dropped tables."
    )
