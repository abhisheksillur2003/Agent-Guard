"""Create the Phase 1 migration baseline.

Revision ID: 20260922_0001
Revises:
Create Date: 2026-09-22
"""

revision: str = "20260922_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Establish the migration history before domain tables are introduced."""


def downgrade() -> None:
    """Remove the empty baseline revision."""
