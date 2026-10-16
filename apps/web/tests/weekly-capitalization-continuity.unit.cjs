const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const fixture = require('./fixtures/sardinas-weekly-capitalization-history.json');
const helperPath = path.join(__dirname, '../src/lib/server/weekly-capitalization-continuity.ts');
const helperModule = { exports: {} };
const helperSource = fs.readFileSync(helperPath, 'utf8');
vm.runInNewContext(ts.transpileModule(helperSource, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, { module: helperModule, exports: helperModule.exports,
  require: name => name.startsWith('.') ? require(path.resolve(path.dirname(helperPath), name)) : require(name) });
const helper = helperModule.exports;
const load = (name, mocks = {}, context = {}) => {
  const module = { exports: {} };
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/', name + '.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { module, exports: module.exports, URLSearchParams, Error,
    require: key => Object.hasOwn(mocks, key) ? mocks[key] : require(key), ...context });
  return module.exports;
};

const legacy = fixture.legacy;
const currentRows = fixture.current_history;
const current = currentRows.at(-1);
const legacyKey = '2559b38f33b35c20b26c52c38abe0e70e5be4bd5bb4e7b1a4d788e261e5fd46b';
const currentKey = '6568e2cd211cd0e0f5c86625926662a742ab3adae0678ee9c0dfa10ae2229a33';
const copy = value => JSON.parse(JSON.stringify(value));

test('authenticates both literal quote keys and selects the latest current spelling', () => {
  assert.equal(helper.expectedWeeklyQuoteKey(legacy), legacyKey);
  assert.equal(helper.expectedWeeklyQuoteKey(current), currentKey);
  const result = helper.capitalizationWeeklyGroups([legacy, current]);
  assert.equal(result.groups.length, 1);
  assert.equal(result.groups[0].canonicalKey, currentKey);
  assert.equal(result.groups[0].canonicalName, 'Sardinas en lata');
  assert.equal(result.byKey.get(legacyKey), result.groups[0]);
});

test('unions the actual 580 current rows with the legacy 2021 source into 581 dates', () => {
  const group = helper.capitalizationWeeklyGroups([legacy, current]).groups[0];
  const merged = helper.mergeCapitalizationWeeklyHistory(group, [legacy, ...currentRows]);
  assert.equal(merged.length, 581);
  const restored = merged.find(row => row.observed_on === '2021-11-19');
  assert.equal(restored.price, 11975);
  assert.equal(restored.min_price, 11892);
  assert.equal(restored.max_price, 12059);
  assert.equal(restored.quote_key, currentKey);
  assert.equal(restored.product_name, 'Sardinas en lata');
  assert.equal(restored.details.original_quote_key, legacyKey);
  assert.equal(restored.details.original_product_name, 'Sardinas en Lata');
  assert.equal(restored.details.capitalization_equivalence_sources[0].source_url, legacy.source_url);
  assert.equal(restored.details.capitalization_equivalence_sources[0].source_locator, '1.8!row 617,cols C:E');
});

test('catalog collapses to one card and retains both current identity witnesses', () => {
  const cards = [legacy, current].map(row => ({ ...row, previous_price: null }));
  const { groups } = helper.capitalizationWeeklyGroups(cards);
  const result = helper.collapseCapitalizationWeeklyCatalog(cards, groups);
  assert.equal(result.length, 1);
  assert.equal(result[0].quote_key, currentKey);
  assert.equal(result[0].product_name, 'Sardinas en lata');
  assert.equal(result[0].details.capitalization_identity_sources.length, 2);
  assert.deepEqual(Array.from(result[0].details.capitalization_identity_sources,
    row => row.original_quote_key).sort(), [legacyKey, currentKey].sort());
});

