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
  Badge,
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
  const defaultQuota = hasRole(['MANAGER']) ? 18 : 12;
  const [balance, setBalance] = useState<LeaveBalance | null>(null);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [myRequests, setMyRequests] = useState<LeaveRequest[]>([]);
  const [approvalRequests, setApprovalRequests] = useState<LeaveRequest[]>([]);
  const [approvalFilter, setApprovalFilter] = useState<'PENDING' | 'APPROVED' | 'REJECTED' | 'ALL'>('PENDING');
  const [pendingCount, setPendingCount] = useState<number>(0);
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
        api.get('/leaves/balances/me').catch(() => null),
        api.get('/leaves/types').catch(() => ({ data: [] })),
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
      const res = await api.get('/leaves/requests?mine=true');
      setMyRequests(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchApprovalRequests = async (filter: 'PENDING' | 'APPROVED' | 'REJECTED' | 'ALL' = approvalFilter) => {
    if (!hasRole(['MANAGER', 'HR', 'ADMIN'])) return;
    try {
      setLoading(true);
      const url = filter === 'ALL' ? '/leaves/requests' : `/leaves/requests?status=${filter}`;
      const res = await api.get(url);
      const list = res.data.filter((r: LeaveRequest) => r.employee_id !== user?.employee_id);
      setApprovalRequests(list);

      if (filter === 'PENDING') {
        setPendingCount(list.length);
      } else {
        const pendingRes = await api.get('/leaves/requests?status=PENDING');
        const pendingList = pendingRes.data.filter((r: LeaveRequest) => r.employee_id !== user?.employee_id);
        setPendingCount(pendingList.length);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBalanceAndTypes();
    if (hasRole(['MANAGER', 'HR', 'ADMIN'])) {
      fetchApprovalRequests(approvalFilter);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'my-requests') fetchMyRequests();
    if (activeTab === 'approvals') fetchApprovalRequests(approvalFilter);
  }, [activeTab, approvalFilter]);

  const handleCreateLeave = async (values: any) => {
    setSubmitting(true);
    try {
      const leaveDateStr = values.leave_date.format('YYYY-MM-DD');

      await api.post('/leaves/requests', {
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
      await api.post(`/leaves/requests/${reviewingReq.leave_request_id}/review`, {
        status: reviewAction,
        review_note: reviewNote,
      });
      message.success(`Đã ${reviewAction === 'APPROVED' ? 'duyệt' : 'từ chối'} đơn nghỉ phép thành công!`);
      setReviewModalOpen(false);
      setReviewingReq(null);
      setReviewNote('');
      fetchApprovalRequests(approvalFilter);
      fetchBalanceAndTypes();
      fetchMyRequests();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi phê duyệt!');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Quản lý Nghỉ phép & Làm việc từ xa (Remote)</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            Quản lý trực tiếp duyệt • Phép năm hết hạn 31/12 • Đơn Remote hưởng 100% lương (Không trừ phép năm)
          </Text>
        </div>

        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            if (leaveTypes.length === 0) {
              fetchBalanceAndTypes();
            }
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
          Tạo đơn xin nghỉ / Remote
        </Button>
      </div>

      {/* Balance Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <Statistic
              title="Tổng tiêu chuẩn phép năm"
              value={balance ? balance.total_entitled_days : defaultQuota}
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
              value={balance ? balance.remaining_days : defaultQuota}
              suffix="ngày"
              valueStyle={{ fontWeight: 700, color: '#16a34a' }}
            />
            <div style={{ marginTop: 8, fontSize: 12, color: '#64748b' }}>
              Hết hạn 31/12 (Đơn Remote hưởng lương, không trừ phép năm)
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
              label: 'Đơn nghỉ phép & Remote của tôi',
              children: (
                <Table
                  dataSource={myRequests}
                  rowKey="leave_request_id"
                  loading={loading}
                  columns={[
                    {
                      title: 'Ngày nghỉ / Remote',
                      dataIndex: 'leave_date',
                      key: 'leave_date',
                      render: (d) => <b>{d}</b>,
                    },
                    {
                      title: 'Buổi làm việc / Nghỉ',
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
                      title: 'Loại đơn',
                      dataIndex: 'leave_type',
                      key: 'leave_type',
                      render: (lt) => {
                        if (lt?.leave_code === 'REMOTE') {
                          return <Tag color="cyan">Làm việc từ xa (Remote)</Tag>;
                        }
                        return lt?.leave_name || 'Phép năm';
                      },
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
                          {st === 'APPROVED' ? 'ĐÃ DUYỆT' : st === 'REJECTED' ? 'TỪ CHỐI' : 'CHỜ DUYỆT'}
                        </Tag>
                      ),
                    },
                    {
                      title: 'Người duyệt',
                      key: 'reviewer',
                      render: (_, req: LeaveRequest) => {
                        if (req.status === 'PENDING') return <span style={{ color: '#9ca3af' }}>Chờ duyệt</span>;
                        return req.reviewer?.full_name || (req.reviewer_employee_id ? `NV #${req.reviewer_employee_id}` : '-');
                      },
                    },
                    {
                      title: 'Thời gian duyệt',
                      dataIndex: 'reviewed_at',
                      key: 'reviewed_at',
                      render: (d) => (d ? dayjs(d).format('DD/MM/YYYY HH:mm') : '-'),
                    },
                    {
                      title: 'Ghi chú phản hồi',
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
                        Duyệt đơn nghỉ & Remote
                        {pendingCount > 0 && (
                          <Tag color="orange" style={{ marginLeft: 6, borderRadius: 10 }}>
                            {pendingCount}
                          </Tag>
                        )}
                      </span>
                    ),
                    children: (
                      <div>
                        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                          <Space>
                            <Text strong>Bộ lọc trạng thái:</Text>
                            <Radio.Group
                              value={approvalFilter}
                              onChange={(e) => {
                                const newFilter = e.target.value;
                                setApprovalFilter(newFilter);
                                fetchApprovalRequests(newFilter);
                              }}
                              buttonStyle="solid"
                            >
                              <Radio.Button value="PENDING">
                                Chờ duyệt {pendingCount > 0 && `(${pendingCount})`}
                              </Radio.Button>
                              <Radio.Button value="APPROVED">Đã duyệt (Lịch sử)</Radio.Button>
                              <Radio.Button value="REJECTED">Đã từ chối</Radio.Button>
                              <Radio.Button value="ALL">Tất cả</Radio.Button>
                            </Radio.Group>
                          </Space>
                          <Text type="secondary" style={{ fontSize: 13 }}>
                            {approvalFilter === 'PENDING'
                              ? 'Danh sách đơn xin nghỉ phép / Remote cấp dưới cần duyệt'
                              : 'Lịch sử xét duyệt đầy đủ để đối chiếu và tra cứu khi có khiếu nại'}
                          </Text>
                        </div>
                        <Table
                          dataSource={approvalRequests}
                          rowKey="leave_request_id"
                          loading={loading}
                          columns={[
                            {
                              title: 'Nhân viên',
                              key: 'employee',
                              render: (_, req: LeaveRequest) => (
                                <div>
                                  <span style={{ fontWeight: 600 }}>{req.employee?.full_name || `Nhân viên #${req.employee_id}`}</span>
                                  <div style={{ fontSize: 12, color: '#64748b' }}>
                                    <Tag color="geekblue" style={{ fontSize: 11, padding: '0 4px', marginRight: 4 }}>
                                      {req.employee?.employee_code || `NV#${req.employee_id}`}
                                    </Tag>
                                    {req.employee?.email}
                                  </div>
                                </div>
                              ),
                            },
                            {
                              title: 'Ngày nghỉ / Remote',
                              dataIndex: 'leave_date',
                              key: 'leave_date',
                              render: (d) => <b>{d}</b>,
                            },
                            {
                              title: 'Buổi làm / Nghỉ',
                              dataIndex: 'session',
                              key: 'session',
                              render: (s) => (
                                <Tag color={s === 'FULL_DAY' ? 'blue' : 'cyan'}>
                                  {s === 'FULL_DAY' ? 'Cả ngày (1.0)' : s === 'MORNING' ? 'Sáng (0.5)' : 'Chiều (0.5)'}
                                </Tag>
                              ),
                            },
                            {
                              title: 'Loại đơn',
                              dataIndex: 'leave_type',
                              key: 'leave_type',
                              render: (lt) => {
                                if (lt?.leave_code === 'REMOTE') {
                                  return <Tag color="cyan">Làm việc từ xa (Remote)</Tag>;
                                }
                                return lt?.leave_name || 'Phép năm';
                              },
                            },
                            {
                              title: 'Lý do',
                              dataIndex: 'reason',
                              key: 'reason',
                            },
                            {
                              title: 'Trạng thái',
                              dataIndex: 'status',
                              key: 'status',
                              render: (st) => (
                                <Tag color={st === 'APPROVED' ? 'success' : st === 'REJECTED' ? 'error' : 'warning'}>
                                  {st === 'APPROVED' ? 'ĐÃ DUYỆT' : st === 'REJECTED' ? 'TỪ CHỐI' : 'CHỜ DUYỆT'}
                                </Tag>
                              ),
                            },
                            {
                              title: 'Thông tin duyệt',
                              key: 'reviewer_info',
                              render: (_, req: LeaveRequest) => {
                                if (req.status === 'PENDING') {
                                  return <span style={{ color: '#9ca3af' }}>Chưa duyệt</span>;
                                }
                                const reviewerName = req.reviewer?.full_name || (req.reviewer_employee_id ? `Quản lý #${req.reviewer_employee_id}` : 'Quản lý');
                                return (
                                  <div>
                                    <div style={{ fontSize: 13, fontWeight: 500 }}>{reviewerName}</div>
                                    {req.reviewed_at && (
                                      <div style={{ fontSize: 12, color: '#6b7280' }}>
                                        {dayjs(req.reviewed_at).format('DD/MM/YYYY HH:mm')}
                                      </div>
                                    )}
                                    {req.review_note && (
                                      <div style={{ fontSize: 12, color: '#4b5563', fontStyle: 'italic', marginTop: 2 }}>
                                        "{req.review_note}"
                                      </div>
                                    )}
                                  </div>
                                );
                              },
                            },
                            {
                              title: 'Hành động',
                              key: 'actions',
                              render: (_, req: LeaveRequest) => {
                                if (req.status === 'PENDING') {
                                  return (
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
                                  );
                                }
                                return <Tag color="default">Đã xử lý</Tag>;
                              },
                            },
                          ]}
                        />
                      </div>
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
        title="Lập đơn xin nghỉ phép / Làm việc từ xa (Remote)"
        forceRender
        footer={null}
        width={540}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateLeave}>
          <Form.Item
            name="leave_type_id"
            label="Loại đơn"
            rules={[{ required: true, message: 'Vui lòng chọn loại đơn!' }]}
          >
            <Select placeholder="-- Chọn loại đơn xin nghỉ / làm việc từ xa --" loading={leaveTypes.length === 0}>
              {leaveTypes.map((lt) => (
                <Select.Option key={lt.leave_type_id} value={lt.leave_type_id}>
                  {lt.leave_name} {lt.leave_code === 'REMOTE' ? '(Hưởng 100% lương • Không trừ phép năm)' : lt.is_paid ? '(Hưởng lương)' : '(Không hưởng lương)'}
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
