const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const vm=require('node:vm');
const ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/lib/server/comparison-corabastos-all-history.ts'),'utf8');
const fakeView='SELECT * FROM TEST_PUBLISHED';
const fakeHash=crypto.createHash('sha256').update(fakeView).digest('hex');
function load(client,errors,{bound=true}={}){
 const loaded=bound?source.replace('b6b773cdb0e1450f926c53d97bcdf4665cb39b3108bf5abb63a6d71b141b0e40',fakeHash):source;
 const compiled=ts.transpileModule(loaded,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const exports={};
 const mocks={
  './db':{database:()=>({connect:async()=>client})},
  './city-market-alias':{CORABASTOS_CITY_MARKET_ID:'sipsa-bogota-d-c-corabastos',cityMarketIdSql:()=>'(market-id)',cityMarketNamesForIdSql:()=>'(names)'},
  './price-quotes':{cityPriceQuotes:()=>'(authored-quote)'},
  './category-path-sql':require('./helpers/load-category-path-sql.cjs')(),
 };
 vm.runInNewContext(compiled,{exports,require:id=>id==='server-only'?{}:id==='node:crypto'?crypto:mocks[id],console:{error:(...v)=>errors.push(v)},Map,Set,Date});
 return exports;
}
function harness({seed=['p','q'],batchRows=[],exceptions=[],collisions=[],classes=[],fault='',rollbackFailure=false,
 bound=true,held=[],overlap=[]}={}){
 const calls=[],errors=[];let releases=0;
 const client={async query(sql,args){
  let stage=sql.startsWith('BEGIN')?'begin':sql==='COMMIT'?'commit':sql==='ROLLBACK'?'rollback'
   :sql===helper.CORABASTOS_PUBLISHED_VIEW_SQL?'binding'
   :sql===helper.CORABASTOS_HELD_DOCUMENTS_SQL?'holds'
   :sql===helper.CORABASTOS_RAW_PRODUCT_SEED_SQL?'seed'
   :sql===helper.CORABASTOS_ALIAS_OVERLAP_DATES_SQL?'overlap'
   :sql===helper.CORABASTOS_TYPED_BATCH_SQL||sql===helper.CORABASTOS_BOUND_TYPED_SQL?'batch'
   :sql===helper.CORABASTOS_INDEXED_EXCEPTION_SQL||sql===helper.CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL?'exception'
   :sql===helper.CORABASTOS_EXACT_PRODUCT_SQL?'collision'
   :sql===helper.CORABASTOS_ORIGINAL_ORDER_SQL?'order'
   :sql===helper.CORABASTOS_SELECTED_CLASSIFICATIONS_SQL?'classification':'UNKNOWN';
  calls.push({stage,args,sql});
  if(stage==='UNKNOWN')throw new Error('unknown SQL');
  if(stage===fault)throw Object.assign(new Error('private price and source detail'),{code:'57014'});
  if(stage==='rollback'&&rollbackFailure)throw new Error('rollback failed');
  if(stage==='binding')return {rows:[{definition:fakeView}]};
  if(stage==='holds')return {rows:held.map(document_id=>({document_id}))};
  if(stage==='seed')return {rows:seed.map(product_id=>({product_id}))};
  if(stage==='overlap')return {rows:overlap.map(observed_on=>({observed_on}))};
  if(stage==='batch')return {rows:batchRows.shift()||[]};
  if(stage==='exception')return {rows:exceptions};
  if(stage==='collision')return {rows:collisions};
  if(stage==='order')return {rows:args[0].map((_,i)=>({ord:i+1}))};
  if(stage==='classification')return {rows:classes};
  return {rows:[]};
 },release(){releases++}};
 const helper=load(client,errors,{bound});
 return {helper,calls,errors,releases:()=>releases};
}
const q=(id,locator)=>({id,name:id,category:'Frutas',category_path:['Frutas'],presentation:'Bulto',units:'50 Kilogramo',unit:'package',series:'city',location_id:'sipsa-bogota-d-c-corabastos',source_market_id:'m',location_name:'Bogotá, D.C., Corabastos',department:'Bogotá, D.C.',price:123.45,min_price:122.11,max_price:124.79,date:'2022-02-10',document_id:'doc',source_locator:locator,source_page:1,source_units:'50 Kilogramo'});
const typed=(quote,kind=0,exception_product_id=null)=>({row_kind:kind,...quote,exception_product_id});
const marker=id=>({row_kind:1,...Object.fromEntries(Object.keys(q('x','x')).map(k=>[k,null])),exception_product_id:id});
test('typed rows, exact indexed exception, ordered and classified in one RR, empty exception and decimal unchanged',async()=>{
 const h=harness({batchRows:[[typed(q('p','old')),marker('q')]],exceptions:[q('q','new')],classes:[{document_id:'doc',source_locator:'new',category_path:['Clasificada']} ]});
 const rows=await h.helper.corabastosAllHistoryQuotes();
 assert.deepEqual(Array.from(rows,r=>r.id),['p','q']);
 assert.equal(rows[0].price,123.45);assert.deepEqual(Array.from(rows[1].category_path),['Clasificada']);
 assert.deepEqual(h.calls.map(c=>c.stage),['begin','binding','holds','seed','overlap','batch','exception','order','classification','commit']);
 assert.equal(h.releases(),1);assert.equal(h.errors.length,0);
 const empty=harness({seed:[],batchRows:[]});
 assert.deepEqual(Array.from(await empty.helper.corabastosAllHistoryQuotes()),[]);
 assert.equal(empty.calls.some(c=>c.stage==='exception'),false);
 assert.equal(empty.releases(),1);
});
test('corrected target after 250-ID boundary removes earlier ordinary, metadata collision uses exact authored fallback',async()=>{
 const seed=Array.from({length:251},(_,i)=>`r${i}`);
 const h=harness({seed,batchRows:[[typed(q('target','stale'))],[marker('target'),{...marker('target'),row_kind:2}]],collisions:[q('target','exact')]});
 const rows=await h.helper.corabastosAllHistoryQuotes();
 assert.deepEqual(Array.from(rows,r=>r.source_locator),['exact']);
 assert.equal(h.calls.some(c=>c.stage==='exception'),false);
 assert.deepEqual(h.calls.filter(c=>c.stage==='batch').map(c=>c.args[0].length),[250,1]);
 assert.equal(h.calls.filter(c=>c.stage==='collision').length,1);
});
for(const stage of ['begin','binding','holds','seed','overlap','batch','exception','collision','order','classification','commit']){
 test(`SQL57014 ${stage}: sanitized diagnostic, no partial result, rollback and release`,async()=>{
  const h=harness({batchRows:[[{...typed(q('p','old'))},marker('q'),{...marker('z'),row_kind:2}]],exceptions:[q('q','new')],collisions:[q('z','exact')],fault:stage,rollbackFailure:stage==='collision'});
  await assert.rejects(h.helper.corabastosAllHistoryQuotes(),e=>e.code==='57014');
  assert.equal(h.calls.some(c=>c.stage==='rollback'),stage!=='begin');
  assert.equal(h.releases(),1);assert.equal(h.errors.length,1);
  assert.equal(h.errors[0][1].stage,stage);
  assert.equal(h.errors[0][1].sqlstate,'57014');
  assert.equal(JSON.stringify(h.errors).includes('private price and source detail'),false);
 });
}
test('invalid batch marker fails closed and rolls back',async()=>{
 const h=harness({batchRows:[[{...marker('p'),row_kind:8}]]});
 await assert.rejects(h.helper.corabastosAllHistoryQuotes(),/CORABASTOS_UNKNOWN_ROW_KIND/);
 assert.equal(h.calls.some(c=>c.stage==='rollback'),true);assert.equal(h.releases(),1);
});

test('nine guarded effective IDs use one source-held, raw-overlap-scoped exception SQL',async()=>{
 const ids=['alpha','beta','gamma','delta','epsilon','zeta','eta','theta','iota'];
 const h=harness({seed:ids,batchRows:[ids.map(marker)],exceptions:ids.map(id=>q(id,'source-'+id))});
 const rows=await h.helper.corabastosAllHistoryQuotes();
 assert.deepEqual(Array.from(rows,r=>r.id),ids);
 assert.equal(crypto.createHash('sha256').update(h.helper.CORABASTOS_INDEXED_EXCEPTION_SQL).digest('hex'),
  '90b8d68352376a25eb5c8983a4cbb4f8d1eba867e0623ebe10b40b2a7fd84c37');
 assert.equal(h.helper.CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL.includes('rival.observed_on=ANY($4::date[])'),true);
 const calls=h.calls.filter(c=>c.stage==='exception');
 assert.equal(calls.length,1);
 assert.equal(calls[0].sql,h.helper.CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL);
 assert.equal(calls[0].args[0],'sipsa-bogota-d-c-corabastos');
 assert.deepEqual(Array.from(calls[0].args[1]),ids);
 assert.deepEqual(Array.from(calls[0].args[2]),[]);
 assert.deepEqual(Array.from(calls[0].args[3]),[]);
 assert.equal(h.calls.filter(c=>c.stage==='order').length,1);
 assert.equal(h.calls.filter(c=>c.stage==='classification').length,1);
 assert.equal(h.calls.filter(c=>c.stage==='commit').length,1);
 assert.equal(h.releases(),1);
});


test('nonempty raw overlap and live held IDs are passed unchanged to scoped exception',async()=>{
 const h=harness({seed:['p'],batchRows:[[marker('p')]],exceptions:[q('p','actual')],
  held:['held-doc'],overlap:['2026-02-25']});
 const rows=await h.helper.corabastosAllHistoryQuotes();
 assert.deepEqual(Array.from(rows,r=>r.source_locator),['actual']);
 const calls=h.calls.filter(c=>c.stage==='exception');
 assert.equal(calls.length,1);assert.equal(calls[0].sql,h.helper.CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL);
 assert.deepEqual(Array.from(calls[0].args[2]),['held-doc']);
 assert.deepEqual(Array.from(calls[0].args[3]),['2026-02-25']);
});
test('unknown published definition retains original published-view SQL and no held read',async()=>{
 const h=harness({bound:false,seed:['p'],batchRows:[[marker('p')]],exceptions:[q('p','fallback')]});
 const rows=await h.helper.corabastosAllHistoryQuotes();
 assert.deepEqual(Array.from(rows,r=>r.source_locator),['fallback']);
 assert.equal(h.calls.some(c=>c.stage==='holds'),false);
 assert.equal(h.calls.find(c=>c.stage==='batch').sql,h.helper.CORABASTOS_TYPED_BATCH_SQL);
 assert.equal(h.calls.find(c=>c.stage==='exception').sql,h.helper.CORABASTOS_INDEXED_EXCEPTION_SQL);
});

function loadComparison(mocks) {
 const exports={};
 const content=fs.readFileSync(path.join(__dirname,'../src/lib/server/comparisons.ts'),'utf8')
   .replace('async function marketQuotes(', 'export async function marketQuotes(');
 const js=ts.transpileModule(content,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(js,{exports,require:id=>id==='server-only'?{}:mocks[id],console,Map,Set,Date});
 return exports;
}
test('only unfiltered canonical Corabastos city/all enters one-snapshot helper; no outside-snapshot classification',async()=>{
 let routed=0,generic=0,enriched=0;
 const canonical='sipsa-bogota-d-c-corabastos';
 const selected=[q('p','row 1')];
 const aliases={CORABASTOS_CITY_MARKET_ID:canonical,cityMarketIdSql:()=>'(market-id)',
  cityMarketNamesForIdSql:()=>'(names)',resolveCityMarketId:id=>id};
 const comparison=loadComparison({
  './db':{database:()=>({query:async()=>{generic++;return {rows:[]}}}),WINDOW:'observed_on<=CURRENT_DATE'},
  './comparison-corabastos-all-history':{corabastosAllHistoryQuotes:async()=>{routed++;return selected}},
  './price-quotes':{PRICE_QUOTE_VALUES:'SELECT 1',CITY_LOOSE_LATEST_QUOTES:'SELECT 1',CITY_RECENT_LOOSE_LATEST_QUOTES:'SELECT 1',
   CITY_LOOSE_UNIT_AMBIGUITY:'SELECT 1',cityPriceQuotes:()=>'(authored-quote)',
   withQuoteClassifications:async rows=>{enriched++;return rows}},
  './city-market-alias':aliases,'./market-sql':{cityAliasConflicts:()=>'(witness)'},
  './input-identities':{},'./market-alias':{},'../comparison-math':{},
  '../comparison-display':{},'../filter-labels':{},'../input-locations':{},
 });
 assert.deepEqual(Array.from(await comparison.marketQuotes(canonical,'city','all','')),selected);
 assert.equal(routed,1);assert.equal(enriched,0);assert.equal(generic,0);
 for(const [location,series,history,product,identities] of [
  [canonical,'city','recent','',undefined],
  [canonical,'city','all','p',undefined],
  [canonical,'city','all','',['p']],
  ['dane-city-bogota-corabastos','city','all','',undefined],
  [canonical,'monthly','all','',undefined],
 ])await comparison.marketQuotes(location,series,history,product,identities);
 assert.equal(routed,1);assert.equal(generic,5);
});
