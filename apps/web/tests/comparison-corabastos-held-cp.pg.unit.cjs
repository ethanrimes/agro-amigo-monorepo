/* Owned pg_temp only: full source/price parity through actual unresolved conflict and CP views. */
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm'),ts=require('typescript');
const {Client,types}=require('pg');types.setTypeParser(1082,x=>x);
const socket=process.env.AGRO_COMPARISON_SQL_SOCKET;
const enabled=socket?.startsWith('/tmp/agro-comparison-pg-')||socket?.startsWith('/private/tmp/agro-comparison-pg-');
const server=path.join(__dirname,'../src/lib/server');
const candidatePath=path.join(server,'comparison-corabastos-all-history.ts');
const viewPin='b6b773cdb0e1450f926c53d97bcdf4665cb39b3108bf5abb63a6d71b141b0e40';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function loadText(source,mocks){const exports={};const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInNewContext(js,{exports,require:id=>id==='server-only'?{}:id==='node:crypto'?crypto:mocks[id],console,Map,Set,Date});return exports}
function load(file,mocks){return loadText(fs.readFileSync(path.join(server,file),'utf8'),mocks)}
const categoryPath=load('category-path-sql.ts',{});
const alias=load('city-market-alias.ts',{'./category-path-sql':categoryPath}),packages=load('city-package-equivalence.ts',{});
const price=load('price-quotes.ts',{'./db':{database:()=>null,WINDOW:'observed_on<=CURRENT_DATE'},'./city-market-alias':alias,'./city-package-equivalence':packages,'./summary-references':{},'./category-path-sql':categoryPath,'../price-classification':{},'./product-detail-diagnostics':{},'../label-normalization':{},'./market-alias':{}});
const scope=`WHERE ${alias.cityMarketNamesForIdSql('$1')} AND ${alias.cityMarketIdSql()}=$1 AND r.product_id=$2 AND r.observed_on<=CURRENT_DATE`;
const originalSql=`WITH quotes AS (${price.cityPriceQuotes(false,scope)})
 SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
 product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
 market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
 price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
 FROM quotes WHERE true AND observed_on<=CURRENT_DATE
 ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`;
