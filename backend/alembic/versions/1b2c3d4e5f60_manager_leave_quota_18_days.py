"""Update MANAGER role annual leave quota to 18 days.

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
"""

from alembic import op

revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE hr_employee_leave_balances
        SET total_entitled_days = 18.00,
            remaining_days = remaining_days + 6.00,
            updated_at = NOW()
        WHERE total_entitled_days = 12.00
          AND employee_id IN (
              SELECT ua.employee_id
              FROM hr_user_accounts ua
              JOIN hr_user_role_assignments ura ON ura.user_account_id = ua.user_account_id
              JOIN hr_roles r ON r.role_id = ura.role_id
              WHERE r.role_code = 'MANAGER'
          )
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE hr_employee_leave_balances
        SET total_entitled_days = 12.00,
            remaining_days = GREATEST(0.00, remaining_days - 6.00),
            updated_at = NOW()
        WHERE total_entitled_days = 18.00
          AND employee_id IN (
              SELECT ua.employee_id
              FROM hr_user_accounts ua
              JOIN hr_user_role_assignments ura ON ura.user_account_id = ua.user_account_id
              JOIN hr_roles r ON r.role_id = ura.role_id
              WHERE r.role_code = 'MANAGER'
          )
        """
    )
