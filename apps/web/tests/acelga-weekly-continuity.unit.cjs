const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const file = path.join(__dirname, '../src/lib/server/acelga-weekly-continuity.ts');
const source = fs.readFileSync(file, 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const scope = { exports: {}, require: () => { throw new Error('Pure helper imported runtime dependency'); } };
vm.runInNewContext(output, scope);
const { ACELGA_WEEKLY_KEYS, ACELGA_WEEKLY_CANONICAL_KEY, ACELGA_WEEKLY_MARKETS,
  isAcelgaWeeklyKey, mergeAcelgaWeeklyHistory, collapseAcelgaWeeklyCatalog } = scope.exports;
const general = { exports: {}, require: name => require(name) };
const generalSource = fs.readFileSync(path.join(__dirname, '../src/lib/server/weekly-corabastos-continuity.ts'), 'utf8');
vm.runInNewContext(ts.transpileModule(generalSource, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, general);
const row = (key, day, price, suffix = '') => ({
  quote_key: key, product_id: 'acelga', product_name: 'Acelga', category: 'Verduras y hortalizas',
  publisher: 'DANE · SIPSA', series: 'dane-weekly', basis: 'Precio mayorista semanal',
  currency: 'COP', unit: 'kg', market: ACELGA_WEEKLY_MARKETS[key], observed_on: day,
  price, min_price: price - 10, max_price: price + 10,
  document_id: 'document-' + suffix, source_locator: 'PDF page 4,table 1' + suffix,
  source_page: 4,
  source_url: 'https://www.dane.gov.co/' + suffix, details: { identity_dimensions: { source_product: 'Acelga' } },
});

test('five exact keys merge 2012 to current, dedupe identical cross-format day, retain alternate evidence and old bookmarks', () => {
  assert.equal(ACELGA_WEEKLY_KEYS.length, 5);
  const canonical = ACELGA_WEEKLY_CANONICAL_KEY;
  const old = ACELGA_WEEKLY_KEYS.filter(k => k !== canonical);
  const rows = [
    row(old[0], '2012-06-22', 793, '2012'),
    row(old[1], '2017-05-19', 463, '2017'),
    row(canonical, '2017-09-01', 576, 'new'),
    row(old[2], '2018-12-21', 761, 'pdf'),
    row(canonical, '2018-12-21', 761, 'annex'),
    row(old[3], '2022-06-24', 1358, 'typo'),
    row(canonical, '2026-10-02', 433, 'latest'),
  ];
  const history = mergeAcelgaWeeklyHistory(rows);
  assert.deepEqual(Array.from(history, r => r.observed_on), ['2012-06-22','2017-05-19','2017-09-01','2018-12-21','2022-06-24','2026-10-02']);
  assert.ok(history.every(r => r.quote_key === canonical && r.market === ACELGA_WEEKLY_MARKETS[canonical]));
  assert.equal(history[3].document_id, 'document-annex', 'current spelling wins identical-date duplicate');
  assert.equal(history[3].details.alternate_originals[0].document_id, 'document-pdf');
  assert.equal(history[3].details.alternate_originals[0].source_page, 4);
  assert.equal(history[0].details.source_market_literal, ACELGA_WEEKLY_MARKETS[old[0]]);
  const cards = rows.filter((r, i) => i !== 3).map(r => ({ ...r, previous_price: null }));
  const quality = { ...row(canonical, '2026-10-02', 100), quote_key: 'quality-other', series: 'corabastos-quality-extra', previous_price: null };
  const mergedCards = collapseAcelgaWeeklyCatalog([...cards, quality], rows);
  assert.equal(mergedCards.length, 2);
  assert.equal(mergedCards.find(r => r.quote_key === canonical).previous_price, 1358);
  assert.equal(mergedCards.find(r => r.quote_key === 'quality-other'), quality);
  assert.ok(old.every(isAcelgaWeeklyKey));
  assert.equal(isAcelgaWeeklyKey('quality-other'), false);
});

test('same-date disagreement and identity changes fail closed', () => {
  const [old] = ACELGA_WEEKLY_KEYS.filter(k => k !== ACELGA_WEEKLY_CANONICAL_KEY);
  const a = row(old, '2018-12-21', 761), b = row(ACELGA_WEEKLY_CANONICAL_KEY, '2018-12-21', 761);
  for (const mutation of [
    r => { r.price = 762; }, r => { r.min_price = 1; }, r => { r.max_price = 2000; },
    r => { r.currency = 'USD'; }, r => { r.unit = 'ATADO'; }, r => { r.basis = 'Precio diario'; },
    r => { r.market = 'Bogotá, otro mercado'; }, r => { r.series = 'dane-daily-query'; },
    r => { r.product_id = 'ajo'; }, r => { r.details.identity_dimensions = { source_product: 'Acelga', quality: 'extra' }; },
  ]) {
    const changed = structuredClone(b); mutation(changed);
    assert.throws(() => mergeAcelgaWeeklyHistory([a, changed]), /ACELGA_WEEKLY_(PRICE|IDENTITY)_CONFLICT/);
  }
  assert.throws(() => collapseAcelgaWeeklyCatalog([{ ...b, market: 'wrong', previous_price: null }], [a,b]), /IDENTITY_CONFLICT/);
});

test('no alias cards leaves unrelated references unchanged', () => {
  const unrelated = { ...row(ACELGA_WEEKLY_CANONICAL_KEY, '2026-10-02', 433), quote_key: 'different-series', previous_price: null };
  assert.equal(collapseAcelgaWeeklyCatalog([unrelated], []).at(0), unrelated);
});

function routeWith(cards, byKey, failAtKey) {
  const module = { exports: {} }, snapshots = new Map(), calls = [];
  const client = {
    query: async (sql, values) => {
      if (failAtKey && values?.[0] === failAtKey) throw new Error('Database unavailable');
      calls.push(values?.[0] || sql);
      return { rows: byKey[values?.[0]] || [] };
    },
    release() {},
  };
  const mocks = {
    'server-only': {},
    './db': { database: () => ({
      connect: async () => client,
      query: async () => ({ rows: cards.map(payload => ({ payload })) }),
    }) },
    './summary-references': { summaryReference: async () => null },
    './snapshot-cache': { snapshotCache: (_ttl, _max, name) => {
      const values = snapshots.get(name) || new Map(); snapshots.set(name, values);
      const cached = (key, loader) => {
        if (!values.has(key)) values.set(key, Promise.resolve().then(loader));
        return values.get(key);
      };
      cached.expiresAt = () => 0;
      cached.withExpiry = async (key, loader) => ({ value: await cached(key, loader), expires: 0 });
      return cached;
    } },
    './official-market-regions': { officialMarketRegions: async values => values },
    './weekly-capitalization-continuity': {
      capitalizationWeeklyGroups: () => ({ groups: [], byKey: new Map() }),
      collapseCapitalizationWeeklyCatalog: rows => rows,
      isReviewedCapitalizationWeeklyKey: () => false,
      isWeeklyCapitalizationConflict: () => false,
      mergeCapitalizationWeeklyHistory: (_group, rows) => rows,
      MAX_WEEKLY_CAPITALIZATION_KEYS: 8,
    },
    './acelga-weekly-continuity': scope.exports,
    './weekly-corabastos-continuity': general.exports,
    './minorista-weekly-continuity': { isMinoristaWeeklyKey: () => false,
      collapseMinoristaWeeklyCatalog: rows => rows, isMinoristaWeeklyConflict: () => false },
    './aguacate-bucaramanga-weekly-continuity': { isAguacateBucaramangaWeeklyKey: () => false,
      collapseAguacateBucaramangaWeeklyCatalog: rows => rows,
      isAguacateBucaramangaWeeklyConflict: () => false },
    '../label-normalization': { normalizeOfficialLabels: row => row, normalizeLabel: value => value },
  };
  const route = fs.readFileSync(path.join(__dirname, '../src/lib/server/official-references.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(route, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { ...module, require: name => mocks[name], URLSearchParams });
  return { route: module.exports, calls };
}

test('real cache-to-catalog/detail path merges raw rows once and retains alternate original provenance', async () => {
  const old = ACELGA_WEEKLY_KEYS[0], canonical = ACELGA_WEEKLY_CANONICAL_KEY;
  const original = row(old, '2018-03-09', 558, 'publisher-PDF');
  const corrected = row(canonical, '2018-03-09', 558, 'publisher-annex');
  const recent = row(canonical, '2026-10-02', 433, 'current');
  const unrelated = { ...row(canonical, '2026-10-02', 100), quote_key: 'other-series', previous_price: null };
  const { route, calls } = routeWith([original, recent, unrelated], {
    [old]: [original], [canonical]: [corrected, recent],
  });
  const catalog = await route.latestOfficialReferences();
  assert.equal(catalog.length, 2);
  assert.equal(catalog.find(x => x.quote_key === canonical).previous_price, 558);
  const detail = await route.officialReferences(new URLSearchParams('id=' + old));
  assert.equal(detail.history[0].details.source_market_literal, corrected.market);
  assert.equal(detail.history[0].details.original_quote_key, canonical);
  assert.equal(detail.history[0].details.alternate_originals[0].literal_market, original.market);
  assert.equal(detail.history[0].details.alternate_originals[0].document_id, original.document_id);
  assert.equal(calls.filter(x => ACELGA_WEEKLY_KEYS.includes(x)).length, 5,
    'Catalog and bookmarked detail share the cached raw five-key read');
});

test('Acelga conflict suppresses only that catalog group/detail; DB failures still propagate', async () => {
  const old = ACELGA_WEEKLY_KEYS[0], canonical = ACELGA_WEEKLY_CANONICAL_KEY;
  const original = row(old, '2018-03-09', 558, 'original');
  const conflict = row(canonical, '2018-03-09', 559, 'conflict');
  const unrelated = { ...row(canonical, '2026-10-02', 100), quote_key: 'other-series', previous_price: null };
  const { route } = routeWith([original, conflict, unrelated], { [old]: [original], [canonical]: [conflict] });
  const catalog = await route.latestOfficialReferences();
  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].quote_key, 'other-series');
  assert.equal(await route.officialReferences(new URLSearchParams('id=' + old)), null);
  const broken = routeWith([original, unrelated], { [old]: [original] }, old);
  await assert.rejects(broken.route.latestOfficialReferences(), /Database unavailable/);
});
