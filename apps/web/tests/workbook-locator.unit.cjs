const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), ts = require('typescript');
const mod = {exports:{}};
new Function('module','exports',ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/workbook-locator.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(mod,mod.exports);
const {workbookLocation} = mod.exports;
test('DANE Spanish department source locators select the cited sheet and row', () => {
  assert.deepEqual(workbookLocation('Hoja 1.3, fila 84352; precio por presentación'), {sheet:'1.3',row:84352});
  assert.deepEqual(workbookLocation('Hoja Boletín diario; fila 18, columna 22'), {sheet:'Boletín diario',row:18,column:22});
});
test('native workbook cell and numbered locators retain their column', () => {
  assert.deepEqual(workbookLocation('1.1!row 15947,col 9'), {sheet:'1.1',row:15947,column:9});
  assert.deepEqual(workbookLocation('Boletín diario!v18'), {sheet:'Boletín diario',row:18,column:22});
});
test('PDF and invalid Spanish rows cannot become workbook targets', () => {
  for (const locator of ['PDF page 4, row y218.33, column 2','Hoja 1.3, fila 0','Hoja 1.3, fila -8','Hoja 1.3, fila 1.5','Hoja 1.3, fila 9007199254740992'])
    assert.equal(workbookLocation(locator), null, locator);
});