test('equal overlapping prices retain both source records; conflicting price/range/period fail', () => {
  const group = helper.capitalizationWeeklyGroups([legacy, current]).groups[0];
  const pair = () => {
    const old = copy(legacy), newer = copy(current);
    newer.observed_on = old.observed_on;
    newer.period_start = old.period_start;
    newer.details.period_end = old.details.period_end;
    newer.price = old.price; newer.min_price = old.min_price; newer.max_price = old.max_price;
    return [old, newer];
  };
  let rows = pair();
  const equal = helper.mergeCapitalizationWeeklyHistory(group, rows);
  assert.equal(equal.length, 1);
  assert.equal(equal[0].price, 11975);
  assert.equal(equal[0].details.capitalization_equivalence_sources.length, 2);
  rows = pair(); rows[1].price += 1;
  assert.throws(() => helper.mergeCapitalizationWeeklyHistory(group, rows), /PRICE_CONFLICT/);
  rows = pair(); rows[1].max_price += 1;
  assert.throws(() => helper.mergeCapitalizationWeeklyHistory(group, rows), /PRICE_CONFLICT/);
  rows = pair(); rows[1].period_start = '2021-11-12';
  assert.throws(() => helper.mergeCapitalizationWeeklyHistory(group, rows), /PERIOD_CONFLICT/);
});

test('no extra keys, altered identity metadata, or more than eight candidates form a bridge', () => {
  const mutations = [
    row => { row.unit = 'unit'; },
    row => { row.market = 'Armenia Mercar'; },
    row => { row.details.price_statistic = 'median'; },
    row => { row.details.period_type = 'daily'; },
    row => { row.details.identity_dimensions.presentation = 'lata'; },
    row => { row.product_id = 'sardinas-en-salsa'; row.quote_key = keyFor(row); },
    row => { row.product_name = 'Sardinas frescas'; row.details.identity_dimensions.source_product = row.product_name; row.quote_key = keyFor(row); },
    row => { row.product_name = 'Sardinas en Lata'; },
    row => { row.quote_key = '0'.repeat(64); },
  ];
  for (const mutate of mutations) {
    const altered = copy(current); mutate(altered);
    assert.equal(helper.capitalizationWeeklyGroups([legacy, altered]).groups.length, 0);
  }
  const variants = [
    'Sardinas en lata', 'sardinas en lata', 'SARDINAS EN LATA', 'Sardinas En Lata',
    'SARDINAS en lata', 'sardinas En lata', 'SARDINAS EN lata', 'sardinas EN LATA', 'sArdinas en lata',
  ];
  const cards = variants.map((name, index) => {
    const row = copy(current); row.product_name = name;
    row.details.identity_dimensions.source_product = name;
    row.quote_key = keyFor(row); row.observed_on = `2026-10-0${(index % 8) + 1}`;
    row.details.period_end = row.observed_on;
    row.period_start = row.observed_on;
    return row;
  });
  assert.equal(helper.capitalizationWeeklyGroups(cards).groups.length, 0);
});

test('NFC casefold keeps accents and punctuation significant', () => {
  assert.equal(helper.nfcCaseFold('Árbol'), helper.nfcCaseFold('A\u0301RBOL'));
  assert.notEqual(helper.nfcCaseFold('Arbol'), helper.nfcCaseFold('Árbol'));
  assert.notEqual(helper.nfcCaseFold('Sardinas en lata'), helper.nfcCaseFold('Sardinas, en lata'));
});

