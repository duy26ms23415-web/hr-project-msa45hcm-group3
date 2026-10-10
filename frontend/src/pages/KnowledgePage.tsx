import { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Row, Empty, Form, Input, InputNumber, Modal, Collapse, Select, Space, Switch, Table, Tabs, Tag, Typography, Upload, Dropdown, Descriptions, message } from 'antd';
import type { FormInstance } from 'antd';
import { FilePdfOutlined, PlusOutlined, DeleteOutlined, InboxOutlined, UploadOutlined, EyeOutlined, DownloadOutlined, MoreOutlined, ReloadOutlined } from '@ant-design/icons';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { aiErrorMessage } from '../api/aiErrors';

interface Document {
  document_id: number;
  title: string;
  content: string;
  source_url?: string | null;
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
  minimum_role: string;
  updated_at: string;
  document_code?: string | null;
  current_version_id?: number | null;
}

interface Version {
  version_id: number;
  version_number: number;
  title: string;
  minimum_role: string;
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
  page_count: number | null;
  byte_size: number | null;
  sha256: string | null;
  created_at: string;
  effective_from: string | null;
  effective_to: string | null;
}

interface Section {
  section_id: number;
  section_code: string;
  heading: string;
  page_start: number;
  page_end: number;
  is_answerable: boolean;
}

interface UploadItem {
  uid: string;
  file: File;
  status: 'pending' | 'uploading' | 'done' | 'error';
  error?: string;
  title: string;
}

const roleLabels: Record<string, string> = { EMPLOYEE: 'Tất cả nhân viên', MANAGER: 'Quản lý, HR và quản trị viên', HR: 'HR và quản trị viên', ADMIN: 'Chỉ quản trị viên' };
const statusLabels: Record<string, string> = { DRAFT: 'Bản nháp', PUBLISHED: 'Đã công bố', ARCHIVED: 'Đã lưu trữ' };
const searchText = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase().trim();

function SectionFields({ form }: { form: FormInstance }) {
  return <Form.List name="sections" rules={[{ validator: async (_, value) => {
    if (!value?.length || value.length > 200) throw new Error('Thêm ít nhất một mục, tối đa 200 mục.');
  } }]}>
    {(fields, { add, remove }, { errors }) => <Space orientation="vertical" style={{ width: '100%' }} size={12}>
      {fields.map(({ key, name, ...rest }) => <Card key={key} size="small" title={`Mục ${name + 1}`}
        extra={<Button type="text" danger icon={<DeleteOutlined />} aria-label={`Xóa mục ${name + 1}`} onClick={() => remove(name)} />}>
        <Form.Item {...rest} name={[name, 'section_code']} hidden><Input /></Form.Item>
        <Form.Item {...rest} name={[name, 'heading']} label="Tiêu đề mục trong PDF"
          rules={[{ required: true, whitespace: true, message: 'Nhập tiêu đề xuất hiện trong PDF.' }, { max: 300 }]}>
          <Input placeholder="Ví dụ: Điều 1. Thời giờ làm việc" maxLength={300} />
        </Form.Item>
        <Row gutter={16}>
          <Col xs={12} sm={8}><Form.Item {...rest} name={[name, 'page_start']} label="Từ trang"
            rules={[{ required: true, message: 'Nhập trang bắt đầu.' }]}><InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col xs={12} sm={8}><Form.Item {...rest} name={[name, 'page_end']} label="Đến trang"
            dependencies={['sections', name, 'page_start']}
            rules={[{ required: true, message: 'Nhập trang kết thúc.' }, { validator: async (_, value) => {
              const start = form.getFieldValue(['sections', name, 'page_start']);
              if (value < start || value - start >= 10) throw new Error('Chọn từ 1 đến 10 trang cho mỗi mục.');
            } }]}><InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col xs={24} sm={8}><Form.Item {...rest} name={[name, 'is_answerable']} label="AI được dùng mục này" valuePropName="checked"><Switch /></Form.Item></Col>
        </Row>
      </Card>)}
      <Form.ErrorList errors={errors} />
      <Button type="dashed" icon={<PlusOutlined />} block disabled={fields.length >= 200}
        onClick={() => add({ heading: '', page_start: 1, page_end: 1, is_answerable: true })}>Thêm mục trong PDF</Button>
    </Space>}
  </Form.List>;
}

