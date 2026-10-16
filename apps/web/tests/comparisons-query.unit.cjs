/* Exact PostgreSQL parity for bounded comparison selection; isolated TEMP data. */
const {test,before,after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const {Client,types} = require('pg');
types.setTypeParser(1082,v=>v);types.setTypeParser(1700,Number);
const socket=process.env.AGRO_COMPARISON_SQL_SOCKET;
const enabled=socket?.startsWith('/tmp/agro-comparison-pg-');
const server=path.join(__dirname,'../src/lib/server');
const WINDOW="observed_on>CURRENT_DATE-INTERVAL '12 months' AND observed_on<=CURRENT_DATE";
let db,price,math,calls=[];
function load(filename,mocks){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require:n=>n==='server-only'?{}:mocks[n],Map,Set,Date});return exports;}
const cityAlias=load(path.join(server,'city-market-alias.ts'),{});
const marketSql=load(path.join(server,'market-sql.ts'),{'./city-market-alias':cityAlias});
const cityPackage=load(path.join(server,'city-package-equivalence.ts'),{});
const detailDiagnostics=load(path.join(server,'product-detail-diagnostics.ts'),{});
const inputIdentityEquivalence=load(path.join(server,'../input-identity-equivalence.ts'),{
 '../../../../shared/input-identity-equivalences.json':{default:JSON.parse(fs.readFileSync(path.join(__dirname,'../../../shared/input-identity-equivalences.json'),'utf8'))},
});
const dbMock={WINDOW,database:()=>({query:async(sql,args)=>{calls.push({sql,args});return db.query(sql,args);}})};
function comparison(){
 const labels=load(path.join(server,'../filter-labels.ts'),{});
 const locations=load(path.join(server,'../input-locations.ts'),{'./filter-labels':labels});
 const display=load(path.join(server,'../comparison-display.ts'),{
  './label-normalization':{normalizeLabel:value=>value},'./comparison-math':math});
 return load(path.join(server,'comparisons.ts'),{'./db':dbMock,'./price-quotes':price,
 // This fixture keeps edits inside one rollback-only transaction, so a reader
 // that opens its own RR transaction cannot share these TEMP rows. Its actual
 // transaction and SQL are exercised in comparison-corabastos-all-history.pg.unit.cjs.
 './comparison-corabastos-all-history':{corabastosAllHistoryQuotes:async()=>{
  calls.push({sql:'CORABASTOS_ALL_HISTORY_READER',args:[]});
  return oldQuotes(cityAlias.CORABASTOS_CITY_MARKET_ID,'city','all');
 }},
 './market-alias':{resolveMarketAlias:async(_,id)=>id},
 './city-market-alias':cityAlias,
 './market-sql':marketSql,
 '../input-identity-equivalence':inputIdentityEquivalence,
 './input-identities':{reconcileInputCatalog:async rows=>rows},'../comparison-math':math,
 '../filter-labels':labels,'../input-locations':locations,
 '../comparison-display':display}).comparison;
}
const normalize=x=>JSON.parse(JSON.stringify(x));
const sorted=rows=>normalize(rows).sort((a,b)=>a.a.id.localeCompare(b.a.id)||a.a.units.localeCompare(b.a.units));
const byCityIdentity=rows=>normalize(rows).sort((a,b)=>JSON.stringify([a.id,a.location_id,a.presentation,a.units,a.unit]).localeCompare(JSON.stringify([b.id,b.location_id,b.presentation,b.units,b.unit])));
before(async()=>{
 if(!enabled)return;
 db=new Client({host:socket,port:65449,database:'postgres'});await db.connect();
 await db.query("SET search_path=pg_temp; SET statement_timeout='8s'; SET TIME ZONE 'America/Bogota'");
 await db.query(`CREATE TEMP TABLE market(id text,name text,city text,region text,municipality_id text);
 CREATE TEMP TABLE product(id text,name text,category text);
 CREATE TEMP TABLE source_document(id text,source_url text,retrieved_at timestamptz);
 CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text);
 CREATE TEMP TABLE input_identity_alias(legacy_id text,id text);
 CREATE TEMP TABLE input_latest_projection_state(scope text,source_epoch bigint,projection_epoch bigint,asof_bogota date);
 INSERT INTO input_latest_projection_state VALUES ('department',0,-1,CURRENT_DATE),('municipality',0,-1,CURRENT_DATE);
 CREATE TEMP TABLE input_department_latest_raw(id text,department text,observed_on date,price numeric);
 CREATE TEMP TABLE input_municipal_latest_raw(id text,department text,municipality text,observed_on date,price numeric);
 CREATE TEMP TABLE price_observation(product_id text,market_id text,source_id text,observed_on date,price numeric,min_price numeric,max_price numeric,unit text,document_id text,source_locator text,source_url text,period text);
 CREATE TEMP VIEW published_price_observation AS SELECT * FROM price_observation WHERE source_locator!='withdrawn';
 CREATE TEMP TABLE regional_price(product_id text,product_name text,market_name text,category text,observed_on date,min_price numeric,max_price numeric,unit text,presentation text,quantity numeric,source_unit text,round integer,document_id text,source_locator text,source_page integer);
 CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text);
 CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
   corrected_min_price numeric,corrected_max_price numeric);
 CREATE TEMP TABLE city_pdf_publication_conflict(document_id text PRIMARY KEY);
    CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS (
      SELECT 1 FROM city_pdf_publication_conflict blocked WHERE blocked.document_id=r.document_id OFFSET 0);
    CREATE TEMP VIEW resolved_regional_price AS
 SELECT r.* FROM published_regional_price r WHERE NOT EXISTS (
   SELECT 1 FROM regional_price_product_correction c
   WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
 UNION ALL
 SELECT c.corrected_product_id,c.corrected_product_name,r.market_name,r.category,
   r.observed_on,r.min_price,r.max_price,r.unit,r.presentation,r.quantity,
   r.source_unit,r.round,r.document_id,r.source_locator,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r
   ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
 CREATE TEMP TABLE input_municipal_price(id text,name text,category text,presentation text,department text,municipality text,price numeric,observed_on date,document_id text,source_locator text,brand text,registration text,product_line text);
 CREATE TEMP VIEW published_input_municipal_price AS SELECT * FROM input_municipal_price;
 CREATE INDEX input_municipal_location_options ON input_municipal_price(department,municipality,observed_on DESC);
 INSERT INTO input_municipal_price SELECT 'input','Insumo','Agrícola','1 litro','Departamento',l.municipality,100,CURRENT_DATE+l.day,'old','row','','','' FROM (VALUES('A',-1),('A',-500),('A',1),('B',-500),('C',1),('D',-1),('D',-2))l(municipality,day);
 INSERT INTO input_municipal_price VALUES
   ('urea-50','Urea','Fertilizantes','50 kg','Departamento','A',120,CURRENT_DATE-1,'old','sheet!row 1','Marca','ICA-1','Línea'),
   ('urea-50','Urea','Fertilizantes','50 kg','Departamento','D',150,CURRENT_DATE-2,'old','sheet!row 2','Marca','ICA-1','Línea'),
   ('urea-25','Urea','Fertilizantes','25 kg','Departamento','A',70,CURRENT_DATE-1,'old','sheet!row 3','Marca','ICA-2','Línea'),
   ('urea-25','Urea','Fertilizantes','25 kg','Departamento','D',80,CURRENT_DATE-2,'old','sheet!row 4','Marca','ICA-2','Línea'),
   ('withdrawn-demo','Corregido','Fertilizantes','1 litro','Departamento','A',999,CURRENT_DATE-1,'withdrawn-doc','sheet!row 5; inputs-pdf-v1','','',''),
   ('withdrawn-demo','Corregido','Fertilizantes','1 litro','Departamento','A',100,CURRENT_DATE-2,'old','sheet!row 5','','',''),
   ('withdrawn-demo','Corregido','Fertilizantes','1 litro','Departamento','D',130,CURRENT_DATE-2,'old','sheet!row 6','','',''),
   ('alias-legacy','Revisión','Fertilizantes','1 litro','Departamento','A',70,CURRENT_DATE-1,'old','sheet!row 7','','',''),
   ('alias-new','Revisión','Fertilizantes','1 litro','Departamento','A',75,CURRENT_DATE-1,'new','sheet!row 7','','','');
 INSERT INTO input_identity_alias VALUES('alias-legacy','alias-new');
 INSERT INTO ingestion_checkpoint VALUES('withdrawn-doc','inputs-pdf-v2','inputs-pdf:published');

 INSERT INTO market VALUES('a','A','A','Uno'),('b','B','B','Dos'),('c','C','C','Tres'),('review-only','Only withdrawn','D','Cuatro');
 INSERT INTO source_document VALUES('old','old','2026-01-01'),('new','new','2026-02-01');
 INSERT INTO source_document VALUES('withdrawn-doc','withdrawn','2026-03-01');
 INSERT INTO product SELECT 'p'||n,'Producto'||n,'Frutas' FROM generate_series(1,16)n;
 INSERT INTO regional_price SELECT 'p'||n,'Producto'||n,m.name,'Frutas',CURRENT_DATE-1,100+n,100+n,'package','Caja',2.5,'Kilogramo',1,'old','base-'||n||'-'||m.id,1 FROM generate_series(1,16)n CROSS JOIN market m WHERE m.id='a' OR (n<15 AND m.id='b') OR(n<14 AND m.id='c');
 INSERT INTO regional_price VALUES('p1','Producto1','A','Frutas',CURRENT_DATE-1,1000,1000,'package','Caja',2.5,'Kilogramo',2,'old','round2',1),('p1','Producto1','A','Frutas',CURRENT_DATE-1,2000,2000,'package','Caja',2.5,'Kilogramo',2,'new','revision',2),('p1','Producto1','A','Frutas',CURRENT_DATE-1,8000,8000,'package','Caja',12.5,'Kilogramo',1,'old','large-a',1),('p1','Producto1','B','Frutas',CURRENT_DATE-2,9000,9000,'package','Caja',12.5,'Kilogramo',1,'old','large-b',1),('p2','Producto2','A','Frutas',CURRENT_DATE-500,50,50,'package','Bolsa',1,'Kilogramo',1,'old','historic',1),('p1','Producto1','C','Frutas',CURRENT_DATE+1,99999,99999,'package','Caja',2.5,'Kilogramo',1,'old','future',1);
 INSERT INTO regional_classification VALUES('new','revision',ARRAY['Frutas','Cítricos corregidos']);
 INSERT INTO price_observation VALUES('p1','a','dane-sipsa',CURRENT_DATE-3,5,5,5,'kg','old','monthly','url','monthly'),('p1','b','dane-sipsa',CURRENT_DATE-3,6,6,6,'kg','old','monthly','url','monthly'),('p1','a','dane-sipsa',CURRENT_DATE-1,999,999,999,'kg','new','withdrawn','url','monthly'),('p1','review-only','dane-sipsa',CURRENT_DATE-1,777,777,777,'kg','new','withdrawn','url','monthly');`);
 await db.query("ALTER TABLE source_document ADD COLUMN kind text NOT NULL DEFAULT 'original', ADD COLUMN media_type text NOT NULL DEFAULT 'application/pdf'");
 await db.query("INSERT INTO price_observation VALUES('orphan','c','dane-sipsa',CURRENT_DATE-1,888,888,888,'kg','old','orphan','url','monthly')");
 const definition=fs.readFileSync(path.join(__dirname,'../../../pipelines/ingestion/schema.sql'),'utf8').match(/CREATE OR REPLACE VIEW published_input_municipal_price AS[\s\S]*?\n\);/);
 assert.ok(definition,'published municipal source view');
 await db.query(definition[0]);
 price=load(path.join(server,'price-quotes.ts'),{'./db':dbMock,'./summary-references':{},'../price-classification':{},'./city-market-alias':cityAlias,'./city-package-equivalence':cityPackage,'./product-detail-diagnostics':detailDiagnostics});
 math=load(path.join(server,'../comparison-math.ts'),{});
});
after(async()=>{await db?.end()});
const check=(name,fn)=>test(name,{skip:!enabled&&'Requires private local PostgreSQL socket'},fn);
async function oldQuotes(location,series,history){return(await db.query(`WITH quotes AS (${price.PRICE_QUOTES}) SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series) product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,market_id AS location_id,source_market_id,market_name AS location_name,region AS department,price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units FROM quotes WHERE ($1='' OR market_id=$1) AND series=$2 AND ${history==='all'?'observed_on<=CURRENT_DATE':WINDOW} ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,[location,series])).rows}
async function genericCity(ids,history){return(await db.query(`WITH quotes AS (${price.PRICE_QUOTE_VALUES})
  SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
    product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
    market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
    price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
  FROM quotes WHERE series='city' AND product_id=ANY($1::text[])
    AND ${history==='all'?'observed_on<=CURRENT_DATE':WINDOW}
  ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,[ids])).rows}
