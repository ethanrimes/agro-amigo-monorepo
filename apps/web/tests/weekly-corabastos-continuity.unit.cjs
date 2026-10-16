const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const oracle = require('./fixtures/weekly-corabastos-source-oracle.json');
const eggOracle = require('./fixtures/weekly-corabastos-eggs-source-oracle.json');
const server = path.join(__dirname, '../src/lib/server');
function load(file, mocks = {}) {
  const exports = {};
  const source = fs.readFileSync(path.join(server, file), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { exports, require: name => Object.hasOwn(mocks, name) ? mocks[name] : require(name), URLSearchParams });
  return exports;
}
const general = load('weekly-corabastos-continuity.ts');
const acelga = load('acelga-weekly-continuity.ts');
const canonicalMarket = general.WEEKLY_CORABASTOS_CANONICAL_MARKET;
function card(product, entry, date = '2026-10-02', price = 2000) {
  return { quote_key: entry.key, market: entry.market,
    product_id: product.product_id, product_name: product.product_name,
    publisher: oracle.publisher, series: 'dane-weekly', basis: oracle.basis,
    currency: oracle.currency, unit: oracle.unit, category: 'Verduras y hortalizas',
    observed_on: date, price, min_price: price - 100, max_price: price + 100,
    previous_price: price - 50, document_id: 'current-'+product.product_id,
    source_locator: 'PDF page 4, current', source_page: 4,
    source_url: 'https://www.dane.gov.co/weekly.pdf',
    details: { identity_dimensions: { source_product: product.product_name } } };
}
const cardsFor = product => product.keys.map(entry => card(product, entry));
function fixture() {
  const cards = oracle.products.flatMap(cardsFor);
  const history = Object.fromEntries(cards.map(row => [row.quote_key, []]));
  for (const product of oracle.products) {
    for (const example of product.source_examples) {
      const entry = product.keys.find(key => key.key === example.key);
      const row = card(product, entry, example.date, example.price);
      Object.assign(row, { min_price: example.min, max_price: example.max,
        document_id: example.document_id, source_locator: example.source_locator,
        source_page: example.source_page });
      history[example.key].push(row);
    }
    const canonical = product.keys.find(key => key.market === canonicalMarket);
    history[canonical.key].push(card(product, canonical));
  }
  return { cards, history };
}

test('source-bound hashes validate ten original keys and group two products without mixing units or series', () => {
  const { cards } = fixture();
  for (const row of cards) assert.equal(general.expectedWeeklyCorabastosKey(row), row.quote_key);
  const egg = { ...cards[0], quote_key: 'egg-reference', product_id: 'huevo-rojo-a', product_name: 'Huevo rojo A', unit: 'unit' };
  const daily = { ...cards[0], quote_key: 'daily-reference', series: 'dane-daily-query' };
  const quality = { ...cards[0], quote_key: 'quality-reference', series: 'corabastos-quality', unit: 'ATADO' };
  const grouped = general.weeklyCorabastosGroups([...cards, egg, daily, quality]);
  assert.equal(grouped.groups.length, 2);
  assert.deepEqual(Array.from(grouped.groups, group => group.keys.length), [5, 5]);
  assert.equal(grouped.byKey.size, 10);
  assert.equal(grouped.byKey.get(oracle.products[0].keys[0].key).canonicalKey,
    oracle.products[0].keys.find(key => key.market === canonicalMarket).key);
  const collapsed = general.collapseWeeklyCorabastosCatalog([...cards, egg, daily, quality], grouped.groups);
  assert.equal(collapsed.length, 5);
  assert.equal(collapsed.filter(row => row.series === 'dane-weekly' && row.unit === 'kg').length, 2);
  assert.ok(collapsed.filter(row => row.series === 'dane-weekly' && row.unit === 'kg')
    .every(row => row.previous_price === null), 'Previous union date is unknown from current payload metadata');
  for (const row of [egg, daily, quality]) assert.ok(collapsed.includes(row));
});

test('one mismatched source hash or absent canonical card blocks that identity group', () => {
  const { cards } = fixture();
  const changed = { ...cards[0], quote_key: 'f'.repeat(64) };
  const corrupted = cards.map((row, i) => i === 0 ? changed : row);
  assert.equal(general.weeklyCorabastosGroups(corrupted).groups.length, 1);
  const missing = cards.filter(row => row.market !== canonicalMarket);
  assert.equal(general.weeklyCorabastosGroups(missing).groups.length, 0);
  const renamed = { ...cards[0], product_name: 'Ahuyama nueva' };
  assert.equal(general.expectedWeeklyCorabastosKey(renamed), null);
});

