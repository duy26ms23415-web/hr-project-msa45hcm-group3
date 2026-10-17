/** Pure UI decisions; server authorization and draft ownership remain authoritative. */
import type { AISuggestion } from '../types/ai';
import type { ReportKind } from '../types/reports';

export function actorChanged(previous?: number, current?: number): boolean {
  return previous !== current;
}

export function readableISODate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() + 1 === month && parsed.getUTCDate() === day
    ? `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}` : value;
}
/** Validate the prefilled period before submitting a report outside chat. */
export function reportPeriodValid(kind: ReportKind, start: string, end: string): boolean {
  const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && readableISODate(value) !== value;
  if (!validDate(start) || !validDate(end) || start > end || start.slice(0, 4) !== end.slice(0, 4)) return false;
  if (kind === 'MY_PAYSLIP' || kind === 'PAYROLL_SUMMARY') {
    const lastDay = new Date(Date.UTC(Number(start.slice(0, 4)), Number(start.slice(5, 7)), 0)).getUTCDate();
    return start.endsWith('-01') && start.slice(0, 7) === end.slice(0, 7)
      && Number(end.slice(-2)) === lastDay;
  }
  return true;
}

export function chatFailureState(status?: number, code?: string) {
  return {
    clearDraft: status === 404 && code === 'AI_DRAFT_NOT_FOUND'
      || status === 409 && code === 'AI_DRAFT_NOT_COLLECTING'
      || status === 410 && code === 'AI_DRAFT_EXPIRED',
    restartRequired: status === 409 && code === 'AI_DRAFT_REVISION_CONFLICT',
    // /ai/chat can persist a draft or report before an HTTP response reaches
    // the browser. Missing responses and 5xx never authorize replaying this POST.
    retryable: status === 429,
    uncertainOutcome: status === undefined || status >= 500,
  };
}

export function acceptsServerSuggestions(value: unknown): value is AISuggestion[] {
  return Array.isArray(value) && value.every((item) => item && typeof item.suggestion_id === 'string'
    && typeof item.prompt === 'string' && typeof item.catalog_version === 'string');
}

/** A conflicting revision must be explicitly discarded or resynced before a new send. */
export function canSubmitChat(restartRequired: boolean): boolean {
  return !restartRequired;
}


