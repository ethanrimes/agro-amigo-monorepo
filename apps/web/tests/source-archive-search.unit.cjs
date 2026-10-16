const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const output = {};
const subjects = {};
const sqlFold = {};
const cityMarkets = {};
new Function('exports', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/server/sql-search-fold.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText)(sqlFold);
new Function('exports', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/server/source-document-subjects.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText)(subjects);
new Function('exports', 'require', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/server/reviewed-city-source-markets.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText)(cityMarkets, name => {
  if (name === '../../../../../pipelines/ingestion/reviewed_city_dates.json')
    return { default: require('../../../pipelines/ingestion/reviewed_city_dates.json') };
  throw new Error('Unexpected dependency ' + name);
});
new Function('exports', 'require', ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/lib/server/source-archive-search.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText)(output, name => {
  if (name === './source-document-scope') return require('./helpers/load-source-scope.cjs')();
  if (name === './source-document-subjects') return subjects;
  if (name === './sql-search-fold') return sqlFold;
  if (name === './reviewed-city-source-markets') return cityMarkets;
  throw new Error('Unexpected dependency ' + name);
});
const { archiveSearchTerms, archiveSearchSql, ARCHIVE_SEARCH_LIMIT } = output;
const { archiveSearchCursor, archiveNextCursor } = output;
const { Client } = require('pg');
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');

test('archive search accepts filename fragments and dates while escaping SQL wildcards', () => {
  assert.deepEqual(archiveSearchTerms('  abril2024  '), ['%abril2024%']);
  assert.deepEqual(archiveSearchTerms('DANE 2024'), ['%DANE%', '%2024%']);
  assert.deepEqual(archiveSearchTerms('anex_SIPSA%'), ['%anex\\_SIPSA\\%%']);
  assert.equal(archiveSearchTerms('ab'), null);
  assert.equal(archiveSearchTerms('x'.repeat(101)), null);
  assert.equal(archiveSearchTerms('foo\nbar'), null);
  assert.equal(archiveSearchTerms('one two three four five six'), null);
});

