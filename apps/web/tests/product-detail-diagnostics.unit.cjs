const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(filename, imports = {}, log = []) {
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  });
  assert.equal(output.diagnostics?.length || 0, 0);
  const exports = {};
  vm.runInNewContext(output.outputText, {
    exports, require: name => {
      if (name === 'server-only') return {};
      if (name in imports) return imports[name];
      throw Error(`missing mock ${name}`);
    }, console: { error: value => log.push(value) }, performance,
    Map, Set, WeakMap, Promise, Date, Object, Array,
  }, { filename });
  return exports;
}
const server = path.join(__dirname, '../src/lib/server');
const helper = load(path.join(server, 'product-detail-diagnostics.ts'));
const defaultDimensions = load(path.join(server, '../product-filter-defaults.ts'));

test('failure diagnostics bound durations and omit source, query and credential text', () => {
  const event = helper.productDetailFailureEvent(
    new helper.ProductDetailStageError('selected_quotes', 1e9,
      { code: '57P01', message: 'SQL SELECT secret/password' }),
    'mandarina-arrayana\nsecret:password',
    { series: 'monthly', history: 'all', region: 'Atlantic secret',
      market: 'SELECT password FROM users', presentation: 'source payload', units: 'secret' },
    Infinity,
  );
  assert.equal(event.stage, 'selected_quotes');
  assert.equal(event.stage_duration_ms, 120000);
  assert.equal(event.duration_ms, 0);
  assert.equal(event.code, '57P01');
  assert.equal(event.filters.series, 'monthly');
  assert.equal(event.filters.history, 'all');
  assert.equal(event.filters.market_present, true);
  for (const forbidden of ['password', 'SELECT', 'Atlantic', 'source payload', 'SQL'])
    assert.ok(!JSON.stringify(event).includes(forbidden));
  assert.equal(helper.productDetailFailureEvent({ code: 'BAD_ SQL secret' }, 'x', {}, -8).code, 'UNKNOWN');
  assert.equal(helper.productDetailFailureEvent(new Error('PRODUCT_DETAIL_BUSY'), 'x', {}, 1).code, 'PRODUCT_DETAIL_BUSY');
});

test('actual product reader attributes each failed branch including concurrent quotes and summaries', async () => {
  const aliases = { CITY_ALIAS_NAMES_SQL: '', CORABASTOS_CITY_MARKET_ID: 'corabastos',
    cityCrossAliasConflictSql: () => 'FALSE', cityMarketIdSql: () => 'm.id',
    cityMarketJoinSql: () => 'TRUE', cityMarketNameSql: () => 'm.name',
    citySourceMarketIdSql: () => 'm.id', resolveCityMarketId: x => x };
  let activeDb, summaryFailure = null, summaryInvocations = 0;
  const packagePath = path.join(server, 'city-package-equivalence.ts');
  const packageIdentity = fs.existsSync(packagePath) ? load(packagePath) : undefined;
  const price = load(path.join(server, 'price-quotes.ts'), {
    '../price-classification': { currentClassifications: () => [] },
    '../label-normalization': { normalizeLabel: x => x, normalizeOfficialLabels: x => x },
    './db': { database: () => activeDb, WINDOW: 'TRUE' },
    './summary-references': { summaryReferencesForProduct: async () => {
      summaryInvocations++; if (summaryFailure) throw summaryFailure; return [];
    } },
    './product-detail-diagnostics': helper,
    './city-package-equivalence': packageIdentity,
    './category-path-sql': require('./helpers/load-category-path-sql.cjs')(),
    '../product-filter-defaults': defaultDimensions,
    './market-alias': { resolveMarketAlias: async (_, x) => x },
    './city-market-alias': aliases,
  });
  const options = [{ series: 'monthly', market_id: 'm1', market_name: 'Bogotá',
    presentation: 'Por unidad de medida', units: '1 kg', requires_revision_resolution: false }];
  for (const stage of ['product_lookup', 'filter_options', 'selected_quotes', 'summary_references']) {
    const calls = [];
    activeDb = { query: async sql => {
      calls.push(sql);
      if (calls.length === 1) {
        if (stage === 'product_lookup') throw { code: '57014' };
        return { rows: [{ id: 'mandarina-arrayana', name: 'Mandarina Arrayana', category: 'Frutas' }] };
      }
      if (calls.length === 2) {
        if (stage === 'filter_options') throw { code: '57014' };
        return { rows: options };
      }
      if (stage === 'selected_quotes') throw { code: '57014' };
      return { rows: [{ markets: [], history: [] }] };
    } };
    summaryFailure = stage === 'summary_references' ? { code: 'XX000', message: 'secret SQL' } : null;
    const before = summaryInvocations;
    const error = await price.filteredProduct('mandarina-arrayana', '',
      { series: 'monthly', presentation: 'Por unidad de medida', units: '1 kg', history: 'recent' })
      .then(() => null, e => e);
    assert.ok(error instanceof helper.ProductDetailStageError);
    assert.equal(error.stage, stage);
    assert.equal(error.failureCode, stage === 'summary_references' ? 'XX000' : '57014');
    assert.equal(calls.length, stage === 'product_lookup' ? 1 : stage === 'filter_options' ? 2 : 3);
    if (stage === 'selected_quotes' || stage === 'summary_references')
      assert.equal(summaryInvocations, before + 1);
  }
});

test('product route retains its 503 response and emits one sanitized stage event', async () => {
  const logs = [];
  const route = load(path.join(__dirname, '../src/app/api/products/[id]/route.ts'), {
    'next/server': { NextResponse: { json: (body, opts) => ({ body, status: opts.status }) } },
    '@/lib/server/price-quotes': { filteredProduct: async () => {
      throw new helper.ProductDetailStageError('summary_references', 8, { code: '57014', message: 'SECRET SQL' });
    } },
    '@/lib/server/product-detail-diagnostics': helper,
  }, logs);
  const request = { nextUrl: { searchParams: new URLSearchParams(
    'series=monthly&history=recent&market=SQLpassword&units=1+kg&region=SecretDepartment') } };
  const response = await route.GET(request, { params: Promise.resolve({ id: 'mandarina-arrayana' }) });
  assert.equal(response.status, 503);
  assert.deepEqual(JSON.parse(JSON.stringify(response.body)),
    { error: 'No pudimos consultar este producto. Intenta de nuevo.' });
  assert.equal(logs.length, 1);
  const logged = JSON.parse(logs[0]);
  assert.equal(logged.stage, 'summary_references');
  assert.equal(logged.code, '57014');
  assert.equal(logged.filters.region_present, true);
  for (const forbidden of ['SECRET', 'SQLpassword', 'SecretDepartment'])
    assert.ok(!logs[0].includes(forbidden));
});
