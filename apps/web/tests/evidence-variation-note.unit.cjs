const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const repo = (() => {
  let here = __dirname;
  while (!fs.existsSync(path.join(here, 'apps/web/node_modules/typescript'))) here = path.dirname(here);
  return here;
})();
const candidate = path.join(__dirname, '../src');
const ts = require(path.join(repo, 'apps/web/node_modules/typescript'));
const React = require(path.join(repo, 'apps/web/node_modules/react'));
const { renderToStaticMarkup } = require(path.join(repo, 'apps/web/node_modules/react-dom/server'));
const DID = '5f908d72f6b60fd3cf3f331ea2ae9434aa026d5561609b1fe4e085b7cad2ec85';
const PDF_DID = 'bed32e2c8fa86f5d29b9131049c3af027bef80815262ee5db329ad560418c25b';
const XLS_URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_agosto_12_2019.xlsx';
const JAN7_DID = '73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72';
const JAN7_PDF_DID = '2bba2c3ed056b5d2624af824c2d845aadbb16cadb31ab29e3ca26475061abaec';
const JAN7_XLS_URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.xlsx';
const JAN7_PDF_URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.pdf';

function loadTs(file, imports = {}) {
  const exports = {};
  const requireMock = name => {
    if (Object.hasOwn(imports, name)) return imports[name];
    if (name === 'react/jsx-runtime') return require('react/jsx-runtime');
    throw new Error('Unexpected import ' + name);
  };
  const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(js, { exports, require: requireMock, URLSearchParams, Date, Intl, console });
  return exports;
}

const noteModule = loadTs(path.join(candidate, 'lib/server/daily-date-note.ts'));
function evidence(overrides = {}) {
  return {
    id: DID, kind: 'original', source_url: XLS_URL,
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    reference_period: '2019-08-12', records: [{ price: 1020, variation: -46.88, details: { source: 'native XLS' } }],
    metadata: { ingestion_kind: 'daily', unrelated: { retained: true } }, ...overrides,
  };
}

test('exact retained XLS gets response-only note and typed provenance; other evidence and rows stay unchanged', () => {
  const exact = evidence();
  const rows = structuredClone(exact.records);
  const details = structuredClone(exact.metadata);
  noteModule.annotateDailySourceVariation(exact);
  assert.match(exact.metadata.variation_disagreement_note, /−46,88 %.*46,48 %/);
  assert.match(exact.metadata.variation_disagreement_note, /\$1\.020\/kg/);
  assert.deepEqual(JSON.parse(JSON.stringify(exact.metadata.variation_disagreement_sources)), [{
    label: 'Boletín acompañante de DANE', document_id: PDF_DID, page: 1,
    locator: 'Página física 1, párrafo sobre Habichuela en Manizales',
  }]);
  assert.deepEqual(exact.records, rows);
  assert.equal(exact.reference_period, '2019-08-12');
  assert.deepEqual(exact.metadata.unrelated, details.unrelated);
  for (const overrides of [
    { id: 'different-body-sha' },
    { source_url: 'https://example.invalid/other.xlsx' },
    { kind: 'extract' },
    { media_type: 'application/pdf' },
    { metadata: { ingestion_kind: 'city-pdf' } },
  ]) {
    const other = evidence(overrides);
    const before = structuredClone(other);
    noteModule.annotateDailySourceVariation(other);
    assert.deepEqual(other, before);
  }
});

