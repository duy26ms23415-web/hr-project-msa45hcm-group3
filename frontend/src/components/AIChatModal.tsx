import React, { useState, useRef, useEffect } from 'react';
import { Alert, Modal, Input, Button, Dropdown, Card, Spin, Space, Typography, DatePicker, Select, Tooltip, message } from 'antd';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import { SendOutlined, RobotOutlined, UserOutlined, ThunderboltOutlined, PlusOutlined, FormOutlined, CloseOutlined, CopyOutlined, CheckOutlined } from '@ant-design/icons';
import api from '../api/client';
import dayjs from 'dayjs';
import type { ReportDefinition, ReportInputs, ReportRunCreateResponse, ReportScope } from '../types/reports';
import { acceptsServerSuggestions, actorChanged, canSubmitChat, chatErrorMessage, chatFailureState, draftKind, draftProgress, draftQuickReplies, nearBottom, newChatRequestKey, readableISODate, replyBlocks, replyPlainText, reportPeriodValid } from '../api/aiChatState';
import type { DraftKind, ReplySpan } from '../api/aiChatState';
import { ChatReportPreview } from './ChatReportPreview';
import { Link, useNavigate } from 'react-router-dom';
import type { AIChatAction, AIChatResponse, AISource, AIExternalSource, AISuggestion, AIInputOption, AIDraftInputs, AIChatRequest, AIPolicyWarning, AIReportAnalysis } from '../types/ai';
import { useAuth } from '../context/AuthContext';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: AIChatAction;
  timestamp: string;
  sources?: AISource[];
  externalSources?: AIExternalSource[];
  searchSuggestionsHtml?: string | null;
  clarificationOptions?: string[];
  policyWarnings?: AIPolicyWarning[];
  isError?: boolean;
}

const Spans: React.FC<{ spans: ReplySpan[] }> = ({ spans }) => <>
  {spans.map((span, index) => span.bold ? <strong key={index}>{span.text}</strong> : <React.Fragment key={index}>{span.text}</React.Fragment>)}
</>;

/** Assistant text with bold and lists; content is rendered as text nodes only. */
const ReplyContent: React.FC<{ content: string }> = ({ content }) => <>
  {replyBlocks(content).map((block, index) => block.type === 'paragraph'
    ? <div key={index} style={{ marginTop: index ? 8 : 0 }}><Spans spans={block.spans} /></div>
    : React.createElement(block.ordered ? 'ol' : 'ul', { key: index, style: { margin: index ? '6px 0 0' : 0, paddingLeft: 20 } },
      block.items.map((item, itemIndex) => <li key={itemIndex} style={{ whiteSpace: 'pre-wrap' }}><Spans spans={item} /></li>)))}
</>;

const suggestionLabel = (prompt: string) => prompt
  .replace(/\s*\(tham kh\u1ea3o m\u1ee5c\s+[^)]*\)\s*$/i, '')
  .trim();

const reportLabels: Record<ReportInputs['kind'], string> = {
  ATTENDANCE: 'Chấm công', LEAVE: 'Nghỉ phép', ATTENDANCE_FIX: 'Giải trình công',
  APPROVAL_QUEUE: 'Đơn chờ duyệt', HEADCOUNT: 'Nhân sự hiện tại',
  MY_PAYSLIP: 'Phiếu lương cá nhân', PAYROLL_SUMMARY: 'Tổng hợp lương',
};
const scopeLabels: Record<ReportScope, string> = {
  SELF: 'Bản thân', DIRECT_REPORTS: 'Nhân viên trực tiếp', COMPANY: 'Toàn công ty',
};

const sourceGroupKey = (source: AISource) => `${source.document_id}-${source.version_id ?? 'current'}`;
const clockTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const WELCOME = 'Xin chào! Tôi là Trợ lý AI Nhân sự. Hỏi tôi về quy định, số dư phép, chấm công, hoặc nhờ soạn đơn nghỉ phép, giải trình và báo cáo.';

interface AIChatModalProps {
  open: boolean;
  onClose: () => void;
}