test('four audited egg grades preserve COP per unit and stay separate from other eggs, kg and daily quotes', () => {
  const all = [];
  for (const product of eggOracle.products) {
    const rows = product.source_examples.map(example => ({
      quote_key: example.key, market: example.market, product_id: product.product_id,
      product_name: product.product_name, publisher: oracle.publisher,
      series: 'dane-weekly', basis: oracle.basis, currency: 'COP', unit: 'unit',
      category: 'Huevos y lácteos', observed_on: example.date,
      price: example.price, min_price: example.min, max_price: example.max,
      previous_price: null, document_id: example.document_id,
      source_locator: example.source_locator, source_url: 'https://www.dane.gov.co/registered-original.xlsx',
      details: { identity_dimensions: { source_product: product.product_name } },
    }));
    assert.ok(rows.every(row => general.expectedWeeklyCorabastosKey(row) === row.quote_key));
    all.push(...rows);
  }
  const unknown = { ...all[0], product_id: 'huevo-rojo-c', product_name: 'Huevo rojo C',
    quote_key: 'unknown-unit-egg' };
  const wrongKg = { ...all[0], unit: 'kg', quote_key: 'wrong-egg-kg' };
  const daily = { ...all[0], series: 'dane-daily-query', quote_key: 'egg-daily' };
  const otherUnit = { ...all[0], unit: 'dozen', quote_key: 'egg-dozen' };
  for (const row of [unknown, wrongKg, daily, otherUnit])
    assert.equal(general.expectedWeeklyCorabastosKey(row), null);
  const groups = general.weeklyCorabastosGroups([...all, unknown, wrongKg, daily, otherUnit]);
  assert.equal(groups.groups.length, 4);
  const catalog = general.collapseWeeklyCorabastosCatalog([...all, unknown, wrongKg, daily, otherUnit], groups.groups);
  assert.equal(catalog.length, 8);
  assert.equal(catalog.filter(row => row.unit === 'unit' && row.quote_key.length === 64).length, 4);
  assert.ok(catalog.filter(row => row.unit === 'unit' && row.quote_key.length === 64)
    .every(row => row.previous_price === null));
  for (const product of eggOracle.products) {
    const group = groups.byKey.get(product.source_examples[0].key);
    const merged = general.mergeWeeklyCorabastosHistory(group,
      all.filter(row => row.product_id === product.product_id));
    assert.equal(merged.length, 2);
    assert.ok(merged.every(row => row.unit === 'unit' && row.currency === 'COP'));
    for (const expected of product.source_examples) {
      const actual = merged.find(row => row.observed_on === expected.date);
      assert.deepEqual([actual.min_price, actual.max_price, actual.price],
        [expected.min, expected.max, expected.price]);
      assert.equal(actual.document_id, expected.document_id);
    }
  }
});

test('original-backed histories stay separate and identical overlap retains alternate provenance', () => {
  const { cards, history } = fixture();
  const grouped = general.weeklyCorabastosGroups(cards);
  for (const product of oracle.products) {
    const group = grouped.byKey.get(product.keys[0].key);
    const rows = group.keys.flatMap(key => history[key]);
    const merged = general.mergeWeeklyCorabastosHistory(group, rows);
    assert.ok(merged.every(row => row.product_id === product.product_id && row.quote_key === group.canonicalKey));
    for (const example of product.source_examples) {
      const row = merged.find(item => item.observed_on === example.date);
      assert.equal(row.price, example.price);
      assert.equal(row.min_price, example.min);
      assert.equal(row.max_price, example.max);
      assert.equal(row.details.source_market_literal, example.market);
      assert.equal(row.document_id, example.document_id);
    }
  }
  const first = oracle.products[0], group = grouped.byKey.get(first.keys[0].key);
  const original = history[first.keys[0].key][0];
  const canonical = first.keys.find(entry => entry.market === canonicalMarket);
  const copy = { ...original, quote_key: canonical.key, market: canonical.market,
    document_id: 'alternate-official-pdf' };
  const merged = general.mergeWeeklyCorabastosHistory(group, [original, copy]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].details.alternate_originals[0].document_id, original.document_id);
  assert.equal(merged[0].details.alternate_originals[0].source_page, original.source_page);
  assert.throws(() => general.mergeWeeklyCorabastosHistory(group,
    [original, { ...copy, price: copy.price + 1 }]), /WEEKLY_CORABASTOS_PRICE_CONFLICT/);
  assert.throws(() => general.mergeWeeklyCorabastosHistory(group,
    [original, { ...copy, product_id: 'ajo' }]), /WEEKLY_CORABASTOS_IDENTITY_CONFLICT/);
});

