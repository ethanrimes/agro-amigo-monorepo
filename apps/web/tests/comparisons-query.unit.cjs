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
const dbMock={WINDOW,database:()=>({query:async(sql,args)=>{calls.push({sql,args});return db.query(sql,args);}})};
function comparison(){return load(path.join(server,'comparisons.ts'),{'./db':dbMock,'./price-quotes':price,'./input-identities':{reconcileInputCatalog:async rows=>rows},'../comparison-math':math}).comparison;}
const normalize=x=>JSON.parse(JSON.stringify(x));
const sorted=rows=>normalize(rows).sort((a,b)=>a.a.id.localeCompare(b.a.id)||a.a.units.localeCompare(b.a.units));
before(async()=>{
 if(!enabled)return;
 db=new Client({host:socket,port:65449,database:'postgres'});await db.connect();
 await db.query("SET search_path=pg_temp; SET statement_timeout='8s'");
 await db.query(`CREATE TEMP TABLE market(id text,name text,city text,region text);
 CREATE TEMP TABLE product(id text,name text,category text);
 CREATE TEMP TABLE source_document(id text,source_url text,retrieved_at timestamptz);
 CREATE TEMP TABLE price_observation(product_id text,market_id text,source_id text,observed_on date,price numeric,min_price numeric,max_price numeric,unit text,document_id text,source_locator text,source_url text,period text);
 CREATE TEMP VIEW published_price_observation AS SELECT * FROM price_observation WHERE source_locator!='withdrawn';
 CREATE TEMP TABLE regional_price(product_id text,product_name text,market_name text,category text,observed_on date,min_price numeric,max_price numeric,unit text,presentation text,quantity numeric,source_unit text,round integer,document_id text,source_locator text,source_page integer);
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
 CREATE TEMP TABLE input_municipal_price(id text,name text,category text,presentation text,department text,municipality text,price numeric,observed_on date,document_id text,source_locator text,brand text,registration text,product_line text);
 CREATE TEMP VIEW published_input_municipal_price AS SELECT * FROM input_municipal_price;
 CREATE INDEX input_municipal_location_options ON input_municipal_price(department,municipality,observed_on DESC);
 INSERT INTO input_municipal_price SELECT 'input','Insumo','Agrícola','1 litro','Departamento',l.municipality,100,CURRENT_DATE+l.day,'old','row','','','' FROM (VALUES('A',-1),('A',-500),('A',1),('B',-500),('C',1),('D',-1),('D',-2))l(municipality,day);

 INSERT INTO market VALUES('a','A','A','Uno'),('b','B','B','Dos'),('c','C','C','Tres'),('review-only','Only withdrawn','D','Cuatro');
 INSERT INTO source_document VALUES('old','old','2026-01-01'),('new','new','2026-02-01');
 INSERT INTO product SELECT 'p'||n,'Producto'||n,'Frutas' FROM generate_series(1,16)n;
 INSERT INTO regional_price SELECT 'p'||n,'Producto'||n,m.name,'Frutas',CURRENT_DATE-1,100+n,100+n,'package','Caja',2.5,'Kilogramo',1,'old','base-'||n||'-'||m.id,1 FROM generate_series(1,16)n CROSS JOIN market m WHERE m.id='a' OR (n<15 AND m.id='b') OR(n<14 AND m.id='c');
 INSERT INTO regional_price VALUES('p1','Producto1','A','Frutas',CURRENT_DATE-1,1000,1000,'package','Caja',2.5,'Kilogramo',2,'old','round2',1),('p1','Producto1','A','Frutas',CURRENT_DATE-1,2000,2000,'package','Caja',2.5,'Kilogramo',2,'new','revision',2),('p1','Producto1','A','Frutas',CURRENT_DATE-1,8000,8000,'package','Caja',12.5,'Kilogramo',1,'old','large-a',1),('p1','Producto1','B','Frutas',CURRENT_DATE-2,9000,9000,'package','Caja',12.5,'Kilogramo',1,'old','large-b',1),('p2','Producto2','A','Frutas',CURRENT_DATE-500,50,50,'package','Bolsa',1,'Kilogramo',1,'old','historic',1),('p1','Producto1','C','Frutas',CURRENT_DATE+1,99999,99999,'package','Caja',2.5,'Kilogramo',1,'old','future',1);
 INSERT INTO regional_classification VALUES('new','revision',ARRAY['Frutas','Cítricos corregidos']);
 INSERT INTO price_observation VALUES('p1','a','dane-sipsa',CURRENT_DATE-3,5,5,5,'kg','old','monthly','url','monthly'),('p1','b','dane-sipsa',CURRENT_DATE-3,6,6,6,'kg','old','monthly','url','monthly'),('p1','a','dane-sipsa',CURRENT_DATE-1,999,999,999,'kg','new','withdrawn','url','monthly'),('p1','review-only','dane-sipsa',CURRENT_DATE-1,777,777,777,'kg','new','withdrawn','url','monthly');`);
 price=load(path.join(server,'price-quotes.ts'),{'./db':dbMock,'./summary-references':{},'../price-classification':{}});
 math=load(path.join(server,'../comparison-math.ts'),{});
});
after(async()=>{await db?.end()});
const check=(name,fn)=>test(name,{skip:!enabled&&'Requires private local PostgreSQL socket'},fn);
async function oldQuotes(location,series,history){return(await db.query(`WITH quotes AS (${price.PRICE_QUOTES}) SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series) product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,market_id AS location_id,market_name AS location_name,region AS department,price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page FROM quotes WHERE ($1='' OR market_id=$1) AND series=$2 AND ${history==='all'?'observed_on<=CURRENT_DATE':WINDOW} ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,[location,series])).rows}
for(const [series,history,dates,b] of [['city','recent','latest','__national__'],['city','all','same','__national__'],['city','recent','latest','b'],['monthly','all','same','__national__']])check(`${series}/${history}/${dates}/${b}: exact old-query values, classifications, counts and means`,async()=>{
 const base=await oldQuotes('a',series,history),other=await oldQuotes(b==='__national__'?'':b,series,history);
 const expected=math.compareQuotes(base,other,dates==='same',false,b==='__national__');
 calls=[];const result=await comparison()('markets',{a:'a',b,series,history,dates});
 assert.deepEqual(sorted(result.rows),sorted(expected));
 assert.deepEqual(normalize({matched:result.matched,unmatched:result.unmatched,percent:result.percent,summaries:result.summaries}),normalize(math.summarizeComparisons(expected)));
 const selections=calls.filter(c=>c.sql.includes('SELECT DISTINCT ON(product_id,market_id,presentation'));
 assert.ok(selections.every(c=>!c.sql.includes('LEFT JOIN regional_classification')));
 assert.ok(selections.slice(1).every(c=>c.args[3]?.length>0&&c.args[3].length<=12));
 if(series==='city'){
  assert.ok(selections.length>=3,'More than12 identities require multiple bounded batches');
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
 const baseline=(await db.query(`WITH quotes AS (${price.PRICE_QUOTES}) SELECT DISTINCT market_id FROM quotes WHERE ${WINDOW}`)).rows.map(row=>row.market_id).sort();
 assert.deepEqual(normalize(result.locations.map(row=>row.id).sort()),baseline);
});
