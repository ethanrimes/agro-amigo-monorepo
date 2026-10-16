const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function renderEvidence(record, mediaType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', metadata = {}) {
  const data = { id: 'original-sha', title: 'Archivo original DANE', publisher: 'DANE',
    source_url: 'https://www.dane.gov.co/original.xlsx', media_type: mediaType,
    kind: 'original', reference_period: '2026', retrieved_at: '2026-10-03T00:00:00Z',
    page_count: null, bytes: 123, metadata, parents: [], records: [record] };
  const root = path.join(__dirname, '../src');
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const mod = { exports: {} }; cache.set(file, mod);
    function imports(name) {
      if (name.endsWith('/useData')) return { useData: () => ({ data, loading: false }) };
      if (name.endsWith('/Shared')) return { ErrorState: () => null };
      if (name.endsWith('/PdfViewer')) return { PdfViewer: () => React.createElement('div', { 'data-testid': 'original-pdf-viewer' }) };
      if (name.endsWith('/WorkbookViewer')) return { WorkbookViewer: () => React.createElement('div', { 'data-testid': 'original-workbook-viewer' }) };
      if (name === './EvidenceProvider') return { useEvidence: () => () => {} };
      if (name.endsWith('.module.css')) return {};
      if (!name.startsWith('.') && !name.startsWith('@/')) return require(name);
      const base = name.startsWith('@/') ? path.join(root, name.slice(2)) : path.resolve(path.dirname(file), name);
      if (name.endsWith('.json')) return JSON.parse(fs.readFileSync(base, 'utf8'));
      const target = [base + '.ts', base + '.tsx'].find(fs.existsSync);
      assert.ok(target, name); return load(target);
    }
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    }).outputText, { module: mod, exports: mod.exports, require: imports, URLSearchParams,
      Date, Intl, console }, { filename: file });
    return mod.exports;
  }
  const { EvidenceContent } = load(path.join(root, 'components/planning/EvidenceContent.tsx'));
  return renderToStaticMarkup(React.createElement(EvidenceContent, {
    id: data.id, query: 'department=Quind%C3%ADo&food=Papa+capira&product=papa-id&productName=Papa+capira&market=armenia&marketName=Armenia%2C+Mercar&units=kg&month=2026-08-01',
  }));
}
const selected = { food_name: 'Papa capira', market_name: 'Armenia, Mercar', quantity_kg: 161000,
  reporting_days: 24, period_start: '2026-08-01', first_reported_on: '2026-08-03',
  observed_on: '2026-08-31', source_rows: { '2.2': [[602025, 602025], [602029, 602030]] } };
test('Excel original and selected monthly sum are both visible, with exact kilos and reporting days', () => {
  const html = renderEvidence(selected);
  assert.match(html, /original-workbook-viewer/);
  assert.match(html, /selected-supply-records/);
  assert.match(html, /161\.000/); assert.match(html, /161 t/);
  assert.match(html, /Días con reporte<\/dt><dd>24/);
  assert.match(html, /Registros originales que forman el total<\/dt><dd>3/);
  assert.match(html, /sheet=2\.2&amp;row=602025/);
  assert.match(html, /market=armenia/); assert.match(html, /food=Papa\+capira/);
  assert.match(html, /department=Quind%C3%ADo/);
  assert.match(html, /month=2026-08-01/);
  assert.match(html, /units=kg/);
});
test('source row ranges remain bounded without truncating the sum or replacing the PDF viewer', () => {
  const record = { ...selected, source_rows: { '2.3': Array.from({ length: 1876 }, (_, i) => [467 + i * 2, 467 + i * 2]) } };
  const html = renderEvidence(record, 'application/pdf');
  assert.match(html, /original-pdf-viewer/);
  assert.match(html, /1\.876/); assert.match(html, /Todos los 1876 intervalos/);
  assert.match(html, /Filas originales de la hoja 2\.3/);
  assert.equal((html.match(/Ver fila \d+ →/g) || []).length, 1);
  assert.doesNotMatch(html, /primeros 100 intervalos/);
});
test('a price observation never becomes a supply sum', () => {
  const html = renderEvidence({ name: 'Papa capira', price: 161000, observed_on: '2026-08-31' });
  assert.match(html, /original-workbook-viewer/);
  assert.doesNotMatch(html, /selected-supply-records/);
});
test('a city PDF held for publication review still renders its original and explains withheld prices', () => {
  const note = 'La extracción de este informe por ciudad presenta diferencias con el PDF original y está pendiente de verificación. Sus precios no se muestran en la aplicación mientras se revisan.';
  const html = renderEvidence({ name: 'Limón Tahití' }, 'application/pdf', { city_pdf_publication_note: note });
  assert.match(html, /original-pdf-viewer/);
  assert.ok(html.includes(note));
  assert.match(html, /role="status"/);
  assert.match(html, /api\/evidence\/original-sha\/content/);
  assert.doesNotMatch(renderEvidence({}, 'application/pdf'), /diferencias con el PDF original/);
});
