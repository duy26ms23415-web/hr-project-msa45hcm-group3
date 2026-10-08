import React, { useState, useEffect } from 'react';
import {
  Tabs,
  Card,
  Table,
  Button,
  Tag,
  Modal,
  Form,
  DatePicker,
  TimePicker,
  Radio,
  Input,
  message,
  Popconfirm,
  Space,
  Typography,
  Alert,
  Tooltip,
} from 'antd';
import {
  ClockCircleOutlined,
  PlusOutlined,
  CheckOutlined,
  CloseOutlined,
  AuditOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import type { AttendanceRecord, AttendanceFix, Employee } from '../types';

const { Title, Text } = Typography;

export const AttendancePage: React.FC = () => {
  const { user, hasRole } = useAuth();
  const [activeTab, setActiveTab] = useState('records');
  const isAdmin = hasRole(['ADMIN']);
  const [employeesById, setEmployeesById] = useState<Record<number, Employee>>({});
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [myFixes, setMyFixes] = useState<AttendanceFix[]>([]);
  const [pendingFixes, setPendingFixes] = useState<AttendanceFix[]>([]);
  const [loading, setLoading] = useState(false);

  // Modal create fix request
  const [fixModalOpen, setFixModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // Review modal
  const [reviewingFix, setReviewingFix] = useState<AttendanceFix | null>(null);
  const [reviewAction, setReviewAction] = useState<'APPROVED' | 'REJECTED'>('APPROVED');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewModalOpen, setReviewModalOpen] = useState(false);

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const [res, employeesRes] = await Promise.all([
        api.get('/attendance/records'),
        isAdmin ? api.get<Employee[]>('/employees') : Promise.resolve(null),
      ]);
      setRecords(res.data);
      if (employeesRes) {
        setEmployeesById(Object.fromEntries(
          employeesRes.data.map((employee) => [employee.employee_id, employee])
        ));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchMyFixes = async () => {
    try {
      setLoading(true);
      const res = await api.get('/attendance/fixes');
      setMyFixes(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchPendingFixes = async () => {
    if (!hasRole(['MANAGER', 'ADMIN'])) return;
    try {
      setLoading(true);
      const res = await api.get('/attendance/fixes?status=PENDING');
      setPendingFixes(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'records') fetchRecords();
    if (activeTab === 'my-fixes') fetchMyFixes();
    if (activeTab === 'approvals') fetchPendingFixes();
  }, [activeTab, isAdmin]);

  const handleCreateFix = async (values: any) => {
    setSubmitting(true);
    try {
      const workDateStr = values.work_date.format('YYYY-MM-DD');
      const timeStr = values.requested_time.format('HH:mm:ss');
      const requestedAt = `${workDateStr}T${timeStr}`;

      await api.post('/attendance/fixes', {
        work_date: workDateStr,
        event_type: values.event_type,
        requested_at: requestedAt,
        reason: values.reason,
      });

      message.success('Đã gửi giải trình chấm công đến Quản lý trực tiếp!');
      setFixModalOpen(false);
      form.resetFields();
      if (activeTab === 'my-fixes') fetchMyFixes();
      else setActiveTab('my-fixes');
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi gửi giải trình!');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReviewSubmit = async () => {
    if (!reviewingFix) return;
    try {
      await api.post(`/attendance/fixes/${reviewingFix.attendance_fix_id}/review`, {
        status: reviewAction,
        review_note: reviewNote,
      });
      message.success(`Đã ${reviewAction === 'APPROVED' ? 'duyệt' : 'từ chối'} giải trình thành công!`);
      setReviewModalOpen(false);
      setReviewingFix(null);
      setReviewNote('');
      fetchPendingFixes();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi phê duyệt!');
    }
  };

  const openQuickFix = (record: AttendanceRecord) => {
    form.setFieldsValue({
      work_date: dayjs(record.work_date),
      event_type: record.first_check_in_at ? 'CHECK_OUT' : 'CHECK_IN',
      requested_time: dayjs('17:00:00', 'HH:mm:ss'),
      reason: 'Quên quẹt thẻ khi ra về/đến văn phòng',
    });
    setFixModalOpen(true);
  };

  const formatHours = (minutes: number) => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m}p`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Quản lý Chấm công</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            Quy định: 08:00 - 17:00 (Nghỉ trưa 12:00 - 13:00 không tính giờ làm) • Chuẩn 8h/ngày
          </Text>
        </div>

        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields();
            form.setFieldsValue({
              work_date: dayjs(),
              event_type: 'CHECK_IN',
              requested_time: dayjs('08:00:00', 'HH:mm:ss'),
            });
            setFixModalOpen(true);
          }}
          style={{ borderRadius: 8, background: '#1677ff' }}
        >
          Gửi giải trình bổ sung công
        </Button>
      </div>

      <Alert
        message="Hạn chốt giải trình chấm công"
        description="Mọi trường hợp quên quẹt thẻ cần gửi giải trình và được Quản lý trực tiếp phê duyệt TRƯỚC NGÀY CHỐT CÔNG CUỐI THÁNG. Các ngày thiếu công không có giải trình được duyệt sẽ bị mất công và không tính lương."
        type="warning"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ borderRadius: 10 }}
      />

      {/* Tabs */}
      <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key)}
          items={[
            {
              key: 'records',
              label: 'Bảng công cá nhân',
              children: (
                <Table
                  dataSource={records}
                  rowKey="attendance_day_id"
                  loading={loading}
                  columns={[
                    ...(isAdmin ? [
                      {
                        title: 'Họ và tên',
                        key: 'employee_full_name',
                        render: (_: unknown, record: AttendanceRecord) =>
                          employeesById[record.employee_id]?.full_name || '-',
                      },
                      {
                        title: 'Email',
                        key: 'employee_email',
                        render: (_: unknown, record: AttendanceRecord) =>
                          employeesById[record.employee_id]?.email || '-',
                      },
                    ] : []),
                    {
                      title: 'Ngày làm việc',
                      dataIndex: 'work_date',
                      key: 'work_date',
                      render: (d) => <b>{d}</b>,
                    },
                    {
                      title: 'Giờ vào (Check-in)',
                      dataIndex: 'first_check_in_at',
                      key: 'first_check_in_at',
                      render: (t) => (t ? dayjs(t).format('HH:mm:ss') : <span style={{ color: '#ef4444' }}>Chưa quẹt</span>),
                    },
                    {
                      title: 'Giờ ra (Check-out)',
                      dataIndex: 'last_check_out_at',
                      key: 'last_check_out_at',
                      render: (t) => (t ? dayjs(t).format('HH:mm:ss') : <span style={{ color: '#ef4444' }}>Chưa quẹt</span>),
                    },
                    {
                      title: 'Tổng giờ làm',
                      dataIndex: 'worked_minutes',
                      key: 'worked_minutes',
                      render: (m) => formatHours(m || 0),
                    },
                    {
                      title: 'Trạng thái',
                      dataIndex: 'attendance_status',
                      key: 'attendance_status',
                      render: (status) => {
                        let color = 'default';
                        if (status === 'PRESENT') color = 'success';
                        else if (status === 'INCOMPLETE') color = 'warning';
                        else if (status === 'ON_LEAVE') color = 'processing';
                        else if (status === 'HOLIDAY') color = 'purple';
                        else if (status === 'ABSENT') color = 'error';
                        return <Tag color={color}>{status}</Tag>;
                      },
                    },
                    {
                      title: 'Thao tác',
                      key: 'action',
                      render: (_, record) => {
                        if (record.attendance_status === 'INCOMPLETE') {
                          return (
                            <Button size="small" type="link" onClick={() => openQuickFix(record)}>
                              Giải trình bổ sung
                            </Button>
                          );
                        }
                        return null;
                      },
                    },
                  ]}
                />
              ),
            },
            {
              key: 'my-fixes',
              label: 'Đơn giải trình của tôi',
              children: (
                <Table
                  dataSource={myFixes}
                  rowKey="attendance_fix_id"
                  loading={loading}
                  columns={[
                    {
                      title: 'Ngày làm việc',
                      dataIndex: 'work_date',
                      key: 'work_date',
                      render: (d) => <b>{d}</b>,
                    },
                    {
                      title: 'Loại quẹt bổ sung',
                      dataIndex: 'event_type',
                      key: 'event_type',
                      render: (t) => <Tag color={t === 'CHECK_IN' ? 'blue' : 'orange'}>{t}</Tag>,
                    },
                    {
                      title: 'Thời gian đề xuất',
                      dataIndex: 'requested_at',
                      key: 'requested_at',
                      render: (t) => dayjs(t).format('DD/MM/YYYY HH:mm'),
                    },
                    {
                      title: 'Lý do giải trình',
                      dataIndex: 'reason',
                      key: 'reason',
                    },
                    {
                      title: 'Trạng thái',
                      dataIndex: 'status',
                      key: 'status',
                      render: (st) => (
                        <Tag color={st === 'APPROVED' ? 'success' : st === 'REJECTED' ? 'error' : 'warning'}>
                          {st}
                        </Tag>
                      ),
                    },
                    {
                      title: 'Ghi chú duyệt',
                      dataIndex: 'review_note',
                      key: 'review_note',
                      render: (note) => note || '-',
                    },
                  ]}
                />
              ),
            },
            ...(hasRole(['MANAGER', 'ADMIN'])
              ? [
                  {
                    key: 'approvals',
                    label: (
                      <span>
                        Duyệt giải trình
                        {pendingFixes.length > 0 && (
                          <Tag color="orange" style={{ marginLeft: 6, borderRadius: 10 }}>
                            {pendingFixes.length}
                          </Tag>
                        )}
                      </span>
                    ),
                    children: (
                      <Table
                        dataSource={pendingFixes}
                        rowKey="attendance_fix_id"
                        loading={loading}
                        columns={[
                          {
                            title: 'Mã NV',
                            dataIndex: 'employee_id',
                            key: 'employee_id',
                            render: (id) => <Tag color="geekblue">NV#{id}</Tag>,
                          },
                          {
                            title: 'Ngày',
                            dataIndex: 'work_date',
                            key: 'work_date',
                            render: (d) => <b>{d}</b>,
                          },
                          {
                            title: 'Sự kiện bổ sung',
                            dataIndex: 'event_type',
                            key: 'event_type',
                            render: (t) => <Tag color={t === 'CHECK_IN' ? 'blue' : 'orange'}>{t}</Tag>,
                          },
                          {
                            title: 'Giờ đề xuất',
                            dataIndex: 'requested_at',
                            key: 'requested_at',
                            render: (t) => dayjs(t).format('HH:mm:ss'),
                          },
                          {
                            title: 'Lý do nhân viên',
                            dataIndex: 'reason',
                            key: 'reason',
                          },
                          {
                            title: 'Hành động',
                            key: 'actions',
                            render: (_, fix) => (
                              <Space size="small">
                                <Button
                                  type="primary"
                                  size="small"
                                  icon={<CheckOutlined />}
                                  onClick={() => {
                                    setReviewingFix(fix);
                                    setReviewAction('APPROVED');
                                    setReviewNote('Đồng ý giải trình');
                                    setReviewModalOpen(true);
                                  }}
                                  style={{ background: '#16a34a' }}
                                >
                                  Duyệt
                                </Button>
                                <Button
                                  danger
                                  size="small"
                                  icon={<CloseOutlined />}
                                  onClick={() => {
                                    setReviewingFix(fix);
                                    setReviewAction('REJECTED');
                                    setReviewNote('Từ chối giải trình');
                                    setReviewModalOpen(true);
                                  }}
                                >
                                  Từ chối
                                </Button>
                              </Space>
                            ),
                          },
                        ]}
                      />
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Card>

      {/* Modal create fix request */}
      <Modal
        open={fixModalOpen}
        onCancel={() => setFixModalOpen(false)}
        title="Lập đơn giải trình bổ sung chấm công"
        footer={null}
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateFix}>
          <Form.Item
            name="work_date"
            label="Ngày làm việc"
            rules={[{ required: true, message: 'Vui lòng chọn ngày!' }]}
          >
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>

          <Form.Item
            name="event_type"
            label="Loại quẹt thẻ bổ sung"
            rules={[{ required: true }]}
            initialValue="CHECK_IN"
          >
            <Radio.Group>
              <Radio.Button value="CHECK_IN">Check-in (Giờ vào)</Radio.Button>
              <Radio.Button value="CHECK_OUT">Check-out (Giờ ra)</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="requested_time"
            label="Giờ thực tế vào/ra"
            rules={[{ required: true, message: 'Vui lòng chọn thời gian!' }]}
          >
            <TimePicker style={{ width: '100%' }} format="HH:mm:ss" />
          </Form.Item>

          <Form.Item
            name="reason"
            label="Lý do giải trình chi tiết"
            rules={[{ required: true, message: 'Vui lòng nhập lý do giải trình!' }]}
          >
            <Input.TextArea rows={3} placeholder="Ví dụ: Quên quẹt thẻ do vội họp sáng..." />
          </Form.Item>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <Button onClick={() => setFixModalOpen(false)}>Hủy</Button>
            <Button type="primary" htmlType="submit" loading={submitting}>
              Gửi giải trình
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Review Modal for Manager */}
      <Modal
        open={reviewModalOpen}
        onCancel={() => setReviewModalOpen(false)}
        title={`${reviewAction === 'APPROVED' ? 'Phê duyệt' : 'Từ chối'} giải trình chấm công`}
        onOk={handleReviewSubmit}
        okText={reviewAction === 'APPROVED' ? 'Xác nhận duyệt' : 'Xác nhận từ chối'}
        okButtonProps={{ danger: reviewAction === 'REJECTED' }}
      >
        <div style={{ marginBottom: 16 }}>
          <p>Nhân viên: <b>NV#{reviewingFix?.employee_id}</b></p>
          <p>Ngày làm việc: <b>{reviewingFix?.work_date}</b></p>
          <p>Loại quẹt: <b>{reviewingFix?.event_type}</b> ({dayjs(reviewingFix?.requested_at).format('HH:mm:ss')})</p>
          <p>Lý do: <i>"{reviewingFix?.reason}"</i></p>
        </div>
        <Form.Item label="Ghi chú phê duyệt">
          <Input.TextArea
            rows={2}
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
            placeholder="Nhập ghi chú cho nhân viên..."
          />
        </Form.Item>
      </Modal>
    </div>
  );
};
