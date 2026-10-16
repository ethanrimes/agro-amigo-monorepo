const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const { Client } = require('pg');
const api = {};
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/city-partial-review.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText)(api);
const exact = api.VALLEDUPAR_PARTIAL_SOURCE;
const source = () => ({ id: exact.child, kind: 'original', publisher: 'DANE',
  media_type: 'application/pdf', source_url: exact.url, bytes: 128456,
  metadata: { ingestion_kind: 'city-pdf', archive_entry: exact.entry, parents: [exact.parent] } });
const review = { document_id: exact.child, filename: exact.entry, error_type: 'SourceQuantityOmitted' };
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
let db;
before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  await db.query(`SET search_path=pg_temp; SET statement_timeout='5s';
    CREATE TEMP TABLE source_archive_member(document_id text,archive_id text,entry_name text);
    CREATE TEMP TABLE source_document(id text,kind text,publisher text,media_type text,source_url text,reference_period text);
    CREATE TEMP TABLE ingestion_asset(document_id text,url text,kind text,status text,records integer,observed_on date,processor_version text);
    CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer);
    CREATE TEMP TABLE city_raw(document_id text,held boolean);
    CREATE TEMP VIEW published_regional_price AS SELECT document_id FROM city_raw WHERE NOT held;`);
  await db.query('INSERT INTO source_archive_member VALUES($1,$2,$3)', [exact.child, exact.parent, exact.entry]);
  await db.query("INSERT INTO source_document VALUES($1,'original','DANE','application/zip',$2,'2022-01-07')", [exact.parent, exact.url]);
  await db.query("INSERT INTO ingestion_asset VALUES($1,$2,'city-zip','review',1418,'2022-01-07',$3)", [exact.parent, exact.url, exact.version]);
  await db.query('INSERT INTO ingestion_checkpoint VALUES($1,$2,$3,35),($1,$2,$4,0)',
    [exact.parent, exact.version, exact.step, 'review:' + JSON.stringify(review)]);
  await db.query('INSERT INTO city_raw SELECT $1,false FROM generate_series(1,35)', [exact.child]);
});
after(async () => { if (db) await db.end(); });
const pgTest = (name, run) => test(name, { skip: !enabled && 'Requires isolated AGRO_CATALOG_SQL_SOCKET' }, run);
async function annotated() {
  const item = source(); await api.annotateCityPartialReview(db, item);
  return item.metadata.city_partial_review_note;
}

test('neighbor originals, changed metadata and derived copies never acquire the exact source notice', async () => {
  for (const change of [
    { id: 'neighbor' }, { kind: 'extract' }, { publisher: 'Other' }, { bytes: 128455 },
    { media_type: 'application/zip' }, { source_url: exact.url + '?copy' },
    { metadata: { ...source().metadata, archive_entry: 'other.pdf' } },
    { metadata: { ...source().metadata, parents: ['wrong'] } },
    { metadata: { ...source().metadata, parents: [exact.parent, 'extra'] } },
  ]) {
    const item = { ...source(), ...change };
    await api.annotateCityPartialReview({ query: () => assert.fail('No query for an unbound source') }, item);
    assert.equal(item.metadata.city_partial_review_note, undefined);
  }
});

pgTest('only committed partial publication exposes the Spanish omitted-quantity notice', async () => {
  const item = source(), original = JSON.stringify(item);
  await api.annotateCityPartialReview(db, item);
  assert.match(item.metadata.city_partial_review_note, /35 cotizaciones verificadas/);
  assert.match(item.metadata.city_partial_review_note, /coco.*no indica una cantidad numérica/);
  assert.doesNotMatch(item.metadata.city_partial_review_note, /SourceQuantityOmitted|kilogramo inferido/);
  delete item.metadata.city_partial_review_note;
  assert.equal(JSON.stringify(item), original, 'Stored source identity and metadata remain unchanged');
});

pgTest('wrong current asset state, date, count or version cannot claim 35 published rows', async () => {
  for (const assignment of ["status='pending'", "status='complete'", "records=1417",
    "kind='daily-zip'", "observed_on='2022-01-08'", "processor_version='city-v8'", "url='wrong'"]) {
    await db.query('BEGIN');
    try { await db.query('UPDATE ingestion_asset SET ' + assignment); assert.equal(await annotated(), undefined); }
    finally { await db.query('ROLLBACK'); }
  }
});

pgTest('a withdrawn row or extra published row prevents a false complete-count notice', async () => {
  for (const mutation of [
    'UPDATE city_raw SET held=true WHERE ctid=(SELECT ctid FROM city_raw LIMIT 1)',
    'INSERT INTO city_raw SELECT document_id,false FROM city_raw LIMIT 1',
  ]) {
    await db.query('BEGIN');
    try { await db.query(mutation); assert.equal(await annotated(), undefined); }
    finally { await db.query('ROLLBACK'); }
  }
});

pgTest('wrong parent/member lineage or publisher identity cannot lend its review to this child', async () => {
  for (const mutation of [
    "UPDATE source_archive_member SET entry_name='wrong.pdf'",
    "UPDATE source_archive_member SET archive_id='wrong'",
    "UPDATE source_document SET source_url='wrong'",
    "UPDATE source_document SET kind='extract'",
    "UPDATE source_document SET publisher='Other'",
    "UPDATE source_document SET media_type='application/pdf'",
    "UPDATE source_document SET reference_period='2022-01-08'",
  ]) {
    await db.query('BEGIN');
    try { await db.query(mutation); assert.equal(await annotated(), undefined); }
    finally { await db.query('ROLLBACK'); }
  }
});

pgTest('missing or wrong child publication checkpoint cannot borrow another member count', async () => {
  for (const mutation of [
    "UPDATE ingestion_checkpoint SET records=34 WHERE records=35",
    "UPDATE ingestion_checkpoint SET step='city-member:other' WHERE records=35",
    "UPDATE ingestion_checkpoint SET processor_version='new' WHERE records=35",
  ]) {
    await db.query('BEGIN');
    try { await db.query(mutation); assert.equal(await annotated(), undefined); }
    finally { await db.query('ROLLBACK'); }
  }
});

pgTest('malformed, different-member and unrelated review payloads remain unexposed', async () => {
  for (const step of ['review:{', 'review:' + JSON.stringify({ ...review, document_id: 'wrong' }),
    'review:' + JSON.stringify({ ...review, filename: 'wrong.pdf' }),
    'review:' + JSON.stringify({ ...review, error_type: 'SourceDateMismatch' })]) {
    await db.query('BEGIN');
    try { await db.query('UPDATE ingestion_checkpoint SET step=$1 WHERE records=0', [step]); assert.equal(await annotated(), undefined); }
    finally { await db.query('ROLLBACK'); }
  }
});
