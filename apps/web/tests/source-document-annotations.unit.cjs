const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');
const moduleOut = {};
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/server/source-document-sql.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(moduleOut);
const SQL = moduleOut.SOURCE_DOCUMENT_EVIDENCE_SQL;
const migration = fs.readFileSync(path.join(__dirname, '../../../pipelines/ingestion/migrations/20260928_021_source_document_annotations.sql'), 'utf8');
const socket = process.env.AGRO_ANNOTATION_SQL_TEST_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-source-annotation-');
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated temporary PostgreSQL instance' }, fn);
let db, original;
const DID = 'a'.repeat(64), OTHER = 'b'.repeat(64);
const OLD = 'Serie original 2018-2026; observaciones de la app limitadas a los últimos 12 meses';
const NEW = 'Enero de 2018 a julio de 2026 (serie departamental publicada)';
async function annotation(value, options = {}) {
  return db.query(`INSERT INTO source_document_annotation(document_id,field,original_value,corrected_value,reason,native_locators,created_at)
    VALUES($1,$2,$3,$4,$5,$6,'2026-09-28T00:00Z') ON CONFLICT DO NOTHING RETURNING annotation_id`,
    [options.did || DID, options.field || 'reference_period', options.original ?? OLD, value, options.reason ?? 'Printed original heading', options.locators ?? ['1.3!A3', '2.1!A3']]);
}
async function source() { return (await db.query('SELECT * FROM source_document WHERE id=$1', [DID])).rows[0]; }
async function evidence(id = DID) { return (await db.query(SQL, [id])).rows[0]; }
before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65458, database: 'postgres' }); await db.connect();
  await db.query(`SET statement_timeout='10s';
    CREATE ROLE agro_reader; CREATE ROLE agro_ingestor;
    CREATE TABLE source_document(id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,kind text,reference_period text,retrieved_at timestamptz DEFAULT now(),page_count int,content bytea,metadata jsonb);
    CREATE TABLE document_alias(alias text PRIMARY KEY,document_id text REFERENCES source_document(id));
    CREATE FUNCTION prevent_history_removal() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'Permanent historical data cannot be changed';END$$;
    CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE OR TRUNCATE ON source_document FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
    GRANT SELECT ON source_document,document_alias TO agro_reader,agro_ingestor;`);
  await db.query("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) VALUES($1,'Original workbook','DANE','https://official/original.xlsx','application/xlsx','original',$2,NULL,$3,$4),($5,'Other','DANE','https://official/other.xlsx','application/xlsx','original','Other period',NULL,$3,'{}')", [DID, OLD, Buffer.from('immutable original bytes'), { origin: 'native', nested: { unchanged: true } }, OTHER]);
  await db.query("INSERT INTO document_alias VALUES('input-static',$1)", [DID]);
  await db.query(migration); original = await source();
});
after(async () => { if (db) await db.end(); });
check('unannotated document and alias retain exact original metadata and period', async () => {
  assert.equal((await evidence()).reference_period, OLD);
  assert.deepEqual((await evidence('input-static')).metadata, original.metadata);
  assert.equal(await evidence('missing'), undefined);
});
check('annotation changes only effective response period and exposes full original/audit provenance', async () => {
  await annotation(NEW);
  assert.deepEqual(await source(), original);
  const r = await evidence('input-static');
  assert.equal(r.reference_period, NEW); assert.equal(r.title, original.title);
  assert.equal(r.publisher, original.publisher); assert.equal(r.bytes, original.content.length);
  assert.equal(r.metadata.original_reference_period, OLD);
  assert.deepEqual(r.metadata.nested, original.metadata.nested);
  assert.equal(r.metadata.source_document_annotations.length, 1);
  assert.deepEqual(r.metadata.source_document_annotations[0].native_locators, ['1.3!A3', '2.1!A3']);
  assert.equal(r.metadata.source_document_annotations[0].original_value, OLD);
  assert.equal((await evidence(OTHER)).reference_period, 'Other period');
});
check('equal timestamps resolve by append order; superseded annotations remain and can explicitly restore original', async () => {
  await annotation('January 2018–July 2026');
  let r = await evidence(); assert.equal(r.reference_period, 'January 2018–July 2026');
  assert.equal(r.metadata.source_document_annotations.length, 2);
  await annotation(OLD, { reason: 'Explicit return to original wording' });
  r = await evidence(); assert.equal(r.reference_period, OLD);
  assert.equal(r.metadata.source_document_annotations.length, 3);
  assert.deepEqual(await source(), original);
});
check('unknown fields, wrong original values and absent native/reason evidence reject', async () => {
  for (const options of [{ field: 'title' }, { original: 'invented' }, { did: 'c'.repeat(64) }, { reason: ' ' }, { locators: [] }, { locators: [''] }, { locators: [null] }]) {
    await assert.rejects(annotation('bad', options));
  }
  assert.equal((await evidence()).metadata.source_document_annotations.length, 3);
});
check('original source and annotation immutability remain enforced for updates/deletes/truncation', async () => {
  for (const sql of ["UPDATE source_document SET reference_period='bad'", "UPDATE source_document_annotation SET reason='bad'", 'DELETE FROM source_document_annotation', 'TRUNCATE source_document_annotation']) {
    await assert.rejects(db.query(sql), /Permanent historical data/);
  }
  assert.deepEqual(await source(), original);
});
check('repeated migration and exact repeat insertion preserve annotation history', async () => {
  await db.query(migration);
  const before = (await evidence()).metadata.source_document_annotations;
  await annotation(NEW);
  assert.deepEqual((await evidence()).metadata.source_document_annotations, before);
});
check('reader can resolve evidence but cannot append; ingestor can append without source UPDATE', async () => {
  await db.query('SET ROLE agro_reader');
  assert.equal((await evidence()).reference_period, OLD);
  await assert.rejects(annotation('denied'), { code: '42501' });
  await db.query('RESET ROLE'); await db.query('SET ROLE agro_ingestor');
  await annotation(NEW, { reason: 'A subsequent reviewed correction' });
  assert.equal((await evidence()).reference_period, NEW);
  await db.query('RESET ROLE'); assert.deepEqual(await source(), original);
});
check('rolled-back annotation never changes public evidence or the original', async () => {
  const before = await evidence();
  await db.query('BEGIN'); await annotation('not committed'); await db.query('ROLLBACK');
  assert.deepEqual(await evidence(), before); assert.deepEqual(await source(), original);
});
