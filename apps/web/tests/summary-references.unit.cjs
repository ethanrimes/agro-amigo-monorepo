const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

test('catalog and detail bundles share monthly summaries, then see the next source revision after expiry', async () => {
  const sharedGlobal = {};
  let clock = 1000, reads = 0, price = 3500, release;
  class Clock extends Date { static now() { return clock; } }
  const gate = new Promise(resolve => { release = resolve; });
  const db = { query: async sql => {
    reads++;
    if (sql === 'SELECT id,name FROM product') return { rows: [{id:'lulo',name:'Lulo'}] };
    await gate;
    return { rows: [{ product_name:'Lulo', market_name:'Bogotá', unit:'kg', observed_on:'2026-08-31', price,
      change_percent:2, document_id:'original-v1', source_locator:'Hoja1!B5', source_url:'https://www.dane.gov.co/original.xlsx', details:{} }] };
  }};
  const output = name => ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/server', name), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const snapshotOutput = output('snapshot-cache.ts'), summaryOutput = output('summary-references.ts');
  const bundle = () => {
    const snapshots = { exports:{}, Date:Clock, Map, Error, Promise, globalThis:sharedGlobal, require:()=>({}) };
    vm.runInNewContext(snapshotOutput, snapshots);
    const summaries = { exports:{}, Map, Date:Clock, require: name => {
      if (name === 'server-only') return {};
      if (name === 'node:crypto') return require(name);
      if (name === './db') return { database:()=>db };
      if (name === './snapshot-cache') return snapshots.exports;
      throw new Error('Unexpected import '+name);
    }};
    vm.runInNewContext(summaryOutput, summaries);
    return summaries.exports;
  };
  const catalog = bundle(), detail = bundle();
  const a = catalog.latestSummaryReferences(), b = detail.latestSummaryReferences();
  release();
  const [first, second] = await Promise.all([a,b]);
  assert.equal(reads,2); assert.equal(first,second);
  assert.equal(first[0].canonical_product_id,'lulo'); assert.equal(first[0].price,3500);
  price=3600;
  assert.equal((await detail.latestSummaryReferences())[0].price,3500);
  clock=301001;
  const revised=await catalog.latestSummaryReferences();
  assert.equal(revised[0].price,3600); assert.equal(reads,4);
  assert.equal(await detail.latestSummaryReferences(),revised);
});
