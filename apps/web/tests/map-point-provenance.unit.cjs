const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript');
const labelModule = {};
const sharedLabels = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/label-normalization.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { exports: labelModule, require: name => {
    assert.equal(name, '../../../../shared/label-normalization.json');
    return { default: sharedLabels };
  } });
test('supply map honors the requested regional history and retains its real month and all original sources', async () => {
  for (const history of ['all', 'recent']) {
    const exports = {}, point = { id: 'barranquillita', name: 'Barranquilla, Barranquillita',
      region: 'Atlántico', department_id: '08', latitude: 10.98, longitude: -74.8,
      value: 31.25, date: '2014-03-29', unit: 'kg', period_start: '2014-03-01',
      sources: [{ document_id: 'original-a', title: 'Anexo.xlsx' }, { document_id: 'original-b', title: 'Complemento.xlsx' }] };
    const mocks = {
      './db': { WINDOW: 'RECENT_WINDOW', database: () => ({ query: async query => {
        assert.equal(query.marker, 'scoped-supply-query'); return { rows: [point] };
      } }) },
      '../filter-labels': { departmentVariants: region => {
        assert.equal(region, 'Atlántico'); return ['Atlántico', 'ATLÁNTICO'];
      } },
      './supply-sql': { supplyMapQuery: (product, departments, window) => {
        assert.equal(product, 'papa-unica'); assert.deepEqual(departments, ['Atlántico', 'ATLÁNTICO']);
        assert.equal(window, history === 'all' ? 'observed_on<=CURRENT_DATE' : 'RECENT_WINDOW');
        return { marker: 'scoped-supply-query' };
      } },
    };
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
      '../src/lib/server/explore.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
      { exports, require: name => mocks[name] || {} });
    const map = await exports.mapData('product', 'papa-unica', 'supply', { region: 'Atlántico', history,
      series: 'city', presentation: 'Bulto', units: '50 Kilogramo' });
    assert.equal(map.period_start, '2014-03-01');
    assert.equal(map.date, '2014-03-29');
    assert.deepEqual(map.points, [point]);
    assert.deepEqual(JSON.parse(JSON.stringify(map.filters)), { region: 'Atlántico', history });
    assert.match(map.basis, /Llegadas reportadas/);
  }
});
test('filtered product map retains the price source row and all selected filters', async () => {
  const exports = {};
  const filters = { series: 'city', presentation: 'Caja de cartÓn', units: '24 Kilogramo',
    market: 'barranquillita', region: 'Atlántico', history: 'all' };
  const source = { id: 'barranquillita', name: 'Barranquilla, Barranquillita', region: 'Atlántico',
    price: 103000, min_price: 101000, max_price: 105000, series: 'city', date: '2026-10-02', document_id: 'retained-city-original', source_page: 1,
    source_locator: 'PDF page 1,table 1,row 7,round 1', presentation: 'Caja de cartÓn', units: '24 Kilogramo' };
  const mocks = {
    '../label-normalization': labelModule,
    './db': { database: () => ({ query: async () => ({ rows: [{ id: source.id, department_id: '08',
      latitude: 10.98, longitude: -74.8 }] }) }) },
    './price-quotes': { filteredProduct: async (id, region, received) => {
      assert.deepEqual(received, filters);
      assert.equal(region, 'Atlántico');
      return { product: { id, name: 'Limón tahití' }, filters, options: {}, markets: [source] };
    } },
  };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
    '../src/lib/server/explore.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    { exports, require: name => mocks[name] || {} });
  const map = await exports.mapData('product', 'limon-tahiti', 'price', filters);
  assert.deepEqual(map.filters, filters);
  assert.equal(map.selection_label, 'Limón tahití');
  assert.equal(map.points.length, 1);
  assert.equal(map.points[0].value, 103000);
  assert.equal(map.points[0].series, 'city');
  assert.equal(map.points[0].min_price, 101000);
  assert.equal(map.points[0].max_price, 105000);
  assert.match(map.basis, /Punto medio calculado/);
  assert.match(map.basis, /No es un promedio publicado por DANE/);
  assert.equal(map.points[0].source_locator, source.source_locator);
  assert.equal(map.points[0].source_page, 1);
  assert.equal(map.points[0].document_id, source.document_id);
  assert.match(map.unit, /Caja de cartón/);
  assert.equal(map.filters.presentation, 'Caja de cartÓn');
});

test('input map retains an exact source municipality without inventing one for a department average', async () => {
  for (const scope of ['municipality', 'department']) {
    const exports = {};
    const input = { id: 'ethrel', name: 'Ethrel 48 Sl', department: 'Valle del Cauca',
      municipality: scope === 'municipality' ? 'Dagua' : '', price: 71450,
      presentation: '200 centímetros cúbicos', observed_on: '2024-01-31',
      document_id: '73cc2a774fdac47799294fb9849c8c4c62a20d291b29782bd1b46c12fdc525ec',
      source_locator: '1.1!row 254; column 9' };
    const mocks = {
      './db': { database: () => ({ query: async () => ({ rows: [{ id: '76233', name: 'DAGUA',
        department_id: '76', department: input.department, latitude: 3.65, longitude: -76.69 }] }) }) },
      './planning': { inputs: async (_region, receivedScope, historical, id) => {
        assert.equal(receivedScope, scope); assert.equal(historical, true); assert.equal(id, 'ethrel');
        return [input];
      } },
      '../input-identity-equivalence': require('./helpers/load-input-identity-equivalence.cjs')(),
      '../input-locations': { latestInputLocations: rows => rows, municipalityKey: s => s.toLowerCase(), municipalityLabel: s => s },
      '../filter-labels': { departmentKey: s => s },
    };
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
      '../src/lib/server/explore.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
      { exports, require: name => mocks[name] || {} });
    const map = await exports.mapData('input', 'ethrel', 'price', { scope, history: 'all' });
    assert.equal(map.points.length, 1);
    assert.equal(map.points[0].municipality, scope === 'municipality' ? 'Dagua' : undefined);
    assert.equal(map.points[0].document_id, input.document_id);
    assert.equal(map.points[0].source_locator, input.source_locator);
    assert.equal(map.points[0].value, input.price);
    assert.equal(map.points[0].date, input.observed_on);
  }
});