test('Jan 7 Pepino variation discrepancy is disclosed without changing the workbook observation', () => {
  const item = {
    product: 'Pepino cohombro', market: 'Neiva, Surabastos',
    xls_price_cell: 'T14', xls_variation_cell: 'U14', xls_price_cop_per_kg: 1120,
    xls_variation_percent: -25.33, pdf_page: 1, pdf_variation_percent: -25.53,
    policy: 'Not used as a corroborating witness; preserve workbook variation literally.',
  };
  const resolution = {
    archive_date: '2020-01-07', observation_date: '2020-01-07',
    printed_heading: 'Martes 7 de enero de 2019', basis: 'native_year_typo',
    corroborating_url: JAN7_PDF_URL, corroborating_sha256: JAN7_PDF_DID,
    excluded_disagreements: [item],
  };
  const record = { date: '2020-01-07', price: 1120, variation: -25.33, unit: 'kg' };
  const exact = {
    id: JAN7_DID, kind: 'original', source_url: JAN7_XLS_URL,
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    reference_period: '2020-01-07', records: [record],
    metadata: { ingestion_kind: 'daily', unrelated: 'preserved' },
  };
  noteModule.annotateDailyDateResolution(exact, resolution);
  assert.match(exact.metadata.variation_disagreement_note, /Pepino cohombro.*Neiva, Surabastos/);
  assert.match(exact.metadata.variation_disagreement_note, /−25,33 %.*−25,53 %/);
  assert.match(exact.metadata.variation_disagreement_note, /Boletín diario!U14/);
  assert.match(exact.metadata.variation_disagreement_note, /Conservamos la variación literal del anexo/);
  assert.deepEqual(JSON.parse(JSON.stringify(exact.metadata.variation_disagreement_sources)), [{
    label: 'Boletín acompañante de DANE', document_id: JAN7_PDF_DID, page: 1,
    locator: 'Página física 1: variación de Pepino cohombro en Neiva, Surabastos (−25,53 %); el anexo Boletín diario!U14 indica −25,33 %.',
  }]);
  assert.deepEqual(exact.records, [record]);
  assert.equal(exact.reference_period, '2020-01-07');
  assert.equal(exact.metadata.unrelated, 'preserved');

  for (const invalid of [
    { ...resolution, corroborating_sha256: 'not-a-sha' },
    { ...resolution, corroborating_url: 'https://example.invalid/other.pdf' },
    { ...resolution, archive_date: '2020-01-08' },
    { ...resolution, excluded_disagreements: [{ ...item, pdf_page: 0 }] },
    { ...resolution, excluded_disagreements: [{ ...item, xls_variation_percent: '-25.33' }] },
    { ...resolution, excluded_disagreements: [{ ...item, pdf_variation_percent: Number.NaN }] },
    { ...resolution, excluded_disagreements: [{ ...item, xls_variation_cell: '' }] },
    { ...resolution, excluded_disagreements: [{ ...item, market: 'Neiva, otro mercado' }] },
    { ...resolution, excluded_disagreements: [null] },
    { ...resolution, excluded_disagreements: [] },
    { ...resolution, excluded_disagreements: [item, item] },
  ]) {
    const candidate = {
      id: JAN7_DID, kind: 'original', source_url: JAN7_XLS_URL,
      media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      reference_period: '2020-01-07', records: [record],
      metadata: { ingestion_kind: 'daily' },
    };
    noteModule.annotateDailyDateResolution(candidate, invalid);
    assert.equal(candidate.metadata.variation_disagreement_note, undefined);
    assert.equal(candidate.metadata.variation_disagreement_sources, undefined);
    assert.deepEqual(candidate.records, [record]);
  }
  const otherOriginal = {
    id: 'different-source', kind: 'original', source_url: JAN7_XLS_URL,
    media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    reference_period: '2020-01-07', records: [record], metadata: { ingestion_kind: 'daily' },
  };
  noteModule.annotateDailyDateResolution(otherOriginal, resolution);
  assert.equal(otherOriginal.metadata.variation_disagreement_note, undefined);
});

test('generic evidence UI renders a string note and in-app retained-document page link', () => {
  const data = evidence({
    title: 'DANE daily workbook', publisher: 'DANE', retrieved_at: '2019-08-12T00:00:00Z',
    page_count: null, bytes: 70697, parents: [],
    metadata: {
      variation_disagreement_note: 'Se conservan ambas lecturas de la fuente.',
      variation_disagreement_sources: [{
        label: 'Boletín acompañante de DANE', document_id: PDF_DID, page: 1,
        locator: 'Página física 1, párrafo de Habichuela',
      }, { label: 'Bad id', document_id: 'not-a-sha', page: 1, locator: 'invalid' },
      { label: 'Bad page', document_id: PDF_DID, page: 0, locator: 'invalid' },
      { label: '', document_id: PDF_DID, page: 1, locator: 'invalid' }],
    },
  });
  const component = () => React.createElement('span');
  const mocks = {
    'react-icons/io5': { IoDownloadOutline: component, IoShieldCheckmarkOutline: component },
    '@/components/marketplace/useData': { useData: () => ({ data, loading: false, error: null, retry() {} }) },
    '@/components/marketplace/Shared': { ErrorState: () => null },
    '@/components/planning/PdfViewer': { PdfViewer: component },
    '@/components/planning/WorkbookViewer': { WorkbookViewer: component },
    '@/components/planning/SupplyEvidenceRecords': { SupplyEvidenceRecords: component },
    './SupplyEvidenceRecords': { SupplyEvidenceRecords: component },
    '@/components/planning/EvidenceLink': { EvidenceLink: component },
    './EvidenceLink': { EvidenceLink: component },
    '@/lib/evidence-period': { evidencePeriod: () => '12 de agosto de 2019' },
    '@/lib/evidence-value': { evidenceValue: () => null, evidenceUnitNote: () => null },
    '@/lib/market-types': { dateLabel: () => '', number: () => '' },
    '@/lib/workbook-locator': { workbookLocation: () => null },
    '@/lib/pdf-locator': { evidencePage: () => ({ page: null, locator: null }) },
    '@/lib/evidence-query-context': { evidenceQueryContext: () => [] },
  };
  const { EvidenceContent } = loadTs(path.join(candidate, 'components/planning/EvidenceContent.tsx'), mocks);
  const html = renderToStaticMarkup(React.createElement(EvidenceContent, { id: DID, query: '' }));
  assert.match(html, /variation-disagreement-note/);
  assert.match(html, /Se conservan ambas lecturas de la fuente/);
  assert.ok(html.includes(`/evidence/${PDF_DID}?page=1`));
  assert.doesNotMatch(html, /Bad id|Bad page|invalid/);
  assert.match(html, /Boletín acompañante de DANE · Página física 1/);
});
