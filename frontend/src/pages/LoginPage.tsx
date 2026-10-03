import React, { useState } from 'react';
import { Card, Form, Input, Button, Alert, Typography, Divider, Space, Tag } from 'antd';
import { UserOutlined, LockOutlined, ThunderboltOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const { Title, Text, Paragraph } = Typography;

export const LoginPage: React.FC = () => {
  const [form] = Form.useForm();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (values: { email: string; pass: string }) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      await login(values.email, values.pass);
      navigate('/dashboard');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Đăng nhập không thành công. Vui lòng kiểm tra lại thông tin!');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (email: string) => {
    form.setFieldsValue({ email, pass: 'Password@123' });
    setLoading(true);
    setErrorMsg(null);
    try {
      await login(email, 'Password@123');
      navigate('/dashboard');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Lỗi đăng nhập nhanh!');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0369a1 100%)',
        padding: 20,
      }}
    >
      <Card
        style={{
          width: 460,
          borderRadius: 16,
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.3)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'rgba(255, 255, 255, 0.98)',
        }}
        styles={{ body: { padding: '36px 32px' } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: 'linear-gradient(135deg, #1677ff 0%, #0284c7 100%)',
              color: '#ffffff',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 26,
              fontWeight: 800,
              boxShadow: '0 6px 18px rgba(22, 119, 255, 0.35)',
              marginBottom: 12,
            }}
          >
            HR
          </div>
          <Title level={3} style={{ margin: 0, fontWeight: 700, color: '#0f172a' }}>
            HR System with AI
          </Title>
          <Text style={{ color: '#64748b', fontSize: 13 }}>
            Hệ thống Quản lý Nhân sự & Chấm công - Group 3
          </Text>
        </div>

        {errorMsg && (
          <Alert
            message={errorMsg}
            type="error"
            showIcon
            closable
            onClose={() => setErrorMsg(null)}
            style={{ marginBottom: 20, borderRadius: 8 }}
          />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          requiredMark={false}
          initialValues={{ email: 'admin@hrgroup3.com', pass: 'Password@123' }}
        >
          <Form.Item
            name="email"
            label={<span style={{ fontWeight: 600, fontSize: 13 }}>Email đăng nhập</span>}
            rules={[
              { required: true, message: 'Vui lòng nhập email!' },
              { type: 'email', message: 'Email không đúng định dạng!' },
            ]}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#94a3b8' }} />}
              placeholder="name@hrgroup3.com"
              size="large"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Form.Item
            name="pass"
            label={<span style={{ fontWeight: 600, fontSize: 13 }}>Mật khẩu</span>}
            rules={[{ required: true, message: 'Vui lòng nhập mật khẩu!' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
              placeholder="••••••••"
              size="large"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Button
            type="primary"
            htmlType="submit"
            size="large"
            block
            loading={loading}
            style={{
              height: 44,
              borderRadius: 8,
              fontWeight: 600,
              background: '#1677ff',
              marginTop: 8,
            }}
          >
            Đăng nhập hệ thống
          </Button>
        </Form>

        <Divider style={{ margin: '24px 0 16px', fontSize: 12, color: '#94a3b8' }}>
          HOẶC ĐĂNG NHẬP NHANH (DEMO)
        </Divider>

        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Button
            block
            icon={<SafetyCertificateOutlined style={{ color: '#dc2626' }} />}
            onClick={() => handleQuickLogin('admin@hrgroup3.com')}
            disabled={loading}
            style={{ borderRadius: 8, textAlign: 'left', display: 'flex', alignItems: 'center' }}
          >
            <span style={{ fontWeight: 600, flex: 1 }}>Admin & HR</span>
            <Tag color="red" style={{ margin: 0 }}>admin@hrgroup3.com</Tag>
          </Button>

          <Button
            block
            icon={<ThunderboltOutlined style={{ color: '#ea580c' }} />}
            onClick={() => handleQuickLogin('manager@hrgroup3.com')}
            disabled={loading}
            style={{ borderRadius: 8, textAlign: 'left', display: 'flex', alignItems: 'center' }}
          >
            <span style={{ fontWeight: 600, flex: 1 }}>Quản lý (Manager)</span>
            <Tag color="orange" style={{ margin: 0 }}>manager@hrgroup3.com</Tag>
          </Button>

          <Button
            block
            icon={<UserOutlined style={{ color: '#2563eb' }} />}
            onClick={() => handleQuickLogin('employee@hrgroup3.com')}
            disabled={loading}
            style={{ borderRadius: 8, textAlign: 'left', display: 'flex', alignItems: 'center' }}
          >
            <span style={{ fontWeight: 600, flex: 1 }}>Nhân viên (Employee)</span>
            <Tag color="blue" style={{ margin: 0 }}>employee@hrgroup3.com</Tag>
          </Button>
        </Space>

        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <Text style={{ fontSize: 11, color: '#94a3b8' }}>
            Mật khẩu mặc định cho các tài khoản demo: <code>Password@123</code>
          </Text>
        </div>
      </Card>
    </div>
  );
};
