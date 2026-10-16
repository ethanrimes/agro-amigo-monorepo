const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function catalogWith(quotes, { products = [], names = [] } = {}) {
  const exports = {};
  const mocks = {
    'server-only': {},
    './city-publication-epoch': { cityPublicationEpoch: async () => '0' },
    './city-catalog-names': { cityCatalogNames: async () => names },
    './queries': { catalog: async () => ({ products, regions: [], cacheExpiresAt: Date.now() + 300000 }) },
    './summary-references': { latestSummaryReferences: async () => [] },
    './official-references': { latestOfficialReferenceSnapshot: async () => ({ value: quotes, expires: Date.now() + 300000 }) },
    '../label-normalization': require('./helpers/load-label-normalization.cjs')(),
  };
  const labels={};
  new Function('exports',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/filter-labels.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(labels);
  mocks['../filter-labels']=labels;
  const frequency = {};
  new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
    '../src/lib/catalog-frequency.ts'), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText)(frequency);
  mocks['../catalog-frequency'] = frequency;
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/catalog.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports, require: name => mocks[name], URLSearchParams, console });
  return exports.unifiedCatalog;
}

function actualCatalogDisplay() {
  const load = (filename, mocks = {}) => {
    const exports = {};
    new Function('exports', 'require', ts.transpileModule(
      fs.readFileSync(path.join(__dirname, '../src/lib', filename), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
    ).outputText)(exports, name => mocks[name]);
    return exports;
  };
  const math = load('planning-math.ts');
  const market = load('market-types.ts');
  return load('catalog-display.ts', { './planning-math': math, './market-types': market });
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

test('Spanish source periods survive official selection into searchable suggestion text', async () => {
  const variants = [
    ['mensual', 'Mensual', 'monthly'],
    ['SEMANAL', 'Semanal', 'weekly'],
    ['diario', 'Diario', 'daily'],
    ['Quincenal', 'Quincenal', 'daily'],
    ['trimestral', 'Trimestral', 'daily'],
    ['semestre', 'Semestral', 'daily'],
    ['anual', 'Anual', 'daily'],
    ['semana de referencia', 'Semanal', 'weekly'],
  ];
  const quotes = variants.map(([period_type], i) => ({ ...milk,
    quote_key: 'fedegan-' + i, series: 'fedegan-milk',
    basis: 'Precio publicado de leche cruda', details: { period_type },
  }));
  const { products } = await catalogWith(quotes)();
  const { catalogSuggestionDetail } = actualCatalogDisplay();
  products.forEach((product, i) => {
    assert.equal(product.frequency_label, variants[i][1]);
    assert.equal(product.period, variants[i][2]);
    assert.ok(catalogSuggestionDetail(product).includes(' · ' + variants[i][1] + ' · '));
    if (variants[i][1] !== 'Diario') assert.doesNotMatch(catalogSuggestionDetail(product), /Diario/);
    for (const key of ['price', 'date', 'unit', 'currency', 'market', 'basis']) {
      assert.equal(product[key], key === 'date' ? quotes[i].observed_on : quotes[i][key], key);
    }
    assert.equal(product.identity, 'reference:' + quotes[i].quote_key);
    assert.equal(product.href, '/references/' + quotes[i].quote_key);
  });
});

test('unknown cadence is omitted instead of asserting daily from a compatibility bucket', async () => {
  const quotes = [
    { ...milk, quote_key: 'unknown', series: 'colombia-current', details: {} },
    { ...milk, quote_key: 'declared-unknown', series: 'dane-weekly', details: {period_type:'variable'} },
    { ...milk, quote_key: 'weekly-series', series: 'dane-weekly', details: {} },
  ].map(quote => ({...quote, basis:'Precio publicado'}));
  const { products } = await catalogWith(quotes)();
  const { catalogSuggestionDetail } = actualCatalogDisplay();
  for (const product of products.slice(0, 2)) {
    assert.equal(product.frequency_label, null);
    assert.doesNotMatch(catalogSuggestionDetail(product), /Diario|Semanal|Mensual/);
  }
  assert.equal(products[2].frequency_label, 'Semanal');
  assert.match(catalogSuggestionDetail(products[2]), /Semanal/);
});

test('regional catalog keeps exact verified DANE market quotes and explains excluded unknown geography',async()=>{
 const oil={...milk,quote_key:'oil-2012',series:'dane-daily-query',market:'Armenia, Mercar',
  department:'Quindío',unit:'litre',price:3792,details:{period_type:'daily'}};
 const unverified={...oil,quote_key:'pork-unverified',market:'Armenia, Frigocafé',department:undefined};
 const other={...oil,quote_key:'other-region',department:'Cundinamarca'};
 const catalog=await catalogWith([oil,unverified,other,milk])('QUINDIO');
 assert.deepEqual(Array.from(catalog.products,p=>p.quote_key),['oil-2012']);
 assert.equal(catalog.products[0].price,3792);
 assert.equal(catalog.products[0].department,'Quindío');
 assert.equal(catalog.filters.excluded_nonregional_count,2,'Other verified departments are filtered normally, not described as unknown geography');
 assert.ok(catalog.filters.excluded_nonregional_reason.includes('sin departamento verificado'));
 assert.ok(catalog.regions.includes('Quindío'));
});

test('market-qualified search finds the canonical product while keeping its own price and source', async () => {
  const product = { id: 'naranja-sweet', name: 'Naranja Sweet', category: 'Frutas', image_key: 'produce',
    price: 1999, previous_price: null, date: '2026-08-31', market_count: 2, unit: 'kg',
    source: 'DANE · SIPSA', period: 'monthly', series: 'monthly',
    presentation: 'Por unidad de medida', units: '1 kg' };
  const another = { ...product, id: 'naranja-other', price: 2100 };
  const names = [{ product_id: product.id, product_name: 'Naranja sweet', latest_date: '2026-10-06' }];
  const mercar = { ...milk, quote_key: 'naranja-armenia-reference', product_id: product.id,
    product_name: product.name, market: 'Armenia, Mercar', department: 'Quindío',
    series: 'dane-daily-query', observed_on: '2016-01-18', price: 1200 };
  const unknown = { ...mercar, quote_key: 'unverified-location', market: 'Mercado sin departamento',
    department: undefined };
  const matches = actualCatalogDisplay().catalogMatches;
  const catalog = await catalogWith([mercar, unknown], { products: [product, another], names })();
  const canonical = catalog.products.find(p => p.id === product.id);
  assert.ok(canonical);
  assert.equal(matches(canonical, 'Naranja sweet Armenia'), true);
  assert.equal(matches(catalog.products.find(p => p.id === another.id), 'Naranja sweet Armenia'), false);
  assert.equal(matches(canonical, 'Naranja sweet Mercado sin departamento'), false);
  assert.equal(canonical.price, product.price);
  assert.equal(canonical.source, product.source);
  assert.match(canonical.href, /^\/product\/naranja-sweet\?series=monthly/);
  const reference = catalog.products.find(p => p.quote_key === mercar.quote_key);
  assert.equal(reference.price, mercar.price);
  assert.equal(reference.href, '/references/' + mercar.quote_key);
  const elsewhere = await catalogWith([mercar], { products: [product], names })('Cundinamarca');
  assert.equal(matches(elsewhere.products[0], 'Naranja sweet Armenia'), false,
    'a verified reference from another department must not add a regional search alias');
});
