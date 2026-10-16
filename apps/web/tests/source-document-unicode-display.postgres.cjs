/* Five source-bound Unicode ZIP names, without changing retained originals. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1082, value => value);
const oracle = require('./fixtures/city-unicode-five-source-oracle.json');
const server = path.join(__dirname, '../src/lib/server');
function load(file, dependencies = {}) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync(path.join(server, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('exports', 'require', js)(exports, name => {
    if (!(name in dependencies)) throw Error(`Unexpected source display dependency ${name}`);
    return dependencies[name];
  });
  return exports;
}
const subjects = load('source-document-subjects.ts');
const scope = require('./helpers/load-source-scope.cjs')();
const fold = load('sql-search-fold.ts');
const reviewed = load('reviewed-city-source-markets.ts', {
  '../../../../../pipelines/ingestion/reviewed_city_dates.json':
    { default: require('../../../pipelines/ingestion/reviewed_city_dates.json') },
});
const archive = load('source-archive-search.ts', {
  './source-document-subjects': subjects,
  './source-document-scope': scope,
  './reviewed-city-source-markets': reviewed,
  './sql-search-fold': fold,
});
const library = load('source-library.ts', {
  './source-document-subjects': subjects, './source-document-scope': scope,
});
const evidence = load('source-document-sql.ts', {
  './source-document-subjects': subjects, './source-document-scope': scope,
});
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const selectedSql = `SELECT d.id,d.title AS archived_title,d.metadata->>'original_filename' AS archived_filename,
  ${subjects.SOURCE_DOCUMENT_DISPLAY_TITLE_SQL} AS title,
  ${subjects.SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL} AS filename,
  ${subjects.SOURCE_DOCUMENT_REVIEWED_FILENAME_SQL} AS reviewed_filename,
  d.content,d.metadata,d.source_url FROM source_document d WHERE d.id=$1`;

test('independent retained five-name oracle is NFC, source-bound, and accounts for all 624 published rows', () => {
  assert.equal(oracle.source_review_sha256,
    '4dbc5ea63a10d948fdb0ae0d76cb32da2c4d6b5eef9f5643ad6e326a5fb018b9');
  assert.equal(oracle.documents.length, 5);
  assert.equal(new Set(oracle.documents.map(row => row.id)).size, 5);
  assert.equal(oracle.documents.reduce((sum, row) => sum + row.published_rows, 0), 624);
  for (const row of oracle.documents) {
    assert.equal(row.display_filename, row.display_filename.normalize('NFC'));
    assert.match(row.raw_entry, /∩/);
    assert.notEqual(row.display_filename, row.raw_entry);
    assert.match(row.parent_url, /^https:\/\/www\.dane\.gov\.co\/files\/.+[.]zip$/);
  }
});

test('archive search, library, evidence and exact bytes use corrected names only for matching originals',
  { skip: !enabled && 'Requires owned AGRO_CATALOG_SQL_SOCKET' }, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres', connectionTimeoutMillis: 5000 });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='8s'; SET TIME ZONE 'America/Bogota'");
    await db.query(`CREATE TEMP TABLE source_document(
      id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,kind text,
      reference_period text,retrieved_at timestamptz,page_count int,content bytea,metadata jsonb);
      CREATE TEMP TABLE document_alias(alias text,document_id text);
      CREATE TEMP TABLE source_document_annotation(annotation_id int,document_id text,field text,
        original_value text,corrected_value text,reason text,native_locators text[],created_at timestamptz);
      CREATE TEMP TABLE crop_suitability(document_id text);
      CREATE TEMP TABLE ingestion_asset(document_id text,status text,kind text,observed_on date);
      CREATE TEMP VIEW published_regional_price AS SELECT NULL::text AS document_id,
        NULL::date AS observed_on WHERE false`);
    const originalBytes = new Map();
    for (const item of oracle.documents) {
      const content = Buffer.from(`%PDF-1.7\nsource identity ${item.id}\n`, 'utf8');
      originalBytes.set(item.id, content);
      await db.query(`INSERT INTO source_document VALUES(
        $1,$2,'DANE',$3,'application/pdf','original','Serie histórica completa',
        '2020-12-20T08:00:00Z',1,$4,$5::jsonb)`, [
        item.id, `DANE - ${item.raw_entry}`, item.parent_url, content,
        JSON.stringify({ parents: [item.parent_sha256], retention: 'permanent',
          archive_entry: item.raw_entry, ingestion_kind: 'city-pdf', original_filename: item.raw_entry }),
      ]);
      await db.query('INSERT INTO document_alias VALUES($1,$2)', [`unicode-${item.id}`, item.id]);
    }
    const rows = (await db.query(library.SOURCE_LIBRARY_SQL)).rows;
    assert.equal(rows.length, 5);
    for (const item of oracle.documents) {
      const projection = (await db.query(selectedSql, [item.id])).rows[0];
      const curated = rows.find(row => row.id === item.id);
      const detail = (await db.query(evidence.SOURCE_DOCUMENT_EVIDENCE_SQL, [item.id])).rows[0];
      assert.equal(projection.reviewed_filename, item.display_filename);
      assert.equal(projection.filename, item.display_filename);
      assert.equal(projection.title, `DANE - ${item.display_filename}`);
      assert.equal(projection.archived_title, `DANE - ${item.raw_entry}`);
      assert.equal(projection.archived_filename, item.raw_entry);
      assert.equal(sha(projection.content), sha(originalBytes.get(item.id)));
      assert.equal(projection.metadata.original_filename, item.raw_entry);
      assert.equal(projection.metadata.archive_entry, item.raw_entry);
      assert.equal(curated.title, projection.title);
      assert.equal(curated.filename, projection.filename);
      assert.equal(curated.archived_title, projection.archived_title);
      assert.equal(curated.archived_filename, item.raw_entry);
      assert.equal(detail.title, projection.title);
      assert.equal(detail.metadata.original_title, projection.archived_title);
      assert.equal(detail.metadata.archived_filename, item.raw_entry);
      assert.equal(detail.metadata.display_filename, item.display_filename);
      assert.equal(detail.id, item.id);
      assert.equal(detail.bytes, originalBytes.get(item.id).length);
    }
    const searches = [
      ['Cucuta Cenabastos', ['4aa6ff456c539f9bac8695dee8c575a20f07db5cd7f51bfe682f69c524dcd12b']],
      ['CÚCUTA CENABASTOS', ['4aa6ff456c539f9bac8695dee8c575a20f07db5cd7f51bfe682f69c524dcd12b']],
      ['Cu\u0301cuta Cenabastos', ['4aa6ff456c539f9bac8695dee8c575a20f07db5cd7f51bfe682f69c524dcd12b']],
      ['Monteria Mercado del Sur', ['7024d5b0a8572a852cedd41efbe596de6dc99fa430697559945c09babfdddd60']],
      ['MONTERÍA Mercado del Sur', ['7024d5b0a8572a852cedd41efbe596de6dc99fa430697559945c09babfdddd60']],
      ['Monteri\u0301a Mercado del Sur', ['7024d5b0a8572a852cedd41efbe596de6dc99fa430697559945c09babfdddd60']],
      ['Bogota Corabastos 20-06-2020', ['4dc73a1d7464f11b707b4ca78127d6f5ac6c3e42f419afbae7af4765e056f270']],
      ['Ibague Plaza La 21', ['b2e3895cbd78b10c12ea922ef7b70a3511bd88cbd656e552d5b9c66bd1f61c10']],
    ];
    for (const [query, expected] of searches) {
      const terms = archive.archiveSearchTerms(query);
      assert(terms, query);
      const actual = (await db.query(archive.archiveSearchSql(terms), terms)).rows;
      assert.deepEqual(actual.map(row => row.id).sort(), expected.slice().sort(), query);
      for (const row of actual) {
        const item = oracle.documents.find(value => value.id === row.id);
        assert.equal(row.title, `DANE - ${item.display_filename}`);
        assert.equal(row.filename, item.display_filename);
        assert.equal(row.archived_title, `DANE - ${item.raw_entry}`);
        assert.equal(row.archived_filename, item.raw_entry);
      }
    }
    const target = oracle.documents.find(row => row.display_filename.startsWith('Cúcuta'));
    await db.query('BEGIN');
    const wrong = [
      ['document ID', "id='" + 'f'.repeat(64) + "'"],
      ['parent URL', "source_url='https://www.dane.gov.co/files/other.zip'"],
      ['kind', "kind='extract'"],
      ['media type', "media_type='application/zip'"],
      ['publisher', "publisher='Other'"],
      ['title', "title='DANE - unrelated.pdf'"],
      ['parent pointer', "metadata=jsonb_set(metadata,'{parents}','[\"other-parent\"]'::jsonb)"],
      ['parent object key', `metadata=jsonb_set(metadata,'{parents}','{"${target.parent_sha256}":true}'::jsonb)`],
      ['entry name', "metadata=jsonb_set(metadata,'{archive_entry}','\"unrelated.pdf\"'::jsonb)"],
      ['original filename', "metadata=jsonb_set(metadata,'{original_filename}','\"unrelated.pdf\"'::jsonb)"],
      ['ingestion kind', "metadata=jsonb_set(metadata,'{ingestion_kind}','\"weekly-pdf\"'::jsonb)"],
    ];
    for (const [label, mutation] of wrong) {
      await db.query('SAVEPOINT wrong_source');
      try {
        await db.query(`UPDATE source_document SET ${mutation} WHERE id=$1`, [target.id]);
        const id = label === 'document ID' ? 'f'.repeat(64) : target.id;
        const row = (await db.query(selectedSql, [id])).rows[0];
        assert.equal(row.reviewed_filename, null, label);
        assert.equal(row.filename, label === 'original filename' ? 'unrelated.pdf' : target.raw_entry, label);
        assert.equal(row.title, label === 'title' ? 'DANE - unrelated.pdf' : `DANE - ${target.raw_entry}`, label);
        assert.equal(sha(row.content), sha(originalBytes.get(target.id)), label);
      } finally {
        await db.query('ROLLBACK TO SAVEPOINT wrong_source');
        await db.query('RELEASE SAVEPOINT wrong_source');
      }
    }
    await db.query('ROLLBACK');
    assert.equal((await db.query('SELECT count(*)::int AS n FROM source_document')).rows[0].n, 5);
  } finally { await db.end(); }
});

test('PDF content header advertises the reviewed NFC filename while the body stays byte-identical', async () => {
  const item = oracle.documents.find(row => row.display_filename.startsWith('Cúcuta'));
  const content = Buffer.from('%PDF-1.7\nunchanged archived bytes\n');
  let sourceReads = 0;
  function routeFor(reviewedFilename) {
    const exported = {};
    const file = path.join(__dirname, '../src/app/api/evidence/[id]/content/route.ts');
    const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    new Function('exports', 'require', js)(exported, name => {
      if (name === 'next/server') return { NextResponse: { json: (body, options) => ({ body, status: options.status }) } };
      if (name === '@/lib/server/db') return { database: () => ({ query: async sql => {
        if (sql.includes('reviewed_filename')) return { rows: [{ id: item.id, media_type: 'application/pdf', reviewed_filename: reviewedFilename, bytes: content.length }] };
        if (sql.includes('SELECT content')) { sourceReads++; return { rows: [{ content }] }; }
        throw Error('unexpected source read');
      } }) };
      if (name === '@/lib/server/location') return { spatialContent: () => { throw Error('unexpected spatial source'); } };
      if (name === '@/lib/server/source-storage') return { sourceBlob: async () => null };
      if (name === '@/lib/server/source-document-scope') return { sourceDocumentInApp: id => id === item.id };
      if (name === '@/lib/server/source-document-subjects') return subjects;
      throw Error(`Unexpected content route dependency ${name}`);
    });
    return exported;
  }
  const params = { params: Promise.resolve({ id: item.id }) };
  const req = { headers: new Headers() };
  const corrected = await routeFor(item.display_filename).GET(req, params);
  assert.equal(corrected.status, 200);
  assert.equal(corrected.headers.get('content-type'), 'application/pdf');
  const header = corrected.headers.get('content-disposition');
  assert.match(header, /^inline; filename="agroamigo-/);
  assert.equal(decodeURIComponent(header.split("filename*=UTF-8''")[1]), item.display_filename);
  assert.equal(sha(Buffer.from(await corrected.arrayBuffer())), sha(content));
  const unmatched = await routeFor(null).GET(req, params);
  assert.doesNotMatch(unmatched.headers.get('content-disposition'), /filename\*/);
  assert.equal(sha(Buffer.from(await unmatched.arrayBuffer())), sha(content));
  assert.equal(sourceReads, 2);
});
