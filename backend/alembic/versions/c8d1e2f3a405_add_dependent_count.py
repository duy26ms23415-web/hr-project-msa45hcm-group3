"""Add dependent_count column to hr_employees for PIT tax calculation.

Revision ID: c8d1e2f3a405
Revises: 2c3d4e5f6a71
"""

from alembic import op

revision = "c8d1e2f3a405"
down_revision = "2c3d4e5f6a71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE hr_employees "
        "ADD COLUMN IF NOT EXISTS dependent_count INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE hr_employees DROP COLUMN IF EXISTS dependent_count")

