"use strict";
const { test }=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const crypto=require('node:crypto');
const {Pool,types}=require('pg');
types.setTypeParser(1700,Number);types.setTypeParser(20,Number);types.setTypeParser(1082,x=>x);
const root=path.join(__dirname,'../../..');
const server=path.join(__dirname,'../src/lib/server');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const socket=process.env.AGRO_PRODUCT_DETAIL_FULLSCHEMA_SOCKET;
const port=Number(process.env.AGRO_PRODUCT_DETAIL_FULLSCHEMA_PORT);
const required=process.env.AGRO_PRODUCT_DETAIL_FULLSCHEMA_REQUIRED==='1';
const enabled=Boolean(socket&&/^\/tmp\/agro-product-detail-fullschema-[^/]+\/socket$/.test(socket)&&Number.isInteger(port)&&port>0);
if(required&&!enabled)throw new Error('dedicated local full-schema PostgreSQL fixture required');
const db=enabled?new Pool({host:socket,port,database:'postgres',user:'postgres',max:2}):null;
function load(file,mocks={}){
 const exports={};
 const js=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(js,{exports,require:n=>n==='server-only'?{}:mocks[n],performance},{filename:file});
 return exports;
}
const classification=load(path.join(root,'apps/web/src/lib/price-classification.ts'));
const defaults=load(path.join(root,'apps/web/src/lib/product-filter-defaults.ts'));
const labels=load(path.join(root,'apps/web/src/lib/label-normalization.ts'),{
 '../../../../shared/label-normalization.json':{default:JSON.parse(fs.readFileSync(path.join(root,'shared/label-normalization.json')))}
});
const alias=load(path.join(server,'city-market-alias.ts'));
const cityPackage=load(path.join(server,'city-package-equivalence.ts'));
const diagnostics=load(path.join(server,'product-detail-diagnostics.ts'));
const WINDOW=fs.readFileSync(path.join(server,'db.ts'),'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
const mocks={'../product-filter-defaults':defaults,'../price-classification':classification,
 '../label-normalization':labels,'./db':{WINDOW,database:()=>db},
 './summary-references':{summaryReferencesForProduct:async()=>[]},
 './market-alias':{resolveMarketAlias:async(_,id)=>id},
 './city-market-alias':alias,'./city-package-equivalence':cityPackage,
 './product-detail-diagnostics':diagnostics};
const price=load(path.join(server,'price-quotes.ts'),mocks);
const source={};
for(const x of ['base','revision','held','correction'])source[x]={body:Buffer.from(`fullschema-${x}`)};
for(const x of Object.keys(source))source[x].id=sha(source[x].body);
async function setup(){
 assert.equal((await db.query('SELECT inet_server_addr() IS NULL AS local')).rows[0].local,true);
 await db.query("INSERT INTO product(id,name,category) VALUES('limon-tahiti','Limón Tahití','Frutas')");
 for(let i=1;i<=20;i++)await db.query('INSERT INTO market(id,name,city,region) VALUES($1,$2,$3,$4)',
  [`dane-city-fixture-${String(i).padStart(2,'0')}`,`Fixture ${String(i).padStart(2,'0')}`,'Fixture','Tolima']);
 for(const [name,item] of Object.entries(source))await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at,metadata)
 VALUES($1,$2,'DANE',$3,'application/pdf','original','2026-09',$4,$5,$6::jsonb)`,
  [item.id,name,`https://example.invalid/${name}.pdf`,item.body,
   name==='base'?'2026-09-01':'2026-10-01',JSON.stringify({ingestion_kind:'city-pdf'})]);
 await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,
 market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
 SELECT $1,'PDF page 1,table 1,row '||(d.n*20+m.n)||',round 1',DATE '2026-09-01'+d.n,
 'limon-tahiti','Limón Tahití','Fixture '||lpad(m.n::text,2,'0'),'Frutas > Cítricos',
 'Kilogramo',1,'Kilogramo',1,'Ronda 1',1000+d.n+m.n,1010+d.n+m.n,'kg',1
 FROM generate_series(0,29) AS d(n) CROSS JOIN generate_series(1,20) AS m(n)`,[source.base.id]);
 const one=(doc,market,row,round,min)=>db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,
 market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
 VALUES($1,$2,'2026-09-30',$3,$4,$5,'Frutas > Cítricos','Kilogramo',1,'Kilogramo',$6,'Ronda',
 $7::numeric,$7::numeric+10,'kg',1)`,[doc.id,`PDF page 1,table 1,row ${row},round ${round}`,
 market===20?'limon-ta-hiti':'limon-tahiti',market===20?'Limón Ta hití':'Limón Tahití',
 `Fixture ${String(market).padStart(2,'0')}`,round,min]);
 await one(source.revision,1,1,2,8000);
 await one(source.held,2,1,2,99999);
 await one(source.correction,20,1,2,9000);
 await db.query(`INSERT INTO regional_price_product_correction(document_id,source_locator,
 old_product_id,old_product_name,corrected_product_id,corrected_product_name,source_sha256,
 source_url,source_page,verification)
 VALUES($1,'PDF page 1,table 1,row 1,round 2','limon-ta-hiti','Limón Ta hití','limon-tahiti',
 'Limón Tahití',$1,'https://example.invalid/correction.pdf',1,
 '{"method":"native-pdf-glyph-spacing","unchanged_fields_sha256":"fixture"}'::jsonb)`,[source.correction.id]);
 await db.query(`INSERT INTO city_pdf_publication_conflict(document_id,processor_version,native_sha256,stored_sha256,details)
 VALUES($1,'held-v1',$2,$3,'{}'::jsonb)`,[source.held.id,'a'.repeat(64),'b'.repeat(64)]);
 await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,
 market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
 VALUES($1,'PDF page 1,table 1,row 999,round 1','2025-01-01','limon-tahiti','Limón Tahití',
 'Fixture 01','Frutas > Cítricos','Bulto',70,'Kilogramo',1,'Ronda 1',10000,11000,'package',1)`,[source.base.id]);
 await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
 SELECT document_id,source_locator,ARRAY['Frutas','Cítricos'] FROM regional_price`);
}
function clean(x){return JSON.parse(JSON.stringify(x));}
test('real public views retain all-market city history and exact source winners',
 {skip:!enabled},async()=>{
 try{
  assert.equal((await db.query('SELECT inet_server_addr() IS NULL AS local')).rows[0].local,true);
  await db.query("SET statement_timeout='8s'");
  await setup();
  const filters={series:'city',market:'',presentation:'Kilogramo',units:'1 Kilogramo',history:'all'};
  const actual=clean(await price.filteredProduct('limon-tahiti','',filters));
  assert.equal(actual.filters.series,'city');
  assert.equal(actual.filters.market,'');
  assert.equal(actual.filters.presentation,'Kilogramo');
  assert.equal(actual.filters.units,'1 Kilogramo');
  assert.equal(actual.filters.history,'all');
  assert.equal(actual.markets.length,20);
  assert.equal(actual.history.length,30);
  assert.equal(actual.classification.some(path=>path.join(' > ')==='Frutas > Cítricos'),true);
  for(let day=0;day<30;day++){
   const point=actual.history[day];
   assert.equal(point.date,new Date(Date.UTC(2026,8,1+day)).toISOString().slice(0,10));
   assert.equal(point.market_count,20,`market count on day ${day}`);
   assert.equal(point.sources.length,20,`source count on day ${day}`);
   assert.equal(Number(point.price),day===29?1790.55:1015.5+day,`mean on day ${day}`);
   const seen=new Set();
   for(const ref of point.sources){
    assert.match(ref.market_id,/^dane-city-fixture-(0[1-9]|1[0-9]|20)$/);
    assert.equal(ref.source_page,1);
    assert.equal(ref.source_units,'1 Kilogramo');
    assert.equal(ref.source_market_id,ref.market_id);
    assert.equal(seen.has(ref.market_id),false,`duplicate market ${ref.market_id}`);
    seen.add(ref.market_id);
    const market=Number(ref.market_id.slice(-2));
    const special=day===29&&market===1?'revision':day===29&&market===20?'correction':'base';
    assert.equal(ref.document_id,source[special].id,`own source on day ${day} market ${market}`);
    assert.equal(ref.source_locator,special==='base'
      ?`PDF page 1,table 1,row ${day*20+market},round 1`
      :'PDF page 1,table 1,row 1,round 2');
   }
  }
  assert.equal(actual.current.date,'2026-09-30');
  assert.equal(Number(actual.current.price),1790.55);
  assert.equal(actual.current.market_count,20);
  const byMarket=new Map(actual.markets.map(m=>[m.market_id,m]));
  assert.equal(byMarket.size,20);
  assert.equal(byMarket.get('dane-city-fixture-01').document_id,source.revision.id);
  assert.equal(Number(byMarket.get('dane-city-fixture-01').price),8005);
  assert.equal(byMarket.get('dane-city-fixture-20').document_id,source.correction.id);
  assert.equal(Number(byMarket.get('dane-city-fixture-20').price),9005);
  assert.equal(byMarket.get('dane-city-fixture-02').document_id,source.base.id);
  assert.equal(Number(byMarket.get('dane-city-fixture-02').price),1036);
  for(const market of actual.markets)assert.deepEqual(market.category_path,['Frutas','Cítricos']);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.regional_price WHERE document_id=$1',[source.held.id])).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.resolved_regional_price WHERE document_id=$1',[source.held.id])).rows[0].n,0);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.regional_price WHERE document_id=$1 AND product_id=$2',[source.correction.id,'limon-ta-hiti'])).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.resolved_regional_price WHERE document_id=$1 AND product_id=$2',[source.correction.id,'limon-tahiti'])).rows[0].n,1);
  const defaulted=clean(await price.filteredProduct('limon-tahiti','',
    {series:'city',market:'',presentation:'',units:'',history:'all'}));
  assert.equal(defaulted.filters.presentation,'Kilogramo');
  assert.equal(defaulted.filters.units,'1 Kilogramo');
  assert.deepEqual(defaulted.history,actual.history);
  const fixture=await aliasFixture();
  const aliasResult=clean(await price.filteredProduct('limon-tahiti','',{
    series:'city',market:'sipsa-bogota-d-c-corabastos',presentation:'Bulto',units:'70 Kilogramo',history:'all'
  }));
  const expected=[
   ['2024-01-01',115,fixture.docs[1],'target-new-round'],
   ['2024-01-02',255,fixture.docs[9],'target-bulto-unrelated-package-conflict'],
   ['2024-01-03',95,fixture.docs[4],'old-valid'],
   ['2024-01-06',805,fixture.docs[8],'corrected-old-product']
  ];
  assert.deepEqual(aliasResult.history.map(point=>[
    point.date,Number(point.price),point.sources?.[0]?.document_id,point.sources?.[0]?.source_locator
  ]),expected,'published, latest-round, all-history alias package winners');
  assert.equal(aliasResult.history.some(point=>point.date==='2024-01-04'),false,'held document excluded');
  assert.equal(aliasResult.history.some(point=>point.date==='2024-01-05'),false,'conflicting aliases excluded');
  assert.equal(aliasResult.history.length,4,'all eligible historical dates retained');
  assert.equal(aliasResult.current.date,'2024-01-06');
  assert.equal(Number(aliasResult.current.price),805);
  assert.equal((await db.query(`SELECT round FROM public.regional_price
    WHERE document_id=$1 AND source_locator='target-new-round'`,[fixture.docs[1]])).rows[0].round,2,
    'the emitted Jan 1 locator is the winning round 2');
  assert.equal((await db.query(`SELECT corrected_product_id FROM public.regional_price_product_correction
    WHERE document_id=$1 AND source_locator='corrected-old-product'`,[fixture.docs[8]])).rows[0].corrected_product_id,'limon-tahiti');
  assert.equal(aliasResult.markets.some(market=>market.market_id==='fixture-invalid-muni-alias'),false,
    'same-name alias from another municipality excluded');
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.regional_price WHERE document_id=$1',[fixture.docs[5]])).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.resolved_regional_price WHERE document_id=$1',[fixture.docs[5]])).rows[0].n,0);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.regional_price WHERE document_id=$1 AND product_id=$2',[fixture.docs[8],'limon-ta-hiti'])).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.resolved_regional_price WHERE document_id=$1 AND product_id=$2',[fixture.docs[8],'limon-tahiti'])).rows[0].n,1);
 }finally{await db.end()}
});