test('archive query searches metadata only and has a fixed result cap', () => {
  const sql = archiveSearchSql(['%abril2024%', '%DANE%']);
  assert.match(sql, /COALESCE\('DANE - '.*d\.title.*d\.publisher.*d\.reference_period.*original_filename/s);
  assert.match(sql, /archived_title/);
  assert.match(sql, /archived_filename/);
  assert.match(sql, /ILIKE \$1 ESCAPE/);
  assert.match(sql, /ILIKE \$2 ESCAPE/);
  assert.match(sql, /d\.kind='original'/);
  assert.match(sql, /LIMIT 41/);
  assert.equal(ARCHIVE_SEARCH_LIMIT, 40);
  assert.doesNotMatch(sql, /d\.content/);
});

test('archive cursors retain microseconds and reject malformed dates and identities', () => {
  const row = { id: 'a'.repeat(64), archive_sort_time: '2026-09-07T22:54:00.123456Z' };
  assert.deepEqual(archiveSearchCursor(archiveNextCursor(row)), { at: row.archive_sort_time, id: row.id });
  assert.equal(archiveSearchCursor(null), null);
  assert.equal(archiveSearchCursor('not-json'), null);
  for (const invalid of [
    { ...row, archive_sort_time: '2026-02-31T22:54:00.123456Z' },
    { ...row, archive_sort_time: '2026-09-07T24:00:00.123456Z' },
    { ...row, id: "' OR TRUE --" },
  ]) assert.equal(archiveSearchCursor(archiveNextCursor(invalid)), null);
});

test('all reused city filenames are reachable with stable paged search and exact copy lookup', {
  skip: !enabled && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text,title text,publisher text,reference_period text,kind text,media_type text,
      metadata jsonb,source_url text,retrieved_at timestamptz)`);
    const ids = Array.from({ length: 93 }, (_, i) => i.toString(16).padStart(64, '0'));
    for (const [index, id] of ids.entries()) {
      // Both exact timestamp ties and copies a microsecond apart are important.
      const timestamp = index < 60 ? '2026-09-07T22:54:00.123456Z' : '2026-09-07T22:54:00.123455Z';
      await db.query(`INSERT INTO source_document VALUES($1,'DANE - Medelli\u0301n, Plaza Minorista .pdf',
        'DANE','Serie histórica completa','original','application/pdf','{}',
        'https://www.dane.gov.co/files/report.zip',$2)`, [id, timestamp]);
    }
    let cursor = null;
    const found = [];
    const sizes = [];
    do {
      const terms = archiveSearchTerms('MEDELLIN plaza MINORISTA');
      const rows = (await db.query(archiveSearchSql(terms, Boolean(cursor)),
        cursor ? [...terms, cursor.at, cursor.id] : terms)).rows;
      const visible = rows.slice(0, ARCHIVE_SEARCH_LIMIT);
      found.push(...visible.map(row => row.id));
      sizes.push(visible.length);
      cursor = rows.length > ARCHIVE_SEARCH_LIMIT ? archiveSearchCursor(archiveNextCursor(visible.at(-1))) : null;
    } while (cursor);
    assert.deepEqual(found, ids);
    assert.deepEqual(sizes, [40, 40, 13]);
    assert.equal(new Set(found).size, 93);
    const terms = archiveSearchTerms(ids[90].toUpperCase());
    assert.deepEqual((await db.query(archiveSearchSql(terms), terms)).rows.map(row => row.id), [ids[90]]);
  } finally { await db.end(); }
});

test('archive title search accepts Spanish conjunctions, accents and single-character file terms', () => {
  assert.deepEqual(archiveSearchTerms('boletín diario y abastecimiento 2026-09-04'),
    ['%boletin%', '%diario%', '%abastecimiento%', '%2026-09-04%']);
  assert.deepEqual(archiveSearchTerms('CAFÉ e insumos'), ['%CAFE%', '%insumos%']);
  assert.deepEqual(archiveSearchTerms('C 2026'), ['%C%', '%2026%']);
  assert.equal(archiveSearchTerms('y e o'), null);
});

test('archive SQL strips the same Unicode mark classes as the shared fold', {
  skip: !enabled && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text,title text,publisher text,reference_period text,kind text,media_type text,
      metadata jsonb,source_url text,retrieved_at timestamptz)`);
    for (const [id, title] of [
      ['mark-1ab0', 'Ar\u1ab0bol 20%_'],
      ['mark-astral', 'Ar\u{1d185}bol 20%_'],
      ['other', 'Arbol 20xx'],
    ]) await db.query(`INSERT INTO source_document VALUES($1,$2,'UPRA','2026',
      'original','application/pdf','{}','https://upra.gov.co/source.pdf',now())`, [id, title]);
    for (const query of ['arbol 20%_', 'ÁRBOL 20%_', 'ar\u0301bol 20%_']) {
      const terms = archiveSearchTerms(query);
      const rows = (await db.query(archiveSearchSql(terms), terms)).rows;
      assert.deepEqual(rows.map((row) => row.id).sort(), ['mark-1ab0', 'mark-astral']);
      assert.deepEqual(rows.map((row) => row.title).sort(), ['Ar\u1ab0bol 20%_', 'Ar\u{1d185}bol 20%_']);
    }
  } finally { await db.end(); }
});

test('PostgreSQL strips every Unicode mark covered by the fixed JavaScript property set', {
  skip: !enabled && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    let marks = '';
    for (let codePoint = 0; codePoint <= 0x10ffff; codePoint++) {
      const character = String.fromCodePoint(codePoint);
      if (/\p{M}/u.test(character)) marks += character;
    }
    const result = await db.query(`SELECT ${sqlFold.sqlSearchFold('$1')} AS folded`, [marks]);
    assert.equal(result.rows[0].folded, '');
  } finally { await db.end(); }
});

