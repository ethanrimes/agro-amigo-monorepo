const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const oracle = require('./fixtures/minorista-weekly-source-oracle.json');

function load(name, mocks = {}, context = {}) {
  const module = { exports: {} };
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/', name + '.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { module, exports: module.exports, URLSearchParams, Error,
    require: key => Object.hasOwn(mocks, key) ? mocks[key] : require(key), ...context });
  return module.exports;
}
const helper = load('minorista-weekly-continuity');
const current = oracle.canonical_key, old = oracle.legacy_key;
const nativeRows = () => structuredClone(oracle.anchors.map(a => a.published));

test('four independent native PDF/XLS anchors join three dates and preserve complete raw provenance', () => {
  const rows = nativeRows(), before = structuredClone(rows);
  const history = helper.mergeMinoristaWeeklyHistory(rows);
  assert.deepEqual(Array.from(history, r => r.observed_on), ['2017-01-27','2019-02-15','2026-10-02']);
  assert.deepEqual(Array.from(history, r => r.price), [1063,1400,3775]);
  assert.equal(history[0].quote_key, current);
  assert.equal(history[0].details.original_quote_key, old);
  assert.equal(history[0].details.source_market_literal, rows[0].market);
  assert.equal(history[0].source_page, 16);
  assert.equal(history[1].document_id, oracle.anchors[2].native.document_id);
  assert.equal(history[1].source_locator, '1.2!row 412,cols C:E');
  assert.equal(history[1].details.alternate_originals[0].document_id, oracle.anchors[1].native.document_id);
  assert.equal(history[1].details.alternate_originals[0].source_page, 29);
  assert.deepEqual(rows, before);
  assert.ok(helper.isMinoristaWeeklyKey(current) && helper.isMinoristaWeeklyKey(old));
});

test('ordinary later current-key publication is accepted without fixed Oct2 cutoff or mandatory old anchors', () => {
  // Synthetic update counterexample, not a claim that DANE published this date.
  const later = { ...nativeRows().at(-1), observed_on: '2026-10-03',
    document_id: 'a'.repeat(64), price: 3800 };
  const history = helper.mergeMinoristaWeeklyHistory([...nativeRows(), later]);
  assert.equal(history.at(-1).document_id, later.document_id);
  assert.equal(history.at(-1).price, 3800);
  assert.equal(helper.mergeMinoristaWeeklyHistory([later]).length, 1);
});

test('exact variety, facility, identity digest, unit, original pointer and amount guards reject broad spelling guesses', () => {
  const mutations = [r => r.market = 'Medellín, Central Mayorista de Antioquia',
    r => r.product_id = 'limon-comun', r => r.product_name = 'Limón mandarino',
    r => r.quote_key = 'a'.repeat(64), r => r.currency = 'USD', r => r.unit = 'unit',
    r => r.series = 'dane-daily', r => r.basis = 'Precio minorista',
    r => r.category = 'Verduras y hortalizas',
    r => r.details.identity_dimensions.quality = 'extra',
    r => r.document_id = 'missing', r => r.source_url = 'https://unofficial.example/file.pdf',
    r => r.source_locator = '', r => r.price = Infinity, r => r.price = 0,
    r => r.min_price = null, r => r.min_price = r.price + 1,
    r => r.max_price = r.price - 1];
  for (const mutate of mutations) {
    const rows = nativeRows(); mutate(rows[0]);
    assert.throws(() => helper.mergeMinoristaWeeklyHistory(rows), /IDENTITY_CONFLICT/);
  }
});

test('price/min/max/period conflicts and new cross-key overlaps do not merge', () => {
  for (const field of ['price','min_price','max_price','period_start']) {
    const rows = nativeRows();
    rows[1][field] = field === 'period_start' ? '2019-02-08' : rows[1][field] + 1;
    assert.throws(() => helper.mergeMinoristaWeeklyHistory(rows), /PRICE_CONFLICT/);
  }
  const rows = nativeRows();
  const duplicate = { ...rows[2], observed_on: rows[0].observed_on,
    price: rows[0].price, min_price: rows[0].min_price, max_price: rows[0].max_price };
  assert.throws(() => helper.mergeMinoristaWeeklyHistory([...rows, duplicate]), /OVERLAP_CONFLICT/);
});

test('catalog collapse uses clean current metadata only and leaves unrelated products and standalone prices intact', () => {
  const rows = nativeRows().map(r => ({ ...r, previous_price: 3600 }));
  const unrelated = { ...rows[3], quote_key: 'unrelated', product_id: 'limon-comun' };
  const cards = helper.collapseMinoristaWeeklyCatalog([rows[1], rows[3], unrelated]);
  assert.equal(cards.length, 2);
  assert.equal(cards[0], rows[3]);
  assert.equal(cards[0].previous_price, 3600);
  assert.equal(cards[1], unrelated);
  assert.equal(helper.collapseMinoristaWeeklyCatalog([rows[0]])[0], rows[0]);
});

