// Browser verification with local API fixtures, never a production fallback.
// Uses the existing build, shipped PDFs and installed Edge; no dependencies.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dist = path.join(repo, 'frontend/dist');
const pdfRoot = path.join(repo, 'backend/storage/tmp/ai-knowledge-demo');
const output = path.join(repo, 'backend/storage/tmp/chat-report-check');
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const manifest = { documents: [] };
await fs.access(edge);
await fs.mkdir(output, { recursive: true });
const requests = [];
const chatBodies = [];
const contentTypes = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.html': 'text/html' };
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const json = (status, value) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' }); res.end(JSON.stringify(value)); };
    if (url.pathname.startsWith('/api/')) {
      if (req.headers.authorization !== 'Bearer local-browser-fixture') return json(401, { message: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.' });
      requests.push(req.url);
      if (url.pathname === '/api/v1/auth/me') return json(200, { user_account_id: 9, employee_id: 7, login_email: 'manager@example.test', is_active: true, roles: ['MANAGER'] });
      if (url.pathname === '/api/v1/ai/chat') {
        let body = ''; for await (const chunk of req) body += chunk;
        chatBodies.push(JSON.parse(body));
        return json(200, { reply: 'Đã tạo báo cáo công.',
          action: { action_type: 'OPEN_REPORT', data: { kind: 'ATTENDANCE', scope: 'SELF',
            start_date: '2026-10-01', end_date: '2026-10-08', run_id: (chatBodies.at(-1).report_run_id ? 'b' : 'a').repeat(32) } },
          sources: [], answer_mode: 'RULE', status: 'OK' });
      }
      if (['a', 'b'].some(id => url.pathname === '/api/v1/reports/runs/' + id.repeat(32))) return json(200, {
        run: { run_id: url.pathname.split('/').at(-1), kind: 'ATTENDANCE', scope: 'SELF', status: 'READY' },
        report: { kind: 'ATTENDANCE', start_date: '2026-10-01', end_date: '2026-10-08', note: 'Dữ liệu đã ghi nhận',
          rows: [{ employee_code:'E07', full_name:'Nhân viên mẫu', recorded_days:6, present_days:5, incomplete_days:1, absent_days:0, worked_minutes:2400 }] },
        total_rows: url.pathname.endsWith('a'.repeat(32)) ? 120 : 1,
      });
      if (url.pathname === '/api/v1/ai/suggestions') return json(200, Array.from({ length: 12 }, (_, i) => ({
        suggestion_id: 'test-' + i, prompt: 'Câu hỏi gợi ý về phép và chấm công ' + i, catalog_version: 'v1',
      })));
      const match = url.pathname.match(/^\/api\/v1\/ai\/knowledge\/(\d+)\/versions\/1\/(?:sections\/(\d+)|file)$/);
      if (!match) return json(404, { message: 'Tài liệu không còn khả dụng hoặc bạn không có quyền truy cập.' });
      const id = Number(match[1]);
      if (id === 99) return json(404, { code: 'DOCUMENT_UNAVAILABLE', message: 'Tài liệu không còn khả dụng hoặc bạn không có quyền truy cập.' });
      const document = manifest.documents[id - 1];
      if (!document) return json(404, {});
      if (match[2]) {
        const section = document.sections[Number(match[2]) - 1];
        if (!section) return json(404, {});
        return json(200, { document_id: id, version_id: 1, section_id: Number(match[2]), title: document.title, anchor: section.heading, ...section });
      }
      res.writeHead(200, { 'Content-Type': 'application/pdf', 'Cache-Control': 'private, no-store' });
      return res.end(await fs.readFile(path.join(pdfRoot, document.file)));
    }
    if (url.pathname.startsWith('/assets/')) {
      const filename = path.resolve(dist, '.' + url.pathname);
      if (!filename.startsWith(dist + path.sep)) return res.writeHead(404).end();
      res.writeHead(200, { 'Content-Type': contentTypes[path.extname(filename)] || 'application/octet-stream' });
      return res.end(await fs.readFile(filename));
    }
    const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(html.replace('</head>', '<script>localStorage.setItem("access_token","local-browser-fixture")</script></head>'));
  } catch { res.writeHead(500).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  for (const [name, width, height] of [['desktop', 1280, 720], ['short', 1024, 600], ['compact', 1280, 480]]) {
    const documentId = 99, sectionId = 2;
    const profile = path.join(output, `profile-${name}-${Date.now()}`);
    const browser = spawn(edge, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
    browser.stderr.on('data', () => {});
    const timeout = setTimeout(() => browser.kill(), 25000);
    let socket;
    try {
      let debugPort;
      for (let attempt = 0; attempt < 100; attempt++) {
        try { debugPort = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch { await pause(50); }
      }
      if (!debugPort) throw new Error('Edge debugging endpoint did not start.');
      const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
      socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
      await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
      let sequence = 0;
      const pending = new Map();
      socket.addEventListener('message', event => {
        const value = JSON.parse(event.data);
        const handler = pending.get(value.id);
        if (handler) { pending.delete(value.id); if (value.error) handler.reject(new Error(value.error.message)); else handler.resolve(value.result); }
      });
      const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
      await send('Page.enable');
      await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
      await send('Page.navigate', { url: `http://127.0.0.1:${port}/knowledge/view/${documentId}?version=1&section=${sectionId}` });
      const expected = 'Tài liệu không còn khả dụng';
      let dom = '';
      for (let attempt = 0; attempt < 150; attempt++) {
        const result = await send('Runtime.evaluate', { expression: 'document.documentElement.outerHTML', returnByValue: true });
        dom = result.result.value || '';
        if (dom.includes(expected)) break;
        await pause(100);
      }
      await send('Runtime.evaluate', { expression: "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Hỏi AI Assistant')).click()" });
      await pause(500);
      await send('Runtime.evaluate', { expression:"Array.from(document.querySelectorAll('.ant-modal button')).find(b=>b.textContent.includes('Gợi ý câu hỏi')).click()" });
      await pause(150);
      await send('Runtime.evaluate', { expression:"Array.from(document.querySelectorAll('.ant-dropdown-menu-item')).find(b=>b.textContent.includes('Câu hỏi gợi ý')).click()" });
      await pause(400);
      const preview = await send('Runtime.evaluate', { returnByValue:true, expression: "document.body.innerText.includes('Tải Excel') && document.body.innerText.includes('E07')" });
      if (!preview.result.value) throw new Error('Inline report preview did not load.');
      await send('Runtime.evaluate', { expression: "document.querySelector('.ant-pagination-item-3').click()" });
      await pause(300);
      if (!requests.some(url => url.includes('/reports/runs/' + 'a'.repeat(32)) && url.includes('offset=100'))) throw new Error('Third report page was not requested.');
      const tableBounds = await send('Runtime.evaluate', { returnByValue:true, expression: "Array.from(document.querySelectorAll('.ant-modal')).filter(x=>x.offsetWidth).map(x=>{const r=x.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right}})" });
      if (tableBounds.result.value.some(r=>r.top<0 || r.bottom>height || r.left<0 || r.right>width)) throw new Error('Preview exceeds viewport: '+JSON.stringify(tableBounds.result.value));
      await send('Runtime.evaluate', { expression: "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Chỉnh qua chat')).click()" });
      await pause(300);
      await send('Runtime.evaluate', { expression: "(() => {const x=document.querySelector('.ant-modal textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(x,'đổi sang tháng trước');x.dispatchEvent(new Event('input',{bubbles:true}));})()" });
      await pause(100);
      await send('Runtime.evaluate', { expression: "Array.from(document.querySelectorAll('.ant-modal button')).find(b=>b.textContent.trim()==='Gửi').click()" });
      await pause(400);
      if (chatBodies.at(-1)?.report_run_id !== 'a'.repeat(32)) throw new Error('Report edit context missing from request.');
      const revisedRequests = requests.filter(url => url.includes('/reports/runs/' + 'b'.repeat(32)));
      if (!revisedRequests.length || revisedRequests.some(url => !url.includes('offset=0'))) throw new Error('New report inherited the old pagination offset.');
      const revisedPreview = await send('Runtime.evaluate', { returnByValue:true, expression: "document.body.innerText.includes('E07') && !!document.querySelector('.ant-pagination-item-1.ant-pagination-item-active')" });
      if (!revisedPreview.result.value) throw new Error('New report did not start on its first page.');
      await send('Runtime.evaluate', { expression: "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Chỉnh qua chat')).click()" });
      await pause(250);
      const layout = await send('Runtime.evaluate', { returnByValue: true, expression: `(() => {
        const modal = document.querySelector('.ant-modal-container') || document.querySelector('.ant-modal-content');
        const input = document.querySelector('.ant-modal textarea');
        const username = document.querySelector('[title="manager@example.test"]');
        const rect = el => { const r = el.getBoundingClientRect(); return { top:r.top,bottom:r.bottom,left:r.left,right:r.right }; };
        return { modal:rect(modal), input:rect(input), username:rect(username), height:innerHeight, width:innerWidth };
      })()` });
      const bounds = layout.result.value;
      if (!bounds || bounds.modal.top < 0 || bounds.modal.bottom > height || bounds.input.bottom > height || bounds.username.top < 0 || bounds.username.bottom > 64) {
        throw new Error('Layout out of viewport: ' + JSON.stringify(bounds));
      }
      console.log('PASS ' + name + ': modal, input and account name fit viewport ' + width + 'x' + height);
      await fs.writeFile(path.join(output, name + '.html'), dom);
      const screenshot = await send('Page.captureScreenshot', { format: 'png' });
      await fs.writeFile(path.join(output, name + '.png'), Buffer.from(screenshot.data, 'base64'));
      if (!dom.includes(expected)) throw new Error(`Viewer ${name} did not render the expected state; inspect its local artifacts.`);

      socket.send(JSON.stringify({ id: ++sequence, method: 'Browser.close' }));
      await pause(100);
    } finally {
      clearTimeout(timeout);
      socket?.close();
      if (browser.exitCode === null) browser.kill();
    }
  }
  if (requests.some(url => /token=|local-browser-fixture/.test(url))) throw new Error('Token found in request URL.');
  console.log('Report preview and editing checked with local fixtures; backend integration is not exercised.');
} finally { server.close(); }
