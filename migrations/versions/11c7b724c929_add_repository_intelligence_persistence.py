"""add repository intelligence persistence

Revision ID: 11c7b724c929
Revises: c6f41d8e29ab
Create Date: 2026-07-31 13:34:26.390131

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "11c7b724c929"
down_revision: Union[str, Sequence[str], None] = "c6f41d8e29ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REPOSITORY_INTELLIGENCE_TABLES = (
    "repository_evidence_links",
    "repository_contradictions",
    "repository_relationships",
    "repository_facts",
    "repository_audit_findings",
    "repository_audit_runs",
    "repository_analysis_jobs",
)


def _assert_repository_intelligence_tables_empty() -> None:
    connection = op.get_bind()
    for table_name in _REPOSITORY_INTELLIGENCE_TABLES:
        connection.execute(
            sa.text(f'LOCK TABLE "{table_name}" IN ACCESS EXCLUSIVE MODE')
        )
    non_empty = [
        table_name
        for table_name in _REPOSITORY_INTELLIGENCE_TABLES
        if connection.execute(
            sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')
        ).scalar_one()
    ]
    if non_empty:
        raise RuntimeError(
            "refusing to downgrade non-empty Repository Intelligence tables"
        )


def upgrade() -> None:
    op.add_column(
        "evidence_refs",
        sa.Column("evidence_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evidence_refs",
        sa.Column("evidence_kind", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "evidence_refs",
        sa.Column("evidence_source", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "evidence_refs",
        sa.Column("selector", sa.String(length=500), nullable=True),
    )
    op.create_check_constraint(
        "ck_evidence_refs_kind",
        "evidence_refs",
        "evidence_kind is null or evidence_kind in ("
        "'repository_metadata','repository_file','repository_manifest',"
        "'repository_symbol','repository_workflow','repository_dependency',"
        "'repository_deployment','repository_test_result',"
        "'repository_scanner_result','github_pull_request','github_issue',"
        "'jira_issue','document'"
        ")",
    )
    op.create_check_constraint(
        "ck_evidence_refs_source",
        "evidence_refs",
        "evidence_source is null or evidence_source in "
        "('github','jira','gmail','drive','internal')",
    )
    op.create_unique_constraint(
        "uq_evidence_refs_workspace_evidence_key",
        "evidence_refs",
        ["workspace_id", "evidence_key"],
    )
    op.create_unique_constraint(
        "uq_evidence_refs_workspace_id_id",
        "evidence_refs",
        ["workspace_id", "id"],
    )

    op.create_table('repository_analysis_jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=128), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('target_status', sa.String(length=20), nullable=False),
    sa.Column('commit_sha', sa.String(length=40), nullable=True),
    sa.Column('metadata_snapshot_id', sa.String(length=255), nullable=True),
    sa.Column('audit_level', sa.String(length=2), nullable=False),
    sa.Column('profile', sa.String(length=80), nullable=False),
    sa.Column('policy_hash', sa.String(length=64), nullable=False),
    sa.Column('engine_version', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
    sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('lease_owner', sa.String(length=64), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_code', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(target_status = 'exact' and commit_sha is not null and metadata_snapshot_id is null) or (target_status = 'unavailable' and commit_sha is null and metadata_snapshot_id is not null)", name='ck_repository_analysis_jobs_target_shape'),
    sa.CheckConstraint("audit_level = 'L0' or target_status = 'exact'", name='ck_repository_analysis_jobs_exact_deep_target'),
    sa.CheckConstraint("audit_level in ('L0','L1','L2')", name='ck_repository_analysis_jobs_audit_level'),
    sa.CheckConstraint("commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'", name='ck_repository_analysis_jobs_commit_sha'),
    sa.CheckConstraint("completed_at is null or status in ('succeeded','failed','partial','cancelled')", name='ck_repository_analysis_jobs_completed_status'),
    sa.CheckConstraint("policy_hash ~ '^[0-9a-f]{64}$' and request_hash ~ '^[0-9a-f]{64}$'", name='ck_repository_analysis_jobs_hashes'),
    sa.CheckConstraint("status in ('queued','running','succeeded','failed','partial','cancelled')", name='ck_repository_analysis_jobs_status'),
    sa.CheckConstraint("target_status in ('exact','unavailable')", name='ck_repository_analysis_jobs_target_status'),
    sa.CheckConstraint('(lease_owner is null and lease_expires_at is null) or (lease_owner is not null and lease_expires_at is not null)', name='ck_repository_analysis_jobs_lease_shape'),
    sa.CheckConstraint('attempt_count >= 0 and max_attempts >= 1 and attempt_count <= max_attempts', name='ck_repository_analysis_jobs_attempts'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_analysis_jobs_workspace_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name='fk_repository_analysis_jobs_requested_by_user_id', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_analysis_jobs_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_analysis_jobs_workspace_id_id'),
    sa.UniqueConstraint('workspace_id', 'idempotency_key', name='uq_repository_analysis_jobs_workspace_idempotency_key'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'id', name='uq_repository_analysis_jobs_workspace_repository_id')
    )
    op.create_index('ix_repository_analysis_jobs_claim', 'repository_analysis_jobs', ['workspace_id', 'status', 'next_attempt_at', 'lease_expires_at'], unique=False)
    op.create_index('ix_repository_analysis_jobs_repository_created', 'repository_analysis_jobs', ['workspace_id', 'repository_id', 'created_at'], unique=False)
    op.create_table('repository_audit_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.UUID(), nullable=False),
    sa.Column('run_key', sa.String(length=64), nullable=False),
    sa.Column('result_hash', sa.String(length=64), nullable=False),
    sa.Column('target_status', sa.String(length=20), nullable=False),
    sa.Column('commit_sha', sa.String(length=40), nullable=True),
    sa.Column('metadata_snapshot_id', sa.String(length=255), nullable=True),
    sa.Column('audit_level', sa.String(length=2), nullable=False),
    sa.Column('profile', sa.String(length=80), nullable=False),
    sa.Column('policy_hash', sa.String(length=64), nullable=False),
    sa.Column('engine_version', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('coverage_status', sa.String(length=20), nullable=False),
    sa.Column('coverage', sa.JSON(), nullable=False),
    sa.Column('reconciliation_applied', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('limitations', sa.JSON(), nullable=False),
    sa.Column('artifact_manifest', sa.JSON(), nullable=False),
    sa.Column('artifact_manifest_hash', sa.String(length=64), nullable=False),
    sa.Column('artifact_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('artifact_purged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retention_policy', sa.String(length=40), server_default='workspace_canonical', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'succeeded' and coverage_status = 'complete') or (status <> 'succeeded' and coverage_status = 'partial')", name='ck_repository_audit_runs_status_coverage'),
    sa.CheckConstraint("(target_status = 'exact' and commit_sha is not null and metadata_snapshot_id is null) or (target_status = 'unavailable' and commit_sha is null and metadata_snapshot_id is not null)", name='ck_repository_audit_runs_target_shape'),
    sa.CheckConstraint("audit_level = 'L0' or target_status = 'exact'", name='ck_repository_audit_runs_exact_deep_target'),
    sa.CheckConstraint("audit_level in ('L0','L1','L2')", name='ck_repository_audit_runs_audit_level'),
    sa.CheckConstraint("commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'", name='ck_repository_audit_runs_commit_sha'),
    sa.CheckConstraint("coverage_status in ('complete','partial')", name='ck_repository_audit_runs_coverage_status'),
    sa.CheckConstraint("not reconciliation_applied or (status = 'succeeded' and coverage_status = 'complete')", name='ck_repository_audit_runs_reconciliation'),
    sa.CheckConstraint("policy_hash ~ '^[0-9a-f]{64}$'", name='ck_repository_audit_runs_policy_hash'),
    sa.CheckConstraint("result_hash ~ '^[0-9a-f]{64}$' and run_key ~ '^[0-9a-f]{64}$' and artifact_manifest_hash ~ '^[0-9a-f]{64}$'", name='ck_repository_audit_runs_hashes'),
    sa.CheckConstraint("retention_policy = 'workspace_canonical'", name='ck_repository_audit_runs_retention_policy'),
    sa.CheckConstraint("status in ('succeeded','partial','failed','cancelled')", name='ck_repository_audit_runs_status'),
    sa.CheckConstraint("target_status in ('exact','unavailable')", name='ck_repository_audit_runs_target_status'),
    sa.CheckConstraint('completed_at >= started_at', name='ck_repository_audit_runs_time_order'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'job_id'], ['repository_analysis_jobs.workspace_id', 'repository_analysis_jobs.repository_id', 'repository_analysis_jobs.id'], name='fk_repository_audit_runs_workspace_repository_job', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_audit_runs_workspace_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'source_record_id'], ['source_records.workspace_id', 'source_records.id'], name='fk_repository_audit_runs_workspace_source_record', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_audit_runs_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_audit_runs_workspace_id_id'),
    sa.UniqueConstraint('workspace_id', 'job_id', name='uq_repository_audit_runs_workspace_job_id'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'id', name='uq_repository_audit_runs_workspace_repository_id'),
    sa.UniqueConstraint('workspace_id', 'source_record_id', name='uq_repository_audit_runs_workspace_source_record_id')
    )
    op.create_index('ix_repository_audit_runs_artifact_expiry', 'repository_audit_runs', ['workspace_id', 'artifact_expires_at'], unique=False, postgresql_where=sa.text('artifact_purged_at IS NULL'))
    op.create_index('ix_repository_audit_runs_repository_completed', 'repository_audit_runs', ['workspace_id', 'repository_id', 'completed_at'], unique=False)
    op.create_index('ix_repository_audit_runs_run_key', 'repository_audit_runs', ['workspace_id', 'run_key'], unique=False)
    op.create_table('repository_audit_findings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('finding_id', sa.String(length=128), nullable=False),
    sa.Column('rule_id', sa.String(length=128), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=30), server_default='new', nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('recommended_next_step', sa.String(length=1000), nullable=True),
    sa.Column('first_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('last_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by_user_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status in ('accepted_risk','false_positive') and decided_by_user_id is not null and decided_at is not null) or (status not in ('accepted_risk','false_positive'))", name='ck_repository_audit_findings_human_decision'),
    sa.CheckConstraint("severity in ('info','low','medium','high','critical')", name='ck_repository_audit_findings_severity'),
    sa.CheckConstraint("status in ('new','open','resolved','regressed','accepted_risk','false_positive','insufficient_evidence')", name='ck_repository_audit_findings_status'),
    sa.CheckConstraint('confidence >= 0 and confidence <= 1', name='ck_repository_audit_findings_confidence'),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], name='fk_repository_audit_findings_decided_by_user_id', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'first_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_audit_findings_workspace_repository_first_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'last_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_audit_findings_workspace_repository_last_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_audit_findings_workspace_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_audit_findings_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_audit_findings_workspace_id_id'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'fingerprint', name='uq_repository_audit_findings_workspace_repository_fingerprint'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'id', name='uq_repository_audit_findings_workspace_repository_id')
    )
    op.create_index('ix_repository_audit_findings_workspace_severity', 'repository_audit_findings', ['workspace_id', 'severity'], unique=False)
    op.create_index('ix_repository_audit_findings_workspace_status', 'repository_audit_findings', ['workspace_id', 'status'], unique=False)
    op.create_table('repository_facts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('claim_id', sa.String(length=128), nullable=False),
    sa.Column('fact_type', sa.String(length=80), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('claim_status', sa.String(length=30), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('lifecycle_status', sa.String(length=20), server_default='current', nullable=False),
    sa.Column('first_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('last_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('stale_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('human_resolution_status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('resolved_by_user_id', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(human_resolution_status = 'pending' and resolved_by_user_id is null and resolved_at is null) or (human_resolution_status in ('confirmed','rejected') and resolved_by_user_id is not null and resolved_at is not null)", name='ck_repository_facts_human_resolution_provenance'),
    sa.CheckConstraint("claim_status in ('observed','inferred','insufficient_evidence')", name='ck_repository_facts_claim_status'),
    sa.CheckConstraint("human_resolution_status in ('pending','confirmed','rejected')", name='ck_repository_facts_human_resolution_status'),
    sa.CheckConstraint("lifecycle_status in ('current','stale')", name='ck_repository_facts_lifecycle_status'),
    sa.CheckConstraint('confidence >= 0 and confidence <= 1', name='ck_repository_facts_confidence'),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], name='fk_repository_facts_resolved_by_user_id', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'first_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_facts_workspace_repository_first_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'last_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_facts_workspace_repository_last_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_facts_workspace_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_facts_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_facts_workspace_id_id'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'fingerprint', name='uq_repository_facts_workspace_repository_fingerprint'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'id', name='uq_repository_facts_workspace_repository_id')
    )
    op.create_index('ix_repository_facts_workspace_lifecycle', 'repository_facts', ['workspace_id', 'lifecycle_status'], unique=False)
    op.create_table('repository_relationships',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('from_repository_id', sa.UUID(), nullable=False),
    sa.Column('to_repository_id', sa.UUID(), nullable=True),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('relationship_type', sa.String(length=80), nullable=False),
    sa.Column('target_provider', sa.String(length=40), nullable=False),
    sa.Column('target_external_id', sa.String(length=255), nullable=False),
    sa.Column('target_full_name', sa.String(length=500), nullable=False),
    sa.Column('resolution_status', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.String(length=1000), nullable=True),
    sa.Column('claim_status', sa.String(length=20), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('lifecycle_status', sa.String(length=20), server_default='current', nullable=False),
    sa.Column('first_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('last_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('stale_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('human_resolution_status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('resolved_by_user_id', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(human_resolution_status = 'pending' and resolved_by_user_id is null and resolved_at is null) or (human_resolution_status in ('confirmed','rejected') and resolved_by_user_id is not null and resolved_at is not null)", name='ck_repository_relationships_human_resolution_provenance'),
    sa.CheckConstraint("(resolution_status = 'canonical' and to_repository_id is not null) or (resolution_status = 'candidate' and to_repository_id is null)", name='ck_repository_relationships_resolution_shape'),
    sa.CheckConstraint("claim_status in ('observed','inferred')", name='ck_repository_relationships_claim_status'),
    sa.CheckConstraint("human_resolution_status in ('pending','confirmed','rejected')", name='ck_repository_relationships_human_resolution_status'),
    sa.CheckConstraint("lifecycle_status in ('current','stale')", name='ck_repository_relationships_lifecycle_status'),
    sa.CheckConstraint("relationship_type in ('calls_api_of','imports_package_from','consumes_event_from','deployed_by','uses_image_from','generates_client_for','tests','documents','replaces','forked_from','duplicate_candidate_of','operationally_coupled_with','shares_schema_with','shares_database_with','owns_migrations_for')", name='ck_repository_relationships_type'),
    sa.CheckConstraint("resolution_status in ('canonical','candidate')", name='ck_repository_relationships_resolution_status'),
    sa.CheckConstraint('confidence >= 0 and confidence <= 1', name='ck_repository_relationships_confidence'),
    sa.CheckConstraint('to_repository_id is null or from_repository_id <> to_repository_id', name='ck_repository_relationships_no_self_edge'),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], name='fk_repository_relationships_resolved_by_user_id', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'from_repository_id', 'first_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_relationships_workspace_source_first_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'from_repository_id', 'last_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_relationships_workspace_source_last_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'from_repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_relationships_workspace_from_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'to_repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_relationships_workspace_to_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_relationships_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'from_repository_id', 'fingerprint', name='uq_repository_relationships_workspace_from_fingerprint'),
    sa.UniqueConstraint('workspace_id', 'from_repository_id', 'id', name='uq_repository_relationships_workspace_source_id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_relationships_workspace_id_id')
    )
    op.create_index('ix_repository_relationships_workspace_lifecycle', 'repository_relationships', ['workspace_id', 'lifecycle_status'], unique=False)
    op.create_index('ix_repository_relationships_workspace_target', 'repository_relationships', ['workspace_id', 'to_repository_id'], unique=False)
    op.create_table('repository_contradictions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('contradiction_id', sa.String(length=128), nullable=False),
    sa.Column('left_fact_id', sa.UUID(), nullable=False),
    sa.Column('right_fact_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='current', nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('summary', sa.String(length=1000), nullable=False),
    sa.Column('first_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('last_seen_run_id', sa.UUID(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status in ('current','resolved')", name='ck_repository_contradictions_status'),
    sa.CheckConstraint('confidence >= 0 and confidence <= 1', name='ck_repository_contradictions_confidence'),
    sa.CheckConstraint('left_fact_id <> right_fact_id', name='ck_repository_contradictions_distinct_facts'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'first_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_contradictions_workspace_repository_first_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'last_seen_run_id'], ['repository_audit_runs.workspace_id', 'repository_audit_runs.repository_id', 'repository_audit_runs.id'], name='fk_repository_contradictions_workspace_repository_last_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'left_fact_id'], ['repository_facts.workspace_id', 'repository_facts.repository_id', 'repository_facts.id'], name='fk_repository_contradictions_workspace_repository_left_fact', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id', 'right_fact_id'], ['repository_facts.workspace_id', 'repository_facts.repository_id', 'repository_facts.id'], name='fk_repository_contradictions_workspace_repository_right_fact', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'repository_id'], ['repositories.workspace_id', 'repositories.id'], name='fk_repository_contradictions_workspace_repository', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_contradictions_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'id', name='uq_repository_contradictions_workspace_id_id'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'fingerprint', name='uq_repository_contradictions_workspace_repository_fingerprint'),
    sa.UniqueConstraint('workspace_id', 'repository_id', 'id', name='uq_repository_contradictions_workspace_repository_id')
    )
    op.create_index('ix_repository_contradictions_workspace_status', 'repository_contradictions', ['workspace_id', 'status'], unique=False)
    op.create_table('repository_evidence_links',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('evidence_ref_id', sa.UUID(), nullable=False),
    sa.Column('evidence_role', sa.String(length=20), nullable=False),
    sa.Column('fact_id', sa.UUID(), nullable=True),
    sa.Column('relationship_id', sa.UUID(), nullable=True),
    sa.Column('finding_id', sa.UUID(), nullable=True),
    sa.Column('contradiction_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("evidence_role in ('supporting','contradicting')", name='ck_repository_evidence_links_role'),
    sa.CheckConstraint('num_nonnulls(fact_id,relationship_id,finding_id,contradiction_id) = 1', name='ck_repository_evidence_links_one_parent'),
    sa.ForeignKeyConstraint(['workspace_id', 'contradiction_id'], ['repository_contradictions.workspace_id', 'repository_contradictions.id'], name='fk_repository_evidence_links_workspace_contradiction', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'evidence_ref_id'], ['evidence_refs.workspace_id', 'evidence_refs.id'], name='fk_repository_evidence_links_workspace_evidence', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'fact_id'], ['repository_facts.workspace_id', 'repository_facts.id'], name='fk_repository_evidence_links_workspace_fact', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'finding_id'], ['repository_audit_findings.workspace_id', 'repository_audit_findings.id'], name='fk_repository_evidence_links_workspace_finding', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'relationship_id'], ['repository_relationships.workspace_id', 'repository_relationships.id'], name='fk_repository_evidence_links_workspace_relationship', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_repository_evidence_links_workspace_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_repository_evidence_links_contradiction', 'repository_evidence_links', ['workspace_id', 'contradiction_id', 'evidence_ref_id', 'evidence_role'], unique=True, postgresql_where=sa.text('contradiction_id IS NOT NULL'))
    op.create_index('uq_repository_evidence_links_fact', 'repository_evidence_links', ['workspace_id', 'fact_id', 'evidence_ref_id', 'evidence_role'], unique=True, postgresql_where=sa.text('fact_id IS NOT NULL'))
    op.create_index('uq_repository_evidence_links_finding', 'repository_evidence_links', ['workspace_id', 'finding_id', 'evidence_ref_id', 'evidence_role'], unique=True, postgresql_where=sa.text('finding_id IS NOT NULL'))
    op.create_index('uq_repository_evidence_links_relationship', 'repository_evidence_links', ['workspace_id', 'relationship_id', 'evidence_ref_id', 'evidence_role'], unique=True, postgresql_where=sa.text('relationship_id IS NOT NULL'))
def downgrade() -> None:
    _assert_repository_intelligence_tables_empty()

    op.drop_index('uq_repository_evidence_links_relationship', table_name='repository_evidence_links', postgresql_where=sa.text('relationship_id IS NOT NULL'))
    op.drop_index('uq_repository_evidence_links_finding', table_name='repository_evidence_links', postgresql_where=sa.text('finding_id IS NOT NULL'))
    op.drop_index('uq_repository_evidence_links_fact', table_name='repository_evidence_links', postgresql_where=sa.text('fact_id IS NOT NULL'))
    op.drop_index('uq_repository_evidence_links_contradiction', table_name='repository_evidence_links', postgresql_where=sa.text('contradiction_id IS NOT NULL'))
    op.drop_table('repository_evidence_links')
    op.drop_index('ix_repository_contradictions_workspace_status', table_name='repository_contradictions')
    op.drop_table('repository_contradictions')
    op.drop_index('ix_repository_relationships_workspace_target', table_name='repository_relationships')
    op.drop_index('ix_repository_relationships_workspace_lifecycle', table_name='repository_relationships')
    op.drop_table('repository_relationships')
    op.drop_index('ix_repository_facts_workspace_lifecycle', table_name='repository_facts')
    op.drop_table('repository_facts')
    op.drop_index('ix_repository_audit_findings_workspace_status', table_name='repository_audit_findings')
    op.drop_index('ix_repository_audit_findings_workspace_severity', table_name='repository_audit_findings')
    op.drop_table('repository_audit_findings')
    op.drop_index('ix_repository_audit_runs_run_key', table_name='repository_audit_runs')
    op.drop_index('ix_repository_audit_runs_repository_completed', table_name='repository_audit_runs')
    op.drop_index('ix_repository_audit_runs_artifact_expiry', table_name='repository_audit_runs', postgresql_where=sa.text('artifact_purged_at IS NULL'))
    op.drop_table('repository_audit_runs')
    op.drop_index('ix_repository_analysis_jobs_repository_created', table_name='repository_analysis_jobs')
    op.drop_index('ix_repository_analysis_jobs_claim', table_name='repository_analysis_jobs')
    op.drop_table('repository_analysis_jobs')
    op.drop_constraint(
        "uq_evidence_refs_workspace_id_id",
        "evidence_refs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_evidence_refs_workspace_evidence_key",
        "evidence_refs",
        type_="unique",
    )
    op.drop_constraint(
        "ck_evidence_refs_source",
        "evidence_refs",
        type_="check",
    )
    op.drop_constraint(
        "ck_evidence_refs_kind",
        "evidence_refs",
        type_="check",
    )
    op.drop_column("evidence_refs", "selector")
    op.drop_column("evidence_refs", "evidence_source")
    op.drop_column("evidence_refs", "evidence_kind")
    op.drop_column("evidence_refs", "evidence_key")
