import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Input, Button, Tag, Typography, Alert, Space, Divider, Tooltip } from 'antd';
import {
  QrcodeOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CameraOutlined,
  StopOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import confetti from 'canvas-confetti';
import jsQR from 'jsqr';
import api from '../api/client';

const { Text } = Typography;

export const KioskScanPage: React.FC = () => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [qrCode, setQrCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastScanResult, setLastScanResult] = useState<any | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  // Camera states
  const [cameraActive, setCameraActive] = useState<boolean>(true);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [cameraLoading, setCameraLoading] = useState<boolean>(false);

  const inputRef = useRef<any>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameIdRef = useRef<number | null>(null);
  const lastScanTimestampRef = useRef<number>(0);
  const isProcessingRef = useRef<boolean>(false);

  // Live clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Auto focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [lastScanResult, scanError]);

  // Audio feedback
  const playBeep = (isSuccess: boolean) => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const audioCtx = new AudioCtx();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = isSuccess ? 'sine' : 'sawtooth';
      osc.frequency.setValueAtTime(isSuccess ? 880 : 250, audioCtx.currentTime);
      gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + (isSuccess ? 0.2 : 0.4));
    } catch {
      // AudioContext might require user interaction first
    }
  };

  const handleScan = useCallback(async (codeToScan?: string) => {
    const code = (codeToScan || qrCode).trim();
    if (!code || isProcessingRef.current) return;

    isProcessingRef.current = true;
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
            'X-Kiosk-Secret': 'kiosk_secret_device_authorization_token_hr_group3',
          },
        }
      );

      playBeep(true);
      confetti({
        particleCount: 60,
        spread: 70,
        origin: { y: 0.65 },
      });

      setLastScanResult(res.data);
      setQrCode('');

      // Auto clear after 4 seconds
      setTimeout(() => {
        setLastScanResult(null);
        isProcessingRef.current = false;
        inputRef.current?.focus();
      }, 4000);
    } catch (err: any) {
      playBeep(false);
      const errMsg = err.response?.data?.detail || 'Thẻ QR không hợp lệ hoặc thiết bị chưa được ủy quyền!';
      setScanError(errMsg);
      setTimeout(() => {
        setScanError(null);
        isProcessingRef.current = false;
        inputRef.current?.focus();
      }, 3500);
    } finally {
      setLoading(false);
    }
  }, [qrCode]);

  // QR Scanning loop from Camera
  const scanQrFrame = useCallback(() => {
    if (!videoRef.current || videoRef.current.readyState !== videoRef.current.HAVE_ENOUGH_DATA) {
      animFrameIdRef.current = requestAnimationFrame(scanQrFrame);
      return;
    }

    const video = videoRef.current;
    if (!canvasRef.current) {
      canvasRef.current = document.createElement('canvas');
    }
    const canvas = canvasRef.current;

    // Downscale slightly for fast 60fps processing
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w;
    canvas.height = h;

    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (ctx) {
      ctx.drawImage(video, 0, 0, w, h);
      const imageData = ctx.getImageData(0, 0, w, h);
      const qrFound = jsQR(imageData.data, imageData.width, imageData.height, {
        inversionAttempts: 'attemptBoth',
      });

      if (qrFound && qrFound.data) {
        const now = Date.now();
        // Prevent duplicate burst scans (cooldown 3.5s)
        if (now - lastScanTimestampRef.current > 3500 && !isProcessingRef.current) {
          lastScanTimestampRef.current = now;
          handleScan(qrFound.data);
        }
      }
    }

    animFrameIdRef.current = requestAnimationFrame(scanQrFrame);
  }, [handleScan]);

  // Start Camera
  const startCamera = useCallback(async () => {
    setCameraLoading(true);
    setCameraError(null);

    // Stop existing stream if any
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Trình duyệt không hỗ trợ WebRTC Camera API.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.setAttribute('playsinline', 'true');
        await videoRef.current.play();
      }

      setCameraActive(true);
      setCameraError(null);
      animFrameIdRef.current = requestAnimationFrame(scanQrFrame);
    } catch (err: any) {
      console.warn('Cannot start camera:', err);
      let errorMsg = 'Không thể kết nối với Camera.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        errorMsg = 'Trình duyệt chưa được cấp quyền sử dụng Camera. Vui lòng bấm vào biểu tượng 🔒 hoặc Camera trên thanh địa chỉ để cấp quyền Cho phép (Allow).';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        errorMsg = 'Không tìm thấy thiết bị Camera nào trên máy tính của bạn.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        errorMsg = 'Camera đang bị ứng dụng khác sử dụng (Zoom, Teams, v.v.). Vui lòng tắt ứng dụng đó và thử lại.';
      }
      setCameraError(errorMsg);
      setCameraActive(false);
    } finally {
      setCameraLoading(false);
    }
  }, [scanQrFrame]);

  // Stop Camera
  const stopCamera = useCallback(() => {
    if (animFrameIdRef.current) {
      cancelAnimationFrame(animFrameIdRef.current);
      animFrameIdRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  // Initialize Camera on mount, cleanup on unmount
  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
    };
  }, [startCamera, stopCamera]);

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
        styles={{ body: { padding: '36px 32px' } }}
      >
        {/* Clock Header */}
        <div style={{ marginBottom: 20 }}>
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
          <div style={{ marginTop: 6, fontSize: 12, color: '#94a3b8' }}>
            Giờ làm việc: <b>08:00 - 17:00</b> (Nghỉ trưa 12:00 - 13:00)
          </div>
        </div>

        {/* Camera Live Scanner Container */}
        <div
          style={{
            margin: '0 auto 20px',
            width: 320,
            height: 320,
            borderRadius: 24,
            overflow: 'hidden',
            backgroundColor: '#0f172a',
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: cameraActive ? '0 0 25px rgba(37, 99, 235, 0.35)' : 'none',
            border: '3px solid #334155',
          }}
        >
          {/* Live Video Feed */}
          <video
            ref={videoRef}
            muted
            playsInline
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              transform: 'scaleX(-1)', // Mirror feed for natural user experience
              display: cameraActive ? 'block' : 'none',
            }}
          />

          {/* Animated Laser Scanning Line */}
          {cameraActive && <div className="scan-laser" />}

          {/* Viewfinder Corner Overlays */}
          {cameraActive && (
            <div
              style={{
                position: 'absolute',
                top: 24,
                left: 24,
                right: 24,
                bottom: 24,
                pointerEvents: 'none',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div style={{ width: 28, height: 28, borderTop: '4px solid #38bdf8', borderLeft: '4px solid #38bdf8', borderRadius: '4px 0 0 0' }} />
                <div style={{ width: 28, height: 28, borderTop: '4px solid #38bdf8', borderRight: '4px solid #38bdf8', borderRadius: '0 4px 0 0' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div style={{ width: 28, height: 28, borderBottom: '4px solid #38bdf8', borderLeft: '4px solid #38bdf8', borderRadius: '0 0 0 4px' }} />
                <div style={{ width: 28, height: 28, borderBottom: '4px solid #38bdf8', borderRight: '4px solid #38bdf8', borderRadius: '0 0 4px 0' }} />
              </div>
            </div>
          )}

          {/* Fallback View when Camera is Inactive or Denied */}
          {!cameraActive && (
            <div style={{ padding: 24, color: '#94a3b8' }}>
              <QrcodeOutlined style={{ fontSize: 64, color: '#64748b', marginBottom: 12 }} />
              <div style={{ fontSize: 13, fontWeight: 600, color: '#f8fafc', marginBottom: 6 }}>
                Camera hiện đang tắt
              </div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 16 }}>
                Bạn có thể bật camera hoặc dùng ô nhập mã / nút thử nghiệm bên dưới.
              </div>
              <Button
                type="primary"
                icon={<CameraOutlined />}
                loading={cameraLoading}
                onClick={startCamera}
                style={{ borderRadius: 8, background: '#2563eb' }}
              >
                Mở lại Camera
              </Button>
            </div>
          )}

          {/* Camera Status Badge */}
          {cameraActive && (
            <div
              style={{
                position: 'absolute',
                bottom: 12,
                left: '50%',
                transform: 'translateX(-50%)',
                background: 'rgba(15, 23, 42, 0.75)',
                backdropFilter: 'blur(6px)',
                color: '#38bdf8',
                padding: '4px 12px',
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                zIndex: 15,
                border: '1px solid rgba(56, 189, 248, 0.3)',
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: '#22c55e',
                  display: 'inline-block',
                  boxShadow: '0 0 6px #22c55e',
                }}
              />
              Đang quét mã QR từ Camera...
            </div>
          )}
        </div>

        {/* Camera Controls & Status Notice */}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          {cameraActive ? (
            <Button
              size="small"
              icon={<StopOutlined />}
              onClick={stopCamera}
              style={{ borderRadius: 16, fontSize: 12 }}
            >
              Tắt Camera
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<CameraOutlined />}
              loading={cameraLoading}
              onClick={startCamera}
              style={{ borderRadius: 16, fontSize: 12, background: '#2563eb' }}
            >
              Bật Camera quét mã
            </Button>
          )}
        </div>

        {/* Camera Error Notice if any */}
        {cameraError && (
          <Alert
            message="Thông báo về Camera"
            description={cameraError}
            type="warning"
            showIcon
            action={
              <Button size="small" type="primary" ghost icon={<ReloadOutlined />} onClick={startCamera}>
                Thử lại
              </Button>
            }
            style={{ maxWidth: 520, margin: '0 auto 20px', borderRadius: 10, textAlign: 'left' }}
          />
        )}

        {/* Manual Barcode / Text Input (Auto-focused) */}
        <div style={{ maxWidth: 460, margin: '0 auto 20px' }}>
          <Input.Search
            ref={inputRef}
            size="large"
            placeholder="Mã thẻ QR (Quét máy đọc barcode hoặc nhập tay)..."
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
              maxWidth: 500,
              margin: '0 auto 20px',
              padding: '16px 20px',
              borderRadius: 12,
              backgroundColor: '#f0fdf4',
              border: '1px solid #86efac',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <CheckCircleFilled style={{ color: '#16a34a', fontSize: 28 }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: 16, color: '#15803d' }}>
                  {lastScanResult.message || 'Chấm công thành công!'}
                </div>
                <div style={{ fontSize: 12, color: '#166534', marginTop: 2 }}>
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
            style={{ maxWidth: 500, margin: '0 auto 20px', borderRadius: 10, textAlign: 'left' }}
          />
        )}

        <Divider style={{ margin: '20px 0 16px', fontSize: 12, color: '#94a3b8' }}>
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

        <div style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 12, color: '#94a3b8' }}>
            ℹ️ Lưu ý: Nếu camera không tự động mở, hãy bấm <b>"Cho phép" (Allow)</b> khi trình duyệt hỏi quyền sử dụng Webcam.
          </Text>
        </div>
      </Card>
    </div>
  );
};
