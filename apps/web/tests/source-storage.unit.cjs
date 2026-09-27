const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const ts = require('typescript');
const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/server/source-storage.ts'), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
const id = 'a'.repeat(64);
async function fixture(handler, check) {
 const server = http.createServer(handler);
 await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
 const base = 'http://127.0.0.1:' + server.address().port;
 const calls = [], exports = {};
 const wrappedFetch = async (url, init) => {
  if (String(url).startsWith('https://identity.test/')) return Response.json({access_token:'test-only',expires_on:Date.now()/1000+3600});
  calls.push({url, init});
  return fetch(base + '/blob', init);
 };
 new Function('exports','require','fetch','process','setTimeout','clearTimeout',source)(exports,()=>({}),wrappedFetch,{env:{SOURCE_STORAGE_ACCOUNT:'teststorage',IDENTITY_ENDPOINT:'https://identity.test/token',IDENTITY_HEADER:'test-only'}},(fn, ms)=>setTimeout(fn,ms===20000?25:ms===60000?250:ms),clearTimeout);
 try { await check(exports.sourceBlob, calls); }
 finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
test('stream finishes after header timeout without buffering or altering original bytes', async () => {
 await fixture((req,res)=>{res.writeHead(200, {'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','Content-Length':'6','ETag':'"original"'});res.flushHeaders();res.write(Buffer.from([0,1,255]));setTimeout(()=>res.end(Buffer.from([2,3,254])),85);},async sourceBlob=>{
  const response=await sourceBlob(id,'xlsx',null); assert.ok(response);assert.equal(response.headers.get('content-length'),'6'); assert.equal(response.headers.get('etag'),'"original"');
  const reader=response.body.getReader(); const first=await reader.read(); assert.deepEqual([...first.value],[0,1,255]);
  const second=await reader.read(); assert.deepEqual([...second.value],[2,3,254]); assert.equal((await reader.read()).done,true);
 });
});
test('range status, headers and exact partial bytes survive wrapping',async()=>{
 await fixture((req,res)=>{assert.equal(req.headers.range,'bytes=2-4');res.writeHead(206,{'Content-Range':'bytes 2-4/6','Content-Length':'3'});res.end('cde');},async sourceBlob=>{const r=await sourceBlob(id,'pdf','bytes=2-4');assert.equal(r.status,206);assert.equal(r.headers.get('content-range'),'bytes 2-4/6');assert.equal(await r.text(),'cde');});
});
test('cancelled downstream reader aborts the upstream fetch',async()=>{
 await fixture((req,res)=>{res.writeHead(200);res.flushHeaders();res.write('start');},async(sourceBlob,calls)=>{const r=await sourceBlob(id,'xlsx',null);const reader=r.body.getReader();assert.equal(new TextDecoder().decode((await reader.read()).value),'start');await reader.cancel('client left');assert.equal(calls[0].init.signal.aborted,true);});
});
test('missing headers are bounded and retain the existing null fallback',async()=>{
 await fixture((req,res)=>{setTimeout(()=>res.end('late'),100);},async sourceBlob=>{assert.equal(await sourceBlob(id,'xlsx',null),null);});
});
test('a stalled body read errors instead of silently returning a truncated file',async()=>{
 await fixture((req,res)=>{res.writeHead(200);res.flushHeaders();res.write('first');},async sourceBlob=>{const r=await sourceBlob(id,'xlsx',null);await assert.rejects(r.arrayBuffer());});
});
test('non-success source responses retain null fallback and invalid range is not forwarded',async()=>{
 await fixture((req,res)=>{assert.equal(req.headers.range,undefined);res.writeHead(404);res.end('missing');},async sourceBlob=>{assert.equal(await sourceBlob(id,'xlsx','bytes=0-2,4-6'),null);});
});
