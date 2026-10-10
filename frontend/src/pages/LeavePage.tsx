import React, { useState, useEffect } from 'react';
import {
  Row,
  Col,
  Card,
  Statistic,
  Table,
  Button,
  Tag,
  Modal,
  Form,
  DatePicker,
  Radio,
  Select,
  Input,
  message,
  Tabs,
  Space,
  Typography,
  Alert,
} from 'antd';
import {
  CalendarOutlined,
  PlusOutlined,
  CheckOutlined,
  CloseOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import type { LeaveBalance, LeaveRequest } from '../types';
import { useLocation, useNavigate } from 'react-router-dom';

const { Title, Text } = Typography;

export const LeavePage: React.FC = () => {
  const { user, hasRole } = useAuth();
  const [balance, setBalance] = useState<LeaveBalance | null>(null);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [myRequests, setMyRequests] = useState<LeaveRequest[]>([]);
  const [pendingRequests, setPendingRequests] = useState<LeaveRequest[]>([]);
  const [activeTab, setActiveTab] = useState('my-requests');
  const [loading, setLoading] = useState(false);

  // Create request modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const draft = location.state?.aiDraft;
    if (!draft) return;
    form.resetFields();
    form.setFieldsValue({ ...draft, leave_date: dayjs(draft.leave_date) });
    setCreateModalOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, form, navigate]);

  useEffect(() => {
    if (location.state?.aiTab === 'approvals') {
      setActiveTab('approvals');
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.state, location.pathname, navigate]);

  // Review modal
  const [reviewingReq, setReviewingReq] = useState<LeaveRequest | null>(null);
  const [reviewAction, setReviewAction] = useState<'APPROVED' | 'REJECTED'>('APPROVED');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewModalOpen, setReviewModalOpen] = useState(false);

  const fetchBalanceAndTypes = async () => {
    try {
      const [balRes, typesRes] = await Promise.all([
        api.get('/leave/balances/me').catch(() => null),
        api.get('/leave/types').catch(() => ({ data: [] })),
      ]);
      if (balRes) setBalance(balRes.data);
      setLeaveTypes(typesRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchMyRequests = async () => {
    try {
      setLoading(true);
      const res = await api.get('/leave/requests?view=mine');
      setMyRequests(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchPendingRequests = async () => {
    if (!hasRole(['MANAGER', 'HR', 'ADMIN'])) return;
    try {
      setLoading(true);
      const res = await api.get('/leave/requests?view=approvals');
      setPendingRequests(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBalanceAndTypes();
  }, []);

  useEffect(() => {
    if (activeTab === 'my-requests') fetchMyRequests();
    if (activeTab === 'approvals') fetchPendingRequests();
  }, [activeTab]);

  const handleCreateLeave = async (values: any) => {
    setSubmitting(true);
    try {
      const leaveDateStr = values.leave_date.format('YYYY-MM-DD');

      await api.post('/leave/requests', {
        leave_type_id: values.leave_type_id,
        leave_date: leaveDateStr,
        session: values.session,
        reason: values.reason,
      });

      message.success('Đã gửi đơn xin nghỉ phép đến Quản lý trực tiếp!');
      setCreateModalOpen(false);
      form.resetFields();
      fetchBalanceAndTypes();
      fetchMyRequests();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi tạo đơn xin nghỉ!');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReviewSubmit = async () => {
    if (!reviewingReq) return;
    try {
      await api.post(`/leave/requests/${reviewingReq.leave_request_id}/${reviewAction === 'APPROVED' ? 'approve' : 'reject'}`, {
        status: reviewAction,
        review_note: reviewNote,
      });
      message.success(`Đã ${reviewAction === 'APPROVED' ? 'duyệt' : 'từ chối'} đơn nghỉ phép thành công!`);
      setReviewModalOpen(false);
      setReviewingReq(null);
      setReviewNote('');
      fetchPendingRequests();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi phê duyệt!');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Quản lý Nghỉ phép</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            Quản lý trực tiếp duyệt • Phép năm tự hết hạn vào 31/12 (Không bảo lưu)
          </Text>
        </div>

        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields();
            form.setFieldsValue({
              leave_date: dayjs().add(1, 'day'),
              session: 'FULL_DAY',
              leave_type_id: leaveTypes[0]?.leave_type_id,
            });
            setCreateModalOpen(true);
          }}
          style={{ borderRadius: 8, background: '#1677ff' }}
        >
          Tạo đơn xin nghỉ phép
        </Button>
      </div>

      {/* Balance Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <Statistic
              title="Tổng tiêu chuẩn phép năm"
              value={balance ? balance.total_entitled_days : 12}
              suffix="ngày"
              valueStyle={{ fontWeight: 700, color: '#1e293b' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
              Quy chế hưởng 100% lương
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <Statistic
              title="Đã sử dụng"
              value={balance ? balance.used_days : 0}
              suffix="ngày"
              valueStyle={{ fontWeight: 700, color: '#ea580c' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
              Bao gồm các đơn đã được duyệt
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <Statistic
              title="Số ngày phép còn lại"
              value={balance ? balance.remaining_days : 12}
              suffix="ngày"
              valueStyle={{ fontWeight: 700, color: '#16a34a' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
              Hết hạn tự động 31/12 (Hết phép buộc nghỉ không lương)
            </div>
          </Card>
        </Col>
      </Row>

      {/* Tabs */}
      <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key)}
          items={[
            {
              key: 'my-requests',
              label: 'Đơn nghỉ phép của tôi',
              children: (
                <Table
                  dataSource={myRequests}
                  rowKey="leave_request_id"
                  loading={loading}
                  columns={[
                    {
                      title: 'Ngày nghỉ',
                      dataIndex: 'leave_date',
                      key: 'leave_date',
                      render: (d) => <b>{d}</b>,
                    },
                    {
                      title: 'Buổi nghỉ',
                      dataIndex: 'session',
                      key: 'session',
                      render: (s) => {
                        let text = 'Cả ngày (1.0 công)';
                        let color = 'blue';
                        if (s === 'MORNING') {
                          text = 'Buổi Sáng (0.5 công)';
                          color = 'cyan';
                        } else if (s === 'AFTERNOON') {
                          text = 'Buổi Chiều (0.5 công)';
                          color = 'purple';
                        }
                        return <Tag color={color}>{text}</Tag>;
                      },
                    },
                    {
                      title: 'Loại phép',
                      dataIndex: 'leave_type',
                      key: 'leave_type',
                      render: (lt) => lt?.leave_name || 'Phép năm',
                    },
                    {
                      title: 'Lý do',
                      dataIndex: 'reason',
                      key: 'reason',
                      render: (r) => r || '-',
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
                      render: (n) => n || '-',
                    },
                  ]}
                />
              ),
            },
            ...(hasRole(['MANAGER', 'HR', 'ADMIN'])
              ? [
                  {
                    key: 'approvals',
                    label: (
                      <span>
                        Duyệt đơn nghỉ phép
                        {pendingRequests.length > 0 && (
                          <Tag color="orange" style={{ marginLeft: 6, borderRadius: 10 }}>
                            {pendingRequests.length}
                          </Tag>
                        )}
                      </span>
                    ),
                    children: (
                      <Table
                        dataSource={pendingRequests}
                        rowKey="leave_request_id"
                        loading={loading}
                        columns={[
                          {
                            title: 'Mã NV',
                            dataIndex: 'employee_id',
                            key: 'employee_id',
                            render: (id) => <Tag color="geekblue">NV#{id}</Tag>,
                          },
                          {
                            title: 'Ngày nghỉ',
                            dataIndex: 'leave_date',
                            key: 'leave_date',
                            render: (d) => <b>{d}</b>,
                          },
                          {
                            title: 'Buổi nghỉ',
                            dataIndex: 'session',
                            key: 'session',
                            render: (s) => (
                              <Tag color={s === 'FULL_DAY' ? 'blue' : 'cyan'}>
                                {s === 'FULL_DAY' ? 'Cả ngày (1.0)' : s === 'MORNING' ? 'Sáng (0.5)' : 'Chiều (0.5)'}
                              </Tag>
                            ),
                          },
                          {
                            title: 'Loại nghỉ',
                            dataIndex: 'leave_type',
                            key: 'leave_type',
                            render: (lt) => lt?.leave_name || 'Phép năm',
                          },
                          {
                            title: 'Lý do',
                            dataIndex: 'reason',
                            key: 'reason',
                          },
                          {
                            title: 'Hành động',
                            key: 'actions',
                            render: (_, req) => (
                              <Space size="small">
                                <Button
                                  type="primary"
                                  size="small"
                                  icon={<CheckOutlined />}
                                  onClick={() => {
                                    setReviewingReq(req);
                                    setReviewAction('APPROVED');
                                    setReviewNote('Đồng ý duyệt');
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
                                    setReviewingReq(req);
                                    setReviewAction('REJECTED');
                                    setReviewNote('Từ chối nghỉ');
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

      {/* Modal create leave request */}
      <Modal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        title="Lập đơn xin nghỉ phép"
        forceRender
        footer={null}
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateLeave}>
          <Form.Item
            name="leave_type_id"
            label="Loại nghỉ phép"
            rules={[{ required: true, message: 'Vui lòng chọn loại nghỉ phép!' }]}
          >
            <Select>
              {leaveTypes.map((lt) => (
                <Select.Option key={lt.leave_type_id} value={lt.leave_type_id}>
                  {lt.leave_name} {lt.is_paid ? '(Hưởng lương)' : '(Không hưởng lương)'}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="leave_date"
            label="Ngày xin nghỉ"
            rules={[{ required: true, message: 'Vui lòng chọn ngày!' }]}
          >
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>

          <Form.Item
            name="session"
            label="Thời gian nghỉ (Buổi)"
            rules={[{ required: true }]}
            initialValue="FULL_DAY"
          >
            <Radio.Group>
              <Radio.Button value="MORNING">Buổi sáng (08:00 - 12:00 • 0.5 công)</Radio.Button>
              <Radio.Button value="AFTERNOON">Buổi chiều (13:00 - 17:00 • 0.5 công)</Radio.Button>
              <Radio.Button value="FULL_DAY">Cả ngày (08:00 - 17:00 • 1.0 công)</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="reason"
            label="Lý do xin nghỉ"
            rules={[{ required: true, message: 'Vui lòng nhập lý do!' }]}
          >
            <Input.TextArea rows={3} placeholder="Ví dụ: Việc gia đình, ốm sốt..." />
          </Form.Item>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <Button onClick={() => setCreateModalOpen(false)}>Hủy</Button>
            <Button type="primary" htmlType="submit" loading={submitting}>
              Gửi đơn xin nghỉ
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Review Modal for Manager */}
      <Modal
        open={reviewModalOpen}
        onCancel={() => setReviewModalOpen(false)}
        title={`${reviewAction === 'APPROVED' ? 'Phê duyệt' : 'Từ chối'} đơn xin nghỉ phép`}
        onOk={handleReviewSubmit}
        okText={reviewAction === 'APPROVED' ? 'Xác nhận duyệt' : 'Xác nhận từ chối'}
        okButtonProps={{ danger: reviewAction === 'REJECTED' }}
      >
        <div style={{ marginBottom: 16 }}>
          <p>Nhân viên: <b>NV#{reviewingReq?.employee_id}</b></p>
          <p>Ngày nghỉ: <b>{reviewingReq?.leave_date}</b> ({reviewingReq?.session})</p>
          <p>Lý do: <i>"{reviewingReq?.reason}"</i></p>
        </div>
        <Form.Item label="Ghi chú phê duyệt">
          <Input.TextArea
            rows={2}
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
            placeholder="Nhập ghi chú phản hồi cho nhân viên..."
          />
        </Form.Item>
      </Modal>
    </div>
  );
};
