/* Real filteredProduct dispatch versus frozen pre-repair SQL in owned TEMP PostgreSQL. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {Client,types}=require('pg');
types.setTypeParser(1700,Number);types.setTypeParser(20,Number);types.setTypeParser(1082,v=>v);

const server=path.join(__dirname,'../src/lib/server');
const root=path.join(__dirname,'../../..');
const socket=process.env.AGRO_PRODUCT_DETAIL_SCOPE_TEST_SOCKET;
const enabled=socket?.startsWith('/tmp/agro-')&&Number.isInteger(Number(process.env.AGRO_PRODUCT_DETAIL_SCOPE_TEST_PORT));
const market='sipsa-medellin-plaza-minorista-jose-maria-villa';
const sqlFalse=fs.readFileSync(path.join(__dirname,'fixtures/product-detail-single-market-legacy-false.sql'),'utf8');
const sqlTrue=fs.readFileSync(path.join(__dirname,'fixtures/product-detail-single-market-legacy-true.sql'),'utf8');
const WINDOW=fs.readFileSync(path.join(server,'db.ts'),'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
function moduleSQL(filename,mocks={}){
  const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server,filename),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
    {exports,require:name=>name==='server-only'?{}:mocks[name],performance});return exports;
}
function legacy(history,ambiguous){
  const all=ambiguous?sqlTrue:sqlFalse;
  if(history==='all')return all;
  const phrase="observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";
  assert.equal(all.split(phrase).length-1,2,'two frozen legacy date predicates');
  return all.replaceAll(phrase,WINDOW);
}
const owner=(name)=>name==='server-only'?{}:undefined;

test('one ordinary city market retains full source, money, category and dated winners',
  {skip:!enabled&&'Requires owned private PostgreSQL socket'},async()=>{
  const db=new Client({host:socket,port:Number(process.env.AGRO_PRODUCT_DETAIL_SCOPE_TEST_PORT),
    database:process.env.AGRO_PRODUCT_DETAIL_SCOPE_TEST_DB||'postgres',
    user:process.env.AGRO_PRODUCT_DETAIL_SCOPE_TEST_USER||process.env.USER});
  await db.connect();
  try{
    await db.query(`SET search_path=pg_temp;SET statement_timeout='8s';SET TIME ZONE 'America/Bogota';
      CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text);
      CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text);
      CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,retrieved_at timestamptz,kind text DEFAULT 'original',media_type text DEFAULT 'application/pdf');
      CREATE TEMP TABLE published_price_observation(product_id text,market_id text,observed_on date,price numeric,min_price numeric,max_price numeric,unit text,source_id text,document_id text,source_locator text,source_url text,period text);
      CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round integer,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page integer,PRIMARY KEY(document_id,source_locator));
      CREATE INDEX ON regional_price(product_id,market_name,observed_on DESC);
      CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text,PRIMARY KEY(document_id,source_locator));
      CREATE TEMP TABLE unresolved_city_pdf_publication_conflict(document_id text PRIMARY KEY);
      CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,corrected_min_price numeric,corrected_max_price numeric,corrected_min_unit_price numeric,corrected_max_unit_price numeric);
      CREATE TEMP TABLE verified_regional_category_overlay(document_id text,source_locator text,corrected_category text);
      CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
      CREATE TEMP VIEW published_regional_price AS SELECT r.document_id,r.source_locator,r.observed_on,r.product_id,r.product_name,r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
        coalesce(o.corrected_min_price,r.min_price) min_price,coalesce(o.corrected_max_price,r.max_price) max_price,r.unit,
        coalesce(o.corrected_min_unit_price,r.min_unit_price) min_unit_price,coalesce(o.corrected_max_unit_price,r.max_unit_price) max_unit_price,r.source_page
        FROM regional_price r LEFT JOIN verified_city_pdf_price_overlay o ON o.document_id=r.document_id AND o.source_locator=r.source_locator
        WHERE NOT EXISTS(SELECT 1 FROM unresolved_city_pdf_publication_conflict h WHERE h.document_id=r.document_id OFFSET 0);
      CREATE TEMP VIEW resolved_regional_price AS
        SELECT r.document_id,r.source_locator,r.observed_on,r.product_id,r.product_name,r.market_name,coalesce(o.corrected_category,r.category) category,
          r.presentation,r.quantity,r.source_unit,r.round,r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
        FROM published_regional_price r LEFT JOIN verified_regional_category_overlay o ON o.document_id=r.document_id AND o.source_locator=r.source_locator
        WHERE NOT EXISTS(SELECT 1 FROM regional_price_product_correction c WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
        UNION ALL SELECT r.document_id,r.source_locator,r.observed_on,c.corrected_product_id,c.corrected_product_name,r.market_name,coalesce(o.corrected_category,r.category),
          r.presentation,r.quantity,r.source_unit,r.round,r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
        FROM regional_price_product_correction c JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
        LEFT JOIN verified_regional_category_overlay o ON o.document_id=r.document_id AND o.source_locator=r.source_locator;
      INSERT INTO market VALUES('sipsa-medellin-plaza-minorista-jose-maria-villa','Medellín, Plaza Minorista "José María Villa"','Medellín','Antioquia','05001'),('other','Other','Other','Antioquia','05002');
      INSERT INTO product VALUES('cilantro','Cilantro','Verduras'),('old-cilantro','Old','Verduras');
      INSERT INTO source_document(id,source_url,retrieved_at) VALUES
       ('a','https://www.dane.gov.co/a.pdf','2024-01-25'),('b','https://www.dane.gov.co/b.pdf','2024-01-26'),
       ('c','https://www.dane.gov.co/c.pdf','2024-01-27'),('r','https://www.dane.gov.co/r.pdf','2026-01-01'),
       ('h','https://www.dane.gov.co/h.pdf','2026-01-02'),('v','https://www.dane.gov.co/v.pdf','2026-01-03');
      INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
      VALUES('a','r1','2024-01-25','cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',1,'R1',5800,6000,'kg',5800,6000,3),
       ('b','r2-old','2024-01-25','cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',2,'R2',5900,6000,'kg',5900,6000,3),
       ('c','r2-new','2024-01-25','cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',2,'R2',5800,6000,'kg',5800,6000,3),
       ('r','recent',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-1,'cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',1,'R1',7000,7200,'kg',7000,7200,1),
       ('h','held',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date,'cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',1,'R1',9000,9500,'kg',9000,9500,1),
       ('a','other-market',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date,'cilantro','Cilantro','Other','Verduras','Kilogramo',1,'Kilogramo',1,'R1',1000,1200,'kg',1000,1200,1);
      INSERT INTO verified_city_pdf_price_overlay VALUES('c','r2-new',6000,6000,6000,6000);
      INSERT INTO verified_regional_category_overlay VALUES('c','r2-new','Hortalizas > Aromáticas');
      INSERT INTO unresolved_city_pdf_publication_conflict VALUES('h');`);
    let picked,optionAmbiguous;
    const database={query:async(sql,args)=>{
      const answer=await db.query(sql,args);
      if(sql.includes('SELECT options.*,ambiguity.requires_revision_resolution'))
        optionAmbiguous=answer.rows.some(x=>x.requires_revision_resolution===true);
      if(sql.includes('selected AS MATERIALIZED')&&sql.includes('jsonb_agg(history'))
        picked={sql,args,result:answer.rows[0]};
      return answer;
    }};
    const classification=moduleSQL('../price-classification.ts');
    const label=moduleSQL('../label-normalization.ts',{'../../../../shared/label-normalization.json':
      {default:JSON.parse(fs.readFileSync(path.join(root,'shared/label-normalization.json'),'utf8'))}});
    const alias=moduleSQL('city-market-alias.ts'),pkg=moduleSQL('city-package-equivalence.ts');
    const diagnostics=moduleSQL('product-detail-diagnostics.ts');
    const defaultDimensions=moduleSQL('../product-filter-defaults.ts');
    const quote=moduleSQL('price-quotes.ts',{'../price-classification':classification,'../label-normalization':label,
      './db':{WINDOW,database:()=>database},'./summary-references':{summaryReferencesForProduct:async()=>[]},
      './market-alias':{resolveMarketAlias:async(_,id)=>id},'./city-market-alias':alias,
      './city-package-equivalence':pkg,'./product-detail-diagnostics':diagnostics,
      '../product-filter-defaults':defaultDimensions});
    async function parity(name,history,expectedAmbiguous){
      picked=undefined;optionAmbiguous=undefined;
      const data=await quote.filteredProduct('cilantro','',{series:'city',market,presentation:'Kilogramo',history});
      assert.ok(data&&picked,name+' actual dispatch');
      assert.equal(optionAmbiguous,expectedAmbiguous,name+' option ambiguity');
      assert.deepEqual(JSON.parse(JSON.stringify(picked.args)),['cilantro','','city','Kilogramo','1 Kilogramo',market,[market]],name+' selected dimensions');
      const old=(await db.query(legacy(history,expectedAmbiguous),picked.args)).rows[0];
      assert.deepEqual(picked.result,old,name+' full legacy selected JSON');
      assert.equal(data.history.length,picked.result.history.length,name+' public history complete');
      return picked.result;
    }
    const all=await parity('all dates, round, retrieval, held, 073 money','all',false);
    assert.equal(Number(all.history.find(x=>x.date==='2024-01-25').price),6000);
    assert.equal(all.history.find(x=>x.date==='2024-01-25').sources[0].source_locator,'r2-new');
    assert.ok(all.history.length>=2,'old source remains in all history');
    const recent=await parity('recent source window','recent',false);
    assert.equal(recent.history.length,1,'recent keeps only current report');
    await db.query("INSERT INTO unresolved_city_pdf_publication_conflict VALUES('r')");
    const fallback=await parity('held recent source reveals older verified quote','all',false);
    assert.equal(fallback.markets[0].category,'Hortalizas > Aromáticas');
    assert.deepEqual([Number(fallback.markets[0].min_price),Number(fallback.markets[0].max_price)],[6000,6000]);
    await db.query("DELETE FROM unresolved_city_pdf_publication_conflict WHERE document_id='r'");
    await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
      VALUES('a','identity-inbound','2025-02-01','old-cilantro','Old','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo',1,'Kilogramo',1,'R1',8000,8300,'kg',1),
      ('a','other-package','2025-02-02','cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Bulto',50,'Kilogramo',1,'R1',100000,110000,'package',1)`);
    await db.query("INSERT INTO regional_price_product_correction VALUES('a','identity-inbound','cilantro','Cilantro')");
    const corrected=await parity('identity correction and unselected package','all',false);
    assert.equal(corrected.history.length,3,'corrected source adds one old date; other package does not');
    await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
      VALUES('v','spelling-revision','2024-01-25','cilantro','Cilantro','Medellín, Plaza Minorista "José María Villa"','Verduras','Kilogramo ',1,'Kilogramo',2,'R2',6500,6700,'kg',3)`);
    const variant=await parity('ambiguous displayed presentation retains winning revision','all',true);
    assert.ok(!variant.history.some(x=>x.date==='2024-01-25'),'later revised spelling hides old same-key presentation');
  }finally{await db.end()}
});
