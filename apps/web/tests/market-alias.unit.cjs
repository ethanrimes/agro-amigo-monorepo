const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/market-alias.ts'), 'utf8');
const out = {};
new Function('exports', 'require', ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(out, () => ({}));
const { resolveMarketAlias } = out;
const oldId = 'finca-bolivar-san-juan-nepomu-ceno';
const canonical = 'finca-bolivar-san-juan-nepomuceno';

test('unrelated markets and unreplayed bookmark retain exact requested ID', async () => {
  const db = { query: async () => ({ rows: [] }) };
  assert.equal(await resolveMarketAlias(db, 'another-market'), 'another-market');
  assert.equal(await resolveMarketAlias(db, oldId), oldId);
});

test('SQL requires source-bound review and exact retained PDF / winning annex pair', async () => {
  let queries = 0;
  const db = { query: async (sql, args) => {
    queries++;
    assert.equal(args[0], oldId);
    assert.equal(args[1].length, 2);
    assert.equal(args.length, 19);
    assert.deepEqual(args.slice(2, 9), [
      'a8e27086128ff3f2a3c67147dfa6782a947a6e3ad6c94b52af4c2d3537d1ab63',
      '4175c659c2c17c9119e2ce280afa9a2b57b9b9a420dff96abfa7802866eab74a',
      '2022-06-30', 1295, 1295.23, 1200, 1400,
    ]);
    assert.deepEqual(args.slice(9, 16), [
      '4cf84658353b236e022d39c737e16975d94e22e5cde92dd96f308d3e042f6e0e',
      '4ad00cdf760af47806e5f1abe1c386e5d02262dea02a354fe510aa2888bd8ae9',
      '2022-07-31', 1328, 1328.12, 1200, 1500,
    ]);
    assert.deepEqual(args.slice(16), [
      'PDF page 5,col 2,line 18; parser milk-pdf-v12', canonical,
      'Precios leche en finca!row 53; precio en finca, COP/litro',
    ]);
    assert.match(sql, /review\.reason='Verified DANE milk line-wrap municipality alias'/);
    assert.match(sql, /review\.document_id=ANY\(\$2::text\[\]\)/);
    assert.match(sql, /review\.evidence->>'source_sha256'=review\.document_id/);
    assert.match(sql, /review\.source_id='dane-milk-farm'/);
    assert.match(sql, /JOIN published_price_observation corrected/);
    assert.match(sql, /corrected\.source_locator=review\.evidence->>'corrected_source_locator'/);
    assert.match(sql, /corrected\.unit=review\.unit/);
    assert.match(sql, /corrected\.price=old\.price/);
    assert.match(sql, /JOIN historical_price native ON native\.document_id=pair\.pdf_sha/);
    assert.match(sql, /native\.details->>'literal_source_locator'='PDF page 5,col 2,line 17-19'/);
    assert.match(sql, /JOIN published_price_observation winner/);
    assert.match(sql, /winner\.document_id=pair\.xls_sha/);
    assert.match(sql, /winner\.source_locator=\$19/);
    assert.match(sql, /winner\.price=pair\.xls_price/);
    assert.match(sql, /winner\.min_price=pair\.min_price/);
    return { rows: [{ market_id: canonical }] };
  } };
  assert.equal(await resolveMarketAlias(db, oldId), canonical);
  assert.equal(queries, 1);
});

test('wrong source or SHA, absent review, unpublished correction and ambiguous target never alias', async () => {
  const scenarios = [[], [], [], [], [{ market_id: canonical }, { market_id: 'other' }],
    [{ market_id: 'other' }]];
  for (const rows of scenarios) {
    const db = { query: async () => ({ rows }) };
    assert.equal(await resolveMarketAlias(db, oldId), oldId);
  }
});