function service({ revised = false, conflict = false, omitLegacyCard = false } = {}) {
  let clock = 0;
  const events = [], shared = {};
  class Clock extends Date { static now() { return clock; } }
  const ctx = { Date: Clock, globalThis: shared };
  const cache = load('snapshot-cache', { 'server-only': {} }, ctx);
  const quoteRows = () => {
    const rows = [legacy, ...currentRows].map(copy);
    if (revised) {
      const last = rows.at(-1);
      last.price += 5; last.min_price += 5; last.max_price += 5;
    }
    if (conflict) {
      const old = copy(legacy), newer = copy(current);
      newer.observed_on = old.observed_on;
      newer.period_start = old.period_start;
      newer.details.period_end = old.details.period_end;
      newer.price += 10;
      rows.push(newer);
    }
    return rows;
  };
  const payloads = () => {
    const rows = quoteRows();
    return [...(omitLegacyCard ? [] : [rows[0]]), rows.at(-1)].map(row => ({ ...row, previous_price: null }));
  };
  const query = async (sql, args = []) => {
    events.push({ sql, args });
    if (sql.includes('WITH candidates AS MATERIALIZED'))
      return { rows: quoteRows().filter(row => row.quote_key === args[0]) };
    if (sql.includes('SELECT payload FROM official_catalog_current') && sql.includes('quote_key=$1'))
      return { rows: quoteRows().filter(row => row.quote_key === args[0]).map(row => ({ payload: { ...row, previous_price: null } })) };
    if (sql.includes('SELECT payload FROM official_catalog_current'))
      return { rows: payloads().map(payload => ({ payload })) };
    return { rows: [] };
  };
  const identity = () => ({
    collapseAcelgaWeeklyCatalog: rows => rows,
    isAcelgaWeeklyConflict: () => false,
    isAcelgaWeeklyKey: () => false,
    mergeAcelgaWeeklyHistory: rows => rows,
    ACELGA_WEEKLY_CANONICAL_KEY: 'not-this-key', ACELGA_WEEKLY_KEYS: [],
  });
  const emptyCorabastos = () => ({
    collapseWeeklyCorabastosCatalog: rows => rows,
    isWeeklyCorabastosConflict: () => false,
    mergeWeeklyCorabastosHistory: (_group, rows) => rows,
    weeklyCorabastosGroups: () => ({ groups: [], byKey: new Map() }),
    expectedWeeklyCorabastosKey: () => null,
    WEEKLY_CORABASTOS_MARKETS: [],
  });
  const minorista = () => ({
    MINORISTA_WEEKLY_CANONICAL_KEY: 'not-this-key', MINORISTA_WEEKLY_KEYS: [],
    collapseMinoristaWeeklyCatalog: rows => rows, isMinoristaWeeklyConflict: () => false,
    isMinoristaWeeklyKey: () => false, mergeMinoristaWeeklyHistory: rows => rows,
    standaloneMinoristaWeeklyHistory: rows => rows,
  });
  const aguacate = () => ({
    AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY: 'not-this-key', AGUACATE_BUCARAMANGA_WEEKLY_KEYS: [],
    collapseAguacateBucaramangaWeeklyCatalog: rows => rows,
    isAguacateBucaramangaWeeklyConflict: () => false, isAguacateBucaramangaWeeklyKey: () => false,
    mergeAguacateBucaramangaWeeklyHistory: rows => rows,
    standaloneAguacateBucaramangaWeeklyHistory: rows => rows,
  });
  const route = load('official-references', {
    'server-only': {}, './db': { database: () => ({ query,
      connect: async () => ({ query, release: () => events.push({ release: true }) }) }) },
    './summary-references': { summaryReference: async () => null }, './snapshot-cache': cache,
    './official-market-regions': { officialMarketRegions: async rows => rows },
    '../label-normalization': { normalizeOfficialLabels: row => row, normalizeLabel: value => value },
    '../category-hierarchy': require('./helpers/category-hierarchy.cjs')(),
    './acelga-weekly-continuity': identity(), './weekly-corabastos-continuity': emptyCorabastos(),
    './minorista-weekly-continuity': minorista(),
    './aguacate-bucaramanga-weekly-continuity': aguacate(),
    './weekly-capitalization-continuity': helper,
  }, ctx);
  return { route, events, setClock: value => { clock = value; }, revise: () => { revised = true; } };
}

test('maintained readers collapse the catalog and resolve canonical and saved legacy URLs through one bounded history snapshot', async () => {
  const app = service();
  const cards = await app.route.latestOfficialReferences();
  assert.equal(cards.length, 1);
  assert.equal(cards[0].quote_key, currentKey);
  assert.equal(cards[0].details.capitalization_identity_sources.length, 2);
  assert.equal(app.events.filter(event => event.sql?.includes('WITH candidates AS MATERIALIZED')).length, 0,
    'catalog stays on the existing cached current snapshot');
  const saved = await app.route.officialReferences(new URLSearchParams('id=' + legacyKey));
  const canonical = await app.route.officialReferences(new URLSearchParams('id=' + currentKey));
  assert.equal(saved.history.length, 581);
  assert.equal(canonical.history.length, 581);
  assert.equal(saved.reference.quote_key, currentKey);
  assert.equal(canonical.reference.quote_key, currentKey);
  const historyReads = app.events.filter(event => event.sql?.includes('WITH candidates AS MATERIALIZED'));
  assert.deepEqual(historyReads.map(event => event.args[0]).sort(), [legacyKey, currentKey].sort());
  assert.equal(app.events.filter(event => event.sql === 'BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ').length, 1);
  assert.equal(app.events.filter(event => event.sql === 'COMMIT').length, 1);
});