async function indexedCity(ids,history){return(await db.query(history==='all'?price.CITY_LOOSE_LATEST_QUOTES:price.CITY_RECENT_LOOSE_LATEST_QUOTES,[ids])).rows}
async function oldInputQuotes(location,history){
 const [department,municipality]=location==='__national__'?['','']:JSON.parse(location);
 return (await db.query(`SELECT DISTINCT ON(p.id,p.department,p.municipality)
   p.id,p.name,p.category,string_to_array(p.category,' > ') AS category_path,p.presentation,
   p.presentation AS units,'presentation'::text AS unit,'input-municipal'::text AS series,
   json_build_array(p.department,p.municipality)::text AS location_id,
   p.municipality || ', ' || p.department AS location_name,p.department,p.municipality,
   p.brand,p.registration,p.product_line,p.price,p.observed_on AS date,p.document_id,p.source_locator
   FROM published_input_municipal_price p
   WHERE ($1='' OR p.department=$1) AND ($2='' OR p.municipality=$2)
   AND ${history==='all'?'p.observed_on<=CURRENT_DATE':WINDOW.replaceAll('observed_on','p.observed_on')}
   ORDER BY p.id,p.department,p.municipality,p.observed_on DESC`,[department,municipality])).rows
   .map(q=>({...q,location_id:JSON.stringify(JSON.parse(q.location_id))}));
}
for(const history of ['recent','all'])check(`municipal comparison ${history} preserves exact packages, source winners, aliases and arithmetic`,async()=>{
 const a=JSON.stringify(['Departamento','A']);
 const base=await oldInputQuotes(a,history),other=await oldInputQuotes('__national__',history);
 const expected=math.compareQuotes(base,other,false,false,true);
 calls=[];
 const actual=await comparison()('inputs',{scope:'municipality',history,a,b:'__national__'});
 assert.deepEqual(sorted(actual.rows),sorted(expected));
 assert.deepEqual(normalize({matched:actual.matched,unmatched:actual.unmatched,percent:actual.percent,summaries:actual.summaries}),normalize(math.summarizeComparisons(expected)));
 assert.ok(!actual.rows.some(row=>row.a.id==='alias-legacy'));
 assert.equal(actual.rows.find(row=>row.a.id==='withdrawn-demo').a.price,100);
 assert.ok(actual.rows.some(row=>row.a.id==='urea-50'&&row.a.units==='50 kg'));
 assert.ok(actual.rows.some(row=>row.a.id==='urea-25'&&row.a.units==='25 kg'));
 assert.ok(calls.some(call=>call.sql.includes('FROM input_municipal_price p')));
 assert.ok(!calls.some(call=>call.sql.includes('SELECT DISTINCT ON(p.id,p.department,p.municipality)')&&call.sql.includes('FROM published_input_municipal_price p')&&!call.sql.includes('jsonb_to_recordset')));
});
for(const [series,history,dates,b] of [['city','recent','latest','__national__'],['city','all','same','__national__'],['city','recent','latest','b'],['monthly','all','same','__national__']])check(`${series}/${history}/${dates}/${b}: exact old-query values, classifications, counts and means`,async()=>{
 const base=await oldQuotes('a',series,history),other=await oldQuotes(b==='__national__'?'':b,series,history);
 const expected=math.compareQuotes(base,other,dates==='same',false,b==='__national__');
 calls=[];const result=await comparison()('markets',{a:'a',b,series,history,dates});
 assert.deepEqual(sorted(result.rows),sorted(expected));
 assert.deepEqual(normalize({matched:result.matched,unmatched:result.unmatched,percent:result.percent,summaries:result.summaries}),normalize(math.summarizeComparisons(expected)));
 const selections=calls.filter(c=>c.sql.includes('SELECT DISTINCT ON(product_id,market_id,presentation'));
 assert.ok(selections.every(c=>!c.sql.includes('LEFT JOIN regional_classification c ON')));
 const maxBatch=series==='city'?50:12;
 assert.ok(selections.slice(1).every(c=>c.args.at(-1)?.length>0&&c.args.at(-1).length<=maxBatch));
 if(series==='city'){
  if(history==='recent')assert.ok(selections.length>=2,'Recent reads retain bounded identity batches');
  assert.equal(result.rows.find(r=>r.a.id==='p1'&&r.a.units==='2.5 Kilogramo').a.price,2000);
  assert.deepEqual(normalize(result.rows.find(r=>r.a.source_locator==='revision').a.category_path),['Frutas','Cítricos corregidos']);
  assert.ok(result.unmatched>=2,'Single-location products stay unmatched, not zero-priced');
 }
});
check('prices-only preserves every base combination and avoids national scans',async()=>{
 const expected=await oldQuotes('a','city','all');calls=[];
 const result=await comparison()('markets',{a:'a',series:'city',history:'all',view:'prices'});
 assert.equal(result.rows.length,expected.length);assert.equal(result.unmatched,expected.length);
 assert.equal(calls.filter(c=>c.sql.includes('SELECT DISTINCT ON(product_id,market_id,presentation')).length,1);
});

