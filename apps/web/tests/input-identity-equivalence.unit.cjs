const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const root = path.resolve(__dirname, '../../..');
const ids = {
  canonical: 'wuxal-tapa-negra-16-16-12-1-litro',
  legacy: 'wuxal-16-16-12-tapa-negra-1-litro',
};
const names = {
  canonical: 'Wuxal tapa negra 16-16-12',
  legacy: 'Wuxal 16-16-12 tapa negra',
};
const group = JSON.parse(fs.readFileSync(path.join(root, 'shared/input-identity-equivalences.json'), 'utf8'));

function load(file, mocks = {}) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/lib', file), 'utf8');
  new Function('exports', 'require', ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText)(exports, name => name === '../../../../shared/input-identity-equivalences.json'
    ? group : (mocks[name] || {}));
  return exports;
}

const equivalence = load('input-identity-equivalence.ts');
const validRow = (overrides = {}) => ({
  id: ids.legacy,
  name: names.legacy,
  category: 'Fertilizantes y enmiendas',
  presentation: '1 litro',
  brand: '', registration: '', product_line: '',
  department: 'Quindío', municipality: 'Armenia',
  observed_on: '2013-03-31', price: 29175,
  document_id: 'old-pdf', source_locator: 'PDF page 13',
  ...overrides,
});

test('only the two exact Wuxal word-order members pass all metadata guards', () => {
  for (const row of [validRow(), validRow({ name: 'WUXAL 16-16-12 TAPA NEGRA' }),
    validRow({ id: ids.canonical, name: 'Wuxal Tapa Negra 16-16-12' })]) {
    assert.equal(equivalence.resolveInputIdentity(row.id, row).canonicalId, ids.canonical);
  }
  for (const row of [
    validRow({ name: 'Wuxal' }),
    validRow({ name: 'Wuxal 15-15-15 tapa negra' }),
    validRow({ presentation: '1 galón' }),
    validRow({ category: 'Otro producto' }),
    validRow({ brand: 'Marca' }),
    validRow({ registration: 'ICA 12' }),
    validRow({ product_line: 'Línea 1' }),
  ]) {
    assert.equal(equivalence.resolveInputIdentity(row.id, row).canonicalId, row.id);
    assert.equal(equivalence.canonicalizeInputRow(row).name, row.name);
  }
  assert.throws(() => equivalence.assertInputIdentityMembers(
    [validRow({ registration: 'ICA 12' })], [ids.canonical, ids.legacy]),
  equivalence.InputIdentityGuardError);
  assert.deepEqual(equivalence.resolveInputIdentity(ids.legacy).memberIds, [ids.canonical, ids.legacy]);
  assert.deepEqual(equivalence.resolveInputIdentity(ids.canonical).memberIds, [ids.canonical, ids.legacy]);
});

test('canonical rows preserve their original identity and source locator', () => {
  const source = validRow();
  const row = equivalence.canonicalizeInputRow(source);
  assert.equal(row.id, ids.canonical);
  assert.equal(row.name, group.groups[0].canonical_name);
  assert.equal(row.source_input_id, ids.legacy);
  assert.equal(row.source_name, names.legacy);
  assert.equal(row.document_id, source.document_id);
  assert.equal(row.source_locator, source.source_locator);
});

