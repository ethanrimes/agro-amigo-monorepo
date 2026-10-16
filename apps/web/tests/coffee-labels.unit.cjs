const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function compiled(file, target, requireModule) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      esModuleInterop: true, resolveJsonModule: true },
  }).outputText;
  vm.runInNewContext(code, { exports, require: requireModule });
  return exports;
}

test('coffee delivery market display is canonical without changing exact quote provenance', async () => {
  const lib = path.join(__dirname, '../src/lib');
  const labels = compiled(path.join(lib, 'label-normalization.ts'), null, name => {
    assert.equal(name, '../../../../shared/label-normalization.json');
    return JSON.parse(fs.readFileSync(path.join(__dirname, '../../../shared/label-normalization.json'), 'utf8'));
  });
  const original = { id: 'fnc-delivery-bogota', name: 'Bogota', region: 'Quindio',
    price: 1250000, unit: '125kg', date: '2026-09-30', document_id: 'original-sha',
    source_locator: 'Hoja1!row53', source_url: 'https://official.example/source.xlsx' };
  const queries = compiled(path.join(lib, 'server/queries.ts'), null, name => {
    if (name === './db') return { WINDOW: 'true', database: () => ({ query: async sql => ({ rows:
      sql.includes('FROM coffee_reference') ? [
        { price: 1200000, date: '2026-08-31' }, { price: 1250000, date: '2026-09-30' },
      ] : sql.includes('FROM published_price_observation') ? [original] : [],
    }) }) };
    if (name === '../label-normalization') return labels;
    return {};
  });
  const shown = await queries.coffee();
  assert.equal(shown.markets[0].name, 'Bogotá');
  assert.equal(shown.markets[0].region, 'Quindío');
  for (const field of ['id', 'price', 'unit', 'date', 'document_id', 'source_locator', 'source_url'])
    assert.equal(shown.markets[0][field], original[field]);
  assert.equal(original.name, 'Bogota');
  assert.equal(shown.price, 1250000);
  assert.equal(shown.previous_price, 1200000);
});
