const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
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
const { normalizeLabel, normalizeOfficialLabels, normalizeInputLabels, officialProductSearchNames } = load('label-normalization.ts');
const { categoryOptions, categoryVariants, displayDetails } = load('data-reference-labels.ts');

test('printed vegetable category typo cleans display and filter aliases without changing the source quote', () => {
  const raw = ['Verduras y hortailizas', 'Verduras y hortalizas',
    'Verduras y hortailizas > Leguminosas'];
  assert.equal(normalizeLabel(raw[0], 'category'), raw[1]);
  assert.equal(normalizeLabel('VERDURAS Y HORTAILIZAS', 'category'), raw[1]);
  assert.equal(normalizeLabel(raw[2], 'category'), 'Verduras y hortalizas > Leguminosas');
  assert.deepEqual(categoryVariants(raw, raw[1]), raw);
  const original = { product_name: 'Habichuela', category: raw[0], market: 'Ibagué',
    document_id: '4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078',
    source_locator: 'PDF page 2,table 1,row 12,round 1', price: 1700,
    date: '2021-11-16', unit: 'kg', quantity: 1, details: { source_category: raw[0] } };
  assert.deepEqual(normalizeOfficialLabels(original), { ...original, category: raw[1] });
  assert.equal(original.category, raw[0]);
  for (const domain of ['product', 'input']) assert.equal(normalizeLabel(raw[0], domain), raw[0]);
  assert.equal(normalizeLabel('Verduras y hortailizas especiales', 'category'),
    'Verduras y hortailizas especiales');
});

test('data-reference category selector groups only reviewed spellings while querying all raw variants', () => {
  const raw = ['Lacteos y huevos', 'Lácteos y huevos', 'Frutas frescas', 'Frutas frescas', 'Lacteos y huevos.'];
  assert.deepEqual(categoryOptions(raw), ['Lácteos y huevos', 'Frutas frescas', 'Lacteos y huevos.']);
  assert.deepEqual(categoryVariants(raw, 'Lácteos y huevos'), ['Lacteos y huevos', 'Lácteos y huevos']);
  assert.deepEqual(categoryVariants(raw, 'Lacteos y huevos'), ['Lacteos y huevos', 'Lácteos y huevos']);
  assert.deepEqual(categoryVariants(raw, 'Lacteos y huevos.'), ['Lacteos y huevos.']);
  assert.deepEqual(categoryVariants(raw, 'Frutas frescas'), ['Frutas frescas']);
  assert.deepEqual(categoryVariants(raw, 'Carnes'), []);
  assert.deepEqual(categoryVariants(raw, ''), []);
});

test('hierarchical category filter expands only literal source-supported descendants', () => {
  const raw = ['Frutas > Citricos', 'Frutas > Tropicales', 'Frutas frescas',
    'Tubérculos, raíces y plátanos > Plátano'];
  assert.deepEqual(categoryVariants(raw, 'Frutas'), raw.slice(0, 2));
  assert.deepEqual(categoryVariants(raw, 'Frutas > Cítricos'), [raw[0]]);
  assert.deepEqual(categoryVariants(raw, 'Frutas frescas'), [raw[2]]);
  assert.deepEqual(categoryVariants(raw, 'Frutas > Carnes'), []);
});

test('data-reference displayed details clean only named labels, retaining literals and source identity', () => {
  const raw = { Producto: 'Limon Tahiti', Ciudad: 'Quindio', Departamento: 'Quindio',
    Grupo: 'Citricos', Unidad: 'kg', 'Precio (COP)': 1234.567,
    'Variación (%)': -0.6, 'Producto y presentación': 'Wuxal 16-16-12 1 litro',
    'Nombre comercial': 'MARACUYA', source_locator: 'Hoja1!row7' };
  const shown = displayDetails(raw, 'wholesale');
  assert.equal(shown.Producto, 'Limón Tahití');
  assert.equal(shown.Ciudad, 'Quindío');
  assert.equal(shown.Departamento, 'Quindío');
  assert.equal(shown.Grupo, 'Cítricos');
  for (const key of ['Unidad', 'Precio (COP)', 'Variación (%)', 'Producto y presentación',
    'Nombre comercial', 'source_locator']) assert.equal(shown[key], raw[key]);
  assert.equal(raw.Producto, 'Limon Tahiti');
  assert.equal(displayDetails(raw, 'summary').Producto, 'Limon Tahiti', 'input/summary name is commercial');
});

