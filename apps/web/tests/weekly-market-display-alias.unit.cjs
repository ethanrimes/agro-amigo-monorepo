const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const lib = path.join(__dirname, '../src/lib');
function load(file) {
  const full = path.resolve(lib, file);
  if (full.endsWith('.json')) return JSON.parse(fs.readFileSync(full, 'utf8'));
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true, resolveJsonModule: true },
  }).outputText;
  new Function('exports', 'require', code)(exports, name => {
    if (name.startsWith('.')) return load(path.relative(lib, path.resolve(path.dirname(full), name) +
      (path.extname(name) ? '' : '.ts')));
    return require(name);
  });
  return exports;
}
const { normalizeLabel, normalizeOfficialLabels } = load('label-normalization.ts');
const aliases = {
  'Popayán, Plaza de }mercado del barrio Bolívar': 'Popayán, Plaza de mercado del barrio Bolívar',
  'Bogotá, D.C., Frigorífi co Guadalupe': 'Bogotá, D.C., Frigorífico Guadalupe',
  'Bogotá, D. C., Frigorífi co Guadalupe': 'Bogotá, D.C., Frigorífico Guadalupe',
  'Bogotá, D.C., Frigorífi co Ble Ltda.': 'Bogotá, D.C., Frigorífico Ble Ltda.',
  'Bogotá, D. C., Frigorífi co Ble Ltda.': 'Bogotá, D.C., Frigorífico Ble Ltda.',
};
test('the exact weekly PDF market OCR spellings have the same display alias in TypeScript', () => {
  for (const [raw, canonical] of Object.entries(aliases)) {
    assert.equal(normalizeLabel(raw, 'place'), canonical);
    assert.equal(normalizeLabel(raw.toLocaleUpperCase('es-CO'), 'place'), canonical);
    assert.equal(normalizeLabel(raw, 'input'), raw);
  }
});
test('official quote display changes the market label without changing source identity or raw details', () => {
  const raw = { document_id: '29934d6aea144d87e2a3cfeb5bc6346ec0ac54f8bc11e3d0badf36b67a8a180f',
    source_locator: 'PDF page 49,table 1,column 2,line 37',
    quote_key: '908ac50d1f3fd9c41e04811b8589e420d284f86ad1c2580072a91e6a3d5d0b23',
    product_id: 'bola-de-pierna', product_name: 'Bola de pierna', category: 'Carnes',
    market: 'Popayán, Plaza de }mercado del barrio Bolívar', observed_on: '2026-08-14',
    price: 34667, unit: 'kg', details: { period_type: 'weekly', period_start: '2026-08-08',
      period_end: '2026-08-14', trend: '+', price_statistic: 'published_mean',
      identity_dimensions: { source_product: 'Bola de pierna' } } };
  const original = structuredClone(raw);
  const shown = normalizeOfficialLabels(raw);
  assert.equal(shown.market, aliases[raw.market]);
  assert.equal(shown.document_id, raw.document_id);
  assert.equal(shown.source_locator, raw.source_locator);
  assert.equal(shown.quote_key, raw.quote_key);
  assert.equal(shown.price, 34667);
  assert.deepEqual(shown.details, original.details, 'all source details are retained');
  assert.deepEqual(raw, original, 'normalization returns a display copy without mutation');
});
test('near-miss place names remain literal and are not fuzzy-normalized', () => {
  for (const raw of ['Popayán, Plaza de } mercado del barrio Bolívar',
    'Popayán, Plaza de mercado del barrio Bolívar Norte', 'Bogotá, D. C., Frigorífi co San Martín'])
    assert.equal(normalizeLabel(raw, 'place'), raw);
});
