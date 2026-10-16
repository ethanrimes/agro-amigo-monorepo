/* Dirty catalog metadata can register an identity, never furnish a price. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);
const oracle = require('./fixtures/weekly-corabastos-source-oracle.json');
const root = path.join(__dirname, '../src/lib/server');
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const unified = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const enabled = Boolean(unified || socket?.startsWith('/tmp/agro-reference-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL' }, fn);

function load(file, mocks = {}) {
  const exports = {};
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const javascript = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  vm.runInNewContext(javascript, {
    exports, require: name => Object.hasOwn(mocks, name) ? mocks[name] : require(name),
    URLSearchParams,
  });
  return exports;
}
const weekly = load('weekly-corabastos-continuity.ts');
const acelga = load('acelga-weekly-continuity.ts');
const canonicalMarket = weekly.WEEKLY_CORABASTOS_CANONICAL_MARKET;
const sentinel = 999999999;
let db;

beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: unified ? 65443 : 65440, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of ['source_document', 'official_price_quote', 'official_source_review',
    'ingestion_asset', 'official_catalog_current'])
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query('CREATE INDEX quote_date ON official_price_quote(quote_key,observed_on DESC)');
  await db.query('CREATE INDEX review_doc ON official_source_review(document_id,source_locator)');
});
afterEach(async () => { if (db) await db.end(); db = undefined; });

async function seedCatalog(product) {
  for (const entry of product.keys) {
    const dirty = entry.market === canonicalMarket;
    const payload = {
      quote_key: entry.key, product_id: product.product_id,
      product_name: product.product_name, publisher: oracle.publisher,
      series: 'dane-weekly', basis: oracle.basis, currency: oracle.currency,
      unit: 'kg', market: entry.market, category: 'Verduras y hortalizas',
      observed_on: '2026-10-02', price: dirty ? sentinel : 1000,
      min_price: dirty ? sentinel : 900, max_price: dirty ? sentinel : 1100,
      previous_price: dirty ? sentinel : null,
      details: { identity_dimensions: { source_product: product.product_name } },
    };
    assert.equal(weekly.expectedWeeklyCorabastosKey(payload), entry.key);
    await db.query(`INSERT INTO official_catalog_current(quote_key,payload,dirty,version)
      VALUES($1,$2,$3,'official-catalog-v1')`, [entry.key, payload, dirty]);
  }
}

async function seedQuote(product, example, options = {}) {
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
    reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,'application/pdf','original',$4,decode('00','hex'),
      '2026-10-02T12:00:00Z') ON CONFLICT DO NOTHING`,
  [example.document_id, product.product_name + ' ' + example.date,
    'https://www.dane.gov.co/weekly/' + example.document_id + '.pdf', example.date]);
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,
    quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,
    observed_on,price,min_price,max_price,source_page,parsed_at,details)
    VALUES($1,$2,$3,$4,$5,$6,'Verduras y hortalizas','DANE · SIPSA',
      'dane-weekly','Precio mayorista semanal','COP','kg',$7,$8,$9,$10,$11,$12,$13,$14)`,
  [example.document_id, example.source_locator, options.version || 'dane-weekly-v19',
    example.key, product.product_id, product.product_name, example.market, example.date,
    options.price ?? example.price, options.min ?? example.min, options.max ?? example.max,
    example.source_page, options.parsedAt || '2026-10-02T12:00:00Z',
    { identity_dimensions: { source_product: product.product_name } }]);
}

async function seedProducts() {
  for (const product of oracle.products) {
    await seedCatalog(product);
    for (const example of product.source_examples) await seedQuote(product, example);
  }
}

function route() {
  const events = [], snapshots = new Map();
  const query = async (sql, params) => {
    events.push({ sql, params });
    return db.query(sql, params);
  };
  const connection = { query, release() {} };
  const mockedDatabase = { query, connect: async () => connection };
  const module = load('official-references.ts', {
    'server-only': {},
    './db': { database: () => mockedDatabase },
    './summary-references': { summaryReference: async () => null },
    './snapshot-cache': { snapshotCache: (_ttl, _capacity, name) => {
      const values = snapshots.get(name) || new Map();
      snapshots.set(name, values);
      const cached = (key, loader) => {
        if (!values.has(key)) values.set(key, Promise.resolve().then(loader));
        return values.get(key);
      };
      cached.expiresAt = () => 0;
      cached.withExpiry = async (key, loader) => ({ value: await cached(key, loader), expires: 0 });
      return cached;
    } },
    './official-market-regions': { officialMarketRegions: async rows => rows },
    './acelga-weekly-continuity': acelga,
    './weekly-corabastos-continuity': weekly,
    './minorista-weekly-continuity': load('minorista-weekly-continuity.ts'),
    './aguacate-bucaramanga-weekly-continuity': load('aguacate-bucaramanga-weekly-continuity.ts'),
    '../label-normalization': { normalizeOfficialLabels: row => row, normalizeLabel: value => value },
    '../category-hierarchy': require('./helpers/category-hierarchy.cjs')(),
  });
  return { module, events };
}

function queryCount(events, kind) {
  if (kind === 'registration')
    return events.filter(event => event.sql.includes('FROM official_catalog_current WHERE quote_key=')).length;
  if (kind === 'history')
    return events.filter(event => event.sql.includes('WITH candidates AS MATERIALIZED')).length;
  if (kind === 'cleanCatalog')
    return events.filter(event => event.sql.includes('payload IS NOT NULL AND NOT dirty')).length;
  throw Error('Unknown query kind');
}

check('dirty canonical metadata recovers exact Ajo and Ahuyama historical originals without catalog prices', async () => {
  await seedProducts();
  const { module, events } = route();
  const catalog = await module.latestOfficialReferences();
  assert.equal(queryCount(events, 'cleanCatalog'), 1);
  assert.ok(catalog.every(card => card.price !== sentinel &&
    card.min_price !== sentinel && card.max_price !== sentinel &&
    card.previous_price !== sentinel));
  assert.ok(oracle.products.every(product => !catalog.some(card => card.quote_key ===
    product.keys.find(entry => entry.market === canonicalMarket).key)));
  const searched = await module.officialReferences(new URLSearchParams('q=Ajo'));
  assert.ok(searched.rows.every(card => card.price !== sentinel));
  for (const product of oracle.products) {
    const start = events.length, old = product.keys[0], canonical =
      product.keys.find(entry => entry.market === canonicalMarket);
    const result = await module.officialReferences(new URLSearchParams('id=' + old.key));
    assert.ok(result);
    assert.equal(result.reference.quote_key, canonical.key);
    assert.deepEqual(Array.from(result.history, row => row.observed_on),
      ['2012-06-22', '2017-05-19', '2018-03-09', '2022-06-24']);
    for (const example of product.source_examples) {
      const row = result.history.find(item => item.observed_on === example.date);
      assert.deepEqual([row.price, row.min_price, row.max_price],
        [example.price, example.min, example.max]);
      assert.equal(row.document_id, example.document_id);
      assert.equal(row.source_locator, example.source_locator);
      assert.equal(row.details.source_market_literal, example.market);
    }
    assert.ok(result.history.every(row => row.price !== sentinel &&
      row.previous_price !== sentinel));
    const spent = events.slice(start);
    assert.equal(queryCount(spent, 'registration'), 2);
    assert.equal(queryCount(spent, 'history'), 5);
    const before = events.length;
    const bookmarked = await module.officialReferences(new URLSearchParams('id=' + canonical.key));
    assert.equal(bookmarked, result, 'A canonical bookmark shares the guarded historical snapshot');
    assert.equal(queryCount(events.slice(before), 'history'), 0);
  }
});

check('reviewed quote and superseded older parse remain retained but do not enter dirty-canonical history', async () => {
  await seedProducts();
  const product = oracle.products.find(row => row.product_id === 'ajo');
  const reviewed = product.source_examples.find(row => row.date === '2022-06-24');
  const revised = product.source_examples.find(row => row.date === '2018-03-09');
  await db.query(`INSERT INTO official_source_review(document_id,source_locator,parser_version,
    record,reason,created_at) VALUES($1,$2,'audit','{}'::jsonb,'Reviewed source cell',
      '2026-10-03T12:00:00Z')`, [reviewed.document_id, reviewed.source_locator]);
  await seedQuote(product, revised, {
    version: 'dane-weekly-v18', price: 888888888, min: 888888888,
    max: 888888888, parsedAt: '2026-10-01T12:00:00Z',
  });
  const { module, events } = route();
  const result = await module.officialReferences(new URLSearchParams('id=' + product.keys[0].key));
  assert.deepEqual(Array.from(result.history, row => row.observed_on),
    ['2012-06-22', '2017-05-19', '2018-03-09']);
  assert.equal(result.history.find(row => row.observed_on === revised.date).price, revised.price);
  assert.ok(result.history.every(row => row.price !== sentinel && row.price !== 888888888));
  assert.equal(queryCount(events, 'history'), 5);
  assert.equal((await db.query('SELECT count(*) FROM official_price_quote')).rows[0].count, '9');
  assert.equal((await db.query('SELECT count(*) FROM official_source_review')).rows[0].count, '1');
});

check('tampered hash or source dimensions cannot turn a dirty payload into an unrelated merged product', async () => {
  await seedProducts();
  const ahuyama = oracle.products.find(row => row.product_id === 'ahuyama');
  const ajo = oracle.products.find(row => row.product_id === 'ajo');
  const canonical = ahuyama.keys.find(entry => entry.market === canonicalMarket);
  for (const tamper of [
    payload => { payload.quote_key = ajo.keys[0].key; },
    payload => { payload.details.identity_dimensions.source_product = 'Ajo'; },
  ]) {
    const saved = (await db.query('SELECT payload FROM official_catalog_current WHERE quote_key=$1',
      [canonical.key])).rows[0].payload;
    const changed = structuredClone(saved);
    tamper(changed);
    await db.query('UPDATE official_catalog_current SET payload=$2 WHERE quote_key=$1',
      [canonical.key, changed]);
    const { module, events } = route();
    const result = await module.officialReferences(new URLSearchParams('id=' + ahuyama.keys[0].key));
    assert.ok(result && result.history.length < 4, 'Fallback is only the requested literal key');
    assert.ok(result.history.every(row => row.product_id === 'ahuyama' && row.price !== sentinel));
    assert.ok(queryCount(events, 'registration') <= 2);
    assert.ok(queryCount(events, 'history') <= 1);
    const other = await module.officialReferences(new URLSearchParams('id=' + ajo.keys[0].key));
    assert.equal(other.history.length, 4, 'Unrelated clean product retains its independent history');
    await db.query('UPDATE official_catalog_current SET payload=$2 WHERE quote_key=$1',
      [canonical.key, saved]);
  }
});
