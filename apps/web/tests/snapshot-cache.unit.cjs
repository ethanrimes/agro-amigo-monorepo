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

test('separate route module evaluations share named data, in-flight work and expiry', async () => {
  let clock=1000, reads=0, release;
  class Clock extends Date { static now() { return clock; } }
  const sharedGlobal = {};
  const load = () => {
    const module = {exports:{},Date:Clock,Map,Error,Promise,globalThis:sharedGlobal};
    vm.runInNewContext(output,module);
    return module.exports.snapshotCache(300000,64,'official-route-regression');
  };
  const catalog = load(), references = load();
  const gate = new Promise(resolve => { release=resolve; });
  const a = catalog('all',async()=>{reads++;await gate;return {total:21572};});
  const b = references('all',async()=>{reads++;return {total:17348};});
  release();
  const [first,second]=await Promise.all([a,b]);
  assert.equal(first,second);assert.equal(reads,1);
  assert.equal(catalog.expiresAt('all'),301000);
  assert.equal(references.expiresAt('all'),301000);
  clock=301001;
  const changed=await references('all',async()=>{reads++;return {total:21573};});
  assert.equal(await catalog('all',async()=>{throw new Error('duplicate query');}),changed);
  assert.equal(reads,2);assert.equal(catalog.expiresAt('all'),601001);
  assert.throws(()=>context.exports.snapshotCache(1,1,'config-test') && context.exports.snapshotCache(2,1,'config-test'),/SNAPSHOT_CONFIGURATION_MISMATCH/);
});

test('an outer snapshot inherits a nearly expired source deadline', async () => {
  let clock = 1000, reads = 0;
  class Clock extends Date { static now() { return clock; } }
  const module = { exports: {}, Date: Clock, Map, Error, Promise };
  vm.runInNewContext(output, module);
  const raw = module.exports.snapshotCache(5000);
  const outer = module.exports.snapshotCache(5000);
  assert.equal(await raw('raw', async () => 'first'), 'first');
  assert.equal(raw.expiresAt('raw'), 6000);
  clock = 5900;
  const readOuter = async () => { reads++; return raw('raw', async () => 'unexpected raw refresh'); };
  assert.equal(await outer('derived', readOuter, () => raw.expiresAt('raw')), 'first');
  assert.equal(outer.expiresAt('derived'), 6000);
  clock = 5999;
  assert.equal(await outer('derived', readOuter, () => raw.expiresAt('raw')), 'first');
  assert.equal(reads, 1);
  clock = 6000;
  assert.equal(await outer('derived', async () => { reads++; return 'second'; }, () => 11000), 'second');
  assert.equal(reads, 2);
  assert.equal(outer.expiresAt('derived'), 11000);
});

test('zero source expiry refreshes immediately and Infinity retains default TTL', async () => {
  let clock = 4000, reads = 0;
  class Clock extends Date { static now() { return clock; } }
  const module = { exports: {}, Date: Clock, Map, Error, Promise };
  vm.runInNewContext(output, module);
  const cached = module.exports.snapshotCache(5000);
  const read = async () => ++reads;
  assert.equal(await cached('zero', read, () => 0), 1);
  assert.equal(cached.expiresAt('zero'), 0);
  assert.equal(await cached('zero', read, () => 0), 2);
  assert.equal(await cached('infinity', read, () => Infinity), 3);
  assert.equal(cached.expiresAt('infinity'), 9000);
  clock = 8999;
  assert.equal(await cached('infinity', read, () => Infinity), 3);
  clock = 9000;
  assert.equal(await cached('infinity', read, () => Infinity), 4);
});

test('upstream deadline callback failure evicts pending work without caching', async () => {
  let clock = 100, reads = 0, callbacks = 0;
  class Clock extends Date { static now() { return clock; } }
  const module = { exports: {}, Date: Clock, Map, Error, Promise };
  vm.runInNewContext(output, module);
  const cached = module.exports.snapshotCache(5000, 1);
  const fail = () => { callbacks++; throw new Error('upstream clock unavailable'); };
  const requests = [cached('same', async () => ++reads, fail), cached('same', async () => ++reads, fail)];
  await Promise.all(requests.map((request) => assert.rejects(request, /upstream clock unavailable/)));
  assert.equal(reads, 1);
  assert.equal(callbacks, 1);
  assert.equal(cached.expiresAt('same'), 0);
  assert.equal(await cached('new', async () => ++reads), 2);
  assert.equal(await cached('same', async () => ++reads), 3);
  assert.equal(cached.expiresAt('same'), 5100);
});