test('only complete, source-backed labels receive canonical accents and casing', () => {
  assert.equal(normalizeLabel('  LiMoN\u200b   TaHiTi  ', 'product'), 'Limón Tahití');
  assert.equal(normalizeLabel('quindio', 'place'), 'Quindío');
  assert.equal(normalizeLabel('caja\u00ad de cartON', 'presentation'), 'Caja de cartón');
  assert.equal(normalizeLabel('citricos', 'category'), 'Cítricos');
  assert.equal(normalizeLabel('frutas > citricos', 'category'), 'Frutas > Cítricos');
  assert.equal(normalizeLabel('frutas frescas', 'category'), 'Frutas frescas');
  assert.equal(normalizeLabel('FRUTAS FRESCAS', 'category'), 'Frutas frescas');
  assert.equal(normalizeLabel('limon tahiti (contiunuación)', 'product'), 'limon tahiti (contiunuación)');
  assert.equal(normalizeLabel('NariNo', 'place'), 'NariNo', 'ñ is not interchangeable with n');
  assert.equal(normalizeLabel('WUXAL  16-16-12', 'input'), 'WUXAL 16-16-12');
});

test('de Ciénaga display spelling retains its separate product and source identity', () => {
  const lexicon = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
  const entry = lexicon.product_display_only[0];
  assert.deepEqual(entry, { raw: 'Limon comun de Cienaga', canonical: 'Limón común de Ciénaga',
    product_id: 'limon-comun-de-cienaga' });
  assert.equal(lexicon.domains.product.length, 382, 'display-only entry does not alter the DANE selector');
  const original = { product_id: entry.product_id, product_name: entry.raw,
    category: 'Frutas', market: 'Barranquilla, Barranquillita',
    document_id: '48218354878fcdbce40a6d321be20821ae64568bddd41e4540c759ea767d1b2e',
    source_locator: 'PDF page 1,table 1,row 13,round 1', observed_on: '2022-01-05',
    presentation: 'Bulto', units: '50 Kilogramo', price: 357500,
    min_price: 355000, max_price: 360000 };
  const shown = normalizeOfficialLabels(original);
  assert.equal(shown.product_name, entry.canonical);
  assert.equal(original.product_name, entry.raw);
  for (const field of ['product_id','document_id','source_locator','observed_on','presentation',
    'units','price','min_price','max_price']) assert.equal(shown[field], original[field]);
  assert.equal(normalizeLabel('LIMON COMUN DE CIENAGA', 'product'), entry.canonical);
  assert.equal(normalizeLabel('Limón común Ciénaga', 'product'), 'Limón común Ciénaga');
  for (const near of ['Limón común', 'Limon comun de Cienaga extra',
    'Limón común de la Ciénaga']) assert.notEqual(normalizeLabel(near, 'product'), entry.canonical);
  assert.equal(normalizeLabel(entry.raw, 'input'), entry.raw);
});

test('de Ciénaga rule refuses an entity merge or mismatched product ID', () => {
  const lexicon = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
  const source = fs.readFileSync(path.join(lib, 'label-normalization.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    esModuleInterop: true, resolveJsonModule: true,
  } }).outputText;
  for (const invalid of [
    { raw: 'Limon comun de Cienaga', canonical: 'Limón común Ciénaga',
      product_id: 'limon-comun-de-cienaga' },
    { raw: 'Limon comun de Cienaga', canonical: 'Limón común de Ciénaga',
      product_id: 'limon-comun-cienaga' },
  ]) {
    assert.throws(() => vm.runInNewContext(compiled, { exports: {}, require(name) {
      assert.equal(name, '../../../../shared/label-normalization.json');
      return { ...lexicon, product_display_only: [invalid] };
    } }), /identity-changing/);
  }
});

