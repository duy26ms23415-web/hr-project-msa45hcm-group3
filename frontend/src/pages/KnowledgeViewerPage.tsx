import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Space, Spin, Typography, message } from 'antd';
import { ArrowLeftOutlined, FilePdfOutlined } from '@ant-design/icons';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import type { PDFDocumentProxy, TextItem } from 'pdfjs-dist/types/src/display/api';
import api from '../api/client';
import { aiErrorMessage } from '../api/aiErrors';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface SourceReference {
  document_id: number;
  version_id: number;
  section_id: number;
  title: string;
  section_code: string;
  heading: string;
  page_start: number;
  page_end: number;
  anchor: string | null;
}

interface HighlightBox { left: number; top: number; width: number; height: number }

function normalizeText(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/\s+/g, ' ').trim().toLowerCase();
}

function PdfPage({ document, pageNumber, heading }: { document: PDFDocumentProxy; pageNumber: number; heading: string }) {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [highlights, setHighlights] = useState<HighlightBox[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!canvas) return;
    let cancelled = false;
    let renderTask: ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']> | undefined;
    const render = async () => {
      try {
        const page = await document.getPage(pageNumber);
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(1.45, Math.max(0.75, 980 / baseViewport.width));
        const viewport = page.getViewport({ scale });
        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Canvas unavailable');
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        setPageSize({ width: viewport.width, height: viewport.height });
        renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        });
        await renderTask.promise;
        const content = await page.getTextContent();
        if (cancelled) return;
        const textItems = content.items.filter((item): item is TextItem => 'str' in item);
        const target = normalizeText(heading);
        let matching = textItems.filter(item => normalizeText(item.str).includes(target));
        if (matching.length === 0 && target) {
          const lines = new Map<number, TextItem[]>();
          for (const item of textItems) {
            const transformed = pdfjsLib.Util.transform(viewport.transform, item.transform);
            const baseline = Math.round(transformed[5] / 4) * 4;
            lines.set(baseline, [...(lines.get(baseline) ?? []), item]);
          }
          for (const items of lines.values()) {
            if (normalizeText(items.map(item => item.str).join(' ')).includes(target)) matching = items;
          }
        }
        const boxes = matching.map(item => {
          const transform = pdfjsLib.Util.transform(viewport.transform, item.transform);
          const height = Math.max(8, Math.hypot(transform[2], transform[3]));
          return {
            left: transform[4],
            top: transform[5] - height,
            width: Math.max(8, item.width * scale),
            height: height * 1.25,
          };
        });
        setHighlights(boxes);
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    void render();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [canvas, document, heading, pageNumber]);

  return <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
    <div style={{ position: 'relative', width: pageSize.width || 'fit-content', maxWidth: '100%', boxShadow: '0 2px 12px rgba(15, 23, 42, .14)' }}>
      <canvas ref={setCanvas} aria-label={`Trang ${pageNumber}`} style={{ display: 'block', maxWidth: '100%', height: 'auto' }} />
      {highlights.map((box, index) => <div key={`${pageNumber}-${index}`} aria-label="Mục được trích dẫn" style={{ position: 'absolute', left: box.left, top: box.top, width: box.width, height: box.height, background: 'rgba(255, 214, 10, .28)', outline: '2px solid #d48806', pointerEvents: 'none' }} />)}
      {failed && <Alert type="warning" title={`Không render được trang ${pageNumber}.`} />}
    </div>
  </div>;
}

export function KnowledgeViewerPage() {
  const { documentId = '' } = useParams();
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const versionId = Number(query.get('version'));
  const sectionId = Number(query.get('section'));
  const [source, setSource] = useState<SourceReference | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const preview = query.get('preview') === 'true';
  const pages = useMemo(() => source ? Array.from({ length: source.page_end - source.page_start + 1 }, (_, index) => source.page_start + index) : [], [source]);

  useEffect(() => {
    const id = Number(documentId);
    if (!Number.isSafeInteger(id) || id < 1 || !Number.isSafeInteger(versionId) || versionId < 1 || !Number.isSafeInteger(sectionId) || sectionId < 1) {
      setError('Liên kết tài liệu không hợp lệ.');
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let task: ReturnType<typeof pdfjsLib.getDocument> | undefined;
    let active = true;
    const load = async () => {
      setLoading(true);
      setError('');
      setSource(null);
      setPdf(null);
      try {
        const params = preview ? { preview: true } : undefined;
        const reference = await api.get<SourceReference>(`/ai/knowledge/${id}/versions/${versionId}/sections/${sectionId}`, { signal: controller.signal, params });
        const file = await api.get<ArrayBuffer>(`/ai/knowledge/${id}/versions/${versionId}/file`, { responseType: 'arraybuffer', signal: controller.signal, params });
        if (!active) return;
        setSource(reference.data);
        task = pdfjsLib.getDocument({ data: new Uint8Array(file.data) });
        setPdf(await task.promise);
      } catch (failure) {
        if (active) {
          const text = await aiErrorMessage(failure, 'Tài liệu không còn khả dụng hoặc bạn không có quyền truy cập.');
          if (active) {
            setError(text);
            message.error(text);
          }
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
      controller.abort();
      void task?.destroy();
    };
  }, [documentId, sectionId, versionId, preview]);

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>Quay lại</Button>
    {preview && <Alert type="info" showIcon title="Xem trước dành cho quản trị. Bản DRAFT và mục chưa ban hành không được dùng để trả lời người dùng." />}
    {loading && <div style={{ padding: 48, textAlign: 'center' }}><Spin size="large" /></div>}
    {error && <Alert type="warning" showIcon title={error} />}
    {source && pdf && <>
      <Card>
        <Space align="start">
          <FilePdfOutlined style={{ fontSize: 24, color: '#d4380d' }} />
          <div>
            <Typography.Title level={4} style={{ marginTop: 0 }}>{source.title}</Typography.Title>
            <Typography.Text strong>{source.section_code} · {source.heading}</Typography.Text>
            <div><Typography.Text type="secondary">Phiên bản {source.version_id} · Trang {source.page_start}{source.page_end !== source.page_start ? `–${source.page_end}` : ''}. Phần được tô sáng là mục trích dẫn.</Typography.Text></div>
          </div>
        </Space>
      </Card>
      {pages.map(page => <PdfPage key={`${source.version_id}-${page}`} document={pdf} pageNumber={page} heading={source.heading} />)}
    </>}
  </Space>;
}
