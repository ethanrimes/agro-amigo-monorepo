const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/planning.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const cityPartialReview = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/city-partial-review.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, cityPartialReview);
const WINDOW = "observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

function row(id, department, price, extra = {}) {
  return { id, department, municipality: '', observed_on: '2026-09-30', price,
    name: id, category: 'Insumos', presentation: '1 litro',
    document_id: `${id}-${department}-source`, source_locator: `${id}-${department}-cell`,
    brand: '', registration: '', product_line: '', ...extra };
}

function makeHarness({ raw, published, delayMs = 0, failNational = false,
  startAt = Date.now(), publicationWaitMs, missingRevision = false,
  onNationalPublication } = {}) {
  const calls = [];
  const revision = { source_epoch: 0, alias_count: 0, checkpoint_count: 0 };
  let epoch = startAt;
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [epoch])); }
    static now() { return epoch; }
  }
  const db = { query: async (sql, args = []) => {
    const municipal = sql.includes('input_municipal_price') || sql.includes('input_municipal_latest_raw');
    const scope = municipal ? 'municipality' : 'department';
    const regional = Array.isArray(args[1]);
    const geography = regional ? args[1][0] : '';
    const historical = sql.includes('p.observed_on<=CURRENT_DATE') ||
      sql.includes('l.observed_on<=CURRENT_DATE');
    if (sql.includes('SELECT s.source_epoch::text AS source_epoch')) {
      calls.push({ phase: 'revision', scope, ...revision });
      return { rows: missingRevision ? [] : [{
        source_epoch: String(revision.source_epoch),
        alias_count: String(revision.alias_count),
        checkpoint_count: String(revision.checkpoint_count),
      }] };
    }
    if (sql.includes('WITH state AS MATERIALIZED')) {
      const first = args.length === (regional ? 3 : 2) && args.at(-1) === 'c';
      const rows = first ? (raw({ scope, geography, historical }) || []) : [];
      calls.push({ phase: 'projection', scope, geography, historical, rows: rows.map(x => x.id) });
      return { rows: [{ ready: true, id: null }, ...rows.map(x => ({ ready: true, ...x }))] };
    }
    if (sql.includes('FROM unnest($1::text[]) AS keys(id)')) {
      const ids = args[0];
      calls.push({ phase: 'publication', scope, geography, historical, ids: [...ids] });
      if (delayMs) await new Promise(resolve => setTimeout(resolve, delayMs));
      if (failNational && !regional) throw new Error('national published view unavailable');
      const rows = ids.flatMap(id => {
        const found = published({ scope, geography, historical, id, revision });
        return found ? [found] : [];
      });
      if (!regional) onNationalPublication?.(revision);
      return { rows };
    }
    if (sql.includes('WITH winners AS MATERIALIZED') && sql.includes('previous_raw')) {
      const keys = JSON.parse(args[0]);
      calls.push({ phase: 'previous', scope, keys });
      return { rows: keys.map(k => ({ id: k.id,
        previous_price: k.department === 'Antioquia' ? 91 : 42,
        previous_date: '2026-08-31' })) };
    }
    throw new Error(`Unexpected query: ${sql.slice(0, 90)}`);
  } };
  const context = { exports: {}, Date: Clock, Map, Set, Error, Promise, process,
    require: name => {
      if (name === 'server-only') return {};
      if (name === 'node:crypto') return require(name);
      if (name === 'node:timers') return {
        setTimeout: (callback, ms) => setTimeout(callback,
          ms === 15_000 && publicationWaitMs !== undefined ? publicationWaitMs : ms),
        clearTimeout,
      };
      if (name === './db') return { database: () => db, WINDOW };
      if (name === './city-partial-review') return cityPartialReview.exports;
      if (name === './input-identities') return { reconcileInputCatalog: async rows => rows };
      if (name === '../planning-math') return { fold: s => s };
      if (name === '../label-normalization') {
        const file = path.join(__dirname, '../src/lib/label-normalization.ts');
        const exports = {};
        const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022, esModuleInterop: true },
        }).outputText;
        new Function('exports', 'require', code)(exports, dependency =>
          require(path.resolve(path.dirname(file), dependency)));
        return exports;
      }
      if (name === '../input-identity-equivalence') return require('./helpers/load-input-identity-equivalence.cjs')();
      if (name === '../filter-labels') {
        const exports = {};
        const code = ts.transpileModule(fs.readFileSync(path.join(__dirname,
          '../src/lib/filter-labels.ts'), 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
        }).outputText;
        new Function('exports', code)(exports);
        return exports;
      }
      if (name === './official-evidence-sql' || name === './daily-date-note' ||
          name === './source-document-sql' || name === './evidence-review-sql' ||
          name === './supply-summary-evidence' || name === '../weather-data') return {};
      throw new Error(`Unexpected import ${name}`);
    },
  };
  vm.runInNewContext(compiled, context);
  return { inputs: context.exports.inputs, calls, revision,
    advance: ms => { epoch += ms; },
    mutate: field => { revision[field] += 1; } };
}

