const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function catalogWith(quotes) {
  const exports = {};
  const mocks = {
    'server-only': {},
    './city-catalog-names': { cityCatalogNames: async () => [] },
    './queries': { catalog: async () => ({ products: [], regions: [], cacheExpiresAt: Date.now() + 300000 }) },
    './summary-references': { latestSummaryReferences: async () => [] },
    './official-references': { latestOfficialReferences: async () => quotes },
  };
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/catalog.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: name => mocks[name], URLSearchParams, console });
  return exports.unifiedCatalog;
}

const milk = {
  quote_key: 'milk-macroregion-fixture', product_id: 'leche-cruda-en-finca-macrorregional',
  product_name: 'Leche cruda en finca · promedio macrorregional', category: 'Leche cruda en finca',
  publisher: 'DANE', series: 'dane-milk-macroregion',
  basis: 'Promedio mensual publicado en finca por macrorregión', currency: 'COP',
  unit: 'litro', market: 'Costa Caribe', observed_on: '2025-12-31',
  price: 1930, previous_price: 1893,
  details: { period_type: 'monthly', period_end: '2025-12-31', price_statistic: 'published_mean' },
};

test('monthly milk chart metadata reaches the catalog without a daily classification or identity change', async () => {
  const product = (await catalogWith([milk])()).products[0];
  assert.equal(product.period, 'monthly');
  assert.equal(product.identity, 'reference:' + milk.quote_key);
  assert.equal(product.href, '/references/' + milk.quote_key);
  for (const key of ['price', 'previous_price', 'currency', 'unit', 'basis', 'market', 'series']) {
    assert.equal(product[key], milk[key], key);
  }
  assert.equal(product.map_supported, false);
});

test('existing series-based monthly, weekly and daily references retain their periods', async () => {
  const variants = [
    ['world-bank-monthly', {}, 'monthly'],
    ['dane-weekly', {}, 'weekly'],
    ['publisher-period', { period_type: 'weekly' }, 'weekly'],
    ['colombia-current', {}, 'daily'],
  ];
  const quotes = variants.map(([series, details], i) => ({ ...milk, quote_key: String(i), series, details }));
  const { products } = await catalogWith(quotes)();
  assert.equal(products.length, variants.length);
  products.forEach((p, i) => assert.equal(p.period, variants[i][2], p.series));
});
