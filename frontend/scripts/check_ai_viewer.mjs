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
const output = path.join(repo, 'backend/.pytest-ai-validation-20261007-batch1/browser');
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const manifest = JSON.parse(await fs.readFile(path.join(pdfRoot, 'manifest.json'), 'utf8'));
await fs.access(edge);
await fs.mkdir(output, { recursive: true });
const requests = [];
const contentTypes = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.html': 'text/html' };
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://127.0.0.1');
    const json = (status, value) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'private, no-store' }); res.end(JSON.stringify(value)); };
    if (url.pathname.startsWith('/api/')) {
      if (req.headers.authorization !== 'Bearer local-browser-fixture') return json(401, { message: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để tiếp tục.' });
      requests.push(req.url);
      if (url.pathname === '/api/v1/auth/me') return json(200, { user_account_id: 9, employee_id: 7, login_email: 'employee@example.test', is_active: true, roles: ['EMPLOYEE'] });
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
  for (const [name, documentId, sectionId] of [['leave', 1, 2], ['attendance', 2, 3], ['report', 3, 2], ['denied', 99, 2]]) {
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
        if (handler) { pending.delete(value.id); value.error ? handler.reject(new Error(value.error.message)) : handler.resolve(value.result); }
      });
      const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
      await send('Page.enable');
      await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1200, deviceScaleFactor: 1, mobile: false });
      await send('Page.navigate', { url: `http://127.0.0.1:${port}/knowledge/view/${documentId}?version=1&section=${sectionId}` });
      const expected = name === 'denied' ? 'Tài liệu không còn khả dụng' : 'aria-label="Mục được trích dẫn"';
      let dom = '';
      for (let attempt = 0; attempt < 150; attempt++) {
        const result = await send('Runtime.evaluate', { expression: 'document.documentElement.outerHTML', returnByValue: true });
        dom = result.result.value || '';
        if (dom.includes(expected)) break;
        await pause(100);
      }
      await fs.writeFile(path.join(output, name + '.html'), dom);
      const screenshot = await send('Page.captureScreenshot', { format: 'png' });
      await fs.writeFile(path.join(output, name + '.png'), Buffer.from(screenshot.data, 'base64'));
      if (!dom.includes(expected)) throw new Error(`Viewer ${name} did not render the expected state; inspect its local artifacts.`);
      console.log(`PASS ${name}: real React viewer, local API fixture, screenshot saved.`);
      socket.send(JSON.stringify({ id: ++sequence, method: 'Browser.close' }));
      await pause(100);
    } finally {
      clearTimeout(timeout);
      socket?.close();
      if (browser.exitCode === null) browser.kill();
    }
  }
  if (requests.some(url => /token=|local-browser-fixture/.test(url))) throw new Error('Token found in request URL.');
  console.log('API fixture verification only; PostgreSQL authorization and browser interaction flows remain unverified.');
} finally { server.close(); }
