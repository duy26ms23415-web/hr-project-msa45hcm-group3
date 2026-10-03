import React, { useState, useEffect, useRef } from 'react';
import { Card, Input, Button, Tag, Typography, Alert, Space, Divider, message } from 'antd';
import {
  QrcodeOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CameraOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import confetti from 'canvas-confetti';
import api from '../api/client';

const { Title, Text, Paragraph } = Typography;

export const KioskScanPage: React.FC = () => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [qrCode, setQrCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastScanResult, setLastScanResult] = useState<any | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const inputRef = useRef<any>(null);

  // Live clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Auto focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [lastScanResult, scanError]);

  // Audio beep
  const playBeep = (isSuccess: boolean) => {
    try {
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = isSuccess ? 'sine' : 'sawtooth';
      osc.frequency.setValueAtTime(isSuccess ? 800 : 300, audioCtx.currentTime);
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + (isSuccess ? 0.18 : 0.35));
    } catch {
      // AudioContext may be restricted before user gesture
    }
  };

  const handleScan = async (codeToScan?: string) => {
    const code = (codeToScan || qrCode).trim();
    if (!code || loading) return;

    setLoading(true);
    setScanError(null);
    setLastScanResult(null);

    try {
      const res = await api.post(
        '/attendance/kiosk/scan',
        {
          qr_code: code,
          device_id: 'KIOSK_MAIN_OFFICE',
          scan_timestamp: new Date().toISOString(),
        },
        {
          headers: {
            'X-Kiosk-Secret': 'kiosk_secret_key_group3',
          },
        }
      );

      playBeep(true);
      confetti({
        particleCount: 50,
        spread: 60,
        origin: { y: 0.7 },
      });

      setLastScanResult(res.data);
      setQrCode('');

      // Auto clear after 4 seconds
      setTimeout(() => {
        setLastScanResult(null);
        inputRef.current?.focus();
      }, 4000);
    } catch (err: any) {
      playBeep(false);
      setScanError(err.response?.data?.detail || 'Thẻ QR không hợp lệ hoặc thiết bị chưa được ủy quyền!');
      setTimeout(() => {
        setScanError(null);
        inputRef.current?.focus();
      }, 3500);
    } finally {
      setLoading(false);
    }
  };

  const demoQRCards = [
    { label: 'Admin (EMP001)', code: 'EMP001_QR_STATIC' },
    { label: 'Manager (EMP002)', code: 'EMP002_QR_STATIC' },
    { label: 'Employee (EMP003)', code: 'EMP003_QR_STATIC' },
  ];

  return (
    <div
      style={{
        maxWidth: 780,
        margin: '0 auto',
        padding: '20px 0',
      }}
    >
      <Card
        style={{
          borderRadius: 20,
          boxShadow: '0 10px 30px rgba(0,0,0,0.06)',
          border: '1px solid #e2e8f0',
          textAlign: 'center',
          overflow: 'hidden',
        }}
        styles={{ body: { padding: '40px 36px' } }}
      >
        {/* Clock Header */}
        <div style={{ marginBottom: 24 }}>
          <Tag color="blue" style={{ padding: '6px 14px', fontSize: 13, borderRadius: 20, marginBottom: 12 }}>
            🏢 TRỤ SỞ DUY NHẤT - MÁY CHẤM CÔNG KIOSK
          </Tag>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 52,
              fontWeight: 800,
              color: '#0f172a',
              letterSpacing: 2,
              lineHeight: 1.1,
            }}
          >
            {currentTime.toLocaleTimeString([], { hour12: false })}
          </div>
          <div style={{ fontSize: 15, color: '#64748b', marginTop: 6 }}>
            {currentTime.toLocaleDateString('vi-VN', {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#94a3b8' }}>
            Giờ làm việc: <b>08:00 - 17:00</b> (Nghỉ trưa 12:00 - 13:00)
          </div>
        </div>

        {/* Scanner Visual Container */}
        <div
          style={{
            margin: '0 auto 28px',
            width: 220,
            height: 220,
            borderRadius: 20,
            border: '3px dashed #3b82f6',
            backgroundColor: '#f8fafc',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}
          className="kiosk-glow"
        >
          <QrcodeOutlined style={{ fontSize: 72, color: '#3b82f6', marginBottom: 12 }} />
          <Text style={{ fontSize: 13, color: '#64748b', fontWeight: 600 }}>
            ĐẶT THẺ QR VÀO ĐÂY
          </Text>
        </div>

        {/* Scan input (auto-focused) */}
        <div style={{ maxWidth: 440, margin: '0 auto 20px' }}>
          <Input.Search
            ref={inputRef}
            size="large"
            placeholder="Mã thẻ QR (Quét tự động hoặc nhập)..."
            value={qrCode}
            onChange={(e) => setQrCode(e.target.value)}
            onSearch={() => handleScan()}
            enterButton={
              <Button type="primary" loading={loading} style={{ background: '#1677ff' }}>
                Quẹt thẻ
              </Button>
            }
            style={{ borderRadius: 8 }}
          />
        </div>

        {/* Success Alert */}
        {lastScanResult && (
          <div
            className="fade-in"
            style={{
              maxWidth: 480,
              margin: '0 auto 20px',
              padding: '16px 20px',
              borderRadius: 12,
              backgroundColor: '#f0fdf4',
              border: '1px solid #86efac',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <CheckCircleFilled style={{ color: '#16a34a', fontSize: 24 }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: 16, color: '#15803d' }}>
                  {lastScanResult.message || 'Chấm công thành công!'}
                </div>
                <div style={{ fontSize: 12, color: '#166534' }}>
                  Loại quẹt: <b>{lastScanResult.event_type}</b> • Thời gian: {new Date(lastScanResult.event_time).toLocaleTimeString()}
                </div>
              </div>
            </div>
            {lastScanResult.worked_minutes !== undefined && (
              <div style={{ fontSize: 13, color: '#14532d', marginTop: 4 }}>
                Tổng thời gian làm việc hôm nay: <b>{Math.floor(lastScanResult.worked_minutes / 60)}h {lastScanResult.worked_minutes % 60}p</b>
              </div>
            )}
          </div>
        )}

        {/* Error Alert */}
        {scanError && (
          <Alert
            message="Quẹt thẻ thất bại"
            description={scanError}
            type="error"
            showIcon
            style={{ maxWidth: 480, margin: '0 auto 20px', borderRadius: 10, textAlign: 'left' }}
          />
        )}

        <Divider style={{ margin: '24px 0 16px', fontSize: 12, color: '#94a3b8' }}>
          THỬ NGHIỆM NHANH VỚI THẺ QR MẪU
        </Divider>

        {/* Demo Fast Scan Buttons */}
        <Space wrap size="small" style={{ justifyContent: 'center' }}>
          {demoQRCards.map((item) => (
            <Button
              key={item.code}
              icon={<ThunderboltOutlined />}
              onClick={() => handleScan(item.code)}
              loading={loading}
              style={{ borderRadius: 8, fontSize: 12 }}
            >
              Quẹt: <b>{item.label}</b>
            </Button>
          ))}
        </Space>

        <div style={{ marginTop: 24 }}>
          <Text style={{ fontSize: 12, color: '#94a3b8' }}>
            ℹ️ Lưu ý: Nếu quên check-in hoặc check-out, vui lòng gửi đơn <b>Giải trình chấm công</b> trước ngày chốt công cuối tháng.
          </Text>
        </div>
      </Card>
    </div>
  );
};