export const AIChatModal: React.FC<AIChatModalProps> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const actorId = user?.user_account_id;
  // The welcome screen is rendered when the list is empty (first open, reset, account switch).
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentDraftKind, setCurrentDraftKind] = useState<DraftKind | null>(null);
  const nextIdRef = useRef(0);
  const inputRef = useRef<TextAreaRef>(null);
  const newId = () => `m${++nextIdRef.current}`;
  const [previewRunId, setPreviewRunId] = useState<string | null>(null);
  const [previewAnalysis, setPreviewAnalysis] = useState<AIReportAnalysis | null>(null);
  // One message typed while a reply is pending is sent right after it, not dropped.
  const [queuedText, setQueuedText] = useState<string | null>(null);
  const [editingRunId, setEditingRunId] = useState<string | null>(null);
  const [lastReportRunId, setLastReportRunId] = useState<string | null>(null);
  const [reportSetup, setReportSetup] = useState<ReportInputs | null>(null);
  const [reportAllowedScopes, setReportAllowedScopes] = useState<ReportScope[]>([]);
  const [reportSetupLoading, setReportSetupLoading] = useState(false);
  const [reportSaving, setReportSaving] = useState(false);
  const [reportUncertain, setReportUncertain] = useState(false);
  const [inputVal, setInputVal] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [draftRestartRequired, setDraftRestartRequired] = useState(false);
  const [activeDraftRevision, setActiveDraftRevision] = useState<number | null>(null);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [inputOptions, setInputOptions] = useState<AIInputOption[]>([]);
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState(false);
  const [suggestionsRetry, setSuggestionsRetry] = useState(0);
  const [retryMessage, setRetryMessage] = useState<{ text: string; startNew: boolean; suggestionId?: string; inputs?: AIDraftInputs } | null>(null);
  const [reference, setReference] = useState<{ title: string; content: string; source_url?: string | null } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // False while the user has scrolled up to read; new replies then do not yank the view.
  const followRef = useRef(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  // Display names for the leave draft card; the action itself only carries leave_type_id.
  const [leaveTypeNames, setLeaveTypeNames] = useState<Record<number, string> | null>(null);
  const leaveTypesRequestedRef = useRef(false);
  const actorIdRef = useRef(actorId);
  const uncertainRequestRef = useRef<{ fingerprint: string; key: string } | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  };

  useEffect(() => {
    if (!open || !followRef.current) return;
    const timer = setTimeout(scrollToBottom, 150);
    return () => clearTimeout(timer);
  }, [open, messages, loading]);

  // Keep the keyboard in the conversation after every reply (opening is handled by afterOpenChange).
  useEffect(() => {
    if (open && !loading) inputRef.current?.focus();
  }, [open, loading]);

  const hasLeaveDraftCard = messages.some((item) => item.action?.action_type === 'DRAFT_LEAVE');
  useEffect(() => {
    if (!hasLeaveDraftCard || leaveTypesRequestedRef.current) return;
    leaveTypesRequestedRef.current = true;
    api.get<{ leave_type_id: number; leave_name: string }[]>('/leaves/types').then((res) => {
      setLeaveTypeNames(Object.fromEntries(res.data.map((type) => [type.leave_type_id, type.leave_name])));
    }).catch(() => { leaveTypesRequestedRef.current = false; });
  }, [hasLeaveDraftCard]);

  useEffect(() => {
    if (actorChanged(actorIdRef.current, actorId)) {
      actorIdRef.current = actorId;
      setMessages([]);
      setActiveDraftId(null);
      setActiveDraftRevision(null);
      setCurrentDraftKind(null);
      setDraftRestartRequired(false);
      setMissingFields([]);
      setInputOptions([]);
      setLastReportRunId(null);
      setReportSetup(null);
      setReportAllowedScopes([]);
      setReportUncertain(false);
      setEditingRunId(null);
      setPreviewRunId(null);
      setRetryMessage(null);
      uncertainRequestRef.current = null;
    }
  }, [actorId]);

  useEffect(() => {
    if (!open || actorId == null) return;
    let cancelled = false;
    setSuggestions([]);
    setSuggestionsError(false);
    setSuggestionsLoading(true);
    api.get<AISuggestion[]>('/ai/suggestions').then((res) => {
      if (!cancelled && acceptsServerSuggestions(res.data)) setSuggestions(res.data);
      else if (!cancelled) setSuggestionsError(true);
    }).catch(() => {
      if (!cancelled) setSuggestionsError(true);
    }).finally(() => {
      if (!cancelled) setSuggestionsLoading(false);
    });
    return () => { cancelled = true; };
  }, [open, actorId, suggestionsRetry]);

  const handleSendMessage = async (textToSend?: string, startNew = false, suggestionId?: string, inputs?: AIDraftInputs) => {
    const text = textToSend || inputVal.trim();
    if (text && loading && !textToSend && canSubmitChat(draftRestartRequired)) {
      setQueuedText(text); setInputVal('');
      return;
    }
    if (!text || loading || !canSubmitChat(draftRestartRequired)) return;
    setRetryMessage(null);

    const userMsg: ChatMessage = {
      id: newId(),
      role: 'user',
      content: suggestionId ? suggestionLabel(text) : text,
      timestamp: clockTime(),
    };

    setMessages((prev) => [...prev.map((item) => ({ ...item, action: undefined })), userMsg]);
    setInputVal('');
    followRef.current = true;
    setLoading(true);
    const requestActorId = actorId;
    // An uncertain previous outcome must reuse the same operation identity.
    // This is NOT a bearer credential; authorization remains server-side.
    const fingerprint = JSON.stringify({
      actorId, text, startNew, suggestionId, inputs,
      draft: startNew ? null : activeDraftId,
      revision: startNew ? null : activeDraftRevision,
    });
    const requestKey = uncertainRequestRef.current?.fingerprint === fingerprint
      ? uncertainRequestRef.current.key
      : newChatRequestKey();
    uncertainRequestRef.current = { fingerprint, key: requestKey };

    try {
      const history = messages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const request: AIChatRequest = {
        message: text,
        request_key: requestKey,
        ...((editingRunId || lastReportRunId && /báo cáo (này|vừa)|bao cao (nay|vua)|this report/i.test(text)) && !startNew && !activeDraftId
          ? { report_run_id: editingRunId || lastReportRunId! } : {}),
        conversation_history: history,
        ...(suggestionId ? { suggestion_id: suggestionId } : {}),
        ...(inputs && activeDraftId && !startNew ? { inputs } : {}),
        ...(activeDraftId && !startNew ? { draft_id: activeDraftId, ...(activeDraftRevision ? { draft_revision: activeDraftRevision } : {}) } : {}),
      };
      const res = await api.post<AIChatResponse>('/ai/chat', request);
      if (actorIdRef.current !== requestActorId) return;
      uncertainRequestRef.current = null;
      if (res.data.action?.action_type === 'OPEN_REPORT' && res.data.action.data.run_id) {
        const runId = res.data.action.data.run_id;
        const analyzed = res.data.message_code === 'REPORT_ANALYZED';
        setLastReportRunId(runId);
        setPreviewAnalysis(analyzed ? res.data.report_analysis ?? null : null);
        setPreviewRunId(runId);
        // Stay in edit mode on the revised run so the next change applies to it too.
        setEditingRunId(editingRunId && request.report_run_id && !analyzed ? runId : analyzed ? editingRunId : null);
      } else if (res.data.draft_id || startNew) setEditingRunId(null);
      setDraftRestartRequired(false);
      setActiveDraftId(res.data.draft_id || null);
      setActiveDraftRevision(res.data.draft_revision || null);
      const missing = res.data.missing_fields || [];
      setMissingFields(missing);
      setCurrentDraftKind((previous) => res.data.draft_id ? draftKind(missing, startNew ? null : previous) : null);
      setInputOptions(res.data.input_options || []);
      // Do not replay a mutating chat POST without server-side idempotency.
      // Even a fallback response is not a general retry guarantee.

      const aiMsg: ChatMessage = {
        id: newId(),
        role: 'assistant',
        content: res.data.reply,
        action: res.data.action || undefined,
        sources: res.data.sources,
        externalSources: res.data.external_sources || [],
        searchSuggestionsHtml: res.data.search_suggestions_html ?? null,
        clarificationOptions: res.data.clarification_options || [],
        policyWarnings: res.data.policy_warnings || [],
        timestamp: clockTime(),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      if (actorIdRef.current !== requestActorId) return;
      const status = err?.response?.status;
      // Stable envelope `{code, message}` on /ai; plain `detail` elsewhere.
      const code = err?.response?.data?.code ?? err?.response?.data?.detail;
      const failure = chatFailureState(status, code);
      if (!failure.uncertainOutcome && !failure.retryable) uncertainRequestRef.current = null;
      if (failure.clearDraft) {
        setActiveDraftId(null); setActiveDraftRevision(null); setMissingFields([]);
        setInputOptions([]); setDraftRestartRequired(false); setCurrentDraftKind(null);
      }
      // A stale revision is recoverable only with fresh server state or an explicit restart.
      // There is no read-draft endpoint, so block stale requests until the user restarts.
      if (failure.restartRequired) { setDraftRestartRequired(true); setRetryMessage(null); }
      if (failure.retryable) setRetryMessage({ text, startNew, suggestionId, inputs });
      setMessages((prev) => [...prev, {
        id: newId(), role: 'assistant', timestamp: clockTime(), isError: true,
        content: chatErrorMessage(status, code, err?.response?.data?.message),
      }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (loading || !queuedText) return;
    const text = queuedText;
    setQueuedText(null);
    void handleSendMessage(text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, queuedText]);

  const startFreshConversation = () => {
    if (loading) return;
    setQueuedText(null);
    // Explicit local reset; do not mutate or cancel the newer server-side draft.
    setActiveDraftId(null);
    setActiveDraftRevision(null);
    setCurrentDraftKind(null);
    setMissingFields([]);
    setInputOptions([]);
    setDraftRestartRequired(false);
    setRetryMessage(null);
    uncertainRequestRef.current = null;
    setMessages([]);
    setInputVal('');
    setPreviewRunId(null);
    setEditingRunId(null);
    setLastReportRunId(null);
    setReportSetup(null);
    setReportAllowedScopes([]);
    setReportUncertain(false);
  };

  const openReportSetup = async (data: ReportInputs) => {
    const { kind, start_date, end_date, scope, department_id, employee_id } = data;
    const requestActor = actorIdRef.current;
    setReportUncertain(false);
    setReportAllowedScopes([]);
    setReportSetup({ kind, start_date, end_date, scope, department_id, employee_id });
    setReportSetupLoading(true);
    try {
      // The catalog comes from the server; do not offer a scope inferred from UI role names.
      const response = await api.get<{ reports: ReportDefinition[] }>('/ai/report-catalog');
      if (actorIdRef.current !== requestActor) return;
      const definition = response.data.reports.find((item) => item.kind === kind);
      if (!definition || !definition.scopes.length) {
        setReportSetup(null);
        message.error('Loại báo cáo này không khả dụng trong phạm vi quyền của bạn.');
        return;
      }
      setReportAllowedScopes(definition.scopes);
      setReportSetup((current) => current && current.kind === kind ? {
        ...current,
        scope: scope && definition.scopes.includes(scope) ? scope : definition.default_scope,
      } : current);
    } catch {
      if (actorIdRef.current === requestActor) {
        setReportSetup(null);
        message.error('Chưa tải được danh mục báo cáo và quyền truy cập.');
      }
    } finally {
      if (actorIdRef.current === requestActor) setReportSetupLoading(false);
    }
  };

  const createConfiguredReport = async () => {
    if (!reportSetup || !reportSetup.scope || reportSaving || reportUncertain ||
        !reportPeriodValid(reportSetup.kind, reportSetup.start_date, reportSetup.end_date)) return;
    const requestActor = actorIdRef.current;
    setReportSaving(true);
    try {
      const response = await api.post<ReportRunCreateResponse>('/ai/report-runs', reportSetup);
      if (actorIdRef.current !== requestActor) return;
      setReportSetup(null);
      setLastReportRunId(response.data.run.run_id);
      setPreviewRunId(response.data.run.run_id);
      setEditingRunId(null);
      message.success('Đã tạo báo cáo. Bạn có thể xem trước và tải Excel.');
    } catch (err: any) {
      if (actorIdRef.current !== requestActor) return;
      const status = err?.response?.status;
      if (status === undefined || status >= 500) {
        setReportUncertain(true);
        message.error('Chưa xác nhận được kết quả tạo báo cáo. Hãy kiểm tra danh sách báo cáo trước khi tạo lại để tránh trùng.');
      } else {
        message.error(status === 403 ? 'Bạn không có quyền tạo báo cáo với phạm vi đã chọn.'
          : status === 404 ? 'Dữ liệu báo cáo hoặc kỳ lương chưa khả dụng.'
          : 'Không thể tạo báo cáo. Vui lòng kiểm tra kỳ và phạm vi đã chọn.');
      }
    } finally {
      if (actorIdRef.current === requestActor) setReportSaving(false);
    }
  };

  const handleActionClick = (action: AIChatAction) => {
    if (action.action_type === 'OPEN_REPORT') {
      if (action.data.run_id) { setPreviewAnalysis(null); setPreviewRunId(action.data.run_id); }
      else void openReportSetup(action.data);
      return;
    }
    onClose();
    if (action.action_type === 'DRAFT_LEAVE' || action.action_type === 'NAVIGATE') {
      const path = action.action_type === 'NAVIGATE' && ['/leaves', '/attendance', '/reports', '/knowledge'].includes(action.data?.path) ? action.data.path : '/leaves';
      navigate(path, { state: action.action_type === 'DRAFT_LEAVE' ? { aiDraft: action.data } : undefined });
    } else if (action.action_type === 'DRAFT_FIX') {
      navigate('/attendance', { state: { aiDraft: action.data } });
    } else if (action.action_type === 'SHOW_DATA') {
      navigate(action.data?.type === 'LEAVE_BALANCE' ? '/leaves' : '/attendance');
    } else if (action.action_type === 'OPEN_APPROVALS') {
      navigate(action.data?.target === 'attendance' ? '/attendance' : '/leaves', { state: { aiTab: 'approvals' } });

    } else if (action.action_type === 'OPEN_KNOWLEDGE') {
      navigate('/knowledge');
    } else if (action.action_type === 'OPEN_SOURCE') {
      navigate(`/knowledge/view/${action.data.document_id}?version=${action.data.version_id}&section=${action.data.section_id}`);
    }
  };

  const copyReply = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(replyPlainText(msg.content));
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId((current) => current === msg.id ? null : current), 1500);
    } catch { message.error('Trình duyệt không cho phép sao chép.'); }
  };

  const readReference = async (documentId: number) => {
    try {
      const response = await api.get(`/ai/knowledge/${documentId}`);
      setReference(response.data);
    } catch { message.error('Tài liệu không còn khả dụng hoặc bạn không có quyền truy cập.'); }
  };

  const progress = activeDraftId && !draftRestartRequired ? draftProgress(currentDraftKind, missingFields) : null;
  const quickReplies = progress ? draftQuickReplies(progress.field, inputOptions) : [];
  const lastAssistantId = [...messages].reverse().find((item) => item.role === 'assistant')?.id;
  const sendSuggestion = (suggestion: AISuggestion) =>
    void handleSendMessage(suggestion.prompt, true, suggestion.catalog_version ? suggestion.suggestion_id : undefined);

  return (
    <Modal
      open={open}
      centered
      onCancel={onClose}
      // The dialog moves focus to its close button once the open animation ends; hand it back to the input.
      afterOpenChange={(visible) => { if (visible) inputRef.current?.focus(); }}
      footer={null}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingRight: 28 }}>
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
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 16 }}>HR AI Assistant</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Tra cứu có nguồn & hỗ trợ soạn đơn</div>
          </div>
          {messages.length > 0 && <Tooltip title="Bắt đầu cuộc trò chuyện mới (bản nháp trên máy chủ không bị xóa)">
            <Button size="small" type="text" icon={<PlusOutlined />} disabled={loading} onClick={startFreshConversation}>Mới</Button>
          </Tooltip>}
        </div>
      }
      width={680}
      styles={{
        body: { padding: '16px 20px', display: 'flex', flexDirection: 'column', height: 'min(620px, calc(100dvh - 160px))', minHeight: 0 },
      }}
    >
      {/* Messages list */}
      <div
        onScroll={(e) => { const el = e.currentTarget; followRef.current = nearBottom(el.scrollTop, el.clientHeight, el.scrollHeight); }}
        aria-live="polite"
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          paddingRight: 8,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {messages.length === 0 && <div style={{ margin: 'auto 0', textAlign: 'center', padding: '8px 4px' }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: '#e6f4ff', color: '#1677ff', fontSize: 24,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><RobotOutlined /></div>
          <Typography.Paragraph style={{ margin: '12px auto 16px', maxWidth: 460, color: '#334155' }}>{WELCOME}</Typography.Paragraph>
          {suggestionsLoading && <Spin size="small" />}
          {!suggestionsLoading && suggestions.length > 0 && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
            {suggestions.slice(0, 4).map((suggestion) => <Button key={suggestion.suggestion_id} disabled={loading}
              onClick={() => sendSuggestion(suggestion)}
              style={{ height: 'auto', minHeight: 32, whiteSpace: 'normal', textAlign: 'left', borderRadius: 16, maxWidth: '100%' }}>
              {suggestionLabel(suggestion.prompt)}
            </Button>)}
          </div>}
        </div>}
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

            <div style={{ maxWidth: '82%', minWidth: 0 }}>
              <div
                style={{
                  backgroundColor: msg.role === 'user' ? '#1677ff' : msg.isError ? '#fff7ed' : '#ffffff',
                  color: msg.role === 'user' ? '#ffffff' : '#0f172a',
                  padding: '12px 16px',
                  borderRadius: msg.role === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                  boxShadow: msg.role === 'user' ? '0 2px 8px rgba(22, 119, 255, 0.2)' : '0 2px 8px rgba(0,0,0,0.06)',
                  border: msg.role === 'user' ? 'none' : msg.isError ? '1px solid #fed7aa' : '1px solid #e2e8f0',
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal',
                  overflowWrap: 'anywhere',
                }}
              >
                {msg.role === 'user' || msg.isError ? <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div> : <ReplyContent content={msg.content} />}
                {/* Only the latest question is answerable; older choices would start a stale flow. */}
                {!!msg.clarificationOptions?.length && msg.id === lastAssistantId && <Space wrap size={6} style={{ marginTop: 10, display: 'flex' }}>
                  {msg.clarificationOptions.map((option) => <Button key={option} size="small" disabled={loading}
                    onClick={() => handleSendMessage(option)}>{option}</Button>)}
                </Space>}
                {!!msg.sources?.length && <div style={{ marginTop: 12, maxWidth: '100%', minWidth: 0 }}>
                  <Typography.Text strong>Tài liệu tham khảo</Typography.Text>
                  {Array.from(new Map(msg.sources.map((source) => [sourceGroupKey(source), source])).entries()).map(([groupKey, firstSource]) => {
                    const groupSources = msg.sources!.map((source, index) => ({ source, index })).filter(({ source }) => sourceGroupKey(source) === groupKey);
                    return <details key={groupKey} className="ai-chat-source-group" data-source-group={groupKey} style={{ marginTop: 4, minWidth: 0 }}>
                      <summary style={{ cursor: 'pointer', color: '#1677ff', overflowWrap: 'anywhere' }}>{firstSource.title} <span style={{ color: '#64748b', fontSize: 12 }}>({groupSources.length} trích dẫn)</span></summary>
                      <div style={{ paddingLeft: 8, minWidth: 0 }}>
                        {groupSources.map(({ source, index }) => {
                          const page = source.page_start == null ? null : source.page_end != null && source.page_end !== source.page_start
                            ? `${source.page_start}–${source.page_end}` : String(source.page_start);
                          const citation = <>
                            <span style={{ flexShrink: 0 }}>[{index + 1}]</span>
                            {page != null && <span style={{ flexShrink: 0, borderRadius: 10, padding: '1px 7px', background: '#f1f5f9', color: '#475569', fontSize: 11 }}>Trang {page}</span>}
                            <span title={source.heading || undefined} style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflowWrap: 'anywhere' }}>{source.heading || (source.section_code?.startsWith('PAGE_') ? 'Nội dung tài liệu' : source.section_code) || 'Nội dung tài liệu'}</span>
                          </>;
                          const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 5, padding: '5px 0', minWidth: 0, maxWidth: '100%', color: '#1677ff', fontSize: 12 };
                          return source.viewer_path
                            ? <Link key={`${sourceGroupKey(source)}-${source.section_id ?? index}-${index}`} to={source.viewer_path} onClick={onClose} style={rowStyle}>{citation}</Link>
                            : <Button key={`${sourceGroupKey(source)}-${source.section_id ?? index}-${index}`} type="link" onClick={() => void readReference(source.document_id)} style={{ ...rowStyle, height: 'auto', padding: '5px 0', textAlign: 'left' }}>{citation}</Button>;
                        })}
                      </div>
                    </details>;
                  })}
                </div>}
                {!!msg.externalSources?.length && <div style={{ marginTop: 10, maxWidth: '100%', minWidth: 0 }}>
                  <Typography.Text strong>Nguồn công khai</Typography.Text>
                  <div style={{ marginTop: 3 }}>
                    {msg.externalSources.map((source, index) => {
                      let url: URL;
                      try { url = new URL(source.url); } catch { return null; }
                      if (url.protocol !== 'https:') return null;
                      return <div key={`${index}-${source.url}`} style={{ fontSize: 12, lineHeight: 1.5, overflowWrap: 'anywhere' }}>
                        <span style={{ color: '#64748b', marginRight: 5 }}>[{index + 1}]</span>
                        <a href={url.href} target="_blank" rel="noopener noreferrer">{source.title}</a>
                      </div>;
                    })}
                  </div>
                  {msg.searchSuggestionsHtml && <iframe
                    title="Tìm kiếm Google cho câu trả lời từ nguồn công khai"
                    srcDoc={msg.searchSuggestionsHtml}
                    sandbox="allow-popups allow-popups-to-escape-sandbox"
                    referrerPolicy="no-referrer"
                    style={{ display: 'block', width: '100%', maxWidth: '100%', height: 'min(180px, 30vh)', border: 0, marginTop: 6 }}
                  />}
                </div>}
                {/* Render Suggested Action if available */}
                {msg.action && msg.action.action_type !== 'SHOW_DATA' && (
                  <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px dashed #cbd5e1' }}>
                    {(msg.action.action_type === 'DRAFT_LEAVE' || msg.action.action_type === 'DRAFT_FIX') ? <Card
                      size="small" style={{ backgroundColor: '#f8fafc', borderColor: '#dbeafe' }}
                      title={msg.action.action_type === 'DRAFT_LEAVE' ? 'Nháp đơn nghỉ phép' : 'Nháp giải trình công'}
                    >
                      {msg.action.action_type === 'DRAFT_LEAVE' && <>
                        {msg.action.data?.leave_date && <div>Ngày nghỉ: <b>{readableISODate(String(msg.action.data.leave_date))}</b></div>}
                        {msg.action.data?.leave_type_id != null && leaveTypeNames?.[Number(msg.action.data.leave_type_id)] &&
                          <div>Loại nghỉ: {leaveTypeNames[Number(msg.action.data.leave_type_id)]}</div>}
                        {msg.action.data?.session && <div>Buổi nghỉ: {({ MORNING: 'Buổi sáng', AFTERNOON: 'Buổi chiều', FULL_DAY: 'Cả ngày' } as Record<string, string>)[String(msg.action.data.session)]}</div>}
                      </>}
                      {msg.action.action_type === 'DRAFT_FIX' && <>
                        {msg.action.data?.work_date && <div>Ngày công: <b>{readableISODate(String(msg.action.data.work_date))}</b></div>}
                        {msg.action.data?.event_type && <div>Lượt công: {msg.action.data.event_type === 'CHECK_IN' ? 'Vào làm' : 'Ra về'}</div>}
                        {msg.action.data?.requested_time && <div>Giờ đề nghị: {msg.action.data.requested_time}</div>}
                      </>}
                      {msg.action.data?.reason && <div>Lý do: {msg.action.data.reason}</div>}
                      {/* Document rules are advisory: the user may still submit; the manager decides. */}
                      {msg.policyWarnings?.map((warning, index) => <Alert key={index} showIcon style={{ marginTop: 8 }}
                        type={warning.severity === 'CONFLICT' ? 'warning' : 'info'}
                        title={warning.severity === 'UNCHECKED' ? 'Chưa kiểm tra được quy định' : 'Có thể chưa phù hợp quy định'}
                        description={<>{warning.message}{warning.source?.viewer_path && <> · <Link to={warning.source.viewer_path} onClick={onClose}>
                          {warning.source.heading || warning.source.title}{warning.source.page_start ? `, trang ${warning.source.page_start}` : ''}</Link></>}</>} />)}
                      <Button type="primary" block onClick={() => handleActionClick(msg.action!)}
                        style={{ marginTop: 12, height: 'auto', minHeight: 32, whiteSpace: 'normal' }}>
                        Kiểm tra và hoàn thiện đơn
                      </Button>
                    </Card> : <Button
                      type="default" icon={<ThunderboltOutlined />} onClick={() => handleActionClick(msg.action!)}
                      style={{ borderColor: '#bfdbfe', color: '#1d4ed8', height: 'auto', minHeight: 36, whiteSpace: 'normal', textAlign: 'left', maxWidth: '100%' }}
                    >
                      {({ OPEN_KNOWLEDGE: 'Mở quản lý tài liệu', OPEN_SOURCE: 'Xem nguồn trích dẫn',
                        OPEN_REPORT: 'Xem báo cáo', OPEN_APPROVALS: 'Mở danh sách chờ duyệt',
                        NAVIGATE: 'Mở màn hình liên quan' } as Record<string, string>)[msg.action.action_type]}
                    </Button>}
                  </div>
                )}
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: '#94a3b8',
                  marginTop: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                {msg.timestamp}
                {msg.role === 'assistant' && !msg.isError && <Tooltip title={copiedId === msg.id ? 'Đã sao chép' : 'Sao chép câu trả lời'}>
                  <Button type="text" size="small" aria-label="Sao chép câu trả lời" onClick={() => void copyReply(msg)}
                    icon={copiedId === msg.id ? <CheckOutlined style={{ color: '#16a34a' }} /> : <CopyOutlined />}
                    style={{ color: '#94a3b8', width: 22, height: 22, minWidth: 22 }} />
                </Tooltip>}
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

      {draftRestartRequired && <Space wrap style={{ margin: '10px 0 8px', flexShrink: 0 }}>
        <Typography.Text type="warning">Nháp hiện tại đã thay đổi ở nơi khác. Không thể tiếp tục bằng revision cũ.</Typography.Text>
        <Button type="primary" size="small" disabled={loading} onClick={startFreshConversation}>Bắt đầu yêu cầu mới</Button>
      </Space>}
      {/* Suggestions stay collapsed so the conversation remains the focus. */}
      {!activeDraftId && suggestionsError && <Space style={{ margin: '10px 0 8px' }}>
        <Typography.Text type="secondary">Chưa tải được gợi ý.</Typography.Text>
        <Button size="small" onClick={() => setSuggestionsRetry((value) => value + 1)}>Thử lại</Button>
      </Space>}
      {!activeDraftId && !suggestionsError && suggestions.length > 0 && <div style={{ margin: '10px 0 8px', flexShrink: 0, position: 'relative' }}>
        {/* Rendered inside the modal so overflow shifting is bounded by the dialog, not the page. */}
        <Dropdown trigger={['click']} placement="topLeft" autoAdjustOverflow
          getPopupContainer={(trigger) => trigger.parentElement ?? document.body}
          align={{ overflow: { adjustX: true, adjustY: true, shiftX: true, shiftY: true } }}
          styles={{ root: { width: 'min(520px, calc(100vw - 80px))', maxWidth: 'calc(100vw - 80px)' } }}
          popupRender={(menu) => <div className="ai-chat-suggestion-popup" style={{ width: '100%', maxHeight: 'min(320px, calc(100dvh - 160px))', overflowY: 'auto', overflowX: 'hidden', boxSizing: 'border-box' }}>{menu}</div>}
          menu={{ items: suggestions.map((suggestion) => ({
            key: suggestion.suggestion_id, label: <span style={{ display: 'block', whiteSpace: 'normal', overflowWrap: 'anywhere', maxWidth: '100%', lineHeight: 1.4 }}>{suggestionLabel(suggestion.prompt)}</span>,
          })), onClick: ({ key }) => {
            const suggestion = suggestions.find((item) => item.suggestion_id === key);
            if (suggestion) sendSuggestion(suggestion);
          }, style: { width: '100%', maxWidth: '100%', boxSizing: 'border-box' } }}>
          <Button type="text" size="small" icon={<ThunderboltOutlined />} disabled={loading} style={{ color: '#64748b' }}>Gợi ý câu hỏi</Button>
        </Dropdown>
      </div>}
      {retryMessage && <Button size="small" style={{ alignSelf: 'flex-start', margin: '8px 0', flexShrink: 0 }} onClick={() => void handleSendMessage(retryMessage.text, retryMessage.startNew, retryMessage.suggestionId, retryMessage.inputs)}>Thử lại yêu cầu</Button>}

      {/* One multi-turn action: every answer below continues the same draft. */}
      {activeDraftId && !draftRestartRequired && <div className="ai-chat-draft-panel" style={{
        margin: '10px 0 8px', padding: '10px 12px', borderRadius: 10, flexShrink: 0,
        background: '#f8fbff', border: '1px solid #cfe3ff',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <FormOutlined style={{ color: '#1677ff' }} />
          <Typography.Text strong>Đang soạn: {progress?.title ?? 'bản nháp'}</Typography.Text>
          {progress && <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bước {progress.step}/{progress.total} · cần <b>{progress.fieldLabel}</b>
          </Typography.Text>}
          <Button size="small" type="text" icon={<CloseOutlined />} disabled={loading} style={{ marginLeft: 'auto' }}
            onClick={() => handleSendMessage('hủy bản nháp')}>Hủy</Button>
        </div>
        {progress && <div aria-hidden style={{ display: 'flex', gap: 4, marginTop: 8 }}>
          {Array.from({ length: progress.total }, (_, index) => <span key={index} style={{
            flex: 1, height: 4, borderRadius: 2, background: index < progress.step - 1 ? '#1677ff' : index === progress.step - 1 ? '#91caff' : '#e2e8f0',
          }} />)}
        </div>}
        {quickReplies.length > 0 && <Space wrap size={6} style={{ marginTop: 8 }}>
          {quickReplies.map((reply) => <Button key={reply.label} size="small" disabled={loading}
            onClick={() => handleSendMessage(reply.text, false, undefined, reply.inputs as AIDraftInputs | undefined)}>{reply.label}</Button>)}
        </Space>}
      </div>}

      {editingRunId && <Space style={{ marginBottom: 8 }}><Typography.Text type="secondary">Đang chỉnh báo cáo vừa xem</Typography.Text><Button size="small" type="text" onClick={() => setEditingRunId(null)}>Kết thúc</Button></Space>}
      {queuedText && <Space style={{ marginBottom: 6, flexShrink: 0 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>Sẽ gửi sau khi trợ lý trả lời: “{queuedText.length > 60 ? queuedText.slice(0, 60) + '…' : queuedText}”</Typography.Text>
        <Button size="small" type="text" onClick={() => { setInputVal(queuedText); setQueuedText(null); }}>Sửa</Button>
      </Space>}
      <ChatReportPreview key={(previewRunId || 'closed') + (previewAnalysis ? ':a' : '')} runId={previewRunId} initialAnalysis={previewAnalysis} onClose={() => setPreviewRunId(null)} onRevise={(id) => { setEditingRunId(id); setInputVal(''); }} />
      {/* Input row */}
      <div style={{ display: 'flex', gap: 8, marginTop: 'auto', flexShrink: 0 }}>
        <Input.TextArea
          ref={inputRef}
          autoSize={{ minRows: 2, maxRows: 5 }}
          maxLength={2000}
          value={inputVal}
          disabled={draftRestartRequired}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={(e) => {
            // Do not send while an IME (Vietnamese Telex/VNI) is still composing a character.
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              handleSendMessage();
            } else if (e.key === 'ArrowUp' && !inputVal && !e.nativeEvent.isComposing) {
              // Recall the last question for a quick edit, as in most chat apps.
              const last = [...messages].reverse().find((item) => item.role === 'user');
              if (last) { e.preventDefault(); setInputVal(last.content); }
            }
          }}
          placeholder={progress
            ? `Trả lời: ${progress.fieldLabel.toLowerCase()}… (hoặc chọn nhanh ở trên)`
            : "Nhập câu hỏi hoặc yêu cầu (ví dụ: 'Tôi còn bao nhiêu ngày phép?')..."}
          style={{ resize: 'none', borderRadius: 8 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          style={{ height: 'auto', borderRadius: 8, padding: '0 20px' }}
          onClick={() => handleSendMessage()}
          loading={loading}
          disabled={draftRestartRequired || !inputVal.trim()}
        >
          Gửi
        </Button>
      </div>
      <Typography.Text type="secondary" style={{ fontSize: 11, marginTop: 4, flexShrink: 0 }}>
        Enter để gửi · Shift+Enter xuống dòng · ↑ sửa câu vừa gửi · Trợ lý chỉ tra cứu và soạn nháp, không tự gửi đơn.
      </Typography.Text>
      <Modal
        open={!!reportSetup}
        title="Kiểm tra và tạo báo cáo"
        okText="Tạo báo cáo"
        cancelText="Đóng"
        onCancel={() => { if (!reportSaving) { setReportSetup(null); setReportUncertain(false); } }}
        onOk={() => void createConfiguredReport()}
        confirmLoading={reportSaving}
        okButtonProps={{ disabled: reportSetupLoading || reportUncertain || !reportSetup?.scope || !reportSetup ||
          !reportPeriodValid(reportSetup.kind, reportSetup.start_date, reportSetup.end_date) }}
      >
        {reportSetupLoading ? <Spin /> : reportSetup && <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div><Typography.Text strong>Loại báo cáo: </Typography.Text>{reportLabels[reportSetup.kind]}</div>
          <div>
            <Typography.Text strong>Từ ngày</Typography.Text>
            <DatePicker format="DD/MM/YYYY" value={reportSetup.start_date ? dayjs(reportSetup.start_date) : null}
              onChange={(value) => setReportSetup((current) => current && ({ ...current, start_date: value?.format('YYYY-MM-DD') || '' }))}
              style={{ display: 'block', maxWidth: 260, marginTop: 4 }} />
          </div>
          <div>
            <Typography.Text strong>Đến ngày</Typography.Text>
            <DatePicker format="DD/MM/YYYY" value={reportSetup.end_date ? dayjs(reportSetup.end_date) : null}
              onChange={(value) => setReportSetup((current) => current && ({ ...current, end_date: value?.format('YYYY-MM-DD') || '' }))}
              style={{ display: 'block', maxWidth: 260, marginTop: 4 }} />
          </div>
          <div>
            <Typography.Text strong>Phạm vi</Typography.Text>
            <Select<ReportScope> value={reportSetup.scope} style={{ display: 'block', maxWidth: 320, marginTop: 4 }}
              options={reportAllowedScopes.map((scope) => ({ value: scope, label: scopeLabels[scope] }))}
              onChange={(scope) => setReportSetup((current) => current && ({ ...current, scope }))} />
          </div>
          {reportSetup.employee_id != null && <Typography.Text type="secondary">Mã nhân viên: {reportSetup.employee_id}</Typography.Text>}
          {reportSetup.department_id != null && <Typography.Text type="secondary">Mã phòng ban: {reportSetup.department_id}</Typography.Text>}
          {!reportPeriodValid(reportSetup.kind, reportSetup.start_date, reportSetup.end_date) &&
            <Typography.Text type="danger">Kỳ không hợp lệ. Hãy chọn hai ngày trong cùng năm; báo cáo lương yêu cầu một tháng trọn vẹn.</Typography.Text>}
          {reportUncertain && <Typography.Text type="warning">Kết quả tạo báo cáo chưa rõ. Đã khóa gửi lại để tránh tạo trùng; hãy kiểm tra các báo cáo hiện có.</Typography.Text>}
        </Space>}
      </Modal>
      <Modal open={!!reference} onCancel={() => setReference(null)} footer={null} title={reference?.title} width={720}>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{reference?.content}</Typography.Paragraph>
        {reference?.source_url && /^https?:\/\//i.test(reference.source_url) && <a href={reference.source_url} target="_blank" rel="noopener noreferrer">Mở tài liệu gốc</a>}
      </Modal>
    </Modal>
  );
};
