/* Verified supply source selection; aliases and guessed PDF pages are insufficient. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client } = require('pg');
const moduleContext = { exports: {}, require: name => {
  if (name === 'server-only') return {};
  throw new Error(`Unexpected import ${name}`);
}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/daily-quotes.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, moduleContext);
const sql = moduleContext.exports.DAILY_SUPPLY_SOURCE_SQL;
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='5s'");
    await db.query(`CREATE TEMP TABLE source_document(id text PRIMARY KEY,kind text,
      media_type text,page_count int); CREATE TEMP TABLE document_alias(alias text PRIMARY KEY,document_id text);
      CREATE TEMP TABLE input_reference_row(document_id text,kind text,observed_on date,details jsonb)`);
    await fn(db);
  } finally { await db.end(); }
});
const add = async (db,id,day,type='application/pdf',pages=6,suffix='bulletin') => {
  await db.query("INSERT INTO source_document VALUES($1,'original',$2,$3)",[id,type,pages]);
  await db.query('INSERT INTO document_alias VALUES($1,$2)',[`daily-${day}-${suffix}`,id]);
};
const cell = async (db,id,day,details,kind='supply-daily-summary') => {
  await db.query('INSERT INTO input_reference_row VALUES($1,$2,$3,$4)',[id,kind,day,details]);
};
check('a two-page legacy price PDF has no invented supply page even when its alias exists',async db => {
  await add(db,'legacy','2012-06-27','application/pdf',2);
  assert.deepEqual((await db.query(sql,['2012-06-27'])).rows,[]);
  await cell(db,'legacy','2012-06-26',{source_page:4});
  assert.deepEqual((await db.query(sql,['2012-06-27'])).rows,[]);
});
check('modern verified supply opens its physical page with the actual covered dates',async db => {
  await add(db,'modern','2026-09-04');
  await cell(db,'modern','2026-08-27',{source_page:4,quantity_tonnes:14943});
  await cell(db,'modern','2026-09-03',{source_page:5,quantity_tonnes:23651});
  assert.deepEqual((await db.query(sql,['2026-09-04'])).rows,[{
    document_id:'modern',first_day:'2026-08-27',last_day:'2026-09-03',source_page:4,sheet:null,
  }]);
  assert.deepEqual((await db.query(sql,['2026-09-05'])).rows,[]);
});
check('unverified kinds, extracts, missing and malformed pages do not create a supply claim',async db => {
  await add(db,'invalid','2026-09-04');
  for(const source_page of [null,'n.d.','',0,-1,7]) await cell(db,'invalid','2026-09-03',{source_page});
  await cell(db,'invalid','2026-09-03',{source_page:4},'price-reference');
  assert.deepEqual((await db.query(sql,['2026-09-04'])).rows,[]);
  await cell(db,'invalid','2026-09-03',{source_page:4});
  await db.query("UPDATE source_document SET kind='extract'");
  assert.deepEqual((await db.query(sql,['2026-09-04'])).rows,[]);
});
check('a verified daily workbook opens its named sheet and preserves the PDF as preferred independent source',async db => {
  await add(db,'book','2026-09-04','application/vnd.ms-excel',null,'workbook');
  await cell(db,'book','2026-09-03',{sheet:'Abastecimiento',quantity_tonnes:23651});
  assert.deepEqual((await db.query(sql,['2026-09-04'])).rows,[{
    document_id:'book',first_day:'2026-09-03',last_day:'2026-09-03',source_page:null,sheet:'Abastecimiento',
  }]);
  await add(db,'pdf','2026-09-04');
  await cell(db,'pdf','2026-09-03',{source_page:4});
  assert.equal((await db.query(sql,['2026-09-04'])).rows[0].document_id,'pdf');
});
check('missing workbook sheet, wrong source date and future aliases stay unavailable',async db => {
  await add(db,'book','2026-09-04','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',null,'workbook');
  await cell(db,'book','2026-09-03',{sheet:''});
  assert.deepEqual((await db.query(sql,['2026-09-04'])).rows,[]);
  await cell(db,'book','2026-09-03',{sheet:'Abastecimiento'});
  assert.deepEqual((await db.query(sql,['2012-06-27'])).rows,[]);
  await add(db,'future','2099-01-01');
  await cell(db,'future','2098-12-31',{source_page:4});
  assert.deepEqual((await db.query(sql,['2099-01-01'])).rows,[]);
});
