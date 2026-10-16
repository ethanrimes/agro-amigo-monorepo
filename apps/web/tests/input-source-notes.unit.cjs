const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const subject = {};
new Function('exports', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/input-source-notes.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText)(subject);
const id = '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403';
const quote = () => ({ document_id: id, name: 'Agrotin Sl', presentation: '1 litro 1234' });
const evidence = () => ({
  id, kind: 'original', publisher: 'DANE', media_type: 'application/pdf', bytes: 2028524,
  source_url: 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf',
  metadata: { ingestion_kind: 'context-pdf', original_filename: 'insumos_factores_de_produccion_mar_2014.pdf' },
});
test('literal ambiguous presentation is explained without changing the quote or merging presentations', () => {
  const q = quote(), before = structuredClone(q);
  assert.match(subject.inputPresentationSourceNote(q), /1 litro 1234/);
  assert.match(subject.inputPresentationSourceNote(q), /no hemos verificado que sean equivalentes/);
  assert.deepEqual(q, before);
  for (const change of [{ presentation: '1 litro' }, { document_id: 'a'.repeat(64) }, { name: 'Other' }, { source_name: 'Other' }]) {
    assert.equal(subject.inputPresentationSourceNote({ ...quote(), ...change }), null);
  }
});
test('only the exact retained original receives the source notice and its original fields remain intact', () => {
  const e = evidence(), before = structuredClone(e);
  subject.annotateInputSourceAmbiguity(e);
  assert.match(e.metadata.presentation_source_note, /páginas 48–49/);
  const { presentation_source_note, ...metadata } = e.metadata;
  assert.deepEqual({ ...e, metadata }, before);
  for (const change of [{ id: 'a'.repeat(64) }, { kind: 'extract' }, { publisher: 'Other' }, { media_type: 'text/html' }, { bytes: 1 }, { source_url: before.source_url + '?changed' }, { metadata: { ...before.metadata, ingestion_kind: 'city-pdf' } }, { metadata: { ...before.metadata, original_filename: 'different.pdf' } }]) {
    const wrong = { ...evidence(), ...change }, original = structuredClone(wrong);
    subject.annotateInputSourceAmbiguity(wrong);
    assert.deepEqual(wrong, original);
  }
});
