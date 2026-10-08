import type { Report } from '../types/reports';
export const reportFields: Record<Report['kind'], string[]> = {
  ATTENDANCE: ['employee_code', 'full_name', 'department_id', 'recorded_days', 'present_days', 'incomplete_days', 'absent_days', 'worked_minutes'],
  LEAVE: ['employee_code', 'full_name', 'department_id', 'approved_days', 'pending_requests', 'rejected_requests', 'remaining_annual_days'],
  ATTENDANCE_FIX: ['attendance_fix_id', 'employee_code', 'full_name', 'department_id', 'work_date', 'event_type', 'requested_at', 'status', 'reason'],
  APPROVAL_QUEUE: ['request_type', 'request_id', 'employee_code', 'full_name', 'department_id', 'request_date', 'detail', 'created_at'],
  HEADCOUNT: ['department_id', 'department_name', 'employment_status', 'employee_count'],
  MY_PAYSLIP: ['employee_code', 'full_name', 'period_year', 'period_month', 'currency_code', 'base_salary', 'standard_work_days', 'actual_work_days', 'allowance_amount', 'overtime_amount', 'deduction_amount', 'gross_salary', 'insurance_deduction', 'taxable_income', 'personal_income_tax', 'other_deductions', 'net_salary'],
  PAYROLL_SUMMARY: ['department_id', 'department_name', 'currency_code', 'employee_count', 'base_salary', 'allowance_amount', 'overtime_amount', 'deduction_amount', 'gross_salary', 'insurance_deduction', 'taxable_income', 'personal_income_tax', 'other_deductions', 'net_salary'],
};
export const reportLabels: Record<string, string> = {
    employee_id: 'Mã nhân viên nội bộ', employee_code: 'Mã nhân viên', full_name: 'Họ tên', department_id: 'Phòng ban',
    department_name: 'Phòng ban', employment_status: 'Trạng thái nhân sự', employee_count: 'Số nhân viên',
    recorded_days: 'Ngày có bản ghi', present_days: 'Đủ công (PRESENT)', incomplete_days: 'Thiếu lượt', absent_days: 'Vắng', worked_minutes: 'Phút làm việc',
    approved_days: 'Ngày phép đã duyệt', pending_requests: 'Đơn chờ duyệt', rejected_requests: 'Đơn từ chối', remaining_annual_days: 'Phép năm còn lại hiện tại',
    attendance_fix_id: 'Mã giải trình', work_date: 'Ngày công', event_type: 'Lượt công', requested_at: 'Giờ đề nghị', status: 'Trạng thái', reason: 'Lý do',
    request_type: 'Loại đề nghị', request_id: 'Mã đề nghị', request_date: 'Ngày nghiệp vụ', detail: 'Nội dung', created_at: 'Tạo lúc',
    currency_code: 'Tiền tệ', period_year: 'Năm lương', period_month: 'Tháng lương', base_salary: 'Lương cơ bản', standard_work_days: 'Công chuẩn', actual_work_days: 'Công thực tế', allowance_amount: 'Phụ cấp', overtime_amount: 'Làm thêm', deduction_amount: 'Khấu trừ', gross_salary: 'Lương gross', insurance_deduction: 'Bảo hiểm', taxable_income: 'Thu nhập chịu thuế', personal_income_tax: 'Thuế TNCN', other_deductions: 'Khấu trừ khác', net_salary: 'Lương net',
  };
export const reportKindLabels: Record<Report['kind'], string> = {
    ATTENDANCE: 'Chấm công', LEAVE: 'Nghỉ phép', ATTENDANCE_FIX: 'Giải trình công', APPROVAL_QUEUE: 'Đơn chờ duyệt', HEADCOUNT: 'Headcount', MY_PAYSLIP: 'Phiếu lương của tôi', PAYROLL_SUMMARY: 'Tổng hợp lương',
  };