for(const history of ['recent','all'])check(`municipal availability ${history} equals full retained dimensions, excluding future-only locations`,async()=>{
 const expected=(await db.query(`SELECT DISTINCT department,municipality FROM input_municipal_price WHERE ${history==='all'?'observed_on<=CURRENT_DATE':WINDOW} ORDER BY department,municipality`)).rows.map(r=>({id:JSON.stringify([r.department,r.municipality]),name:`${r.municipality}, ${r.department}`}));
 const result=await comparison()('inputs',{scope:'municipality',history,view:'prices'});
 assert.deepEqual(normalize(result.locations),expected);
 assert.equal(result.rows[0].a.location_name,'A, Departamento');
 assert.ok(result.locations.every(l=>!l.name.startsWith('C,')));
 assert.equal(result.locations.some(l=>l.name.startsWith('B,')),history==='all');
});

check('market picker excludes a location with only withdrawn monthly quotations',async()=>{
 const result=await comparison()('markets',{a:'a',series:'monthly',view:'prices'});
 assert.ok(!result.locations.some(location=>location.id==='review-only'));
 assert.ok(!result.locations.find(location=>location.id==='c').series.includes('monthly'));
 const baseline=(await db.query(`WITH quotes AS (${price.PRICE_QUOTES}) SELECT DISTINCT market_id FROM quotes WHERE ${WINDOW}`)).rows.map(row=>row.market_id).sort();
 assert.deepEqual(normalize(result.locations.map(row=>row.id).sort()),baseline);
});

