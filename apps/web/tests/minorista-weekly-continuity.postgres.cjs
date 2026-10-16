/* Native controls through actual guarded SQL in isolated TEMP PostgreSQL.
 * Minimal table bytes are synthetic SQL fixtures; original hashes were
 * independently verified during source review, not by these table fixtures. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number); types.setTypeParser(1082, value => value);
const oracle = require('./fixtures/minorista-weekly-source-oracle.json');
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const enabled = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL' }, fn);
const root = path.join(__dirname, '../src/lib/server');
function load(file, mocks = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, file+'.ts'),'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { module, exports: module.exports, Error, URLSearchParams,
    require: key => Object.hasOwn(mocks,key) ? mocks[key] : require(key) });
  return module.exports;
}
let db;
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of ['source_document','official_price_quote','official_source_review','ingestion_asset','official_catalog_current'])
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query('CREATE INDEX minorista_quote_date ON official_price_quote(quote_key,observed_on DESC)');
  for (const entry of oracle.anchors) await seed(entry.published);
  const current = oracle.anchors[3].published;
  await db.query(`INSERT INTO official_catalog_current(quote_key,payload,dirty,version)
    VALUES($1,$2,false,'official-catalog-v1')`, [current.quote_key,{...current,previous_price:1400}]);
});
afterEach(async () => { if(db) await db.end(); db=undefined; });

async function seed(r, version = 'native-source-reviewed-v23', parsed='2026-10-02T11:00:00Z') {
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,$4,'original',$5,decode('00','hex'),'2026-10-02T10:00:00Z') ON CONFLICT DO NOTHING`,
    [r.document_id, r.product_name, r.source_url, r.source_page ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', r.observed_on]);
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,
    product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,
    period_start,price,min_price,max_price,source_page,details,parsed_at)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)`,
    [r.document_id,r.source_locator,version,r.quote_key,r.product_id,r.product_name,r.category,
      r.publisher,r.series,r.basis,r.currency,r.unit,r.market,r.observed_on,r.period_start,
      r.price,r.min_price,r.max_price,r.source_page,r.details,parsed]);
}

function service() {
  const events=[], shared={};
  const query=async (sql,args) => { events.push({sql,args}); return db.query(sql,args); };
  const cache=load('snapshot-cache',{'server-only':{}});
  const route=load('official-references',{
    'server-only':{},'./db':{database:()=>({query,connect:async()=>({query,release(){}})})},
    './snapshot-cache':cache,'./summary-references':{summaryReference:async()=>null},
    './official-market-regions':{officialMarketRegions:async rows=>rows},
    '../label-normalization':{normalizeOfficialLabels:r=>r,normalizeLabel:v=>v},
    '../category-hierarchy':require('./helpers/category-hierarchy.cjs')(),
    './acelga-weekly-continuity':load('acelga-weekly-continuity'),
    './weekly-corabastos-continuity':load('weekly-corabastos-continuity'),
    './minorista-weekly-continuity':load('minorista-weekly-continuity'),
    './aguacate-bucaramanga-weekly-continuity':load('aguacate-bucaramanga-weekly-continuity'),
  });
  return {route,events};
}
const request=(app,key=oracle.canonical_key)=>app.route.officialReferences(new URLSearchParams('id='+key));

check('native Jan2017 PDF and 2019 XLS/PDF winners join with both bookmarks and no raw changes',async()=>{
  const before=(await db.query('SELECT row_to_json(q) FROM official_price_quote q ORDER BY document_id,source_locator')).rows;
  const app=service();
  const old=await request(app,oracle.legacy_key), current=await request(app);
  assert.deepEqual(Array.from(current.history,r=>r.price),[1063,1400,3775]);
  assert.equal(old.history[0].document_id,oracle.anchors[0].native.document_id);
  assert.equal(current.history[1].document_id,oracle.anchors[2].native.document_id);
  assert.equal(current.history[1].details.alternate_originals[0].document_id,oracle.anchors[1].native.document_id);
  assert.equal(app.events.filter(e=>e.sql.includes('WITH candidates')).length,2);
  assert.deepEqual((await db.query('SELECT row_to_json(q) FROM official_price_quote q ORDER BY document_id,source_locator')).rows,before);
});

check('new eligible current publication is fetched while future observations stay out',async()=>{
  const r=oracle.anchors[3].published;
  await seed({...r,document_id:'a'.repeat(64),observed_on:'2026-10-03',price:3800});
  await seed({...r,document_id:'b'.repeat(64),observed_on:'2099-01-01',price:3900});
  const result=await request(service());
  assert.equal(result.reference.price,3800);
  assert.equal(result.reference.observed_on,'2026-10-03');
  assert.ok(result.history.every(r=>r.observed_on<'2099-01-01'));
});

check('reviewed and superseded source locators remain raw and are excluded from the bridged history',async()=>{
  const r=oracle.anchors[0].published;
  await seed({...r,quote_key:'c'.repeat(64),market:'Different exact publication'},'identity-correction-v24','2026-10-03T11:00:00Z');
  const x=oracle.anchors[3].published;
  await db.query(`INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason,created_at)
    VALUES($1,$2,'source-review-v24','{}','Source-backed review','2026-10-03T12:00:00Z')`,[x.document_id,x.source_locator]);
  const result=await request(service());
  assert.deepEqual(Array.from(result.history,r=>r.observed_on),['2019-02-15']);
  assert.equal((await db.query('SELECT count(*)::int n FROM official_price_quote')).rows[0].n,5);
  assert.equal(result.history[0].details.alternate_originals[0].source_page,29);
});

check('a conflicting publication isolates the bridge; current standalone original remains reachable',async()=>{
  const old=oracle.anchors[1].published;
  await seed({...old,price:1401},'corrected-native-v24','2026-10-03T11:00:00Z');
  const app=service();
  const a=await request(app,oracle.legacy_key), b=await request(app);
  assert.ok(a.history.every(r=>r.quote_key===oracle.legacy_key));
  assert.ok(b.history.every(r=>r.quote_key===oracle.canonical_key));
  assert.equal(a.reference.price,1401); assert.equal(b.reference.price,3775);
  assert.match(b.reference.details.history_continuity_note,/por separado/);
});
