import React, { useState, useRef, useEffect } from 'react';
import { Modal, Input, Button, Tag, Card, Spin, Space, Typography, Tooltip } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined, ThunderboltOutlined, CalendarOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import api from '../api/client';
import { useNavigate } from 'react-router-dom';

const { Text, Paragraph } = Typography;

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: {
    action_type: string;
    data?: any;
  };
  timestamp: string;
}

interface AIChatModalProps {
  open: boolean;
  onClose: () => void;
}

export const AIChatModal: React.FC<AIChatModalProps> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Xin chào! Tôi là Trợ lý AI Nhân sự Group 3. Bạn có thể hỏi tôi về quy chế chấm công, số dư ngày phép, hoặc yêu cầu hỗ trợ tạo đơn nghỉ phép/giải trình.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [inputVal, setInputVal] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (open) {
      setTimeout(scrollToBottom, 150);
    }
  }, [open, messages]);

  const quickPrompts = [
    'Quy chế giờ làm việc và nghỉ trưa?',
    'Số dư phép năm của tôi còn bao nhiêu?',
    'Tôi muốn xin nghỉ phép sáng mai',
    'Tôi quên quẹt thẻ thì phải làm sao?',
  ];

  const handleSendMessage = async (textToSend?: string) => {
    const text = textToSend || inputVal.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputVal('');
    setLoading(true);

    try {
      const history = messages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await api.post('/ai/chat', {
        message: text,
        conversation_history: history,
      });

      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.data.reply,
        action: res.data.action,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Xin lỗi, hiện tại tôi gặp sự cố kết nối. Vui lòng thử lại sau giây lát!',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleActionClick = (action: { action_type: string; data?: any }) => {
    onClose();
    if (action.action_type === 'DRAFT_LEAVE' || action.action_type === 'NAVIGATE') {
      navigate('/leaves');
    } else if (action.action_type === 'DRAFT_FIX') {
      navigate('/attendance');
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              backgroundColor: '#e6f4ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#1677ff',
              fontSize: 18,
            }}
          >
            <RobotOutlined />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 16 }}>HR AI Assistant</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Trợ lý giải đáp chính sách & tạo đơn tự động</div>
          </div>
        </div>
      }
      width={680}
      styles={{
        body: { padding: '16px 20px', display: 'flex', flexDirection: 'column', height: '620px' },
      }}
    >
      {/* Messages list */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          paddingRight: 8,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              alignItems: 'flex-start',
              gap: 10,
            }}
          >
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                backgroundColor: msg.role === 'user' ? '#1677ff' : '#f0f5ff',
                color: msg.role === 'user' ? '#fff' : '#1677ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 14,
                flexShrink: 0,
              }}
            >
              {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
            </div>

            <div style={{ maxWidth: '82%' }}>
              <div
                style={{
                  backgroundColor: msg.role === 'user' ? '#1677ff' : '#ffffff',
                  color: msg.role === 'user' ? '#ffffff' : '#0f172a',
                  padding: '12px 16px',
                  borderRadius: msg.role === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                  boxShadow: msg.role === 'user' ? '0 2px 8px rgba(22, 119, 255, 0.2)' : '0 2px 8px rgba(0,0,0,0.06)',
                  border: msg.role === 'user' ? 'none' : '1px solid #e2e8f0',
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg.content}

                {/* Render Suggested Action if available */}
                {msg.action && (
                  <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px dashed #cbd5e1' }}>
                    <Card
                      size="small"
                      style={{ backgroundColor: '#f8fafc', borderColor: '#93c5fd' }}
                      title={
                        <Space>
                          <ThunderboltOutlined style={{ color: '#1677ff' }} />
                          <span style={{ fontSize: 13, fontWeight: 600 }}>Thao tác nhanh đề xuất</span>
                        </Space>
                      }
                      extra={
                        <Button
                          type="primary"
                          size="small"
                          onClick={() => handleActionClick(msg.action!)}
                          style={{ fontSize: 12 }}
                        >
                          Đi đến thực hiện
                        </Button>
                      }
                    >
                      {msg.action.action_type === 'DRAFT_LEAVE' && (
                        <div>
                          <div>• Loại hành động: <b>Lập đơn nghỉ phép</b></div>
                          {msg.action.data?.session && <div>• Buổi nghỉ: <Tag color="blue">{msg.action.data.session}</Tag></div>}
                          {msg.action.data?.leave_date && <div>• Ngày nghỉ: {msg.action.data.leave_date}</div>}
                          {msg.action.data?.reason && <div>• Lý do: {msg.action.data.reason}</div>}
                        </div>
                      )}
                      {msg.action.action_type === 'DRAFT_FIX' && (
                        <div>
                          <div>• Loại hành động: <b>Giải trình bổ sung công</b></div>
                          {msg.action.data?.work_date && <div>• Ngày: {msg.action.data.work_date}</div>}
                          {msg.action.data?.event_type && <div>• Loại quẹt: <Tag color="orange">{msg.action.data.event_type}</Tag></div>}
                          {msg.action.data?.reason && <div>• Lý do: {msg.action.data.reason}</div>}
                        </div>
                      )}
                      {msg.action.action_type === 'SHOW_DATA' && (
                        <div>
                          <div>• Dữ liệu hệ thống đã đồng bộ chuẩn thời gian thực.</div>
                        </div>
                      )}
                    </Card>
                  </div>
                )}
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: '#94a3b8',
                  marginTop: 4,
                  textAlign: msg.role === 'user' ? 'right' : 'left',
                }}
              >
                {msg.timestamp}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                backgroundColor: '#f0f5ff',
                color: '#1677ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <RobotOutlined />
            </div>
            <div
              style={{
                backgroundColor: '#ffffff',
                padding: '10px 16px',
                borderRadius: '4px 16px 16px 16px',
                border: '1px solid #e2e8f0',
              }}
            >
              <Spin size="small" /> <span style={{ marginLeft: 8, fontSize: 13, color: '#64748b' }}>Đang suy nghĩ...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Prompts */}
      <div style={{ marginTop: 12, marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {quickPrompts.map((p, idx) => (
          <Button
            key={idx}
            size="small"
            style={{ borderRadius: 12, fontSize: 12, backgroundColor: '#f1f5f9', border: 'none' }}
            onClick={() => handleSendMessage(p)}
          >
            {p}
          </Button>
        ))}
      </div>

      {/* Input row */}
      <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
        <Input.TextArea
          rows={2}
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          placeholder="Nhập câu hỏi hoặc yêu cầu (ví dụ: 'Tôi còn bao nhiêu ngày phép?')..."
          style={{ resize: 'none', borderRadius: 8 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          style={{ height: 'auto', borderRadius: 8, padding: '0 20px' }}
          onClick={() => handleSendMessage()}
          loading={loading}
        >
          Gửi
        </Button>
      </div>
    </Modal>
  );
};
