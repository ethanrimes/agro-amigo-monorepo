/* Actual all-history helper against owned pg_temp fixtures and current authored SQL. */
const { test } = require('node:test');
const fs=require('fs'),path=require('path'),crypto=require('crypto'),assert=require('assert/strict');
const {Client,types}=require('pg');
const vm=require('vm'),ts=require('typescript');
/* Keep source decimal precision during exact full-tuple parity. */
types.setTypeParser(1082,v=>v);
const socket=process.env.AGRO_COMPARISON_SQL_SOCKET;
const enabled=socket?.startsWith('/tmp/agro-comparison-pg-')
  ||socket?.startsWith('/private/tmp/agro-comparison-pg-');
const server=path.join(__dirname,'../src/lib/server');
function load(file,mocks){
 const exports={};
 let source=fs.readFileSync(path.isAbsolute(file)?file:path.join(server,file),'utf8');
 if(mocks.__viewHash)source=source.replace('b6b773cdb0e1450f926c53d97bcdf4665cb39b3108bf5abb63a6d71b141b0e40',mocks.__viewHash);
 const js=ts.transpileModule(source,
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(js,{exports,require:id=>id==='server-only'?{}:id==='node:crypto'?crypto:mocks[id],console,Map,Set,Date});
 return exports;
}
const categoryPath=load('category-path-sql.ts',{});
const alias=load('city-market-alias.ts',{'./category-path-sql':categoryPath});
const marketSql=load('market-sql.ts',{'./city-market-alias':alias});
const packages=load('city-package-equivalence.ts',{});
const price=load('price-quotes.ts',{
 './db':{database:()=>null,WINDOW:'observed_on<=CURRENT_DATE'},
 './city-market-alias':alias,'./city-package-equivalence':packages,
 './summary-references':{},'./category-path-sql':categoryPath,'../price-classification':{},
 './product-detail-diagnostics':{},'../label-normalization':{},'./market-alias':{},
});
const originalScope=`WHERE ${alias.cityMarketNamesForIdSql('$1')}
 AND ${alias.cityMarketIdSql()}=$1 AND r.product_id=$2 AND r.observed_on<=CURRENT_DATE`;
const original={sql:`WITH quotes AS (${price.cityPriceQuotes(false,originalScope)})
 SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
 product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
 market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
 price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
 FROM quotes WHERE true AND observed_on<=CURRENT_DATE
 ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`};
const db=new Client({host:socket,port:Number(process.env.AGRO_COMPARISON_SQL_PORT||65449),
 database:'postgres',connectionTimeoutMillis:5000});
let helperBatchSizes=[],helperSqlCalls=[],helperQueryArgs=[];
const helperClient={
 async query(sql,args){
  if(sql.startsWith('BEGIN ISOLATION LEVEL'))return db.query('SAVEPOINT helper_snapshot');
  if(sql==='COMMIT')return db.query('RELEASE SAVEPOINT helper_snapshot');
  if(sql==='ROLLBACK')return db.query('ROLLBACK TO SAVEPOINT helper_snapshot');
  helperSqlCalls.push(sql);helperQueryArgs.push(args);
  if(sql===candidate.sql||sql===helper?.CORABASTOS_BOUND_TYPED_SQL)helperBatchSizes.push(args[0].length);
  return db.query(sql,args);
 },release(){}
};
let helper=load('comparison-corabastos-all-history.ts',{
 './db':{database:()=>({connect:async()=>helperClient})},
 './city-market-alias':alias,'./price-quotes':price,'./category-path-sql':categoryPath,
});
const fallbackHelper=helper;
const candidate={sql:helper.CORABASTOS_TYPED_BATCH_SQL,
 overlap_sql:helper.CORABASTOS_ALIAS_OVERLAP_DATES_SQL,
 sha256:crypto.createHash('sha256').update(helper.CORABASTOS_TYPED_BATCH_SQL).digest('hex')};
const looseSeed=helper.CORABASTOS_RAW_PRODUCT_SEED_SQL;
const ac={sql:helper.CORABASTOS_INDEXED_EXCEPTION_SQL,
 sha256:crypto.createHash('sha256').update(helper.CORABASTOS_INDEXED_EXCEPTION_SQL).digest('hex')};
const sourceIdsSql=`SELECT DISTINCT coalesce(c.corrected_product_id,r.product_id) id FROM published_regional_price r
 LEFT JOIN regional_price_product_correction c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
 WHERE r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
 AND r.observed_on<=CURRENT_DATE ORDER BY id`;
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const normalize=x=>Array.isArray(x)?x.map(normalize):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,normalize(x[k])])):x;
const canonical=rows=>rows.map(r=>JSON.stringify(normalize(r))).sort();
const result={scope:'separate owned local PostgreSQL, pg_temp-only fixtures; source SQL exact hashes; no production writes',
 candidate_sql_sha256:candidate.sha256,exception_sql_sha256:ac.sha256,original_sql_sha256:sha(original.sql),cases:{}};
