const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const { Client } = require('pg');
const scope = require('./helpers/load-source-scope.cjs')();
const registry = require('../../../shared/source-document-scope.json');
const rejected = registry.documents[0].document_id;
const neighbor = 'a'.repeat(64), parent = registry.documents[0].archive_id;
const web = path.resolve(__dirname, '..');
function load(file, dependencies) {
  const output = {};
  new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(web, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(output, name => {
    if (!(name in dependencies)) throw Error('Unexpected source-scope test dependency ' + name);
    return dependencies[name];
  });
  return output;
}
const subjects = load('src/lib/server/source-document-subjects.ts', {});
const fold = load('src/lib/server/sql-search-fold.ts', {});
const markets = load('src/lib/server/reviewed-city-source-markets.ts', {
  '../../../../../pipelines/ingestion/reviewed_city_dates.json':
    { default: require('../../../pipelines/ingestion/reviewed_city_dates.json') },
});
const archive = load('src/lib/server/source-archive-search.ts', {
  './source-document-subjects': subjects, './sql-search-fold': fold,
  './reviewed-city-source-markets': markets, './source-document-scope': scope,
});
const library = load('src/lib/server/source-library.ts', {
  './source-document-subjects': subjects, './source-document-scope': scope,
});
const evidence = load('src/lib/server/source-document-sql.ts', {
  './source-document-scope': scope, './source-document-subjects': subjects,
});

test('reviewed non-price visibility keeps neighboring held originals and complete publisher ZIPs', () => {
  assert.equal(scope.sourceDocumentInApp(rejected), false);
  assert.equal(scope.sourceDocumentInApp(parent), true);
  assert.equal(scope.sourceDocumentInApp(neighbor), true);
  assert.equal(scope.sourceDocumentInApp('0252263a3e19f9425aba43095bb0f4ad2324ad84741a42a2749626c6467f4459'), true);
  assert.equal(scope.sourceDocumentInApp('58b12b179a9293e584e22473f60a97fab1b632cee35f27318953dc7de10e866c'), true);
});

const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
test('archive, curated alias and evidence SQL exclude the exact unrelated member without deleting it', {
  skip: !socket?.startsWith('/tmp/agro-unified-catalog-pg-') && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='8s'");
    await db.query(`CREATE TEMP TABLE source_document(id text PRIMARY KEY,title text,publisher text,
      reference_period text,kind text,media_type text,retrieved_at timestamptz,
      metadata jsonb,source_url text,page_count int,content bytea);
      CREATE TEMP TABLE document_alias(alias text PRIMARY KEY,document_id text);
      CREATE TEMP TABLE source_document_annotation(annotation_id int,document_id text,field text,
        original_value text,corrected_value text,reason text,native_locators text[],created_at timestamptz);
      CREATE TEMP TABLE crop_suitability(document_id text);
      CREATE TEMP TABLE ingestion_asset(document_id text,status text,kind text,observed_on date)`);
    for (const [id, title, type] of [[rejected, 'DANE - metas2023finalf.pdf', 'application/pdf'],
      [neighbor, 'DANE - price source still awaiting verification.pdf', 'application/pdf'],
      [parent, 'DANE - complete publisher ZIP.zip', 'application/zip']]) {
      await db.query(`INSERT INTO source_document VALUES($1,$2,'DANE','2024','original',$3,
        now(),'{}','https://www.dane.gov.co/files/operaciones/SIPSA/source.zip',2,'original bytes')`, [id, title, type]);
      await db.query('INSERT INTO document_alias VALUES($1,$2)', ['alias-' + id, id]);
    }
    const found = (await db.query(archive.archiveSearchSql(archive.archiveSearchTerms('DANE')),
      archive.archiveSearchTerms('DANE'))).rows;
    assert.deepEqual(found.map(row => row.id).sort(), [neighbor, parent].sort());
    assert.deepEqual((await db.query(library.SOURCE_LIBRARY_SQL)).rows.map(row => row.id).sort(), [neighbor, parent].sort());
    for (const id of [rejected, 'alias-' + rejected])
      assert.equal((await db.query(evidence.SOURCE_DOCUMENT_EVIDENCE_SQL, [id])).rowCount, 0);
    for (const id of [neighbor, parent])
      assert.equal((await db.query(evidence.SOURCE_DOCUMENT_EVIDENCE_SQL, [id])).rows[0].id, id);
    assert.equal((await db.query('SELECT count(*)::int n FROM source_document')).rows[0].n, 3);
    assert.equal((await db.query('SELECT content FROM source_document WHERE id=$1', [rejected])).rows[0].content.toString(), 'original bytes');
  } finally { await db.end(); }
});

test('binary content refuses a resolved non-price alias before any source bytes or blob are fetched', async () => {
  let metadataQueries = 0, sourceReads = 0;
  const db = { async query(sql) {
    if (!sql.includes('octet_length(d.content)')) throw Error('Unexpected source byte read');
    metadataQueries++;
    return { rows: [{ id: rejected, media_type: 'application/pdf', bytes: 9634 }] };
  } };
  const route = load('src/app/api/evidence/[id]/content/route.ts', {
    'next/server': { NextResponse: { json: (body, options) => ({ body, status: options.status }) } },
    '@/lib/server/db': { database: () => db },
    '@/lib/server/location': { spatialContent: () => { throw Error('Unexpected spatial read'); } },
    '@/lib/server/source-storage': { sourceBlob: () => { sourceReads++; throw Error('Unexpected source blob read'); } },
    '@/lib/server/source-document-scope': scope,
    '@/lib/server/source-document-subjects': subjects,
  });
  for (const id of [rejected, 'alias-' + rejected]) {
    const response = await route.GET({ headers: new Headers() }, { params: Promise.resolve({ id }) });
    assert.equal(response.status, 404);
  }
  assert.equal(metadataQueries, 2);
  assert.equal(sourceReads, 0);
});
