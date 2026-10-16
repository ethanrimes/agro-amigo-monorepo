const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const { Client } = require('pg');
const api = {};
const subjects = {};
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/source-document-subjects.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText)(subjects);
new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/source-library.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText)(api, name => {
  if (name === './source-document-scope') return require('./helpers/load-source-scope.cjs')();
  assert.equal(name, './source-document-subjects');
  return subjects;
});
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
test('public SIPRA originals are reachable without EVA crops, with one municipal entry per original', {
  skip: !socket?.startsWith('/tmp/agro-unified-catalog-pg-') && 'Requires isolated PostgreSQL runner',
}, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document(id text,title text,publisher text,
      reference_period text,kind text,media_type text,retrieved_at timestamptz,
      source_url text,metadata jsonb NOT NULL DEFAULT '{}'::jsonb);
      CREATE TEMP TABLE document_alias(alias text,document_id text);
      CREATE TEMP TABLE crop_suitability(document_id text);
      CREATE TEMP TABLE ingestion_asset(document_id text,status text,kind text,observed_on date)`);
    await db.query(`INSERT INTO source_document(id,title,publisher,reference_period,kind,media_type,retrieved_at) VALUES
      ('bulbo','Cebolla de bulbo primer semestre','UPRA · SIPRA','2022','extract','application/json',now()),
      ('aliased','Café aptitud','UPRA · SIPRA','2022','extract','application/json',now()),
      ('private','Location capture','Private','2026','extract','application/json',now()),
      ('unlinked','Unverified snapshot','UPRA · SIPRA','2022','extract','application/json',now()),
      ('daily','DANE original','DANE','2026-09-04','original','application/vnd.ms-excel',now());
      INSERT INTO crop_suitability VALUES ('bulbo'),('bulbo'),('aliased'),('private');
      INSERT INTO document_alias VALUES ('coffee-suitability','aliased'),('daily-2026-09-04-workbook','daily');
      INSERT INTO ingestion_asset VALUES ('daily','review','daily','2026-09-04')`);
    const rows = (await db.query(api.SOURCE_LIBRARY_SQL)).rows;
    assert.deepEqual(rows.map(row => row.id).sort(), ['aliased', 'bulbo']);
    assert.ok(rows.every(row => row.municipality_filter === true));
    assert.equal(rows.filter(row => row.id === 'aliased').length, 1);
    assert.equal(rows.find(row => row.id === 'bulbo').title, 'Cebolla de bulbo primer semestre');
    const original = '6d7f0f181521b8df528b748d2bc10ecac2a605a8987de4a9b152eb8ff71bb637';
    await db.query(`INSERT INTO source_document(id,title,publisher,reference_period,kind,media_type,retrieved_at) VALUES($1,'UPRA - 11 BolCosGrana 20241015.pdf',
      'UPRA','2024','original','application/pdf',now());`, [original]);
    await db.query('INSERT INTO document_alias VALUES($1,$2)', ['reference-cost-11-bolcosgrana-20241015', original]);
    const current = (await db.query(api.SOURCE_LIBRARY_SQL)).rows;
    const granadilla = current.find(row => row.id === original);
    assert.equal(granadilla.subject, 'Granadilla · costos de producción · 2024');
    assert.equal(granadilla.title, 'UPRA - 11 BolCosGrana 20241015.pdf');
    assert.equal(granadilla.municipality_filter, false);
  } finally { await db.end(); }
});
