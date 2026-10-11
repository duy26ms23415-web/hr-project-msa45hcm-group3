// Invoked by backend/scripts/check_leave_integration.py with a disposable DB.
// Serves the existing build and proxies every API request to the real backend.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, execFile } from 'node:child_process';
import assert from 'node:assert/strict';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dist = path.join(repo, 'frontend/dist');
const output = path.resolve(process.env.HR_LEAVE_CHECK_OUTPUT || '');
assert(output.startsWith(path.join(repo, 'backend/storage/tmp/hr_leave_check_')));
const backend = new URL(process.env.HR_LEAVE_CHECK_API);
assert.equal(backend.hostname, '127.0.0.1');
const password = process.env.HR_LEAVE_CHECK_PASSWORD;
const dates = JSON.parse(process.env.HR_LEAVE_CHECK_DATES);
assert(password && dates.length === 2);
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
await fs.access(edge);
await fs.access(path.join(dist, 'index.html'));
const requests = [];
const created = [];
const reviews = [];
const contentTypes = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/')) {
    const upstream = http.request(new URL(req.url, backend), { method: req.method, headers: req.headers }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => {
        const body = Buffer.concat(chunks);
        requests.push({ method: req.method, path: req.url, status: response.statusCode });
        if (req.method === 'POST' && response.statusCode < 300) {
          if (url.pathname === '/api/v1/leaves/requests') created.push(JSON.parse(body));
          if (/\/leaves\/requests\/\d+\/review$/.test(url.pathname)) reviews.push(JSON.parse(body));
        }
        res.writeHead(response.statusCode, response.headers);
        res.end(body);
      });
    });
    upstream.on('error', () => res.writeHead(502).end());
    req.pipe(upstream);
    return;
  }
  try {
    const filename = url.pathname.startsWith('/assets/') ? path.resolve(dist, '.' + url.pathname) : path.join(dist, 'index.html');
    assert(filename.startsWith(dist + path.sep));
    res.writeHead(200, { 'Content-Type': contentTypes[path.extname(filename)] || 'text/html' });
    res.end(await fs.readFile(filename));
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const profile = await fs.mkdtemp(path.join(output, 'profile-'));
const browser = spawn(edge, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let socket;
let phase = 'start';
let captureFailure;
try {
  let debugPort;
  for (let i = 0; i < 100; i++) {
    try { debugPort = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch { await pause(50); }
  }
  assert(debugPort, 'Edge debugging endpoint did not start');
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
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 10000);
    pending.set(id, { resolve: result => { clearTimeout(timer); resolve(result); }, reject: error => { clearTimeout(timer); reject(error); } });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(`Browser evaluation failed during ${phase}`);
    return result.result.value;
  };
  const until = async (expression, description) => {
    for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await pause(100); }
    throw new Error(`UI timeout: ${description}`);
  };
  const click = async label => {
    const labelJSON = JSON.stringify(label);
    await until(`Array.from(document.querySelectorAll('button,[role="tab"]')).some(e => e.getClientRects().length && e.textContent.trim() === ${labelJSON})`, label);
    await evaluate(`Array.from(document.querySelectorAll('button,[role="tab"]')).find(e => e.getClientRects().length && e.textContent.trim() === ${labelJSON}).click()`);
  };
  const fill = async (selector, value) => {
    await evaluate(`(() => { const e=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set; setter.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); })()`);
  };
  const pointerClick = async selector => {
    const point = await evaluate(`(() => {const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 });
  };
  const screenshot = async name => {
    const result = await send('Page.captureScreenshot', { format: 'png' });
    await fs.writeFile(path.join(output, name + '.png'), Buffer.from(result.data, 'base64'));
  };
  captureFailure = async () => {
    if (phase.startsWith('login-')) return {};
    await screenshot('ui-failure');
    return evaluate(`({errors:Array.from(document.querySelectorAll('.ant-form-item-explain-error')).map(e=>e.textContent), date:document.querySelector('#leave_date')?.value, leaveType:document.querySelector('.ant-modal .ant-select-selection-item')?.textContent})`);
  };
  const login = async role => {
    phase = `login-${role}`;
    await evaluate(`if (location.origin === ${JSON.stringify(origin)}) localStorage.clear()`);
    await send('Page.navigate', { url: origin + '/login' });
    await until('!!document.querySelector("#email")', 'login form');
    await fill('#email', role + '@leave-check.example');
    await fill('#pass', password);
    await evaluate('document.querySelector("button[type=submit]").click()');
    await until('location.pathname === "/dashboard"', 'authenticated dashboard');
    await send('Page.navigate', { url: origin + '/leaves' });
    await until('Array.from(document.querySelectorAll("button")).some(e=>e.textContent.includes("Tạo đơn xin nghỉ / Remote"))', 'leave page');
  };
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await login('staff');
  await until(`!!document.querySelector('button') && document.body.innerText.includes('Tổng tiêu chuẩn phép năm')`, 'balance rendered');
  for (let i = 0; i < 2; i++) {
    phase = `submit-${i}`;
    await click('Tạo đơn xin nghỉ / Remote');
    await until('!!document.querySelector("#reason") && !!document.querySelector("#leave_date")', 'leave form');
    await pointerClick('.ant-modal .ant-select');
    await until(`Array.from(document.querySelectorAll('.ant-select-item-option')).some(e=>e.getClientRects().length && e.textContent.includes('Nghỉ phép năm'))`, 'annual leave option');
    await evaluate(`Array.from(document.querySelectorAll('.ant-select-item-option')).find(e=>e.getClientRects().length && e.textContent.includes('Nghỉ phép năm')).click()`);
    await evaluate('document.querySelector("#leave_date").focus()');
    await fill('#leave_date', dates[i]);
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await fill('#reason', 'UI integration ' + i);
    await click('Gửi đơn xin nghỉ');
    for (let attempt = 0; attempt < 100 && created.length < i + 1; attempt++) await pause(100);
    assert.equal(created.length, i + 1, 'UI submission did not reach the real API');
    assert.equal(created[i].status, 'PENDING');
    assert.equal(created[i].leave_date, dates[i]);
    await until(`document.body.innerText.includes('UI integration ${i}') && !Array.from(document.querySelectorAll('.ant-modal')).some(e => e.getClientRects().length)`, 'submitted request in employee list');
  }
  await screenshot('employee-submitted');
  await login('manager');
  await until('Array.from(document.querySelectorAll("[role=tab]")).some(e=>e.textContent.includes("Duyệt đơn nghỉ phép"))', 'manager approval tab');
  await evaluate('Array.from(document.querySelectorAll("[role=tab]")).find(e=>e.textContent.includes("Duyệt đơn nghỉ phép")).click()');
  for (const [i, action, confirm, expected] of [[0, 'Duyệt', 'Xác nhận duyệt', 'APPROVED'], [1, 'Từ chối', 'Xác nhận từ chối', 'REJECTED']]) {
    phase = `review-${expected}`;
    await until(`Array.from(document.querySelectorAll('tr')).some(e=>e.innerText.includes('UI integration ${i}'))`, 'pending request for manager');
    await evaluate(`(() => {const row=Array.from(document.querySelectorAll('tr')).find(e=>e.innerText.includes('UI integration ${i}')); Array.from(row.querySelectorAll('button')).find(e=>e.textContent.trim()===${JSON.stringify(action)}).click();})()`);
    await click(confirm);
    for (let attempt = 0; attempt < 100 && reviews.length < i + 1; attempt++) await pause(100);
    assert.equal(reviews.length, i + 1);
    assert.equal(reviews[i].leave_request_id, created[i].leave_request_id);
    assert.equal(reviews[i].status, expected);
    await until(`!Array.from(document.querySelectorAll('tr')).some(e=>e.innerText.includes('UI integration ${i}') && e.getClientRects().length)`, 'reviewed request removed from approval queue');
  }
  await screenshot('manager-reviewed');
  await login('staff');
  phase = 'employee-result';
  await until('Array.from(document.querySelectorAll("tr")).filter(e=>e.innerText.includes("UI integration")).length === 2', 'employee final list');
  const rows = await evaluate('Array.from(document.querySelectorAll("tr")).filter(e=>e.innerText.includes("UI integration")).map(e=>e.innerText)');
  assert(rows.find(e => e.includes('UI integration 0')).includes('APPROVED'));
  assert(rows.find(e => e.includes('UI integration 1')).includes('REJECTED'));
  await screenshot('employee-reviewed');
  assert(requests.filter(r => r.path.startsWith('/api/v1/leaves')).every(r => r.status < 400));
  assert(requests.some(r => r.path === '/api/v1/leaves/balances/me' && r.status === 200));
  await fs.writeFile(path.join(output, 'browser-result.json'), JSON.stringify({ passed: true, requests, created: created.map(r => r.leave_request_id), reviews: reviews.map(r => ({ id: r.leave_request_id, status: r.status })) }, null, 2));
  console.log('PASS: Edge UI -> real HTTP backend -> PostgreSQL; submit, approve, reject and employee status refresh');
} catch (error) {
  const ui = await captureFailure?.().catch(() => ({}));
  await fs.writeFile(path.join(output, 'browser-failure.json'), JSON.stringify({ phase, requests, ui }, null, 2));
  // Avoid recording login inputs or authentication tokens in failure artifacts.
  throw error;
} finally {
  socket?.close();
  if (browser.exitCode === null) await new Promise(resolve => execFile('taskkill', ['/PID', String(browser.pid), '/T', '/F'], { windowsHide: true }, () => resolve()));
  await new Promise(resolve => server.close(resolve));
  assert(path.resolve(profile).startsWith(output + path.sep + 'profile-'));
  await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