check('recent city picker equals retained date-window markets without future-only or old-only names',async()=>{
 await db.query("INSERT INTO market VALUES('old-city','Old city','Old','Cinco'),('future-city','Future city','Future','Seis')");
 await db.query("INSERT INTO regional_price VALUES('p1','Producto1','Old city','Frutas',CURRENT_DATE-500,10,10,'package','Caja',1,'Kilogramo',1,'old','old-city',1),('p1','Producto1','Future city','Frutas',CURRENT_DATE+1,10,10,'package','Caja',1,'Kilogramo',1,'old','future-city',1)");
 calls=[];
 const recent=await comparison()('markets',{a:'a',series:'city',history:'recent',view:'prices'});
 const expected=(await db.query(`SELECT DISTINCT m.id FROM regional_price r JOIN market m ON m.name=r.market_name WHERE ${WINDOW}`)).rows.map(row=>row.id).sort();
 assert.deepEqual(normalize(recent.locations.filter(row=>row.series.includes('city')).map(row=>row.id).sort()),expected);
 assert.ok(calls.some(call=>call.sql.includes('WHERE EXISTS (SELECT 1 FROM published_regional_price r')));
 const all=await comparison()('markets',{a:'a',series:'city',history:'all',view:'prices'});
 assert.ok(all.locations.find(row=>row.id==='old-city')?.series.includes('city'));
 assert.ok(!all.locations.find(row=>row.id==='future-city')?.series.includes('city'));
});

check('fresh latest-location pointers preserve municipal comparison parity',async()=>{
 await db.query(`INSERT INTO input_municipal_latest_raw
   SELECT DISTINCT ON(id,department,municipality) id,department,municipality,observed_on,price
   FROM input_municipal_price WHERE observed_on<=CURRENT_DATE
   ORDER BY id,department,municipality,observed_on DESC,price`);
 await db.query("UPDATE input_latest_projection_state SET projection_epoch=source_epoch,asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date WHERE scope='municipality'");
 for(const history of ['recent','all']){
   const a=JSON.stringify(['Departamento','A']);
   const expected=math.compareQuotes(await oldInputQuotes(a,history),
     await oldInputQuotes('__national__',history),false,false,true);
   calls=[];
   const actual=await comparison()('inputs',{scope:'municipality',history,a,b:'__national__'});
   assert.deepEqual(sorted(actual.rows),sorted(expected));
   assert.ok(calls.some(call=>call.sql.includes('FROM input_municipal_latest_raw l')));
 }
 await db.query("UPDATE input_latest_projection_state SET source_epoch=source_epoch+1 WHERE scope='municipality'");
 calls=[];
 await comparison()('inputs',{scope:'municipality',history:'all',a:JSON.stringify(['Departamento','A']),b:'__national__'});
 assert.ok(calls.some(call=>call.sql.includes('SELECT DISTINCT ON(p.id,p.department,p.municipality)')&&call.sql.includes('FROM input_municipal_price p')));
});

check('recent city comparison retains over 100 exact source-backed identities in bounded national batches',async()=>{
 await db.query(`INSERT INTO product SELECT 'wide-'||n,'Wide '||n,'Frutas' FROM generate_series(1,105)n;
 INSERT INTO regional_price SELECT 'wide-'||n,'Wide '||n,m.name,'Frutas',CURRENT_DATE-1,
   100+n,100+n,'package','Caja',2.5,'Kilogramo',1,'old',
   'wide-'||n||'-'||m.id,1 FROM generate_series(1,105)n
   CROSS JOIN market m WHERE m.id IN ('a','b')`);
 const base=await oldQuotes('a','city','recent'),other=await oldQuotes('','city','recent');
 const expected=math.compareQuotes(base,other,false,false,true);
 calls=[];
 const actual=await comparison()('markets',{a:'a',series:'city',history:'recent'});
 assert.deepEqual(sorted(actual.rows),sorted(expected));
 const batches=calls.filter(call=>call.sql.includes('SELECT DISTINCT ON(product_id,market_id,presentation'))
   .filter(call=>Array.isArray(call.args.at(-1)));
 assert.equal(batches.length,3);
 assert.deepEqual(batches.map(call=>call.args.at(-1).length),[50,50,21]);
});

check('recent indexed city seek matches generic full quote tuples and arithmetic across corrections, packages and date limits',async()=>{
 await db.query(`INSERT INTO regional_price VALUES
   ('p1','Producto1','B','Frutas',CURRENT_DATE-1,311,333,'package','Caja',2.5,'Kilogramo',2,'new','corrected-row',1),
   ('p2','Producto2','B','Frutas',CURRENT_DATE-400,444,466,'package','Caja',2.5,'Kilogramo',1,'old','old-only-p2',1),
   ('p2','Producto2','B','Frutas',CURRENT_DATE+1,99999,99999,'package','Caja',2.5,'Kilogramo',3,'new','future-p2',1);
 INSERT INTO regional_price_product_correction VALUES('new','corrected-row','p2','Producto2 corregido')`);
 const ids=['p1','p2'];
 const generic=await genericCity(ids,'recent');
 const indexed=await indexedCity(ids,'recent');
 assert.deepEqual(byCityIdentity(indexed),byCityIdentity(generic),
   'full price, range, date, package, original and source locator must match');
 assert.ok(indexed.some(row=>row.id==='p2'&&row.source_locator==='corrected-row'));
 assert.ok(indexed.some(row=>row.id==='p1'&&row.units==='12.5 Kilogramo'));
 assert.ok(!indexed.some(row=>['old-only-p2','future-p2'].includes(row.source_locator)));
 const base=await oldQuotes('a','city','recent');
 assert.deepEqual(normalize(math.compareQuotes(base,indexed,false,true,true)),
   normalize(math.compareQuotes(base,generic,false,true,true)));
});

