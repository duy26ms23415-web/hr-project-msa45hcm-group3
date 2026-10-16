// Browser workflow check with isolated API fixtures; never uses real accounts/data.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dist = path.join(repo, 'frontend/dist');
const output = path.join(repo, 'backend/storage/tmp/knowledge-flow-check');
const candidates = [process.env.CHROME_PATH,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].filter(Boolean);
let executable;
for (const candidate of candidates) {
  try { await fs.access(candidate); executable = candidate; break; } catch { /* try next */ }
}
if (!executable) throw Error('Set CHROME_PATH to an installed Chromium browser.');
await fs.mkdir(output, { recursive: true });
let document, version;
const requests = [];
const reset = () => {
  document = { document_id: 16, title: 'Quy trình quản trị nhân sự', content: '', status: 'DRAFT', minimum_role: 'EMPLOYEE', updated_at: '2026-10-15T12:00:00Z', current_version_id: null };
  version = { version_id: 20, document_id: 16, version_number: 1, title: document.title, minimum_role: 'EMPLOYEE', status: 'DRAFT', page_count: 2, byte_size: 1000, created_at: document.updated_at, effective_from: null, effective_to: null };
  requests.length = 0;
};
const sections = [{ section_id: 3, section_code: 'SECTION_1', heading: 'Quy định nhân sự', page_start: 1, page_end: 2, is_answerable: true }];
const server = http.createServer(async (req, res) => {
  const json = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)); };
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname === '/api/v1/auth/me') return json({ user_account_id: 9, employee_id: 7, login_email: 'fixture@example.test', roles: ['ADMIN', 'HR'], is_active: true });
    if (req.method !== 'GET' && url.pathname.startsWith('/api/')) {
      let body = ''; for await (const chunk of req) body += chunk;
      const payload = body ? JSON.parse(body) : null;
      requests.push({ method: req.method, path: url.pathname, payload });
      if (url.pathname.endsWith('/access')) {
        // A failed save must keep the editor open and preserve the old table value.
        if (payload.minimum_role === 'MANAGER') return json({ message: 'Không thể lưu quyền trong lần thử này.' }, 503);
        document.minimum_role = version.minimum_role = payload.minimum_role;
        return json(document);
      }
      if (req.method === 'PUT' && url.pathname.endsWith('/versions/20')) { Object.assign(version, payload); return json(version); }
      if (url.pathname.endsWith('/publish')) {
        version.status = document.status = 'PUBLISHED';
        document.current_version_id = version.version_id;
        document.title = version.title;
        return json(version);
      }
      return json({ detail: 'Unexpected mutation' }, 400);
    }
    if (url.pathname === '/api/v1/ai/knowledge') return json([document]);
    if (url.pathname.endsWith('/versions')) return json([version]);
    if (url.pathname.endsWith('/sections')) return json(sections);
    if (url.pathname.startsWith('/api/')) return json([]);
    if (url.pathname.startsWith('/assets/')) {
      const filename = path.resolve(dist, '.' + url.pathname);
      if (!filename.startsWith(dist + path.sep)) return res.writeHead(404).end();
      res.writeHead(200, { 'Content-Type': ({ '.js': 'text/javascript', '.css': 'text/css' })[path.extname(filename)] || 'application/octet-stream' });
      return res.end(await fs.readFile(filename));
    }
    const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(html.replace('</head>', '<script>localStorage.setItem("access_token","knowledge-fixture")</script></head>'));
  } catch (error) { console.error(error.message); res.writeHead(500).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  for (const [name, width, height] of [['desktop', 1440, 1000], ['compact', 768, 900]]) {
    reset();
    const profile = path.join(output, `profile-${name}-${Date.now()}`);
    const browser = spawn(executable, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
    const timeout = setTimeout(() => browser.kill(), 45000);
    let socket;
    try {
      let port;
      for (let i = 0; i < 100; i++) {
        try { port = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch { await pause(50); }
      }
      if (!port) throw Error('Browser debugging endpoint unavailable');
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
      await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
      let sequence = 0;
      const pending = new Map();
      socket.addEventListener('message', event => {
        const value = JSON.parse(event.data), handler = pending.get(value.id);
        if (handler) { pending.delete(value.id); value.error ? handler.reject(Error(value.error.message)) : handler.resolve(value.result); }
      });
      const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
      const evaluate = async expression => {
        const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
        return result.result.value;
      };
      const until = async expression => {
        for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await pause(100); }
        const image = await send('Page.captureScreenshot', { format: 'png' });
        await fs.writeFile(path.join(output, `${name}-failure.png`), Buffer.from(image.data, 'base64'));
        throw Error(`UI timeout: ${expression}; requests=${JSON.stringify(requests)}`);
      };
      const click = async expression => {
        await pause(300); // Let modal/dropdown transitions finish before pointer input.
        const rect = await evaluate(`(() => { const e=${expression}; e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()`);
        await send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, ...rect });
        await send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, ...rect });
      };
      const button = text => `Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)} && b.getBoundingClientRect().width>0)`;
      const visibleModals = `Array.from(document.querySelectorAll('.ant-modal-wrap')).filter(e=>getComputedStyle(e).display!=='none').length`;
      const shot = async suffix => { const image = await send('Page.captureScreenshot', { format: 'png' }); await fs.writeFile(path.join(output, `${name}-${suffix}.png`), Buffer.from(image.data, 'base64')); };
      await send('Page.enable');
      await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
      await send('Page.navigate', { url: origin + '/knowledge' });
      await until(`!!document.querySelector('button[title="Sửa người được đọc"]')`);
      await shot('list');
      await click(`document.querySelector('button[title="Sửa người được đọc"]')`);
      await until(`${visibleModals}===1`);
      await pause(300);
      const chooseRole = async label => {
        await click(`document.querySelector('.ant-modal-wrap:not([style*="display: none"]) .ant-select')`);
        const option = `Array.from(document.querySelectorAll('.ant-select-item-option')).find(e=>e.textContent===${JSON.stringify(label)})`;
        await until(`!!(${option})`); await pause(200); await click(option);
        await until(`document.querySelector('.ant-modal .ant-select').textContent.includes(${JSON.stringify(label)})`);
        await pause(250);
      };
      await chooseRole('Quản lý, HR và quản trị viên');
      await click(button('Lưu thay đổi'));
      await until(`document.body.textContent.includes('Không thể lưu quyền trong lần thử này.')`);
      assert.equal(await evaluate(visibleModals), 1);
      assert.equal(document.minimum_role, 'EMPLOYEE');
      await chooseRole('HR và quản trị viên');
      await click(button('Lưu thay đổi'));
      await until(`${visibleModals}===0`);
      assert.equal(document.minimum_role, 'HR');
      assert.deepEqual(requests.at(-1).payload, { minimum_role: 'HR' });
      await click(button('Kiểm tra & công bố'));
      await until(`!!(${button('Chỉnh sửa')})`);
      assert.equal(await evaluate(visibleModals), 1);
      await click(button('Chỉnh sửa'));
      await until(`!!document.querySelector('input[id$="title"]') && !!(${button('Quay lại')})`);
      assert.equal(await evaluate(visibleModals), 1, 'Editing must not stack another modal');
      await evaluate(`(() => { const e=Array.from(document.querySelectorAll('.ant-modal input')).find(e=>e.id.endsWith('title') && e.getBoundingClientRect().width>0); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'Quy trình nhân sự đã chỉnh'); e.dispatchEvent(new Event('input',{bubbles:true})); })()`);
      await pause(100);
      await click(button('Lưu thay đổi'));
      await until(`!!(${button('Công bố')}) && document.body.textContent.includes('Quy trình nhân sự đã chỉnh')`);
      assert.equal(version.title, 'Quy trình nhân sự đã chỉnh');
      assert.equal(version.minimum_role, 'HR');
      assert.equal(await evaluate(visibleModals), 1);
      await shot('review');
      await click(button('Công bố'));
      await until(`${visibleModals}===0`);
      assert.equal(document.status, 'PUBLISHED');
      assert.equal(requests.filter(r=>r.path.endsWith('/publish')).length, 1);
      await until(`document.querySelector('.ant-table-tbody').textContent.includes('Đã công bố')`);
      await shot('published');
      console.log(`PASS ${name}: failed/successful access save, single-panel edit/review, publish and table refresh`);
      socket.send(JSON.stringify({ id: ++sequence, method: 'Browser.close' }));
      await pause(100);
    } finally { clearTimeout(timeout); socket?.close(); if (browser.exitCode === null) browser.kill(); }
  }
  console.log('Local API fixtures only; live database writes were not exercised.');
} finally { server.close(); }
