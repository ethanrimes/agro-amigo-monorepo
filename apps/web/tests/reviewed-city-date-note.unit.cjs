const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const reviews = require('../../../pipelines/ingestion/reviewed_city_dates.json');
const subject = {};
new Function('exports', 'require', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/server/reviewed-city-source-markets.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText)(subject, name => {
  assert.equal(name, '../../../../../pipelines/ingestion/reviewed_city_dates.json');
  return { default: reviews };
});
const neivaArchive = reviews.archives.find(archive => archive.archive_id ===
  '2ca39b0eacb32edb497e0be527f93e581de9edecdd5364cda7b7ba7b381a1857');
const neiva = neivaArchive.members.find(member => member.document_id ===
  '43ebf9389cf5831258e3f6363518e917b59b7bfa3e2b384ba0f5684d634f1905');
function evidence(archive = neivaArchive, member = neiva) {
  return {
    id: member.document_id, kind: 'original', publisher: 'DANE',
    media_type: 'application/pdf', source_url: archive.url,
    title: `DANE - ${member.entry_name.split('/').at(-1)}`,
    reference_period: 'Serie histórica completa', bytes: 12345,
    metadata: { ingestion_kind: 'city-pdf', archive_entry: member.entry_name,
      original_filename: member.entry_name.split('/').at(-1), parents: [archive.archive_id] },
  };
}
test('Neiva explains its verified printed 2022 date and literal 2021 ZIP without rewriting originals', () => {
  const value = evidence(), before = structuredClone(value);
  subject.annotateReviewedCityDate(value);
  assert.match(value.metadata.date_resolution_note, /2022-02-10/);
  assert.match(value.metadata.date_resolution_note, /2021-02-10/);
  assert.match(value.metadata.date_resolution_note, /fechas difieren/);
  assert.match(value.metadata.date_resolution_note, /no a la del enlace/);
  const { date_resolution_note, ...metadata } = value.metadata;
  assert.deepEqual({ ...value, metadata }, before);
});
test('each reviewed original explains its own dates without borrowing a different member date', () => {
  for (const archive of reviews.archives) for (const member of archive.members) {
    const value = evidence(archive, member);
    subject.annotateReviewedCityDate(value);
    if (archive.archive_day !== member.printed_day) {
      assert.ok(value.metadata.date_resolution_note.includes(member.printed_day), member.document_id);
      assert.ok(value.metadata.date_resolution_note.includes(archive.archive_day), member.document_id);
    } else assert.equal(value.metadata.date_resolution_note, undefined);
  }
});
test('changed document, URL, provenance, kind, publisher or media type receives no reviewed-date assertion', () => {
  const mutations = [
    value => { value.id = 'a'.repeat(64); },
    value => { value.source_url += '?changed=1'; },
    value => { value.kind = 'extract'; },
    value => { value.media_type = 'text/html'; },
    value => { value.publisher = 'Other'; },
    value => { value.metadata.ingestion_kind = 'daily-pdf'; },
    value => { value.metadata.archive_entry = 'renamed.pdf'; },
    value => { value.metadata.original_filename = 'renamed.pdf'; },
    value => { value.metadata.parents = ['b'.repeat(64)]; },
    value => { value.metadata.parents = neivaArchive.archive_id; },
    value => { delete value.metadata.parents; },
  ];
  for (const mutate of mutations) {
    const value = evidence(); mutate(value);
    const before = structuredClone(value);
    subject.annotateReviewedCityDate(value);
    assert.deepEqual(value, before);
  }
});