check('exact twelve-month cutoff and day-after, future exclusion, and same-date revision ties retain full tuples in both scopes',async()=>{
 await db.query('BEGIN');
 try {
  await db.query(`INSERT INTO regional_price VALUES
    ('p3','Producto3','A','Frutas',(CURRENT_DATE-INTERVAL '12 months')::date,10,12,'package','Bolsa',1,'Kilogramo',1,'old','boundary-old',1),
    ('p4','Producto4','A','Frutas',(CURRENT_DATE-INTERVAL '12 months')::date+1,20,22,'package','Bolsa',1,'Kilogramo',1,'old','boundary-in',1),
    ('p5','Producto5','B','Frutas',CURRENT_DATE-1,30,32,'package','Caja',2.5,'Kilogramo',2,'old','same-day-old-doc',1),
    ('p5','Producto5','B','Frutas',CURRENT_DATE-1,40,42,'package','Caja',2.5,'Kilogramo',2,'new','same-day-new-doc',1),
    ('p6','Producto6','B','Frutas',CURRENT_DATE+1,9999,9999,'package','Bolsa',1,'Kilogramo',3,'new','future-only',1)`);
  const ids=['p3','p4','p5','p6'];
  for(const history of ['recent','all']){
   const generic=await genericCity(ids,history),indexed=await indexedCity(ids,history);
   assert.deepEqual(byCityIdentity(indexed),byCityIdentity(generic),history+' full tuple parity');
   assert.ok(indexed.some(row=>row.source_locator==='boundary-in'));
   assert.ok(indexed.some(row=>row.source_locator==='same-day-new-doc'));
   assert.ok(!indexed.some(row=>['same-day-old-doc','future-only'].includes(row.source_locator)));
   assert.equal(indexed.some(row=>row.source_locator==='boundary-old'),history==='all');
  }
 } finally {await db.query('ROLLBACK')}
});

check('case and surrounding whitespace variants keep the same normalized package winner and original',async()=>{
 await db.query('BEGIN');
 try {
  await db.query(`INSERT INTO regional_price VALUES
    ('p7','Producto7','B','Frutas',CURRENT_DATE-1,101,103,'package','Caja',2.5,'Kilogramo',1,'old','case-lower',1),
    ('p7','Producto7','B','Frutas',CURRENT_DATE-1,111,113,'package',' caja ',2.5,' KILOGRAMO ',2,'new','case-upper',1),
    ('p7','Producto7','C','Frutas',CURRENT_DATE-3,121,123,'package','CAJA',12.5,'Kilogramo',1,'old','other-package',1)`);
  for(const history of ['recent','all']){
   const generic=await genericCity(['p7'],history),indexed=await indexedCity(['p7'],history);
   assert.deepEqual(byCityIdentity(indexed),byCityIdentity(generic),history+' full tuple parity');
   assert.ok(indexed.some(row=>row.source_locator==='case-upper'));
   assert.ok(indexed.some(row=>row.source_locator==='other-package'));
   assert.ok(!indexed.some(row=>row.source_locator==='case-lower'));
  }
 } finally {await db.query('ROLLBACK')}
});

check('legacy inconsistent unit dimension is tested against generic dated winner rather than assumed equivalent',async()=>{
 await db.query('BEGIN');
 try {
  await db.query(`INSERT INTO regional_price VALUES
    ('p8','Producto8','A','Frutas',CURRENT_DATE-2,100,100,'package','Bulto',24,'Kilogramo',1,'old','legacy-package-older',1),
    ('p8','Producto8','A','Frutas',CURRENT_DATE-1,200,200,'kg','Bulto',24,'Kilogramo',1,'old','legacy-kg-loser',1),
    ('p8','Producto8','A','Frutas',CURRENT_DATE-1,300,300,'package','Bulto',24,'Kilogramo',2,'new','legacy-package-winner',1),
    ('p9','Producto9','B','Frutas',CURRENT_DATE-3,400,400,'kg','Bulto',24,'Kilogramo',1,'old','legacy-kg-prior-date',1),
    ('p9','Producto9','B','Frutas',CURRENT_DATE-1,500,500,'kg','Bulto',24,'Kilogramo',1,'old','legacy-kg-same-round',1),
    ('p9','Producto9','B','Frutas',CURRENT_DATE-1,600,600,'package','Bulto',24,'Kilogramo',1,'new','legacy-package-newer-doc',1)`);
  for(const history of ['recent','all']){
   const generic=await genericCity(['p8','p9'],history),indexed=await indexedCity(['p8','p9'],history);
   assert.ok(!indexed.some(row=>row.source_locator==='legacy-kg-prior-date'),
     'raw indexed path alone demonstrates the legacy-unit counterexample');
   assert.ok(generic.some(row=>row.source_locator==='legacy-kg-prior-date'));
   const base=(await oldQuotes('b','city',history)).filter(row=>row.id==='p9');
   const expected=math.compareQuotes(base,generic.filter(row=>row.id==='p9'),false,true,true);
   calls=[];
   const actual=await comparison()('markets',{a:'b',b:'__national__',series:'city',history,product:'p9',sources:'true'});
   assert.deepEqual(sorted(actual.rows),sorted(expected),history+' guarded public full tuples');
   assert.deepEqual(normalize({matched:actual.matched,unmatched:actual.unmatched,percent:actual.percent,summaries:actual.summaries}),
    normalize(math.summarizeComparisons(expected)),history+' guarded public arithmetic');
   assert.ok(actual.rows.some(row=>row.a.source_locator==='legacy-kg-prior-date'));
   assert.ok(calls.some(call=>call.sql.includes('CITY_LOOSE_UNIT_AMBIGUITY')||call.sql.includes('WITH selected(product_id,document_id,source_locator)')));
   assert.ok(calls.some(call=>call.sql.includes('FROM quotes WHERE observed_on')&&call.args?.[0]?.includes('p9')),
     'only the ambiguous product falls back to the generic dated query');
  }
 } finally {await db.query('ROLLBACK')}
});

