const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// Execute the actual reference service and actual cache against one controllable
// clock. Database responses carry distinct originals and prices so expiry must
// refresh data, not just a timestamp or a mocked cache call signature.
function service(options = {}) {
  let clock = 0, revision = 1;
  const calls = { catalog: 0, history: 0 };
  class Clock extends Date { static now() { return clock; } }
  const shared = {};
  const load = (name, mocks = {}) => {
    const module = { exports: {} };
    const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/', name + '.ts'), 'utf8');
    vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    } }).outputText, { module, exports: module.exports, Date: Clock, Map, Error, Promise,
      URLSearchParams, globalThis: shared, require: key => {
        if (!(key in mocks)) throw new Error('Unexpected dependency ' + key);
        return mocks[key];
      } });
    return module.exports;
  };
  const cache = load('snapshot-cache', { 'server-only': {} });
  const quote = (key) => ({ quote_key: key, product_id: 'acelga', product_name: 'Acelga',
    observed_on: '2026-10-02', market: 'Medellín', series: 'dane-weekly',
    currency: 'COP', unit: 'kg', basis: 'Precio mayorista semanal',
    document_id: 'original-' + revision, source_locator: 'PDF page 6,line 12',
    price: revision * 1000, previous_price: null, details: {} });
  const query = async (sql, args) => {
    if (sql.includes('SELECT payload FROM official_catalog_current') && !args) {
      calls.catalog++;
      return { rows: [quote('a'.repeat(64)), quote('plain')].map(payload => ({ payload })) };
    }
    if (sql.includes('WITH candidates AS MATERIALIZED')) {
      calls.history++;
      return { rows: [quote(args[0])] };
    }
    return { rows: [] };
  };
  const db = { query, connect: async () => ({ query, release() {} }) };
  const route = load('official-references', {
    'server-only': {}, './db': { database: () => db }, './snapshot-cache': cache,
    './summary-references': { summaryReference: async () => null },
    './official-market-regions': { officialMarketRegions: async rows => rows },
    '../label-normalization': { normalizeOfficialLabels: row => row },
    '../category-hierarchy': require('./helpers/category-hierarchy.cjs')(),
    './weekly-capitalization-continuity': {
      capitalizationWeeklyGroups: () => ({ groups: [], byKey: new Map() }),
      collapseCapitalizationWeeklyCatalog: rows => rows,
      isReviewedCapitalizationWeeklyKey: () => false,
      isWeeklyCapitalizationConflict: () => false,
      mergeCapitalizationWeeklyHistory: (_group, rows) => rows,
      MAX_WEEKLY_CAPITALIZATION_KEYS: 8,
    },
    './acelga-weekly-continuity': {
      ACELGA_WEEKLY_CANONICAL_KEY: 'a'.repeat(64), ACELGA_WEEKLY_KEYS: ['a'.repeat(64)],
      isAcelgaWeeklyKey: key => key === 'a'.repeat(64),
      isAcelgaWeeklyConflict: () => false,
      mergeAcelgaWeeklyHistory: rows => rows,
      collapseAcelgaWeeklyCatalog: (cards, history) => cards.map(card =>
        card.quote_key === 'a'.repeat(64) ? { ...history.at(-1), quote_key: 'a'.repeat(64) } : card),
    },
    './weekly-corabastos-continuity': {
      weeklyCorabastosGroups: cards => {
        if (!options.group) return { groups: [], byKey: new Map() };
        const keys=['b'.repeat(64),'c'.repeat(64)];
        if (cards.some(card => card.document_id === 'original-2')) keys.push('d'.repeat(64));
        const group={canonicalKey:keys[0],keys};
        return {groups:[group],byKey:new Map(keys.map(key=>[key,group]))};
      },
      collapseWeeklyCorabastosCatalog: rows => rows,
      mergeWeeklyCorabastosHistory: (_group, rows) => rows,
      expectedWeeklyCorabastosKey: () => undefined,
      WEEKLY_CORABASTOS_MARKETS: [], isWeeklyCorabastosConflict: () => false,
    },
    './minorista-weekly-continuity': { isMinoristaWeeklyKey: () => false,
      collapseMinoristaWeeklyCatalog: rows => rows, isMinoristaWeeklyConflict: () => false },
    './aguacate-bucaramanga-weekly-continuity': { isAguacateBucaramangaWeeklyKey: () => false,
      collapseAguacateBucaramangaWeeklyCatalog: rows => rows,
      isAguacateBucaramangaWeeklyConflict: () => false },
  });
  return { route, calls, clock: value => { clock = value; }, revision: value => { revision = value; } };
}

