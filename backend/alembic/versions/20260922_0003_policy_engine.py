"""Add versioned policies and durable policy decisions.

Revision ID: 20260922_0003
Revises: 20260922_0002
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0003"
down_revision: str | None = "20260922_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_policies_status"),
        sa.CheckConstraint("priority >= 0 AND priority <= 10000", name="ck_policies_priority"),
        sa.CheckConstraint("current_version >= 1", name="ck_policies_current_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_policies_org_name"),
    )
    op.create_index("ix_policies_org_status", "policies", ["organization_id", "status"])

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_policy_versions_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_versions_number"),
    )
    op.create_index("ix_policy_versions_policy_id", "policy_versions", ["policy_id"])

    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("requested_tool_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("environment", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=True),
        sa.Column(
            "matched_policy_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "outcome IN ('allow', 'deny', 'require_approval')",
            name="ck_policy_decisions_outcome",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["permission_id"], ["agent_permissions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "idempotency_key",
            name="uq_policy_decisions_idempotency",
        ),
    )
    op.create_index(
        "ix_policy_decisions_org_created",
        "policy_decisions",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_policy_decisions_org_created", table_name="policy_decisions")
    op.drop_table("policy_decisions")
    op.drop_index("ix_policy_versions_policy_id", table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index("ix_policies_org_status", table_name="policies")
    op.drop_table("policies")
