const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const oracle = require('./fixtures/aguacate-bucaramanga-weekly-source-oracle.json');

function load(name, mocks = {}, context = {}) {
  const module = { exports: {} };
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/', name + '.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { module, exports: module.exports, URLSearchParams, Error,
    require: key => Object.hasOwn(mocks, key) ? mocks[key] : require(key), ...context });
  return module.exports;
}
const helper = load('aguacate-bucaramanga-weekly-continuity');
const old = oracle.legacy_key, current = oracle.canonical_key;
const sourceRows = () => oracle.anchors.map((a) => ({
  document_id: a.document_id, source_locator: a.source_locator, source_page: a.source_page,
  source_url: a.source_url, parser_version: 'official-v2:dane-weekly-v24',
  quote_key: a.quote_key, product_id: 'aguacate-comun', product_name: a.source_product,
  category: a.date === '2021-11-19' ? 'Frutas frescas' : 'frutas frescas',
  publisher: 'DANE · SIPSA', series: 'dane-weekly', basis: 'Precio mayorista semanal',
  currency: 'COP', unit: 'kg', market: 'Bucaramanga, Centroabastos',
  observed_on: a.date, period_start: a.period_start, price: a.price,
  min_price: a.min_price, max_price: a.max_price,
  details: { identity_dimensions: { source_product: a.source_product },
    period_type: 'weekly', price_statistic: 'published_mean', period_end: a.date },
}));

test('independent XLSX/PDF cells form three dates with exact old bookmark and native provenance', () => {
  const rows = sourceRows(), before = structuredClone(rows);
  const history = helper.mergeAguacateBucaramangaWeeklyHistory(rows);
  assert.deepEqual(Array.from(history, r => r.observed_on),
    ['2021-11-19', '2022-07-08', '2026-08-14']);
  assert.deepEqual(Array.from(history, r => r.price), [5000, 5500, 8833]);
  assert.equal(history[0].quote_key, current);
  assert.equal(history[0].details.original_quote_key, old);
  assert.equal(history[0].details.source_product_literal, 'Aguacate Común');
  assert.equal(history[0].document_id, oracle.anchors[0].document_id);
  assert.equal(history[0].source_locator, '1.2!row 12,cols C:E');
  assert.equal(history[1].source_page, 21);
  assert.deepEqual(rows, before);
});

test('exact identity guard excludes daily, other variety/facility/unit and unaudited case folding', () => {
  const mutations = [
    r => r.quote_key = oracle.excluded_daily_key,
    r => r.product_id = 'aguacate-papelillo', r => r.product_name = 'Aguacate ComUn',
    r => r.market = 'Medellín, Central Mayorista de Antioquia',
    r => r.series = 'dane-daily-query', r => r.basis = 'Precio mayorista diario · promedio publicado',
    r => r.currency = 'USD', r => r.unit = 'unit', r => r.category = 'Verduras y hortalizas',
    r => r.publisher = 'Otro editor', r => r.details.identity_dimensions.quality = 'extra',
    r => r.details.identity_dimensions.source_product = 'Aguacate ComUn',
    r => r.details.period_type = 'daily', r => r.details.price_statistic = 'midpoint',
    r => r.document_id = 'missing', r => r.source_locator = '',
    r => r.source_url = 'https://other.example/file.pdf',
    r => r.price = 0, r => r.min_price = null, r => r.max_price = r.price - 1,
  ];
  for (const mutation of mutations) {
    const rows = sourceRows(); mutation(rows[0]);
    assert.throws(() => helper.mergeAguacateBucaramangaWeeklyHistory(rows), /IDENTITY_CONFLICT/);
  }
});

test('a new same-date full-tuple match retains both originals; any disagreement isolates histories', () => {
  const rows = sourceRows();
  const duplicate = { ...rows[0], quote_key: current, product_name: 'Aguacate común',
    details: { ...rows[0].details, identity_dimensions: { source_product: 'Aguacate común' } },
    document_id: 'a'.repeat(64), source_locator: 'PDF page 30,table 1,column 1,line 2' };
  const matching = helper.mergeAguacateBucaramangaWeeklyHistory([...rows, duplicate]);
  assert.equal(matching.length, 3);
  assert.equal(matching[0].document_id, duplicate.document_id);
  assert.equal(matching[0].details.alternate_originals[0].document_id, rows[0].document_id);
  for (const field of ['price', 'min_price', 'max_price', 'period_start']) {
    const changed = { ...duplicate,
      ...(field === 'price' ? { price: 5100, max_price: 5100 } : {}),
      ...(field === 'min_price' ? { min_price: 4900 } : {}),
      ...(field === 'max_price' ? { max_price: 5100 } : {}),
      ...(field === 'period_start' ? { period_start: '2021-11-12' } : {}) };
    assert.throws(() => helper.mergeAguacateBucaramangaWeeklyHistory([...rows, changed]), /OVERLAP_CONFLICT/);
  }
  assert.throws(() => helper.mergeAguacateBucaramangaWeeklyHistory([...rows, rows[0]]), /OVERLAP_CONFLICT/);
});

