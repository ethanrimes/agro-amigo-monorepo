/* Private PostgreSQL source cases against the retained P-O query reference. */
const { test } = require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm'),ts=require('typescript');
const {Client,types}=require('pg');types.setTypeParser(1082,v=>v);types.setTypeParser(1700,Number);
const root=path.join(__dirname,'../../..');
const old=fs.readFileSync(path.join(__dirname,'fixtures/product-filter-options-p-o-source-reference.sql'),'utf8');
const server=path.join(__dirname,'../src/lib/server');
const WINDOW=fs.readFileSync(path.join(server,'db.ts'),'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
function load(filename,mocks){
 const exports={};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server,filename),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
 }).outputText,{exports,require:name=>name==='server-only'?{}:mocks[name],performance});
 return exports;
}
const classification=load('../price-classification.ts',{});
const labels=JSON.parse(fs.readFileSync(path.join(root,'shared/label-normalization.json'),'utf8'));
const normalize=load('../label-normalization.ts',{'../../../../shared/label-normalization.json':{default:labels}});
const categoryPath=load('category-path-sql.ts',{});
const alias=load('city-market-alias.ts',{'./category-path-sql':categoryPath});
const pack=load('city-package-equivalence.ts',{});
const diagnostics=load('product-detail-diagnostics.ts',{});
const defaults=load('../product-filter-defaults.ts',{});
let queryPool;
const candidate=load('price-quotes.ts',{'../price-classification':classification,'../label-normalization':normalize,
 'node:crypto':crypto,'./db':{WINDOW,database:()=>queryPool},'./summary-references':{summaryReferencesForProduct:async()=>[]},'./market-alias':{resolveMarketAlias:async(_,id)=>id},'./city-market-alias':alias,
 './city-package-equivalence':pack,'./category-path-sql':categoryPath,'./product-detail-diagnostics':diagnostics,'../product-filter-defaults':defaults});
const currentSQL=candidate.PRODUCT_FILTER_OPTIONS_SQL;
const optimizedSQL=candidate.PRODUCT_FILTER_OPTIONS_078_SQL;
const ambiguousQuotesSQL=candidate.PRODUCT_FILTER_OPTIONS_AMBIGUOUS_QUOTES_SQL;
const oldAmbiguousFallbackSQL=`WITH quotes AS (${candidate.PRICE_QUOTE_VALUES}) SELECT DISTINCT series,market_id,
 CASE WHEN series IN ('farmgate','mill') THEN market_name || ' · ' || region ELSE market_name END AS market_name,
 presentation,units,
 min(observed_on) OVER (PARTITION BY series,market_id,presentation,units) AS first_report_on,
 max(observed_on) OVER (PARTITION BY series,market_id,presentation,units) AS last_report_on
 FROM quotes WHERE product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
 AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY series,market_name,presentation,units`;
const readSnapshot=candidate.readProductFilterOptionsSnapshot;
assert.equal(candidate.PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256,
 'e804ec4ef27f4a19a194d6ff68933ac619524c591c5cb9b7551ab884cbe4c6a0',
 'the guarded fast path is pinned to the reviewed production 078 view');