test('ordinary latest catalogue cannot renew nearly expired raw source data', async () => {
  const app = service();
  // A bookmarked ordinary detail warms raw metadata independently of catalogue.
  await app.route.officialReferences(new URLSearchParams('id=' + 'b'.repeat(64)));
  assert.equal(app.calls.catalog, 1);
  app.clock(299999);
  const initial = await app.route.latestOfficialReferences();
  assert.equal(initial.find(row => row.quote_key === 'plain').document_id, 'original-1');
  assert.equal(app.route.officialReferencesCacheExpiresAt(), 300000);
  app.revision(2);
  app.clock(300000);
  const refreshed = await app.route.latestOfficialReferences();
  assert.equal(app.calls.catalog, 2);
  assert.equal(refreshed.find(row => row.quote_key === 'plain').price, 2000);
  assert.equal(refreshed.find(row => row.quote_key === 'plain').document_id, 'original-2');
});

test('an ungrouped bookmark cannot outlive the raw metadata used to classify it', async () => {
  const app=service();
  await app.route.officialReferences(new URLSearchParams('id='+'b'.repeat(64)));
  app.clock(299999);
  const before=await app.route.officialReferences(new URLSearchParams('id='+'e'.repeat(64)));
  assert.equal(before.reference.document_id,'original-1');
  app.revision(2);
  app.clock(300000);
  const after=await app.route.officialReferences(new URLSearchParams('id='+'e'.repeat(64)));
  assert.equal(after.reference.document_id,'original-2');
  assert.equal(after.reference.price,2000);
  assert.equal(app.calls.history,3,'ordinary history refreshes at raw deadline despite newer null registration deadline');
});

test('new clean group membership refreshes bookmarked history before old money cache expiry', async () => {
  const app=service({group:true});
  await app.route.latestOfficialReferences(); // Raw metadata expires at300000.
  app.clock(100000);
  const old=await app.route.officialReferences(new URLSearchParams('id='+'b'.repeat(64)));
  assert.equal(old.history.length,2);
  const reads=app.calls.history;
  app.revision(2);
  app.clock(300000); // Metadata changes while group history remains cached until400000.
  const current=await app.route.officialReferences(new URLSearchParams('id='+'b'.repeat(64)));
  assert.equal(current.history.length,3);
  assert.ok(current.history.every(row=>row.price===2000&&row.document_id==='original-2'));
  assert.equal(app.calls.history-reads,3,'new membership performs three guarded source seeks');
  const alias=await app.route.officialReferences(new URLSearchParams('id='+'d'.repeat(64)));
  assert.equal(alias,current,'all current group aliases share the same complete history');
});

test('catalogue and bookmarked detail inherit earlier guarded weekly history expiry', async () => {
  const app = service();
  await app.route.officialReferences(new URLSearchParams('id=' + 'b'.repeat(64)));
  app.clock(100000);
  const old = await app.route.officialReferences(new URLSearchParams('id=' + 'a'.repeat(64)));
  assert.equal(old.reference.price, 1000);
  app.clock(300000);
  await app.route.officialReferences(new URLSearchParams('id=' + 'b'.repeat(64)));
  app.clock(350000);
  await app.route.latestOfficialReferences();
  assert.equal(app.route.officialReferencesCacheExpiresAt(), 400000,
    'raw metadata expires at600000; guarded money expires first at400000');
  app.revision(2);
  app.clock(400000);
  const updated = await app.route.latestOfficialReferences();
  assert.equal(updated.find(row => row.quote_key === 'a'.repeat(64)).document_id, 'original-2');
  const detail = await app.route.officialReferences(new URLSearchParams('id=' + 'a'.repeat(64)));
  assert.equal(detail.reference.price, 2000);
  assert.equal(detail.reference.document_id, 'original-2');
  assert.equal(app.calls.history, 4, 'two plain SQL reads plus two shared guarded weekly reads');
});
