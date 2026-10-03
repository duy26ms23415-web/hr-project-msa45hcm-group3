import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Tag, Button, Typography, Space, Table, Alert } from 'antd';
import {
  ClockCircleOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  QrcodeOutlined,
  AuditOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import type { LeaveBalance, AttendanceRecord } from '../types';

const { Title, Text, Paragraph } = Typography;

export const DashboardPage: React.FC = () => {
  const { user, hasRole } = useAuth();
  const navigate = useNavigate();
  const [balance, setBalance] = useState<LeaveBalance | null>(null);
  const [todayRecord, setTodayRecord] = useState<AttendanceRecord | null>(null);
  const [recentRecords, setRecentRecords] = useState<AttendanceRecord[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<{ leaves: number; fixes: number }>({ leaves: 0, fixes: 0 });
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      setLoading(true);
      // Fetch leave balance
      const balRes = await api.get('/leaves/balances/me').catch(() => null);
      if (balRes) setBalance(balRes.data);

      // Fetch attendance records
      const attRes = await api.get('/attendance/records').catch(() => null);
      if (attRes && attRes.data) {
        const records: AttendanceRecord[] = attRes.data;
        setRecentRecords(records.slice(0, 5));
        const todayStr = new Date().toISOString().split('T')[0];
        const today = records.find((r) => r.work_date === todayStr);
        if (today) setTodayRecord(today);
      }

      // If Manager, fetch pending approvals
      if (hasRole(['MANAGER', 'ADMIN'])) {
        const [leavesRes, fixesRes] = await Promise.all([
          api.get('/leaves/requests?status=PENDING').catch(() => ({ data: [] })),
          api.get('/attendance/fixes?status=PENDING').catch(() => ({ data: [] })),
        ]);
        setPendingApprovals({
          leaves: leavesRes.data.length || 0,
          fixes: fixesRes.data.length || 0,
        });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const formatHours = (minutes: number) => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m}p`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Welcome Banner */}
      <div
        style={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          borderRadius: 16,
          padding: '24px 28px',
          color: '#ffffff',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          boxShadow: '0 4px 16px rgba(15, 23, 42, 0.15)',
        }}
      >
        <div>
          <Title level={3} style={{ color: '#ffffff', margin: 0, fontWeight: 700 }}>
            Xin chào, {user?.login_email.split('@')[0]} 👋
          </Title>
          <Text style={{ color: '#94a3b8', fontSize: 14 }}>
            Chào mừng bạn đến với Cổng thông tin Nhân sự & Chấm công Group 3.
          </Text>
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            {user?.roles.map((r) => (
              <Tag color={r === 'ADMIN' ? 'red' : r === 'MANAGER' ? 'orange' : 'blue'} key={r}>
                {r}
              </Tag>
            ))}
          </div>
        </div>

        <Space size="middle">
          <Button
            type="primary"
            size="large"
            icon={<QrcodeOutlined />}
            onClick={() => navigate('/kiosk')}
            style={{
              background: '#0284c7',
              borderColor: '#0284c7',
              borderRadius: 8,
              fontWeight: 600,
            }}
          >
            Quẹt thẻ Kiosk
          </Button>
          <Button
            size="large"
            icon={<CalendarOutlined />}
            onClick={() => navigate('/leaves')}
            style={{ borderRadius: 8, fontWeight: 600 }}
          >
            Xin nghỉ phép
          </Button>
        </Space>
      </div>

      {/* Office Rules Reminder Alert */}
      <Alert
        message="Quy chế làm việc nội bộ"
        description="Thời gian làm việc từ 08:00 - 17:00 (Nghỉ trưa 12:00 - 13:00 không tính giờ làm). Nhân viên cần giải trình quên chấm công và được Quản lý duyệt trước ngày chốt công cuối tháng để tránh mất ngày công."
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ borderRadius: 12, backgroundColor: '#f0f9ff', borderColor: '#bae6fd' }}
      />

      {/* Metrics Row */}
      <Row gutter={[16, 16]}>
        {/* Today's Attendance */}
        <Col xs={24} sm={12} lg={6}>
          <Card
            bordered={false}
            style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
          >
            <Statistic
              title="Chấm công hôm nay"
              value={todayRecord ? formatHours(todayRecord.worked_minutes) : 'Chưa quẹt thẻ'}
              prefix={<ClockCircleOutlined style={{ color: '#1677ff' }} />}
              valueStyle={{ fontWeight: 700, fontSize: 20 }}
            />
            <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Trạng thái:</Text>
              {todayRecord ? (
                <Tag color={todayRecord.attendance_status === 'PRESENT' ? 'success' : 'warning'}>
                  {todayRecord.attendance_status}
                </Tag>
              ) : (
                <Tag color="default">NO_RECORD</Tag>
              )}
            </div>
            {todayRecord?.first_check_in_at && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#64748b' }}>
                Vào: {new Date(todayRecord.first_check_in_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                {todayRecord.last_check_out_at && ` | Ra: ${new Date(todayRecord.last_check_out_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
              </div>
            )}
          </Card>
        </Col>

        {/* Leave Balance Remaining */}
        <Col xs={24} sm={12} lg={6}>
          <Card
            bordered={false}
            style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
          >
            <Statistic
              title="Phép năm còn lại"
              value={balance ? balance.remaining_days : 0}
              suffix={`/ ${balance ? balance.total_entitled_days : 12} ngày`}
              prefix={<CalendarOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ fontWeight: 700, fontSize: 22, color: '#52c41a' }}
            />
            <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Đã sử dụng:</Text>
              <Tag color="geekblue">{balance ? balance.used_days : 0} ngày</Tag>
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
              Hết hạn tự động vào 31/12 (Không bảo lưu)
            </div>
          </Card>
        </Col>

        {/* Manager Pending Approvals (or Personal Status) */}
        {hasRole(['MANAGER', 'ADMIN']) ? (
          <Col xs={24} sm={12} lg={6}>
            <Card
              bordered={false}
              style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
            >
              <Statistic
                title="Chờ quản lý duyệt"
                value={pendingApprovals.leaves + pendingApprovals.fixes}
                prefix={<AuditOutlined style={{ color: '#faad14' }} />}
                valueStyle={{ fontWeight: 700, fontSize: 22, color: '#d97706' }}
              />
              <div style={{ marginTop: 12, display: 'flex', gap: 6 }}>
                <Tag color="orange">{pendingApprovals.leaves} nghỉ phép</Tag>
                <Tag color="gold">{pendingApprovals.fixes} giải trình</Tag>
              </div>
              <div style={{ marginTop: 6 }}>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, fontSize: 12 }}
                  onClick={() => navigate('/leaves')}
                >
                  Duyệt ngay →
                </Button>
              </div>
            </Card>
          </Col>
        ) : (
          <Col xs={24} sm={12} lg={6}>
            <Card
              bordered={false}
              style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
            >
              <Statistic
                title="Quy định ngày công"
                value="8.0 giờ"
                suffix="/ ngày"
                prefix={<CheckCircleOutlined style={{ color: '#0284c7' }} />}
                valueStyle={{ fontWeight: 700, fontSize: 22 }}
              />
              <div style={{ marginTop: 12, fontSize: 12, color: '#64748b' }}>
                Khung giờ chuẩn: 08:00 - 17:00
              </div>
              <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
                Thứ Bảy, Chủ Nhật nghỉ
              </div>
            </Card>
          </Col>
        )}

        {/* AI Quick Assistant Widget */}
        <Col xs={24} sm={12} lg={6}>
          <Card
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
              background: 'linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%)',
              border: '1px solid #bae6fd',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <RobotOutlined style={{ color: '#1677ff', fontSize: 20 }} />
              <span style={{ fontWeight: 700, fontSize: 14 }}>HR AI Assistant</span>
            </div>
            <Paragraph style={{ fontSize: 12, color: '#64748b', margin: '4px 0 12px' }}>
              Trợ lý giải đáp luật lao động, chính sách và tạo nháp đơn nghỉ phép.
            </Paragraph>
            <Button
              type="primary"
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={() => {
                const btn = document.querySelector('.ant-btn-circle') as HTMLButtonElement;
                if (btn) btn.click();
              }}
              style={{ borderRadius: 6, fontSize: 12 }}
            >
              Hỏi AI ngay
            </Button>
          </Card>
        </Col>
      </Row>

      {/* Recent Attendance Activity */}
      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 600 }}>Lịch sử chấm công gần đây</span>
            <Button type="link" onClick={() => navigate('/attendance')}>
              Xem tất cả →
            </Button>
          </div>
        }
        bordered={false}
        style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
      >
        <Table
          dataSource={recentRecords}
          rowKey="attendance_day_id"
          pagination={false}
          size="middle"
          columns={[
            {
              title: 'Ngày làm việc',
              dataIndex: 'work_date',
              key: 'work_date',
              render: (d) => <b>{d}</b>,
            },
            {
              title: 'Vào (Check-in)',
              dataIndex: 'first_check_in_at',
              key: 'first_check_in_at',
              render: (t) => (t ? new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'),
            },
            {
              title: 'Ra (Check-out)',
              dataIndex: 'last_check_out_at',
              key: 'last_check_out_at',
              render: (t) => (t ? new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'),
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
                return <Tag color={color}>{status}</Tag>;
              },
            },
          ]}
        />
      </Card>
    </div>
  );
};
