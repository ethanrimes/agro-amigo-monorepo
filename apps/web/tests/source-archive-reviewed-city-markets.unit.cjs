/* Source-backed printed-market search for exact retained city PDFs. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');

const web = path.resolve(__dirname, '..');
const registry = require('../../../pipelines/ingestion/reviewed_city_dates.json');
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
  '../../../../../pipelines/ingestion/reviewed_city_dates.json': { default: registry },
});
const search = load(path.join(web, 'src/lib/server/source-archive-search.ts'), {
  './sql-search-fold': fold, './source-document-subjects': subjects,
  './reviewed-city-source-markets': cityMarkets,
  './source-document-scope': require('./helpers/load-source-scope.cjs')(),
});
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const archive = registry.archives.find((item) => item.archive_id.startsWith('2ca39'));
const members = archive.members;

test('the bounded web projection is derived from the shared exact-source review registry', () => {
  const entries = registry.archives.flatMap((item) => item.members);
  assert.equal(registry.format, 1);
  assert.equal(entries.length, 41);
  assert.equal(new Set(entries.map((item) => item.document_id)).size, entries.length);
  assert.equal(members.length, 13);
  assert.equal(cityMarkets.REVIEWED_CITY_MARKET_VALUES_SQL.split('\n').length, entries.length);
  assert.match(cityMarkets.REVIEWED_CITY_MARKET_JOIN_SQL, /d\.media_type='application\/pdf'/);
  assert.match(cityMarkets.REVIEWED_CITY_MARKET_JOIN_SQL, /archive_entry/);
  assert.match(cityMarkets.REVIEWED_CITY_MARKET_JOIN_SQL, /parents/);
  assert.deepEqual(search.archiveSearchTerms('Tunja, Complejo de Servicios del Sur 10-2-2022'),
    ['%Tunja,%', '%Complejo%', '%Servicios%', '%Sur%', '%10-2-2022%']);
  assert.deepEqual(search.archiveSearchTerms('Medellín, Central Mayorista de Antioquia 10-2-2022'),
    ['%Medellin,%', '%Central%', '%Mayorista%', '%Antioquia%', '%10-2-2022%']);
});

test('private PostgreSQL binds every reviewed printed market to its own original, not a similar or changed source',
  { skip: !enabled && 'Requires isolated AGRO_CATALOG_SQL_SOCKET' }, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='10s'");
    await db.query(`CREATE TEMP TABLE source_document (
      id text PRIMARY KEY,title text,publisher text,reference_period text,kind text,
      media_type text,metadata jsonb,source_url text,retrieved_at timestamptz);
      CREATE TEMP VIEW published_regional_price AS
        SELECT NULL::text AS document_id,NULL::date AS observed_on WHERE false`);
    for (const member of members) {
      const filename = member.entry_name.split('/').at(-1);
      await db.query(`INSERT INTO source_document VALUES($1,$2,'DANE',
        'Serie histórica completa','original','application/pdf',$3::jsonb,$4,'2026-10-02T09:30:00Z')`,
      [member.document_id, `DANE - ${filename}`, JSON.stringify({
        ingestion_kind: 'city-pdf', original_filename: filename,
        archive_entry: member.entry_name, parents: [archive.archive_id],
      }), archive.url]);
    }
    const find = async (query) => {
      const terms = search.archiveSearchTerms(query);
      assert(terms, query);
      return (await db.query(search.archiveSearchSql(terms), terms)).rows;
    };
    // All 13 exact source IDs and their preserved titles remain reachable by
    // both reviewed market names and literal filename forms.
    for (const member of members) {
      const market = member.market_name;
      const printed = await find(`${market} 10-2-2022`);
      assert.deepEqual(printed.map((row) => row.id), [member.document_id], market);
      assert.equal(printed[0].verified_market, market);
      assert.equal(printed[0].title, `DANE - ${member.entry_name}`);
      assert.equal(printed[0].filename, member.entry_name);
      const stem = member.entry_name.replace(/[ -]*10-2-2022\.pdf$/, '');
      const filename = await find(`${stem} 10-2-2022`);
      assert(filename.some((row) => row.id === member.document_id), member.entry_name);
    }
    for (const query of [
      'Neiva Surabastos 10-2-2022', 'NEIVA SURABASTOS 10-2-2022',
      'Manizales Galerías 10-2-2022', 'MANIZALES GALERIAS 10-2-2022',
      'Medellín Central Mayorista 10-2-2022', 'MEDELLI\u0301N CENTRAL MAYORISTA 10-2-2022',
    ]) assert.equal((await find(query)).length, 1, query);
    const pereiraLa41 = members.find((row) => row.market_name === 'Pereira, La 41');
    const pereiraMercasa = members.find((row) => row.market_name === 'Pereira, Mercasa');
    assert.deepEqual((await find('Pereira La 41 10-2-2022')).map((row) => row.id), [pereiraLa41.document_id]);
    assert.deepEqual((await find('Pereira Mercasa 10-2-2022')).map((row) => row.id), [pereiraMercasa.document_id]);
    const neiva = members.find((row) => row.market_name === 'Neiva, Surabastos');
    const neighbor = '9'.repeat(64);
    await db.query(`INSERT INTO source_document VALUES($1,'DANE - Neiva, Surabastos 15-2-2022.pdf',
      'DANE','Serie histórica completa','original','application/pdf',$2::jsonb,$3,now())`,
    [neighbor, JSON.stringify({ ingestion_kind:'city-pdf',original_filename:'Neiva, Surabastos 15-2-2022.pdf',
      archive_entry:'Neiva, Surabastos 15-2-2022.pdf',parents:[archive.archive_id] }), archive.url]);
    assert.deepEqual((await find('Neiva Surabastos 10-2-2022')).map((row) => row.id), [neiva.document_id]);
    assert.deepEqual((await find('Neiva Surabastos 15-2-2022')).map((row) => row.id), [neighbor]);
    assert.deepEqual(await find('Neiva Surabastos 11-2-2022'), []);
    const original = (await db.query('SELECT * FROM source_document WHERE id=$1', [neiva.document_id])).rows[0];
    for (const changed of [
      { id: neighbor }, { publisher:'Other' }, { kind:'extract' },
      { media_type:'application/zip' }, { source_url:'https://www.dane.gov.co/files/other.zip' },
      { metadata:{ ...original.metadata, ingestion_kind:'weekly-pdf' } },
      { metadata:{ ...original.metadata, original_filename:'Neiva, Surabastos 10-2-2022.pdf' } },
      { metadata:{ ...original.metadata, archive_entry:'Neiva, Surabastos 10-2-2022.pdf' } },
      { metadata:{ ...original.metadata, parents:['0'.repeat(64)] } },
    ]) {
      if (changed.id) {
        // A matching filename and provenance on an unreviewed content hash
        // must never inherit the reviewed alias.
        await db.query('UPDATE source_document SET title=$2,metadata=$3::jsonb WHERE id=$1',
          [neighbor, original.title, JSON.stringify(original.metadata)]);
        assert.deepEqual((await find('Neiva Surabastos 10-2-2022')).map((row) => row.id),
          [neiva.document_id]);
        await db.query('UPDATE source_document SET title=$2,metadata=$3::jsonb WHERE id=$1',
          [neighbor, 'DANE - Neiva, Surabastos 15-2-2022.pdf',
            JSON.stringify({ ingestion_kind:'city-pdf',original_filename:'Neiva, Surabastos 15-2-2022.pdf',
              archive_entry:'Neiva, Surabastos 15-2-2022.pdf',parents:[archive.archive_id] })]);
        continue;
      }
      const [field, value] = Object.entries(changed)[0];
      await db.query(`UPDATE source_document SET ${field}=$2${field === 'metadata' ? '::jsonb' : ''} WHERE id=$1`,
        [neiva.document_id, field === 'metadata' ? JSON.stringify(value) : value]);
      const changedRows = await find('Neiva Surabastos 10-2-2022');
      assert(changedRows.every((row) => row.verified_market === null), field);
      // A changed raw filename may independently contain the queried name;
      // that still must not masquerade as a verified printed-market alias.
      if (field !== 'metadata' || value.original_filename === original.metadata.original_filename)
        assert.deepEqual(changedRows.map((row) => row.id), [], field);
      await db.query(`UPDATE source_document SET ${field}=$2${field === 'metadata' ? '::jsonb' : ''} WHERE id=$1`,
        [neiva.document_id, field === 'metadata' ? JSON.stringify(original.metadata) : original[field]]);
    }
    assert.deepEqual((await find('Neiva Suarbastos 10-2-2022')).map((row) => row.id), [neiva.document_id]);
  } finally { await db.end(); }
});
