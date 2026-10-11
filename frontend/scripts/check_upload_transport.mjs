import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

// Exercise the real client/interceptors against a local HTTP receiver, without DB or JWT.
const source = await readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
  .replace("from 'axios'", `from '${import.meta.resolve('axios')}'`);
globalThis.localStorage = { getItem: () => null };
globalThis.window = { location: { pathname: '/knowledge' } };
const { default: api } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const requests = [];
const server = createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  requests.push({ contentType: req.headers['content-type'], body: Buffer.concat(chunks).toString() });
  res.writeHead(201, { 'Content-Type': 'application/json' });
  res.end('{}');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
try {
  api.defaults.baseURL = `http://127.0.0.1:${server.address().port}`;
  api.defaults.adapter = 'fetch';
  for (const explicitHeader of [false, true]) {
    const body = new FormData();
    body.append('file', new File(['%PDF-test'], 'policy.pdf', { type: 'application/pdf' }));
    body.append('minimum_role', 'EMPLOYEE');
    await api.post('/ai/knowledge/upload', body, explicitHeader ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined);
    const request = requests.at(-1);
    assert.match(request.contentType, /^multipart\/form-data; boundary=/);
    assert.match(request.body, /name="file"; filename="policy.pdf"/);
    assert.match(request.body, /%PDF-test/);
    assert.match(request.body, /EMPLOYEE/);
  }
  await api.post('/json', { title: 'Policy' });
  assert.match(requests.at(-1).contentType, /^application\/json/);
  assert.equal(JSON.parse(requests.at(-1).body).title, 'Policy');
  console.log('PASS: multipart files reach transport with boundary; JSON requests remain JSON.');
} finally {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
