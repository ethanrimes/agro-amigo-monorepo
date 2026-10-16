/* Source-guard proof against private, session-local PostgreSQL objects only. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');

const dsn = process.env.AGRO_LABEL_ALIAS_TEST_DSN || '';
const expectedDsn = 'postgresql:///postgres?host=/tmp/agro-unified-catalog-pg-v24-20261004&port=65473';
if (dsn && dsn !== expectedDsn && !/^postgresql:\/\/\/postgres\?host=\/tmp\/agro-market-alias-he-b-[A-Za-z0-9_-]+&port=65515$/.test(dsn)) throw new Error('Alias test accepts only the private PostgreSQL socket');

const helperExports = {};
const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/market-alias.ts'), 'utf8');
new Function('exports', 'require', ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(helperExports, () => ({}));
const { resolveMarketAlias } = helperExports;
const oldId = 'finca-bolivar-san-juan-nepomu-ceno';
const canonical = 'finca-bolivar-san-juan-nepomuceno';
const sha = 'a8e27086128ff3f2a3c67147dfa6782a947a6e3ad6c94b52af4c2d3537d1ab63';
const otherSha = 'f'.repeat(64);
const oldLocator = 'PDF page 5,col 2,line 19; precio en finca, COP/litro';
const correctedLocator = 'PDF page 5,col 2,line 18; parser milk-pdf-v12; precio en finca, COP/litro';
const nativeLocator = 'PDF page 5,col 2,line 18; parser milk-pdf-v12';
const xlsLocator = 'Precios leche en finca!row 53; precio en finca, COP/litro';
const pairs = [
  { pdf: sha, xls: '4175c659c2c17c9119e2ce280afa9a2b57b9b9a420dff96abfa7802866eab74a',
    day: '2022-06-30', pdfPrice: 1295, xlsPrice: 1295.23, low: 1200, high: 1400 },
  { pdf: '4cf84658353b236e022d39c737e16975d94e22e5cde92dd96f308d3e042f6e0e',
    xls: '4ad00cdf760af47806e5f1abe1c386e5d02262dea02a354fe510aa2888bd8ae9',
    day: '2022-07-31', pdfPrice: 1328, xlsPrice: 1328.12, low: 1200, high: 1500 },
];
const base = {
  document_id: sha, product_id: 'leche-cruda-en-finca', source_id: 'dane-milk-farm',
  observed_on: '2022-06-30', period: 'monthly', unit: 'litre',
  price: 1295, min_price: 1200, max_price: 1400,
};

test('verified milk municipality bookmark requires a published exact native counterpart', {
  skip: !dsn && 'Requires private local PostgreSQL socket',
}, async () => {
  const db = new Client({ connectionString: dsn });
  await db.connect();
  try {
    await db.query('BEGIN');
    await db.query("SET LOCAL search_path=pg_temp,public; SET LOCAL statement_timeout='8s'");
    await db.query(`CREATE TEMP TABLE price_observation (
      document_id text,source_locator text,product_id text,market_id text,source_id text,
      observed_on date,period text,unit text,price numeric,min_price numeric,max_price numeric,
      eligible boolean NOT NULL DEFAULT true) ON COMMIT DROP;
      CREATE TEMP TABLE price_observation_review (
      document_id text,source_locator text,product_id text,market_id text,source_id text,
      observed_on date,period text,unit text,reason text,evidence jsonb) ON COMMIT DROP;
      CREATE TEMP TABLE historical_price (
      document_id text,source_locator text,series text,observed_on date,
      product_name text,market_name text,unit text,price numeric,details jsonb) ON COMMIT DROP;
      CREATE TEMP VIEW published_price_observation AS
        SELECT * FROM price_observation WHERE eligible`);
    const insertPrice = async (row) => db.query(`INSERT INTO price_observation
      (document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,
       price,min_price,max_price,eligible)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`, [
      row.document_id,row.source_locator,row.product_id,row.market_id,row.source_id,
      row.observed_on,row.period,row.unit,row.price,row.min_price,row.max_price,
      row.eligible !== false,
    ]);
    const insertReview = async (row) => db.query(`INSERT INTO price_observation_review
      (document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,reason,evidence)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`, [
      row.document_id,row.source_locator,row.product_id,row.market_id,row.source_id,
      row.observed_on,row.period,row.unit,row.reason,JSON.stringify(row.evidence),
    ]);
    const insertNative = async (row) => db.query(`INSERT INTO historical_price
      (document_id,source_locator,series,observed_on,product_name,market_name,unit,price,details)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)`, [
      row.document_id,row.source_locator,row.series,row.observed_on,row.product_name,
      row.market_name,row.unit,row.price,JSON.stringify(row.details),
    ]);
    const setup = async ({ original = {}, target = {}, review = {}, extraTarget } = {}) => {
      await db.query('TRUNCATE price_observation_review,price_observation');
      const old = { ...base, market_id: oldId, source_locator: oldLocator, ...original };
      const next = { ...base, market_id: canonical, source_locator: correctedLocator, ...target };
      const evidence = {
        source_sha256: old.document_id, canonical_municipality: 'San Juan Nepomuceno',
        corrected_source_locator: correctedLocator, original_retained: true,
      };
      const reviewed = { ...old,
        reason: 'Verified DANE milk line-wrap municipality alias',
        evidence, ...review, evidence: { ...evidence, ...review.evidence },
      };
      await insertPrice(old);
      await insertPrice(next);
      if (extraTarget) await insertPrice({ ...next, ...extraTarget });
      return reviewed;
    };
    assert.equal(await resolveMarketAlias(db, 'ordinary-market'), 'ordinary-market');
    let reviewed = await setup();
    assert.equal(await resolveMarketAlias(db, oldId), oldId, 'no review means no alias');
    await insertReview(reviewed);
    assert.equal(await resolveMarketAlias(db, oldId), canonical, 'exact review and published row resolve');

    for (const [label, changes] of [
      ['wrong source SHA', { review: { evidence: { source_sha256: otherSha } } }],
      ['unapproved document SHA', { original: { document_id: otherSha },
        target: { document_id: otherSha } }],
      ['wrong review reason', { review: { reason: 'Other review' } }],
      ['wrong source', { original: { source_id: 'other' },
        target: { source_id: 'other' } }],
      ['wrong unit basis', { original: { unit: 'kg' }, target: { unit: 'kg' } }],
      ['wrong period basis', { original: { period: 'daily' }, target: { period: 'daily' } }],
      ['different price', { target: { price: 1296 } }],
      ['different minimum', { target: { min_price: 1199 } }],
      ['different maximum', { target: { max_price: 1401 } }],
      ['different date', { target: { observed_on: '2022-07-31' } }],
      ['different locator', { target: { source_locator: 'PDF page 5,col 2,line 20' } }],
      ['unpublished target', { target: { eligible: false } }],
      ['different original locator', { original: { source_locator: 'PDF page 5,col 2,line 20' } }],
      ['ambiguous targets', { extraTarget: { market_id: 'another-published-market' } }],
    ]) {
      reviewed = await setup(changes);
      await insertReview(reviewed);
      assert.equal(await resolveMarketAlias(db, oldId), oldId, label);
    }

    const setupPair = async (pair, { oldChange = {}, winnerChange = {},
      reviewChange = {}, nativeChange = {} } = {}) => {
      await db.query('TRUNCATE historical_price,price_observation_review,price_observation');
      const old = { ...base, document_id: pair.pdf, observed_on: pair.day,
        price: pair.pdfPrice, min_price: pair.low, max_price: pair.high,
        market_id: oldId, source_locator: oldLocator, ...oldChange };
      const winner = { ...old, document_id: pair.xls, market_id: canonical,
        source_locator: xlsLocator, price: pair.xlsPrice, ...winnerChange };
      const evidence = { source_sha256: pair.pdf,
        canonical_municipality: 'San Juan Nepomuceno',
        corrected_source_locator: correctedLocator, original_retained: true,
        ...reviewChange.evidence };
      const review = { ...old, reason: 'Verified DANE milk line-wrap municipality alias',
        ...reviewChange, evidence };
      const native = { document_id: pair.pdf, source_locator: nativeLocator,
        series: 'dane-milk-farm', observed_on: pair.day,
        product_name: 'Leche cruda en finca', market_name: 'San Juan Nepomuceno',
        unit: 'litre', price: pair.pdfPrice,
        details: { source_sha256: pair.pdf,
          literal_municipality: 'San Juan Nepomu- ceno',
          literal_source_locator: 'PDF page 5,col 2,line 17-19',
          department: 'Bolívar', municipality: 'San Juan Nepomuceno',
          min_price: pair.low, max_price: pair.high },
        ...nativeChange, details: {
          source_sha256: pair.pdf,
          literal_municipality: 'San Juan Nepomu- ceno',
          literal_source_locator: 'PDF page 5,col 2,line 17-19',
          department: 'Bolívar', municipality: 'San Juan Nepomuceno',
          min_price: pair.low, max_price: pair.high,
          ...nativeChange.details,
        } };
      await insertPrice(old);
      await insertPrice(winner);
      await insertReview(review);
      await insertNative(native);
    };
    for (const pair of pairs) {
      await setupPair(pair);
      assert.equal(await resolveMarketAlias(db, oldId), canonical,
        `${pair.day} exact PDF correction plus own published XLS row`);
    }
    for (const [label, changes] of [
      ['wrong XLS SHA', { winnerChange: { document_id: otherSha } }],
      ['wrong PDF SHA', { nativeChange: { document_id: otherSha } }],
      ['wrong native source locator', { nativeChange: { source_locator: 'PDF page 5,col 2,line 19' } }],
      ['wrong native literal cell', { nativeChange: { details: { literal_source_locator: 'PDF page 5,col 2,line 19' } } }],
      ['wrong native municipality', { nativeChange: { details: { municipality: 'Other' } } }],
      ['wrong native price', { nativeChange: { price: 1296 } }],
      ['wrong annex cell', { winnerChange: { source_locator: 'Precios leche en finca!row 54; precio en finca, COP/litro' } }],
      ['wrong annex cent price', { winnerChange: { price: 1295.24 } }],
      ['wrong month', { winnerChange: { observed_on: '2022-07-31' } }],
      ['wrong PDF bounds', { oldChange: { min_price: 1199 } }],
      ['wrong XLS bounds', { winnerChange: { max_price: 1401 } }],
      ['wrong native bounds', { nativeChange: { details: { max_price: 1401 } } }],
      ['unpublished XLS winner', { winnerChange: { eligible: false } }],
      ['wrong source basis', { winnerChange: { source_id: 'other' } }],
      ['wrong product', { winnerChange: { product_id: 'other' } }],
    ]) {
      await setupPair(pairs[0], changes);
      assert.equal(await resolveMarketAlias(db, oldId), oldId, label);
    }
  } finally {
    await db.query('ROLLBACK');
    await db.end();
  }
});