async function aliasFixture(){
 await db.query("INSERT INTO municipality(id,name,department,department_id,latitude,longitude) VALUES('11001','Bogotá','Bogotá D.C.','11',4.711,-74.072),('05001','Medellín','Antioquia','05',6.251,-75.563) ON CONFLICT(id) DO NOTHING");
 await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
 ('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('fixture-bogota-corabastos','Bogotá, Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('fixture-bogota-dc-corabastos','Bogotá D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('fixture-bogota-accent-corabastos','Bogotà, Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('fixture-invalid-muni-alias','Bogotá, Corabastos','Medellín','Antioquia','05001') ON CONFLICT(id) DO NOTHING`);
 const docs=[];
 for(let i=0;i<10;i++){
  const id=sha(Buffer.from('limon-alias-fullschema-'+i)); docs.push(id);
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at,metadata)
   VALUES($1,$2,'DANE',$3,'application/pdf','original','2024',$4,$5,'{"ingestion_kind":"city-pdf"}'::jsonb)`,[id,'alias-'+i,`https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/${i}.pdf`,Buffer.from('fixture'),`2024-02-0${i+1}`]);
 }
 await db.query("INSERT INTO product(id,name,category) VALUES('limon-ta-hiti','Limón Ta hití','Frutas') ON CONFLICT(id) DO NOTHING");
 const rows=[
  [docs[0],'target-upper','2024-01-01','Bogotá, D.C., Corabastos','BULTO','KILOGRAMO',70,1,100],
  [docs[1],'target-new-round','2024-01-01','Bogotá, D.C., Corabastos','bulto','kilogramo',70,2,110],
  [docs[2],'irrelevant-sack-a','2024-01-02','Bogotá, Corabastos','Saco','Kilogramo',70,1,200],
  [docs[3],'irrelevant-sack-b','2024-01-02','Bogotá D.C., Corabastos','Saco','Kilogramo',70,1,300],
  [docs[9],'target-bulto-unrelated-package-conflict','2024-01-02','Bogotá, D.C., Corabastos','Bulto','Kilogramo',70,1,250],
  [docs[4],'old-valid','2024-01-03','Bogotá, D.C., Corabastos','Bulto','Kilogramo',70,1,90],
  [docs[5],'held-latest','2024-01-04','Bogotá, Corabastos','Bulto','Kilogramo',70,1,500],
  [docs[6],'alias-conflict-a','2024-01-05','Bogotá, Corabastos','Bulto','Kilogramo',70,1,600],
  [docs[7],'alias-conflict-b','2024-01-05','Bogotá D.C., Corabastos',' bUlTo ','kILoGrAmO ',70,1,700],
  [docs[8],'corrected-old-product','2024-01-06','Bogotá, D.C., Corabastos','Bulto','Kilogramo',70,1,800]
 ];
 for(const [doc,loc,day,market,pres,unit,qty,round,price] of rows)
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
   VALUES($1,$2,$3,CASE WHEN $2='corrected-old-product' THEN 'limon-ta-hiti' ELSE 'limon-tahiti' END,CASE WHEN $2='corrected-old-product' THEN 'Limón Ta hití' ELSE 'Limón Tahití' END,$4,'Frutas > Cítricos',$5,$6,$7,$8,'Ronda',$9::numeric,$9::numeric+10,'package',$9::numeric,$9::numeric+10,1)`,[doc,loc,day,market,pres,qty,unit,round,price]);
 await db.query(`INSERT INTO regional_price_product_correction(document_id,source_locator,old_product_id,old_product_name,corrected_product_id,corrected_product_name,source_sha256,source_url,source_page,verification)
  VALUES($1,'corrected-old-product','limon-ta-hiti','Limón Ta hití','limon-tahiti','Limón Tahití',$1,$2,1,'{"method":"native-pdf-glyph-spacing","unchanged_fields_sha256":"fixture"}'::jsonb)`,[docs[8],`https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/8.pdf`]);
 await db.query("INSERT INTO city_pdf_publication_conflict(document_id,processor_version,native_sha256,stored_sha256,details) VALUES($1,'fixture-v1',$2,$3,'{}'::jsonb)",[docs[5],'a'.repeat(64),'b'.repeat(64)]);
 return {docs,rows};
}
