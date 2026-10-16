const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const lib = path.join(__dirname, '../src/lib');
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
  new Function('exports', 'require', code)(exports, (name) =>
    name.startsWith('.') ? load(path.relative(lib, path.resolve(path.dirname(full), name)) +
      (path.extname(name) ? '' : '.ts'), cache) : require(name));
  return exports;
}
const { comparisonDisplay } = load('comparison-display.ts');

function quote(fields = {}) {
  return { id: 'limon-tahiti', name: 'limon tahiti', category: 'FRUTAS FRESCAS',
    category_path: ['FRUTAS', 'Citricos'], presentation: 'Caja de cartón',
    units: '12.5 Kilogramo', unit: 'package', series: 'city',
    location_id: 'sipsa-armenia-mercar', location_name: 'Armenia, Mercar',
    department: 'Quindio', price: 2150, date: '2024-03-27',
    document_id: 'source-sha', source_locator: 'PDF page 21,row 3',
    source_page: 21, ...fields };
}

function data(kind, a, sources) {
  return { kind, filters: { a: a.location_id, b: '__national__', series: a.series,
      scope: kind === 'inputs' ? 'municipality' : 'department', history: 'all',
      dates: 'same', product: a.id },
    locations: [{ id: a.location_id, name: a.location_name, series: [a.series] }],
    series: [a.series], a_name: a.location_name, b_name: 'Promedio de Colombia',
    rows: [{ key: 'exact-commercial-identity', a,
      b: { price: 3000, date_from: '2024-03-27', date_to: '2024-03-27',
        location_count: sources.length, sources }, difference: 850, percent: 39.5348837 }],
    matched: 1, unmatched: 0, percent: 39.5348837,
    summaries: [{ category: a.category, subcategory: 'Citricos', count: 1, percent: 39.5348837 }] };
}

test('market comparison spells output and nested national sources after retaining exact identities and arithmetic', () => {
  const a = quote(), source = quote({ location_id: 'sipsa-quindio',
    location_name: 'Quindio', price: 3000, document_id: 'other-original',
    source_locator: '1.1!row14,col5' });
  const raw = data('markets', a, [source]);
  const before = structuredClone(raw);
  const shown = comparisonDisplay(raw);
  assert.equal(shown.rows[0].a.name, 'Limón Tahití');
  assert.equal(shown.rows[0].a.category, 'Frutas frescas');
  assert.deepEqual(shown.rows[0].a.category_path, ['Frutas', 'Cítricos']);
  assert.equal(shown.rows[0].a.department, 'Quindío');
  assert.equal(shown.rows[0].b.sources[0].location_name, 'Quindío');
  assert.ok(shown.summaries.some((summary) => summary.subcategory === 'Cítricos'));
  for (const key of ['id', 'presentation', 'units', 'unit', 'price', 'date',
    'document_id', 'source_locator', 'source_page'])
    assert.deepEqual(shown.rows[0].a[key], before.rows[0].a[key], key);
  assert.deepEqual(shown.rows[0].b.sources[0].document_id, source.document_id);
  for (const key of ['key', 'difference', 'percent'])
    assert.equal(shown.rows[0][key], before.rows[0][key], key);
  for (const key of ['price', 'location_count', 'date_from', 'date_to'])
    assert.equal(shown.rows[0].b[key], before.rows[0].b[key], key);
  assert.deepEqual(shown.filters, before.filters);
  assert.deepEqual(raw, before, 'presentation mapping cannot mutate source input');
});

