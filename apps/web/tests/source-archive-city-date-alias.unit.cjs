/* Exact retained city-member filename dates are searchable without publishing prices. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');
const web = path.resolve(__dirname, '..');
function load(file, dependencies = {}) {
  const exports = {};
  new Function('exports', 'require', ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(exports, name => {
    if (!(name in dependencies)) throw Error(`Unexpected dependency ${name}`);
    return dependencies[name];
  });
  return exports;
}
const fold = load(path.join(web, 'src/lib/server/sql-search-fold.ts'));
const subjects = load(path.join(web, 'src/lib/server/source-document-subjects.ts'));
const cityMarkets = load(path.join(web, 'src/lib/server/reviewed-city-source-markets.ts'), {
  '../../../../../pipelines/ingestion/reviewed_city_dates.json':
    { default: require('../../../pipelines/ingestion/reviewed_city_dates.json') },
});
const search = load(path.join(web, 'src/lib/server/source-archive-search.ts'), {
  './sql-search-fold': fold, './source-document-subjects': subjects,
  './reviewed-city-source-markets': cityMarkets,
  './source-document-scope': require('./helpers/load-source-scope.cjs')(),
});
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const id = digit => digit.repeat(64);
const armeniaId = '742a2c32e4963c8fb4074d1249fbdbde86b1006fe354a7c404b919600ce84b83';

test('only valid calendar tokens acquire date search arms; malformed dates remain metadata text', () => {
  for (const query of ['2023-01-05', '05-01-2023', '5-1-2023', '05/01/2023', '5/1/2023', '29/02/2024', '2024-02-29']) {
    const sql = search.archiveSearchSql(search.archiveSearchTerms(query));
    assert.match(sql, /published_day_1 AS MATERIALIZED/);
    assert.match(sql, /original_filename.*~\*/s);
  }
  for (const query of ['0000-01-01', '31-02-2023', '31/02/2023', '29/02/2023', '05/01-2023', '05-01/2023', '2023-02-30', '2023-13-05']) {
    const sql = search.archiveSearchSql(search.archiveSearchTerms(query));
    assert.doesNotMatch(sql, /published_day_1|original_filename.*~\*/s);
  }
});

test('ISO, padded DMY, unpadded DMY and NFD case queries find the same archived city PDF, not a neighboring day',
  { skip: !enabled && 'Requires isolated AGRO_CATALOG_SQL_SOCKET' }, async () => {
  const db = new Client({ host: socket, port: 65443, database:'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text PRIMARY KEY,title text,publisher text,reference_period text,kind text,
      media_type text,metadata jsonb,source_url text,retrieved_at timestamptz);
      CREATE TEMP TABLE city_publication(document_id text,observed_on date,visible boolean);
      CREATE TEMP VIEW published_regional_price AS
        SELECT document_id,observed_on FROM city_publication WHERE visible`);
    const rows = [
      [armeniaId, 'Armenia, Mercar 5-1-2023.pdf', 'city-pdf'],
      [id('b'), 'Armenia, Mercar 15-1-2023.pdf', 'city-pdf'],
      [id('c'), 'Armenia, Mercar 5-1-2023.pdf', 'weekly-pdf'],
      [id('d'), 'sipsa-05-01-2023.zip', 'city-zip'],
      [id('e'), 'Bogotá, Corabastos undated.pdf', 'city-pdf'],
      [id('f'), 'Armenia, Mercar 5-1-2023.pdf', 'city-pdf'],
      [id('1'), 'Armenia, Mercar 05-010-2023.pdf', 'city-pdf'],
      [id('2'), 'Armenia, Mercar 010-01-2023.pdf', 'city-pdf'],
    ];
    for (const [documentId, filename, kind] of rows) {
      await db.query(`INSERT INTO source_document VALUES($1,$2,'DANE',
        'Serie histórica completa','original',$3,$4::jsonb,
        'https://www.dane.gov.co/files/retained-original','2023-01-06T12:00:00Z')`,
      [documentId, `DANE - ${filename}`, kind === 'city-zip' ? 'application/zip' : 'application/pdf',
        JSON.stringify({ ingestion_kind:kind, original_filename:filename })]);
    }
    await db.query(`INSERT INTO city_publication VALUES
      ($1,'2023-01-05',false),($2,'2023-01-05',true)`, [armeniaId,id('e')]);
    for (const query of [
      'Armenia 2023-01-05', 'ARMENIA 05-01-2023', 'Armenia 5-1-2023',
      'ARMENI\u0301A 2023-01-05',
      'ArMeNiA 05/01/2023', 'ARME\u0301NIA 5/1/2023',
    ]) {
      const terms=search.archiveSearchTerms(query);
      const found=(await db.query(search.archiveSearchSql(terms),terms)).rows.map(row=>row.id);
      assert.deepEqual(found,query === 'Armenia 5-1-2023' ? [armeniaId,id('c'),id('f')] : [armeniaId,id('f')],query);
    }
    for (const query of ['Armenia 2023-10-05', 'Armenia 2023-01-10']) {
      const terms=search.archiveSearchTerms(query);
      assert.deepEqual((await db.query(search.archiveSearchSql(terms),terms)).rows, [],
        'Invalid three-digit filename parts must not become calendar aliases');
    }
    const bogota=search.archiveSearchTerms('BOGOTA 2023-01-05');
    assert.deepEqual((await db.query(search.archiveSearchSql(bogota),bogota)).rows.map(row=>row.id),
      [id('e')], 'Authoritatively published date remains searchable without a filename date');
    const next=search.archiveSearchTerms('Armenia 2023-01-15');
    assert.deepEqual((await db.query(search.archiveSearchSql(next),next)).rows.map(row=>row.id),[id('b')]);
    const zip=search.archiveSearchTerms('2023-01-05');
    const ids=(await db.query(search.archiveSearchSql(zip),zip)).rows.map(row=>row.id);
    assert(!ids.includes(id('d')), 'An ambiguous ZIP filename is not remapped into a city PDF date');
    assert(!ids.includes(id('c')), 'Non-city PDFs do not inherit ISO city filename-date aliases');
  } finally { await db.end(); }
});
