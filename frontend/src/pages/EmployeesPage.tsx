import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  message,
  Typography,
  Divider,
} from 'antd';
import {
  UserAddOutlined,
  EditOutlined,
  DeleteOutlined,
  QrcodeOutlined,
  TeamOutlined,
  MailOutlined,
  PhoneOutlined,
  IdcardOutlined,
} from '@ant-design/icons';
import { QRCodeSVG } from 'qrcode.react';
import dayjs from 'dayjs';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import type { Employee, QRCard } from '../types';

const { Title, Text } = Typography;
const DEMO_EMAILS = new Set(['admin@hrgroup3.com', 'manager@hrgroup3.com', 'employee@hrgroup3.com']);

export const EmployeesPage: React.FC = () => {
  const { hasRole } = useAuth();
  const isAdmin = hasRole(['ADMIN']);
  const isAdminOrHR = hasRole(['ADMIN', 'HR']);

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Add employee modal
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [editForm] = Form.useForm();
  const [savingEmployee, setSavingEmployee] = useState(false);
  const editingDemo = !!editingEmployee && DEMO_EMAILS.has(editingEmployee.email.toLowerCase());

  const closeEditModal = () => {
    if (savingEmployee) return;
    setEditingEmployee(null);
    editForm.resetFields();
  };

  const handleUpdateEmployee = async (values: any) => {
    if (!isAdmin || !editingEmployee || savingEmployee) return;
    setSavingEmployee(true);
    try {
      const payload = {
        full_name: values.full_name,
        phone_number: values.phone_number || null,
        department_id: values.department_id,
        position_id: values.position_id,
        manager_employee_id: values.manager_employee_id ?? null,
        hire_date: values.hire_date.format('YYYY-MM-DD'),
        ...(editingDemo ? {} : {
          email: values.email,
          employment_status: values.employment_status,
          ...(values.new_password ? { new_password: values.new_password } : {}),
        }),
      };
      await api.patch(`/employees/${editingEmployee.employee_id}`, payload);
      message.success('Đã cập nhật thông tin nhân viên và tài khoản đăng nhập.');
      setEditingEmployee(null);
      editForm.resetFields();
      fetchEmployees();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : 'Không cập nhật được nhân viên. Vui lòng kiểm tra thông tin.');
    } finally {
      setSavingEmployee(false);
    }
  };

  const confirmDeleteAccount = (employee: Employee) => {
    if (!isAdmin || DEMO_EMAILS.has(employee.email.toLowerCase())) return;
    Modal.confirm({
      title: 'Xóa tài khoản đăng nhập?',
      content: `Nhân viên: ${employee.full_name} (${employee.email}). Tài khoản sẽ bị xóa và không thể đăng nhập. Hồ sơ nhân viên và lịch sử chấm công được giữ lại.`,
      okText: 'Xóa tài khoản',
      okButtonProps: { danger: true },
      cancelText: 'Hủy',
      onOk: async () => {
        try {
          await api.delete(`/employees/${employee.employee_id}/account`);
          message.success('Đã xóa tài khoản đăng nhập. Hồ sơ nhân viên được giữ lại.');
          fetchEmployees();
        } catch (err: any) {
          const detail = err.response?.data?.detail;
          message.error(typeof detail === 'string' ? detail : 'Không xóa được tài khoản. Vui lòng thử lại.');
          throw err;
        }
      },
    });
  };

  // QR Modal
  const [qrModalOpen, setQrModalOpen] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [qrCard, setQrCard] = useState<any | null>(null);
  const [loadingQr, setLoadingQr] = useState(false);

  const fetchEmployees = async () => {
    try {
      setLoading(true);
      const res = await api.get('/employees');
      setEmployees(res.data);
    } catch (e) {
      console.error(e);
      setEmployees([]);
      message.error('Không tải được danh sách nhân viên. Vui lòng thử lại.');
    } finally {
      setLoading(false);
    }
  };

  const fetchMetadata = async () => {
    try {
      const [deptRes, posRes] = await Promise.all([
        api.get('/departments'),
        api.get('/positions'),
      ]);
      setDepartments(deptRes.data);
      setPositions(posRes.data);
    } catch (e) {
      console.error(e);
      message.error('Không tải được danh sách phòng ban và chức danh. Vui lòng tải lại trang.');
    }
  };

  useEffect(() => {
    fetchEmployees();
    if (isAdminOrHR) fetchMetadata();
  }, [isAdminOrHR]);

  const handleCreateEmployee = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = {
        employee_code: values.employee_code,
        full_name: values.full_name,
        email: values.email,
        phone_number: values.phone_number,
        login_password: values.login_password,
        department_id: values.department_id,
        position_id: values.position_id,
        manager_employee_id: values.manager_employee_id || null,
        hire_date: values.hire_date.format('YYYY-MM-DD'),
        employment_status: 'ACTIVE',
      };

      const res = await api.post('/employees', payload);

      // Auto-issue QR card for new employee
      await api.post(`/attendance/employees/${res.data.employee_id}/qr-cards`, {
        qr_code_value: `${res.data.employee_code}_QR_STATIC`,
      }).catch(() => null);

      message.success('Đã thêm nhân viên và cấp tài khoản đăng nhập bằng email công ty.');
      setAddModalOpen(false);
      form.resetFields();
      fetchEmployees();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : 'Lỗi khi thêm nhân viên. Vui lòng kiểm tra thông tin.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleViewQR = async (emp: Employee) => {
    setSelectedEmployee(emp);
    setQrModalOpen(true);
    setLoadingQr(true);
    try {
      const res = await api.get(`/attendance/employees/${emp.employee_id}/qr-cards`);
      if (res.data && res.data.length > 0) {
        setQrCard(res.data[0]);
      } else {
        // Generate on demand if none exists
        const createRes = await api.post(`/attendance/employees/${emp.employee_id}/qr-cards`, {
          qr_code_value: `${emp.employee_code}_QR_STATIC`,
        });
        setQrCard(createRes.data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingQr(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>{isAdminOrHR ? 'Quản lý Nhân sự & Thẻ QR' : 'Nhân viên của tôi'}</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {isAdminOrHR
              ? 'Danh sách toàn bộ nhân viên • Thẻ QR vật lý tĩnh để quẹt tại máy Kiosk'
              : 'Danh sách nhân viên do bạn quản lý trực tiếp'}
          </Text>
        </div>

        {isAdminOrHR && (
          <Button
            type="primary"
            icon={<UserAddOutlined />}
            onClick={() => {
              form.resetFields();
              form.setFieldsValue({
                hire_date: dayjs(),
                department_id: departments[0]?.department_id,
                position_id: positions[0]?.position_id,
              });
              setAddModalOpen(true);
            }}
            style={{ borderRadius: 8, background: '#1677ff' }}
          >
            Thêm nhân viên mới
          </Button>
        )}
      </div>

      {/* Employees Table */}
      <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <Table
          dataSource={employees}
          rowKey="employee_id"
          loading={loading}
          locale={{ emptyText: isAdminOrHR ? 'Chưa có nhân viên' : 'Chưa có nhân viên được phân công cho bạn' }}
          columns={[
            ...(isAdmin ? [{
              title: 'Thao tác',
              key: 'edit_employee',
              render: (_: unknown, record: Employee) => (
                <Space wrap>
                <Button size="small" icon={<EditOutlined />} onClick={() => {
                  editForm.resetFields();
                  editForm.setFieldsValue({
                    ...record,
                    hire_date: dayjs(record.hire_date),
                    new_password: undefined,
                    confirm_password: undefined,
                  });
                  setEditingEmployee(record);
                }}>
                  Cập nhật nhân viên
                </Button>
                {!DEMO_EMAILS.has(record.email.toLowerCase()) && (
                  <Button size="small" danger icon={<DeleteOutlined />} onClick={() => confirmDeleteAccount(record)}>
                    Xóa tài khoản
                  </Button>
                )}
                </Space>
              ),
            }] : []),
            {
              title: 'Mã NV',
              dataIndex: 'employee_code',
              key: 'employee_code',
              render: (code) => <b>{code}</b>,
            },
            {
              title: 'Họ và tên',
              dataIndex: 'full_name',
              key: 'full_name',
              render: (name) => <span style={{ fontWeight: 600 }}>{name}</span>,
            },
            {
              title: 'Email',
              dataIndex: 'email',
              key: 'email',
            },
            {
              title: 'Số điện thoại',
              dataIndex: 'phone_number',
              key: 'phone_number',
              render: (p) => p || '-',
            },
            {
              title: 'Phòng ban',
              dataIndex: 'department',
              key: 'department',
              render: (d) => <Tag color="blue">{d?.department_name || 'Phòng Nhân sự'}</Tag>,
            },
            {
              title: 'Vị trí',
              dataIndex: 'position',
              key: 'position',
              render: (p) => p?.position_name || 'Chuyên viên',
            },
            {
              title: 'Trạng thái',
              dataIndex: 'employment_status',
              key: 'employment_status',
              render: (s) => (
                <Tag color={s === 'ACTIVE' ? 'success' : 'default'}>
                  {s === 'ACTIVE' ? 'Đang làm việc' : s === 'TERMINATED' ? 'Đã nghỉ việc' : s === 'INACTIVE' ? 'Tạm ngưng' : s}
                </Tag>
              ),
            },
            {
              title: 'Thẻ QR',
              key: 'qr_card',
              render: (_, record) => (
                <Button
                  size="small"
                  icon={<QrcodeOutlined />}
                  onClick={() => handleViewQR(record)}
                  style={{ borderRadius: 6 }}
                >
                  Xem thẻ QR
                </Button>
              ),
            },
          ]}
        />
      </Card>

      {isAdmin && (
        <Modal
          open={editingEmployee !== null}
          title="Cập nhật nhân viên"
          onCancel={closeEditModal}
          footer={null}
          closable={!savingEmployee}
          maskClosable={!savingEmployee}
          keyboard={!savingEmployee}
          width={600}
        >
          <p>Mã nhân viên: <b>{editingEmployee?.employee_code}</b></p>
          {editingDemo && <p>Tài khoản demo: giữ nguyên email, mật khẩu và trạng thái đăng nhập.</p>}
          <Form form={editForm} layout="vertical" onFinish={handleUpdateEmployee} disabled={savingEmployee}>
            <Form.Item name="full_name" label="Họ và tên" rules={[{ required: true, whitespace: true, max: 200, message: 'Vui lòng nhập họ tên, tối đa 200 ký tự.' }]}>
              <Input />
            </Form.Item>
            <Form.Item name="email" label="Email công ty / Email đăng nhập" extra="Cập nhật email này đồng thời cập nhật email đăng nhập của tài khoản hiện có." rules={[{ required: true, type: 'email', message: 'Vui lòng nhập email hợp lệ.' }]}>
              <Input disabled={editingDemo || savingEmployee} />
            </Form.Item>
            <Form.Item name="phone_number" label="Số điện thoại" rules={[{ max: 20, message: 'Tối đa 20 ký tự.' }]}>
              <Input />
            </Form.Item>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Form.Item name="department_id" label="Phòng ban" rules={[{ required: true, message: 'Chọn phòng ban.' }]}>
                <Select options={departments.map(d => ({ value: d.department_id, label: d.department_name }))} />
              </Form.Item>
              <Form.Item name="position_id" label="Chức danh" rules={[{ required: true, message: 'Chọn chức danh.' }]}>
                <Select options={positions.map(p => ({ value: p.position_id, label: p.position_name }))} />
              </Form.Item>
            </div>
            <Form.Item name="manager_employee_id" label="Quản lý trực tiếp">
              <Select allowClear options={employees.filter(e => e.employee_id !== editingEmployee?.employee_id).map(e => ({ value: e.employee_id, label: `${e.full_name} (${e.employee_code})` }))} />
            </Form.Item>
            <Form.Item name="hire_date" label="Ngày bắt đầu làm việc" rules={[{ required: true, message: 'Chọn ngày bắt đầu.' }]}>
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="employment_status" label="Trạng thái làm việc" extra="Tạm ngưng hoặc đã nghỉ việc sẽ khóa đăng nhập; đang làm việc sẽ mở lại tài khoản hiện có." rules={[{ required: true }]}>
              <Select disabled={editingDemo || savingEmployee} options={[
                { value: 'ACTIVE', label: 'Đang làm việc' },
                { value: 'INACTIVE', label: 'Tạm ngưng' },
                { value: 'TERMINATED', label: 'Đã nghỉ việc' },
              ]} />
            </Form.Item>
            {!editingDemo && <>
              <Form.Item name="new_password" label="Mật khẩu mới (tùy chọn)" extra="Để trống để giữ nguyên mật khẩu hiện tại." rules={[
                { min: 8, message: 'Mật khẩu cần ít nhất 8 ký tự.' },
                { validator: (_, value) => !value || new TextEncoder().encode(value).length <= 72 ? Promise.resolve() : Promise.reject(new Error('Mật khẩu không được vượt quá 72 byte UTF-8.')) },
              ]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
              <Form.Item name="confirm_password" label="Nhập lại mật khẩu mới" dependencies={['new_password']} rules={[
                ({ getFieldValue }) => ({ validator: (_, value) => value === getFieldValue('new_password') || (!value && !getFieldValue('new_password')) ? Promise.resolve() : Promise.reject(new Error('Mật khẩu nhập lại không khớp.')) }),
              ]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </>}
            <Space>
              <Button onClick={closeEditModal} disabled={savingEmployee}>Hủy</Button>
              <Button type="primary" htmlType="submit" loading={savingEmployee}>Lưu thay đổi</Button>
            </Space>
          </Form>
        </Modal>
      )}

      {/* Modal Add Employee */}
      <Modal
        open={addModalOpen}
        onCancel={() => setAddModalOpen(false)}
        title="Thêm nhân viên mới"
        footer={null}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateEmployee}>
          <Form.Item
            name="employee_code"
            label="Mã nhân viên"
            rules={[{ required: true, message: 'Vui lòng nhập mã NV!' }]}
          >
            <Input placeholder="Ví dụ: EMP004" />
          </Form.Item>

          <Form.Item
            name="full_name"
            label="Họ và tên"
            rules={[{ required: true, message: 'Vui lòng nhập họ và tên!' }]}
          >
            <Input placeholder="Ví dụ: Nguyễn Văn A" />
          </Form.Item>

          <Form.Item
            name="email"
            label="Email công ty"
            rules={[{ required: true, type: 'email', message: 'Vui lòng nhập email hợp lệ!' }]}
          >
            <Input placeholder="name@hrgroup3.com" />
          </Form.Item>

          <Form.Item
            name="login_password"
            label="Mật khẩu đăng nhập portal"
            extra="Nhân viên dùng email công ty ở trên và mật khẩu này để đăng nhập với quyền Nhân viên."
            rules={[
              { required: true, message: 'Vui lòng nhập mật khẩu!' },
              { min: 8, message: 'Mật khẩu cần ít nhất 8 ký tự.' },
              {
                validator: (_, value) =>
                  !value || new TextEncoder().encode(value).length <= 72
                    ? Promise.resolve()
                    : Promise.reject(new Error('Mật khẩu không được vượt quá 72 byte UTF-8.')),
              },
            ]}
          >
            <Input.Password autoComplete="new-password" placeholder="Ít nhất 8 ký tự" />
          </Form.Item>

          <Form.Item name="phone_number" label="Số điện thoại">
            <Input placeholder="0901234567" />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Form.Item
              name="department_id"
              label="Phòng ban"
              rules={[{ required: true, message: 'Chọn phòng ban!' }]}
            >
              <Select>
                {departments.map((d) => (
                  <Select.Option key={d.department_id} value={d.department_id}>
                    {d.department_name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              name="position_id"
              label="Chức danh"
              rules={[{ required: true, message: 'Chọn chức danh!' }]}
            >
              <Select>
                {positions.map((p) => (
                  <Select.Option key={p.position_id} value={p.position_id}>
                    {p.position_name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </div>

          <Form.Item name="manager_employee_id" label="Quản lý trực tiếp (Người duyệt đơn)">
            <Select allowClear placeholder="Chọn quản lý trực tiếp...">
              {employees.map((e) => (
                <Select.Option key={e.employee_id} value={e.employee_id}>
                  {e.full_name} ({e.employee_code})
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="hire_date"
            label="Ngày bắt đầu làm việc"
            rules={[{ required: true, message: 'Chọn ngày bắt đầu!' }]}
          >
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
            <Button onClick={() => setAddModalOpen(false)}>Hủy</Button>
            <Button type="primary" htmlType="submit" loading={submitting}>
              Tạo nhân viên & Tài khoản
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Modal View QR Card */}
      <Modal
        open={qrModalOpen}
        onCancel={() => setQrModalOpen(false)}
        footer={null}
        width={380}
        styles={{ body: { textAlign: 'center', padding: '28px 24px' } }}
      >
        <div style={{ marginBottom: 16 }}>
          <IdcardOutlined style={{ fontSize: 32, color: '#1677ff', marginBottom: 8 }} />
          <Title level={4} style={{ margin: 0 }}>Thẻ QR Nhân Viên</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>Thẻ vật lý tĩnh quét tại máy Kiosk</Text>
        </div>

        {(() => {
          const qrCodeValue =
            qrCard?.card_code ||
            qrCard?.qr_code_value ||
            qrCard?.raw_token ||
            (selectedEmployee ? `${selectedEmployee.employee_code}_QR_STATIC` : '');

          return (
            <>
              <div
                style={{
                  background: '#f8fafc',
                  border: '2px dashed #93c5fd',
                  borderRadius: 16,
                  padding: 24,
                  display: 'inline-block',
                  margin: '8px auto 16px',
                }}
              >
                {qrCodeValue ? (
                  <QRCodeSVG value={qrCodeValue} size={180} />
                ) : (
                  <div style={{ width: 180, height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    Đang tải mã QR...
                  </div>
                )}
              </div>

              <div style={{ textAlign: 'left', background: '#f1f5f9', padding: '12px 16px', borderRadius: 10, fontSize: 13 }}>
                <div>Họ tên: <b>{selectedEmployee?.full_name}</b></div>
                <div>Mã nhân viên: <b>{selectedEmployee?.employee_code}</b></div>
                <div>Mã thẻ QR: <code style={{ color: '#1677ff', fontWeight: 600 }}>{qrCodeValue}</code></div>
                <div style={{ marginTop: 4 }}>Trạng thái: <Tag color="success">HOẠT ĐỘNG</Tag></div>
              </div>
            </>
          );
        })()}

        <div style={{ marginTop: 20 }}>
          <Button type="primary" block onClick={() => setQrModalOpen(false)}>
            Đóng
          </Button>
        </div>
      </Modal>
    </div>
  );
};
