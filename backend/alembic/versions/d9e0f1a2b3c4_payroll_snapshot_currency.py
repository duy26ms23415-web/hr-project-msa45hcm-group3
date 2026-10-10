"""Capture payroll snapshot currency without guessing legacy records."""
from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade():
    # Historical lines did not capture currency. Keep unknown rather than
    # infer it from a compensation profile that may have changed since then.
    op.add_column("hr_payroll_lines", sa.Column("currency_code", sa.String(3), nullable=True))
    op.create_check_constraint("ck_payroll_line_currency", "hr_payroll_lines", "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'")


def downgrade():
    op.drop_constraint("ck_payroll_line_currency", "hr_payroll_lines", type_="check")
    op.drop_column("hr_payroll_lines", "currency_code")