function signatures(rows) {
  return Array.from(rows, r => [r.id, r.department, r.municipality, r.price,
    r.document_id, r.source_locator, r.previous_price, r.previous_date]);
}

test('regional publication shares only examined absence and same-department winner; residual IDs keep their own original and prior price', async () => {
  const national = [row('neg', 'Valle del Cauca', 1, { needs_published_lookup: true }),
    row('same', 'Antioquia', 2, { needs_published_lookup: true }),
    row('foreign', 'Valle del Cauca', 3, { needs_published_lookup: true }),
    row('unexamined', 'Valle del Cauca', 4, { needs_published_lookup: false }),
    row('keep', 'Valle del Cauca', 5, { needs_published_lookup: true })];
  const regional = ['neg', 'same', 'foreign', 'unexamined'].map((id, i) =>
    row(id, 'Antioquia', i + 11, { needs_published_lookup: true }))
    .concat(row('keep', 'Antioquia', 99, { needs_published_lookup: false }));
  const h = makeHarness({ raw: ({ geography }) => geography ? regional : national,
    published: ({ geography, id }) => geography
      ? ({ foreign: row('foreign', 'Antioquia', 73), unexamined: row('unexamined', 'Antioquia', 74) })[id]
      : ({ same: row('same', 'Antioquia', 52), foreign: row('foreign', 'Valle del Cauca', 53),
        keep: row('keep', 'Valle del Cauca', 54) })[id],
    delayMs: 5 });
  const [all, antioquia] = await Promise.race([
    Promise.all([h.inputs('', 'department', true, '', true),
      h.inputs('Antioquia', 'department', true, '', true)]),
    new Promise((_, reject) => setTimeout(() => reject(new Error('publication sharing deadlocked')), 1500)),
  ]);
  assert.deepEqual(signatures(antioquia), [
    ['foreign', 'Antioquia', '', 73, 'foreign-Antioquia-source', 'foreign-Antioquia-cell', 91, '2026-08-31'],
    ['keep', 'Antioquia', '', 99, 'keep-Antioquia-source', 'keep-Antioquia-cell', 91, '2026-08-31'],
    ['same', 'Antioquia', '', 52, 'same-Antioquia-source', 'same-Antioquia-cell', 91, '2026-08-31'],
    ['unexamined', 'Antioquia', '', 74, 'unexamined-Antioquia-source', 'unexamined-Antioquia-cell', 91, '2026-08-31'],
  ]);
  assert.equal(all.some(r => r.id === 'neg'), false);
  assert.equal(h.calls.filter(c => c.phase === 'publication' && !c.geography).length, 1);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids).sort(), ['foreign', 'unexamined']);
  assert.equal(h.calls.filter(c => c.phase === 'previous').length, 2,
    'the regional response independently reads prior-month prices for its selected locations');
});

test('scope and history windows do not cross-share national publication outcomes', async () => {
  const h = makeHarness({ raw: ({ scope }) => [row('one', 'Antioquia', 1,
    { municipality: scope === 'municipality' ? 'Medellín' : '', needs_published_lookup: true })],
  published: ({ scope, historical, geography }) => geography
    ? row('one', 'Antioquia', scope === 'municipality' ? 401 : historical ? 301 : 201,
      { municipality: scope === 'municipality' ? 'Medellín' : '' })
    : row('one', 'Valle del Cauca', scope === 'municipality' ? 400 : historical ? 300 : 200,
      { municipality: scope === 'municipality' ? 'Cali' : '' }) });
  await Promise.all([h.inputs('', 'department', true, '', true),
    h.inputs('', 'department', false, '', true), h.inputs('', 'municipality', true, '', true)]);
  const [all, recent, municipal] = await Promise.all([
    h.inputs('Antioquia', 'department', true, '', true),
    h.inputs('Antioquia', 'department', false, '', true),
    h.inputs('Antioquia', 'municipality', true, '', true),
  ]);
  assert.deepEqual([all[0].price, recent[0].price, municipal[0].price], [301, 201, 401]);
  assert.equal(municipal[0].municipality, 'Medellín');
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .map(c => [c.scope, c.historical, c.ids.join(',')]).sort(), [
      ['department', false, 'one'], ['department', true, 'one'], ['municipality', true, 'one']]);
});

test('a rejected national publication stage falls back to regional SQL and releases the fair-reader queue', async () => {
  const h = makeHarness({ raw: () => [row('old', 'Antioquia', 1, { needs_published_lookup: true })],
    published: ({ geography }) => geography ? row('old', 'Antioquia', 44) : undefined,
    failNational: true, delayMs: 5 });
  const settled = await Promise.race([
    Promise.allSettled([h.inputs('', 'department', true, '', true),
      h.inputs('Antioquia', 'department', true, '', true)]),
    new Promise((_, reject) => setTimeout(() => reject(new Error('publication failure deadlocked')), 1500)),
  ]);
  assert.deepEqual(settled.map(x => x.status), ['rejected', 'fulfilled']);
  assert.deepEqual(signatures(settled[1].value), [
    ['old', 'Antioquia', '', 44, 'old-Antioquia-source', 'old-Antioquia-cell', 91, '2026-08-31'],
  ]);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids), ['old']);
});