function routeWith(cards, byKey, brokenKey, registered = cards, metadataError = false) {
  const snapshots = new Map(), calls = [];
  const client = { query: async (sql, values) => {
    if (brokenKey && values?.[0] === brokenKey) throw new Error('Reader outage');
    calls.push({ sql, key: values?.[0] });
    return { rows: byKey[values?.[0]] || [] };
  }, release() {} };
  const mocks = {
    'server-only': {},
    './db': { database: () => ({
      connect: async () => client,
      query: async (sql, values) => {
        if (sql.includes('WITH candidates AS MATERIALIZED')) {
          calls.push({ sql, key: values[0] });
          if (brokenKey === values[0]) throw new Error('Reader outage');
          return { rows: byKey[values[0]] || [] };
        }
        if (sql.includes('quote_key=$1') || sql.includes('quote_key=ANY($1::text[])')) {
          calls.push({ sql, metadata: true });
          if (metadataError) throw new Error('Identity reader outage');
          const keys = Array.isArray(values[0]) ? values[0] : [values[0]];
          return { rows: registered.filter(row => keys.includes(row.quote_key)).map(payload => ({ payload })) };
        }
        calls.push({ sql, catalog: true });
        return { rows: cards.map(payload => ({ payload })) };
      },
    }) },
    './summary-references': { summaryReference: async () => null },
    './snapshot-cache': { snapshotCache: (_ttl, _capacity, name) => {
      const values = snapshots.get(name) || new Map(); snapshots.set(name, values);
      const cached = (key, loader) => {
        if (!values.has(key)) values.set(key, Promise.resolve().then(loader));
        return values.get(key);
      };
      cached.expiresAt = () => 0;
      cached.withExpiry = async (key, loader) => ({ value: await cached(key, loader), expires: 0 });
      return cached;
    } },
    './official-market-regions': { officialMarketRegions: async rows => rows },
    './weekly-capitalization-continuity': {
      capitalizationWeeklyGroups: () => ({ groups: [], byKey: new Map() }),
      collapseCapitalizationWeeklyCatalog: rows => rows,
      isReviewedCapitalizationWeeklyKey: () => false,
      isWeeklyCapitalizationConflict: () => false,
      mergeCapitalizationWeeklyHistory: (_group, rows) => rows,
      MAX_WEEKLY_CAPITALIZATION_KEYS: 8,
    },
    './acelga-weekly-continuity': acelga,
    './weekly-corabastos-continuity': general,
    './minorista-weekly-continuity': load('minorista-weekly-continuity.ts'),
    './aguacate-bucaramanga-weekly-continuity': load('aguacate-bucaramanga-weekly-continuity.ts'),
    '../label-normalization': { normalizeOfficialLabels: row => row, normalizeLabel: value => value },
    '../category-hierarchy': require('./helpers/category-hierarchy.cjs')(),
  };
  return { route: load('official-references.ts', mocks), calls };
}

test('catalog reads metadata once with zero non-Acelga histories; each old bookmark uses at most five seeks', async () => {
  const { cards, history } = fixture();
  const { route, calls } = routeWith(cards, history);
  const catalog = await route.latestOfficialReferences();
  assert.equal(catalog.length, 2);
  assert.equal(calls.filter(call => call.catalog).length, 1);
  assert.equal(calls.filter(call => call.key && oracle.products.some(product => product.keys.some(k => k.key === call.key))).length, 0);
  for (const product of oracle.products) {
    const [old, another] = product.keys;
    const detail = await route.officialReferences(new URLSearchParams('id='+old.key));
    assert.equal(detail.reference.quote_key, product.keys.find(k => k.market === canonicalMarket).key);
    const before = calls.length;
    const second = await route.officialReferences(new URLSearchParams('id='+another.key));
    assert.equal(second, detail, 'All old bookmarks share the same merged cache result');
    assert.equal(calls.length, before);
  }
  const keyed = calls.filter(call => call.key && oracle.products.some(product => product.keys.some(k => k.key === call.key)));
  assert.equal(keyed.length, 10, 'Two requested products, five indexed source seeks each');
  assert.equal(calls.filter(call => call.catalog).length, 1, 'Catalog metadata shared with detail requests');
});

