/* Source-bound Arroz package SQL: synthetic TEMP rows, exact original identities. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const crypto=require('node:crypto');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {Client,types}=require('pg');
const {test}=require('node:test');
types.setTypeParser(1082,v=>v);types.setTypeParser(1700,Number);
const root=path.join(__dirname,'../src/lib/server');
function sourceFile(file){return path.normalize(file);}
const categoryPathSql=require('./helpers/load-category-path-sql.cjs')();
function load(file,mocks={}) {const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(sourceFile(file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require:n=>n==='server-only'?{}:n.endsWith('category-path-sql')?categoryPathSql:n==='../input-identity-equivalence'?require('./helpers/load-input-identity-equivalence.cjs')():(mocks[n]||(()=>{throw Error('unmocked '+n)})()),Map,Set,Date,console,performance});return exports;}
const alias=load(path.join(root,'city-market-alias.ts'));
const marketSql=load(path.join(root,'market-sql.ts'),{'./city-market-alias':alias});
const equivalence=load(path.join(root,'city-package-equivalence.ts'));
const defaultDimensions=load(path.join(root,'../product-filter-defaults.ts'));
const diagnostic=load(path.join(root,'product-detail-diagnostics.ts'));
const mock={WINDOW:"observed_on>(CURRENT_DATE-INTERVAL '12 months') AND observed_on<=CURRENT_DATE"};
let db,queries=[];
const dbMock={...mock,database:()=>{
 const query=async(q,a)=>{queries.push({sql:q,args:a});return db.query(q,a)};
 return {query,connect:async()=>({query,release(){}})};
}};
const price=load(path.join(root,'price-quotes.ts'),{'./db':dbMock,'./city-package-equivalence':equivalence,'../product-filter-defaults':defaultDimensions,'./city-market-alias':alias,'./product-detail-diagnostics':diagnostic,'./summary-references':{summaryReferencesForProduct:async()=>[]},'../price-classification':{currentClassifications:()=>[]},'../label-normalization':require('./helpers/load-label-normalization.cjs')(),'./market-alias':{resolveMarketAlias:async(_,id)=>id}});
const catalog=load(path.join(root,'catalog-sql.ts'),{'./city-package-equivalence':equivalence,'./city-market-alias':alias});
const math=load(path.join(root,'../comparison-math.ts'));
const labels=load(path.join(root,'../filter-labels.ts'));
const normalization=require('./helpers/load-label-normalization.cjs')();
const locations=load(path.join(root,'../input-locations.ts'),{'./filter-labels':labels,'./label-normalization':normalization});
const display=load(path.join(root,'../comparison-display.ts'),{'./label-normalization':normalization,'./comparison-math':math,'./input-locations':locations});
const corabastos=load(path.join(root,'comparison-corabastos-all-history.ts'),{'./db':dbMock,'./price-quotes':price,'./city-market-alias':alias,'node:crypto':crypto});
const comparisons=load(path.join(root,'comparisons.ts'),{'./db':dbMock,'./price-quotes':price,'./comparison-corabastos-all-history':corabastos,'./city-market-alias':alias,'./market-sql':marketSql,'./market-alias':{resolveMarketAlias:async(_,id)=>id},'./input-identities':{reconcileInputCatalog:async x=>x},'../comparison-math':math,'../filter-labels':labels,'../input-locations':locations,'../comparison-display':display});
const socket=process.env.AGRO_CATALOG_SQL_SOCKET;
const cases=[];async function run(name,sql,args,check=()=>{}){const rows=(await db.query(sql,args)).rows;check(rows);cases.push({name,sql_sha256:crypto.createHash('sha256').update(sql).digest('hex'),rows:rows.length,example:rows[0]&&{id:rows[0].id||rows[0].product_id,units:rows[0].units,source_units:rows[0].source_units,document_id:rows[0].document_id,source_locator:rows[0].source_locator,price:rows[0].price}});return rows}
test('Arroz 25×500g: 16 generated-query, filter, revision and provenance controls', {
 skip: !socket?.startsWith('/tmp/agro-unified-catalog-pg-') && 'Requires isolated AGRO_CATALOG_SQL_SOCKET',
}, async(t)=>{
 db=new Client({host:socket,port:65443,database:'postgres'});await db.connect();
 t.after(async()=>{await db.end()});
 await db.query("SET search_path=pg_temp; SET statement_timeout='8s'; SET TIME ZONE 'America/Bogota'");
 await db.query(`CREATE TEMP TABLE market(id text,name text,city text,region text,municipality_id text);
 CREATE TEMP TABLE product(id text,name text,category text);
 CREATE TEMP TABLE source_document(id text,source_url text,retrieved_at timestamptz,kind text,media_type text);
 CREATE TEMP TABLE price_observation(product_id text,market_id text,source_id text,observed_on date,price numeric,min_price numeric,max_price numeric,unit text,document_id text,source_locator text,source_url text,period text);
 CREATE TEMP VIEW published_price_observation AS SELECT * FROM price_observation;
 CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round int,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page int);
 CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text);
 CREATE TEMP TABLE city_pdf_publication_conflict(document_id text);
 CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS
   SELECT document_id FROM city_pdf_publication_conflict;
 CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r
   WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict c
     WHERE c.document_id=r.document_id);
 CREATE TEMP VIEW verified_regional_category_overlay AS
   SELECT document_id,source_locator,category AS corrected_category FROM regional_price WHERE FALSE;
 CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
   corrected_min_price numeric,corrected_max_price numeric);
 CREATE TEMP VIEW resolved_regional_price AS SELECT * FROM published_regional_price;
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
 INSERT INTO market VALUES('cali','Cali, Santa Elena','Cali','Valle del Cauca','76001'),('other','Cali, Santa Helena','Cali','Valle del Cauca','76001');
 INSERT INTO product VALUES('arroz-de-primera','Arroz de primera','Granos');
 INSERT INTO source_document VALUES
 ('1ccc3818bf3c6757de0f6179e6ce20adbcd37a15f307e33ed51edea4f23e0641','https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_21_2021.zip','2021-12-22','original','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
 ('8440cada34d16f78dd1f8ca024a4201c39a87511756a4e97b6d1ac6c8841c88c','https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-04-01-2022.zip','2022-01-05','original','application/pdf'),
 ('beef587b9f89f5d1c94e6e2dc5046ca7c574d58f55df2d9e162302c9e0a676d2','https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-29sep2026.zip','2026-09-30','original','application/pdf'),
 ('rev','https://www.dane.gov.co/files/operaciones/SIPSA/revision.zip','2026-10-01','original','application/pdf'),
 ('negative','https://example.org/non-authoritative','2026-10-01','original','application/pdf');
 INSERT INTO regional_price VALUES
 ('1ccc3818bf3c6757de0f6179e6ce20adbcd37a15f307e33ed51edea4f23e0641','Cali!row 100,cols D:G,round 1; daily-zip-v1','2021-12-21','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidades 500 GR',1,'Ronda 1',28400,29000,'Unidades 500 GR',NULL,NULL,1),
 ('8440cada34d16f78dd1f8ca024a4201c39a87511756a4e97b6d1ac6c8841c88c','PDF page 3,table 1,row 16,round 1','2022-01-04','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidades 500 GR',1,'Ronda 1',29000,30000,'Unidades 500 GR',NULL,NULL,3),
 ('beef587b9f89f5d1c94e6e2dc5046ca7c574d58f55df2d9e162302c9e0a676d2','PDF page 2,table 1,row 28,round 1','2026-09-29','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidad 500 GR',1,'Ronda 1',43000,44000,'Unidad 500 GR',NULL,NULL,2),
 ('rev','PDF page 2,table 1,row 28,round 2','2026-09-29','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidad 500 GR',2,'Ronda 2',44000,45000,'Unidad 500 GR',NULL,NULL,2),
 ('negative','other-market','2026-09-28','arroz-de-primera','Arroz de primera','Cali, Santa Helena','Granos','Bolsa',25,'Unidades 500 GR',1,'Ronda 1',1,2,'Unidades 500 GR',NULL,NULL,2),
 ('negative','fifty-gram','2026-09-28','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidad 50 GR',1,'Ronda 1',1,2,'Unidad 50 GR',NULL,NULL,2),
 ('negative','thousand-gram','2026-09-28','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidad 1000 GR',1,'Ronda 1',1,2,'Unidad 1000 GR',NULL,NULL,2);
 INSERT INTO regional_classification VALUES('rev','PDF page 2,table 1,row 28,round 2',ARRAY['Granos']);`);
 // Each guard changes one attribute of the same otherwise eligible PDF row.
 // This probes the production SQL expression, not a duplicate JavaScript predicate.
 const guardDoc='8440cada34d16f78dd1f8ca024a4201c39a87511756a4e97b6d1ac6c8841c88c';
 const guardLocator='PDF page 3,table 1,row 16,round 1';
 const guardSql=`SELECT ${equivalence.cityPackageMatchSql('r','d')} AS eligible,
   ${equivalence.cityFilterUnitsSql('r','d')} AS selected_units,
   r.source_unit,r.unit,r.quantity,r.min_price,r.max_price,r.source_locator,d.id AS document_id
   FROM regional_price r JOIN source_document d ON d.id=r.document_id
   WHERE r.document_id=$1 AND r.source_locator=$2`;
 const guarded=async()=>{const rows=(await db.query(guardSql,[guardDoc,guardLocator])).rows;assert.equal(rows.length,1);return rows[0]};
 const baseline=await guarded();assert.equal(baseline.eligible,true);assert.equal(baseline.selected_units,'25 × 500 g');
 assert.equal(baseline.source_unit,'Unidades 500 GR');assert.equal(baseline.unit,'Unidades 500 GR');
 assert.equal(baseline.quantity,25);assert.equal(baseline.min_price,29000);assert.equal(baseline.max_price,30000);
 assert.equal(baseline.document_id,guardDoc);assert.equal(baseline.source_locator,guardLocator);
 assert.ok(!baseline.selected_units.toLowerCase().includes('kg'),'the package quote is never invented as COP/kg');
 const guardCases=[
   ['other product',`UPDATE regional_price SET product_id='otro-arroz' WHERE document_id=$1 AND source_locator=$2`],
   ['other market',`UPDATE regional_price SET market_name='Cali, Santa Helena' WHERE document_id=$1 AND source_locator=$2`],
   ['other presentation',`UPDATE regional_price SET presentation='Caja' WHERE document_id=$1 AND source_locator=$2`],
   ['other quantity',`UPDATE regional_price SET quantity=15 WHERE document_id=$1 AND source_locator=$2`],
   ['50g package',`UPDATE regional_price SET source_unit='Unidades 50 GR',unit='Unidades 50 GR' WHERE document_id=$1 AND source_locator=$2`],
   ['1000g package',`UPDATE regional_price SET source_unit='Unidades 1000 GR',unit='Unidades 1000 GR' WHERE document_id=$1 AND source_locator=$2`],
   ['raw unit mismatch',`UPDATE regional_price SET unit='Kilogramo' WHERE document_id=$1 AND source_locator=$2`],
   ['null locator',`UPDATE regional_price SET source_locator=NULL WHERE document_id=$1 AND source_locator=$2`],
   ['empty locator',`UPDATE regional_price SET source_locator='' WHERE document_id=$1 AND source_locator=$2`],
   ['non-original document',`UPDATE source_document SET kind='derived' WHERE id=$1`],
   ['wrong media',`UPDATE source_document SET media_type='text/plain' WHERE id=$1`],
   ['unofficial URL',`UPDATE source_document SET source_url='https://example.org/official-looking.pdf' WHERE id=$1`],
 ];
 for(const [name,mutation] of guardCases){
   await db.query('BEGIN');await db.query(mutation,mutation.includes('source_document')?[guardDoc]:[guardDoc,guardLocator]);
   const sql=`SELECT ${equivalence.cityPackageMatchSql('r','d')} AS eligible FROM regional_price r JOIN source_document d ON d.id=r.document_id WHERE r.document_id=$1`;
   const rows=(await db.query(sql,[guardDoc])).rows;assert.equal(rows.length,1,name);assert.equal(rows[0].eligible,false,name);
   await db.query('ROLLBACK');assert.equal((await guarded()).eligible,true,`restored after ${name}`);
 }
 const id='arroz-de-primera', region='Valle del Cauca', json=JSON.stringify([{product_id:id,latest_date:'2026-09-29'}]);
 await run('catalog city quotes / region',catalog.CITY_CATALOG_SQL,[region,json],rows=>{assert(rows.some(r=>r.units==='25 × 500 g'));});
 await run('catalog city quotes / national',catalog.CITY_CATALOG_SQL,['',json]);
 await run('cityPriceQuotes classify false',`SELECT * FROM (${price.cityPriceQuotes(false)}) q WHERE market_id='cali'`,[],rows=>{assert(rows.some(r=>r.source_units==='25 Unidades 500 GR'));assert(rows.some(r=>r.units==='25 × 500 g'));});
 await run('cityPriceQuotes classify true',`SELECT * FROM (${price.cityPriceQuotes(true)}) q WHERE market_id='cali'`,[],rows=>{assert(rows.some(r=>r.document_id==='rev'));});
 await run('ordinary filter options',price.PRODUCT_FILTER_OPTIONS_SQL,[id,region],rows=>{assert(rows.some(r=>r.units==='25 × 500 g'));});
 await run('fallback filter options',`WITH quotes AS (${price.PRICE_QUOTE_VALUES}) SELECT DISTINCT series,market_id,market_name,presentation,units FROM quotes WHERE product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ')) AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY series,market_name,presentation,units`,[id,region],rows=>assert(rows.some(r=>r.units==='25 × 500 g')));
 await run('cityLooseLatestQuotes all',price.CITY_LOOSE_LATEST_QUOTES,[[id]],rows=>{assert(rows.some(r=>r.units==='25 × 500 g'));assert(rows.some(r=>r.source_units==='25 Unidad 500 GR'));});
 await run('cityLooseLatestQuotes recent',price.CITY_RECENT_LOOSE_LATEST_QUOTES,[[id]],rows=>assert(rows.some(r=>r.units==='25 × 500 g')));
 const detail=await price.filteredProduct(id,region,{series:'city',market:'cali',presentation:'Bolsa',units:'25 × 500 g',history:'all'});
 for(const old of ['25 Unidad 500 gr','25 Unidades 500 GR']) {
   const legacy=await price.filteredProduct(id,region,{series:'city',market:'cali',presentation:'Bolsa',units:old,history:'all'});
   assert.equal(legacy.filters.units,'25 × 500 g');assert.equal(legacy.history.length,3);
   assert(legacy.history[0].sources.some(source=>source.source_units==='25 Unidades 500 GR'));
   cases.push({name:'legacy literal URL '+old,rows:legacy.history.length,selected_units:legacy.filters.units});
 }
 const unsafe=await price.filteredProduct(id,region,{series:'city',market:'other',presentation:'Bolsa',units:'25 Unidad 500 gr',history:'all'});
 assert.equal(unsafe.filters.units,'25 Unidad 500 gr');assert.equal(unsafe.history.length,0);
 cases.push({name:'legacy URL different market fails closed',rows:unsafe.history.length,selected_units:unsafe.filters.units});
 assert.equal(detail.filters.units,'25 × 500 g');assert.deepEqual(Array.from(detail.history,h=>[h.date,Number(h.price)]),[['2021-12-21',28700],['2022-01-04',29500],['2026-09-29',44500]]);assert.equal(detail.current.price,44500);assert.equal(detail.markets[0].document_id,'rev');assert.equal(detail.markets[0].source_locator,'PDF page 2,table 1,row 28,round 2');cases.push({name:'history/current canonical filter',rows:detail.history.length,markets:detail.markets.length,current:detail.current?.date,raw_source_units:detail.history.flatMap(h=>h.sources||[]).map(s=>s.source_units)});
 const badUnits=(await db.query(price.PRODUCT_FILTER_OPTIONS_SQL,[id,region])).rows.map(r=>r.units);assert(badUnits.includes('25 Unidad 50 gr')&&badUnits.includes('25 Unidad 1000 gr'));assert(!badUnits.includes('25 × 50 g'));
 const before=queries.length;const comparisonResult=await comparisons.comparison('markets',{a:'cali',b:'__national__',series:'city',history:'all'});const after=queries.slice(before);assert(comparisonResult.rows.some(r=>r.a.units==='25 × 500 g'));cases.push({name:'comparison national indexed branch',rows:comparisonResult.rows.length,sql_calls:after.length,sql_sha256:after.map(q=>crypto.createHash('sha256').update(q.sql).digest('hex')),raw_source_units:comparisonResult.rows.find(r=>r.a.units==='25 × 500 g').a.source_units});
 const before2=queries.length;const comparisonSpecific=await comparisons.comparison('markets',{a:'cali',b:'other',series:'city',history:'all'});const after2=queries.slice(before2);cases.push({name:'comparison named-market generic branch',rows:comparisonSpecific.rows.length,sql_calls:after2.length,sql_sha256:after2.map(q=>crypto.createHash('sha256').update(q.sql).digest('hex'))});
 await db.query(`INSERT INTO source_document VALUES('rev-same','https://www.dane.gov.co/files/operaciones/SIPSA/revision-same.zip','2026-10-02','original','application/pdf'); INSERT INTO regional_price VALUES('rev-same','same-round-newer','2026-09-29','arroz-de-primera','Arroz de primera','Cali, Santa Elena','Granos','Bolsa',25,'Unidad 500 GR',1,'Ronda 1',46000,47000,'Unidad 500 GR',NULL,NULL,2)`);
 const priorRound=(await db.query(`SELECT price,document_id FROM (${price.cityPriceQuotes(false)}) q WHERE market_id='cali' AND observed_on='2026-09-29' AND units='25 × 500 g'`)).rows;assert.equal(priorRound.length,1);assert.equal(priorRound[0].document_id,'rev');cases.push({name:'round 2 outranks newer round 1',rows:priorRound.length,winner:priorRound[0].document_id});
 await db.query(`DELETE FROM regional_price WHERE document_id='rev'`);const sameRound=(await db.query(`SELECT price,document_id FROM (${price.cityPriceQuotes(false)}) q WHERE market_id='cali' AND observed_on='2026-09-29' AND units='25 × 500 g'`)).rows;assert.equal(sameRound.length,1);assert.equal(sameRound[0].document_id,'rev-same');assert.equal(Number(sameRound[0].price),46500);cases.push({name:'same-round later revision wins',rows:sameRound.length,winner:sameRound[0].document_id,price:sameRound[0].price});
 assert.equal(cases.length,16);
});