test('catalog exposes conflicting latest prices and detail/map preserve both source-backed quotes', async () => {
  const rows = [
    validRow(),
    validRow({ id: ids.canonical, name: names.canonical, observed_on: '2014-04-30', price: 29317,
      document_id: 'apr-pdf', source_locator: 'PDF page 13' }),
    validRow({ id: ids.legacy, observed_on: '2014-04-30', price: 30025,
      document_id: 'conflict-pdf', source_locator: 'PDF page 14' }),
  ];
  const catalog = equivalence.canonicalInputCatalogRows(rows);
  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].id, ids.canonical);
  assert.equal(catalog[0].identity_conflict, true);
  assert.deepEqual(catalog[0].identity_conflict_quotes.map(quote => quote.price).sort(), [29317, 30025]);
  assert.throws(() => equivalence.assertNoLatestInputIdentityConflicts(rows),
    equivalence.InputIdentityConflictError);

  const places = [{ id: 'armenia', name: 'Armenia', department_id: 'quindio',
    department: 'Quindío', latitude: 4.53, longitude: -75.68 }];
  const calls = [];
  const database = { query: async (sql, args = []) => {
    calls.push({ sql, args });
    if (sql.includes('SELECT id,name,category,presentation'))
      return { rows: rows.filter(row => args[0].includes(row.id) && args[2].includes(row.municipality))
        .map(row => ({ ...row, date: row.observed_on })) };
    if (sql.includes('FROM municipality ORDER BY id')) return { rows: places };
    throw new Error(`Unexpected SQL: ${sql.slice(0, 100)}`);
  } };
  const labels = load('filter-labels.ts');
  const locations = load('input-locations.ts', { './filter-labels': labels });
  const explore = load('server/explore.ts', {
    './db': { database: () => database, WINDOW: 'observed_on<=CURRENT_DATE' },
    './planning': { inputs: async (_department, _scope, _historical, id) => {
      const memberIds = equivalence.resolveInputIdentity(id).memberIds;
      return rows.filter(row => memberIds.includes(row.id)).map(equivalence.canonicalizeInputRow);
    } },
    './price-quotes': { PRICE_QUOTES: '', filteredProduct: async () => null },
    '../filter-labels': labels,
    '../input-locations': locations,
    '../input-identity-equivalence': equivalence,
    '../pdf-locator': { pdfLocationPage: () => 13 },
    './supply-sql': { supplyQueries: () => ({}) },
    './market-sql': { marketsQuery: () => '', marketDetailQuery: () => '', marketProductsQuery: () => '' },
  });
  const detail = await explore.inputDetail(ids.legacy, 'Quindío', 'municipality', 'Armenia', true);
  assert.equal(detail.input.id, ids.canonical);
  assert.equal(detail.input.name, names.canonical);
  assert.deepEqual(detail.current_quotes.map(quote => quote.price).sort(), [29317, 30025]);
  assert.equal(new Set(detail.history.map(point => point.observation_id)).size, detail.history.length);
  assert.ok(detail.history.some(point => point.sources[0].source_input_id === ids.legacy &&
    point.sources[0].source_name === names.legacy && point.sources[0].source_locator === 'PDF page 14'));
  const historyCall = calls.find(call => call.sql.includes('SELECT id,name,category,presentation'));
  assert.ok(historyCall.sql.includes('id=ANY($1::text[])'));
  for (const identityField of ['category', 'presentation', 'brand', 'registration', 'product_line'])
    assert.ok(historyCall.sql.includes(identityField));
  assert.deepEqual(historyCall.args[0], [ids.canonical, ids.legacy]);

  await assert.rejects(explore.mapData('input', ids.legacy, 'price', {
    scope: 'municipality', history: 'all', municipality: 'Armenia', region: 'Quindío',
  }), equivalence.InputIdentityConflictError,
  'the map must refuse a single visual summary when latest source-backed prices differ');
});

test('poisoned member rows fail detail and map identity guards without rewriting source rows', async () => {
  const valid = validRow({ observed_on: '2014-04-30', price: 29317 });
  const poison = validRow({ category: 'Otra línea', presentation: '5 litros',
    brand: 'Marca distinta', registration: 'ICA-77', product_line: 'Línea distinta',
    name: 'Wuxal 15-15-15', observed_on: '2014-04-30', price: 1 });
  const savedPoison = { ...poison };
  let includePoisonInPlanner = true;
  const places = [{ id: 'armenia', name: 'Armenia', department_id: 'quindio',
    department: 'Quindío', latitude: 4.53, longitude: -75.68 }];
  const database = { query: async (sql, args = []) => {
    if (sql.includes('SELECT id,name,category,presentation'))
      return { rows: [valid, poison].filter(row => args[0].includes(row.id) && args[2].includes(row.municipality))
        .map(row => ({ ...row, date: row.observed_on })) };
    if (sql.includes('FROM municipality ORDER BY id')) return { rows: places };
    throw new Error(`Unexpected SQL: ${sql.slice(0, 100)}`);
  } };
  const labels = load('filter-labels.ts');
  const locations = load('input-locations.ts', { './filter-labels': labels });
  const explore = load('server/explore.ts', {
    './db': { database: () => database, WINDOW: 'observed_on<=CURRENT_DATE' },
    './planning': { inputs: async (_department, _scope, _historical, id) => {
      return id === ids.legacy ? [valid, ...(includePoisonInPlanner ? [poison] : [])].filter(row =>
        equivalence.resolveInputIdentity(row.id).memberIds.includes(id)).map(equivalence.canonicalizeInputRow) : [];
    } },
    './price-quotes': { PRICE_QUOTES: '', filteredProduct: async () => null },
    '../filter-labels': labels,
    '../input-locations': locations,
    '../input-identity-equivalence': equivalence,
    '../pdf-locator': { pdfLocationPage: () => 13 },
    './supply-sql': { supplyQueries: () => ({}) },
    './market-sql': { marketsQuery: () => '', marketDetailQuery: () => '', marketProductsQuery: () => '' },
  });
  await assert.rejects(explore.inputDetail(ids.legacy, 'Quindío', 'municipality', 'Armenia', true),
    equivalence.InputIdentityGuardError);
  includePoisonInPlanner = false;
  await assert.rejects(explore.inputDetail(ids.legacy, 'Quindío', 'municipality', 'Armenia', true),
    equivalence.InputIdentityGuardError, 'history query must reject a mismatched source row before mapping');
  includePoisonInPlanner = true;
  await assert.rejects(explore.mapData('input', ids.legacy, 'price', {
    scope: 'municipality', history: 'all', municipality: 'Armenia', region: 'Quindío',
  }), equivalence.InputIdentityGuardError);
  assert.deepEqual(poison, savedPoison, 'read paths must not rewrite retained source records');
});
