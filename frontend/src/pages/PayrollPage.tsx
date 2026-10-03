import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Modal,
  Form,
  InputNumber,
  Select,
  message,
  Popconfirm,
  Typography,
  Alert,
  Tabs,
  Row,
  Col,
  Statistic,
} from 'antd';
import {
  DollarOutlined,
  CalculatorOutlined,
  DownloadOutlined,
  LockOutlined,
  PlusOutlined,
  FileExcelOutlined,
  InfoCircleOutlined,
  UserOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import type { PayrollPeriod, PayrollLine } from '../types';

const { Title, Text } = Typography;

export const PayrollPage: React.FC = () => {
  const { user, hasRole } = useAuth();
  const isAdminOrHR = hasRole(['ADMIN', 'HR']);
  const [activeTab, setActiveTab] = useState(isAdminOrHR ? 'periods' : 'my-slips');

  // Admin states
  const [periods, setPeriods] = useState<PayrollPeriod[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<PayrollPeriod | null>(null);
  const [lines, setLines] = useState<PayrollLine[]>([]);
  const [loadingPeriods, setLoadingPeriods] = useState(false);
  const [loadingLines, setLoadingLines] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [createPeriodModalOpen, setCreatePeriodModalOpen] = useState(false);

  // Employee states
  const [mySlips, setMySlips] = useState<PayrollLine[]>([]);
  const [loadingSlips, setLoadingSlips] = useState(false);

  const fetchPeriods = async () => {
    if (!isAdminOrHR) return;
    try {
      setLoadingPeriods(true);
      const res = await api.get('/payroll/periods');
      setPeriods(res.data);
      if (res.data.length > 0 && !selectedPeriod) {
        setSelectedPeriod(res.data[0]);
        fetchPeriodLines(res.data[0].payroll_period_id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingPeriods(false);
    }
  };

  const fetchPeriodLines = async (periodId: number) => {
    try {
      setLoadingLines(true);
      const res = await api.get(`/payroll/periods/${periodId}/lines`);
      setLines(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingLines(false);
    }
  };

  const fetchMySlips = async () => {
    try {
      setLoadingSlips(true);
      const res = await api.get('/payroll/me/slips');
      setMySlips(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSlips(false);
    }
  };

  useEffect(() => {
    if (isAdminOrHR) {
      fetchPeriods();
    }
    fetchMySlips();
  }, []);

  const handleSelectPeriod = (period: PayrollPeriod) => {
    setSelectedPeriod(period);
    fetchPeriodLines(period.payroll_period_id);
  };

  const handleCreatePeriod = async (values: any) => {
    try {
      const year = values.year;
      const month = values.month;
      const startDate = dayjs(`${year}-${month}-01`).format('YYYY-MM-DD');
      const endDate = dayjs(`${year}-${month}-01`).endOf('month').format('YYYY-MM-DD');

      const res = await api.post('/payroll/periods', {
        period_year: year,
        period_month: month,
        start_date: startDate,
        end_date: endDate,
      });

      message.success(`Đã khởi tạo kỳ lương tháng ${month}/${year}!`);
      setCreatePeriodModalOpen(false);
      fetchPeriods();
      handleSelectPeriod(res.data);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi tạo kỳ lương!');
    }
  };

  const handleCalculatePayroll = async () => {
    if (!selectedPeriod) return;
    try {
      setCalculating(true);
      await api.post(`/payroll/periods/${selectedPeriod.payroll_period_id}/calculate`);
      message.success('Tính toán bảng lương hoàn tất!');
      fetchPeriods();
      fetchPeriodLines(selectedPeriod.payroll_period_id);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi tính lương!');
    } finally {
      setCalculating(false);
    }
  };

  const handleClosePeriod = async () => {
    if (!selectedPeriod) return;
    try {
      await api.post(`/payroll/periods/${selectedPeriod.payroll_period_id}/close`);
      message.success('Đã khóa kỳ lương thành công! Dữ liệu chấm công kỳ này đã được cố định.');
      fetchPeriods();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Lỗi khi khóa kỳ lương!');
    }
  };

  const handleExportExcel = async () => {
    if (!selectedPeriod) return;
    try {
      const response = await api.get(`/payroll/periods/${selectedPeriod.payroll_period_id}/export`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Bang_Luong_Thang_${selectedPeriod.period_month}_${selectedPeriod.period_year}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      message.success('Đã tải xuống file Excel bảng lương!');
    } catch (err) {
      message.error('Lỗi khi xuất file Excel!');
    }
  };

  const formatVND = (num: number) => {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(num || 0);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Quản lý Bảng lương & Thuế TNCN</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            Lương GROSS • BHXH 8%, BHYT 1.5%, BHTN 1% (Tổng 10.5%) • Giảm trừ 11M • Biểu thuế TNCN lũy tiến
          </Text>
        </div>

        {isAdminOrHR && (
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreatePeriodModalOpen(true)}
              style={{ borderRadius: 8, background: '#1677ff' }}
            >
              Tạo kỳ lương mới
            </Button>
          </Space>
        )}
      </div>

      <Alert
        message="Nguyên tắc tính lương & bảo mật"
        description="Mỗi nhân viên chỉ có thể xem phiếu lương cá nhân của chính mình. Sau khi HR/Admin nhấn 'Khóa kỳ lương', hệ thống sẽ chốt dữ liệu và không thể duyệt giải trình công hay đơn nghỉ phép của tháng đó nữa."
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ borderRadius: 10 }}
      />

      {/* Tabs */}
      <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k)}
          items={[
            ...(isAdminOrHR
              ? [
                  {
                    key: 'periods',
                    label: 'Quản lý Kỳ lương (HR/Admin)',
                    children: (
                      <div>
                        {/* Period selector & Action Bar */}
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: 12,
                            padding: '16px 20px',
                            backgroundColor: '#f8fafc',
                            borderRadius: 10,
                            marginBottom: 20,
                            border: '1px solid #e2e8f0',
                          }}
                        >
                          <Space size="middle">
                            <span style={{ fontWeight: 600 }}>Chọn kỳ lương:</span>
                            <Select
                              value={selectedPeriod?.payroll_period_id}
                              style={{ width: 180 }}
                              onChange={(id) => {
                                const p = periods.find((item) => item.payroll_period_id === id);
                                if (p) handleSelectPeriod(p);
                              }}
                            >
                              {periods.map((p) => (
                                <Select.Option key={p.payroll_period_id} value={p.payroll_period_id}>
                                  Tháng {p.period_month}/{p.period_year} ({p.status})
                                </Select.Option>
                              ))}
                            </Select>

                            {selectedPeriod && (
                              <Tag
                                color={
                                  selectedPeriod.status === 'CLOSED'
                                    ? 'red'
                                    : selectedPeriod.status === 'CALCULATED'
                                    ? 'green'
                                    : 'orange'
                                }
                              >
                                {selectedPeriod.status}
                              </Tag>
                            )}
                          </Space>

                          {selectedPeriod && (
                            <Space size="small">
                              <Button
                                type="primary"
                                icon={<CalculatorOutlined />}
                                loading={calculating}
                                disabled={selectedPeriod.status === 'CLOSED'}
                                onClick={handleCalculatePayroll}
                                style={{ background: '#16a34a' }}
                              >
                                Tính bảng lương
                              </Button>

                              <Button
                                icon={<FileExcelOutlined />}
                                onClick={handleExportExcel}
                                disabled={lines.length === 0}
                              >
                                Xuất file Excel
                              </Button>

                              {selectedPeriod.status !== 'CLOSED' && (
                                <Popconfirm
                                  title="Khóa kỳ lương"
                                  description="Sau khi khóa, kỳ lương sẽ được chốt và không thể sửa đổi hay duyệt bù công nữa. Bạn chắc chắn chứ?"
                                  onConfirm={handleClosePeriod}
                                  okText="Khóa kỳ lương"
                                  cancelText="Hủy"
                                  okButtonProps={{ danger: true }}
                                >
                                  <Button danger icon={<LockOutlined />}>
                                    Khóa kỳ lương
                                  </Button>
                                </Popconfirm>
                              )}
                            </Space>
                          )}
                        </div>

                        {/* Salary Lines Table */}
                        <Table
                          dataSource={lines}
                          rowKey="payroll_line_id"
                          loading={loadingLines}
                          scroll={{ x: 1100 }}
                          columns={[
                            {
                              title: 'Mã NV',
                              dataIndex: 'employee_id',
                              key: 'employee_id',
                              width: 90,
                              render: (id) => <Tag color="blue">NV#{id}</Tag>,
                            },
                            {
                              title: 'Lương Gross',
                              dataIndex: 'base_salary',
                              key: 'base_salary',
                              render: (s) => formatVND(s),
                            },
                            {
                              title: 'Công chuẩn',
                              dataIndex: 'standard_work_days',
                              key: 'standard_work_days',
                              width: 100,
                            },
                            {
                              title: 'Công thực tế',
                              dataIndex: 'actual_work_days',
                              key: 'actual_work_days',
                              width: 110,
                              render: (d) => <b>{d}</b>,
                            },
                            {
                              title: 'Phụ cấp',
                              dataIndex: 'allowance_amount',
                              key: 'allowance_amount',
                              render: (a) => formatVND(a),
                            },
                            {
                              title: 'Lương thực tế',
                              dataIndex: 'gross_salary',
                              key: 'gross_salary',
                              render: (g) => formatVND(g),
                            },
                            {
                              title: 'BHXH/YT/TN (10.5%)',
                              dataIndex: 'insurance_deduction',
                              key: 'insurance_deduction',
                              render: (i) => <span style={{ color: '#ea580c' }}>-{formatVND(i)}</span>,
                            },
                            {
                              title: 'Thuế TNCN',
                              dataIndex: 'personal_income_tax',
                              key: 'personal_income_tax',
                              render: (t) => <span style={{ color: '#dc2626' }}>-{formatVND(t)}</span>,
                            },
                            {
                              title: 'Lương thực nhận (NET)',
                              dataIndex: 'net_salary',
                              key: 'net_salary',
                              fixed: 'right',
                              render: (n) => <b style={{ color: '#16a34a', fontSize: 14 }}>{formatVND(n)}</b>,
                            },
                          ]}
                        />
                      </div>
                    ),
                  },
                ]
              : []),
            {
              key: 'my-slips',
              label: 'Phiếu lương của tôi',
              children: (
                <div>
                  <Table
                    dataSource={mySlips}
                    rowKey="payroll_line_id"
                    loading={loadingSlips}
                    columns={[
                      {
                        title: 'Kỳ lương ID',
                        dataIndex: 'payroll_period_id',
                        key: 'payroll_period_id',
                        render: (id) => <Tag color="geekblue">Kỳ #{id}</Tag>,
                      },
                      {
                        title: 'Lương hợp đồng (Gross)',
                        dataIndex: 'base_salary',
                        key: 'base_salary',
                        render: (s) => formatVND(s),
                      },
                      {
                        title: 'Công thực tế / Công chuẩn',
                        key: 'work_days',
                        render: (_, record) => `${record.actual_work_days} / ${record.standard_work_days} ngày`,
                      },
                      {
                        title: 'Tổng bảo hiểm (10.5%)',
                        dataIndex: 'insurance_deduction',
                        key: 'insurance_deduction',
                        render: (i) => <span style={{ color: '#ea580c' }}>-{formatVND(i)}</span>,
                      },
                      {
                        title: 'Thuế TNCN',
                        dataIndex: 'personal_income_tax',
                        key: 'personal_income_tax',
                        render: (t) => <span style={{ color: '#dc2626' }}>-{formatVND(t)}</span>,
                      },
                      {
                        title: 'Thực nhận (NET)',
                        dataIndex: 'net_salary',
                        key: 'net_salary',
                        render: (n) => <b style={{ color: '#16a34a', fontSize: 15 }}>{formatVND(n)}</b>,
                      },
                    ]}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* Modal create payroll period */}
      <Modal
        open={createPeriodModalOpen}
        onCancel={() => setCreatePeriodModalOpen(false)}
        title="Tạo kỳ lương mới"
        footer={null}
        width={420}
      >
        <Form
          layout="vertical"
          onFinish={handleCreatePeriod}
          initialValues={{ year: new Date().getFullYear(), month: new Date().getMonth() + 1 }}
        >
          <Form.Item name="year" label="Năm" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={2020} max={2030} />
          </Form.Item>

          <Form.Item name="month" label="Tháng" rules={[{ required: true }]}>
            <Select>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <Select.Option key={m} value={m}>
                  Tháng {m}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <Button onClick={() => setCreatePeriodModalOpen(false)}>Hủy</Button>
            <Button type="primary" htmlType="submit">
              Khởi tạo
            </Button>
          </div>
        </Form>
      </Modal>
    </div>
  );
};
