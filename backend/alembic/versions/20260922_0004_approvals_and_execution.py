"""Add approval workflow and controlled tool executions.

Revision ID: 20260922_0004
Revises: 20260922_0003
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0004"
down_revision: str | None = "20260922_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "adapter_name",
            sa.String(length=80),
            server_default="safe_echo",
            nullable=False,
        ),
    )
    op.add_column(
        "tools",
        sa.Column("adapter_version", sa.String(length=40), server_default="1", nullable=False),
    )
    op.add_column(
        "tools",
        sa.Column(
            "execution_timeout_seconds",
            sa.Integer(),
            server_default="10",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_tools_execution_timeout",
        "tools",
        "execution_timeout_seconds >= 1 AND execution_timeout_seconds <= 60",
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("requested_tool_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_approval_requests_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_id"], ["policy_decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id"),
    )
    op.create_index(
        "ix_approval_requests_org_status",
        "approval_requests",
        ["organization_id", "status"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO approval_requests (
                id,
                organization_id,
                decision_id,
                agent_id,
                requested_tool_id,
                status,
                expires_at,
                decided_at,
                decision_reason,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                organization_id,
                id,
                agent_id,
                requested_tool_id,
                'expired',
                now(),
                now(),
                'Decision predates the approval workflow; evaluate the request again',
                now(),
                now()
            FROM policy_decisions
            WHERE outcome = 'require_approval'
            """
        )
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("environment", sa.String(length=80), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("adapter_name", sa.String(length=80), nullable=False),
        sa.Column("adapter_version", sa.String(length=40), nullable=False),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('authorized', 'queued', 'running', 'succeeded', 'failed', "
            "'timed_out', 'cancelled')",
            name="ck_tool_executions_status",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_id"], ["policy_decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id"),
        sa.UniqueConstraint("decision_id"),
    )
    op.create_index(
        "ix_tool_executions_org_created",
        "tool_executions",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "execution_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "details_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('authorized', 'queued', 'running', 'succeeded', 'failed', "
            "'timed_out', 'cancelled')",
            name="ck_execution_events_status",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_execution_events_sequence"),
        sa.ForeignKeyConstraint(["execution_id"], ["tool_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", "sequence", name="uq_execution_events_sequence"),
    )
    op.create_index(
        "ix_execution_events_execution_created",
        "execution_events",
        ["execution_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_events_execution_created", table_name="execution_events")
    op.drop_table("execution_events")
    op.drop_index("ix_tool_executions_org_created", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index("ix_approval_requests_org_status", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_constraint("ck_tools_execution_timeout", "tools", type_="check")
    op.drop_column("tools", "execution_timeout_seconds")
    op.drop_column("tools", "adapter_version")
    op.drop_column("tools", "adapter_name")