test('Caparrapí detached source token is a document-and-row scoped display alias only', () => {
  const fixturePath = path.join(__dirname, '../../../pipelines/ingestion/testdata/panela_caparrapi_1234_reference_fixture.json');
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const original = fixture.reference;
  const evidence = fixture.source_evidence;
  const rule = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'))
    .source_scoped_product_display_only[0];
  assert.equal(evidence.source_url, 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_9feb_15feb_2013.pdf');
  assert.equal(evidence.document_id_sha256, rule.document_id);
  assert.equal(original.document_id, rule.document_id);
  assert.equal(original.source_locator, rule.source_locator);
  assert.equal(original.product_id, rule.product_id);
  assert.equal(original.product_name, rule.raw);
  assert.equal(original.details.identity_dimensions.source_product, rule.source_product);
  assert.equal(evidence.printed_heading, rule.canonical);
  assert.equal(evidence.detached_token, '1234');
  assert.match(evidence.interpretation_limit, /meaning is unresolved/);

  const shown = normalizeOfficialLabels(original);
  assert.equal(shown.product_name, rule.canonical);
  assert.deepEqual(officialProductSearchNames(original), [rule.raw, rule.canonical]);
  assert.equal(original.product_name, rule.raw);
  for (const field of Object.keys(original)) {
    if (field === 'product_name') continue;
    assert.deepEqual(shown[field], original[field], field);
  }
  assert.equal(shown.price, 1550);
  assert.equal(shown.min_price, 1550);
  assert.equal(shown.max_price, 1550);
  assert.equal(shown.observed_on, '2013-02-15');
  assert.equal(shown.source_locator, rule.source_locator);

  for (const [field, value] of [
    ['document_id', 'f'.repeat(64)],
    ['source_locator', 'PDF page 42,table 1,column 1,line 4'],
    ['product_id', 'panela-cuadrada-morena'],
    ['product_name', 'Panela cuadrada morena 1235'],
  ]) {
    const negative = { ...original, [field]: value };
    assert.equal(normalizeOfficialLabels(negative).product_name, value === original.product_name
      ? rule.canonical : negative.product_name, field);
  }
  const wrongDimension = structuredClone(original);
  wrongDimension.details.identity_dimensions.source_product = 'Panela cuadrada morena';
  assert.equal(normalizeOfficialLabels(wrongDimension).product_name, rule.raw);
  for (const numericIdentity of ['Wuxal 16-16-12', 'Wuxal tapa negra 16-16-12 1 litro',
    'Papa R-12 negra', 'Panela cuadrada morena 1234 extra'])
    assert.equal(normalizeLabel(numericIdentity, 'product'), numericIdentity);
});

test('source-scoped display selectors reject duplicates and ambiguous targets at module load', () => {
  const lexicon = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
  const source = fs.readFileSync(path.join(lib, 'label-normalization.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    esModuleInterop: true, resolveJsonModule: true,
  } }).outputText;
  const rule = lexicon.source_scoped_product_display_only[0];
  for (const rules of [
    [rule, { ...rule }],
    [rule, { ...rule, canonical: 'Panela cuadrada' }],
    [{ ...rule, product_id: 'panela-cuadrada-morena' }],
  ]) {
    assert.throws(() => vm.runInNewContext(compiled, { exports: {}, require(name) {
      assert.equal(name, '../../../../shared/label-normalization.json');
      return { ...lexicon, source_scoped_product_display_only: rules };
    } }), /source-scoped product display rule/);
  }
});

test('reviewed joined category spelling keeps raw selectors and evidence intact', () => {
  for (const raw of ['Frutas > Otrasfrutas', 'FRUTAS > OTRASFRUTAS'])
    assert.equal(normalizeLabel(raw, 'category'), 'Frutas > Otras frutas');
  const raw = ['Frutas > Otrasfrutas', 'Frutas > Otras frutas', 'Frutas > Otrasfrutas especiales'];
  assert.deepEqual(categoryVariants(raw, 'Frutas > Otras frutas'), raw.slice(0, 2));
  assert.equal(normalizeLabel('Otrasfrutas especiales', 'category'), 'Otrasfrutas especiales');
  assert.equal(normalizeLabel('Otrasfrutas', 'product'), 'Otrasfrutas');
  assert.equal(normalizeLabel('Otrasfrutas', 'input'), 'Otrasfrutas');
  const original = { product_name: 'Banano urabá', category: raw[0], market: 'Arauca (Arauca)',
    document_id: 'f955e19e02fae8927610bcc104f74bf90121f0f8bea63ee5ac1333fd03ec0737',
    price: 54000, min_price: 52000, max_price: 56000,
    presentation: 'Caja de cartÓn', units: '18 Kilogramo', observed_on: '2025-01-07' };
  const shown = normalizeOfficialLabels(original);
  assert.equal(shown.category, 'Frutas > Otras frutas');
  for (const field of ['document_id', 'price', 'min_price', 'max_price', 'presentation', 'units', 'observed_on'])
    assert.equal(shown[field], original[field]);
  assert.equal(original.category, 'Frutas > Otrasfrutas');
});

test('reviewed tuber child spelling yields one hierarchy choice without changing money or source', () => {
  const raw=['Tuberculos, raices y platanos > Otrostuberculos',
    'Tuberculos, raices y platanos > Otros tuberculos',
    'Tuberculos, raices y platanos > Otros tuberculos especiales'];
  const canonical='Tubérculos, raíces y plátanos > Otros tubérculos';
  assert.deepEqual(categoryVariants(raw,canonical),raw.slice(0,2));
  for(const value of raw.slice(0,2)) assert.equal(normalizeLabel(value,'category'),canonical);
  assert.equal(normalizeLabel('OTROS TUBE\u0301RCULOS','category'),'Otros tubérculos');
  assert.equal(normalizeLabel('Otrostuberculos','product'),'Otrostuberculos');
  assert.equal(normalizeLabel('Otrostuberculos','input'),'Otrostuberculos');
  assert.equal(normalizeLabel('Otrostuberculos especiales','category'),'Otrostuberculos especiales');
  const original={product_name:'Ulluco',category:raw[0],market:'Túquerres (Nariño)',
    document_id:'e64e083358cfbc92d541b47e76c2188f4f3888dbf87786ce0bdbea91e5d3e7ab',
    source_locator:'PDF page 1,table 1,row 16,round 1',price:32500,min_price:30000,max_price:35000,
    presentation:'Bulto',units:'30 Kilogramo',observed_on:'2024-07-17'};
  assert.deepEqual(normalizeOfficialLabels(original),{...original,category:canonical});
  assert.equal(original.category,raw[0]);
});