test('archive search exposes public DANE daily price JSON while excluding other JSON originals', {
  skip: !enabled && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text,title text,publisher text,reference_period text,kind text,media_type text,
      metadata jsonb,source_url text,retrieved_at timestamptz)`);
    // ISO terms now also inspect published city rows; this metadata-only
    // fixture has no city publications, so keep its existing title oracle.
    await db.query(`CREATE TEMP VIEW published_regional_price AS
      SELECT NULL::text AS document_id,NULL::date AS observed_on WHERE false`);
    const original = { filename: 'sipsa-2013-01-04-daily-prices.json', kind: 'dane-daily-query',
      publisher: 'DANE', url: 'https://apps.dane.gov.co/pentaho/api/repos/public/SIPSA', media: 'application/json' };
    const cases = [
      ['public-daily', {}],
      ['weather-location', { kind: 'weather', publisher: 'IDEAM' }],
      ['other-dane-json', { kind: 'dane-context' }],
      ['wrong-publisher', { publisher: 'Private' }],
      ['wrong-host', { url: 'https://private.invalid/pentaho/data' }],
      ['other-query-original', { filename: 'sipsa-2013-01-04-location.json' }],
      ['retained-excel', { media: 'application/vnd.ms-excel', filename: 'anex2013.xls', kind: 'daily' }],
    ];
    for (const [id, changes] of cases) {
      const row = { ...original, ...changes };
      await db.query(`INSERT INTO source_document VALUES($1,'2013 original',$2,'2013-01-04',
        'original',$3,$4::jsonb,$5,'2026-09-07T23:42:16Z')`, [id, row.publisher, row.media,
        JSON.stringify({ ingestion_kind: row.kind, original_filename: row.filename }), row.url]);
    }
    const rows = (await db.query(archiveSearchSql(archiveSearchTerms('2013')),
      archiveSearchTerms('2013'))).rows;
    assert.deepEqual(rows.map(row => row.id).sort(), ['public-daily', 'retained-excel']);
    assert.equal(rows[0].retrieved_at.toISOString(), '2026-09-07T23:42:16.000Z');
    await db.query(`INSERT INTO source_document VALUES
      ('daily-bulletin','Boletín diario y abastecimiento 2026-09-04','DANE','2026-09-04',
        'original','application/pdf','{}','https://www.dane.gov.co/files/bol.pdf','2026-09-04'),
      ('different-bulletin','Boletín semanal y abastecimiento 2026-09-04','DANE','2026-09-04',
        'original','application/pdf','{}','https://www.dane.gov.co/files/sem.pdf','2026-09-04')`);
    for (const query of ['boletín diario y abastecimiento 2026-09-04',
      'BOLETIN diario abastecimiento 2026-09-04', 'BOLETI\u0301N DIARIO abastecimiento 2026-09-04']) {
      const terms = archiveSearchTerms(query);
      const selected = (await db.query(archiveSearchSql(terms), terms)).rows;
      assert.deepEqual(selected.map(row => row.id), ['daily-bulletin'], query);
    }
    await db.query(`UPDATE source_document SET title=$1 WHERE id='daily-bulletin'`, ['BOLETI\u0301N diario y abastecimiento 2026-09-04']);
    const decomposedTerms = archiveSearchTerms('boletin DIARIO abastecimiento 2026-09-04');
    assert.deepEqual((await db.query(archiveSearchSql(decomposedTerms), decomposedTerms)).rows.map(row => row.id), ['daily-bulletin']);
  } finally { await db.end(); }
});

test('a verified crop subject finds its abbreviated original without relabeling other files', {
  skip: !enabled && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  const id = '6d7f0f181521b8df528b748d2bc10ecac2a605a8987de4a9b152eb8ff71bb637';
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text,title text,publisher text,reference_period text,kind text,media_type text,
      metadata jsonb,source_url text,retrieved_at timestamptz)`);
    for (const key of [id, 'unverified-similar-filename'])
      await db.query(`INSERT INTO source_document VALUES($1,
        'UPRA - 11 BolCosGrana 20241015.pdf','UPRA','2024','original','application/pdf',
        '{}','https://upra.gov.co/sites/default/files/2025-03/11_BolCosGrana_20241015.pdf',now())`, [key]);
    for (const query of ['Granadilla', 'Granadilla UPRA 2024', 'granadilla costos producción']) {
      const terms = archiveSearchTerms(query);
      const rows = (await db.query(archiveSearchSql(terms), terms)).rows;
      assert.deepEqual(rows.map(row => row.id), [id]);
      assert.equal(rows[0].title, 'UPRA - 11 BolCosGrana 20241015.pdf');
      assert.equal(rows[0].subject, 'Granadilla · costos de producción · 2024');
    }
    const terms = archiveSearchTerms('BolCosGrana');
    assert.equal((await db.query(archiveSearchSql(terms), terms)).rows.length, 2);
  } finally { await db.end(); }
});