const db=new Client({host:socket,port:Number(process.env.AGRO_COMPARISON_SQL_PORT||65449),database:'postgres',connectionTimeoutMillis:5000});
let calls=[],failMetadata=false,forcedHeldRows=null;
const proxy={async query(sql,args){
 if(sql.startsWith('BEGIN ISOLATION LEVEL'))return db.query('SAVEPOINT helper_snapshot');
 if(sql==='COMMIT')return db.query('RELEASE SAVEPOINT helper_snapshot');
 if(sql==='ROLLBACK')return db.query('ROLLBACK TO SAVEPOINT helper_snapshot');
 calls.push(sql);if(failMetadata&&sql===fast.CORABASTOS_PUBLISHED_VIEW_SQL)throw Error('TEST_METADATA_UNAVAILABLE');
 if(sql===fast?.CORABASTOS_HELD_DOCUMENTS_SQL&&forcedHeldRows)return {rows:forcedHeldRows};
 return db.query(sql,args);
},release(){}};
const mocks={'./db':{database:()=>({connect:async()=>proxy})},'./city-market-alias':alias,'./price-quotes':price,'./category-path-sql':categoryPath};
const source=fs.readFileSync(candidatePath,'utf8');
const fallback=loadText(source,mocks);let fast;
const normalize=x=>Array.isArray(x)?x.map(normalize):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,normalize(x[k])])):x;
const canonical=rows=>rows.map(r=>JSON.stringify(normalize(r)));
const out={scope:'owned local pg_temp only; actual CP-resolution view shape; full 20 fields and selected source',cases:[]};
async function check(label,{document,category,heldCount}={}){
 const authored=(await db.query(originalSql,[alias.CORABASTOS_CITY_MARKET_ID,'p'])).rows;
 const classes=(await db.query('SELECT document_id,source_locator,category_path FROM regional_classification')).rows;
 const classMap=new Map(classes.map(c=>[JSON.stringify([c.document_id,c.source_locator]),c.category_path]));
 const expected=authored.map(r=>({...r,category_path:
  classMap.get(JSON.stringify([r.document_id,r.source_locator]))||r.category_path}));
 assert.equal(expected.length,1,label+': authored count');assert.equal(Object.keys(expected[0]).length,20,label+': authored fields');
 calls=[];const got=await fast.corabastosAllHistoryQuotes();const fastCalls=[...calls];
 assert.deepEqual(canonical(got),canonical(expected),label+': bound full tuple parity');
 assert.equal(fastCalls.filter(s=>s===fast.CORABASTOS_PUBLISHED_VIEW_SQL).length,1,label+': bound view check');
 assert.equal(fastCalls.filter(s=>s===fast.CORABASTOS_HELD_DOCUMENTS_SQL).length,1,label+': one held set');
 assert.equal(fastCalls.filter(s=>s===fast.CORABASTOS_BOUND_TYPED_SQL).length,1,label+': bound typed');
 calls=[];const old=await fallback.corabastosAllHistoryQuotes();const fallbackCalls=[...calls];
 assert.deepEqual(canonical(old),canonical(expected),label+': original-view fallback full tuple');
 assert.equal(fallbackCalls.filter(s=>s===fast.CORABASTOS_HELD_DOCUMENTS_SQL).length,0,label+': fallback no held read');
 assert.equal(fallbackCalls.filter(s=>s===fast.CORABASTOS_TYPED_BATCH_SQL).length,1,label+': fallback original published typed');
 if(document)assert.equal(got[0].document_id,document,label+': selected original');
 if(category)assert.equal(got[0].category,category,label+': category overlay');
 const held=(await db.query(fast.CORABASTOS_HELD_DOCUMENTS_SQL)).rows.map(r=>r.document_id);
 if(heldCount!==undefined)assert.equal(held.length,heldCount,label+': held count');
 out.cases.push({label,source_document:got[0].document_id,source_locator:got[0].source_locator,category:got[0].category,
  held_count:held.length,full_tuple_sha256:sha(canonical(got).join('\n')),bound:true,unknown_view_fallback:true});
}
test('bound held source preserves published full tuple through CP and category changes',
 {skip:!enabled&&'Requires owned local socket'},async()=>{try{
 await db.connect();await db.query(`SET search_path=pg_temp; SET TIME ZONE 'America/Bogota'; SET statement_timeout='8s';
 CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text);
 CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,kind text,media_type text,retrieved_at timestamptz);
 CREATE TEMP TABLE regional_price(document_id text NOT NULL,source_locator text NOT NULL,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round int,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page int,PRIMARY KEY(document_id,source_locator));
 CREATE INDEX regional_quote_latest_full_cover ON regional_price(product_id,market_name,lower(btrim(presentation)),quantity,lower(btrim(source_unit)),unit,observed_on DESC,round DESC) INCLUDE(presentation,source_unit,document_id,source_locator);
 CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text,PRIMARY KEY(document_id,source_locator));
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
 CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
  corrected_min_price numeric,corrected_max_price numeric);
 CREATE TEMP TABLE city_pdf_publication_conflict(id text PRIMARY KEY,document_id text);
 CREATE TEMP TABLE city_pdf_category_resolution(conflict_id text,document_id text,archive_id text,member_checkpoint_step text);
 CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records int);
 CREATE TEMP VIEW verified_city_pdf_category_resolution AS SELECT a.* FROM city_pdf_category_resolution a WHERE EXISTS
  (SELECT 1 FROM ingestion_checkpoint cp WHERE cp.document_id=a.archive_id AND cp.processor_version='city-v8' AND cp.step=a.member_checkpoint_step AND cp.records=198);
 CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS SELECT c.* FROM city_pdf_publication_conflict c WHERE NOT EXISTS
  (SELECT 1 FROM verified_city_pdf_category_resolution a WHERE a.conflict_id=c.id AND a.document_id=c.document_id);
 CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE (NOT EXISTS
  (SELECT 1 FROM unresolved_city_pdf_publication_conflict c WHERE c.document_id=r.document_id OFFSET 0)) IS TRUE;
 CREATE TEMP VIEW verified_regional_category_overlay AS SELECT r.document_id,r.source_locator,array_to_string(c.category_path,' > ') AS corrected_category
  FROM verified_city_pdf_category_resolution a JOIN regional_price r ON r.document_id=a.document_id
  JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator;
 CREATE TEMP VIEW raw_resolved_regional_price AS SELECT r.* FROM published_regional_price r WHERE NOT EXISTS
  (SELECT 1 FROM regional_price_product_correction c WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
 UNION ALL SELECT r.document_id,r.source_locator,r.observed_on,c.corrected_product_id,c.corrected_product_name,r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
  FROM regional_price_product_correction c JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
 CREATE TEMP VIEW resolved_regional_price AS SELECT x.document_id,x.source_locator,x.observed_on,x.product_id,x.product_name,x.market_name,coalesce(o.corrected_category,x.category) AS category,x.presentation,x.quantity,x.source_unit,x.round,x.round_label,x.min_price,x.max_price,x.unit,x.min_unit_price,x.max_unit_price,x.source_page FROM raw_resolved_regional_price x LEFT JOIN verified_regional_category_overlay o ON o.document_id=x.document_id AND o.source_locator=x.source_locator;
 INSERT INTO market VALUES('canonical','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001');
 INSERT INTO source_document VALUES('old','https://www.dane.gov.co/old.pdf','original','application/pdf','2022-01-11'),('held','https://www.dane.gov.co/held.pdf','original','application/pdf','2026-01-11');
 INSERT INTO regional_price VALUES
 ('old','old-row','2022-01-10','p','Product P','Bogotá, D.C., Corabastos','Frutas > Cítricos','Bulto',50,'Kilogramo',1,'Ronda',100,102,'package',100,102,1),
 ('held','held-row','2025-01-10','p','Product P','Bogotá, D.C., Corabastos','Frutas > Cítricos','Bulto',50,'Kilogramo',1,'Ronda',200,202,'package',200,202,1);
 INSERT INTO regional_classification VALUES('held','held-row',ARRAY['Verduras','Raíces']::text[]);`);
 await db.query('BEGIN');await db.query('SAVEPOINT all_controls');
 const view=(await db.query("SELECT pg_get_viewdef('published_regional_price'::regclass,true) AS definition")).rows[0].definition;
 const localHash=sha(view);assert.notEqual(localHash,viewPin);
 fast=loadText(source.replace(viewPin,localHash),mocks);out.local_view_sha256=localHash;
 await check('empty held set',{document:'held',heldCount:0});
 await db.query("INSERT INTO city_pdf_publication_conflict VALUES('conflict-1','held')");
 await check('unresolved hold excludes newer',{document:'old',heldCount:1});
 await db.query("INSERT INTO city_pdf_category_resolution VALUES('conflict-1','held','archive','member')");
 await check('resolution without CP still held',{document:'old',heldCount:1});
 await db.query("INSERT INTO ingestion_checkpoint VALUES('archive','city-v8','member',197)");
 await check('wrong CP count still held',{document:'old',heldCount:1});
 await db.query("UPDATE ingestion_checkpoint SET records=198");
 await check('exact CP resolves and category overlays',{document:'held',category:'Verduras > Raíces',heldCount:0});
 await db.query("UPDATE ingestion_checkpoint SET records=199");
 await check('changed CP reholds source',{document:'old',heldCount:1});
 await db.query("INSERT INTO city_pdf_publication_conflict VALUES('conflict-2','held')");
 await check('multiple conflicts one unresolved still held',{document:'old',heldCount:1});
 // Unknown publication-view shape must fall back to the original published SQL, not use the raw shortcut.
 await db.query("CREATE OR REPLACE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE r.observed_on<'2024-01-01'");
 calls=[];const changed=await fast.corabastosAllHistoryQuotes();
 const changedAuthored=(await db.query(originalSql,[alias.CORABASTOS_CITY_MARKET_ID,'p'])).rows;
 const changedClasses=(await db.query('SELECT document_id,source_locator,category_path FROM regional_classification')).rows;
 const changedClassMap=new Map(changedClasses.map(c=>[JSON.stringify([c.document_id,c.source_locator]),c.category_path]));
 const changedOriginal=changedAuthored.map(r=>({...r,category_path:
  changedClassMap.get(JSON.stringify([r.document_id,r.source_locator]))||r.category_path}));
 assert.deepEqual(canonical(changed),canonical(changedOriginal));
 assert.equal(calls.filter(s=>s===fast.CORABASTOS_HELD_DOCUMENTS_SQL).length,0);
 assert.equal(calls.filter(s=>s===fast.CORABASTOS_TYPED_BATCH_SQL).length,1);
 out.cases.push({label:'changed published-view definition uses original SQL',fallback:true,full_tuple_sha256:sha(canonical(changed).join('\n'))});
 // Restore the bound view and test a bad live held set; it must fail before any raw price query.
 await db.query("CREATE OR REPLACE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict c WHERE c.document_id=r.document_id OFFSET 0)");
 // The equivalent recreated view may format differently. Bind a new test-only copy to its exact definition.
 const restored=(await db.query("SELECT pg_get_viewdef('published_regional_price'::regclass,true) AS definition")).rows[0].definition;
 fast=loadText(source.replace(viewPin,sha(restored)),mocks);
 await db.query("INSERT INTO city_pdf_publication_conflict VALUES('null-conflict',NULL)");
 calls=[];await assert.rejects(fast.corabastosAllHistoryQuotes(),/CORABASTOS_INVALID_HELD_DOCUMENT_SET/);
 assert.equal(calls.filter(s=>s===fast.CORABASTOS_BOUND_TYPED_SQL).length,0);
 out.cases.push({label:'null held ID fails closed before raw quote',fail_closed:true});
 await db.query("DELETE FROM city_pdf_publication_conflict WHERE id='null-conflict'");
 failMetadata=true;calls=[];
 await assert.rejects(fast.corabastosAllHistoryQuotes(),/TEST_METADATA_UNAVAILABLE/);
 failMetadata=false;
 assert.equal(calls.filter(s=>s===fast.CORABASTOS_BOUND_TYPED_SQL).length,0);
 out.cases.push({label:'view metadata failure rolls back before raw quote',fail_closed:true});
 for(const [label,rows] of [
  ['duplicate held IDs rejected',[{document_id:'held'},{document_id:'held'}]],
  ['nonstring held ID rejected',[{document_id:42}]]]){
  forcedHeldRows=rows;calls=[];
  await assert.rejects(fast.corabastosAllHistoryQuotes(),/CORABASTOS_INVALID_HELD_DOCUMENT_SET/);
  assert.equal(calls.filter(s=>s===fast.CORABASTOS_BOUND_TYPED_SQL).length,0);
  out.cases.push({label,fail_closed:true});
 }
 forcedHeldRows=null;
 await db.query('ROLLBACK TO SAVEPOINT all_controls');await db.query('RELEASE SAVEPOINT all_controls');await db.query('ROLLBACK');
 assert.equal(out.cases.length,12);
 }finally{try{await db.end()}catch{}}});