const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
assert.equal(sha(old),'c32187975dda629afd3208e61dea6891cd07e0ebf6c933384ea2ae763c9f1b14');
const socket=process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled=socket?.startsWith('/tmp/agro-unified-catalog-pg-');
test('source-wide publication gate and corrected city option keys match immutable P-O reference',
 {skip:!enabled && 'Requires isolated AGRO_CATALOG_SQL_SOCKET'},async()=>{
 const db=new Client({host:socket,port:65443,database:'postgres'});
 await db.connect();try{
 await db.query("SET search_path=pg_temp; SET statement_timeout='8s'; SET TIME ZONE 'America/Bogota'");
 await db.query(`CREATE TEMP TABLE market(id text PRIMARY KEY,name text UNIQUE,city text,region text,municipality_id text);
 CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz,kind text,media_type text,source_url text);
 CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round int,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page int,PRIMARY KEY(document_id,source_locator));
 CREATE INDEX regional_price_product_market_day ON regional_price(product_id,market_name,observed_on);
 CREATE INDEX regional_price_market_day ON regional_price(market_name,observed_on);
 CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[],PRIMARY KEY(document_id,source_locator));
 CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text NOT NULL,corrected_product_name text NOT NULL,PRIMARY KEY(document_id,source_locator));
 CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
   corrected_min_price numeric,corrected_max_price numeric,corrected_min_unit_price numeric,corrected_max_unit_price numeric);
 CREATE TEMP TABLE verified_regional_category_overlay(document_id text,source_locator text,corrected_category text);
 CREATE TEMP TABLE source_archive_member(archive_id text,entry_name text,document_id text);
 CREATE TEMP TABLE dane_city_revision_source(source_url text,observed_on date,archive_id text,source_sha256 text);
 CREATE TEMP TABLE dane_city_cohort_current(archive_id text,source_url text,observed_on date);
 CREATE TEMP TABLE ingestion_asset(document_id text,kind text);
 CREATE INDEX correction_product ON regional_price_product_correction(corrected_product_id);
 CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text);
 CREATE TEMP TABLE price_observation(product_id text,market_id text,source_id text,unit text,observed_on date,
   price numeric,min_price numeric,max_price numeric,document_id text,source_locator text,source_url text,period text);
 CREATE TEMP VIEW published_price_observation AS SELECT * FROM price_observation;
 CREATE TEMP TABLE city_pdf_publication_conflict(id text PRIMARY KEY,document_id text NOT NULL,archive_id text,entry_name text,processor_version text,native_sha256 text,stored_sha256 text,details jsonb,detected_at timestamptz);
 CREATE TEMP TABLE city_pdf_category_resolution(conflict_id text PRIMARY KEY,document_id text,archive_id text,member_checkpoint_step text);
 CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer);
 CREATE TEMP VIEW verified_city_pdf_category_resolution AS
  SELECT a.* FROM city_pdf_category_resolution a WHERE EXISTS (
    SELECT 1 FROM ingestion_checkpoint cp WHERE cp.document_id=a.archive_id
      AND cp.processor_version='city-v8' AND cp.step=a.member_checkpoint_step AND cp.records=198);
 CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS
  SELECT c.* FROM city_pdf_publication_conflict c WHERE NOT EXISTS (
    SELECT 1 FROM verified_city_pdf_category_resolution a WHERE a.conflict_id=c.id AND a.document_id=c.document_id);
 CREATE TEMP VIEW published_regional_price AS
  SELECT r.document_id,r.source_locator,r.observed_on,r.product_id,r.product_name,r.market_name,r.category,
    r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
    coalesce(o.corrected_min_price,r.min_price) AS min_price,
    coalesce(o.corrected_max_price,r.max_price) AS max_price,r.unit,
    coalesce(o.corrected_min_unit_price,r.min_unit_price) AS min_unit_price,
    coalesce(o.corrected_max_unit_price,r.max_unit_price) AS max_unit_price,r.source_page
  FROM regional_price r LEFT JOIN verified_city_pdf_price_overlay o
    ON o.document_id=r.document_id AND o.source_locator=r.source_locator
  WHERE NOT EXISTS (
    SELECT 1 FROM unresolved_city_pdf_publication_conflict c WHERE c.document_id=r.document_id OFFSET 0)
  AND (
    NOT EXISTS (SELECT 1 FROM source_archive_member enrolled_member
      JOIN dane_city_revision_source enrolled_source ON enrolled_source.archive_id=enrolled_member.archive_id
      WHERE enrolled_member.document_id=r.document_id)
    OR EXISTS (SELECT 1 FROM source_archive_member active_member
      JOIN dane_city_cohort_current active_head ON active_head.archive_id=active_member.archive_id
      WHERE active_member.document_id=r.document_id)
    OR EXISTS (SELECT 1 FROM ingestion_asset direct_asset
      WHERE direct_asset.document_id=r.document_id AND direct_asset.kind='city-pdf')
    OR EXISTS (SELECT 1 FROM source_archive_member legacy_member
      WHERE legacy_member.document_id=r.document_id AND NOT EXISTS (
        SELECT 1 FROM dane_city_revision_source enrolled_legacy_parent
        WHERE enrolled_legacy_parent.archive_id=legacy_member.archive_id))
  );
 CREATE TEMP VIEW resolved_regional_price AS
  SELECT r.document_id,r.source_locator,r.observed_on,
    r.product_id,r.product_name,r.market_name,r.category,r.presentation,r.quantity,r.source_unit,
    r.round,r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
  FROM published_regional_price r WHERE NOT EXISTS (
    SELECT 1 FROM regional_price_product_correction c WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
  UNION ALL
  SELECT r.document_id,r.source_locator,r.observed_on,c.corrected_product_id,c.corrected_product_name,
    r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
    r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
  FROM regional_price_product_correction c JOIN published_regional_price r
   ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
 INSERT INTO market VALUES
 ('bog-a','Bogotá, Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('bog-b','Bogotá D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('bog-c','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('bog-d','Bogotà, Corabastos','Bogotá','Bogotá, D.C.','11001'),
 ('cali','Cali, Santa Elena','Cali','Valle del Cauca','76001'),
 ('other','Cali, Santa Helena','Cali','Valle del Cauca','76001');
 INSERT INTO product VALUES('mandarina-arrayana','Mandarina arrayana','Frutas'),
   ('arroz-de-primera','Arroz de primera','Granos'),('unrelated-decoy','Decoy product','Otros');
 INSERT INTO price_observation(product_id,market_id,source_id,unit,observed_on,price,min_price,max_price,source_url,period)
   VALUES('mandarina-arrayana','cali','monthly','kg','2026-08-31',5000,4900,5100,'https://example.test/monthly','monthly'),
   ('arroz-de-primera','cali','monthly','kg','2026-08-31',4000,3900,4100,'https://example.test/rice-monthly','monthly'),
   ('unrelated-decoy','cali','monthly','kg','2026-08-31',9999,9900,10000,'https://example.test/decoy','monthly');`);
 const captured=[];
 queryPool={query:async(sql,args)=>db.query(sql,args),connect:async()=>({
  query:async(sql,args)=>{captured.push(sql);return db.query(sql,args);},
  release:()=>{},
 })};
 const actualView=(await db.query(`SELECT pg_catalog.pg_get_viewdef(c.oid,true) AS definition
  FROM pg_catalog.pg_class c WHERE c.oid=pg_catalog.to_regclass('public.published_regional_price')`)).rows[0];
 assert(actualView?.definition,'owned PostgreSQL fixture must expose the current public 078 view');
 const actualViewHash=sha(actualView.definition);
 const actualViewSql=actualView.definition.trim().replace(/;\s*$/,'');
 assert.match(actualViewHash,/^[a-f0-9]{64}$/,'owned PostgreSQL fixture view fingerprint is recorded independently');
 assert.equal(candidate.PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256,
  'e804ec4ef27f4a19a194d6ff68933ac619524c591c5cb9b7551ab884cbe4c6a0',
  'production fast-path remains pinned to the independently reviewed migration-078 definition');
 const optimizedResult=await readSnapshot(queryPool,'mandarina-arrayana','',candidate.PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256);
 const optimized=optimizedResult.options;
 assert.equal(optimizedResult.ambiguousPackages,false);
 assert(captured.includes(currentSQL),'production fingerprint mismatch on this fixture selects safe view-backed fallback');
 assert.deepStrictEqual(optimized,(await db.query(currentSQL,['mandarina-arrayana',''])).rows);
 captured.length=0;
 const fallbackResult=await readSnapshot(queryPool,'mandarina-arrayana','', '0'.repeat(64));
 const fallback=fallbackResult.options;
 assert(captured.includes(currentSQL),'different view fingerprint falls back to the view-backed AI query');
 assert.deepStrictEqual(fallback,optimized,'fallback keeps option rows unchanged');
 captured.length=0;
 const fixtureOptimized=(await readSnapshot(queryPool,'mandarina-arrayana','',actualViewHash)).options;
 assert(captured.includes(optimizedSQL),'fixture fingerprint selects optimized SQL through the test seam only');
 assert(captured.indexOf('LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE')>0 &&
  captured.indexOf('LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE')<captured.indexOf(optimizedSQL),
  'view lock is acquired before fingerprint selection and query execution');
 assert.deepStrictEqual(fixtureOptimized,(await db.query(currentSQL,['mandarina-arrayana',''])).rows,
  'fixture optimized SQL preserves complete current-query rows');
 let continueCandidate;
 let candidateEntered;
 const candidateCanContinue=new Promise(resolve=>{continueCandidate=resolve;});
 const candidateIsEntered=new Promise(resolve=>{candidateEntered=resolve;});
 const lockHeldPool={connect:async()=>({
  query:async(sql,args)=>{
   if(sql===optimizedSQL){candidateEntered();await candidateCanContinue;}
   return db.query(sql,args);
  },release:()=>{},
 })};
 const heldRead=readSnapshot(lockHeldPool,'mandarina-arrayana','',actualViewHash);
 await candidateIsEntered;
 const ddlClient=new Client({host:socket,port:65443,database:'postgres'});
 await ddlClient.connect();
 try{
  await ddlClient.query("SET lock_timeout='500ms'");
  await assert.rejects(ddlClient.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`),
   error=>error.code==='55P03','compatible view replacement waits while helper holds ACCESS SHARE');
  continueCandidate();
  await heldRead;
  await ddlClient.query("SET lock_timeout='2s'");
  await ddlClient.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`);
 }finally{
  continueCandidate();
  await ddlClient.end();
 }
 let releases=0;
 const failingPool={connect:async()=>({
  query:async(sql,args)=>{
   if(sql===optimizedSQL)throw Object.assign(new Error('fixture query failure'),{code:'57014'});
   return db.query(sql,args);
  },release:()=>{releases++;},
 })};
 await assert.rejects(readSnapshot(failingPool,'mandarina-arrayana','',actualViewHash),/fixture query failure/);
 assert.equal(releases,1,'failed query releases its connection and is not converted into an empty result');
 assert.deepStrictEqual((await readSnapshot(queryPool,'mandarina-arrayana','',actualViewHash)).options,optimized,
  'a later request can retry after the failed query');
 async function queryCandidate(args){
  const baseline=await db.query(currentSQL,args);
  const optimizedResult=await db.query(optimizedSQL,args);
  assert.deepStrictEqual(optimizedResult.rows,baseline.rows,
   'optimized 078 query must preserve every ordered row from current SQL for '+args.join('/'));
  return optimizedResult;
 }
 const docs=[['d1','2025-01-01'],['d2','2025-01-02'],['d3','2025-01-03'],['d4','2025-01-04'],['d5','2025-01-05'],['d6','2025-01-06'],['d7','2025-01-07'],['d8','2025-01-08'],['d9','2025-01-09'],['d10','2025-01-10']];
 for(const [id,date] of docs)await db.query("INSERT INTO source_document VALUES($1,$2,'original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/example.pdf')",[id,date]);
 let n=0;
 async function quote({doc='d1',day='2025-01-01',product='mandarina-arrayana',market='Bogotá, Corabastos',name='Mandarina arrayana',price=100,minPrice=undefined,maxPrice=undefined,presentation='Canastilla',quantity=25,sourceUnit='Kilogramo',unit='package',round=1,minUnit=null,maxUnit=null,category='Frutas',path=['Frutas'],correction=null}={}){
  const locator='loc-'+(++n);
  await db.query(`INSERT INTO regional_price VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'Ronda',$12,$13,$14,$15,$16,1)`,[doc,locator,day,product,name,market,category,presentation,quantity,sourceUnit,round,minPrice??price,maxPrice??(price+10),unit,minUnit,maxUnit]);
  if(path)await db.query('INSERT INTO regional_classification VALUES($1,$2,$3)',[doc,locator,path]);
  if(correction)await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',[doc,locator,correction,correction]);
  return locator;
 }
 // Four reviewed literal market aliases: equal and unequal cross-literal dates.
 await quote();await quote({market:'Bogotá D.C., Corabastos'});
 await quote({doc:'d2',day:'2025-01-02'});await quote({doc:'d2',day:'2025-01-02',market:'Bogotá D.C., Corabastos',price:120});
 // Old revision conflicts, but latest revision for the same literal agrees.
 await quote({doc:'d1',day:'2025-01-03',price:80});await quote({doc:'d3',day:'2025-01-03',price:100});await quote({doc:'d3',day:'2025-01-03',market:'Bogotá, D.C., Corabastos'});
 // Corrected product enters target; target corrected away and must leave target.
 await quote({doc:'d4',day:'2025-01-04',product:'old-mandarina',correction:'mandarina-arrayana'});await quote({doc:'d4',day:'2025-01-04',market:'Bogotà, Corabastos'});
 await quote({doc:'d5',day:'2025-01-05',correction:'other-product',price:200});await quote({doc:'d5',day:'2025-01-05',market:'Bogotá D.C., Corabastos',price:100});
 // Every field of cross-literal conflict tuple and identity key stays material.
 await quote({doc:'d6',day:'2025-01-06'});await quote({doc:'d6',day:'2025-01-06',market:'Bogotá D.C., Corabastos',path:['Frutas','Cítricos']});
 await quote({doc:'d7',day:'2025-01-07',minUnit:10});await quote({doc:'d7',day:'2025-01-07',market:'Bogotá D.C., Corabastos',minUnit:11});
 await quote({doc:'d8',day:'2025-01-08',round:1});await quote({doc:'d8',day:'2025-01-08',market:'Bogotá D.C., Corabastos',round:2,price:120});
 await quote({doc:'d9',day:'2025-01-09',unit:'package'});await quote({doc:'d9',day:'2025-01-09',market:'Bogotá D.C., Corabastos',unit:'kg',price:120});
 await quote({doc:'d10',day:'2025-01-10',quantity:25});await quote({doc:'d10',day:'2025-01-10',market:'Bogotá D.C., Corabastos',quantity:50,price:120});
 const categoryOverlayLocator=await quote({doc:'d1',day:'2025-03-06',product:'overlay-category',market:'Bogotá, Corabastos'});
 await quote({doc:'d2',day:'2025-03-06',product:'overlay-category',market:'Bogotá D.C., Corabastos'});
 await db.query('INSERT INTO verified_regional_category_overlay VALUES($1,$2,$3)',
  ['d1',categoryOverlayLocator,'Frutas > Cítricos']);
 const categoryOverlayRows=(await queryCandidate(['overlay-category',''])).rows.filter(row=>row.series==='city');
 assert.equal(categoryOverlayRows.length,0,'verified category overlay participates in cross-literal conflict check');
 await quote({doc:'d10',day:'2025-02-01',market:'Cali, Santa Elena',product:'arroz-de-primera',name:'Arroz de primera',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:43000,path:['Granos']});
 await quote({doc:'d10',day:'2025-02-02',market:'Cali, Santa Elena',product:'arroz-de-primera',name:'Arroz de primera',presentation:'Bolsa',quantity:25,sourceUnit:'Unidades 500 GR',unit:'Unidades 500 GR',price:28000,path:['Granos']});
 await quote({doc:'d10',day:'2025-02-03',market:'Cali, Santa Elena',product:'arroz-de-primera',name:'Arroz de primera',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 50 GR',unit:'Unidad 50 GR',price:8000,path:['Granos']});

 // Migration 078 publication eligibility is document-wide. Cover the accepted
 // current head, stale enrolled head, unregistered legacy, direct-asset escape,
 // child shared by legacy and staged parents, and unresolved-conflict hold.
 await db.query(`INSERT INTO source_document VALUES
  ('d17','2025-06-01','original','application/pdf','https://www.dane.gov.co/078/current.pdf'),
  ('d18','2025-06-02','original','application/pdf','https://www.dane.gov.co/078/stale.pdf'),
  ('d19','2025-06-03','original','application/pdf','https://www.dane.gov.co/078/legacy.pdf'),
  ('d20','2025-06-04','original','application/pdf','https://www.dane.gov.co/078/direct.pdf'),
  ('d21','2025-06-05','original','application/pdf','https://www.dane.gov.co/078/shared.pdf'),
  ('d22','2025-06-06','original','application/pdf','https://www.dane.gov.co/078/conflict.pdf'),
  ('p17','2025-06-01','original','application/zip','https://www.dane.gov.co/078/current.zip'),
  ('p18','2025-06-02','original','application/zip','https://www.dane.gov.co/078/stale.zip'),
  ('p19','2025-06-03','original','application/zip','https://www.dane.gov.co/078/legacy.zip'),
  ('p20','2025-06-04','original','application/zip','https://www.dane.gov.co/078/direct.zip'),
  ('p21-legacy','2025-06-05','original','application/zip','https://www.dane.gov.co/078/old.zip'),
  ('p21-staged','2025-06-05','original','application/zip','https://www.dane.gov.co/078/new.zip')`);
 const correctedLocator=await quote({doc:'d17',day:'2024-02-01',product:'raw-078-product',correction:'effective-078-product',name:'Effective 078 Product',market:'Cali, Santa Elena'});
 await quote({doc:'d17',day:'2026-09-01',product:'effective-078-product',name:'Effective 078 Product',market:'Cali, Santa Elena'});
 await quote({doc:'d18',day:'2023-01-01',product:'stale-only-078',market:'Cali, Santa Elena'});
 await quote({doc:'d19',day:'2025-03-01',product:'legacy-only-078',market:'Cali, Santa Elena'});
 await quote({doc:'d20',day:'2025-04-01',product:'direct-only-078',market:'Cali, Santa Elena'});
 await quote({doc:'d21',day:'2025-05-01',product:'shared-only-078',market:'Cali, Santa Elena'});
 await quote({doc:'d22',day:'2026-10-01',product:'conflict-only-078',market:'Cali, Santa Elena'});
 for (const [parent,child] of [['p17','d17'],['p18','d18'],['p19','d19'],['p20','d20'],['p21-legacy','d21'],['p21-staged','d21']]) {
  await db.query('INSERT INTO source_archive_member VALUES($1,$2,$3)',[parent,child+'.pdf',child]);
 }
 for (const parent of ['p17','p18','p20','p21-staged']) {
  await db.query('INSERT INTO dane_city_revision_source VALUES($1,$2,$3,$4)',[
   `https://www.dane.gov.co/078/${parent}.zip`,'2025-06-01',parent,'a'.repeat(64)]);
 }
 await db.query('INSERT INTO dane_city_cohort_current VALUES($1,$2,$3)',[
  'p17','https://www.dane.gov.co/078/p17.zip','2025-06-01']);
 await db.query("INSERT INTO ingestion_asset VALUES('d20','city-pdf')");
 await db.query("INSERT INTO city_pdf_publication_conflict(id,document_id) VALUES('conflict-078','d22')");
 // A source-bound money overlay changes only quote values; option dimensions
 // remain sourced from the same visible document/locator set.
 await db.query('INSERT INTO verified_city_pdf_price_overlay VALUES($1,$2,777,888,77,88)', ['d17',correctedLocator]);
 const correctedOptions=(await queryCandidate(['effective-078-product','Valle del Cauca'])).rows.filter(row=>row.series==='city');
 const correctedOld=(await db.query(old,['effective-078-product','Valle del Cauca'])).rows.filter(row=>row.series==='city');
 assert.deepStrictEqual(correctedOptions,correctedOld,'078 current/legacy/direct and overlay dimension parity');
 assert.equal(correctedOptions.length,1,'same option dimension deduplicates every published source locator');
 assert.equal(correctedOptions[0].first_report_on,'2024-02-01','corrected raw product id supplies first date');
 assert.equal(correctedOptions[0].last_report_on,'2026-09-01','last accepted current-head report supplies last date');
 for (const [product,count] of [['stale-only-078',0],['legacy-only-078',1],['direct-only-078',1],['shared-only-078',1],['conflict-only-078',0]]) {
  const actual=(await queryCandidate([product,'Valle del Cauca'])).rows.filter(row=>row.series==='city');
  assert.equal(actual.length,count,`078 publication lane ${product}`);
 }
 const regionRows=(await queryCandidate(['effective-078-product','bogotá d.c.'])).rows.filter(row=>row.series==='city');
 assert.equal(regionRows.length,0,'region filtering is unchanged for an unmatching Unicode/case-insensitive region');
 const requests=[['mandarina-arrayana',''],['mandarina-arrayana','Bogotá D.C.'],['mandarina-arrayana','bogotá d.c.'],['mandarina-arrayana','Valle del Cauca'],['arroz-de-primera',''],['arroz-de-primera','Valle del Cauca'],['other-product',''],['missing','']];
 const cases=[];
 for(const args of requests){const oldRows=(await db.query(old,args)).rows,newRows=(await queryCandidate(args)).rows;assert.deepStrictEqual(newRows,oldRows,'Full options parity '+args.join('/'));cases.push({product:args[0],region:args[1],rows:newRows.length,requires_revision_resolution:newRows[0]?.requires_revision_resolution||false});}
 // Conflicting date contributes no city dimension when isolated in its own product.
 await quote({doc:'d1',day:'2025-03-01',product:'conflict-only',market:'Bogotá, Corabastos'});
 await quote({doc:'d2',day:'2025-03-01',product:'conflict-only',market:'Bogotá D.C., Corabastos',price:999});
 const conflictOld=(await db.query(old,['conflict-only',''])).rows, conflictNew=(await queryCandidate(['conflict-only',''])).rows;
 assert.deepStrictEqual(conflictNew,conflictOld);assert.equal(conflictNew.length,0);
 cases.push({product:'conflict-only',region:'',rows:0});

 // Each conflict field independently quarantines an otherwise identical typed alias key.
 const typedCases=[
  ['min_price', {minPrice:111}, true],
  ['max_price', {maxPrice:121}, true],
  ['min_unit_price', {minUnit:13}, true],
  ['max_unit_price', {maxUnit:19}, true],
  ['category_path', {path:['Frutas','Cítricos']}, true],
  ['presentation_separate', {presentation:'Caja',price:111}, 2],
  ['quantity_separate', {quantity:50,price:111}, 2],
  ['source_unit_separate', {sourceUnit:'Unidad',price:111}, 2],
  ['unit_separate', {unit:'kg',price:111}, 1],
  ['round_separate', {round:2,price:111}, 1],
 ];
 for(const [key,change,expected] of typedCases){
   const product='isolated-'+key;
   await quote({doc:'d1',day:'2025-03-02',product,market:'Bogotá, Corabastos',minUnit:10,maxUnit:18});
   await quote({doc:'d2',day:'2025-03-02',product,market:'Bogotà, Corabastos',minUnit:10,maxUnit:18,...change});
   const a=(await db.query(old,[product,''])).rows,b=(await queryCandidate([product,''])).rows;
   assert.deepStrictEqual(b,a,'Full isolated conflict parity '+key);
   assert.equal(b.length,expected===true?0:expected,'Expected isolated conflict status '+key);
   cases.push({product,region:'',rows:b.length});
 }
 // A stale revision for a literal cannot turn an agreeing latest pair into a conflict.
 await quote({doc:'d1',day:'2025-03-03',product:'revision-only',price:999});
 await quote({doc:'d3',day:'2025-03-03',product:'revision-only',price:100});
 await quote({doc:'d3',day:'2025-03-03',product:'revision-only',market:'Bogotá, D.C., Corabastos',price:100});
 let ro=(await db.query(old,['revision-only',''])).rows,rn=(await queryCandidate(['revision-only',''])).rows;
 assert.deepStrictEqual(rn,ro);assert.equal(rn.length,1);cases.push({product:'revision-only',rows:rn.length});
 // A correction into the target participates, while a correction away cannot conflict with it.
 await quote({doc:'d1',day:'2025-03-04',product:'raw-old',correction:'corrected-target',price:101});
 await quote({doc:'d2',day:'2025-03-04',product:'corrected-target',market:'Bogotá D.C., Corabastos',price:999});
 let ci=(await db.query(old,['corrected-target',''])).rows,cj=(await queryCandidate(['corrected-target',''])).rows;
 assert.deepStrictEqual(cj,ci);assert.equal(cj.length,0);cases.push({product:'corrected-target',rows:0});
 await quote({doc:'d1',day:'2025-03-05',product:'corrected-away',correction:'elsewhere',price:101});
 await quote({doc:'d2',day:'2025-03-05',product:'corrected-away',market:'Bogotá D.C., Corabastos',price:999});
 let ca=(await db.query(old,['corrected-away',''])).rows,cb=(await queryCandidate(['corrected-away',''])).rows;
 assert.deepStrictEqual(cb,ca);assert.equal(cb.length,1);cases.push({product:'corrected-away',rows:1});

 // Held publication and future source rows must never create selectable options.
 await db.query("INSERT INTO source_document VALUES ('d11','2025-01-11','original','application/pdf','https://www.dane.gov.co/held.pdf'),('d12','2025-01-12','original','application/pdf','https://www.dane.gov.co/future.pdf')");
 await quote({doc:'d11',day:'2025-04-01',product:'held-only',market:'Cali, Santa Elena',price:999});
 await db.query("INSERT INTO city_pdf_publication_conflict(id,document_id) VALUES ('conflict-held','d11')");
 await quote({doc:'d12',day:'2030-04-01',product:'future-only',market:'Cali, Santa Elena',price:100});
 await db.query("INSERT INTO price_observation(product_id,market_id,source_id,unit,observed_on,price,min_price,max_price,source_url,period) VALUES('future-only','cali','monthly','kg','2030-04-01',100,90,110,'https://example.test/future','monthly')");
 for (const product of ['held-only','future-only']) { const oldRows=(await db.query(old,[product,''])).rows;const newRows=(await queryCandidate([product,''])).rows;assert.deepStrictEqual(newRows,oldRows,'Held/future parity '+product);assert.equal(newRows.length,0);cases.push({product,region:'',rows:0}); }
 // Actual SQL059-style resolution lifts only the exact conflicting document.
 await db.query("INSERT INTO source_document VALUES ('d13','2025-01-13','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/resolved.pdf'),('d14','2025-01-14','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/blocked.pdf'),('d15','2025-01-15','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/rice.pdf'),('d16','2025-01-16','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/away.pdf'),('d23','2025-01-23','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/rice-literal.pdf'),('d24','2025-01-24','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/rice-bog-a.pdf'),('d25','2025-01-25','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/rice-bog-b.pdf'),('d26','2025-01-26','original','application/pdf','https://www.dane.gov.co/files/operaciones/SIPSA/unrelated-decoy.pdf')");
 await quote({doc:'d13',day:'2025-05-01',product:'resolved-only',market:'Cali, Santa Elena',price:123});
 await db.query("INSERT INTO city_pdf_publication_conflict(id,document_id) VALUES ('conflict-resolved','d13')");
 await db.query("INSERT INTO city_pdf_category_resolution VALUES ('conflict-resolved','d13','archive13','member13')");
 await db.query("INSERT INTO ingestion_checkpoint VALUES ('archive13','city-v8','member13',198)");
 await quote({doc:'d14',day:'2025-05-02',product:'sourcewide-held',market:'Cali, Santa Elena',price:456});
 await quote({doc:'d14',day:'2025-05-02',product:'unrelated-source',market:'Cali, Santa Elena',price:789});
 await quote({doc:'d14',day:'2025-05-02',product:'arroz-de-primera',market:'Cali, Santa Elena',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:41000,path:['Granos']});
 await db.query("INSERT INTO city_pdf_publication_conflict(id,document_id) VALUES ('conflict-unrelated','d14')");
 await quote({doc:'d15',day:'2025-05-03',product:'old-rice',correction:'arroz-de-primera',market:'Cali, Santa Elena',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:43210,path:['Granos']});
 await quote({doc:'d23',day:'2025-05-05',product:'arroz-de-primera',market:'Cali, Santa Elena',presentation:'Bolsa',quantity:25,sourceUnit:'Unidades 500 GR',unit:'Unidades 500 GR',price:43800,path:['Granos']});
 await quote({doc:'d26',day:'2025-05-08',product:'unrelated-decoy',market:'Cali, Santa Elena',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:90000,path:['Otros']});
 await quote({doc:'d24',day:'2025-05-06',product:'arroz-de-primera',market:'Bogotá, Corabastos',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:43800,path:['Granos']});
 await quote({doc:'d25',day:'2025-05-07',product:'arroz-de-primera',market:'Bogotá, Corabastos',presentation:'Bolsa',quantity:25,sourceUnit:'Unidades 500 GR',unit:'Unidades 500 GR',price:43900,path:['Granos']});
 await quote({doc:'d16',day:'2025-05-04',product:'arroz-de-primera',correction:'elsewhere',market:'Cali, Santa Elena',presentation:'Bolsa',quantity:25,sourceUnit:'Unidad 500 GR',unit:'Unidad 500 GR',price:98765,path:['Granos']});
 for (const [product,count] of [['resolved-only',1],['sourcewide-held',0],['unrelated-source',0],['old-rice',0]]) {
   const a=(await db.query(old,[product,''])).rows,b=(await queryCandidate([product,''])).rows;
   assert.deepStrictEqual(b,a,'SQL059 document gate parity '+product);assert.equal(b.length,count);cases.push({product,rows:count});
 }
 const riceOld=(await db.query(old,['arroz-de-primera','Valle del Cauca'])).rows;
 const riceNew=(await queryCandidate(['arroz-de-primera','Valle del Cauca'])).rows;
 assert.deepStrictEqual(riceNew,riceOld,'Corrected compact rice and corrected-away parity');
 assert(riceNew.some(r=>r.units==='25 × 500 g'),'Effective corrected product ID preserves compact-unit guard');
 cases.push({product:'arroz-de-primera',region:'Valle del Cauca',rows:riceNew.length,corrected_compact_units:true});

 // The ambiguity fallback is product/region scoped in both source arms and
 // runs inside the same 078-guarded repeatable-read snapshot as the option gate.
 captured.length=0;
 for(const region of ['', 'Valle del Cauca']){
  const scoped=(await readSnapshot(queryPool,'arroz-de-primera',region,actualViewHash));
  const legacy=(await db.query(oldAmbiguousFallbackSQL,['arroz-de-primera',region])).rows;
  assert.equal(scoped.ambiguousPackages,true,'rice literal package spellings exercise the ambiguous path '+region);
  assert.deepStrictEqual(scoped.options,legacy,'Ambiguous fallback full ordered option parity '+region);
  if(region===''){
   assert.equal(captured[0],'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
   assert.equal(captured[1],'LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE');
   assert.match(captured[2],/pg_get_viewdef/,'view hash is checked in the transaction');
   assert.equal(captured[3],optimizedSQL);
   assert.equal(captured[4],ambiguousQuotesSQL);
   assert.equal(captured[5],'COMMIT','ambiguity query commits after same-snapshot fallback');
  }
 }
 const outsideRegion=await readSnapshot(queryPool,'arroz-de-primera','bogotá d.c.',actualViewHash);
 assert.equal(outsideRegion.ambiguousPackages,false,'no Bogotá package rows trigger an irrelevant ambiguity fallback');
 assert.deepStrictEqual(outsideRegion.options,
  (await db.query(optimizedSQL,['arroz-de-primera','bogotá d.c.'])).rows,
  'nonmatching region remains on the guarded options query');
 const scopedUnknownView=await readSnapshot(queryPool,'arroz-de-primera','Valle del Cauca','0'.repeat(64));
 assert.equal(scopedUnknownView.ambiguousPackages,true);
 assert(captured.includes(currentSQL),'unknown view hash retains the safe view-backed options query');
 assert.deepStrictEqual(scopedUnknownView.options,
  (await db.query(oldAmbiguousFallbackSQL,['arroz-de-primera','Valle del Cauca'])).rows,
  'unknown published-view definitions retain the old view-backed eligibility and result semantics');
 assert.notEqual(actualViewHash,candidate.PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256,
  'the private migration fixture has its own fingerprint and is not presented as production 078');
 // The source fixture is the repository migration-generated view, while the
 // production fast-path hash is separately hard-pinned above. Inject this
 // fixture's fingerprint only into the in-memory test module to exercise the
 // recognized-view branch against its independently populated publication data.
 candidate.PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256=actualViewHash;

 // Exercise the same guarded 078 gate on selected ordinary city quotes, not
 // just filter options. This cohort covers corrected IDs, current and stale
 // enrolled revisions, legacy/shared children, direct assets and held sources.
 await db.query("INSERT INTO product VALUES('effective-078-product','Effective 078 Product','Grains'),('partition-ordinary','Partitioned ordinary product','Grains')");
 await db.query(`INSERT INTO source_document VALUES
  ('d27','2025-06-07','original','application/pdf','https://www.dane.gov.co/operaciones/ordinary-27.pdf'),
  ('d28','2025-06-08','original','application/pdf','https://www.dane.gov.co/operaciones/ordinary-28.pdf'),
  ('d29','2025-06-09','original','application/pdf','https://www.dane.gov.co/operaciones/ordinary-29.pdf'),
  ('d30','2025-06-10','original','application/pdf','https://www.dane.gov.co/operaciones/ordinary-30.pdf'),
  ('d31','2025-06-11','original','application/pdf','https://www.dane.gov.co/operaciones/ordinary-31.pdf')`);
 for(const [doc,market,day] of [
  ['d27','Ordinary Market A','2025-06-07'],['d28','Ordinary Market B','2025-06-08'],
  ['d29','Ordinary Market C','2025-06-09'],['d30','Ordinary Market D','2025-06-10'],['d31','Ordinary Market E','2025-06-11'],
 ]) await db.query('INSERT INTO market VALUES($1,$2,$3,$4,$5)',[
  market.toLowerCase().replaceAll(' ','-'),market,market.replace('Market','Town'),'Valle del Cauca','76001']);
 await quote({doc:'d17',day:'2026-09-01',product:'effective-078-product',market:'Cali, Santa Elena',price:120});
 await quote({doc:'d13',day:'2025-05-09',product:'effective-078-product',market:'Cali, Santa Elena',price:110});
 await quote({doc:'d18',day:'2025-05-10',product:'effective-078-product',market:'Cali, Santa Elena',price:100});
 await quote({doc:'d19',day:'2025-05-11',product:'effective-078-product',market:'Cali, Santa Elena',price:130});
 await quote({doc:'d20',day:'2025-05-12',product:'effective-078-product',market:'Cali, Santa Elena',price:140});
 await quote({doc:'d21',day:'2025-05-13',product:'effective-078-product',market:'Cali, Santa Elena',price:150});
 await quote({doc:'d22',day:'2025-05-14',product:'effective-078-product',market:'Cali, Santa Elena',price:160});
 for(const [doc,market,day] of [
  ['d27','Ordinary Market A','2025-06-07'],['d28','Ordinary Market B','2025-06-08'],
  ['d29','Ordinary Market C','2025-06-09'],['d30','Ordinary Market D','2025-06-10'],['d31','Ordinary Market E','2025-06-11'],
 ]) await quote({doc,day,product:'partition-ordinary',market,presentation:'Bulto',quantity:1,sourceUnit:'Kilogramo',unit:'Kilogramo',price:100});

 const productArgs=['effective-078-product','Valle del Cauca',{
  series:'city',market:'cali',presentation:'Canastilla',units:'25 Kilogramo',history:'all',
 }];
 captured.length=0;
 const selectedKnown=await candidate.filteredProduct(...productArgs);
 const selectedKnownSql=captured.find(sql=>sql.includes('ordinary_eligible_docs'));
 assert(selectedKnownSql,'known 078 selected quote query is captured');
 assert.match(selectedKnownSql,/AND \(\s*NOT EXISTS \(\s*SELECT 1 FROM source_archive_member enrolled_member/s,
  'known 078 selected query substitutes document-wide eligibility before selected rows');
 assert(!selectedKnownSql.includes('accepted.document_id=k.document_id OFFSET 0'),
  'known selected-query gate no longer performs a published-view EXISTS for every quote');
 assert.deepStrictEqual(selectedKnown.history.map(point=>point.date),
  ['2024-02-01','2025-05-09','2025-05-11','2025-05-12','2025-05-13','2026-09-01'],
  'selected history preserves resolved, legacy, direct, shared and current-head documents while excluding stale and held sources');

 const selectedFailureCalls=[];let selectedFailureReleases=0;
 const selectedFailurePool=queryPool;
 queryPool={query:(...args)=>db.query(...args),connect:async()=>({
  query:async(sql,args)=>{
   selectedFailureCalls.push(sql);
   if(typeof sql==='string' && sql.includes('ordinary_eligible_docs'))throw new Error('selected fixture failure');
   return db.query(sql,args);
  },release:()=>{selectedFailureReleases++;},
 })};
 try{
  await assert.rejects(candidate.filteredProduct(...productArgs),error=>
   error.stage==='selected_quotes' && error.message==='PRODUCT_DETAIL_STAGE_FAILED');
  assert.equal(selectedFailureCalls[0],'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  assert(selectedFailureCalls[1].startsWith('LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE'));
  const failedSelectedIndex=selectedFailureCalls.findIndex(sql=>typeof sql==='string' && sql.includes('ordinary_eligible_docs'));
  assert(failedSelectedIndex>0,'failure is raised by the selected history query after the options read');
  assert(selectedFailureCalls.slice(failedSelectedIndex+1).includes('ROLLBACK'),
   'selected-query failure rolls its guarded snapshot back');
  assert.equal(selectedFailureCalls.slice(failedSelectedIndex+1).includes('COMMIT'),false,
   'the failed selected snapshot never commits, while the preceding options snapshot may');
  assert.equal(selectedFailureReleases,2,'options and failed selected snapshots each release their checked-out client');
 }finally{queryPool=selectedFailurePool;}

 // Unknown view definitions retain the exact legacy selected-query predicate.
 await db.query(`CREATE OR REPLACE VIEW public.published_regional_price AS
  SELECT * FROM (${actualViewSql}) original_view WHERE TRUE`);
 try{
  captured.length=0;
  const selectedUnknown=await candidate.filteredProduct(...productArgs);
  assert.deepStrictEqual(selectedUnknown,selectedKnown,'unknown-view selected history preserves every ordered result/provenance field');
  const unknownSelectedSql=captured.find(sql=>sql.includes('ordinary_eligible_docs'));
  assert(unknownSelectedSql?.includes('accepted.document_id=k.document_id OFFSET 0'),
   'unknown view definition keeps the original published-view selected-query gate');
 }finally{
  await db.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`);
 }

 // The partitioned reader also pins the view and holds its lock until the
 // final chunk/merge has committed; the unknown-hash baseline remains equal.
 const partitionArgs=['partition-ordinary','Valle del Cauca',{
  series:'city',market:'',presentation:'Bulto',units:'1 Kilogramo',history:'all',
 }];
 captured.length=0;
 const partitionKnown=await candidate.filteredProduct(...partitionArgs);
 assert.equal(partitionKnown.markets.length,5);
 assert.equal(partitionKnown.history.length,5);
 const partitionSelectedSql=captured.find(sql=>sql.includes('ordinary_eligible_docs'));
 assert.match(partitionSelectedSql,/source_archive_member enrolled_member/,
  'partition chunks use the 078 direct eligibility only under the guarded view hash');
 await db.query(`CREATE OR REPLACE VIEW public.published_regional_price AS
  SELECT * FROM (${actualViewSql}) original_view WHERE TRUE`);
 try{
  const partitionUnknown=await candidate.filteredProduct(...partitionArgs);
  assert.deepStrictEqual(partitionUnknown,partitionKnown,'partitioned output is full-row equal under unknown-view fallback');
 }finally{
  await db.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`);
 }

 // DDL cannot replace the recognized view between its hash read and the
 // selected query; the ACCESS SHARE lock spans selected SQL and commit.
 let unblockSelected;let selectedEntered;
 const selectedCanContinue=new Promise(resolve=>{unblockSelected=resolve;});
 const selectedIsEntered=new Promise(resolve=>{selectedEntered=resolve;});
 const baseConnect=queryPool.connect;
 queryPool.connect=async()=>({
  query:async(sql,args)=>{
   if(sql.includes('ordinary_eligible_docs')){selectedEntered();await selectedCanContinue;}
   return db.query(sql,args);
  },release:()=>{},
 });
 const selectedHeld=candidate.filteredProduct(...productArgs);
 await selectedIsEntered;
 const selectedDdlClient=new Client({host:socket,port:65443,database:'postgres'});
 await selectedDdlClient.connect();
 try{
  await selectedDdlClient.query("SET lock_timeout='500ms'");
  await assert.rejects(selectedDdlClient.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`),
   error=>error.code==='55P03','selected-query view replacement waits while the snapshot holds ACCESS SHARE');
  unblockSelected();
  await selectedHeld;
  await selectedDdlClient.query("SET lock_timeout='2s'");
  await selectedDdlClient.query(`CREATE OR REPLACE VIEW public.published_regional_price AS ${actualViewSql}`);
 }finally{
  unblockSelected();queryPool.connect=baseConnect;await selectedDdlClient.end();
 }

 const monthlyArm=ambiguousQuotesSQL.slice(0,ambiguousQuotesSQL.indexOf('UNION ALL'));
 const cityArm=ambiguousQuotesSQL.slice(ambiguousQuotesSQL.indexOf('UNION ALL'));
 assert.match(monthlyArm,/WHERE o\.product_id=\$1 AND/,'monthly branch is constrained before the union');
 assert.match(cityArm,/WHERE r\.product_id=\$1 AND/,'city branch is constrained before its DISTINCT ON winner selection');
 assert.match(cityArm,/regional_price_product_correction/,'corrected IDs remain in the city source branch');
 assert.match(ambiguousQuotesSQL,/WHERE product_id=\$1 AND .*observed_on<=/s,
  'outer dated option projection and exact region filtering remain intact');
 // Production-shaped volume locally only; compare complete ordered options.
 await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
 SELECT 'd10','volume-'||g::text,date '2025-05-01'+(g%1000),'mandarina-arrayana','Mandarina arrayana',
 'Cali, Santa Elena','Frutas','Canastilla',25,'Kilogramo',1,'Ronda',100,110,'package',1
 FROM generate_series(1,3167) g`);
 await db.query('ANALYZE regional_price; ANALYZE regional_price_product_correction; ANALYZE regional_classification; ANALYZE source_document; ANALYZE market');
 const oldVolume=(await db.query(old,['mandarina-arrayana',''])).rows,newVolume=(await queryCandidate(['mandarina-arrayana',''])).rows;
 assert.deepStrictEqual(newVolume,oldVolume,'Full options parity with 3167 extra city quotes');
 assert.equal(cases.length,29,'Keep the 29 adversarial source cases in the tracked regression');
 // Printed municipality names need their department in farm/mill choices.
 // The source name and stable identity remain unchanged, including homonyms.
 await db.query('ALTER TABLE market DROP CONSTRAINT market_name_key');
 await db.query(`INSERT INTO market VALUES
  ('mill-meta','GRANADA · molinos','Granada','Meta','50313'),
  ('mill-antioquia','GRANADA · molinos','Granada','Antioquia','05313'),
  ('farm-meta','GRANADA · leche en finca','Granada','Meta','50313')`);
 await db.query(`INSERT INTO product VALUES('rice-display','Rice display','Grains'),('milk-display','Milk display','Dairy');
  INSERT INTO price_observation(product_id,market_id,source_id,unit,observed_on,price,min_price,max_price,source_url,period) VALUES
  ('rice-display','mill-meta','dane-rice-mill','kg','2025-05-01',100,90,110,'https://example.test/rice','monthly'),
  ('rice-display','mill-antioquia','dane-rice-mill','kg','2025-05-01',100,90,110,'https://example.test/rice','monthly'),
  ('milk-display','farm-meta','dane-milk-farm','litre','2025-05-01',100,90,110,'https://example.test/milk','monthly')`);
 for (const [product,expected] of [
  ['rice-display',[['mill-antioquia','GRANADA · molinos · Antioquia'],['mill-meta','GRANADA · molinos · Meta']]],
  ['milk-display',[['farm-meta','GRANADA · leche en finca · Meta']]],
 ]) {
  const original=(await db.query(old,[product,''])).rows;
  const clarified=(await queryCandidate([product,''])).rows;
  assert.deepStrictEqual(clarified.map(r=>[r.market_id,r.market_name]),expected);
  assert.deepStrictEqual(clarified.map(({market_name,...rest})=>rest),original.map(({market_name,...rest})=>rest));
 }
 assert.equal((await db.query("SELECT name FROM market WHERE id='mill-meta'")).rows[0].name,'GRANADA · molinos');
 assert.equal(sha(currentSQL),'32da018751fbb6e2b6c28569377ed13bc07baefe7f614e0ff649f43394267967');
}finally{await db.end()}});
