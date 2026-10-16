const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '../../..');
const lib = path.join(root, 'apps/web/src/lib');
function load(file, cache = new Map()) {
  const full = path.resolve(lib, file);
  if (full.endsWith('.json')) return JSON.parse(fs.readFileSync(full, 'utf8'));
  if (cache.has(full)) return cache.get(full);
  const exports = {};
  cache.set(full, exports);
  const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true, resolveJsonModule: true },
  }).outputText;
  new Function('exports', 'require', code)(exports, (name) => {
    if (name.startsWith('.')) return load(path.relative(lib, path.resolve(path.dirname(full), name) +
      (path.extname(name) ? '' : '.ts')), cache);
    return require(name);
  });
  return exports;
}
const { normalizeLabel, normalizeInputLabels } = load('label-normalization.ts');
const { inputLocationDisplayLabel, inputMunicipalityDisplayLabel, mapPointDisplayName, inputLocationId, canonicalInputLocation } = load('input-locations.ts');
const { comparisonDisplay } = load('comparison-display.ts');
const { evidenceQueryContext } = load('evidence-query-context.ts');

test('official DANE place spelling is display-only and exact municipal selector remains raw', () => {
  assert.equal(normalizeLabel('Calarca', 'place'), 'Calarcá');
  assert.equal(normalizeLabel('CALARCA', 'place'), 'Calarcá');
  assert.equal(normalizeLabel('Calarcá', 'place'), 'Calarcá');
  assert.equal(normalizeLabel('Calarca rural', 'place'), 'Calarca rural');
  assert.equal(normalizeLabel('Buga', 'place'), 'Buga');
  assert.equal(normalizeLabel('Guadalajara de Buga', 'place'), 'Guadalajara de Buga');

  const raw = { id: 'urea-granulada', name: 'Urea granulada', category: 'Fertilizantes y enmiendas',
    department: 'Quindio', municipality: 'Calarca', presentation: 'Bulto',
    observed_on: '2026-08-31', price: 99000,
    document_id: 'original-dane-source', source_locator: 'PDF page 7,table 2,row 3' };
  const apiRow = normalizeInputLabels(raw);
  assert.equal(apiRow.department, 'Quindío');
  assert.equal(apiRow.municipality, 'Calarca', 'API selector value remains the exact stored spelling');
  assert.equal(inputLocationDisplayLabel(apiRow.department, apiRow.municipality), 'Calarcá, Quindío');
  assert.equal(inputMunicipalityDisplayLabel(''), '', 'a department-only filter has an empty municipality value');
  assert.equal(inputMunicipalityDisplayLabel('Calarca'), 'Calarcá');
  assert.equal(mapPointDisplayName('input', 'Calarca, Quindío', 'Quindío', 'Calarca'), 'Calarcá, Quindío');
  assert.equal(mapPointDisplayName('market', 'Calarca, Quindío', 'Quindío', 'Calarca'),
    'Calarca, Quindío', 'non-input map point label stays on its existing display path');
  const selector = inputLocationId(raw.department, raw.municipality, true);
  assert.equal(selector, '["Quindío","Calarca"]');
  assert.equal(canonicalInputLocation(selector, true), selector);
  assert.equal(raw.municipality, 'Calarca');
  const query = new URLSearchParams({ municipality: raw.municipality, department: raw.department });
  const queryContext = evidenceQueryContext(undefined, query);
  assert.equal(queryContext.find((item) => item.label === 'Municipio de la consulta').value, 'Calarcá');
  assert.equal(query.get('municipality'), 'Calarca', 'evidence URL/query remains the original selector');
  const sourceContext = [{ label: 'Municipio de referencia', value: 'Calarca' }];
  assert.deepEqual(evidenceQueryContext(sourceContext, new URLSearchParams()), sourceContext,
    'literal source metadata is not relabeled as consultation geography');
  assert.equal(apiRow.document_id, raw.document_id);
  assert.equal(apiRow.source_locator, raw.source_locator);
});

test('municipal comparison labels normalize the display while preserving selector identity', () => {
  const locationId = '["Quindío","Calarca"]';
  const source = { id: 'urea-granulada', name: 'Urea', category: 'Fertilizantes', category_path: ['Fertilizantes'],
    presentation: 'Bulto', units: '50 Kilogramo', unit: 'COP / bulto', series: 'input-municipal',
    location_id: locationId, location_name: 'Calarca, Quindio', department: 'Quindio', municipality: 'Calarca',
    price: 99000, date: '2026-08-31', document_id: 'original-dane-source', source_locator: 'PDF page 7,table 2,row 3' };
  const data = { kind: 'inputs', filters: { scope: 'municipality', a: locationId, b: '__national__' },
    locations: [{ id: locationId, name: 'Calarca, Quindio' }], a_name: 'Calarca, Quindio',
    b_name: 'Colombia', rows: [{ key: 'same-business-key', a: source,
      b: { price: 90000, date_from: '2026-08-01', date_to: '2026-08-31', location_count: 1, sources: [source] },
      difference: -9000, percent: -9.09 }], summaries: [] };
  const shown = comparisonDisplay(data);
  assert.equal(shown.locations[0].id, locationId);
  assert.equal(shown.locations[0].name, 'Calarcá, Quindío');
  assert.equal(shown.a_name, 'Calarcá, Quindío');
  assert.equal(shown.rows[0].b.sources[0].location_name, 'Calarcá, Quindío', 'chooser/source option receives formatted label');
  assert.equal(shown.rows[0].b.sources[0].location_id, locationId);
  assert.equal(shown.rows[0].b.sources[0].municipality, 'Calarca');
  assert.equal(data.locations[0].name, 'Calarca, Quindio', 'source/API input object is not mutated');
});

test('empty municipal filters and unrelated market map names retain their meaning', () => {
  assert.equal(inputMunicipalityDisplayLabel(''), '');
  assert.equal(inputLocationDisplayLabel('Quindio', ''), 'Quindío');
  assert.equal(mapPointDisplayName('input', 'Calarca, Quindio', 'Quindio', 'Calarca'), 'Calarcá, Quindío');
  assert.equal(mapPointDisplayName('input', 'Promedio departamental', 'Quindio', ''), 'Promedio departamental');
  assert.equal(mapPointDisplayName('product', 'Bogotá, Corabastos', 'Cundinamarca', 'Bogotá'), 'Bogotá, Corabastos');
  assert.equal(mapPointDisplayName('market', 'Calarca, Quindío', 'Quindío', 'Calarca'), 'Calarca, Quindío');
});
