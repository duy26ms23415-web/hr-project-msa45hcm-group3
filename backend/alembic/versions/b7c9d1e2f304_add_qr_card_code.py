"""Add the QR card code used by the model and demo seed.

Revision ID: b7c9d1e2f304
Revises: 853259f774e1
"""

from alembic import op

revision = "b7c9d1e2f304"
down_revision = "853259f774e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow databases repaired manually in Cloud SQL Studio to migrate too.
    op.execute(
        "ALTER TABLE hr_qr_cards "
        "ADD COLUMN IF NOT EXISTS card_code VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE hr_qr_cards DROP COLUMN IF EXISTS card_code")