test('catalog keeps clean current card, never substitutes missing current with stale old price', () => {
  const rows = sourceRows().map(r => ({ ...r, previous_price: null }));
  const unrelated = { ...rows[0], quote_key: oracle.excluded_daily_key,
    series: 'dane-daily-query', basis: 'Precio mayorista diario · promedio publicado' };
  const result = helper.collapseAguacateBucaramangaWeeklyCatalog([rows[0], rows[2], unrelated]);
  assert.deepEqual(Array.from(result, r => r.quote_key), [current, oracle.excluded_daily_key]);
  assert.equal(result[0], rows[2]);
  assert.deepEqual(helper.collapseAguacateBucaramangaWeeklyCatalog([rows[0], unrelated]), [unrelated]);
});

function service({ conflicting = false, malformed = false, broken = false } = {}) {
  const events = [], shared = {}, rows = sourceRows();
  if (conflicting) rows.push({ ...rows[0], quote_key: current, product_name: 'Aguacate común',
    details: { ...rows[0].details, identity_dimensions: { source_product: 'Aguacate común' } },
    document_id: 'a'.repeat(64), price: 5100, max_price: 5100 });
  if (malformed) rows[0].details.identity_dimensions.quality = 'unknown';
  const query = async (sql, args) => {
    events.push({ sql, args });
    if (sql.includes('WITH candidates AS MATERIALIZED')) {
      if (broken) throw new Error('Source reader unavailable');
      return { rows: rows.filter(r => r.quote_key === args[0]) };
    }
    if (sql.includes('SELECT payload FROM official_catalog_current'))
      return { rows: [rows[0], rows[2]].map(payload => ({ payload: { ...payload, previous_price: null } })) };
    return { rows: [] };
  };
  const cache = load('snapshot-cache', { 'server-only': {} }, { globalThis: shared });
  const route = load('official-references', {
    'server-only': {}, './db': { database: () => ({ query,
      connect: async () => ({ query, release: () => events.push({ release: true }) }) }) },
    './summary-references': { summaryReference: async () => null },
    './snapshot-cache': cache, './official-market-regions': { officialMarketRegions: async r => r },
    '../label-normalization': require('./helpers/load-label-normalization.cjs')(),
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
    './minorista-weekly-continuity': load('minorista-weekly-continuity'),
    './aguacate-bucaramanga-weekly-continuity': helper,
  }, { globalThis: shared });
  return { route, events };
}

test('service resolves both bookmarks through two one-key guarded seeks in one read snapshot', async () => {
  const app = service();
  const cards = await app.route.latestOfficialReferences();
  assert.equal(cards.length, 1);
  assert.equal(cards[0].quote_key, current);
  assert.equal(app.events.filter(e => e.sql?.includes('WITH candidates')).length, 0);
  const a = await app.route.officialReferences(new URLSearchParams('id=' + old));
  const b = await app.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(a.history.length, 3); assert.equal(b.reference.price, 8833);
  assert.equal(app.events.filter(e => e.sql?.includes('WITH candidates')).length, 2);
  assert.equal(app.events.filter(e => e.sql === 'BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ').length, 1);
  assert.equal(app.events.filter(e => e.sql === 'COMMIT').length, 1);
});

test('catalog search folds extended Unicode combining marks without changing source names or keys', async () => {
  const app = service();
  const result = await app.route.officialReferences(new URLSearchParams('q=Aguacate\u1ab0 común'));
  assert.equal(result.total, 1);
  assert.equal(result.rows[0].quote_key, current);
  assert.equal(result.rows[0].product_name, 'Aguacate común');
});

test('conflict is scoped to requested standalone bookmark; database failure propagates and rolls back', async () => {
  const conflict = service({ conflicting: true });
  const a = await conflict.route.officialReferences(new URLSearchParams('id=' + old));
  const b = await conflict.route.officialReferences(new URLSearchParams('id=' + current));
  assert.equal(a.history.length, 1); assert.equal(b.history.length, 3);
  assert.ok(a.history.every(r => r.quote_key === old));
  assert.ok(b.history.every(r => r.quote_key === current));
  assert.match(a.reference.details.history_continuity_note, /por separado/);
  const malformed = service({ malformed: true });
  assert.equal(await malformed.route.officialReferences(new URLSearchParams('id=' + old)), null);
  assert.equal((await malformed.route.officialReferences(new URLSearchParams('id=' + current))).reference.price, 8833);
  const failed = service({ broken: true });
  await assert.rejects(failed.route.officialReferences(new URLSearchParams('id=' + old)), /Source reader unavailable/);
  assert.ok(failed.events.some(e => e.sql === 'ROLLBACK'));
  assert.ok(failed.events.some(e => e.release));
});
