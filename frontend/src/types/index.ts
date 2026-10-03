export interface User {
  user_account_id: number;
  employee_id: number;
  login_email: string;
  is_active: boolean;
  roles: string[];
}

export interface Employee {
  employee_id: number;
  employee_code: string;
  full_name: string;
  email: string;
  phone_number?: string;
  date_of_birth?: string;
  department_id: number;
  position_id: number;
  manager_employee_id?: number;
  employment_status: string;
  hire_date: string;
  termination_date?: string;
  department?: { department_name: string };
  position?: { position_name: string };
}

export interface QRCard {
  qr_card_id: number;
  employee_id: number;
  token_hash: string;
  card_code?: string;
  qr_code_value?: string;
  raw_token?: string;
  issued_at: string;
  expires_at?: string;
  revoked_at?: string;
}

export interface AttendanceRecord {
  attendance_day_id: number;
  employee_id: number;
  work_date: string;
  first_check_in_at?: string;
  last_check_out_at?: string;
  worked_minutes: number;
  attendance_status: 'PRESENT' | 'INCOMPLETE' | 'ABSENT' | 'ON_LEAVE' | 'HOLIDAY';
  updated_at: string;
}

export interface AttendanceFix {
  attendance_fix_id: number;
  employee_id: number;
  work_date: string;
  event_type: 'CHECK_IN' | 'CHECK_OUT';
  requested_at: string;
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  reviewer_employee_id?: number;
  reviewed_at?: string;
  review_note?: string;
  created_at: string;
}

export interface LeaveBalance {
  leave_balance_id: number;
  employee_id: number;
  year: number;
  total_entitled_days: number;
  used_days: number;
  remaining_days: number;
  updated_at: string;
}

export interface LeaveRequest {
  leave_request_id: number;
  employee_id: number;
  leave_type_id: number;
  leave_date: string;
  session: 'MORNING' | 'AFTERNOON' | 'FULL_DAY';
  leave_days: number;
  reason?: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
  reviewer_employee_id?: number;
  reviewed_at?: string;
  review_note?: string;
  created_at: string;
  leave_type?: {
    leave_code: string;
    leave_name: string;
    is_paid: boolean;
  };
}

export interface PayrollPeriod {
  payroll_period_id: number;
  period_year: number;
  period_month: number;
  start_date: string;
  end_date: string;
  status: 'DRAFT' | 'CALCULATED' | 'APPROVED' | 'CLOSED';
  created_at: string;
  closed_at?: string;
}

export interface PayrollLine {
  payroll_line_id: number;
  payroll_period_id: number;
  employee_id: number;
  base_salary: number;
  standard_work_days: number;
  actual_work_days: number;
  allowance_amount: number;
  gross_salary: number;
  insurance_deduction: number;
  taxable_income: number;
  personal_income_tax: number;
  net_salary: number;
  calculated_at: string;
  employee?: Employee;
}
