const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const ts = require('typescript'), React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const root = path.join(__dirname, '../src');
function load(file, imports = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function('exports', 'require', code)(exports, name => imports[name] || require(name));
  return exports;
}
const { EvidenceLink } = load('components/planning/EvidenceLink.tsx', {
  './EvidenceProvider': { useEvidence: () => () => {} },
  '@/lib/workbook-locator': load('lib/workbook-locator.ts'),
  '@/lib/pdf-locator': load('lib/pdf-locator.ts'),
});
const { QuoteEvidence } = load('components/comparison/QuoteEvidence.tsx', {
  '@/components/planning/EvidenceLink': { EvidenceLink },
});
function source(quote, kind) {
  const html = renderToStaticMarkup(React.createElement(QuoteEvidence, { quote, kind }));
  return new URL(html.match(/href="([^"]+)"/)[1].replaceAll('&amp;', '&'), 'https://qa.invalid');
}
test('market city-card consultation retains the exact PDF row and package identity', () => {
  const quote = { document_id: 'city-original', source_locator: 'PDF page 1,row 18,round 1',
    id: 'mora-de-castilla', name: 'Mora de Castilla', location_id: 'sipsa-barranquilla-barranquillita',
    location_name: 'Barranquilla, Barranquillita', presentation: 'Caja de cartón', units: '12.5 Kilogramo',
    department: 'Atlántico', date: '2026-10-02' };
  const url = source(quote, 'markets'), q = url.searchParams;
  assert.equal(url.pathname, '/evidence/city-original');
  assert.equal(q.get('page'), '1');
  assert.equal(q.get('locator'), quote.source_locator);
  assert.equal(q.get('productName'), quote.name);
  assert.equal(q.get('marketName'), quote.location_name);
  assert.equal(q.get('presentation'), quote.presentation);
  assert.equal(q.get('units'), quote.units);
  assert.equal(q.get('month'), quote.date);
});
test('input comparison opens the native cell with town, package and historical date', () => {
  const quote = { document_id: 'input-original', source_locator: '1.1!row 15947,col 9',
    id: 'wuxal', name: 'Wuxal Tapa Negra', location_id: 'input-armenia',
    location_name: 'Armenia, Quindío', department: 'Quindío', municipality: 'Armenia',
    presentation: '1 litro', units: '1 litro', date: '2014-09-30' };
  const q = source(quote, 'inputs').searchParams;
  assert.equal(q.get('sheet'), '1.1');
  assert.equal(q.get('row'), '15947');
  assert.equal(q.get('col'), '9');
  assert.equal(q.get('input'), 'wuxal');
  assert.equal(q.get('productName'), quote.name);
  assert.equal(q.get('municipality'), 'Armenia');
  assert.equal(q.get('department'), 'Quindío');
  assert.equal(q.get('presentation'), '1 litro');
  assert.equal(q.get('month'), '2014-09-30');
  assert.equal(q.has('market'), false);
});
