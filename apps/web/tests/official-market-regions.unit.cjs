const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Client } = require('pg');
const ts = require('typescript'), fs = require('node:fs'), path = require('node:path');
const dsn=process.env.AGRO_INPUT_QUERY_TEST_DATABASE;
function load(relative,mocks={}) { const api={};new Function('exports','require',
 ts.transpileModule(fs.readFileSync(path.join(__dirname,relative),'utf8'),
 {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(api,n=>mocks[n]||{});return api; }
test('regional DANE references use only exact unambiguous known markets without changing source prices',
 {skip:!dsn},async()=>{
 const db=new Client({connectionString:dsn,statement_timeout:12000});await db.connect();
 try {
  await db.query('BEGIN');await db.query('SET LOCAL search_path=pg_temp');
  await db.query(`CREATE TEMP TABLE market(name text,region text);
    INSERT INTO market VALUES('Armenia, Mercar','Quindío'),('Armenia, Mercar','Quindio'),
    ('Armenia, Frigocafé',''),('Ambiguous market','Quindío'),('Ambiguous market','Antioquia'),
    ('Miami','Quindío')`);
  const base={quote_key:'oil',product_id:'oil',product_name:'Aceite vegetal mezcla',category:'Aceites',
   publisher:'DANE',series:'dane-daily-query',basis:'Publicado',currency:'COP',unit:'litre',
   market:'Armenia, Mercar',observed_on:'2012-10-23',period_start:null,price:3792,
   min_price:3542,max_price:4000,document_id:'original2012',source_locator:'JSON resultset[0]',
   source_url:'https://apps.dane.gov.co/pentaho/',details:{price_statistic:'published_mean'}};
  const quotes=[base,{...base,quote_key:'unknown',market:'Armenia, Frigocafé'},
   {...base,quote_key:'near-name',market:'Armenia Mercar'},
   {...base,quote_key:'ambiguous',market:'Ambiguous market'},
   {...base,quote_key:'foreign-publisher',publisher:'USDA',market:'Miami'},
   {...base,quote_key:'national-series',series:'world-bank-monthly'},
   {...base,quote_key:'weekly',series:'dane-weekly'}];
  const before=JSON.stringify(quotes);
  const api=load('../src/lib/server/official-market-regions.ts',{
   './db':{database:()=>db},'../filter-labels':load('../src/lib/filter-labels.ts')});
  const result=await api.officialMarketRegions(quotes);
  assert.equal(result[0].department,'Quindío');
  assert.equal(result[6].department,'Quindío');
  for(const index of [1,2,3,4,5])assert.equal(result[index].department,undefined);
  assert.equal(JSON.stringify(quotes),before,'Price history and literal sources are not mutated');
  for(const key of ['price','min_price','max_price','observed_on','document_id','source_locator','market'])
   assert.equal(result[0][key],base[key]);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM market')).rows[0].n,6);
 } finally {await db.query('ROLLBACK');await db.end();}
});
