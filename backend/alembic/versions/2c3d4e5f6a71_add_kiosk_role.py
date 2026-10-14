"""Add KIOSK role for dedicated timekeeping devices.

Revision ID: 2c3d4e5f6a71
Revises: 1b2c3d4e5f60
"""

from alembic import op

revision = "2c3d4e5f6a71"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO hr_roles (role_code, role_name)
        VALUES ('KIOSK', 'Thiết bị chấm công Kiosk')
        ON CONFLICT (role_code) DO NOTHING;
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM hr_roles WHERE role_code = 'KIOSK';
        """
    )