/** Idempotency token, not authentication; supported on insecure localhost too. */
export function newChatRequestKey(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** User-facing text for a failed chat request (server message wins when present). */
export function chatErrorMessage(status: number | undefined, code: string | undefined, serverMessage?: unknown): string {
  const failure = chatFailureState(status, code);
  if (failure.restartRequired) return 'Bản nháp đã được cập nhật ở lượt khác. Hãy chọn “Bắt đầu yêu cầu mới” bên dưới. Bản nháp trên máy chủ không bị xóa.';
  if (failure.uncertainOutcome) return 'Chưa nhận được xác nhận từ máy chủ. Yêu cầu có thể đã tạo bản nháp hoặc báo cáo. Hãy kiểm tra các bản nháp hoặc báo cáo hiện có trước khi gửi yêu cầu mới để tránh tạo trùng.';
  if (typeof serverMessage === 'string' && serverMessage) return serverMessage;
  if (status === 422) return 'Thông tin chưa hợp lệ. Vui lòng kiểm tra các trường được yêu cầu.';
  if (status === 403 || code === 'AI_DRAFT_NOT_FOUND') return 'Bạn không có quyền thực hiện yêu cầu này hoặc truy cập dữ liệu được yêu cầu. Vui lòng chọn chức năng trong phạm vi quyền của bạn.';
  if (status === 410 && code === 'AI_DRAFT_EXPIRED') return 'Bản nháp đã hết hạn. Vui lòng bắt đầu lại từ một gợi ý có sẵn.';
  if (status === 409) return 'Bản nháp đã thay đổi hoặc kết thúc. Vui lòng bắt đầu lại từ một gợi ý có sẵn.';
  if (status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.';
  if (status === 429) return 'Bạn đã gửi quá nhiều yêu cầu. Vui lòng đợi một phút rồi thử lại.';
  if (code === 'REPORT_UNAVAILABLE') return 'Kỳ lương chưa được phát hành hoặc báo cáo không còn khả dụng.';
  if (code === 'REPORT_TOO_LARGE') return 'Báo cáo vượt giới hạn 10.000 dòng. Vui lòng thu hẹp kỳ hoặc phòng ban.';
  return 'Không thể kết nối hệ thống HR. Vui lòng kiểm tra kết nối và thử lại.';
}

export type DraftKind = 'LEAVE' | 'FIX' | 'REPORT';
const DRAFT_STEPS: Record<DraftKind, { title: string; fields: string[] }> = {
  LEAVE: { title: 'Đơn nghỉ phép', fields: ['leave_date', 'session', 'leave_type_id', 'reason'] },
  FIX: { title: 'Giải trình chấm công', fields: ['work_date', 'event_type', 'requested_time', 'reason'] },
  REPORT: { title: 'Báo cáo', fields: ['kind', 'start_date', 'end_date', 'scope'] },
};
const FIELD_LABELS: Record<string, string> = {
  leave_date: 'Ngày nghỉ', session: 'Buổi nghỉ', leave_type_id: 'Loại nghỉ', reason: 'Lý do',
  work_date: 'Ngày công', event_type: 'Lượt công', requested_time: 'Giờ đề nghị',
  kind: 'Loại báo cáo', start_date: 'Kỳ báo cáo', end_date: 'Ngày kết thúc', scope: 'Phạm vi',
};

/** Which draft is being collected; "reason" alone keeps the previous kind. */
export function draftKind(missingFields: string[], previous: DraftKind | null): DraftKind | null {
  if (!missingFields.length) return null;
  const match = (Object.keys(DRAFT_STEPS) as DraftKind[]).filter((kind) =>
    missingFields.every((field) => DRAFT_STEPS[kind].fields.includes(field)));
  if (previous && match.includes(previous)) return previous;
  return match.length === 1 ? match[0] : previous;
}

/** Progress of a multi-turn draft, so follow-up questions read as one action. */
export function draftProgress(kind: DraftKind | null, missingFields: string[]) {
  if (!kind || !missingFields.length) return null;
  const { title, fields } = DRAFT_STEPS[kind];
  const field = missingFields[0];
  return { title, step: Math.min(fields.length - missingFields.length + 1, fields.length), total: fields.length,
    field, fieldLabel: FIELD_LABELS[field] ?? field };
}

export interface QuickReply { label: string; text: string; inputs?: Partial<Record<string, string | number>> }

/** One-click answers for the field the draft is asking for. Server options come first. */
export function draftQuickReplies(field: string | undefined, options: { field: string; value: string | number; label: string }[]): QuickReply[] {
  if (!field) return [];
  const server = options.filter((option) => option.field === field)
    .map((option) => ({ label: option.label, text: option.label, inputs: { [field]: option.value } }));
  if (server.length) return server;
  switch (field) {
    case 'start_date': return ['Tháng này', 'Tháng trước'].map((label) => ({ label, text: label }));
    case 'session': return [['MORNING', 'Buổi sáng'], ['AFTERNOON', 'Buổi chiều'], ['FULL_DAY', 'Cả ngày']]
      .map(([value, label]) => ({ label, text: label, inputs: { session: value } }));
    case 'leave_type_id': return ['Phép năm', 'Nghỉ ốm', 'Nghỉ không lương'].map((label) => ({ label, text: label }));
    case 'event_type': return [['CHECK_IN', 'Check-in'], ['CHECK_OUT', 'Check-out']]
      .map(([value, label]) => ({ label, text: label.toLowerCase(), inputs: { event_type: value } }));
    // Leave is usually planned ahead; attendance fixes are about days already worked.
    case 'leave_date': return ['Hôm nay', 'Ngày mai', 'Ngày kia'].map((label) => ({ label, text: label }));
    case 'work_date': return ['Hôm nay', 'Hôm qua'].map((label) => ({ label, text: label }));
    default: return [];
  }
}

export type ReplySpan = { text: string; bold: boolean };
export type ReplyBlock =
  | { type: 'paragraph'; spans: ReplySpan[] }
  | { type: 'list'; ordered: boolean; items: ReplySpan[][] };

/** `**bold**` runs; unmatched markers stay literal. */
function replySpans(line: string): ReplySpan[] {
  const spans: ReplySpan[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let last = 0;
  for (const match of line.matchAll(pattern)) {
    if (match.index > last) spans.push({ text: line.slice(last, match.index), bold: false });
    spans.push({ text: match[1], bold: true });
    last = match.index + match[0].length;
  }
  if (last < line.length) spans.push({ text: line.slice(last), bold: false });
  return spans;
}

/**
 * Minimal Markdown subset for assistant replies (bold, bullet and numbered lists).
 * Returns plain data rendered as React text nodes, so reply text is never parsed as HTML.
 */
export function replyBlocks(content: string): ReplyBlock[] {
  const blocks: ReplyBlock[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: 'paragraph', spans: replySpans(paragraph.join('\n')) });
    paragraph = [];
  };
  for (const raw of content.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = bullet ? null : /^\s*\d{1,2}[.)]\s+(.*)$/.exec(line);
    const item = bullet ?? numbered;
    if (item) {
      flush();
      const ordered = !!numbered;
      const previous = blocks[blocks.length - 1];
      if (previous?.type === 'list' && previous.ordered === ordered) previous.items.push(replySpans(item[1]));
      else blocks.push({ type: 'list', ordered, items: [replySpans(item[1])] });
    } else if (!line.trim()) flush();
    else paragraph.push(/^#{1,4}\s+/.test(line) ? `**${line.replace(/^#{1,4}\s+/, '')}**` : line);
  }
  flush();
  return blocks;
}

/** Follow new messages only when the reader is already at (or near) the bottom. */
export function nearBottom(scrollTop: number, clientHeight: number, scrollHeight: number, threshold = 80): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold;
}

/** Plain text for the clipboard: Markdown markers removed, list items kept on their own lines. */
export function replyPlainText(content: string): string {
  return replyBlocks(content).map((block) => block.type === 'paragraph'
    ? block.spans.map((span) => span.text).join('')
    : block.items.map((item, index) => `${block.ordered ? `${index + 1}.` : '-'} ${item.map((span) => span.text).join('')}`).join('\n'))
    .join('\n\n');
}
