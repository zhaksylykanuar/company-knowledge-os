"""add company memory event policy fields

Revision ID: d8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-27 00:00:00.000000

Lifecycle facts are verified workspace-canonical records. The explicit policy
columns make their confidence, access and retention contract inspectable.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_memory_events",
        sa.Column(
            "confidence",
            sa.Float(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "company_memory_events",
        sa.Column(
            "access_scope",
            sa.String(length=20),
            server_default="workspace",
            nullable=False,
        ),
    )
    op.add_column(
        "company_memory_events",
        sa.Column(
            "sensitivity",
            sa.String(length=20),
            server_default="internal",
            nullable=False,
        ),
    )
    op.add_column(
        "company_memory_events",
        sa.Column(
            "retention_policy",
            sa.String(length=40),
            server_default="workspace_canonical",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_company_memory_events_confidence",
        "company_memory_events",
        "confidence >= 0 and confidence <= 1",
    )
    op.create_check_constraint(
        "ck_company_memory_events_access_scope",
        "company_memory_events",
        "access_scope = 'workspace'",
    )
    op.create_check_constraint(
        "ck_company_memory_events_sensitivity",
        "company_memory_events",
        "sensitivity = 'internal'",
    )
    op.create_check_constraint(
        "ck_company_memory_events_retention_policy",
        "company_memory_events",
        "retention_policy = 'workspace_canonical'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_company_memory_events_retention_policy",
        "company_memory_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_company_memory_events_sensitivity",
        "company_memory_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_company_memory_events_access_scope",
        "company_memory_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_company_memory_events_confidence",
        "company_memory_events",
        type_="check",
    )
    op.drop_column("company_memory_events", "retention_policy")
    op.drop_column("company_memory_events", "sensitivity")
    op.drop_column("company_memory_events", "access_scope")
    op.drop_column("company_memory_events", "confidence")
