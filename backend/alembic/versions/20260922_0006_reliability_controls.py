"""Add bounded execution retry metadata.

Revision ID: 20260922_0006
Revises: 20260922_0005
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0006"
down_revision: str | None = "20260922_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tool_executions",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "tool_executions",
        sa.Column("max_attempts", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_tool_executions_attempt_count",
        "tool_executions",
        "attempt_count >= 0 AND attempt_count <= max_attempts",
    )
    op.create_check_constraint(
        "ck_tool_executions_max_attempts",
        "tool_executions",
        "max_attempts >= 1 AND max_attempts <= 5",
    )
    op.alter_column("tool_executions", "attempt_count", server_default=None)
    op.alter_column("tool_executions", "max_attempts", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_tool_executions_max_attempts", "tool_executions", type_="check")
    op.drop_constraint("ck_tool_executions_attempt_count", "tool_executions", type_="check")
    op.drop_column("tool_executions", "max_attempts")
    op.drop_column("tool_executions", "attempt_count")