test('input comparison keeps municipality selector, brand, formulation, numeric package and original cell literal', () => {
  const location = JSON.stringify(['Quindio', 'San Juan Nepomu- ceno']);
  const a = quote({ id: 'wuxal-tapa-negra-16-16-12', name: ' WUXAL  Tapa Negra 16-16-12 ',
    category: 'FERTILIZANTES Y ENMIENDAS', category_path: ['FERTILIZANTES Y ENMIENDAS'],
    location_id: location, location_name: 'San Juan Nepomu- ceno, Quindio',
    municipality: 'San Juan Nepomu- ceno', presentation: '1  Litro', units: '1  Litro',
    unit: 'presentation', series: 'input-municipal', brand: 'BAYER S.A.',
    registration: 'ICA 789', product_line: '16-16-12',
    source_locator: 'Hoja 1.3, fila 84352; precio por presentación' });
  const source = quote({ ...a, location_id: JSON.stringify(['Quindio', 'Dagua']),
    location_name: 'Dagua, Quindio', municipality: 'Dagua', price: 3200 });
  const raw = data('inputs', a, [source]);
  const shown = comparisonDisplay(raw);
  assert.equal(shown.rows[0].a.name, 'WUXAL Tapa Negra 16-16-12');
  assert.equal(shown.rows[0].a.category, 'Fertilizantes y enmiendas');
  assert.equal(shown.a_name, 'San Juan Nepomu- ceno, Quindío');
  assert.equal(shown.locations[0].name, shown.a_name);
  assert.equal(shown.rows[0].b.sources[0].location_name, 'Dagua, Quindío');
  for (const key of ['location_id', 'municipality', 'presentation', 'units', 'unit',
    'brand', 'registration', 'product_line', 'document_id', 'source_locator'])
    assert.equal(shown.rows[0].a[key], a[key], key);
  assert.equal(shown.rows[0].b.price, raw.rows[0].b.price);
  assert.equal(shown.b_name, 'Promedio de Colombia');
});

test('unknown varieties, ñ distinctions and punctuation are not guessed into another identity', () => {
  const a = quote({ id: 'pina-gold-extra', name: 'Pina gold extra',
    category: 'Frutas frescas', category_path: ['Frutas frescas'],
    location_id: 'nariNo-12.5', location_name: 'NariNo · mercado 12.5',
    presentation: 'Caja 12.5 kg', units: '12.5 kg', brand: 'BAYER S.A.',
    registration: 'ICA-789', product_line: 'R-12' });
  const shown = comparisonDisplay(data('markets', a, [a]));
  assert.equal(shown.rows[0].a.name, 'Pina gold extra');
  assert.equal(shown.locations[0].name, 'NariNo · mercado 12.5');
  assert.equal(shown.rows[0].a.presentation, 'Caja 12.5 kg');
  assert.equal(shown.rows[0].a.brand, 'BAYER S.A.');
  assert.equal(shown.rows[0].a.registration, 'ICA-789');
  assert.equal(shown.rows[0].a.product_line, 'R-12');
});

test('category spelling convergence recomputes one count-weighted API summary from unchanged row percentages', () => {
  const first = quote({ id: 'huevo-a', name: 'Huevo rojo A',
    category: 'Lacteos y huevos', category_path: ['Lacteos y huevos'] });
  const raw = data('markets', first, [first]);
  raw.rows = [
    { ...raw.rows[0], key: 'a', percent: 10 },
    { ...raw.rows[0], key: 'b', a: { ...first, id: 'huevo-b' }, percent: 20 },
    { ...raw.rows[0], key: 'c', a: { ...first, id: 'huevo-c', category: 'Lácteos y huevos',
      category_path: ['Lácteos y huevos'] }, percent: 40 },
  ];
  raw.summaries = [
    { category: 'Lacteos y huevos', subcategory: null, count: 2, percent: 15 },
    { category: 'Lácteos y huevos', subcategory: null, count: 1, percent: 40 },
  ];
  raw.matched = 3; raw.percent = 70 / 3;
  const before = structuredClone(raw);
  const shown = comparisonDisplay(raw);
  assert.deepEqual(shown.summaries, [{ category: 'Lácteos y huevos',
    subcategory: null, count: 3, percent: 70 / 3 }]);
  assert.deepEqual(shown.rows.map((row) => row.percent), [10, 20, 40]);
  assert.deepEqual(shown.rows.map((row) => row.key), ['a', 'b', 'c']);
  assert.equal(shown.matched, 3);
  assert.equal(shown.percent, 70 / 3);
  assert.deepEqual(raw, before, 'source rows and former grouping remain unmodified');
});
