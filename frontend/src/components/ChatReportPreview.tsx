import { useEffect, useState } from 'react';
import dayjs from 'dayjs';
import { Alert, Button, Modal, Space, Table, Typography, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import api from '../api/client';
import type { Report, ReportRun } from '../types/reports';
import { reportFields, reportLabels, reportKindLabels } from './reportPresentation';

interface Props { runId: string | null; onClose: () => void; onRevise: (runId: string) => void }
export function ChatReportPreview(props: Props) {
  return <ReportPreview key={props.runId ?? 'closed'} {...props} />;
}

function ReportPreview({ runId, onClose, onRevise }: Props) {
  const [data, setData] = useState<{ run: ReportRun; report: Report; total_rows: number } | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setLoading(true); setError('');
    api.get('/reports/runs/' + runId, { params: { offset: (page - 1) * 50, limit: 50 } })
      .then((res) => { if (!cancelled) setData(res.data); })
      .catch(() => { if (!cancelled) { setData(null); setError('Báo cáo hết hạn hoặc không còn thuộc quyền truy cập của bạn. Hãy yêu cầu tạo lại trong chat.'); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId, page]);
  const download = async () => {
    if (!runId) return;
    setExporting(true);
    try {
      const res = await api.get('/reports/runs/' + runId + '/download', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement('a'); link.href = url;
      link.download = (data?.report.kind || 'report') + '_' + (data?.report.start_date || '') + '.xlsx';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { message.error('Không tải được báo cáo. Hãy tạo lại nếu báo cáo đã hết hạn.'); }
    finally { setExporting(false); }
  };
  const fields = data ? reportFields[data.report.kind].filter((key) =>
    !(key === 'department_id' && ['HEADCOUNT', 'PAYROLL_SUMMARY'].includes(data.report.kind))) : [];
  return <Modal open={!!runId} centered width={1100} title={data ? reportKindLabels[data.report.kind] : 'Xem báo cáo'}
    onCancel={onClose} footer={null} styles={{ body: { maxHeight: 'calc(100dvh - 180px)', overflowY: 'auto' } }}>
    {error && <Alert type="warning" showIcon title={error} />}
    {data && <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <div><Typography.Text strong>{data.report.start_date.split('-').reverse().join('/')} – {data.report.end_date.split('-').reverse().join('/')}</Typography.Text>
          <div><Typography.Text type="secondary">{({ SELF: 'Bản thân', DIRECT_REPORTS: 'Nhân viên trực tiếp', COMPANY: 'Toàn công ty' })[data.run.scope]} · {data.total_rows} dòng</Typography.Text></div>
        </div>
        <Space><Button onClick={() => { onRevise(data.run.run_id); onClose(); }}>Chỉnh qua chat</Button>
          <Button type="primary" icon={<DownloadOutlined />} loading={exporting} disabled={loading} onClick={() => void download()}>Tải Excel</Button></Space>
      </Space>
      <Table size="small" bordered loading={loading} dataSource={data.report.rows.map((row, i) => ({ ...row, key: i }))}
        columns={fields.map((key) => ({ title: reportLabels[key] || key, dataIndex: key, width: key === 'full_name' ? 200 : 150,
          fixed: key === 'employee_code' || key === 'full_name' ? 'left' as const : undefined,
          render: (value: unknown) => {
            if (value == null) return '—';
            if (['work_date', 'request_date'].includes(key)) return dayjs(String(value)).format('DD/MM/YYYY');
            if (['created_at', 'requested_at'].includes(key)) return dayjs(String(value)).format('DD/MM/YYYY HH:mm');
            const text = String(value);
            if (/^-?\d+(\.\d+)?$/.test(text) && !key.endsWith('_id') && !['employee_code','period_year','period_month'].includes(key)) {
              const [whole, fraction] = text.split('.');
              return <span style={{ display: 'block', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')}{fraction ? ',' + fraction : ''}</span>;
            }
            return text;
          } }))}
        scroll={{ x: fields.length * 150, y: 'min(420px, 48dvh)' }}
        pagination={{ current: page, pageSize: 50, total: data.total_rows, showSizeChanger: false, onChange: setPage }} />
      <Typography.Text type="secondary">{data.report.note} · File tải về chứa toàn bộ dòng của cùng báo cáo.</Typography.Text>
    </Space>}
    {loading && !data && <Typography.Paragraph>Đang tải báo cáo…</Typography.Paragraph>}
  </Modal>;
}