function service({ conflicting = false, broken = false, malformedLegacy = false } = {}) {
  let clock = 0, revised = false;
  const events = [], shared = {};
  class Clock extends Date { static now() { return clock; } }
  const ctx = { Date: Clock, globalThis: shared };
  const cache = load('snapshot-cache', { 'server-only': {} }, ctx);
  const rows = () => {
    const result = nativeRows();
    if (malformedLegacy) result[0].category = 'Verduras y hortalizas';
    if (revised) result[3] = { ...result[3], price: 3800, document_id: 'a'.repeat(64) };
    if (conflicting) result.push({ ...result[3], observed_on: result[0].observed_on,
      price: result[0].price, min_price: result[0].min_price, max_price: result[0].max_price });
    return result;
  };
  const query = async (sql, args) => {
    events.push({ sql, args });
    if (sql.includes('WITH candidates AS MATERIALIZED')) {
      if (broken) throw new Error('Source reader unavailable');
      return { rows: rows().filter(r => r.quote_key === args[0]) };
    }
    if (sql.includes('SELECT payload FROM official_catalog_current'))
      return { rows: [rows()[1],rows()[3]].map(payload => ({ payload: { ...payload, previous_price: null } })) };
    return { rows: [] };
  };
  const route = load('official-references', {
    'server-only': {}, './db': { database: () => ({ query,
      connect: async () => ({ query, release: () => events.push({ release: true }) }) }) },
    './summary-references': { summaryReference: async () => null },
    './snapshot-cache': cache, './official-market-regions': { officialMarketRegions: async r => r },
    '../label-normalization': { normalizeOfficialLabels: r => r, normalizeLabel: v => v },
    '../category-hierarchy': require('./helpers/category-hierarchy.cjs')(),
    './weekly-capitalization-continuity': {
      capitalizationWeeklyGroups: () => ({ groups: [], byKey: new Map() }),
      collapseCapitalizationWeeklyCatalog: rows => rows,
      isReviewedCapitalizationWeeklyKey: () => false,
      isWeeklyCapitalizationConflict: () => false,
      mergeCapitalizationWeeklyHistory: (_group, rows) => rows,
      MAX_WEEKLY_CAPITALIZATION_KEYS: 8,
    },
    './acelga-weekly-continuity': load('acelga-weekly-continuity'),
    './weekly-corabastos-continuity': load('weekly-corabastos-continuity'),
    './minorista-weekly-continuity': helper,
    './aguacate-bucaramanga-weekly-continuity': load('aguacate-bucaramanga-weekly-continuity'),
  }, ctx);
  return { route, events, clock: value => clock = value, revise: () => revised = true };
}

test('real service preserves both bookmarks, executes two guarded seeks in one read snapshot, and catalog performs no history scans', async () => {
  const app = service();
  const cards = await app.route.latestOfficialReferences();
  assert.equal(cards.length, 1); assert.equal(cards[0].quote_key, current);
  assert.equal(app.events.filter(e => e.sql?.includes('WITH candidates')).length, 0);
  const a = await app.route.officialReferences(new URLSearchParams('id=' + old));
  const b = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(a.history[0].price, 1063); assert.equal(b.reference.price, 3775);
  assert.equal(a.history[1].details.alternate_originals[0].source_page, 29);
  assert.equal(app.events.filter(e => e.sql?.includes('WITH candidates')).length, 2);
  assert.equal(app.events.filter(e => e.sql === 'BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ').length, 1);
  assert.equal(app.events.filter(e => e.sql === 'COMMIT').length, 1);
});

test('bookmarked detail inherits exact raw history deadline and fetches revised original money at expiry', async () => {
  const app = service();
  await app.route.officialReferences(new URLSearchParams('id=' + old));
  app.clock(299999);
  const before = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(before.reference.price, 3775);
  app.revise(); app.clock(300000);
  const after = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(after.reference.price, 3800);
  assert.equal(after.reference.document_id, 'a'.repeat(64));
  assert.equal(app.events.filter(e => e.sql?.includes('WITH candidates')).length, 4);
});

test('an unreviewed overlap isolates the bridge and preserves separate current/old bookmark histories with visible scope note', async () => {
  const app = service({ conflicting: true });
  const cards = await app.route.latestOfficialReferences();
  assert.ok(cards.some(r => r.quote_key === current));
  const a = await app.route.officialReferences(new URLSearchParams('id=' + old));
  const b = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.ok(a.history.every(r => r.quote_key === old));
  assert.ok(b.history.every(r => r.quote_key === current));
  assert.equal(a.reference.document_id, oracle.anchors[1].native.document_id);
  assert.equal(b.reference.document_id, oracle.anchors[3].native.document_id);
  assert.match(b.reference.details.history_continuity_note, /por separado/);
});

test('database failures rollback and release, rather than substituting cached catalogue money for history', async () => {
  const app = service({ broken: true });
  await assert.rejects(app.route.officialReferences(new URLSearchParams('id=' + old)), /Source reader unavailable/);
  assert.ok(app.events.some(e => e.sql === 'ROLLBACK'));
  assert.ok(app.events.some(e => e.release));
});

test('malformed legacy identity fails closed for itself while valid current history survives separately', async () => {
  const app = service({ malformedLegacy: true });
  const oldResult = await app.route.officialReferences(new URLSearchParams('id=' + old));
  const currentResult = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(oldResult, null);
  assert.equal(currentResult.reference.price, 3775);
  assert.ok(currentResult.history.every(r => r.quote_key === current));
  assert.match(currentResult.reference.details.history_continuity_note, /por separado/);
});