check('verified department aliases preserve historic bookmarks and one current location per national input mean',async()=>{
 await db.query('BEGIN');
 try {
  await db.query(`INSERT INTO input_municipal_price VALUES
   ('wuxal-alias','Wuxal','Fertilizantes','1 litro','Quindio','Armenia',100,CURRENT_DATE-500,'old','PDF page 34,col 2,y 691.3','','',''),
   ('wuxal-alias','Wuxal','Fertilizantes','1 litro','Quindío','Armenia',120,CURRENT_DATE-1,'new','1.2!row 1470','','',''),
   ('wuxal-alias','Wuxal','Fertilizantes','1 litro','Quindío','Calarcá',180,CURRENT_DATE-1,'new','1.2!row 1471','','',''),
   ('wuxal-alias','Wuxal','Fertilizantes','1 litro','Quindío','Armenia',999,CURRENT_DATE+1,'new','future','','','')`);
  await db.query("UPDATE input_latest_projection_state SET projection_epoch=-1 WHERE scope='municipality'");
  for(const a of ['[\"Quindio\",\"Armenia\"]','[\"QUINDÍO\",\"Armenia\"]']) {
   calls=[];
   const result=await comparison()('inputs',{scope:'municipality',history:'all',a,
    b:'__national__',product:'wuxal-alias',sources:'true'});
   assert.equal(result.filters.a,'[\"Quindío\",\"Armenia\"]');
   assert.equal(result.locations.filter(l=>l.name==='Armenia, Quindío').length,1);
   assert.equal(result.rows.length,1);
   const row=result.rows[0];
   assert.equal(row.a.price,120);
   assert.equal(row.a.document_id,'new');
   assert.equal(row.a.source_locator,'1.2!row 1470');
   assert.equal(row.b.price,150,'Independent oracle mean=(120+180)/2; retained old alias is not a third location');
   assert.equal(row.b.location_count,2);
   assert.equal(row.percent,25);
   assert.deepEqual(normalize(row.b.sources.map(q=>q.price).sort((x,y)=>x-y)),[120,180]);
   assert.ok(calls.some(c=>c.sql.includes('p.department=ANY($1::text[])')&&c.args[0].includes('Quindio')));
  }
  const retained=(await db.query("SELECT department,price FROM input_municipal_price WHERE id='wuxal-alias' ORDER BY observed_on")).rows;
  assert.equal(retained.length,4);
  assert.equal(retained[0].department,'Quindio');assert.equal(retained[0].price,100);
 } finally { await db.query('ROLLBACK'); }
});