test('an absent legacy current card keeps the ordinary standalone one-key history behavior', async () => {
  const app = service({ omitLegacyCard: true });
  const saved = await app.route.officialReferences(new URLSearchParams('id=' + legacyKey));
  assert.equal(saved.history.length, 1);
  assert.equal(saved.reference.quote_key, legacyKey);
  assert.equal(app.events.filter(event => event.sql?.includes('official_catalog_current') && event.sql.includes('quote_key=$1')).length, 1,
    'the only metadata lookup is the pre-existing bounded Corabastos classifier');
  assert.equal(app.events.filter(event => event.sql?.includes('WITH candidates AS MATERIALIZED')).length, 1);
});

test('refreshed raw source rows replace the expired merged-history snapshot for both saved spellings', async () => {
  const app = service();
  const before = await app.route.officialReferences(new URLSearchParams('id=' + legacyKey));
  app.revise(); app.setClock(300_000);
  const refreshed = await app.route.officialReferences(new URLSearchParams('id=' + currentKey));
  assert.equal(refreshed.history.length, 581);
  assert.equal(refreshed.reference.price, before.reference.price + 5);
  assert.equal(refreshed.reference.quote_key, currentKey);
  assert.equal(app.events.filter(event => event.sql?.includes('WITH candidates AS MATERIALIZED')).length, 4,
    'both keys are fetched again after the current snapshot expires');
});

test('maintained detail resolution propagates same-date source conflicts for the API 409 path', async () => {
  const app = service({ conflict: true });
  await assert.rejects(app.route.officialReferences(new URLSearchParams('id=' + legacyKey)),
    error => helper.isWeeklyCapitalizationConflict(error) && /PRICE_CONFLICT/.test(error.message));
});

test('the existing references route returns 409 with explicit weekly source-conflict feedback', async () => {
  const response = { json: (body, options) => ({ body, status: options.status }) };
  let conflictError;
  try {
    const group = helper.capitalizationWeeklyGroups([legacy, current]).groups[0];
    const first = copy(legacy), second = copy(current);
    second.observed_on = first.observed_on; second.period_start = first.period_start;
    second.details.period_end = first.details.period_end;
    second.price += 1;
    helper.mergeCapitalizationWeeklyHistory(group, [first, second]);
  } catch (error) { conflictError = error; }
  assert.ok(helper.isWeeklyCapitalizationConflict(conflictError));
  const module = { exports: {} };
  const routePath = path.join(__dirname, '../src/app/api/references/route.ts');
  const source = fs.readFileSync(routePath, 'utf8');
  const routeMocks = {
    '@/lib/server/official-references': { officialReferences: async () => { throw conflictError; } },
    '@/lib/server/weekly-capitalization-continuity': helper,
    'next/server': { NextResponse: response },
  };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { module, exports: module.exports,
    require: key => routeMocks[key] || require(key), Error });
  const routeModule = module.exports;
  const result = await routeModule.GET({ nextUrl: { searchParams: new URLSearchParams() } });
  assert.equal(result.status, 409);
  assert.match(result.body.error, /precios oficiales incompatibles para una misma semana/i);
  assert.equal(result.body.code, 'WEEKLY_CAPITALIZATION_PRICE_CONFLICT');
});

function keyFor(row) {
  const identity = {
    product_id: row.product_id, series: row.series, market: row.market,
    currency: row.currency, unit: row.unit, basis: row.basis,
    dimensions: row.details.identity_dimensions,
  };
  const py = value => typeof value === 'string' ? JSON.stringify(value) :
    value && typeof value === 'object' ? `{${Object.keys(value).sort().map(k => `${py(k)}: ${py(value[k])}`).join(', ')}}` : JSON.stringify(value);
  return require('node:crypto').createHash('sha256').update(py(identity), 'utf8').digest('hex');
}