test('a still-pending national stage times out and the region reads its own winner without a SQL-slot deadlock', async () => {
  const h = makeHarness({ raw: () => [row('slow', 'Antioquia', 1,
    { needs_published_lookup: true })],
  published: ({ geography }) => geography ? row('slow', 'Antioquia', 83) : undefined,
  delayMs: 35, publicationWaitMs: 1 });
  const [national, regional] = await Promise.race([
    Promise.all([h.inputs('', 'department', true, '', true),
      h.inputs('Antioquia', 'department', true, '', true)]),
    new Promise((_, reject) => setTimeout(() => reject(new Error('timeout fallback deadlocked')), 1500)),
  ]);
  assert.equal(national.length, 0);
  assert.deepEqual(signatures(regional), [
    ['slow', 'Antioquia', '', 83, 'slow-Antioquia-source', 'slow-Antioquia-cell', 91, '2026-08-31'],
  ]);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids), ['slow'], 'timeout must run the authoritative regional publication query');
});

test('coalescing avoids duplicate 40-ID published-view batches and expiry restores own regional lookup', async () => {
  const names = Array.from({ length: 81 }, (_, i) => `legacy-${String(i).padStart(3, '0')}`);
  const h = makeHarness({ raw: () => names.map(id => row(id, 'Antioquia', 1,
    { needs_published_lookup: true })), published: () => undefined });
  const [national, regional] = await Promise.all([
    h.inputs('', 'department', true, '', true), h.inputs('Antioquia', 'department', true, '', true),
  ]);
  assert.equal(national.length, 0);
  assert.equal(regional.length, 0);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && !c.geography)
    .map(c => c.ids.length), [40, 40, 1]);
  assert.equal(h.calls.filter(c => c.phase === 'publication' && c.geography).length, 0,
    'an examined negative is not re-queried regionally');
  h.advance(300_001);
  const later = await h.inputs('Boyacá', 'department', true, '', true);
  assert.equal(later.length, 0);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography === 'Boyacá')
    .map(c => c.ids.length), [40, 40, 1], 'expired stage cannot imply negative results');
});

test('Bogotá publication-day rollover invalidates even an otherwise fresh negative stage', async () => {
  const h = makeHarness({ startAt: Date.parse('2026-10-04T04:59:58Z'),
    raw: () => [row('dated', 'Antioquia', 1, { needs_published_lookup: true })],
    published: ({ geography }) => geography ? row('dated', 'Antioquia', 81) : undefined });
  assert.equal((await h.inputs('', 'department', true, '', true)).length, 0);
  h.advance(5_000); // Bogotá 23:59:58 -> 00:00:03, still inside the five-minute TTL.
  const regional = await h.inputs('Antioquia', 'department', true, '', true);
  assert.equal(regional[0].price, 81);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids), ['dated']);
});

for (const field of ['source_epoch', 'alias_count', 'checkpoint_count']) {
  test(`a new ${field} invalidates a completed national negative before regional reuse`, async () => {
    const h = makeHarness({ raw: () => [row('changed', 'Antioquia', 1,
      { needs_published_lookup: true })],
    published: ({ geography }) => geography ? row('changed', 'Antioquia', 87) : undefined });
    assert.equal((await h.inputs('', 'department', true, '', true)).length, 0);
    h.mutate(field);
    const regional = await h.inputs('Antioquia', 'department', true, '', true);
    assert.equal(regional[0].price, 87);
    assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
      .flatMap(c => c.ids), ['changed']);
  });
}

test('a publication mutation during the national SQL cannot attach a stale negative to its new token', async () => {
  const h = makeHarness({ raw: () => [row('racing', 'Antioquia', 1,
    { needs_published_lookup: true })], published: ({ geography }) => geography
    ? row('racing', 'Antioquia', 89) : undefined,
  onNationalPublication: revision => { revision.checkpoint_count += 1; } });
  assert.equal((await h.inputs('', 'department', true, '', true)).length, 0);
  const regional = await h.inputs('Antioquia', 'department', true, '', true);
  assert.equal(regional[0].price, 89);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids), ['racing']);
});

test('missing publication revision never suppresses a regional winner', async () => {
  const h = makeHarness({ missingRevision: true,
    raw: () => [row('unknown', 'Antioquia', 1, { needs_published_lookup: true })],
    published: ({ geography }) => geography ? row('unknown', 'Antioquia', 97) : undefined });
  assert.equal((await h.inputs('', 'department', true, '', true)).length, 0);
  const regional = await h.inputs('Antioquia', 'department', true, '', true);
  assert.equal(regional[0].price, 97);
  assert.deepEqual(h.calls.filter(c => c.phase === 'publication' && c.geography)
    .flatMap(c => c.ids), ['unknown']);
});