let sequence=0;
async function addRow({product='p',name='Product P',market='Bogotá, D.C., Corabastos',doc='old',day='2022-01-10',
 round=1,price=100,presentation='Bulto',quantity=50,sourceUnit='Kilogramo',unit='package',category='Frutas > Cítricos'}={}){
 const locator='row-'+(++sequence);
 await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,
 category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'Ronda',$12::numeric,$12::numeric+2,$13,$12::numeric,$12::numeric+2,1)`,
 [doc,locator,day,product,name,market,category,presentation,quantity,sourceUnit,round,price,unit]);
 return locator;
}
async function verify(label,{expectedIds,expectedLocators,expectedExceptions}={}){
 const scopedIds=(await db.query(sourceIdsSql)).rows.map(r=>r.id);
 const rawIds=(await db.query(looseSeed)).rows.map(r=>r.product_id);
 const directIds=(await db.query("SELECT DISTINCT product_id FROM regional_price WHERE market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') AND observed_on<=CURRENT_DATE ORDER BY product_id")).rows.map(r=>r.product_id);
 assert.deepEqual(rawIds,directIds);
 const overlapDates=(await db.query(candidate.overlap_sql)).rows.map(r=>r.observed_on);
 const ordinary=[];const exceptions=new Set(),hydrationCollisions=new Set();
 for(const rawId of rawIds){
  const parts=(await db.query(candidate.sql,[[rawId],overlapDates])).rows;
  for(const part of parts){ if(part.row_kind===1){exceptions.add(part.exception_product_id);continue;}if(part.row_kind===2){exceptions.add(part.exception_product_id);hydrationCollisions.add(part.exception_product_id);continue;}const {row_kind,exception_product_id,...quote}=part; ordinary.push(quote);}
 }
 for(let i=ordinary.length-1;i>=0;i--)if(exceptions.has(ordinary[i].id))ordinary.splice(i,1);
 assert.ok(ordinary.every(row=>!exceptions.has(row.id)),`${label} ordinary leakage`);
 const originalRows=[],actual=[...ordinary];
 const ordinaryExceptionIds=[...exceptions].filter(id=>!hydrationCollisions.has(id));
 const exceptionRows=ordinaryExceptionIds.length ? (await db.query(ac.sql,['sipsa-bogota-d-c-corabastos',ordinaryExceptionIds])).rows : [];
 actual.push(...exceptionRows);
 for(const id of hydrationCollisions)actual.push(...(await db.query(original.sql,['sipsa-bogota-d-c-corabastos',id])).rows);
 for(const id of scopedIds){const old=(await db.query(original.sql,['sipsa-bogota-d-c-corabastos',id])).rows;
 originalRows.push(...old);}
 assert.deepEqual(canonical(actual),canonical(originalRows),`${label}: full authored tuple parity`);
 const order=(await db.query(`SELECT ord FROM unnest($1::text[],$2::text[],$3::text[],$4::text[],$5::text[],$6::date[],$7::text[]) WITH ORDINALITY AS t(id,presentation,units,unit,series,day,document_id,ord) ORDER BY id,presentation,units,unit,series,day DESC,document_id`,[actual.map(r=>r.id),actual.map(r=>r.presentation),actual.map(r=>r.units),actual.map(r=>r.unit),actual.map(r=>r.series),actual.map(r=>r.date),actual.map(r=>r.document_id)])).rows;
 const ordered=order.map(r=>actual[Number(r.ord)-1]);
 assert.deepEqual(ordered.map(r=>JSON.stringify(normalize(r))),originalRows.map(r=>JSON.stringify(normalize(r))),`${label}: ordered authored tuple parity`);
 if(expectedIds)assert.deepEqual([...new Set(actual.map(r=>r.id))].sort(),expectedIds.slice().sort(),`${label}: ids`);
 if(expectedLocators)assert.deepEqual(actual.map(r=>r.source_locator).sort(),expectedLocators.slice().sort(),`${label}: winners`);
 if(expectedExceptions)assert.deepEqual([...exceptions].sort(),expectedExceptions.slice().sort(),`${label}: guarded ids`);
 const classifications=(await db.query('SELECT document_id,source_locator,category_path FROM regional_classification')).rows;
 const classMap=new Map(classifications.map(c=>[JSON.stringify([c.document_id,c.source_locator]),c.category_path]));
 const overlays=(await db.query('SELECT document_id,source_locator,corrected_category FROM verified_regional_category_overlay')).rows;
 const overlaysByKey=new Map();
 for(const overlay of overlays){const key=JSON.stringify([overlay.document_id,overlay.source_locator]);const entries=overlaysByKey.get(key)||[];entries.push(overlay.corrected_category.split(' > '));overlaysByKey.set(key,entries);}
 const classified=rows=>rows.map(row=>{const key=JSON.stringify([row.document_id,row.source_locator]);const candidates=overlaysByKey.get(key)||[];return {...row,category_path:candidates.length===1?candidates[0]:candidates.length>1?row.category_path:classMap.get(key)||row.category_path};});
 assert.deepEqual(classified(ordered).map(r=>JSON.stringify(normalize(r))),classified(originalRows).map(r=>JSON.stringify(normalize(r))),`${label}: post-classification ordered parity`);
 helperBatchSizes=[];helperSqlCalls=[];helperQueryArgs=[];
 const actualHelper=await helper.corabastosAllHistoryQuotes();
 const fastCalls=[...helperSqlCalls];
 const scopedExceptionCalls=fastCalls.map((sql,index)=>({sql,args:helperQueryArgs[index]}))
  .filter(call=>call.sql===helper.CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL);
 assert.equal(scopedExceptionCalls.length,ordinaryExceptionIds.length?1:0,`${label}: one scoped exception`);
 if(scopedExceptionCalls.length){
  assert.deepEqual(scopedExceptionCalls[0].args[3],overlapDates,`${label}: global raw overlap date binding`);
  assert.equal(scopedExceptionCalls[0].args[1].length,ordinaryExceptionIds.length,`${label}: guarded IDs`);
 }
 assert.equal(fastCalls.filter(sql=>sql===helper.CORABASTOS_BOUND_EXCEPTION_SQL).length,0,`${label}: old bound exception unused`);
 assert.equal(fastCalls.filter(sql=>sql===helper.CORABASTOS_PUBLISHED_VIEW_SQL).length,1,`${label}: view binding`);
 assert.equal(fastCalls.filter(sql=>sql===helper.CORABASTOS_HELD_DOCUMENTS_SQL).length,1,`${label}: one held set`);
 assert.equal(fastCalls.filter(sql=>sql===helper.CORABASTOS_BOUND_TYPED_SQL).length,Math.ceil(rawIds.length/250),`${label}: bound typed batches`);
 const fastBatchSizes=[...helperBatchSizes];
 helperSqlCalls=[];helperBatchSizes=[];helperQueryArgs=[];
 const fallbackRows=await fallbackHelper.corabastosAllHistoryQuotes();
 const fallbackCalls=[...helperSqlCalls];
 assert.equal(fallbackCalls.filter(sql=>sql===helper.CORABASTOS_HELD_DOCUMENTS_SQL).length,0,`${label}: unknown view no raw shortcut`);
 assert.equal(fallbackCalls.filter(sql=>sql===candidate.sql).length,Math.ceil(rawIds.length/250),`${label}: unknown view published fallback`);
 assert.deepEqual(fallbackRows.map(r=>JSON.stringify(normalize(r))),actualHelper.map(r=>JSON.stringify(normalize(r))),`${label}: unknown view fallback full tuple`);
 helperBatchSizes=fastBatchSizes;
 if(label===stressLabel)assert.deepEqual(helperBatchSizes,[250,1],`${label}: bounded batches`);
 assert.deepEqual(actualHelper.map(r=>JSON.stringify(normalize(r))),classified(originalRows).map(r=>JSON.stringify(normalize(r))),`${label}: actual shadow helper ordered full tuple parity`);
 result.cases[label]={bound_source_guard:true,unknown_view_original_fallback:true,source_ids:scopedIds,
  overlap_dates:overlapDates,scoped_exception_calls:scopedExceptionCalls.length,
  ordinary_count:ordinary.length,exception_ids:[...exceptions].sort(),
  rows:actual.length,helper_batch_sizes:helperBatchSizes,full_tuple_sha256:sha(canonical(actual).join('\n')),ordered_tuple_sha256:sha(ordered.map(r=>JSON.stringify(normalize(r))).join('\n'))};
}
async function scenario(label,setup,expected){await db.query('SAVEPOINT case_row');
 try{const resolved=await setup();await verify(label,typeof expected==='function'?expected(resolved):expected);}
 finally{await db.query('ROLLBACK TO SAVEPOINT case_row');await db.query('RELEASE SAVEPOINT case_row');}}
const stressLabel='251 raw IDs across 250 boundary with correction, held, future, alias and overlay collision';
test('bound source guard retains exact ordered/source tuples across 34 cases and unknown-view fallback',
 {skip:!enabled&&'Requires owned AGRO_COMPARISON_SQL_SOCKET'},async()=>{try{await db.connect();await db.query(`SET search_path=pg_temp; SET TIME ZONE 'America/Bogota'; SET statement_timeout='8s';
 CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text);
 CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,kind text,media_type text,retrieved_at timestamptz);
 CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,
  market_name text,category text,presentation text,quantity numeric,source_unit text,round int,round_label text,
  min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page int,
  PRIMARY KEY(document_id,source_locator));
 CREATE INDEX regional_quote_latest_full_cover ON regional_price(product_id,market_name,lower(btrim(presentation)),quantity,
  lower(btrim(source_unit)),unit,observed_on DESC,round DESC) INCLUDE(presentation,source_unit,document_id,source_locator);
 CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text,
  PRIMARY KEY(document_id,source_locator));
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
 CREATE TEMP TABLE verified_regional_category_overlay(document_id text,source_locator text,corrected_category text);
 CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
  corrected_min_price numeric,corrected_max_price numeric);
 CREATE TEMP TABLE unresolved_city_pdf_publication_conflict(document_id text PRIMARY KEY);
 CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS
  (SELECT 1 FROM unresolved_city_pdf_publication_conflict held WHERE held.document_id=r.document_id OFFSET 0);
 CREATE TEMP VIEW raw_resolved_regional_price AS
 SELECT r.* FROM published_regional_price r WHERE NOT EXISTS
  (SELECT 1 FROM regional_price_product_correction c WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
 UNION ALL SELECT r.document_id,r.source_locator,r.observed_on,c.corrected_product_id,c.corrected_product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,r.min_price,r.max_price,r.unit,
  r.min_unit_price,r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
 CREATE TEMP VIEW resolved_regional_price AS
 SELECT x.document_id,x.source_locator,x.observed_on,x.product_id,x.product_name,
  x.market_name,coalesce(o.corrected_category,x.category) AS category,
  x.presentation,x.quantity,x.source_unit,x.round,x.round_label,x.min_price,x.max_price,
  x.unit,x.min_unit_price,x.max_unit_price,x.source_page
 FROM raw_resolved_regional_price x LEFT JOIN verified_regional_category_overlay o
  ON o.document_id=x.document_id AND o.source_locator=x.source_locator;
 INSERT INTO market VALUES
 ('legacy1','Bogotá, Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('legacy2','Bogotá D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('canonical','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('rawgrave','Bogotà, Corabastos','Bogotá','Bogotá, D.C.','99999');
 INSERT INTO source_document VALUES
 ('old','https://www.dane.gov.co/old.pdf','original','application/pdf','2022-01-11'),
 ('new','https://www.dane.gov.co/new.pdf','original','application/pdf','2023-01-11'),
 ('held','https://www.dane.gov.co/held.pdf','original','application/pdf','2026-01-11'),
 ('same','https://www.dane.gov.co/same.pdf','original','application/pdf','2023-01-11');`);
 const localView=(await db.query("SELECT pg_get_viewdef('published_regional_price'::regclass,true) AS definition")).rows[0].definition;
 const localHash=sha(localView);
 helper=load('comparison-corabastos-all-history.ts',{
  './db':{database:()=>({connect:async()=>helperClient})},
  './city-market-alias':alias,'./price-quotes':price,'./category-path-sql':categoryPath,__viewHash:localHash});
 assert.notEqual(localHash,fallbackHelper.CORABASTOS_PUBLISHED_VIEW_SHA256);
 result.local_view_sha256=localHash;
 await db.query('BEGIN');
 await scenario('fractional native numeric fields preserved as strings',async()=>({a:await addRow({price:'100.125'})}),x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('database collation with accented product and presentation',async()=>{const a=await addRow({product:'azucar',presentation:'Ático'});const b=await addRow({product:'arándanos',presentation:'Bulto'});const c=await addRow({product:'azucar',presentation:'Bulto',quantity:25});return {a,b,c};},x=>({expectedIds:['arándanos','azucar'],expectedLocators:[x.a,x.b,x.c]}));
 await scenario('verified winner category overlay projects into original quote',async()=>{const a=await addRow({category:'Frutas > Cítricos'});await db.query('INSERT INTO verified_regional_category_overlay VALUES($1,$2,$3)',['old',a,'Verduras > Hojas']);return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('verified money overlay preserves the selected source and all quoted fields',async()=>{
  const a=await addRow({price:100});
  await db.query('INSERT INTO verified_city_pdf_price_overlay VALUES($1,$2,6000,7000)',['old',a]);
  const raw=(await db.query('SELECT min_price,max_price FROM regional_price WHERE document_id=$1 AND source_locator=$2',['old',a])).rows[0];
  assert.deepEqual(raw,{min_price:'100',max_price:'102'});
  return {a};
 },x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('classification path stays distinct from verified category',async()=>{const a=await addRow({category:'Frutas > Cítricos'});await db.query('INSERT INTO verified_regional_category_overlay VALUES($1,$2,$3)',['old',a,'Verduras > Hojas']);await db.query('INSERT INTO regional_classification VALUES($1,$2,$3::text[])',['old',a,['Revisada','Fuente']]);return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('two verified categories for one locator take exact generic fallback',async()=>{const a=await addRow({category:'Frutas > Cítricos'});await db.query('INSERT INTO verified_regional_category_overlay VALUES($1,$2,$3),($1,$2,$4)',['old',a,'Verduras > Hojas','Tubérculos > Raíces']);return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('same-name market outside canonical municipality cannot hydrate winner',async()=>{const a=await addRow();await db.query("INSERT INTO market VALUES('wrongarea','Bogotá, D.C., Corabastos','Elsewhere','Other','99999')");return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('same-name duplicate market within canonical municipality takes generic fallback',async()=>{const a=await addRow();await db.query("INSERT INTO market VALUES('duplicate11001','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')");return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('corrected raw ID joins cross-alias conflict witnesses before older fallback',async()=>{
  const older=await addRow({product:'p',market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const legacy=await addRow({product:'legacy-p',market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',['old',legacy,'p','Product P']);
  await addRow({product:'p',market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:300});
  return {older};
 },x=>({expectedIds:['p'],expectedLocators:[x.older],expectedExceptions:['p']}));
 await scenario('held corrected alias rival cannot suppress published newer source',async()=>{
  await addRow({product:'p',market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const current=await addRow({product:'p',market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  const held=await addRow({product:'legacy-p',market:'Bogotá D.C., Corabastos',doc:'held',day:'2022-01-10',price:300});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',['held',held,'p','Product P']);
  await db.query("INSERT INTO unresolved_city_pdf_publication_conflict VALUES('held')");
  return {current};
 },x=>({expectedIds:['p'],expectedLocators:[x.current],expectedExceptions:['p']}));
 await scenario('old only',async()=>({a:await addRow()}),x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('held latest keeps older eligible',async()=>{const a=await addRow();await addRow({doc:'held',day:'2025-01-10',price:999});await db.query("INSERT INTO unresolved_city_pdf_publication_conflict VALUES('held')");return {a};},x=>({expectedIds:['p'],expectedLocators:[x.a]}));
 await scenario('future-only source stays absent',async()=>{await addRow({day:'2099-01-10'});return {};},{expectedIds:[]});
 await scenario('future latest leaves old winner',async()=>{const a=await addRow();await addRow({day:'2099-01-10',price:999});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('higher round wins same date',async()=>{await addRow({round:1});const a=await addRow({round:2,price:150});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('newer retrieved document wins tied round',async()=>{await addRow({doc:'old'});const a=await addRow({doc:'new',price:150});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('two package quantities both survive',async()=>{const a=await addRow({quantity:25});const b=await addRow({quantity:50});return {a,b};},x=>({expectedLocators:[x.a,x.b]}));
 await scenario('two source unit spellings both survive',async()=>{const a=await addRow({sourceUnit:'Kilogramo'});const b=await addRow({sourceUnit:'Caja'});return {a,b};},x=>({expectedLocators:[x.a,x.b]}));
 await scenario('corrected product id and name route to original',async()=>{const a=await addRow({product:'old-p'});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',['old',a,'new-p','Corrected P']);return {a};},x=>({expectedIds:['new-p'],expectedLocators:[x.a],expectedExceptions:['new-p']}));
 await scenario('cross alias same day different round original chooses higher',async()=>{await addRow({market:'Bogotá, Corabastos',round:1});const a=await addRow({market:'Bogotá D.C., Corabastos',round:2,price:101});return {a};},x=>({expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('four aliases including raw grave market do not add fifth market',async()=>{
  const a=await addRow({market:'Bogotà, Corabastos',day:'2022-01-11'});
  await addRow({market:'Bogotá, Corabastos',day:'2022-01-10'});
  await addRow({market:'Bogotá D.C., Corabastos',day:'2022-01-09'});
  await addRow({market:'Bogotá, D.C., Corabastos',day:'2022-01-08'});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('same-day contradictory alias money falls back older',async()=>{
  const a=await addRow({market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  await addRow({market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  await addRow({market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:300});return {a};},x=>({expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('same-day unit ambiguity falls back to original',async()=>{
  const a=await addRow({day:'2022-01-01',unit:'kg'});
  const b=await addRow({day:'2022-01-10',round:2,unit:'package'});
  await addRow({day:'2022-01-10',round:1,unit:'kg'});return {a,b};},x=>({expectedLocators:[x.a,x.b],expectedExceptions:['p']}));
 await scenario('display spelling variation takes original',async()=>{
  await addRow({presentation:'Bulto',day:'2022-01-01'});
  const a=await addRow({presentation:' bulto ',day:'2022-01-10'});return {a};},x=>({expectedExceptions:['p']}));
 await scenario('same retrieval ties select source locator',async()=>{
  const a=await addRow({price:100});await addRow({price:101});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('same literal revised category remains eligible',async()=>{
  await addRow({doc:'old',category:'Frutas > Cítricos'});
  const a=await addRow({doc:'new',category:'Verduras > Raíces'});return {a};},x=>({expectedLocators:[x.a]}));
 await scenario('cross alias different min unit price rejects same money',async()=>{
  const a=await addRow({market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const b=await addRow({market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  const c=await addRow({market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:200});
  await db.query('UPDATE regional_price SET min_unit_price=201 WHERE source_locator=$1',[c]);return {a,b};
 },x=>({expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('cross alias nullable min unit differs and older survives',async()=>{
  const a=await addRow({market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const b=await addRow({market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  await addRow({market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:200});
  await db.query('UPDATE regional_price SET min_unit_price=NULL WHERE source_locator=$1',[b]);return {a};
 },x=>({expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('cross alias classification path conflict rejects equal money',async()=>{
  const a=await addRow({market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const b=await addRow({market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  const c=await addRow({market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:200});
  await db.query('INSERT INTO regional_classification VALUES($1,$2,$3::text[])',['old',b,['Frutas','Cítricos']]);
  await db.query('INSERT INTO regional_classification VALUES($1,$2,$3::text[])',['old',c,['Verduras','Raíces']]);return {a};
 },x=>({expectedLocators:[x.a],expectedExceptions:['p']}));
 await scenario('cross-batch corrected target excludes independently ordinary key',async()=>{
  const a=await addRow({product:'old-p',name:'Old name',day:'2022-01-11',price:200});
  await addRow({product:'new-p',name:'New name',day:'2022-01-10',price:100});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',['old',a,'new-p','Corrected name']);return {a};
 },x=>({expectedIds:['new-p'],expectedLocators:[x.a],expectedExceptions:['new-p']}));
 await scenario('nine effective corrections with shared raw ID split and exact source locators',async()=>{
  const ids=['alpha','beta','gamma','delta','epsilon','zeta','eta','theta','iota'];
  const locators=[];
  for(let i=0;i<ids.length;i++){
   const raw=i<2?'legacy-shared':`legacy-${ids[i]}`;
   const locator=await addRow({product:raw,name:`Legacy ${ids[i]}`,price:100+i});
   locators.push(locator);
   await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',
    ['old',locator,ids[i],`Corrected ${ids[i]}`]);
  }
  return {ids,locators};
 },x=>({expectedIds:x.ids,expectedLocators:x.locators,expectedExceptions:x.ids}));
 await scenario('shared raw ID corrections preserve one target alias conflict without cross-target exclusion',async()=>{
  const older=await addRow({product:'alpha',market:'Bogotá, D.C., Corabastos',day:'2022-01-01',price:100});
  const a=await addRow({product:'legacy-shared',market:'Bogotá, Corabastos',day:'2022-01-10',price:200});
  const b=await addRow({product:'legacy-shared',market:'Bogotá D.C., Corabastos',day:'2022-01-10',price:300});
  const beta=await addRow({product:'legacy-shared',market:'Bogotá, D.C., Corabastos',day:'2022-01-11',price:400});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4),($1,$5,$3,$4),($1,$6,$7,$8)',
   ['old',a,'alpha','Alpha',b,beta,'beta','Beta']);
  return {older,beta};
 },x=>({expectedIds:['alpha','beta'],expectedLocators:[x.older,x.beta],expectedExceptions:['alpha','beta']}));
 await scenario('nine corrected IDs include held, future, and same-day round winners without crosstalk',async()=>{
  const ids=['alpha','beta','gamma','delta','epsilon','zeta','eta','theta','iota'];
  const locators=[];
  for(let i=0;i<ids.length;i++){
   const raw=i<2?'legacy-shared':`legacy-${ids[i]}`;
   const first=await addRow({product:raw,price:200+i});
   let selected=first;
   if(i===2){selected=await addRow({product:raw,round:2,price:300+i});}
   if(i===3){await addRow({product:raw,doc:'held',day:'2025-01-10',price:999});}
   if(i===4){await addRow({product:raw,day:'2099-01-10',price:999});}
   if(i===2)await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',
    ['old',selected,ids[i],`Corrected ${ids[i]}`]);
   await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',
    ['old',first,ids[i],`Corrected ${ids[i]}`]);
   locators.push(selected);
  }
  await db.query("INSERT INTO unresolved_city_pdf_publication_conflict VALUES('held')");
  return {ids,locators};
 },x=>({expectedIds:x.ids,expectedLocators:x.locators,expectedExceptions:x.ids}));
 await scenario(stressLabel,async()=>{
  const locators=[];
  for(let i=0;i<251;i++)locators.push(await addRow({product:`item${String(i).padStart(3,'0')}`,name:`Item ${i}`,price:100+i}));
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',
   ['old',locators[250],'item000','Corrected Item 000']);
  await addRow({product:'item248',doc:'held',day:'2025-01-10',price:999});
  await db.query("INSERT INTO unresolved_city_pdf_publication_conflict VALUES('held')");
  await addRow({product:'item247',day:'2099-01-10',price:999});
  await addRow({product:'item246',market:'Bogotá, Corabastos',day:'2022-01-10',price:999});
  await addRow({product:'item246',day:'2022-01-01',price:90});
  await db.query('INSERT INTO verified_regional_category_overlay VALUES($1,$2,$3),($1,$2,$4)',
   ['old',locators[245],'Verduras > Hojas','Tubérculos > Raíces']);
  return {locators};
 });
 await db.query('ROLLBACK');assert.equal(Object.keys(result.cases).length,34);
 }catch(e){try{await db.query('ROLLBACK')}catch{}throw e}
 finally{try{await db.end()}catch{}}});
