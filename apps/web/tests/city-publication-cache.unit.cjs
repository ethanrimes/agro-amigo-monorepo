const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const server = path.join(__dirname, '../src/lib/server');
const categoryPathSql = require('./helpers/load-category-path-sql.cjs')();
function load(name, mocks) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server, name), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: key => key === 'server-only' ? {} : key.endsWith('category-path-sql') ? categoryPathSql : mocks[key], console, URLSearchParams });
  return exports;
}

test('city names and regional report invalidate five-minute snapshots after a child conflict', async () => {
  let epoch = '0', nameReads = 0, regionalReads = 0;
  const eligibility = { cityPublicationEpoch: async () => epoch };
  const names = load('city-catalog-names.ts', {
    './city-publication-epoch': eligibility,
    './catalog-sql': { CITY_CATALOG_NAMES_SQL: 'names' },
    './db': { database: () => ({ query: async () => ({ rows: [{ product_id: 'city', product_name: ++nameReads === 1 ? 'old' : 'new' }] }) }) },
  });
  const snapshots = new Map();
  const regional = load('regional-prices.ts', {
    './city-publication-epoch': eligibility,
    './city-market-alias': load('city-market-alias.ts', {}),
    './snapshot-cache': { snapshotCache: () => async (key, read) => {
      if (!snapshots.has(key)) snapshots.set(key, await read());
      return snapshots.get(key);
    } },
    './db': { database: () => ({ query: async () => ({ rows: [{ product_name: ++regionalReads === 1 ? 'old' : 'new' }] }) }) },
  });
  assert.equal((await names.cityCatalogNames())[0].product_name, 'old');
  assert.equal((await regional.latestRegionalPrices())[0].product_name, 'old');
  epoch = '1';
  assert.equal((await names.cityCatalogNames())[0].product_name, 'new');
  assert.equal((await regional.latestRegionalPrices())[0].product_name, 'new');
  assert.equal(nameReads, 2);
  assert.equal(regionalReads, 2);
});

test('unified catalog cache re-reads canonical rows when conflict epoch advances', async () => {
  let epoch = '0', reads = 0;
  const catalog = load('catalog.ts', {
    './city-publication-epoch': { cityPublicationEpoch: async () => epoch },
    './city-catalog-names': { cityCatalogNames: async () => [] },
    './queries': { catalog: async () => { reads++; return { products: [], regions: [], cacheExpiresAt: Infinity }; } },
    './summary-references': { latestSummaryReferences: async () => [] },
    './official-references': { latestOfficialReferenceSnapshot: async () => ({ value: [], expires: Infinity }) },
    '../filter-labels': { departmentLabels: values => values, departmentKey: value => value },
    '../label-normalization': { normalizeLabel: value => value },
  });
  await catalog.unifiedCatalog();
  await catalog.unifiedCatalog();
  assert.equal(reads, 1);
  epoch = '1';
  await catalog.unifiedCatalog();
  assert.equal(reads, 2);
});

test('a conflict committed during an in-flight catalog read cannot return its stale result', async () => {
  let epoch = '0', reads = 0, release;
  const gate = new Promise(resolve => { release = resolve; });
  const catalog = load('catalog.ts', {
    './city-publication-epoch': { cityPublicationEpoch: async () => epoch },
    './city-catalog-names': { cityCatalogNames: async () => [] },
    './queries': { catalog: async () => {
      reads++;
      if (reads === 1) await gate;
      return { products: [], regions: [], cacheExpiresAt: Infinity };
    } },
    './summary-references': { latestSummaryReferences: async () => [] },
    './official-references': { latestOfficialReferenceSnapshot: async () => ({ value: [], expires: Infinity }) },
    '../filter-labels': { departmentLabels: values => values, departmentKey: value => value },
    '../label-normalization': { normalizeLabel: value => value },
  });
  const pending = catalog.unifiedCatalog();
  for (let i = 0; i < 10 && !reads; i++) await Promise.resolve();
  assert.equal(reads, 1);
  epoch = '1';
  release();
  await pending;
  assert.equal(reads, 2, 'the request retries under the committed conflict epoch');
});
