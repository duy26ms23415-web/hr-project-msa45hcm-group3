import { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Row, Empty, Form, Input, InputNumber, Modal, Popconfirm, Collapse, Select, Space, Switch, Table, Tabs, Tag, Typography, Upload, message } from 'antd';
import type { FormInstance } from 'antd';
import { FilePdfOutlined, PlusOutlined, DeleteOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons';
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

const roleLabels: Record<string, string> = { EMPLOYEE: 'Tất cả nhân viên', MANAGER: 'Quản lý, HR và quản trị viên', HR: 'HR và quản trị viên', ADMIN: 'Chỉ quản trị viên' };
const statusLabels: Record<string, string> = { DRAFT: 'Bản nháp', PUBLISHED: 'Đã công bố', ARCHIVED: 'Đã lưu trữ' };

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
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Document | null>(null);
  const [versionDocument, setVersionDocument] = useState<Document | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [selectedPdf, setSelectedPdf] = useState<File | null>(null);
  const [editingVersion, setEditingVersion] = useState<Version | null>(null);
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
        if (!selectedPdf) { message.error('Chọn file PDF trước.'); return; }
        const body = new FormData();
        body.append('file', selectedPdf);
        body.append('minimum_role', values.minimum_role || 'EMPLOYEE');
        const response = await api.post<{ document: Document; version: Version }>('/ai/knowledge/upload', body);
        openVersions(response.data.document);
        setPdfTab('versions');
      }
      setOpen(false);
      message.success(editing ? 'Đã lưu tài liệu.' : 'Đã tải PDF thành bản nháp. Có thể xem trước và công bố.');
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
      await api.post(`/ai/knowledge/${versionDocument.document_id}/versions`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
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
      message.success('Đã công bố phiên bản.');
      await Promise.all([loadVersions(versionDocument), load()]);
    } catch (error: any) { message.error(error.response?.data?.detail || 'Không công bố được phiên bản.'); }
    finally { setSaving(false); }
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
  const previewVersion = async (version: Version) => {
    if (!versionDocument) return;
    try {
      const sections = (await api.get<Section[]>(`/ai/knowledge/${versionDocument.document_id}/versions/${version.version_id}/sections`, { params: { preview: true } })).data;
      if (!sections.length) { message.error('Phiên bản chưa có mục để xem trước.'); return; }
      navigate(`/knowledge/view/${versionDocument.document_id}?version=${version.version_id}&section=${sections[0].section_id}&preview=true`);
    } catch { message.error('Không mở được bản xem trước.'); }
  };
  const archiveDocument = async (document: Document) => {
    try {
      await api.post(`/ai/knowledge/${document.document_id}/archive`);
      message.success('Đã lưu trữ tài liệu.');
      await load();
    } catch (error: any) { message.error(error.response?.data?.detail || 'Không lưu trữ được tài liệu.'); }
  };
  const roleOptions = ['EMPLOYEE', 'MANAGER', 'HR', ...(hasRole(['ADMIN']) ? ['ADMIN'] : [])].map(value => ({ value, label: roleLabels[value] }));
  const filtered = documents.filter(document => document.title.toLocaleLowerCase('vi-VN').includes(search.toLocaleLowerCase('vi-VN')) && (!statusFilter || document.status === statusFilter));
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
      { title: 'Thao tác', render: (_, version: Version) => version.page_count && version.status !== 'ARCHIVED' ? <Space wrap>
        <Button size="small" onClick={() => void previewVersion(version)}>Xem trước</Button>
        {version.status === 'DRAFT' && <>
          <Button size="small" loading={editorLoading} onClick={() => void editDraftVersion(version)}>Sửa nội dung nguồn</Button>
          <Popconfirm title="Công bố phiên bản đã kiểm tra?" description="AI sẽ dùng phiên bản này làm nguồn hiện hành." okText="Công bố" cancelText="Để sau" onConfirm={() => void publishVersion(version)}><Button type="primary" size="small" loading={saving}>Công bố</Button></Popconfirm>
        </>}
      </Space> : null },
    ]} />;
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <div><Typography.Title level={4} style={{ marginBottom: 8 }}>Tài liệu & chính sách</Typography.Title>
      <Typography.Text type="secondary">Quản lý nguồn nội bộ để trợ lý AI trả lời có căn cứ.</Typography.Text></div>
    <Alert type="info" showIcon title="Lưu bản nháp → kiểm tra nội dung → công bố. Chỉ tài liệu đã công bố và đúng quyền truy cập mới được AI sử dụng." />
    <Card title="Danh sách tài liệu" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => edit(null)}>Thêm tài liệu</Button>}>
      <Space wrap style={{ marginBottom: 20 }}>
        <Input.Search placeholder="Tìm theo tên tài liệu" allowClear value={search} onChange={event => setSearch(event.target.value)} style={{ width: 280 }} />
        <Select allowClear placeholder="Tất cả trạng thái" value={statusFilter} onChange={setStatusFilter} style={{ width: 180 }}
          options={Object.entries(statusLabels).map(([value, label]) => ({ value, label }))} />
      </Space>
      <Table rowKey="document_id" dataSource={filtered} loading={loading} scroll={{ x: 850 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={documents.length ? 'Không có tài liệu phù hợp bộ lọc.' : 'Chưa có tài liệu. Thêm PDF nội quy hoặc chính sách để bắt đầu.'} /> }}
        columns={[
          { title: 'Tài liệu', dataIndex: 'title', render: (value: string) => <Typography.Text strong>{value}</Typography.Text> },
          { title: 'Trạng thái', dataIndex: 'status', render: (value: string) => <Tag color={value === 'PUBLISHED' ? 'green' : 'default'}>{statusLabels[value]}</Tag> },
          { title: 'Người được đọc', dataIndex: 'minimum_role', render: (value: string) => roleLabels[value] || value },
          { title: 'Cập nhật', dataIndex: 'updated_at', render: (value: string) => new Date(value).toLocaleString('vi-VN') },
          { title: 'Thao tác', render: (_, document: Document) => <Space wrap>
            <Button disabled={document.status !== 'DRAFT'} onClick={() => edit(document)}>Sửa thông tin</Button>
            <Button icon={<FilePdfOutlined />} disabled={document.status === 'ARCHIVED'} onClick={() => openVersions(document)}>Quản lý PDF</Button>
            {document.status !== 'ARCHIVED' && <Popconfirm title="Lưu trữ tài liệu?" description="Tài liệu sẽ ngừng được AI sử dụng." onConfirm={() => void archiveDocument(document)} okText="Lưu trữ" cancelText="Hủy"><Button type="text" danger>Lưu trữ</Button></Popconfirm>}
          </Space> },
        ]} />
    </Card>
    <Modal forceRender centered open={open} title={editing ? 'Sửa thông tin tài liệu' : 'Thêm tài liệu'}
      okButtonProps={{ disabled: !editing && !selectedPdf }} onCancel={() => { if (!saving) setOpen(false); }} onOk={() => void save()} confirmLoading={saving}
      okText={editing ? "Lưu thay đổi" : "Tải lên và lưu nháp"} cancelText="Hủy" width={720} styles={modalStyles}>
      <Form form={form} layout="vertical" disabled={saving}>
        {!editing ? <>
          <Form.Item style={{ marginTop: 16 }}>{pdfPicker}</Form.Item>
          <Typography.Paragraph type="secondary">Tên tài liệu lấy từ tên file. Sau khi tải, bạn có thể xem trước và công bố bản nháp.</Typography.Paragraph>
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
    <Modal forceRender centered open={!!versionDocument} title={versionDocument ? `PDF · ${versionDocument.title}` : 'Quản lý PDF'}
      onCancel={() => { if (!saving) setVersionDocument(null); }} footer={null} width={820} styles={modalStyles}>
      <Tabs activeKey={pdfTab} onChange={setPdfTab} items={[
        { key: 'upload', label: 'Tải phiên bản mới', children: uploadPanel },
        { key: 'versions', label: `Kiểm tra & công bố (${versions.length})`, children: versionsPanel },
      ]} />
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