check('case-only municipal spellings share one picker, indexed history aliases and national constituent',async()=>{
 await db.query('BEGIN');
 try {
  await db.query(`INSERT INTO input_municipal_price VALUES
   ('wuxal-case','Wuxal Tapa Negra','Fertilizantes','1 litro','Risaralda','Belén De Umbría',100,CURRENT_DATE-500,'old','PDF page 20,col 1,y 158.3','','',''),
   ('wuxal-case','Wuxal Tapa Negra','Fertilizantes','1 litro','Risaralda','Belén de Umbría',120,CURRENT_DATE-1,'new','1.2!row 1470','','',''),
   ('wuxal-case','Wuxal Tapa Negra','Fertilizantes','1 litro','Risaralda','Santa Rosa de Cabal',180,CURRENT_DATE-1,'new','1.2!row 1471','','',''),
   ('other-product','Other','Fertilizantes','1 litro','Risaralda','Belén De Umbría',900,CURRENT_DATE-1,'new','other!row 1','','','')`);
  await db.query("UPDATE input_latest_projection_state SET projection_epoch=-1 WHERE scope='municipality'");
  calls=[];
  const actual=await comparison()('inputs',{scope:'municipality',history:'all',
   a:JSON.stringify(['Risaralda','Belén De Umbría']),b:'__national__',
   product:'wuxal-case',sources:'true'});
  assert.equal(actual.filters.a,JSON.stringify(['Risaralda','Belén de Umbría']));
  assert.equal(actual.locations.filter(x=>x.id===actual.filters.a).length,1);
  assert.equal(actual.rows.length,1);
  assert.equal(actual.rows[0].a.price,120);
  assert.equal(actual.rows[0].b.price,150);
  assert.equal(actual.rows[0].b.location_count,2);
  assert.deepEqual(normalize(actual.rows[0].b.sources.map(x=>x.price).sort((a,b)=>a-b)),[120,180]);
  assert.ok(calls.some(c=>c.sql.includes('p.municipality=ANY($2::text[])') &&
   c.args[1].includes('Belén De Umbría') && c.args[1].includes('Belén de Umbría')));
  assert.equal((await db.query("SELECT count(*) n FROM input_municipal_price WHERE id='wuxal-case'")).rows[0].n,'3');
 } finally {await db.query('ROLLBACK');}
});
check('Corabastos saved city aliases compare as one physical market without changing monthly IDs',async()=>{
 await db.query('BEGIN');
 try {
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
  for(let i=0;i<3;i++) await db.query('INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
   [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  await db.query("INSERT INTO product VALUES('p17','Mandarina Arrayana','Frutas')");
  for(let i=0;i<3;i++) await db.query(`INSERT INTO regional_price VALUES
   ('p17','Mandarina Arrayana',$1,'Frutas',CURRENT_DATE-3+$2::integer,$3::numeric,$3::numeric,
    'package','Canastilla',22,'Kilogramo',2,'old',$4,1)`,[names[i],i,100+i*100,'alias-'+i]);
  await db.query(`INSERT INTO regional_price VALUES
   ('p17','Mandarina Arrayana','B','Frutas',CURRENT_DATE-1,900,900,
    'package','Canastilla',22,'Kilogramo',2,'old','other-market',1)`);
  const indexed=await indexedCity(['p17'],'all');
  assert.equal(indexed.length,2);
  assert.equal(indexed.find(x=>x.location_id===ids[2]).price,300);
  const city=await comparison()('markets',{a:ids[0],b:'__national__',series:'city',history:'all',product:'p17',sources:'true'});
  assert.equal(city.filters.a,ids[2]);
  assert.equal(city.locations.filter(x=>x.id===ids[2]).length,1);
  assert.equal(city.rows.length,1);
  assert.equal(city.rows[0].a.price,300);
  assert.equal(city.rows[0].a.source_market_id,ids[2]);
  assert.equal(city.rows[0].b.price,600);
  assert.equal(city.rows[0].b.location_count,2);
  assert.equal(city.rows[0].b.sources.find(x=>x.location_id===ids[2]).source_locator,'alias-2');
  assert.equal(city.rows[0].b.sources.find(x=>x.location_id===ids[2]).source_market_id,ids[2]);
  await db.query(`INSERT INTO price_observation VALUES('p17',$1,'dane-sipsa',CURRENT_DATE-1,777,777,777,
    'kg','old','monthly-alias','url','monthly')`,[ids[0]]);
  const monthly=await comparison()('markets',{a:ids[0],series:'monthly',history:'all',product:'p17'});
  assert.equal(monthly.filters.a,ids[0]);
  assert.equal(monthly.rows[0].a.price,777);
  await db.query(`INSERT INTO regional_price VALUES
   ('p17','Mandarina Arrayana',$1,'Frutas',CURRENT_DATE-1,999,999,
    'package','Canastilla',22,'Kilogramo',2,'old','alias-conflict',1)`,[names[0]]);
  const conflicted=await comparison()('markets',{a:ids[0],series:'city',history:'all',product:'p17'});
  assert.equal(conflicted.rows[0].a.price,200,'different-date alias history remains eligible');
  assert.equal((await db.query(`SELECT count(*)::integer n FROM regional_price WHERE product_id='p17'`)).rows[0].n,5);
 } finally {await db.query('ROLLBACK')}
});
check('2022 native grave-accent Corabastos quote joins only the canonical city comparison',async()=>{
 await db.query('BEGIN');
 try {
  const canonical='sipsa-bogota-d-c-corabastos';
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`,[canonical]);
  await db.query("INSERT INTO product VALUES('naranja-sweet','Naranja Sweet','Frutas')");
  await db.query(`INSERT INTO regional_price VALUES
    ('naranja-sweet','Naranja Sweet','Bogotà, Corabastos','Frutas','2022-01-03',26000,28000,
     'package','Canastilla',20,'Kilogramo',2,'old','native-2022-r2',1)`);
  const indexed=await indexedCity(['naranja-sweet'],'all');
  assert.equal(indexed.length,1);
  assert.equal(indexed[0].location_id,canonical);
  assert.equal(indexed[0].source_market_id,null);
  assert.equal(indexed[0].location_name,'Bogotà, Corabastos');
  assert.equal(indexed[0].price,27000);
  const city=await comparison()('markets',{a:canonical,series:'city',history:'all',product:'naranja-sweet',sources:'true'});
  assert.equal(city.rows.length,1);
  assert.equal(city.rows[0].a.price,27000);
  assert.equal(city.rows[0].a.source_market_id,null);
  assert.equal(city.rows[0].a.location_name,'Bogotà, Corabastos');
  await db.query(`INSERT INTO price_observation VALUES('naranja-sweet',$1,'dane-sipsa','2022-01-31',777,777,777,
    'kg','old','monthly-2022','url','monthly')`,[canonical]);
  const monthly=await comparison()('markets',{a:canonical,series:'monthly',history:'all',product:'naranja-sweet'});
  assert.equal(monthly.rows[0].a.price,777);
  assert.equal(monthly.rows[0].a.source_market_id,canonical);
  assert.equal((await db.query("SELECT count(*) n FROM market WHERE name='Bogotà, Corabastos'")).rows[0].n,'0');
 } finally { await db.query('ROLLBACK'); }
});

check('recent Corabastos overview preserves every eligible tuple and older fallback across alias conflicts',async()=>{
 await db.query('BEGIN');
 try {
  const canonical=cityAlias.CORABASTOS_CITY_MARKET_ID;
  const names=['Bogotá, Corabastos','Bogotá, D.C., Corabastos'];
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
   ('dane-city-bogota-corabastos',$1,'Bogotá','Bogotá, D.C.','11001'),
   ($2,$3,'Bogotá','Bogotá, D.C.','11001')`,[names[0],canonical,names[1]]);
  await db.query("INSERT INTO product VALUES('p17','Producto17','Frutas'),('p18','Producto18','Frutas')");
  async function pair({price=100,category='Cítricos',product='p17',quantity=20,round=1,
   presentation='Bulto',sourceUnit='Kilogramo',dateOffset=1}={}) {
   await db.query("DELETE FROM regional_classification WHERE source_locator LIKE 'overview-%'");
   await db.query("DELETE FROM regional_price_product_correction WHERE source_locator LIKE 'overview-%'");
   await db.query("DELETE FROM regional_price WHERE source_locator LIKE 'overview-%'");
   await db.query(`INSERT INTO regional_price VALUES
    ('p17','Producto17',$1,'Frutas',CURRENT_DATE-3,50,70,'package','Bulto',20,'Kilogramo',1,'old','overview-older',1),
    ('p17','Producto17',$1,'Frutas',CURRENT_DATE-1,100,120,'package','Bulto',20,'Kilogramo',1,'old','overview-a',1),
    ($2,'Producto17',$3,'Frutas',CURRENT_DATE-$4::integer,$5,120,'package',$6,$7,$8,$9,'old','overview-b',1)`,
    [names[0],product,names[1],dateOffset,price,presentation,quantity,sourceUnit,round]);
   await db.query(`INSERT INTO regional_classification VALUES
    ('old','overview-a',ARRAY['Frutas','Cítricos']),('old','overview-b',ARRAY['Frutas',$1])`,[category]);
  }
  async function parity(message,request={}) {
   const history=request.history||'recent';
   const expected=(await oldQuotes(canonical,'city',history)).filter(q=>!request.product||q.id===request.product);
   calls=[];
   const actual=await comparison()('markets',{a:canonical,series:'city',history,view:'prices',...request});
   assert.deepEqual(byCityIdentity(actual.rows.map(row=>row.a)),byCityIdentity(expected),message);
   if(history==='all'&&!request.product) {
    assert.ok(calls.some(call=>call.sql==='CORABASTOS_ALL_HISTORY_READER'),
      message+' enters the isolated all-history reader');
   } else {
    const selection=calls.find(call=>call.sql.includes('SELECT DISTINCT ON(product_id,market_id,presentation'));
    assert.ok(selection,message+' executes the actual public quote path');
    assert.equal(selection.sql.includes('city_alias_witnesses AS MATERIALIZED'),
      history==='recent'&&!request.product,message+' only recent unfiltered overview opts in');
   }
   return actual.rows.map(row=>row.a);
  }
  await pair();let rows=await parity('identical witnesses');assert.equal(rows[0].price,110);
  for(const dimensions of [{price:101},{category:'Otras frutas'},
   {price:101,presentation:' bUlTo ',sourceUnit:' kIlOgRaMo '}]) {
   await pair(dimensions);rows=await parity(JSON.stringify(dimensions));
   assert.equal(rows[0].source_locator,'overview-older','rejected latest date must retain the older eligible quote');
   assert.equal(rows[0].price,60);
  }
  for(const dimensions of [{price:101,quantity:30},{price:101,round:2},
   {price:101,presentation:'Canastilla'},{price:101,sourceUnit:'Gramo'},
   {price:101,dateOffset:2}]) {
   await pair(dimensions);await parity(JSON.stringify(dimensions));
  }
  await pair({product:'p18',price:101});rows=await parity('distinct raw identities');assert.equal(rows.length,2);
  await db.query("INSERT INTO regional_price_product_correction VALUES('old','overview-b','p17','Producto17')");
  rows=await parity('corrected shared identity');assert.equal(rows.length,1);assert.equal(rows[0].price,60);
  await parity('all-history enters the isolated source-safe reader',{history:'all'});
  await parity('product selection retains the original scoped path',{product:'p17'});
  assert.equal((await db.query("SELECT count(*) n FROM regional_price WHERE source_locator LIKE 'overview-%'")).rows[0].n,'3');
 } finally {await db.query('ROLLBACK')}
});

check('indexed market availability keeps all published aliases and never offers a synthetic raw-grave market',async()=>{
 await db.query('BEGIN');
 try {
  const canonical=cityAlias.CORABASTOS_CITY_MARKET_ID;
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
   ($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
   ('grave-market','Bogotà, Corabastos','Unverified','Unverified','99999')`,[canonical]);
  await db.query(`INSERT INTO regional_price VALUES
   ('p1','Producto1','Bogotà, Corabastos','Frutas',CURRENT_DATE-1,100,120,'package','Caja',20,'Kilogramo',1,'old','picker-grave',1)`);
  for(const history of ['recent','all']) {
   const period=history==='all'?'observed_on<=CURRENT_DATE':WINDOW;
   const expected=(await db.query(`SELECT DISTINCT ${cityAlias.cityMarketIdSql()} AS id,
    ${cityAlias.cityMarketNameSql()} AS name FROM market m
    WHERE EXISTS(SELECT 1 FROM published_regional_price r
      WHERE ${cityAlias.cityMarketJoinSql()} AND ${period}) ORDER BY name`)).rows;
   const actual=await comparison()('markets',{a:canonical,series:'city',history,view:'prices'});
   const locations=actual.locations.filter(row=>row.series.includes('city')).map(({id,name})=>({id,name}));
   assert.deepEqual(normalize(locations),normalize(expected),history+' exact original market-name joins');
   assert.ok(locations.some(row=>row.id===canonical));
   assert.ok(!locations.some(row=>row.id==='grave-market'));
   assert.equal(actual.rows[0].a.source_market_id,null);
   assert.equal(actual.rows[0].a.price,110);
  }
  await db.query("INSERT INTO city_pdf_publication_conflict VALUES('old')");
  const held=await comparison()('markets',{a:canonical,series:'city',history:'all',view:'prices'});
  assert.ok(!held.locations.some(row=>row.id===canonical||row.id==='grave-market'),
   'indexed seek retains authoritative document publication gate');
 } finally {await db.query('ROLLBACK')}
});

check('strict Wuxal comparison unites both IDs and refuses a same-date conflicting price',async()=>{
 await db.query('BEGIN');
 try {
  const oldId='wuxal-16-16-12-tapa-negra-1-litro';
  const newId='wuxal-tapa-negra-16-16-12-1-litro';
  const location=JSON.stringify(['Quindío','Armenia']);
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES('quindio-armenia','Armenia','Armenia','Quindío','63001')`);
  await db.query(`INSERT INTO source_document(id,source_url,retrieved_at) VALUES
    ('wuxal-old','https://example.test/wuxal-old','2026-01-01'),
    ('wuxal-new','https://example.test/wuxal-new','2026-02-01')`);
  await db.query(`INSERT INTO input_municipal_price VALUES
    ($1,'Wuxal 16-16-12 tapa negra','Fertilizantes y enmiendas','1 litro','Quindío','Armenia',29175,'2013-03-31','wuxal-old','old!PDF page 13','','',''),
    ($2,'Wuxal tapa negra 16-16-12','Fertilizantes y enmiendas','1 Litro','Quindío','Armenia',29317,'2014-04-30','wuxal-new','new!PDF page 13','','','')`,[oldId,newId]);
  await db.query(`INSERT INTO input_municipal_latest_raw VALUES
    ($1,'Quindío','Armenia','2013-03-31',29175),
    ($2,'Quindío','Armenia','2014-04-30',29317)`,[oldId,newId]);
  calls=[];
  const result=await comparison()('inputs',{scope:'municipality',history:'all',a:location,
    b:'__national__',product:newId,dates:'latest'});
  assert.equal(result.rows.length,1);
  assert.equal(result.rows[0].a.id,newId);
  assert.equal(result.rows[0].a.price,29317);
  assert.equal(result.rows[0].a.source_input_id,newId);
  assert.equal(result.rows[0].a.source_name,'Wuxal tapa negra 16-16-12');
  assert.ok(calls.some(call=>call.sql.includes('cardinality($3::text[])=0 OR p.id=ANY($3)') &&
    call.args[2].includes(oldId) && call.args[2].includes(newId)),
    'selected legacy/canonical product filter binds the exact group members');
  assert.ok(calls.some(call=>call.sql.includes('p.id=ANY($4)') &&
    call.args[3]?.includes(oldId) && call.args[3]?.includes(newId)),
    'comparison reference read expands a canonical catalog ID to both retained IDs');

  await db.query(`INSERT INTO input_municipal_price VALUES
    ($1,'Wuxal 16-16-12 tapa negra','Fertilizantes y enmiendas','1 litro','Quindío','Armenia',30025,'2014-04-30','wuxal-old','old!PDF page 14','','','')`,[oldId]);
  await db.query(`INSERT INTO input_municipal_latest_raw VALUES
    ($1,'Quindío','Armenia','2014-04-30',30025)`,[oldId]);
  await assert.rejects(
    comparison()('inputs',{scope:'municipality',history:'all',a:location,
      b:'__national__',product:newId,dates:'same'}),
    inputIdentityEquivalence.InputIdentityConflictError,
  );
  await db.query(`INSERT INTO input_municipal_price VALUES
    ($1,'Wuxal 15-15-15','Otra categoría','5 litros','Quindío','Armenia',1,'2015-04-30','wuxal-poison','poison!PDF page 99','Marca distinta','ICA-77','Línea distinta')`,[oldId]);
  await db.query(`INSERT INTO input_municipal_latest_raw VALUES
    ($1,'Quindío','Armenia','2015-04-30',1)`,[oldId]);
  await assert.rejects(
    comparison()('inputs',{scope:'municipality',history:'all',a:location,
      b:'__national__',product:newId,dates:'latest'}),
    inputIdentityEquivalence.InputIdentityGuardError,
    'a member ID with different formulation or metadata cannot enter canonical comparison output',
  );
  const retainedPoison = (await db.query(`SELECT name,category,presentation,brand,registration,product_line,price
    FROM input_municipal_price WHERE id=$1 AND document_id='wuxal-poison'`,[oldId])).rows[0];
  assert.deepEqual(retainedPoison,{name:'Wuxal 15-15-15',category:'Otra categoría',presentation:'5 litros',
    brand:'Marca distinta',registration:'ICA-77',product_line:'Línea distinta',price:1});
 } finally {await db.query('ROLLBACK')}
});
