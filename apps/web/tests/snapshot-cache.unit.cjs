const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/lib/server/snapshot-cache.ts'), 'utf8').replace('import "server-only";', '');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const context = { exports: {}, Date, Map, Error, Promise };
vm.runInNewContext(output, context);
const { snapshotCache } = context.exports;
test('concurrent readers share one completed snapshot', async () => {
  const cached = snapshotCache(); let reads = 0, release;
  const gate = new Promise((resolve) => { release = resolve; });
  const read = async () => { reads++; await gate; return { price: 2105000 }; };
  const requests = Array.from({ length: 30 }, () => cached('same', read)); release();
  const values = await Promise.all(requests);
  assert.equal(reads, 1); assert.ok(values.every((value) => value === values[0]));
  assert.equal(await cached('same', read), values[0]); assert.equal(reads, 1);
});
test('failed reads are retried and expired values are refreshed', async () => {
  const cached = snapshotCache(0); let reads = 0;
  const read = async () => { if (++reads === 1) throw new Error('temporary DB outage'); return reads; };
  await assert.rejects(cached('same', read), /temporary DB outage/);
  assert.equal(await cached('same', read), 2); assert.equal(await cached('same', read), 3);
});
test('pending work and stored snapshots stay bounded', async () => {
  const cached = snapshotCache(300000, 1); let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const first = cached('first', async () => { await gate; return 1; });
  await assert.rejects(cached('second', async () => 2), /SNAPSHOT_BUSY/); release();
  assert.equal(await first, 1); assert.equal(await cached('second', async () => 2), 2);
  assert.equal(await cached('first', async () => 3), 3);
});