test('one group conflict removes only its card/detail and does not hide another product or a DB failure', async () => {
  const { cards, history } = fixture();
  const ahuyama = oracle.products[0], ajo = oracle.products[1];
  const one = ahuyama.keys[0], two = ahuyama.keys[1];
  const changedCards = cards.map(row => row.quote_key === two.key ? { ...row, price: row.price + 1 } : row);
  const { route } = routeWith(changedCards, history);
  const catalog = await route.latestOfficialReferences();
  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].product_id, ajo.product_id);
  const conflicting = structuredClone(history);
  const base = conflicting[one.key][0];
  conflicting[two.key].push({ ...base, quote_key: two.key, market: two.market, price: base.price + 1 });
  const details = routeWith(cards, conflicting);
  assert.equal(await details.route.officialReferences(new URLSearchParams('id='+one.key)), null);
  assert.ok((await details.route.officialReferences(new URLSearchParams('id='+ajo.keys[0].key))).history.length > 0);
  const broken = routeWith(cards, history, one.key);
  await assert.rejects(broken.route.officialReferences(new URLSearchParams('id='+one.key)), /Reader outage/);
});

test('dirty registration metadata restores a bookmarked union without publishing its cached price', async () => {
  const { cards, history } = fixture();
  const product = oracle.products[1];
  const canonical = product.keys.find(entry => entry.market === canonicalMarket);
  const clean = cards.filter(row => row.quote_key !== canonical.key);
  const registered = cards.map(row => row.quote_key === canonical.key ?
    { ...row, price: 999999999, previous_price: 888888888 } : row);
  const { route, calls } = routeWith(clean, history, undefined, registered);
  const catalog = await route.latestOfficialReferences();
  assert.ok(catalog.every(row => row.quote_key !== canonical.key && row.price !== 999999999));
  const detail = await route.officialReferences(new URLSearchParams('id='+product.keys[0].key));
  assert.equal(detail.reference.quote_key, canonical.key);
  assert.equal(detail.reference.price, 2000);
  assert.equal(detail.history.length, 5);
  assert.ok(detail.history.every(row => row.price !== 999999999 && row.price !== 888888888));
  for (const example of product.source_examples)
    assert.equal(detail.history.find(row => row.observed_on === example.date).price, example.price);
  assert.equal(calls.filter(call => call.metadata).length, 2);
  assert.equal(calls.filter(call => call.key).length, 5);
  assert.equal(calls.filter(call => call.catalog).length, 1);
});

test('tampered dirty identity cannot combine another product with an old bookmark', async () => {
  const { cards, history } = fixture();
  const product = oracle.products[1];
  const canonical = product.keys.find(entry => entry.market === canonicalMarket);
  const clean = cards.filter(row => row.quote_key !== canonical.key);
  const registered = cards.map(row => row.quote_key === canonical.key ?
    { ...row, product_id: oracle.products[0].product_id } : row);
  const { route } = routeWith(clean, history, undefined, registered);
  const old = product.keys[0].key;
  const detail = await route.officialReferences(new URLSearchParams('id='+old));
  assert.equal(detail.reference.quote_key, old);
  assert.ok(detail.history.every(row => row.product_id === product.product_id));
  assert.equal(detail.history.length, history[old].length);
});

test('registration database errors propagate instead of silently narrowing a history', async () => {
  const { cards, history } = fixture();
  const product = oracle.products[1];
  const canonical = product.keys.find(entry => entry.market === canonicalMarket);
  const clean = cards.filter(row => row.quote_key !== canonical.key);
  const { route } = routeWith(clean, history, undefined, cards, true);
  await assert.rejects(route.officialReferences(new URLSearchParams('id='+product.keys[0].key)),
    /Identity reader outage/);
});