const sectionPayload = (sections: Record<string, unknown>[]) => sections.map((section, index) => ({
  ...section, section_code: section.section_code || `SECTION_${index + 1}`,
}));

export function KnowledgePage() {
  const { hasRole } = useAuth();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pdfTab, setPdfTab] = useState('upload');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>();
  const [roleFilter, setRoleFilter] = useState<string>();
  const [viewing, setViewing] = useState<Document | null>(null);
  const [renaming, setRenaming] = useState<Document | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Document | null>(null);
  const [versionDocument, setVersionDocument] = useState<Document | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [selectedPdf, setSelectedPdf] = useState<File | null>(null);
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [editingVersion, setEditingVersion] = useState<Version | null>(null);
  const [reviewingVersion, setReviewingVersion] = useState<Version | null>(null);
  const [reviewSections, setReviewSections] = useState<Section[]>([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [editorLoading, setEditorLoading] = useState(false);
  const [form] = Form.useForm();
  const [versionForm] = Form.useForm();
  const [draftForm] = Form.useForm();
  const load = async () => {
    setLoading(true);
    try { setDocuments((await api.get('/ai/knowledge')).data); }
    catch { message.error('Không tải được kho kiến thức.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const edit = (document: Document | null) => {
    setEditing(document);
    setSelectedPdf(null);
    setUploadItems([]);
    form.resetFields();
    form.setFieldsValue(document ?? { status: 'DRAFT', minimum_role: 'EMPLOYEE' });
    setOpen(true);
  };
  const save = async () => {
    let values;
    try { values = await form.validateFields(); } catch { return; }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/ai/knowledge/${editing.document_id}`, { ...values, source_url: values.source_url?.trim() || null });
      } else {
        const pending = uploadItems.filter(item => item.status === 'pending' || item.status === 'error');
        if (!pending.length) return;
        let completed = 0;
        for (const item of pending) {
          setUploadItems(items => items.map(current => current.uid === item.uid ? { ...current, status: 'uploading', error: undefined } : current));
          const body = new FormData();
          body.append('file', item.file);
          body.append('title', item.title.trim());
          body.append('minimum_role', values.minimum_role || 'EMPLOYEE');
          try {
            await api.post('/ai/knowledge/upload', body);
            completed += 1;
            setUploadItems(items => items.map(current => current.uid === item.uid ? { ...current, status: 'done' } : current));
          } catch (error: unknown) {
            const detail = await aiErrorMessage(error, 'Không tải được PDF.');
            setUploadItems(items => items.map(current => current.uid === item.uid ? { ...current, status: 'error', error: detail } : current));
          }
        }
        if (completed) message.success(`Đã lưu ${completed} tài liệu thành bản nháp. Mở Phiên bản PDF để kiểm tra và công bố.`);
        await load();
        return;
      }
      setOpen(false);
      message.success('Đã lưu tài liệu.');
      await load();
    } catch (error: unknown) { message.error(await aiErrorMessage(error, 'Không lưu được tài liệu. Kiểm tra PDF và quyền truy cập.')); }
    finally { setSaving(false); }
  };
  const loadVersions = async (document: Document) => {
    setVersionsLoading(true);
    try { setVersions((await api.get(`/ai/knowledge/${document.document_id}/versions`)).data); }
    catch { message.error('Không tải được lịch sử phiên bản.'); }
    finally { setVersionsLoading(false); }
  };
  const openVersions = (document: Document) => {
    setVersionDocument(document);
    setPdfTab('versions');
    setVersions([]);
    setSelectedPdf(null);
    versionForm.resetFields();
    versionForm.setFieldsValue({ title: document.title, minimum_role: document.minimum_role, sections: [{ heading: '', page_start: 1, page_end: 1, is_answerable: true }] });
    void loadVersions(document);
  };
  const uploadVersion = async () => {
    if (!versionDocument) return;
    let values;
    try { values = await versionForm.validateFields(); } catch { return; }
    if (!selectedPdf) { message.error('Chọn một file PDF trước.'); return; }
    const body = new FormData();
    body.append('file', selectedPdf);
    body.append('title', values.title || versionDocument.title);
    body.append('minimum_role', values.minimum_role || versionDocument.minimum_role);
    setSaving(true);
    try {
      await api.post(`/ai/knowledge/${versionDocument.document_id}/versions`, body);
      setSelectedPdf(null);
      setPdfTab('versions');
      message.success('Đã tải phiên bản nháp. Kiểm tra mục/trang rồi mới công bố.');
      await loadVersions(versionDocument);
    } catch (error: any) {
      message.error(await aiErrorMessage(error, 'Không tải được PDF. Kiểm tra file và tiêu đề mục/trang.'));
    } finally { setSaving(false); }
  };
  const publishVersion = async (version: Version) => {
    if (!versionDocument) return;
    setSaving(true);
    try {
      await api.post(`/ai/knowledge/${versionDocument.document_id}/versions/${version.version_id}/publish`);
      message.success(`Đã công bố v${version.version_number}. AI có thể dùng các mục được cho phép trong thời gian hiệu lực.`);
      setReviewingVersion(null);
      await Promise.all([loadVersions(versionDocument), load()]);
    } catch (error: any) { message.error(error.response?.data?.detail || 'Không công bố được phiên bản.'); }
    finally { setSaving(false); }
  };
  const reviewVersion = async (version: Version, document = versionDocument) => {
    if (!document) return;
    setReviewLoading(true);
    try {
      const sections = (await api.get<Section[]>(`/ai/knowledge/${document.document_id}/versions/${version.version_id}/sections`, { params: { preview: true } })).data;
      setVersionDocument(document); setReviewSections(sections); setReviewingVersion(version);
    } catch (error) { message.error(await aiErrorMessage(error, 'Không tải được các mục cần kiểm tra.')); }
    finally { setReviewLoading(false); }
  };
  const reviewFromList = async (document: Document) => {
    setOpeningId(document.document_id);
    try {
      const available = (await api.get<Version[]>(`/ai/knowledge/${document.document_id}/versions`)).data;
      const draft = available.find(version => version.status === 'DRAFT' && version.page_count);
      if (!draft) {
        if (document.content.trim() && !available.some(version => version.page_count)) edit(document);
        else { openVersions(document); setPdfTab('upload'); message.info('Chưa có phiên bản PDF nháp. Tải phiên bản mới trước khi công bố.'); }
        return;
      }
      setVersions(available); await reviewVersion(draft, document);
    } catch (error) { message.error(await aiErrorMessage(error, 'Không mở được bước kiểm tra công bố.')); }
    finally { setOpeningId(null); }
  };
  const editDraftVersion = async (version: Version) => {
    if (!versionDocument) return;
    setEditorLoading(true);
    draftForm.resetFields();
    try {
      const sections = (await api.get<Section[]>(`/ai/knowledge/${versionDocument.document_id}/versions/${version.version_id}/sections`, { params: { preview: true } })).data;
      draftForm.setFieldsValue({ title: version.title, minimum_role: version.minimum_role, effective_from: version.effective_from || '', effective_to: version.effective_to || '', sections: sections.map(({ section_code, heading, page_start, page_end, is_answerable }) => ({ section_code, heading, page_start, page_end, is_answerable })) });
      setEditingVersion(version);
    } catch { message.error('Không đọc được bản nháp hoặc bạn không có quyền sửa.'); }
    finally { setEditorLoading(false); }
  };
  const saveDraftVersion = async () => {
    if (!versionDocument || !editingVersion) return;
    let values;
    try { values = await draftForm.validateFields(); } catch { return; }
    const sections = sectionPayload(values.sections);
    setSaving(true);
    try {
      await api.put(`/ai/knowledge/${versionDocument.document_id}/versions/${editingVersion.version_id}`, { title: values.title, minimum_role: values.minimum_role, effective_from: values.effective_from || null, effective_to: values.effective_to || null, sections });
      setEditingVersion(null);
      message.success('Đã lưu bản nháp và kiểm tra mapping với PDF.');
      await loadVersions(versionDocument);
    } catch (error: any) { message.error(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Không lưu được mapping. Kiểm tra heading/trang và quyền.'); }
    finally { setSaving(false); }
  };
  const downloadPdf = async (document: Document, version: Version) => {
    const response = await api.get(`/ai/knowledge/${document.document_id}/versions/${version.version_id}/file`, { params: { preview: true, download: true }, responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = window.document.createElement('a');
    link.href = url; link.download = `${document.title}_v${version.version_number}.pdf`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const openDocument = async (document: Document, download = false) => {
    setOpeningId(document.document_id);
    try {
      const available = (await api.get<Version[]>(`/ai/knowledge/${document.document_id}/versions`)).data;
      const pdf = available.find(version => version.version_id === document.current_version_id && version.page_count)
        || available.find(version => version.page_count);
      if (!pdf) { setViewing(document); return; }
      if (download) await downloadPdf(document, pdf);
      else navigate(`/knowledge/view/${document.document_id}?version=${pdf.version_id}&preview=true`);
    } catch (error) { message.error(await aiErrorMessage(error, 'Không mở được tài liệu.')); }
    finally { setOpeningId(null); }
  };
  const renameDocument = async () => {
    if (!renaming || !newTitle.trim()) return;
    setSaving(true);
    try {
      await api.patch(`/ai/knowledge/${renaming.document_id}/title`, { title: newTitle.trim() });
      setRenaming(null); message.success('Đã đổi tên hiển thị.'); await load();
    } catch (error) { message.error(await aiErrorMessage(error, 'Không đổi được tên tài liệu.')); }
    finally { setSaving(false); }
  };
  const restoreDocument = async (document: Document) => {
    setSaving(true);
    try {
      await api.post(`/ai/knowledge/${document.document_id}/restore`);
      message.success('Đã khôi phục về bản nháp. Mở Phiên bản PDF để kiểm tra và công bố lại.'); await load();
    } catch (error) { message.error(await aiErrorMessage(error, 'Không khôi phục được tài liệu.')); }
    finally { setSaving(false); }
  };
  const archiveDocument = async (document: Document) => {
    try {
      await api.post(`/ai/knowledge/${document.document_id}/archive`);
      message.success('Đã lưu trữ tài liệu.');
      await load();
    } catch (error: any) { message.error(error.response?.data?.detail || 'Không lưu trữ được tài liệu.'); }
  };
  const roleOptions = ['EMPLOYEE', 'MANAGER', 'HR', ...(hasRole(['ADMIN']) ? ['ADMIN'] : [])].map(value => ({ value, label: roleLabels[value] }));
  const filtered = documents.filter(document => searchText(`${document.title} ${document.document_code || ''}`).includes(searchText(search))
    && (!statusFilter || document.status === statusFilter) && (!roleFilter || document.minimum_role === roleFilter));
  const modalStyles = { body: { maxHeight: 'calc(100dvh - 180px)', overflowY: 'auto' as const } };
  const pdfPicker = <Upload.Dragger accept="application/pdf,.pdf" maxCount={1}
    fileList={selectedPdf ? [{ uid: selectedPdf.name, name: selectedPdf.name }] : []}
    beforeUpload={file => {
      if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 10 * 1024 * 1024) { message.error('Chọn PDF không quá 10 MiB.'); return Upload.LIST_IGNORE; }
      setSelectedPdf(file); return false;
    }} onRemove={() => { setSelectedPdf(null); return true; }} disabled={saving}>
    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
    <p className="ant-upload-text">Kéo PDF vào đây hoặc bấm để chọn</p>
    <p className="ant-upload-hint">PDF có văn bản · tối đa 10 MiB, 100 trang</p>
  </Upload.Dragger>;
  const batchPicker = <Upload.Dragger accept="application/pdf,.pdf" multiple
    fileList={uploadItems.map(item => ({ uid: item.uid, name: item.file.name,
      status: item.status === 'pending' ? undefined : item.status === 'uploading' ? 'uploading' : item.status === 'done' ? 'done' : 'error' }))}
    beforeUpload={file => {
      if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 10 * 1024 * 1024) {
        message.error(`${file.name}: chọn PDF không quá 10 MiB.`); return Upload.LIST_IGNORE;
      }
      setUploadItems(items => [...items, { uid: file.uid, file, title: file.name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').slice(0, 200), status: 'pending' }]);
      return false;
    }} onRemove={file => { setUploadItems(items => items.filter(item => item.uid !== file.uid)); return true; }}
    disabled={saving}>
    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
    <p className="ant-upload-text">Kéo nhiều PDF vào đây hoặc bấm để chọn</p>
    <p className="ant-upload-hint">Mỗi file là một tài liệu · PDF có văn bản · tối đa 10 MiB, 100 trang/file</p>
  </Upload.Dragger>;
  const uploadPanel = <Form form={versionForm} layout="vertical" disabled={saving}>
    <Form.Item>{pdfPicker}</Form.Item>
    <Collapse ghost items={[{ key: 'options', label: 'Tùy chọn tài liệu', children: <>
      <Form.Item name="title" label="Tên tài liệu" rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
      <Form.Item name="minimum_role" label="Người được đọc" extra="Mặc định giữ quyền của tài liệu hiện tại. AI chỉ trích dẫn cho người được đọc."><Select options={roleOptions} /></Form.Item>
    </> }]} />
    <Button type="primary" icon={<UploadOutlined />} loading={saving} disabled={!selectedPdf} style={{ marginTop: 16 }} onClick={() => void uploadVersion()}>Lưu phiên bản nháp</Button>
  </Form>;
  const versionsPanel = <Table rowKey="version_id" size="small" loading={versionsLoading} dataSource={versions} pagination={false} scroll={{ x: 650 }}
    locale={{ emptyText: <Empty description="Chưa có phiên bản PDF. Hãy tải bản đầu tiên." /> }}
    columns={[
      { title: 'Phiên bản', dataIndex: 'version_number', render: (value: number) => `v${value}` },
      { title: 'Tên', dataIndex: 'title' }, { title: 'Số trang', dataIndex: 'page_count', render: (value: number | null) => value ?? 'Văn bản' },
      { title: 'Trạng thái', dataIndex: 'status', render: (value: string) => <Tag color={value === 'PUBLISHED' ? 'green' : 'default'}>{statusLabels[value]}</Tag> },
      { title: 'Thao tác', render: (_, version: Version) => version.page_count ? <Space wrap>
        <Button size="small" icon={<EyeOutlined />} href={`/knowledge/view/${versionDocument?.document_id}?version=${version.version_id}&preview=true`} target="_blank" rel="noopener noreferrer">Xem PDF</Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => { if (versionDocument) void downloadPdf(versionDocument, version).catch(async error => message.error(await aiErrorMessage(error, 'Không tải được PDF.'))); }}>Tải</Button>
        {version.status === 'DRAFT' && versionDocument?.status !== 'ARCHIVED' && <>
          <Button type="primary" size="small" loading={reviewLoading} onClick={() => void reviewVersion(version)}>Kiểm tra & công bố</Button>
        </>}
      </Space> : null },
    ]} />;
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <div><Typography.Title level={4} style={{ marginBottom: 8 }}>Tài liệu & chính sách</Typography.Title>
      <Typography.Text type="secondary">Quản lý nguồn nội bộ để trợ lý AI trả lời có căn cứ.</Typography.Text></div>
    <Alert type="info" showIcon title="Lưu bản nháp → kiểm tra nội dung → công bố. Chỉ tài liệu đã công bố và đúng quyền truy cập mới được AI sử dụng." />
    <Card title={`Danh sách tài liệu (${documents.length})`} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => edit(null)}>Thêm tài liệu</Button>}>
      <Space wrap style={{ marginBottom: 20 }}>
        <Input.Search placeholder="Tìm tên hoặc mã, không cần dấu" allowClear value={search} onChange={event => setSearch(event.target.value)} style={{ width: 300 }} />
        <Select allowClear placeholder="Tất cả trạng thái" value={statusFilter} onChange={setStatusFilter} style={{ width: 180 }}
          options={Object.entries(statusLabels).map(([value, label]) => ({ value, label: `${label} (${documents.filter(document => document.status === value).length})` }))} />
        <Select allowClear placeholder="Tất cả người được đọc" value={roleFilter} onChange={setRoleFilter} style={{ width: 250 }} options={roleOptions} />
        {(search || statusFilter || roleFilter) && <Button onClick={() => { setSearch(''); setStatusFilter(undefined); setRoleFilter(undefined); }}>Xóa bộ lọc</Button>}
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>Làm mới</Button>
      </Space>
      <Typography.Paragraph type="secondary">{filtered.length} tài liệu phù hợp · Bản nháp và tài liệu lưu trữ chỉ dùng để kiểm tra, chưa được AI sử dụng.</Typography.Paragraph>
      <Table rowKey="document_id" dataSource={filtered} loading={loading} scroll={{ x: 850 }}
        pagination={{ pageSize: 10, showTotal: total => `${total} tài liệu` }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={documents.length ? 'Không có tài liệu phù hợp bộ lọc.' : 'Chưa có tài liệu. Thêm PDF nội quy hoặc chính sách để bắt đầu.'} /> }}
        columns={[
          { title: 'Tài liệu', dataIndex: 'title', width: 320, sorter: (a, b) => a.title.localeCompare(b.title, 'vi'), render: (value: string, document: Document) => <div>
            <Button type="link" style={{ padding: 0, height: 'auto', whiteSpace: 'normal', textAlign: 'left' }} onClick={() => void openDocument(document)}>{value}</Button>
            <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{document.document_code && !document.document_code.startsWith('DOC-') && document.document_code !== value ? document.document_code : `Tài liệu #${document.document_id}`}</Typography.Text></div>
          </div> },
          { title: 'Trạng thái', dataIndex: 'status', render: (value: string) => <Tag color={value === 'PUBLISHED' ? 'green' : 'default'}>{statusLabels[value]}</Tag> },
          { title: 'Người được đọc', dataIndex: 'minimum_role', render: (value: string) => roleLabels[value] || value },
          { title: 'Cập nhật', dataIndex: 'updated_at', defaultSortOrder: 'descend', sorter: (a, b) => Date.parse(a.updated_at) - Date.parse(b.updated_at), render: (value: string) => new Date(value).toLocaleString('vi-VN') },
          { title: 'Thao tác', render: (_, document: Document) => <Space wrap>
            <Button icon={<EyeOutlined />} loading={openingId === document.document_id} onClick={() => void openDocument(document)}>Xem</Button>
            {document.status === 'DRAFT' && <Button type="primary" loading={openingId === document.document_id} onClick={() => void reviewFromList(document)}>Kiểm tra & công bố</Button>}
            {document.status !== 'DRAFT' && <Button icon={<FilePdfOutlined />} onClick={() => openVersions(document)}>Phiên bản PDF</Button>}
            <Dropdown menu={{ items: [
              { key: 'rename', label: 'Đổi tên hiển thị', onClick: () => { setRenaming(document); setNewTitle(document.title); } },
              { key: 'download', label: 'Tải PDF', icon: <DownloadOutlined />, onClick: () => void openDocument(document, true) },
              ...(document.status === 'DRAFT' ? [{ key: 'versions', label: 'Lịch sử & tải phiên bản PDF', icon: <FilePdfOutlined />, onClick: () => openVersions(document) }] : []),
              ...(document.status === 'PUBLISHED' ? [{ key: 'review', label: 'Kiểm tra phiên bản nháp mới', onClick: () => void reviewFromList(document) }] : []),
              ...(document.status === 'DRAFT' && !document.current_version_id && document.content.trim() ? [{ key: 'edit', label: 'Sửa thông tin văn bản', onClick: () => edit(document) }] : []),
              { key: 'lifecycle', label: document.status === 'ARCHIVED' ? 'Khôi phục về bản nháp' : 'Lưu trữ tài liệu', danger: document.status !== 'ARCHIVED', onClick: () => Modal.confirm({
                title: document.status === 'ARCHIVED' ? 'Khôi phục về bản nháp?' : 'Lưu trữ tài liệu?',
                content: document.status === 'ARCHIVED' ? 'Tạo bản nháp từ PDF đã lưu, giữ lại lịch sử. Kiểm tra rồi công bố lại để AI sử dụng; không cần tải lại file.' : 'Tài liệu sẽ ngừng được AI sử dụng. Bạn vẫn có thể xem và tải các phiên bản.',
                okText: document.status === 'ARCHIVED' ? 'Khôi phục' : 'Lưu trữ', cancelText: 'Hủy', onOk: () => document.status === 'ARCHIVED' ? restoreDocument(document) : archiveDocument(document),
              }) },
            ] }}><Button icon={<MoreOutlined />} aria-label={`Thao tác khác: ${document.title}`} /></Dropdown>
          </Space> },
        ]} />
    </Card>
    <Modal forceRender centered open={open} title={editing ? 'Sửa thông tin tài liệu' : 'Thêm tài liệu'}
      okButtonProps={{ disabled: !editing && (!uploadItems.some(item => item.status === 'pending' || item.status === 'error') || uploadItems.some(item => item.status !== 'done' && !item.title.trim())) }} onCancel={() => { if (!saving) setOpen(false); }} onOk={() => void save()} confirmLoading={saving}
      okText={editing ? "Lưu thay đổi" : uploadItems.some(item => item.status === 'error') ? 'Thử lại file lỗi' : 'Tải lên và lưu nháp'} cancelText={editing ? 'Hủy' : 'Đóng'} width={720} styles={modalStyles}>
      <Form form={form} layout="vertical" disabled={saving}>
        {!editing ? <>
          <Form.Item style={{ marginTop: 16 }}>{batchPicker}</Form.Item>
          {uploadItems.filter(item => item.status === 'error').map(item => <Alert key={item.uid} type="error" showIcon title={item.file.name} description={item.error} style={{ marginBottom: 8 }} />)}
          {uploadItems.map(item => <Form.Item key={item.uid} label={`Tên hiển thị · ${item.file.name}`}>
            <Input value={item.title} maxLength={200} disabled={saving || item.status === 'done'} onChange={event => setUploadItems(items => items.map(current => current.uid === item.uid ? { ...current, title: event.target.value } : current))} placeholder="Ví dụ: Chính sách nghỉ phép năm" />
          </Form.Item>)}
          <Typography.Paragraph type="secondary">Đặt tên dễ hiểu trước khi tải. File được xử lý lần lượt; thử lại chỉ tải file lỗi.</Typography.Paragraph>
          <Collapse ghost items={[{ key: 'access', label: 'Giới hạn người được đọc (không bắt buộc)', children:
            <Form.Item name="minimum_role" label="Người được đọc" extra="Mặc định tất cả nhân viên. Chỉ giới hạn với tài liệu dành riêng cho quản lý hoặc HR."><Select options={roleOptions} /></Form.Item>
          }]} />
        </> : <>
          <Form.Item name="title" label="Tên tài liệu" rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
          <Form.Item name="content" label="Nội dung văn bản" rules={[{ required: true, whitespace: true, max: 50000 }]}><Input.TextArea autoSize={{ minRows: 5, maxRows: 10 }} maxLength={50000} /></Form.Item>
          <Form.Item name="source_url" label="Liên kết nguồn" rules={[{ type: 'url' }]}><Input /></Form.Item>
          <Form.Item name="minimum_role" label="Người được đọc"><Select options={roleOptions} /></Form.Item>
          <Form.Item name="status" label="Trạng thái"><Select options={Object.entries(statusLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
        </>}
      </Form>
    </Modal>
    <Modal forceRender centered open={!!versionDocument && !reviewingVersion} title={versionDocument ? `PDF · ${versionDocument.title}` : 'Quản lý PDF'}
      onCancel={() => { if (!saving) setVersionDocument(null); }} footer={null} width={1000} styles={modalStyles}>
      <Tabs activeKey={pdfTab} onChange={setPdfTab} items={[
        ...(versionDocument?.status !== 'ARCHIVED' ? [{ key: 'upload', label: 'Tải phiên bản mới', children: uploadPanel }] : []),
        { key: 'versions', label: `Lịch sử phiên bản (${versions.length})`, children: <>
          {versionDocument?.status === 'ARCHIVED' && <Alert type="warning" showIcon title="Tài liệu đã lưu trữ. Bạn có thể xem/tải các phiên bản; khôi phục về bản nháp để tải bản mới." style={{ marginBottom: 16 }} />}
          {versionsPanel}</> },
      ]} />
    </Modal>
    <Modal centered open={!!reviewingVersion} title={`Kiểm tra & công bố · v${reviewingVersion?.version_number || ''}`} width={850} styles={modalStyles}
      onCancel={() => { if (!saving) setReviewingVersion(null); }} footer={<Space wrap>
        <Button disabled={saving} onClick={() => setReviewingVersion(null)}>Để sau</Button>
        <Button loading={editorLoading} onClick={() => { if (reviewingVersion) { void editDraftVersion(reviewingVersion); setReviewingVersion(null); } }} disabled={saving}>Chỉnh thông tin & mục</Button>
        <Button type="primary" loading={saving} disabled={!reviewSections.length} onClick={() => { if (reviewingVersion) void publishVersion(reviewingVersion); }}>Công bố v{reviewingVersion?.version_number}</Button>
      </Space>}>
      {reviewingVersion && versionDocument && <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Alert type="info" showIcon title="Sau công bố, phiên bản này trở thành nguồn hiện hành của tài liệu." description="AI chỉ sử dụng các mục được bật, trong thời gian hiệu lực và đúng quyền đọc. Các phiên bản trước vẫn được giữ trong lịch sử." />
        <Descriptions bordered size="small" column={1} items={[
          { key: 'title', label: 'Tên được công bố', children: reviewingVersion.title },
          { key: 'role', label: 'Người được đọc', children: roleLabels[reviewingVersion.minimum_role] || reviewingVersion.minimum_role },
          { key: 'date', label: 'Hiệu lực', children: `${reviewingVersion.effective_from ? new Date(reviewingVersion.effective_from + 'T00:00:00').toLocaleDateString('vi-VN') : 'Từ khi công bố'} → ${reviewingVersion.effective_to ? new Date(reviewingVersion.effective_to + 'T00:00:00').toLocaleDateString('vi-VN') : 'Không đặt ngày kết thúc'}` },
          { key: 'pdf', label: 'PDF nguồn', children: <Space wrap><Typography.Text>{reviewingVersion.page_count} trang</Typography.Text>
            <Button icon={<EyeOutlined />} href={`/knowledge/view/${versionDocument.document_id}?version=${reviewingVersion.version_id}&preview=true`} target="_blank" rel="noopener noreferrer">Xem PDF ở tab riêng</Button></Space> },
        ]} />
        <Typography.Text strong>Các mục nguồn · {reviewSections.filter(section => section.is_answerable).length}/{reviewSections.length} mục cho AI sử dụng</Typography.Text>
        {!reviewSections.some(section => section.is_answerable) && <Alert type="warning" showIcon title="Chưa bật mục nào cho AI. Sau công bố, AI vẫn chưa thể trả lời từ tài liệu này." />}
        <Table rowKey="section_id" size="small" pagination={false} dataSource={reviewSections} scroll={{ y: 280 }} columns={[
          { title: 'Mục trong PDF', dataIndex: 'heading' },
          { title: 'Trang', render: (_, section: Section) => section.page_start === section.page_end ? section.page_start : `${section.page_start}–${section.page_end}` },
          { title: 'AI sử dụng', dataIndex: 'is_answerable', render: (value: boolean) => <Tag color={value ? 'green' : 'default'}>{value ? 'Được dùng' : 'Không dùng'}</Tag> },
        ]} />
      </Space>}
    </Modal>
    <Modal open={!!renaming} title="Đổi tên hiển thị" onCancel={() => { if (!saving) setRenaming(null); }} onOk={() => void renameDocument()} confirmLoading={saving} okText="Lưu tên" cancelText="Hủy" okButtonProps={{ disabled: !newTitle.trim() }}>
      <Typography.Paragraph type="secondary">Tên dùng trong danh sách tài liệu. Nội dung và phiên bản PDF đã công bố được giữ nguyên.</Typography.Paragraph>
      <Input aria-label="Tên hiển thị tài liệu" value={newTitle} maxLength={200} onChange={event => setNewTitle(event.target.value)} />
    </Modal>
    <Modal open={!!viewing} title={viewing?.title} onCancel={() => setViewing(null)} footer={<Button onClick={() => setViewing(null)}>Đóng</Button>} width={800} styles={modalStyles}>
      <Alert type="info" showIcon title={`${statusLabels[viewing?.status || 'DRAFT']} · Tài liệu văn bản, chưa có file PDF`} style={{ marginBottom: 16 }} />
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{viewing?.content || 'Chưa có nội dung. Mở Phiên bản PDF để tải tài liệu.'}</Typography.Paragraph>
      {viewing?.source_url && <Typography.Link href={viewing.source_url} target="_blank" rel="noopener noreferrer">Mở liên kết nguồn</Typography.Link>}
    </Modal>
    <Modal forceRender centered open={!!editingVersion} title="Chỉnh bản nháp PDF" width={820}
      onCancel={() => { if (!saving) setEditingVersion(null); }} onOk={() => void saveDraftVersion()} confirmLoading={saving}
      okText="Lưu thay đổi" cancelText="Hủy" styles={modalStyles}>
      <Form form={draftForm} layout="vertical" disabled={saving}>
        <Form.Item name="title" label="Tên phiên bản" rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
        <Form.Item name="minimum_role" label="Ai được đọc?" rules={[{ required: true }]}><Select options={roleOptions} /></Form.Item>
        <Row gutter={16}><Col xs={12}><Form.Item name="effective_from" label="Hiệu lực từ"><Input type="date" /></Form.Item></Col><Col xs={12}><Form.Item name="effective_to" label="Hiệu lực đến"><Input type="date" /></Form.Item></Col></Row>
        <Typography.Paragraph type="secondary">Tắt “AI được dùng mục này” cho nội dung chưa ban hành hoặc chưa đủ căn cứ.</Typography.Paragraph>
        <SectionFields form={draftForm} />
      </Form>
    </Modal>
  </Space>;
}
