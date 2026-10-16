const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript'), fs = require('node:fs'), path = require('node:path');
const api = {};
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/pdf-locator.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(api);
test('retained native PDF locations open their one-based page',()=>{
  for(const [locator,page] of [['PDF page 34,col 2,y 691.3; inputs-pdf-v13',34],
    ['PDF page 72,col 1,y 84; inputs-pdf-v14',72],['PDF page 3',3],
    ['PDF page 5, OCR table 1, row 31; printed-row-v2',5]])
    assert.equal(api.evidencePage(null,locator),page);
});
test('explicit approved source page takes precedence over retained locator',()=>{
  assert.equal(api.evidencePage('3','PDF page 4,col 2,line 8; parser milk-pdf-v10'),3);
  assert.equal(api.evidencePage('bad','PDF page 34,col 2,y 691.3'),34);
  assert.equal(api.evidencePage(-2,'PDF page 34,col 2,y 691.3'),34);
});
test('workbook rows and malformed locations do not become PDF pages',()=>{
  for(const locator of ['1.2!row 17381','PDF page 0','PDF page -2','PDF page 3.2',
    'PDF page 123456,col 1','not PDF page 2','PDF page 3malformed',null]) {
    assert.equal(api.pdfLocationPage(locator),undefined);
    assert.equal(api.evidencePage(null,locator),1);
  }
});
