import test from 'node:test';
import assert from 'node:assert/strict';
import { acceptsServerSuggestions, actorChanged, canSubmitChat, chatFailureState, newChatRequestKey, readableISODate, reportPeriodValid } from '../src/api/aiChatState.ts';
import * as aiState from '../src/api/aiChatState.ts';

test('server suggestions are accepted without local role filtering', () => {
  const response = [{ suggestion_id: 'knowledge_admin', prompt: 'Mở tài liệu', catalog_version: 'v1' }];
  assert.equal(acceptsServerSuggestions(response), true);
  assert.equal(acceptsServerSuggestions(undefined), false);
  assert.equal(acceptsServerSuggestions([{ suggestion_id: 'knowledge_admin' }]), false);
});

test('network timeouts and provider errors never offer a blind chat POST retry', () => {
  assert.deepEqual(chatFailureState(503, 'AI_UNAVAILABLE'),
    { clearDraft: false, restartRequired: false, retryable: false, uncertainOutcome: true });
  assert.deepEqual(chatFailureState(undefined),
    { clearDraft: false, restartRequired: false, retryable: false, uncertainOutcome: true });
  assert.deepEqual(chatFailureState(504, 'DATA_SERVICE_UNAVAILABLE'),
    { clearDraft: false, restartRequired: false, retryable: false, uncertainOutcome: true });
});

test('only a pre-execution rate limit can offer the same-request retry', () => {
  assert.deepEqual(chatFailureState(429, 'RATE_LIMITED'),
    { clearDraft: false, restartRequired: false, retryable: true, uncertainOutcome: false });
});

test('expiry and authorization have different recovery', () => {
  assert.deepEqual(chatFailureState(410, 'AI_DRAFT_EXPIRED'), { clearDraft: true, restartRequired: false, retryable: false, uncertainOutcome: false });
  assert.deepEqual(chatFailureState(403, 'PERMISSION_DENIED'), { clearDraft: false, restartRequired: false, retryable: false, uncertainOutcome: false });
});

test('validated date is readable and actor switch is detected', () => {
  assert.equal(readableISODate('2026-11-02'), '02/11/2026');
  assert.equal(readableISODate('2026-02-31'), '2026-02-31');
  assert.equal(actorChanged(9, 10), true);
  assert.equal(actorChanged(9, 9), false);
});


test('revision conflict is recoverable and must not erase draft state', () => {
  assert.deepEqual(chatFailureState(409, 'AI_DRAFT_REVISION_CONFLICT'),
    { clearDraft: false, restartRequired: true, retryable: false, uncertainOutcome: false });
  assert.deepEqual(chatFailureState(409, 'AI_DRAFT_NOT_COLLECTING'),
    { clearDraft: true, restartRequired: false, retryable: false, uncertainOutcome: false });
});

test('a conflict blocks new sends until the user explicitly restarts', () => {
  const conflict = chatFailureState(409, 'AI_DRAFT_REVISION_CONFLICT');
  assert.equal(canSubmitChat(conflict.restartRequired), false);
  assert.equal(canSubmitChat(false), true);
});


test('chat request keys are unique 32-character hex tokens', () => {
  const first = newChatRequestKey();
  const second = newChatRequestKey();
  assert.match(first, /^[a-f0-9]{32}$/);
  assert.notEqual(first, second);
});

test('report setup validates dates and requires a full payroll month', () => {
  assert.equal(reportPeriodValid('ATTENDANCE', '2026-10-01', '2026-10-15'), true);
  assert.equal(reportPeriodValid('ATTENDANCE', '2026-02-31', '2026-03-01'), false);
  assert.equal(reportPeriodValid('ATTENDANCE', '2026-12-31', '2027-01-01'), false);
  assert.equal(reportPeriodValid('PAYROLL_SUMMARY', '2026-02-01', '2026-02-28'), true);
  assert.equal(reportPeriodValid('MY_PAYSLIP', '2026-02-01', '2026-02-27'), false);
  assert.equal(reportPeriodValid('PAYROLL_SUMMARY', '2026-02-02', '2026-02-28'), false);
});

