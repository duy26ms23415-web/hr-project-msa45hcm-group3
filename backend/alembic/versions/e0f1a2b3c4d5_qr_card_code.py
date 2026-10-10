"""Align QR card schema with the existing ORM model."""
from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    # The parallel b7c9d1e2f304 branch may already have added this column.
    op.execute("ALTER TABLE hr_qr_cards ADD COLUMN IF NOT EXISTS card_code VARCHAR(255)")


def downgrade():
    op.drop_column("hr_qr_cards", "card_code")
