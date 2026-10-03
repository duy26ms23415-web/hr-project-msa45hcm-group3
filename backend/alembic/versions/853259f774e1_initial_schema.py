"""Initial schema

Revision ID: 853259f774e1
Revises: 
Create Date: 2026-10-03 17:13:03.424388+07:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '853259f774e1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Independent lookup tables
    op.create_table('hr_positions',
        sa.Column('position_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('position_code', sa.String(length=30), nullable=False),
        sa.Column('position_name', sa.String(length=150), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('position_id')
    )
    op.create_index(op.f('ix_hr_positions_position_code'), 'hr_positions', ['position_code'], unique=True)

    op.create_table('hr_leave_types',
        sa.Column('leave_type_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('leave_code', sa.String(length=30), nullable=False),
        sa.Column('leave_name', sa.String(length=100), nullable=False),
        sa.Column('is_paid', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('leave_type_id')
    )
    op.create_index(op.f('ix_hr_leave_types_leave_code'), 'hr_leave_types', ['leave_code'], unique=True)

    op.create_table('hr_roles',
        sa.Column('role_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('role_code', sa.String(length=30), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('role_id')
    )
    op.create_index(op.f('ix_hr_roles_role_code'), 'hr_roles', ['role_code'], unique=True)

    # 2. Departments table (manager_employee_id FK deferred to break cycle)
    op.create_table('hr_departments',
        sa.Column('department_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('department_code', sa.String(length=30), nullable=False),
        sa.Column('department_name', sa.String(length=150), nullable=False),
        sa.Column('manager_employee_id', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('department_id')
    )
    op.create_index(op.f('ix_hr_departments_department_code'), 'hr_departments', ['department_code'], unique=True)

    # 3. Employees table
    op.create_table('hr_employees',
        sa.Column('employee_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_code', sa.String(length=30), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('department_id', sa.BigInteger(), nullable=False),
        sa.Column('position_id', sa.BigInteger(), nullable=False),
        sa.Column('manager_employee_id', sa.BigInteger(), nullable=True),
        sa.Column('employment_status', sa.String(length=20), nullable=False),
        sa.Column('hire_date', sa.Date(), nullable=False),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['hr_departments.department_id'], ),
        sa.ForeignKeyConstraint(['manager_employee_id'], ['hr_employees.employee_id'], ),
        sa.ForeignKeyConstraint(['position_id'], ['hr_positions.position_id'], ),
        sa.PrimaryKeyConstraint('employee_id')
    )
    op.create_index(op.f('ix_hr_employees_email'), 'hr_employees', ['email'], unique=True)
    op.create_index(op.f('ix_hr_employees_employee_code'), 'hr_employees', ['employee_code'], unique=True)

    # Add deferred manager_employee_id foreign key on hr_departments
    op.create_foreign_key(
        'fk_hr_departments_manager_employee_id',
        'hr_departments', 'hr_employees',
        ['manager_employee_id'], ['employee_id']
    )

    # 4. User accounts
    op.create_table('hr_user_accounts',
        sa.Column('user_account_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('login_email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('user_account_id'),
        sa.UniqueConstraint('employee_id')
    )
    op.create_index(op.f('ix_hr_user_accounts_login_email'), 'hr_user_accounts', ['login_email'], unique=True)

    # 5. User role assignments
    op.create_table('hr_user_role_assignments',
        sa.Column('user_role_assignment_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_account_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['hr_roles.role_id'], ),
        sa.ForeignKeyConstraint(['user_account_id'], ['hr_user_accounts.user_account_id'], ),
        sa.PrimaryKeyConstraint('user_role_assignment_id'),
        sa.UniqueConstraint('user_account_id', 'role_id', name='uq_hr_user_roles_account_role')
    )

    # 6. Holidays
    op.create_table('hr_holidays',
        sa.Column('holiday_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('holiday_date', sa.Date(), nullable=False),
        sa.Column('holiday_name', sa.String(length=150), nullable=False),
        sa.Column('is_paid', sa.Boolean(), nullable=False),
        sa.Column('created_by_user_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['hr_user_accounts.user_account_id'], ),
        sa.PrimaryKeyConstraint('holiday_id')
    )
    op.create_index(op.f('ix_hr_holidays_holiday_date'), 'hr_holidays', ['holiday_date'], unique=True)

    # 7. QR cards
    op.create_table('hr_qr_cards',
        sa.Column('qr_card_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['hr_user_accounts.user_account_id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('qr_card_id')
    )
    op.create_index(op.f('ix_hr_qr_cards_employee_id'), 'hr_qr_cards', ['employee_id'], unique=False)
    op.create_index(op.f('ix_hr_qr_cards_token_hash'), 'hr_qr_cards', ['token_hash'], unique=True)

    # 8. Attendance days
    op.create_table('hr_attendance_days',
        sa.Column('attendance_day_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('first_check_in_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_check_out_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worked_minutes', sa.Integer(), nullable=False),
        sa.Column('attendance_status', sa.String(length=20), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('attendance_day_id'),
        sa.UniqueConstraint('employee_id', 'work_date', name='uq_hr_att_days_employee_date')
    )
    op.create_index(op.f('ix_hr_attendance_days_employee_id'), 'hr_attendance_days', ['employee_id'], unique=False)

    # 9. Attendance fixes
    op.create_table('hr_attendance_fixes',
        sa.Column('attendance_fix_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reviewer_employee_id', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.ForeignKeyConstraint(['reviewer_employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('attendance_fix_id')
    )
    op.create_index(op.f('ix_hr_attendance_fixes_employee_id'), 'hr_attendance_fixes', ['employee_id'], unique=False)

    # 10. Attendance events
    op.create_table('hr_attendance_events',
        sa.Column('attendance_event_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('qr_card_id', sa.BigInteger(), nullable=True),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('device_id', sa.String(length=100), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('attendance_fix_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['attendance_fix_id'], ['hr_attendance_fixes.attendance_fix_id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.ForeignKeyConstraint(['qr_card_id'], ['hr_qr_cards.qr_card_id'], ),
        sa.PrimaryKeyConstraint('attendance_event_id')
    )
    op.create_index('idx_hr_att_events_employee_time', 'hr_attendance_events', ['employee_id', 'occurred_at'], unique=False)
    op.create_index(op.f('ix_hr_attendance_events_employee_id'), 'hr_attendance_events', ['employee_id'], unique=False)
    op.create_index(op.f('ix_hr_attendance_events_idempotency_key'), 'hr_attendance_events', ['idempotency_key'], unique=True)

    # 11. Leave balances
    op.create_table('hr_employee_leave_balances',
        sa.Column('leave_balance_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('total_entitled_days', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('used_days', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('remaining_days', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('leave_balance_id'),
        sa.UniqueConstraint('employee_id', 'year', name='uq_hr_leave_balance_emp_year')
    )
    op.create_index(op.f('ix_hr_employee_leave_balances_employee_id'), 'hr_employee_leave_balances', ['employee_id'], unique=False)

    # 12. Leave requests
    op.create_table('hr_leave_requests',
        sa.Column('leave_request_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('leave_type_id', sa.BigInteger(), nullable=False),
        sa.Column('leave_date', sa.Date(), nullable=False),
        sa.Column('session', sa.String(length=20), nullable=False),
        sa.Column('leave_days', sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reviewer_employee_id', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.ForeignKeyConstraint(['leave_type_id'], ['hr_leave_types.leave_type_id'], ),
        sa.ForeignKeyConstraint(['reviewer_employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('leave_request_id')
    )
    op.create_index(op.f('ix_hr_leave_requests_employee_id'), 'hr_leave_requests', ['employee_id'], unique=False)

    # 13. Employee compensation (Gross salary)
    op.create_table('hr_employee_compensation',
        sa.Column('employee_compensation_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('base_monthly_salary', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('fixed_allowance', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('created_by_user_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['hr_user_accounts.user_account_id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.PrimaryKeyConstraint('employee_compensation_id')
    )
    op.create_index(op.f('ix_hr_employee_compensation_employee_id'), 'hr_employee_compensation', ['employee_id'], unique=False)

    # 14. Payroll periods
    op.create_table('hr_payroll_periods',
        sa.Column('payroll_period_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_by_user_id', sa.BigInteger(), nullable=False),
        sa.Column('approved_by_user_id', sa.BigInteger(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['hr_user_accounts.user_account_id'], ),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['hr_user_accounts.user_account_id'], ),
        sa.PrimaryKeyConstraint('payroll_period_id'),
        sa.UniqueConstraint('period_year', 'period_month', name='uq_hr_pay_period_year_month')
    )

    # 15. Payroll lines
    op.create_table('hr_payroll_lines',
        sa.Column('payroll_line_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('payroll_period_id', sa.BigInteger(), nullable=False),
        sa.Column('employee_id', sa.BigInteger(), nullable=False),
        sa.Column('base_salary', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('standard_work_days', sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column('actual_work_days', sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column('allowance_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('overtime_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('deduction_amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('gross_salary', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('insurance_deduction', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('taxable_income', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('personal_income_tax', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('other_deductions', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('net_salary', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('calculation_details', sa.JSON(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['hr_employees.employee_id'], ),
        sa.ForeignKeyConstraint(['payroll_period_id'], ['hr_payroll_periods.payroll_period_id'], ),
        sa.PrimaryKeyConstraint('payroll_line_id'),
        sa.UniqueConstraint('payroll_period_id', 'employee_id', name='uq_hr_pay_lines_period_employee')
    )
    op.create_index(op.f('ix_hr_payroll_lines_employee_id'), 'hr_payroll_lines', ['employee_id'], unique=False)
    op.create_index(op.f('ix_hr_payroll_lines_payroll_period_id'), 'hr_payroll_lines', ['payroll_period_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hr_payroll_lines_payroll_period_id'), table_name='hr_payroll_lines')
    op.drop_index(op.f('ix_hr_payroll_lines_employee_id'), table_name='hr_payroll_lines')
    op.drop_table('hr_payroll_lines')

    op.drop_table('hr_payroll_periods')

    op.drop_index(op.f('ix_hr_employee_compensation_employee_id'), table_name='hr_employee_compensation')
    op.drop_table('hr_employee_compensation')

    op.drop_index(op.f('ix_hr_leave_requests_employee_id'), table_name='hr_leave_requests')
    op.drop_table('hr_leave_requests')

    op.drop_index(op.f('ix_hr_employee_leave_balances_employee_id'), table_name='hr_employee_leave_balances')
    op.drop_table('hr_employee_leave_balances')

    op.drop_index(op.f('ix_hr_attendance_events_idempotency_key'), table_name='hr_attendance_events')
    op.drop_index(op.f('ix_hr_attendance_events_employee_id'), table_name='hr_attendance_events')
    op.drop_index('idx_hr_att_events_employee_time', table_name='hr_attendance_events')
    op.drop_table('hr_attendance_events')

    op.drop_index(op.f('ix_hr_attendance_fixes_employee_id'), table_name='hr_attendance_fixes')
    op.drop_table('hr_attendance_fixes')

    op.drop_index(op.f('ix_hr_attendance_days_employee_id'), table_name='hr_attendance_days')
    op.drop_table('hr_attendance_days')

    op.drop_index(op.f('ix_hr_qr_cards_token_hash'), table_name='hr_qr_cards')
    op.drop_index(op.f('ix_hr_qr_cards_employee_id'), table_name='hr_qr_cards')
    op.drop_table('hr_qr_cards')

    op.drop_index(op.f('ix_hr_holidays_holiday_date'), table_name='hr_holidays')
    op.drop_table('hr_holidays')

    op.drop_table('hr_user_role_assignments')

    op.drop_index(op.f('ix_hr_user_accounts_login_email'), table_name='hr_user_accounts')
    op.drop_table('hr_user_accounts')

    op.drop_constraint('fk_hr_departments_manager_employee_id', 'hr_departments', type_='foreignkey')

    op.drop_index(op.f('ix_hr_employees_employee_code'), table_name='hr_employees')
    op.drop_index(op.f('ix_hr_employees_email'), table_name='hr_employees')
    op.drop_table('hr_employees')

    op.drop_index(op.f('ix_hr_departments_department_code'), table_name='hr_departments')
    op.drop_table('hr_departments')

    op.drop_index(op.f('ix_hr_roles_role_code'), table_name='hr_roles')
    op.drop_table('hr_roles')

    op.drop_index(op.f('ix_hr_leave_types_leave_code'), table_name='hr_leave_types')
    op.drop_table('hr_leave_types')

    op.drop_index(op.f('ix_hr_positions_position_code'), table_name='hr_positions')
    op.drop_table('hr_positions')