test('without an upstream callback, TTL and shared-state semantics are unchanged', async () => {
  let clock = 2000, reads = 0;
  class Clock extends Date { static now() { return clock; } }
  const sharedGlobal = {};
  const load = () => {
    const module = { exports: {}, Date: Clock, Map, Error, Promise, globalThis: sharedGlobal };
    vm.runInNewContext(output, module);
    return module.exports.snapshotCache(5000, 2, 'plain-route');
  };
  const a = load(), b = load();
  assert.equal(await a('same', async () => ++reads), 1);
  assert.equal(a.expiresAt('same'), 7000);
  clock = 6999;
  assert.equal(await b('same', async () => ++reads), 1);
  clock = 7000;
  assert.equal(await b('same', async () => ++reads), 2);
  assert.equal(a.expiresAt('same'), 12000);
  assert.equal(reads, 2);
});

test('withExpiry binds an old source value to its original deadline across a parallel refresh', async () => {
  let clock = 0, releaseOuter;
  class Clock extends Date { static now() { return clock; } }
  const module = { exports: {}, Date: Clock, Map, Error, Promise };
  vm.runInNewContext(output, module);
  const raw = module.exports.snapshotCache(100);
  const outer = module.exports.snapshotCache(100);
  const first = await raw.withExpiry('raw', async () => ({ price: 10 }));
  assert.equal(first.expires, 100);
  assert.ok(Object.isFrozen(first));
  clock = 99;
  const waitForOtherSource = new Promise((resolve) => { releaseOuter = resolve; });
  let capturedDeadline;
  const slowOuter = outer.withExpiry('derived', async () => {
    const [source] = await Promise.all([
      raw.withExpiry('raw', async () => { throw new Error('unexpected raw refresh'); }),
      waitForOtherSource,
    ]);
    capturedDeadline = source.expires;
    return { price: source.value.price };
  }, () => capturedDeadline);
  clock = 100;
  const updated = await raw.withExpiry('raw', async () => ({ price: 20 }));
  assert.equal(updated.expires, 200);
  releaseOuter();
  const oldDerived = await slowOuter;
  assert.equal(oldDerived.value.price, 10);
  assert.equal(oldDerived.expires, 100);
  assert.equal(raw.expiresAt('raw'), 200); // Diagnostic current state is newer.
  assert.equal(outer.expiresAt('derived'), 100);
  clock = 101;
  const currentDerived = await outer.withExpiry('derived', async () => {
    const source = await raw.withExpiry('raw', async () => { throw new Error('unexpected raw refresh'); });
    capturedDeadline = source.expires;
    return { price: source.value.price };
  }, () => capturedDeadline);
  assert.equal(currentDerived.value.price, 20);
  assert.equal(currentDerived.expires, 200);
  assert.equal(oldDerived.expires, 100); // Entry metadata cannot be extended later.
});

test('named route concurrent calls share one immutable value/deadline generation', async () => {
  let clock = 200, reads = 0, release;
  class Clock extends Date { static now() { return clock; } }
  const sharedGlobal = {};
  const load = () => {
    const module = { exports: {}, Date: Clock, Map, Error, Promise, globalThis: sharedGlobal };
    vm.runInNewContext(output, module);
    return module.exports.snapshotCache(50, 2, 'atomic-route-entry');
  };
  const a = load(), b = load();
  const gate = new Promise((resolve) => { release = resolve; });
  const original = { quote: 367 };
  const pendingEntry = a.withExpiry('same', async () => { reads++; await gate; return original; });
  const pendingValue = b('same', async () => { reads++; return { quote: 999 }; });
  release();
  const [entry, value] = await Promise.all([pendingEntry, pendingValue]);
  assert.equal(reads, 1);
  assert.equal(entry.value, original);
  assert.equal(value, original);
  assert.equal(entry.expires, 250);
  assert.equal(await b.withExpiry('same', async () => { throw new Error('duplicate read'); }), entry);
  clock = 250;
  const next = await b.withExpiry('same', async () => ({ quote: 368 }));
  assert.notEqual(next, entry);
  assert.equal(next.expires, 300);
  assert.equal(entry.expires, 250);
  assert.equal(a.expiresAt('same'), 300);
});
