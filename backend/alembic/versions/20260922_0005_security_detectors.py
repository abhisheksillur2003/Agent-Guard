"""Add versioned security detectors and sanitized findings.

Revision ID: 20260922_0005
Revises: 20260922_0004
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0005"
down_revision: str | None = "20260922_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_detectors",
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
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_security_detectors_status"),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 10000", name="ck_security_detectors_priority"
        ),
        sa.CheckConstraint("current_version >= 1", name="ck_security_detectors_current_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_security_detectors_org_name"),
    )
    op.create_index(
        "ix_security_detectors_org_status",
        "security_detectors",
        ["organization_id", "status"],
    )

    op.create_table(
        "detector_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("detector_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_detector_versions_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["detector_id"], ["security_detectors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("detector_id", "version", name="uq_detector_versions_number"),
    )
    op.create_index("ix_detector_versions_detector_id", "detector_versions", ["detector_id"])

    op.create_table(
        "security_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("detector_id", sa.Uuid(), nullable=False),
        sa.Column("detector_version_id", sa.Uuid(), nullable=False),
        sa.Column("detector_kind", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "detector_kind IN ('secret', 'pii', 'prompt_injection')",
            name="ck_security_findings_kind",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_security_findings_severity",
        ),
        sa.CheckConstraint(
            "action IN ('record', 'require_approval', 'deny')",
            name="ck_security_findings_action",
        ),
        sa.CheckConstraint("occurrence_count >= 1", name="ck_security_findings_occurrence_count"),
        sa.ForeignKeyConstraint(["decision_id"], ["policy_decisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["detector_id"], ["security_detectors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["detector_version_id"], ["detector_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_findings_org_created",
        "security_findings",
        ["organization_id", "created_at"],
    )
    op.create_index("ix_security_findings_decision", "security_findings", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_security_findings_decision", table_name="security_findings")
    op.drop_index("ix_security_findings_org_created", table_name="security_findings")
    op.drop_table("security_findings")
    op.drop_index("ix_detector_versions_detector_id", table_name="detector_versions")
    op.drop_table("detector_versions")
    op.drop_index("ix_security_detectors_org_status", table_name="security_detectors")
    op.drop_table("security_detectors")