test('display mapping leaves quote IDs, price, date, unit, package and raw source evidence intact', () => {
  const original = { quote_key: 'literal-key', product_id: 'limon-tahiti', product_name: 'Limon Tahiti',
    category: 'Citricos', market: 'Armenia, Mercar', department: 'Quindio',
    price: 2150, min_price: 2000, max_price: 2400,
    unit: 'kg', observed_on: '2024-03-27', document_id: 'source-sha',
    source_locator: 'PDF page 21,table 1,column 1,line 3',
    details: { literal_product_heading: 'Limón Tahití (contiunuación)' } };
  const shown = normalizeOfficialLabels(original);
  assert.equal(shown.product_name, 'Limón Tahití');
  assert.equal(shown.category, 'Cítricos');
  assert.equal(shown.department, 'Quindío');
  for (const field of ['quote_key', 'product_id', 'price', 'min_price', 'max_price', 'unit',
    'observed_on', 'document_id', 'source_locator', 'details'])
    assert.deepEqual(shown[field], original[field], field);
  assert.deepEqual(original.product_name, 'Limon Tahiti', 'source row is not mutated');
});

test('input spelling receives hygiene only and retains commercial identity', () => {
  const original = { id: 'wuxal-tapa-negra-16-16-12', name: ' Wuxal\u200b Tapa  Negra 16-16-12 ',
    category: 'Fertilizantes y enmiendas', presentation: '1  Litro', department: 'Quindio',
    municipality: 'Ubate', brand: 'BAYER S.A.', registration: '790', product_line: '16-16-12',
    price: 29317, observed_on: '2014-04-30', document_id: 'original',
    source_locator: 'PDF page 13,table 1,row 8' };
  const shown = normalizeInputLabels(original);
  assert.equal(shown.name, 'Wuxal Tapa Negra 16-16-12');
  assert.equal(shown.department, 'Quindío');
  for (const field of ['id', 'presentation', 'municipality', 'brand', 'registration', 'product_line', 'price', 'observed_on',
    'document_id', 'source_locator']) assert.equal(shown[field], original[field], field);
  assert.equal(original.name, ' Wuxal\u200b Tapa  Negra 16-16-12 ');
});

test('catalog search accepts accentless canonical names without equating varieties', () => {
  const { catalogMatches } = load('catalog-display.ts');
  const base = { id: 'limon-tahiti', name: normalizeLabel('Limon Tahiti', 'product'),
    category: 'Cítricos', price: 2150, date: '2024-03-27', source: 'DANE',
    unit: 'kg', search_terms: ['Limon Tahiti'] };
  assert.equal(catalogMatches(base, 'limon tahiti'), true);
  assert.equal(catalogMatches(base, 'limon mandarino'), false);
});

test('catalog category selection accepts both the former literal and canonical label', () => {
  const { paginateCatalog } = load('catalog-page.ts');
  const item = { id: 'limon-tahiti', identity: 'limon-tahiti', saved_key: 'limon-tahiti',
    name: 'Limón Tahití', category: 'Cítricos', image_key: 'produce', price: 2150,
    previous_price: null, date: '2024-03-27', market_count: 1, unit: 'kg', source: 'DANE',
    period: 'weekly', href: '/product/limon-tahiti', kind: 'product', currency: 'COP',
    basis: 'Precio publicado', market: 'Armenia, Mercar', map_supported: true,
    search_terms: ['Limon Tahiti'] };
  const catalog = { products: [item], regions: ['Quindío'], latestDate: item.date,
    filters: { region: '', reference_scope: 'all', excluded_nonregional_count: 0,
      excluded_nonregional_reason: null } };
  for (const category of ['Citricos', 'Cítricos']) {
    const page = paginateCatalog(catalog, { category, q: 'limon tahiti' });
    assert.equal(page.total, 1);
    assert.equal(page.products[0].id, item.id);
    assert.equal(page.categories[0], 'Cítricos');
  }
});
