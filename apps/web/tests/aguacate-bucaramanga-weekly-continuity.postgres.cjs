/* Selected historical prices through the actual guarded SQL in isolated TEMP PG.
 * Literal cells and source locators are independently recorded in the oracle. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1700, Number); types.setTypeParser(1082, value => value);
const oracle = require('./fixtures/aguacate-bucaramanga-weekly-source-oracle.json');
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
const mkrow = a => ({
  document_id:a.document_id,source_locator:a.source_locator,source_page:a.source_page,
  source_url:a.source_url,quote_key:a.quote_key,observed_on:a.date,period_start:a.period_start,
  product_id:'aguacate-comun',product_name:a.source_product,
  category:a.date==='2021-11-19'?'Frutas frescas':'frutas frescas',
  publisher:'DANE · SIPSA',series:'dane-weekly',basis:'Precio mayorista semanal',
  currency:'COP',unit:'kg',market:'Bucaramanga, Centroabastos',
  price:a.price,min_price:a.min_price,max_price:a.max_price,
  details:{identity_dimensions:{source_product:a.source_product},
    period_type:'weekly',price_statistic:'published_mean',period_end:a.date},
});
let db;
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host:socket,port:65443,database:'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  for (const table of ['source_document','official_price_quote','official_source_review','ingestion_asset','official_catalog_current'])
    await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query('CREATE INDEX aguacate_quote_date ON official_price_quote(quote_key,observed_on DESC)');
  for (const anchor of oracle.anchors) await seed(mkrow(anchor));
  for (const row of [mkrow(oracle.anchors[0]),mkrow(oracle.anchors[2])])
    await db.query(`INSERT INTO official_catalog_current(quote_key,payload,dirty,version)
      VALUES($1,$2,false,'official-catalog-v1')`,[row.quote_key,{...row,previous_price:null}]);
});
afterEach(async () => { if (db) await db.end(); db=undefined; });
async function seed(r, version='native-reviewed-v1', parsed='2026-10-04T11:00:00Z') {
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,$2,'DANE',$3,$4,'original',$5,decode('00','hex'),'2026-10-04T10:00:00Z') ON CONFLICT DO NOTHING`,
    [r.document_id,r.product_name,r.source_url,r.source_page?'application/pdf':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',r.observed_on]);
  await db.query(`INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,
    product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,
    period_start,price,min_price,max_price,source_page,details,parsed_at)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)`,
    [r.document_id,r.source_locator,version,r.quote_key,r.product_id,r.product_name,r.category,
      r.publisher,r.series,r.basis,r.currency,r.unit,r.market,r.observed_on,r.period_start,
      r.price,r.min_price,r.max_price,r.source_page,r.details,parsed]);
}
function service() {
  const events=[];
  const query=async(sql,args)=>{ events.push({sql,args}); return db.query(sql,args); };
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
const request=(app,key)=>app.route.officialReferences(new URLSearchParams('id='+key));

check('native 2021 XLSX and 2022/2026 PDF selected money merges while raw rows stay byte-equal',async()=>{
  const before=(await db.query('SELECT row_to_json(q) FROM official_price_quote q ORDER BY document_id,source_locator')).rows;
  const app=service();
  const old=await request(app,oracle.legacy_key), current=await request(app,oracle.canonical_key);
  assert.deepEqual(Array.from(current.history,r=>r.price),[5000,5500,8833]);
  assert.equal(old.history[0].document_id,oracle.anchors[0].document_id);
  assert.equal(current.history[1].source_locator,oracle.anchors[1].source_locator);
  assert.equal(app.events.filter(e=>e.sql.includes('WITH candidates')).length,2);
  assert.deepEqual((await db.query('SELECT row_to_json(q) FROM official_price_quote q ORDER BY document_id,source_locator')).rows,before);
});

check('review and newer same-locator parse hide old evidence without deleting it',async()=>{
  const first=mkrow(oracle.anchors[0]);
  await seed({...first,product_name:'Unrelated audited correction',quote_key:'c'.repeat(64)},
    'source-correction-v2','2026-10-04T12:00:00Z');
  await db.query(`INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason,created_at)
    VALUES($1,$2,'source-review-v2','{}','Source-backed review','2026-10-04T12:00:00Z')`,
    [oracle.anchors[1].document_id,oracle.anchors[1].source_locator]);
  const result=await request(service(),oracle.canonical_key);
  assert.deepEqual(Array.from(result.history,r=>r.observed_on),['2026-08-14']);
  assert.equal((await db.query('SELECT count(*)::int n FROM official_price_quote')).rows[0].n,4);
});

check('a future current-key observation is selected; future-dated source stays excluded',async()=>{
  const current=mkrow(oracle.anchors[2]);
  await seed({...current,document_id:'a'.repeat(64),observed_on:'2026-10-03',
    period_start:'2026-09-27',price:8900,details:{...current.details,period_end:'2026-10-03'}});
  await seed({...current,document_id:'b'.repeat(64),observed_on:'2099-01-01',
    period_start:'2098-12-26',price:9000,details:{...current.details,period_end:'2099-01-01'}});
  const result=await request(service(),oracle.canonical_key);
  assert.equal(result.reference.price,8900);
  assert.ok(result.history.every(r=>r.observed_on<'2099-01-01'));
});

check('new conflicting same-date publication fails only the bridge; both bookmarked originals remain reachable',async()=>{
  const old=mkrow(oracle.anchors[0]), current=mkrow(oracle.anchors[2]);
  await seed({...current,document_id:'a'.repeat(64),observed_on:old.observed_on,
    period_start:old.period_start,price:5100,min_price:5000,max_price:5100,
    details:{...current.details,period_end:old.observed_on}});
  const app=service();
  const a=await request(app,oracle.legacy_key),b=await request(app,oracle.canonical_key);
  assert.equal(a.reference.price,5000); assert.equal(b.reference.price,8833);
  assert.ok(a.history.every(r=>r.quote_key===oracle.legacy_key));
  assert.ok(b.history.every(r=>r.quote_key===oracle.canonical_key));
  assert.match(a.reference.details.history_continuity_note,/por separado/);
});