test('error text keeps the uncertain-outcome warning ahead of server text', () => {
  const { chatErrorMessage } = aiState;
  assert.match(chatErrorMessage(503, 'AI_UNAVAILABLE', 'x'), /Chưa nhận được xác nhận/);
  assert.equal(chatErrorMessage(400, 'X', 'Thông báo máy chủ'), 'Thông báo máy chủ');
  assert.match(chatErrorMessage(429, 'RATE_LIMITED'), /quá nhiều yêu cầu/);
});

test('draft progress names the action and the field being asked', () => {
  const { draftKind, draftProgress } = aiState;
  const kind = draftKind(['session', 'leave_type_id', 'reason'], null);
  assert.equal(kind, 'LEAVE');
  assert.deepEqual(draftProgress(kind, ['session', 'leave_type_id', 'reason']),
    { title: 'Đơn nghỉ phép', step: 2, total: 4, field: 'session', fieldLabel: 'Buổi nghỉ' });
  // "reason" alone is shared by leave and fix drafts: keep the kind already shown.
  assert.equal(draftKind(['reason'], 'FIX'), 'FIX');
  assert.equal(draftKind(['scope'], null), 'REPORT');
  assert.equal(draftProgress(null, []), null);
});

test('quick replies prefer server options and send typed inputs', () => {
  const { draftQuickReplies } = aiState;
  assert.deepEqual(draftQuickReplies('scope', [{ field: 'scope', value: 'SELF', label: 'Bản thân' }]),
    [{ label: 'Bản thân', text: 'Bản thân', inputs: { scope: 'SELF' } }]);
  assert.deepEqual(draftQuickReplies('session', [])[0], { label: 'Buổi sáng', text: 'Buổi sáng', inputs: { session: 'MORNING' } });
  assert.deepEqual(draftQuickReplies('reason', []), []);
});

test('date quick replies follow the draft direction', () => {
  assert.deepEqual(aiState.draftQuickReplies('leave_date', []).map((r) => r.label), ['Hôm nay', 'Ngày mai', 'Ngày kia']);
  assert.deepEqual(aiState.draftQuickReplies('work_date', []).map((r) => r.label), ['Hôm nay', 'Hôm qua']);
});

test('reply formatting keeps text as data and groups lists', () => {
  const blocks = aiState.replyBlocks('Theo **Điều 5**:\n\n- Nghỉ phép năm: **12 ngày**\n* Nghỉ ốm\n1. Bước một\n2) Bước hai\nKết thúc');
  assert.deepEqual(blocks[0], { type: 'paragraph', spans: [{ text: 'Theo ', bold: false }, { text: 'Điều 5', bold: true }, { text: ':', bold: false }] });
  assert.equal(blocks[1].type, 'list');
  assert.equal(blocks[1].ordered, false);
  assert.equal(blocks[1].items.length, 2);
  assert.equal(blocks[2].ordered, true);
  assert.equal(blocks[2].items.length, 2);
  assert.deepEqual(blocks[3], { type: 'paragraph', spans: [{ text: 'Kết thúc', bold: false }] });
});

test('reply formatting leaves markup and unmatched markers literal', () => {
  const blocks = aiState.replyBlocks('<img src=x onerror=alert(1)> 2**3 = 8');
  assert.deepEqual(blocks, [{ type: 'paragraph', spans: [{ text: '<img src=x onerror=alert(1)> 2**3 = 8', bold: false }] }]);
  assert.deepEqual(aiState.replyBlocks('## Tiêu đề')[0].spans, [{ text: 'Tiêu đề', bold: true }]);
});

test('copy text drops markdown markers', () => {
  assert.equal(aiState.replyPlainText('Có **2** loại:\n- A\n- B'), 'Có 2 loại:\n\n- A\n- B');
});

test('auto-scroll only follows a reader near the bottom', () => {
  assert.equal(aiState.nearBottom(900, 300, 1250), true);
  assert.equal(aiState.nearBottom(200, 300, 1250), false);
});

test('a message queued during a failed reply goes back to the input instead of being sent', () => {
  assert.deepEqual(aiState.queuedFollowUp('ok', false), { send: 'ok' });
  assert.deepEqual(aiState.queuedFollowUp('ok', true), { restore: 'ok' });
  assert.deepEqual(aiState.queuedFollowUp(null, true), {});
});
