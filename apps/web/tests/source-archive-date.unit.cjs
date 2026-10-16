/* Exact source-archive date-search regression on isolated PostgreSQL only. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');

const WEB = path.resolve(__dirname, '..');
function load(file, dependencies = {}) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('exports', 'require', js)(exports, name => {
    if (!(name in dependencies)) throw new Error(`Unexpected dependency: ${name}`);
    return dependencies[name];
  });
  return exports;
}
const fold = load(path.join(WEB, 'src/lib/server/sql-search-fold.ts'));
const subjects = load(path.join(WEB, 'src/lib/server/source-document-subjects.ts'));
const cityMarkets = load(path.join(WEB, 'src/lib/server/reviewed-city-source-markets.ts'), {
  '../../../../../pipelines/ingestion/reviewed_city_dates.json':
    { default: require('../../../pipelines/ingestion/reviewed_city_dates.json') },
});
const dependencies = { './sql-search-fold': fold, './source-document-subjects': subjects,
  './reviewed-city-source-markets': cityMarkets,
  './source-document-scope': require('./helpers/load-source-scope.cjs')() };
const current = load(path.join(WEB, 'src/lib/server/source-archive-search.ts'), dependencies);
// Independent publication lookup arm from the earlier correlated query. Keep
// the same metadata predicate/order, so equality isolates the CTE rewrite.
function correlatedOracleSql(terms, cursor = false) {
  let query = current.archiveSearchSql(terms, cursor);
  if (query.startsWith('WITH published_day_')) query = query.slice(query.indexOf('SELECT d.id'));
  return query.replace(/d\.id IN \(SELECT document_id FROM published_day_(\d+)\)/g,
    (_all, index) => `EXISTS (SELECT 1 FROM published_regional_price p
      WHERE p.document_id=d.id AND p.observed_on=substring($${index}::text FROM 2 FOR 10)::date)`);
}
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const pgTest = (name, body) => test(name,
  { skip: !enabled && 'Requires isolated AGRO_CATALOG_SQL_SOCKET' }, body);
const id = n => n.toString(16).padStart(64, '0');

async function fixture() {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='8s'; SET lock_timeout='2s'");
  await db.query(`CREATE TEMP TABLE source_document (
    id text PRIMARY KEY,title text,publisher text,reference_period text,kind text,
    media_type text,metadata jsonb,source_url text,retrieved_at timestamptz);
    CREATE TEMP TABLE city_publication(document_id text,observed_on date,visible boolean);
    -- This TEMP visibility fixture checks query gating only. SQL059's
    -- actual resolution/requarantine behavior has a separate private PG proof.
    CREATE TEMP VIEW published_regional_price AS
      SELECT document_id,observed_on FROM city_publication WHERE visible`);
  const insert = async (n, title, media, metadata = {}, stamp = '2026-10-05T17:00:00.123456Z') => {
    await db.query(`INSERT INTO source_document VALUES($1,$2,'DANE','Serie histórica completa',
      'original',$3,$4::jsonb,'https://www.dane.gov.co/files/source',$5)`,
    [id(n), title, media, JSON.stringify(metadata), stamp]);
  };
  return { db, insert };
}

test('only real calendar days create the materialized published-day CTE', () => {
  for (const day of ['2024-02-29', '2026-09-07']) {
    const sql = current.archiveSearchSql(current.archiveSearchTerms(day));
    assert.match(sql, /published_day_1 AS MATERIALIZED/);
    assert.match(sql, /substring\(\$1::text FROM 2 FOR 10\)::date/);
  }
  for (const day of ['2024-02-30', '2026-13-01', '0000-01-01']) {
    const sql = current.archiveSearchSql(current.archiveSearchTerms(day));
    assert.doesNotMatch(sql, /published_day_|substring\(\$1::text FROM 2 FOR 10\)::date/,
      `${day} must remain safe metadata text, never a PostgreSQL date cast`);
  }
});

pgTest('published city dates, held and no-quote children, metadata ZIP fallback, mixed-case accent search', async () => {
  const { db, insert } = await fixture();
  try {
    await insert(1, 'Bogotá Corabastos original', 'application/pdf', { ingestion_kind:'city-pdf' });
    await insert(2, 'Bogotá held original', 'application/pdf', { ingestion_kind:'city-pdf' });
    await insert(3, 'Bogotá no-quote original', 'application/pdf', { ingestion_kind:'city-pdf' });
    await insert(4, 'Regionales 2026-09-07', 'application/zip', { ingestion_kind:'city-zip' });
    await insert(5, 'Boletín Bogotá 2026-09-07', 'application/pdf');
    await db.query(`INSERT INTO city_publication VALUES
      ($1,'2026-09-07',true),($2,'2026-09-07',false),($3,'2026-09-08',false)`, [id(1), id(2), id(3)]);
    const cases = [
      ['2026-09-07', [id(1),id(4),id(5)]],
      ['BOGOTA 2026-09-07', [id(1),id(5)]],
      ['bogota', [id(1),id(2),id(3),id(5)]],
      ['BOGOTA CORABASTOS 2026-09-07', [id(1)]],
      ['2024-02-30', []],
    ];
    for (const [query, want] of cases) {
      const terms = current.archiveSearchTerms(query);
      const rows = (await db.query(current.archiveSearchSql(terms), terms)).rows;
      assert.deepEqual(rows.map(row => row.id).sort(), want.slice().sort(), query);
      const oracle = (await db.query(correlatedOracleSql(terms), terms)).rows;
      assert.deepEqual(rows, oracle, `CTE B must preserve correlated A results: ${query}`);
    }
    const yearZero = current.archiveSearchTerms('0000-01-01');
    assert.deepEqual((await db.query(current.archiveSearchSql(yearZero), yearZero)).rows, [],
      'Invalid PostgreSQL year zero must not abort the metadata search');
  } finally { await db.end(); }
});

pgTest('B matches correlated A over 93 tied microsecond copies and every stable cursor page', async () => {
  const { db, insert } = await fixture();
  try {
    for (let n = 100; n < 193; n++) await insert(n, 'Medellín source copy', 'application/pdf',
      { original_filename:'Medellín, Plaza Minorista.pdf' },
      n < 160 ? '2026-09-07T22:54:00.123456Z' : '2026-09-07T22:54:00.123455Z');
    let cursor = null;
    const seen = [], sizes = [];
    do {
      const terms = current.archiveSearchTerms('MEDELLIN');
      const params = cursor ? [...terms, cursor.at, cursor.id] : terms;
      const b = (await db.query(current.archiveSearchSql(terms, Boolean(cursor)), params)).rows;
      const a = (await db.query(correlatedOracleSql(terms, Boolean(cursor)), params)).rows;
      assert.deepEqual(b, a);
      const page = b.slice(0,current.ARCHIVE_SEARCH_LIMIT);
      seen.push(...page.map(row => row.id)); sizes.push(page.length);
      cursor = b.length > current.ARCHIVE_SEARCH_LIMIT
        ? current.archiveSearchCursor(current.archiveNextCursor(page.at(-1))) : null;
    } while (cursor);
    assert.deepEqual(sizes,[40,40,13]);
    assert.deepEqual(seen,Array.from({length:93},(_,n)=>id(n+100)));
    assert.equal(new Set(seen).size,93);
  } finally { await db.end(); }
});

pgTest('date match and historical period query share one repeatable-read snapshot', async () => {
  // Separate sessions with an actual concurrent commit, using a private
  // schema because PostgreSQL TEMP relations cannot cross connections.
  const admin = new Client({ host: socket, port:65443, database:'postgres' });
  const writer = new Client({ host: socket, port:65443, database:'postgres' });
  await admin.connect(); await writer.connect();
  const schema = `qa_archive_date_${process.pid}_${Date.now()}`;
  try {
    await admin.query(`CREATE SCHEMA ${schema}`);
    for (const client of [admin,writer]) await client.query(`SET search_path=${schema},public; SET statement_timeout='8s'`);
    await admin.query(`CREATE TABLE source_document (
      id text PRIMARY KEY,title text,publisher text,reference_period text,kind text,
      media_type text,metadata jsonb,source_url text,retrieved_at timestamptz);
      CREATE TABLE city_publication(document_id text,observed_on date,visible boolean);
      CREATE VIEW published_regional_price AS SELECT document_id,observed_on
        FROM city_publication WHERE visible`);
    await admin.query(`INSERT INTO source_document VALUES($1,'Bogotá Corabastos','DANE',
      'Serie histórica completa','original','application/pdf','{"ingestion_kind":"city-pdf"}',
      'https://www.dane.gov.co/files/original.pdf',now())`,[id(9)]);
    await admin.query('INSERT INTO city_publication VALUES($1,$2,true)',[id(9),'2026-09-07']);
    await admin.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    const terms = current.archiveSearchTerms('2026-09-07');
    assert.deepEqual((await admin.query(current.archiveSearchSql(terms),terms)).rows.map(r=>r.id),[id(9)]);
    await writer.query('INSERT INTO city_publication VALUES($1,$2,true)',[id(9),'2026-09-08']);
    const period = `SELECT min(observed_on)::text AS observed_first,max(observed_on)::text AS observed_last
      FROM published_regional_price WHERE document_id=$1`;
    assert.deepEqual((await admin.query(period,[id(9)])).rows[0],
      {observed_first:'2026-09-07',observed_last:'2026-09-07'});
    await admin.query('COMMIT');
    assert.equal((await admin.query(period,[id(9)])).rows[0].observed_last,'2026-09-08');
  } finally {
    await admin.query('ROLLBACK').catch(()=>{});
    await writer.end();
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`).catch(()=>{});
    await admin.end();
  }
});

function routeFixture({ failStages = [], failAcquire = false, failRelease = false } = {}) {
  const calls = []; let releases = 0;
  const row = { id:id(1),reference_period:'Serie histórica completa',media_type:'application/pdf',
    archive_sort_time:'2026-10-05T00:00:00.123456Z' };
  const client = { async query(sql) {
    const stage = sql.startsWith('BEGIN') ? 'begin' : sql.startsWith('COMMIT') ? 'commit'
      : sql.startsWith('ROLLBACK') ? 'rollback' : sql.includes('FROM source_document d') ? 'search' : 'period';
    calls.push({stage,sql});
    if (failStages.includes(stage)) throw Error(`private ${stage} failure`);
    return { rows: stage === 'search' ? [row] : stage === 'period'
      ? [{document_id:row.id,observed_first:'2026-09-07',observed_last:'2026-09-07'}] : [] };
  }, release() { releases++; if (failRelease) throw Error('private release failure'); } };
  const pool = { async connect() { calls.push({stage:'acquire'});
    if (failAcquire) throw Error('private acquire failure'); return client; } };
  const route = load(path.join(WEB,'src/app/api/source-archive/route.ts'), {
    'next/server':{ NextResponse:{ json:(body,options={})=>({body,status:options.status||200}) } },
    '@/lib/server/db':{ database:()=>pool },
    '@/lib/server/source-archive-search':current,
  });
  return { get:route.GET,calls,released:()=>releases };
}
const request = {nextUrl:new URL('https://local.test/api/source-archive?q=2026-09-07')};
test('route holds one RR read-only snapshot for search and period and releases client', async () => {
  const f=routeFixture(); const result=await f.get(request);
  assert.equal(result.status,200);
  assert.deepEqual(f.calls.map(x=>x.stage),['acquire','begin','search','period','commit']);
  assert.equal(f.calls[1].sql,'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  assert.equal(f.released(),1);
  assert.equal(result.body.rows[0].observed_first,'2026-09-07');
});
for (const stage of ['begin','search','period','commit'])
  test(`route ${stage} failure attempts rollback and releases`, async () => {
    const f=routeFixture({failStages:[stage]}); const result=await f.get(request);
    assert.equal(result.status,503);
    assert.deepEqual(f.calls.map(x=>x.stage).at(-1),'rollback');
    assert.equal(f.released(),1);
  });
test('rollback failure after search error still releases and returns 503', async () => {
  const f=routeFixture({failStages:['search','rollback']});
  const result=await f.get(request);
  assert.equal(result.status,503); assert.equal(f.released(),1);
  assert.deepEqual(f.calls.map(x=>x.stage),['acquire','begin','search','rollback']);
});
test('release failure returns 503 without a duplicate transaction or second release', async () => {
  const f=routeFixture({failRelease:true});
  const result=await f.get(request);
  assert.equal(result.status,503); assert.equal(f.released(),1);
  assert.deepEqual(f.calls.map(x=>x.stage),['acquire','begin','search','period','commit']);
});
test('acquisition failure has no client to release', async () => {
  const unavailable=routeFixture({failAcquire:true});
  assert.equal((await unavailable.get(request)).status,503);
  assert.deepEqual(unavailable.calls.map(x=>x.stage),['acquire']);
  assert.equal(unavailable.released(),0);
});
