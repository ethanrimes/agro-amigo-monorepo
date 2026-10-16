/* Product detail options/classifications: production-shaped TEMP PostgreSQL. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
// Match production db.ts, including numeric JSON aggregation equivalence.
types.setTypeParser(1700, Number);
types.setTypeParser(20, Number);
types.setTypeParser(1082, value => value);
const root = path.join(__dirname, '../../..');
const server = path.join(__dirname, '../src/lib/server');
const WINDOW = fs.readFileSync(path.join(server, 'db.ts'), 'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
function moduleSQL(filename, mocks, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server, filename), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, require: (name) => name === 'server-only' ? {} : mocks[name], performance, ...globals,
  });
  return exports;
}
const classificationModule = moduleSQL('../price-classification.ts', {});
const sharedLabels = JSON.parse(fs.readFileSync(path.join(root, 'shared/label-normalization.json'), 'utf8'));
const normalizationModule = moduleSQL('../label-normalization.ts', {
  '../../../../shared/label-normalization.json': { default: sharedLabels },
});
const categoryPath = moduleSQL('category-path-sql.ts', {});
const cityAlias = moduleSQL('city-market-alias.ts', { './category-path-sql': categoryPath });
const cityPackage = moduleSQL('city-package-equivalence.ts', {});
const detailDiagnostics = moduleSQL('product-detail-diagnostics.ts', {});
const defaultDimensions = moduleSQL('../product-filter-defaults.ts', {});
const queryPool = { query: (...args) => db.query(...args), connect: async (...args) => {
  // Partition tests replace `db` with a mock that owns a checkout function.
  // The normal fixture `db` is already connected, so reuse its query method.
  if (typeof db.connect === 'function' && db.connect !== Client.prototype.connect) {
    const connected = await db.connect(...args);
    return connected && typeof connected.query === 'function' ? connected : {
      query: (...queryArgs) => db.query(...queryArgs), release: () => {},
    };
  }
  return { query: (...queryArgs) => db.query(...queryArgs), release: () => {} };
} };
const quoteModule = moduleSQL('price-quotes.ts', { 'node:crypto': require('node:crypto'), './category-path-sql': categoryPath, '../price-classification': classificationModule, '../label-normalization': normalizationModule, './db': { WINDOW, database: () => queryPool }, './summary-references': { summaryReferencesForProduct: async () => [] }, './market-alias': { resolveMarketAlias: async (_, id) => id }, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage, './product-detail-diagnostics': detailDiagnostics, '../product-filter-defaults': defaultDimensions });
const catalogModule = moduleSQL('catalog-sql.ts', {
  './db': { WINDOW }, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage,
  './category-path-sql': categoryPath,
});
const allHistoryModule = moduleSQL('comparison-corabastos-all-history.ts', {
  'node:crypto': require('node:crypto'), './db': { database: () => queryPool },
  './city-market-alias': cityAlias, './price-quotes': quoteModule,
  './category-path-sql': categoryPath,
});
const regionalModule = moduleSQL('regional-prices.ts', { './db': {}, './snapshot-cache': {snapshotCache:()=>()=>{}}, './city-publication-epoch': {}, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage, './category-path-sql': categoryPath });
const regionalOracleSQL = fs.readFileSync(path.join(__dirname, 'fixtures/regional-prices-pre-indexed-alias.oracle.sql'), 'utf8');
const schema = fs.readFileSync(path.join(root, 'pipelines/ingestion/schema.sql'), 'utf8');
const view = schema.split('CREATE OR REPLACE VIEW published_price_observation AS')[1].split('GRANT SELECT ON published_price_observation')[0];
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const tables = ['product','market','source_document','ingestion_asset','price_observation','regional_price','regional_classification'];
let db;
beforeEach(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' }); await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='10s'; SET TIME ZONE 'America/Bogota'");
  for (const table of tables) await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
  await db.query(`CREATE TEMP TABLE regional_price_product_correction (
    document_id text NOT NULL,source_locator text NOT NULL,corrected_product_id text NOT NULL,
    corrected_product_name text NOT NULL,PRIMARY KEY(document_id,source_locator));
    CREATE INDEX ON regional_price_product_correction(corrected_product_id,corrected_product_name);
    CREATE TEMP TABLE city_pdf_publication_conflict(document_id text PRIMARY KEY);
    CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS
      SELECT document_id FROM city_pdf_publication_conflict;
    CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS (
      SELECT 1 FROM city_pdf_publication_conflict blocked WHERE blocked.document_id=r.document_id OFFSET 0);
    CREATE TEMP TABLE category_overlay_fixture (
      document_id text NOT NULL,source_locator text NOT NULL,corrected_category text NOT NULL,
      PRIMARY KEY(document_id,source_locator));
    CREATE TEMP VIEW verified_regional_category_overlay AS
      SELECT document_id,source_locator,corrected_category FROM category_overlay_fixture;
    CREATE TEMP TABLE verified_city_pdf_price_overlay (
      document_id text NOT NULL,source_locator text NOT NULL,
      corrected_min_price numeric NOT NULL,corrected_max_price numeric NOT NULL,
      corrected_min_unit_price numeric,corrected_max_unit_price numeric,
      PRIMARY KEY(document_id,source_locator));
    CREATE TEMP VIEW resolved_regional_price AS
    SELECT r.* FROM published_regional_price r WHERE NOT EXISTS (
      SELECT 1 FROM regional_price_product_correction c
      WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
    UNION ALL
    SELECT r.document_id,r.source_locator,r.observed_on,
      c.corrected_product_id,c.corrected_product_name,r.market_name,r.category,
      r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
      r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
    FROM regional_price_product_correction c JOIN published_regional_price r
      ON r.document_id=c.document_id AND r.source_locator=c.source_locator`);
  const reviewDefinition = schema.match(/CREATE TABLE IF NOT EXISTS price_observation_review \([\s\S]*?\n\);/)[0];
  await db.query(reviewDefinition.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'));
  await db.query('CREATE TEMP VIEW published_price_observation AS ' + view);
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_008_catalog_reads.sql'), 'utf8'));
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_011_classification_reads.sql'), 'utf8'));
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_012_product_options_reads.sql'), 'utf8'));
  await db.query('CREATE INDEX regional_price_lookup ON regional_price(product_id,market_name,observed_on DESC); CREATE INDEX regional_market_latest ON regional_price(market_name,observed_on DESC)');
  await db.query(`INSERT INTO product(id,name,category) VALUES('city','Ciudad','Frutas'),('monthly','Mensual','Verduras'),('milk','Leche','Lácteos'),('rice','Arroz','Cereales');
    INSERT INTO market(id,name,city,region) VALUES('a','A','Ciudad A','Uno'),('b','B','Ciudad B','Dos'),('empty','Empty','Ciudad E','Vacía');
    INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','Old','DANE','https://example.invalid/old','application/pdf','original','',decode('00','hex'),'2026-09-01'),
    ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','New','DANE','https://example.invalid/new','application/pdf','original','',decode('00','hex'),'2026-09-25')`);
});
afterEach(async () => { if (db) await db.end(); db = undefined; });
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
const withoutSources = rows => rows.map(({sources,...point}) => point);
let seq = 0;
async function regional({ product = 'city', name = 'Nombre literal', market = 'A', day = -1, price = 10, presentation = 'Bulto', quantity = 25, unit = 'Kilogramo', round = 1, doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  const locator='row-' + (++seq);
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    VALUES($1,$2,CURRENT_DATE+$3::integer,$4,$5,$6,'Frutas',$7,$8,$9,$10,'Ronda',$11::numeric,$11::numeric+2,'package',1)`,
    [doc, locator, day, product, name, market, presentation, quantity, unit, round, price]);
  return locator;
}
async function monthly({ product = 'monthly', market = 'a', month = 1, price = 100, source = 'dane-sipsa', unit = 'kg', doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  await db.query(`INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    VALUES($1,$2,$3,(date_trunc('month',CURRENT_DATE)-($4||' months')::interval+interval '1 month - 1 day')::date,'monthly',$5,$6,'https://example.invalid/',$7)`, [product, market, source, month, unit, price, doc]);
}

const untilToday = "observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";
const oldOptions = `WITH quotes AS (${quoteModule.PRICE_QUOTES}) SELECT DISTINCT series,market_id,
  CASE WHEN series IN ('farmgate','mill') THEN market_name || ' · ' || region
    ELSE market_name END AS market_name,presentation,units
  FROM quotes WHERE product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ')) AND ${untilToday} ORDER BY series,market_name,presentation,units`;
async function options(product, region='') {
  const raw = (await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,[product,region])).rows;
  const actual = raw.some(row => row.requires_revision_resolution) ? (await db.query(oldOptions,[product,region])).rows : raw.map(({requires_revision_resolution,first_report_on,last_report_on,...row}) => row);
  assert.deepEqual(actual,(await db.query(oldOptions,[product,region])).rows);
  return {raw,actual};
}
async function classify() {
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,string_to_array(category,' > ') FROM regional_price ON CONFLICT DO NOTHING`);
}
check('duplicate normalized city market labels expose source-specific package dates without changing price history',async()=>{
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
    ('upper','BARRANQUILLA, GRANABASTOS','Barranquilla','Atlántico','08001'),
    ('canonical','Barranquilla, Granabastos','Barranquilla','Atlántico','08001')`);
  const original=await regional({market:'BARRANQUILLA, GRANABASTOS',price:90000,
    presentation:'Caja de cartón',quantity:10});
  const current=await regional({market:'Barranquilla, Granabastos',price:110000,
    presentation:'Caja de cartón',quantity:10});
  const otherPackage=await regional({market:'BARRANQUILLA, GRANABASTOS',price:1,quantity:25});
  const withheld=await regional({market:'BARRANQUILLA, GRANABASTOS',price:999999,
    presentation:'Caja de cartón',quantity:10,doc:'b'.repeat(64)});
  await db.query("UPDATE regional_price SET observed_on='2021-09-01' WHERE source_locator=$1",[original]);
  await db.query("UPDATE regional_price SET observed_on='2026-09-07' WHERE source_locator=$1",[current]);
  await db.query("UPDATE regional_price SET observed_on='2020-01-01' WHERE source_locator=$1",[otherPackage]);
  await db.query("UPDATE regional_price SET observed_on='2022-01-01' WHERE source_locator=$1",[withheld]);
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)',['b'.repeat(64)]);
  const detail=await quoteModule.filteredProduct('city','Atlántico',{
    series:'city',presentation:'Caja de cartón',units:'10 Kilogramo',market:'upper',history:'all'});
  assert.deepEqual(Array.from(detail.options.markets,x=>[x.id,x.name,x.literal_name,x.first_report_on,x.last_report_on]),[
    ['upper','Barranquilla, Granabastos','BARRANQUILLA, GRANABASTOS','2021-09-01','2021-09-01'],
    ['canonical','Barranquilla, Granabastos','Barranquilla, Granabastos','2026-09-07','2026-09-07'],
  ]);
  assert.deepEqual(Array.from(detail.history,x=>[x.date,x.price,x.market_count]),[['2021-09-01',90001,1]]);
  assert.equal(detail.filters.market,'upper');
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,4);
});
check('department case aliases include both literal markets in picker, current card and history',async()=>{
  await db.query("UPDATE market SET region=CASE id WHEN 'a' THEN 'ATLÁNTICO' WHEN 'b' THEN 'Atlántico' ELSE region END");
  await regional({market:'A',price:10});
  await regional({market:'B',price:30});
  for(const region of ['Atlántico','ATLÁNTICO','atlántico']) {
    const raw=(await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,['city',region])).rows;
    assert.deepEqual(raw.map(row=>row.market_id).sort(),['a','b']);
    const detail=await quoteModule.filteredProduct('city',region,{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(detail.current.price,21);
    assert.equal(detail.markets.length,2);
    assert.equal(detail.history.at(-1).price,21);
  }
});
check('multi-market ordinary selection retains only source-bound winning overlays and excludes held documents',async()=>{
  await db.query(`CREATE TEMP TABLE selected_test_overlay(document_id text,source_locator text,corrected_category text);
    CREATE OR REPLACE TEMP VIEW verified_regional_category_overlay AS
      SELECT document_id,source_locator,corrected_category FROM selected_test_overlay`);
  const resolved=fs.readFileSync(path.join(root,'pipelines/ingestion/migrations/20261005_057_city_category_overlay.sql'),'utf8')
    .split('CREATE OR REPLACE VIEW resolved_regional_price AS')[1].split('GRANT SELECT ON resolved_regional_price')[0];
  await db.query('CREATE OR REPLACE TEMP VIEW resolved_regional_price AS '+resolved);
  const old=await regional({price:10,day:-500});
  const winner=await regional({price:40,round:2,day:-1});
  const loser=await regional({price:900,round:1,day:-1});
  const other=await regional({price:80,market:'B',day:-1});
  const held=await regional({price:99999,round:2,day:-1,doc:'b'.repeat(64)});
  await db.query(`INSERT INTO selected_test_overlay VALUES
    (repeat('a',64),$1,'Frutas > Otras frutas'),
    (repeat('a',64),$2,'Carnes > Pollo')`,[winner,loser]);
  await db.query('INSERT INTO city_pdf_publication_conflict VALUES($1)',['b'.repeat(64)]);
  for(const history of ['all','recent']) {
    const detail=await quoteModule.filteredProduct('city','',{
      series:'city',presentation:'Bulto',units:'25 Kilogramo',history});
    assert.equal(detail.current.price,61);
    assert.deepEqual(Array.from(detail.current.sources,x=>x.source_locator).sort(),[winner,other].sort());
    assert.equal(detail.markets.find(x=>x.id==='a').category,'Frutas > Otras frutas');
    assert.ok(detail.history.every(x=>x.sources.every(s=>s.source_locator!==held&&s.source_locator!==loser)));
    assert.equal(detail.history.length,history==='all'?2:1);
    assert.equal(detail.history[0].sources.some(s=>s.source_locator===old),history==='all');
    const expected=(await db.query(`WITH q AS (${quoteModule.PRICE_QUOTES})
      SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count
      FROM q WHERE product_id='city' AND series='city' AND presentation='Bulto' AND units='25 Kilogramo'
      AND ${history==='all'?untilToday:WINDOW} GROUP BY observed_on ORDER BY observed_on`)).rows;
    assert.deepEqual(withoutSources(detail.history),expected);
  }
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,5);
});
check('multi-market monthly selection avoids city scope and preserves its complete contributing sources',async()=>{
  await monthly({price:100,market:'a'});await monthly({price:300,market:'b'});
  const captured=[];const query=db.query.bind(db);
  db.query=(sql,...args)=>{if(typeof sql==='string')captured.push(sql);return query(sql,...args);};
  const detail=await quoteModule.filteredProduct('monthly','',{
    series:'monthly',presentation:'Por unidad de medida',units:'1 kg',history:'all'});
  assert.equal(detail.current.price,200);
  assert.equal(detail.current.market_count,2);
  assert.deepEqual(Array.from(detail.current.sources,x=>x.market_id).sort(),['a','b']);
  assert.ok(captured.every(sql=>!sql.includes('ordinary_market_names AS MATERIALIZED')));
});
check('three documented Corabastos city labels form one historical market without rewriting source identities',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
  for(let i=0;i<3;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  for(let i=0;i<3;i++) {
    const observed=['2021-12-29','2024-01-02','2026-10-03'][i];
    const first=await regional({market:names[i],day:-5+i,price:100+i*100,round:1});
    const second=await regional({market:names[i],day:-5+i,price:120+i*100,round:2,doc:'b'.repeat(64)});
    await db.query('UPDATE regional_price SET observed_on=$1::date WHERE source_locator=ANY($2::text[])',
      [observed,[first,second]]);
  }
  await regional({market:'B',day:-3,price:900});
  const otherPackage = await regional({market:names[2],day:-3,price:700,quantity:12.5});
  // Keep this second package on the fixture's latest report day. A relative
  // date can eventually advance it past the fixed 25 kg report and change
  // which report the latest-day map legitimately shows.
  await db.query('UPDATE regional_price SET observed_on=$1::date WHERE source_locator=$2',
    ['2026-10-03',otherPackage]);
  await monthly({product:'city',market:ids[2],price:1000});
  const raw=(await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,['city','Bogotá, D.C.'])).rows;
  assert.deepEqual(raw.filter(x=>x.series==='city').map(x=>[x.market_id,x.market_name,x.units]).sort(),
    [[ids[2],names[2],'12.5 Kilogramo'],[ids[2],names[2],'25 Kilogramo']].sort());
  assert.deepEqual(raw.filter(x=>x.series==='monthly').map(x=>x.market_id),[ids[2]]);
  const map=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows
    .filter(x=>x.product_id==='city' && x.market_id===ids[2] && x.quantity===25);
  assert.deepEqual(map.map(x=>[x.round,x.source_market_id,x.market_name,x.min_price]).sort(),
    [[1,ids[2],names[2],300],[2,ids[2],names[2],320]].sort());
  for(const savedId of ids) {
    const detail=await quoteModule.filteredProduct('city','Bogotá, D.C.',
      {series:'city',market:savedId,presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(detail.filters.market,ids[2]);
    assert.deepEqual(detail.history.map(x=>x.price),[121,221,321]);
    assert.deepEqual(detail.history.map(x=>x.date),['2021-12-29','2024-01-02','2026-10-03']);
    assert.deepEqual(detail.history.map(x=>x.market_count),[1,1,1]);
    assert.deepEqual(detail.history.map(x=>x.sources[0].market_name),names);
    assert.deepEqual(detail.history.map(x=>x.sources[0].source_market_id),ids);
    assert.deepEqual(detail.history.map(x=>x.sources[0].market_id),[ids[2],ids[2],ids[2]]);
    assert.equal(detail.current.price,321);
    assert.equal(detail.markets.length,1);
  }
  const monthlyDetail=await quoteModule.filteredProduct('city','Bogotá, D.C.',
    {series:'monthly',market:ids[2],history:'all'});
  assert.equal(monthlyDetail.current.price,1000);
  assert.equal(monthlyDetail.history.length,1);
  assert.equal((await db.query('SELECT count(*)::integer n FROM regional_price')).rows[0].n,8);
});
check('city overview category labels use only verified corrections without altering source prices or provenance',async()=>{
  const corrected=await regional({price:500,quantity:10});
  const unchanged=await regional({price:700,market:'B',quantity:20});
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,
      ARRAY['Categoría anterior']::text[] FROM regional_price`);
  await db.query(`CREATE TEMP TABLE overview_category_corrections(document_id text,source_locator text,corrected_category text);
    CREATE OR REPLACE TEMP VIEW verified_regional_category_overlay AS
      SELECT document_id,source_locator,corrected_category FROM overview_category_corrections`);
  await db.query('INSERT INTO overview_category_corrections VALUES($1,$2,$3)',
    ['a'.repeat(64),corrected,'Frutas > Cítricos']);
  const rows=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  const projected=rows.find(x=>x.source_locator===corrected);
  assert.equal(projected.category,'Frutas > Cítricos');
  assert.deepEqual(projected.category_path,['Frutas','Cítricos']);
  assert.equal(projected.document_id,'a'.repeat(64));
  assert.equal(projected.market_name,'A');
  assert.equal(projected.quantity,10);
  assert.equal(projected.min_price,500);
  assert.equal(projected.max_price,502);
  assert.deepEqual(rows.find(x=>x.source_locator===unchanged).category_path,['Categoría anterior']);
  assert.equal((await db.query('SELECT category FROM regional_price WHERE source_locator=$1',[corrected])).rows[0].category,'Frutas');
  assert.equal((await db.query('SELECT category_path FROM regional_classification WHERE source_locator=$1',[corrected])).rows[0].category_path[0],'Categoría anterior');
});
check('city browsing groups verified Corabastos labels while retaining every source spelling and identity',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos'];
  const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
  for(let i=0;i<3;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  const locators=[];
  for(let i=0;i<4;i++) locators.push(await regional({market:names[i],quantity:20+i,price:100+i}));
  const unknown=await regional({market:'Corabastos sin ubicación verificada',quantity:30,price:900});
  const rows=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  const known=rows.filter(x=>locators.includes(x.source_locator));
  assert.equal(known.length,4);
  assert.deepEqual([...new Set(known.map(x=>x.display_market_name))],['Bogotá, D.C., Corabastos']);
  assert.deepEqual(known.map(x=>x.market_name).sort(),names.slice().sort());
  assert.deepEqual(known.map(x=>x.source_market_id).filter(Boolean).sort(),ids.slice().sort());
  assert.equal(known.filter(x=>x.source_market_id===null).length,1);
  assert.ok(known.every(x=>x.market_id===ids[2] && x.market_region==='Bogotá, D.C.'));
  const uncurated=rows.find(x=>x.source_locator===unknown);
  assert.equal(uncurated.display_market_name,'Corabastos sin ubicación verificada');
  assert.equal(uncurated.market_id,null);
  assert.equal(uncurated.market_region,null);
  const literalRows=(await db.query('SELECT source_locator,market_name,min_price FROM regional_price ORDER BY source_locator')).rows;
  assert.equal(literalRows.length,5);
  for(let i=0;i<4;i++) {
    const raw=literalRows.find(x=>x.source_locator===locators[i]);
    assert.equal(raw.market_name,names[i]);
    assert.equal(raw.min_price,100+i);
  }
});
check('the native 2022 grave-accent Corabastos source keeps its literal and no invented source market ID',async()=>{
  const canonical='sipsa-bogota-d-c-corabastos';
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`,[canonical]);
  for(const [round,low,high] of [[1,27000,30000],[2,26000,28000]]) {
    const locator=await regional({product:'city',name:'Naranja Sweet',market:'Bogotà, Corabastos',
      day:-1,price:low,presentation:'Canastilla',quantity:20,round});
    await db.query('UPDATE regional_price SET min_price=$1,max_price=$2,observed_on=$3 WHERE source_locator=$4',
      [low,high,'2022-01-03',locator]);
  }
  const rows=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' AND series='city'`)).rows;
  assert.equal(rows.length,1);
  assert.equal(rows[0].market_id,canonical);
  assert.equal(rows[0].source_market_id,null);
  assert.equal(rows[0].market_name,'Bogotà, Corabastos');
  assert.equal(rows[0].price,27000);
  assert.deepEqual((await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,['city','Bogotá, D.C.'])).rows
    .filter(x=>x.series==='city').map(x=>x.market_id),[canonical]);
  const saved=await quoteModule.filteredProduct('city','Bogotá, D.C.',
    {series:'city',market:canonical,presentation:'Canastilla',units:'20 Kilogramo',history:'all'});
  assert.equal(saved.current.price,27000);
  assert.equal(saved.history[0].sources[0].market_name,'Bogotà, Corabastos');
  assert.equal(saved.history[0].sources[0].source_market_id,null);
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,2);
});
check('Corabastos cross-label price conflicts fail closed, while same-label revisions and other packages stay published',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
  for(let i=0;i<3;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  await regional({market:names[0],day:-1,price:100});
  await regional({market:names[0],day:-1,price:300,doc:'b'.repeat(64)});
  let quotes=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' AND units='25 Kilogramo'`)).rows;
  assert.equal(quotes.length,1);
  assert.equal(quotes[0].price,301);
  assert.equal(quotes[0].source_market_id,ids[0]);
  await regional({market:names[1],day:-1,price:500});
  quotes=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' AND units='25 Kilogramo'`)).rows;
  assert.equal(quotes.length,0);
  await regional({market:names[2],day:-1,price:700,quantity:12.5});
  quotes=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city'`)).rows;
  assert.deepEqual(quotes.map(x=>x.units),['12.5 Kilogramo']);
  assert.equal(quotes[0].source_market_id,ids[2]);
  const options=(await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,['city','Bogotá, D.C.'])).rows;
  assert.deepEqual(options.filter(x=>x.series==='city').map(x=>x.units),['12.5 Kilogramo']);
  assert.equal((await db.query('SELECT count(*)::integer n FROM regional_price')).rows[0].n,4);
});
check('cross-label category path or per-unit price disagreement excludes only that typed city quote',async()=>{
  const canonical='sipsa-bogota-d-c-corabastos';
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`,[canonical]);
  const a=await regional({market:'Bogotá, D.C., Corabastos',price:100,quantity:20});
  const b=await regional({market:'Bogotà, Corabastos',price:100,quantity:20});
  const other=await regional({market:'Bogotà, Corabastos',price:200,quantity:12.5});
  await db.query(`UPDATE regional_price SET min_unit_price=5,max_unit_price=5.1
    WHERE source_locator=ANY($1::text[])`,[[a,b]]);
  const quoteRows=async()=>(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' AND series='city' ORDER BY units`)).rows;
  assert.equal((await quoteRows()).length,2);
  await db.query('UPDATE regional_price SET min_unit_price=5.00,max_unit_price=5.10 WHERE source_locator=$1',[b]);
  assert.equal((await quoteRows()).length,2,'numeric scale alone cannot quarantine a quote');
  await db.query('UPDATE regional_price SET min_unit_price=5.2 WHERE source_locator=$1',[b]);
  assert.deepEqual((await quoteRows()).map(x=>x.units),['12.5 Kilogramo']);
  await db.query('UPDATE regional_price SET min_unit_price=5 WHERE source_locator=$1',[b]);
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,ARRAY['Frutas','Cítricos'] FROM regional_price WHERE source_locator=$1`,[a]);
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,ARRAY['Frutas','Otras frutas'] FROM regional_price WHERE source_locator=$1`,[b]);
  assert.deepEqual((await quoteRows()).map(x=>x.units),['12.5 Kilogramo']);
  await db.query(`UPDATE regional_classification SET category_path=ARRAY['Frutas','Cítricos'] WHERE source_locator=$1`,[b]);
  assert.equal((await quoteRows()).length,2);
  await db.query("UPDATE regional_price SET category='Frutas > Cítricos' WHERE source_locator=$1",[b]);
  assert.equal((await quoteRows()).length,2,'broad raw category and full raw path agree through audited classification');
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,3);
  assert.equal(other.startsWith('row-'),true);
});
check('city map retains an uncurated literal market when the alias predicate sees no market join',async()=>{
  await regional({market:'Sin mercado curado',price:123});
  const rows=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  assert.equal(rows.length,1);
  assert.equal(rows[0].market_name,'Sin mercado curado');
  assert.equal(rows[0].market_id,null);
  assert.equal(rows[0].min_price,123);
});
check('corrected product drives quote detail, options and classification without mutating evidence',async()=>{
  await regional({product:'rice',name:'Raw label',price:40});
  await classify();
  await db.query(`INSERT INTO regional_price_product_correction
    SELECT document_id,source_locator,'city','Corrected label'
    FROM regional_price WHERE product_id='rice'`);
  const city=await options('city');
  assert.equal(city.actual.length,1);
  assert.equal((await options('rice')).actual.length,0);
  const detail=await quoteModule.filteredProduct('city','',{series:'city',history:'all'});
  assert.equal(detail.markets.length,1);
  assert.equal(detail.markets[0].product_name,'Corrected label');
  assert.deepEqual((await db.query(quoteModule.PRODUCT_CLASSIFICATIONS_SQL,['city'])).rows,
    [{category_path:['Frutas']}]);
  assert.deepEqual((await db.query('SELECT product_id,product_name FROM regional_price')).rows,
    [{product_id:'rice',product_name:'Raw label'}]);
});
check('Banano criollo 2024 city history keeps its exact PDF identity',async()=>{
  const documentId='50d273edf3673067e4901722a4e38a76f6b4b91c2a227200799f18d4a012ec49';
  const marketId='sipsa-popayan-plaza-de-mercado-del-barrio-bolivar';
  const marketName='Popayán, Plaza de mercado del barrio Bolívar';
  await db.query("INSERT INTO product(id,name,category) VALUES('banano-criollo','Banano criollo','Frutas')");
  await db.query('INSERT INTO market(id,name,city,region) VALUES($1,$2,$3,$4)',[marketId,marketName,'Popayán','Cauca']);
  await db.query(`INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES($1,'Popayán 05-07-2024','DANE','https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-5jul2024.zip','application/pdf','original','2024-07-05',decode('00','hex'),now())`,[documentId]);
  await regional({product:'banano-criollo',name:'Banano criollo',market:marketName,day:-1,
    presentation:'Kilogramo',quantity:1,price:2349,doc:documentId});
  await db.query(`UPDATE regional_price SET observed_on=DATE '2024-07-05',min_price=2300,max_price=2400
    WHERE product_id='banano-criollo'`);
  const locator=(await db.query("SELECT source_locator FROM regional_price WHERE product_id='banano-criollo'")).rows[0].source_locator;
  const result=await quoteModule.filteredProduct('banano-criollo','Cauca',{
    series:'city',market:marketId,presentation:'Kilogramo',units:'1 Kilogramo',history:'all'});
  assert.equal(result.history.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(result.history[0])),{
    date:'2024-07-05',price:2350,market_count:1,
    sources:[{document_id:documentId,source_locator:locator,source_page:1,market_id:marketId,source_market_id:marketId,market_name:marketName,source_units:'1 Kilogramo'}],
  });
});
check('a dated multi-market average lists only its contributing revision winners',async()=>{
  await regional({day:-1,market:'A',price:100,doc:'a'.repeat(64)});
  await regional({day:-1,market:'A',price:120,round:2,doc:'b'.repeat(64)});
  await regional({day:-1,market:'B',price:200,doc:'a'.repeat(64)});
  const result=await quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
  assert.equal(Number(result.history[0].price),161);
  assert.equal(Number(result.history[0].market_count),2);
  const sources=result.history[0].sources.sort((a,b)=>a.market_id.localeCompare(b.market_id));
  assert.deepEqual(sources.map(s=>[s.market_id,s.document_id,s.source_page]),
    [['a','b'.repeat(64),1],['b','a'.repeat(64),1]]);
  assert.ok(sources.every(s=>s.source_locator && s.market_name));
  const single=await quoteModule.filteredProduct('city','Uno',{series:'city',market:'a',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
  assert.equal(single.history[0].sources.length,1);
  assert.equal(single.history[0].sources[0].document_id,'b'.repeat(64));
});
check('verified money correction changes only the selected quote, preserving the raw source row',async()=>{
  const documentId='a'.repeat(64);
  const locator=await regional({market:'A',price:100,doc:documentId});
  await db.query(`INSERT INTO verified_city_pdf_price_overlay
    (document_id,source_locator,corrected_min_price,corrected_max_price)
    VALUES($1,$2,6000,7000)`,[documentId,locator]);
  const result=await quoteModule.filteredProduct('city','Uno',{
    series:'city',market:'a',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
  assert.equal(result.current.price,6500);
  assert.equal(result.history[0].price,6500);
  assert.equal(result.history[0].sources[0].document_id,documentId);
  assert.equal(result.history[0].sources[0].source_locator,locator);
  const raw=(await db.query('SELECT min_price,max_price FROM regional_price WHERE document_id=$1 AND source_locator=$2',
    [documentId,locator])).rows[0];
  assert.deepEqual(raw,{min_price:100,max_price:102});
});
check('concurrent exact-filter readers share work and the next read sees a new price',async()=>{
  await regional({market:'A',price:100});
  await regional({market:'B',price:200});
  const original=db.query.bind(db);
  let optionReads=0;
  db.query=(sql,args)=>{
    if(sql===quoteModule.PRODUCT_FILTER_OPTIONS_SQL) optionReads++;
    return original(sql,args);
  };
  try {
    const filter={series:'city',market:'a',presentation:'Bulto',units:'25 Kilogramo',history:'all'};
    const first=await Promise.all(Array.from({length:12},()=>quoteModule.filteredProduct('city','',filter)));
    assert.equal(optionReads,1);
    assert.ok(first.every(result=>result===first[0]));
    assert.equal(Number(first[0].current.price),101);
    const other=await quoteModule.filteredProduct('city','',{...filter,market:'b'});
    assert.equal(Number(other.current.price),201);
    assert.equal(optionReads,2);
    await regional({market:'A',price:300,round:2,doc:'b'.repeat(64)});
    const fresh=await quoteModule.filteredProduct('city','',filter);
    assert.equal(Number(fresh.current.price),301);
    assert.equal(optionReads,3);
    assert.equal(fresh.history[0].sources[0].document_id,'b'.repeat(64));
  } finally { db.query=original; }
});
check('simultaneous different packages share dimensions and retain independent prices and fresh packages',async()=>{
  await regional({market:'A',quantity:25,price:100});
  await regional({market:'A',quantity:12.5,price:500});
  const original=db.query.bind(db);let optionReads=0,release;
  const gate=new Promise(resolve=>{release=resolve});
  db.query=async(sql,args)=>{
    if(sql===quoteModule.PRODUCT_FILTER_OPTIONS_SQL){optionReads++;await gate;}
    return original(sql,args);
  };
  try {
    const filter={series:'city',market:'a',presentation:'Bulto',history:'all'};
    const first=quoteModule.filteredProduct('city','',{...filter,units:'25 Kilogramo'});
    const second=quoteModule.filteredProduct('city','',{...filter,units:'12.5 Kilogramo'});
    for(let n=0;n<100 && optionReads===0;n++)await new Promise(resolve=>setTimeout(resolve,2));
    // Both have reached the common dimensions read before it is released.
    await new Promise(resolve=>setTimeout(resolve,10));release();
    const [a,b]=await Promise.all([first,second]);assert.equal(optionReads,1);
    assert.equal(a.current.price,101);assert.equal(a.filters.units,'25 Kilogramo');
    assert.equal(b.current.price,501);assert.equal(b.filters.units,'12.5 Kilogramo');
    await regional({market:'A',quantity:5,price:700});
    const fresh=await quoteModule.filteredProduct('city','',{...filter,units:'5 Kilogramo'});
    assert.equal(fresh.filters.units,'5 Kilogramo');assert.equal(fresh.current.price,701);
    assert.equal(optionReads,2);
  } finally {release();db.query=original;}
});
check('all retained package, market, round, revision and source options match the price oracle',async()=>{
  await regional({day:-1200,presentation:'Caja',quantity:10});
  await regional({day:-2,presentation:'BULTO',quantity:25});
  await regional({day:-2,presentation:'bulto',quantity:25,round:2,price:25,doc:'b'.repeat(64)});
  await regional({day:-1,presentation:'Canastilla',quantity:12.5,market:'B'});
  await regional({day:100,presentation:'Future'});
  await regional({day:-1,presentation:'Unknown',market:'Not curated'});
  await monthly({product:'city',price:100});
  await monthly({product:'city',source:'dane-milk-farm',unit:'litre',price:110});
  await monthly({product:'city',source:'dane-rice-mill',unit:'unit',price:120});
  await monthly({product:'city',market:'b',price:500,doc:'b'.repeat(64)});
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES('https://example.invalid/review','monthly',repeat('b',64),'review')");
  for(const region of ['','Uno','Dos','absent']) await options('city',region);
  const result=await options('city'); assert.ok(result.actual.some(row=>row.presentation==='Caja'));
  assert.ok(!result.raw.some(row=>row.requires_revision_resolution));
});
check('ambiguous whitespace labels preserve only actual dated revision winners',async()=>{
  await regional({day:-2,presentation:' Bulto',unit:'Kilogramo',price:10});
  await regional({day:-2,presentation:'Bulto',unit:'Kilogramo',price:20,round:2,doc:'b'.repeat(64)});
  const {raw,actual}=await options('city');
  assert.ok(raw.some(row=>row.requires_revision_resolution));
  assert.deepEqual(actual.map(row=>row.presentation),['Bulto']);
  await classify();
  const result=await quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo'});
  assert.equal(result.options.presentations.length,1); assert.equal(result.options.presentations[0],'Bulto');
  assert.equal(Number(result.current.price),21);
});
check('package prefilter retains normalized-identity competitors before exact display filtering',async()=>{
  for(const [product,paddedPresentation,paddedUnit]of [
    ['pad-presentation',' Bulto ','Kilogramo'],
    ['pad-unit','Bulto',' Kilogramo '],
    ['pad-both',' Bulto ',' Kilogramo '],
  ]){
    await db.query("INSERT INTO product(id,name,category) VALUES($1,$1,'Frutas')",[product]);
    await regional({product,day:-2,price:10});
    await regional({product,day:-1,price:20}); // Requested display matches this old revision.
    await regional({product,day:-1,price:30,doc:'b'.repeat(64),presentation:paddedPresentation,unit:paddedUnit});
    const {actual:choices}=await options(product);
    for(const choice of choices){
      const result=await quoteModule.filteredProduct(product,'',{series:'city',presentation:choice.presentation,units:choice.units,history:'all'});
      const expected=(await db.query(`WITH quotes AS (${quoteModule.PRICE_QUOTES})
        SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count
        FROM quotes WHERE product_id=$1 AND presentation=$2 AND units=$3 AND ${untilToday}
        GROUP BY observed_on ORDER BY observed_on`,[product,choice.presentation,choice.units])).rows;
      assert.deepEqual(withoutSources(result.history),expected,`${product}: ${JSON.stringify(choice)}`);
      // An older matching display must not resurrect a defeated dated revision.
      assert.ok(!result.history.some(row=>Number(row.price)===21));
      assert.deepEqual(result.current ? withoutSources([result.current])[0] : null,expected.at(-1)||null);
    }
    const canonical=await quoteModule.filteredProduct(product,'',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(Number(canonical.current.price),11);
  }
});
check('classification preserves stored corrections with a raw-category fallback for unclassified rows',async()=>{
  await regional({day:-1400}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Cítricos corregidos']");
  await regional({day:-1}); // Intentionally missing separately published classification.
  const previous=(await db.query(`SELECT DISTINCT c.category_path FROM regional_classification c JOIN regional_price r USING(document_id,source_locator) WHERE r.product_id=$1 ORDER BY c.category_path`,['city'])).rows;
  const actual=(await db.query(quoteModule.PRODUCT_CLASSIFICATIONS_SQL,['city'])).rows;
  assert.deepEqual(previous,[{category_path:['Frutas','Cítricos corregidos']}]);
  assert.deepEqual(actual,[{category_path:['Frutas']},...previous]);
});

check('late classification preserves every dated round/revision winner and its literal evidence',async()=>{
  await regional({day:-500,price:10});
  await regional({day:-3,price:20});
  await regional({day:-3,price:30,doc:'b'.repeat(64)});
  await regional({day:-3,price:40,round:2}); // Higher round wins before newer retrieval.
  await regional({day:-1,price:50,round:2});
  await regional({day:-1,price:60,round:2,doc:'b'.repeat(64)});
  await regional({day:-1,price:70,round:2,doc:'b'.repeat(64)}); // Same document: lexical locator tie break.
  await regional({day:-1,price:100,market:'B'});
  await regional({day:-1,price:500,quantity:12.5}); // Distinct package cannot collapse.
  await regional({day:100,price:900});
  await regional({day:-1,market:'Unknown market',price:1000});
  await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Clasificación corregida'] WHERE document_id=repeat('b',64)");
  const oracle=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id=$1 ORDER BY observed_on,market_id,units`,['city'])).rows;
  const values=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTE_VALUES}) q WHERE product_id=$1 ORDER BY observed_on,market_id,units`,['city'])).rows;
  const actual=await quoteModule.withQuoteClassifications(values);
  assert.deepEqual(JSON.parse(JSON.stringify(actual)),oracle);
  // Reconstruct the exact SQL winner rather than assuming insertion order equals
  // lexical locator order (row-9 sorts after row-10).
  const latest=oracle.filter(r=>r.market_id==='a'&&r.units==='25 Kilogramo'&&r.document_id==='b'.repeat(64)).at(-1);
  assert.ok(latest.source_locator); assert.ok([61,71].includes(latest.price));
  assert.ok(oracle.some(r=>r.price===41&&r.document_id==='a'.repeat(64)));
  assert.equal(oracle.filter(r=>r.market_name==='Unknown market').length,0);
});

check('filtered history/current/regions match classified SQL oracle while paths use exact current winner',async()=>{
  await regional({day:-500,price:10}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Vieja','Solo histórica']");
  await regional({day:-3,price:20});
  await regional({day:-3,price:30,doc:'b'.repeat(64)});
  await regional({day:-3,price:40,round:2});
  await regional({day:-1,price:50,round:2});
  await regional({day:-1,price:60,round:2,doc:'b'.repeat(64)});
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
    SELECT document_id,source_locator,ARRAY['Frutas','Corrección del original'] FROM regional_price
    WHERE document_id=repeat('b',64) AND observed_on=CURRENT_DATE-1`);
  await regional({day:-1,price:100,market:'B'}); // Missing c row falls back to r.category.
  await regional({day:-1,price:500,quantity:12.5});
  await regional({day:100,price:900});
  for(const [region,market,history]of [['','','all'],['Uno','','all'],['','b','all'],['','','recent']]){
    const request={series:'city',presentation:'Bulto',units:'25 Kilogramo',market,history};
    const result=await quoteModule.filteredProduct('city',region,request);
    const filter=`product_id=$1 AND ($2='' OR region=$2) AND series='city' AND presentation='Bulto' AND units='25 Kilogramo' AND ($3='' OR market_id=$3) AND ${history==='all'?untilToday:WINDOW}`;
    const args=['city',region,market];
    const expectedHistory=(await db.query(`WITH q AS (${quoteModule.PRICE_QUOTES}) SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count FROM q WHERE ${filter} GROUP BY observed_on ORDER BY observed_on`,args)).rows;
    const expectedMarkets=(await db.query(`WITH q AS (${quoteModule.PRICE_QUOTES}) SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date FROM q WHERE ${filter} ORDER BY market_id,observed_on DESC`,args)).rows;
    assert.deepEqual(withoutSources(result.history),expectedHistory);
    assert.deepEqual(JSON.parse(JSON.stringify(result.markets)),expectedMarkets);
    assert.deepEqual(result.current ? withoutSources([result.current])[0] : null,expectedHistory.at(-1));
    if(!region&&!market&&history==='all'){
      assert.deepEqual(result.history.map(r=>Number(r.price)),[11,41,81]);
      assert.deepEqual(JSON.parse(JSON.stringify(result.classification)),[['Frutas','Corrección del original'],['Frutas']]);
      assert.equal(result.markets.find(r=>r.id==='a').document_id,'b'.repeat(64));
    }
    if(history==='recent')assert.equal(result.history.length,2);
  }
});

check('late path lookup preserves stored corrections, missing-path fallback and non-city paths',async()=>{
  await regional({price:10}); await classify();
  await db.query("UPDATE regional_classification SET category_path=ARRAY['Frutas','Cítricos corregidos']");
  await regional({market:'B',price:20});
  await monthly({product:'city',price:100});
  const expected=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTES}) q WHERE product_id='city' ORDER BY series,market_id`)).rows;
  const raw=(await db.query(`SELECT * FROM (${quoteModule.PRICE_QUOTE_VALUES}) q WHERE product_id='city' ORDER BY series,market_id`)).rows;
  assert.notDeepEqual(raw,expected);
  const actual=await quoteModule.withQuoteClassifications(raw);
  assert.deepEqual(JSON.parse(JSON.stringify(actual)),expected);
  assert.deepEqual(actual.find(r=>r.series==='city'&&r.market_id==='a').category_path,['Frutas','Cítricos corregidos']);
  assert.deepEqual(actual.find(r=>r.series==='city'&&r.market_id==='b').category_path,['Frutas']);
  assert.deepEqual(actual.find(r=>r.series==='monthly').category_path,['Frutas']);
});

check('asset and locator reviews stay excluded from current prices, history and options',async()=>{
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:1700});
  await monthly({product:'milk',market:'b',source:'dane-milk-farm',unit:'litre',price:3000,doc:'b'.repeat(64)});
  await monthly({product:'milk',market:'a',month:2,source:'dane-milk-farm',unit:'litre',price:9999});
  await db.query("UPDATE price_observation SET source_locator='reviewed-old-cell' WHERE price=9999");
  await db.query(`INSERT INTO price_observation_review(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,reason)
    SELECT document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit,'Exact original identity invalid' FROM price_observation WHERE price=9999`);
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES('https://example.invalid/milk-review','milk',repeat('b',64),'review')");
  const actual=await quoteModule.filteredProduct('milk','',{series:'farmgate',units:'1 litro',history:'all'});
  assert.equal(actual.history.length,1);assert.equal(actual.markets.length,1);assert.equal(Number(actual.current.price),1700);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.options.markets.map(r=>r.id))),['a']);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.classification)),[['Lácteos']]);
});
check('monthly litre/rice and city package detail prices and explicit filters remain exact',async()=>{
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:1700});
  await monthly({product:'rice',source:'dane-rice-mill',unit:'kg',price:2200});
  await regional({price:100,day:-1}); await regional({price:200,day:-1,market:'B'}); await classify();
  for(const [id,series,units,price,count] of [['milk','farmgate','1 litro',1700,1],['rice','mill','1 kg',2200,1],['city','city','25 Kilogramo',151,2]]) {
    const result=await quoteModule.filteredProduct(id,'',{series,units,presentation:series==='city'?'Bulto':'Por unidad de medida'});
    assert.equal(Number(result.current.price),price); assert.equal(result.markets.length,count);
    assert.equal(result.filters.series,series); assert.equal(result.filters.units,units);
  }
  assert.equal(await quoteModule.filteredProduct('absent','',{}),null);
});

check('market choices belong to the selected series and package; saved unavailable choices stay explicit',async()=>{
  await monthly({product:'city',market:'a',price:100});
  await regional({market:'B',presentation:'Bulto',quantity:25,price:200});
  await regional({market:'Empty',presentation:'Bulto',quantity:50,price:300});
  const ids = result => Array.from(result.options.markets, row => row.id);
  const monthlyResult=await quoteModule.filteredProduct('city','',{
    series:'monthly',presentation:'Por unidad de medida',units:'1 kg',history:'all'});
  assert.deepEqual(ids(monthlyResult),['a']);
  assert.equal(monthlyResult.current.price,100);
  const cityResult=await quoteModule.filteredProduct('city','',{
    series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
  assert.deepEqual(ids(cityResult),['b']);
  assert.equal(cityResult.current.price,201);
  const bigger=await quoteModule.filteredProduct('city','',{
    series:'city',presentation:'Bulto',units:'50 Kilogramo',history:'all'});
  assert.deepEqual(ids(bigger),['empty']);
  assert.equal(bigger.current.price,301);
  const saved=await quoteModule.filteredProduct('city','',{
    series:'monthly',market:'b',presentation:'Por unidad de medida',units:'1 kg',history:'all'});
  assert.equal(saved.current,null);
  assert.equal(saved.history.length,0);
  assert.equal(saved.filters.market,'b');
  assert.deepEqual(ids(saved),['a','b']);
  assert.match(saved.options.markets.find(row=>row.id==='b').name,/sin reportes para estos filtros/);
});

check('farmgate PDF current and history links retain their printed table pages',async()=>{
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:892,month:1});
  await monthly({product:'milk',source:'dane-milk-farm',unit:'litre',price:887,month:2});
  await monthly({product:'rice',source:'dane-rice-mill',unit:'kg',price:2400});
  await db.query(`UPDATE price_observation SET source_locator=CASE price
    WHEN 892 THEN 'PDF page 3,col 1,line 11; parser milk-pdf-v10; precio en finca, COP/litro'
    WHEN 887 THEN 'PDF page 4,col 2,line 8; parser milk-pdf-v10; precio en finca, COP/litro'
    ELSE '2021!row 8; precio en molino, COP/kg' END`);
  const result=await quoteModule.filteredProduct('milk','',{
    series:'farmgate',units:'1 litro',presentation:'Por unidad de medida',history:'all'});
  assert.equal(result.current.price,892);
  assert.equal(result.current.sources[0].source_page,3);
  assert.equal(result.markets[0].source_page,3);
  assert.deepEqual(Array.from(result.history,p=>p.sources[0].source_page),[4,3]);
  const workbook=await quoteModule.filteredProduct('rice','',{
    series:'mill',units:'1 kg',presentation:'Por unidad de medida',history:'all'});
  assert.equal(workbook.current.sources[0].source_page,1);
});

check('city history stays selective with a large unrelated price table',async()=>{
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    SELECT repeat('a',64),'bulk-'||n,CURRENT_DATE-(n%100),
      CASE WHEN n<=500 THEN 'city' ELSE 'other-'||(n%100) END,
      'Nombre',CASE WHEN n%2=0 THEN 'A' ELSE 'B' END,'Frutas','Bulto',25,'Kilogramo',1,'Ronda',10,12,'package',1
    FROM generate_series(1,20000) AS n`);
  await db.query('ANALYZE regional_price');
  const original=db.query.bind(db);
  let captured;
  db.query=(sql,args)=>{
    if(typeof sql==='string'&&sql.includes('selected AS MATERIALIZED')&&sql.includes('ordinary_market_names AS MATERIALIZED')) captured={sql,args};
    return original(sql,args);
  };
  try {
    const result=await quoteModule.filteredProduct('city','Uno',{series:'city',market:'a',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(result.history.length,50);
    assert.ok(result.history.every(point=>point.sources.length===1));
    assert.equal(result.markets.length,1);
  } finally { db.query=original; }
  assert.ok(captured,'ordinary one-market source scope must be selected');
  const plan=(await db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+captured.sql,captured.args)).rows[0]['QUERY PLAN'][0];
  const indexScans=[];
  const visit=(node)=>{
    if(node['Index Name']) indexScans.push(node);
    for(const child of node.Plans||[]) visit(child);
  };
  visit(plan.Plan);
  assert.ok(indexScans.some(node=>
    node['Index Name']==='regional_price_lookup'&&
    node['Index Cond']?.includes('product_id')&&node['Index Cond']?.includes('market_name')),
    `city detail should seek the selected product and market before sorting revisions: ${JSON.stringify(indexScans.map(n=>[n['Index Name'],n['Index Cond']]))}`);
});

check('grouped Corabastos options preserve latest document and locator ties, exact region, and conflict quarantine',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  for(let i=0;i<names.length;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    ['alias-'+i,names[i],'Bogotá',i===1?'BOGOTÁ, D.C.':'Bogotá, D.C.','11001']);
  const older=await regional({market:names[0],price:100});
  const preferred=await regional({market:names[0],price:200,doc:'b'.repeat(64)});
  const laterLocator=await regional({market:names[0],price:999,doc:'b'.repeat(64)});
  await db.query("UPDATE regional_price SET source_locator='a-preferred' WHERE source_locator=$1",[preferred]);
  await db.query("UPDATE regional_price SET source_locator='z-later' WHERE source_locator=$1",[laterLocator]);
  const equalAlias=await regional({market:names[1],price:200,doc:'b'.repeat(64)});
  const cityOptions=async(region,product='city')=>(await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,[product,region])).rows.filter(x=>x.series==='city');
  for(const region of ['','Bogotá, D.C.','BOGOTÁ, D.C.']) {
    const city=await cityOptions(region);
    assert.deepEqual(city.map(x=>[x.market_id,x.market_name,x.units]),
      [['sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','25 Kilogramo']]);
    assert.equal(city[0].requires_revision_resolution,false);
  }
  await db.query('UPDATE regional_price SET max_unit_price=9 WHERE source_locator=$1',[equalAlias]);
  assert.deepEqual(await cityOptions('Bogotá, D.C.'),[],
    'a different price-range field on another literal quarantines only that typed key');
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)', ['b'.repeat(64)]);
  const published=await cityOptions('Bogotá, D.C.');
  assert.deepEqual(published.map(x=>x.units),['25 Kilogramo'],
    'quarantined source rows never reenter grouped rival candidates');
  assert.equal(older.startsWith('row-'),true);
});

check('grouped options use only published corrected product IDs and leave source evidence raw',async()=>{
  const names=['Bogotá, Corabastos','Bogotá, D.C., Corabastos'];
  for(let i=0;i<names.length;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    ['alias-'+i,names[i],'Bogotá','Bogotá, D.C.','11001']);
  const cityOptions=async(product)=>(await db.query(quoteModule.PRODUCT_FILTER_OPTIONS_SQL,[product,'Bogotá, D.C.'])).rows.filter(x=>x.series==='city');
  const corrected=await regional({product:'rice',market:names[0],price:100});
  await db.query(`INSERT INTO regional_price_product_correction
    SELECT document_id,source_locator,'city','Ciudad corregida' FROM regional_price WHERE source_locator=$1`,[corrected]);
  const native=await regional({product:'city',market:names[1],price:100});
  assert.deepEqual((await cityOptions('city')).map(x=>x.units),['25 Kilogramo']);
  assert.deepEqual(await cityOptions('rice'),[]);
  await db.query('UPDATE regional_price SET min_price=101 WHERE source_locator=$1',[native]);
  assert.deepEqual(await cityOptions('city'),[]);
  assert.deepEqual((await db.query('SELECT product_id,product_name FROM regional_price WHERE source_locator=$1',[corrected])).rows,
    [{product_id:'rice',product_name:'Nombre literal'}]);
  assert.deepEqual((await db.query('SELECT corrected_product_id FROM regional_price_product_correction WHERE source_locator=$1',[corrected])).rows,
    [{corrected_product_id:'city'}]);
});

// PRICE_QUOTES retains the original, unoptimized city conflict predicate and
// serves as the independent oracle for the selected-statement overlap gate.
const corabastosMarket='sipsa-bogota-d-c-corabastos';
const corabastosFilters={series:'city',market:corabastosMarket,presentation:'Bulto',units:'70 Kilogramo',history:'all'};
async function corabastosSetup(){
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`,[corabastosMarket]);
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES('dane-city-bogota-corabastos','Bogotá, Corabastos','Bogotá','Bogotá, D.C.','11001')`);
}
async function corabastosOracle(product='city'){
  return (await db.query(`WITH quotes AS (${quoteModule.PRICE_QUOTES})
    SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count,
      coalesce(jsonb_agg(DISTINCT jsonb_build_object(
        'document_id',document_id,'source_locator',source_locator,'source_page',source_page,
        'market_id',market_id,'source_market_id',source_market_id,'market_name',market_name,
        'source_units',source_units)) FILTER (WHERE document_id IS NOT NULL),'[]'::jsonb) AS sources
    FROM quotes WHERE product_id=$1 AND region=$2 AND series='city' AND market_id=$3
      AND presentation='Bulto' AND units='70 Kilogramo' AND ${untilToday}
    GROUP BY observed_on ORDER BY observed_on`,[product,'Bogotá, D.C.',corabastosMarket])).rows;
}
async function assertCorabastosOracle(product='city'){
  const actual=await quoteModule.filteredProduct(product,'Bogotá, D.C.',corabastosFilters);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.history)),
    JSON.parse(JSON.stringify(await corabastosOracle(product))));
  return actual;
}
check('selected city overlap gate matches unoptimized quotes with disjoint literal dates',async()=>{
  await corabastosSetup();
  await regional({market:'Bogotá, D.C., Corabastos',quantity:70,day:-3,price:100});
  await regional({market:'Bogotá, Corabastos',quantity:70,day:-2,price:200});
  await classify();
  const actual=await assertCorabastosOracle();
  assert.deepEqual(actual.history.map(point=>Number(point.price)),[101,201]);
  assert.equal(actual.current.price,201);
});
check('selected city overlap gate retains identical and compatible cross-literal rows',async()=>{
  await corabastosSetup();
  const first=await regional({market:'Bogotá, D.C., Corabastos',quantity:70,day:-2,price:100});
  const second=await regional({market:'Bogotá, Corabastos',quantity:70,day:-2,price:100});
  await classify();
  await db.query(`UPDATE regional_price SET observed_on=(SELECT observed_on FROM regional_price WHERE source_locator=$1)
    WHERE source_locator=$2`,[first,second]);
  const actual=await assertCorabastosOracle();
  assert.equal(actual.history.length,1);
  assert.equal(actual.history[0].price,101);
  assert.equal(actual.history[0].sources.length,1,'a compatible rival does not duplicate the winner');
});
check('selected city overlap gate includes corrections targeting the requested product',async()=>{
  await corabastosSetup();
  const corrected=await regional({product:'rice',market:'Bogotá, Corabastos',quantity:70,day:-2,price:100});
  await db.query(`INSERT INTO regional_price_product_correction
    SELECT document_id,source_locator,'city','Producto corregido' FROM regional_price WHERE source_locator=$1`,[corrected]);
  const native=await regional({product:'city',market:'Bogotá, D.C., Corabastos',quantity:70,day:-2,price:200});
  await db.query(`UPDATE regional_price SET observed_on=(SELECT observed_on FROM regional_price WHERE source_locator=$1)
    WHERE source_locator=$2`,[corrected,native]);
  await classify();
  const city=await assertCorabastosOracle('city');
  assert.equal(city.history.length,0,'the corrected raw product participates in the conflict');
  const rice=await corabastosOracle('rice');
  assert.equal(rice.length,0,'the correction does not leak back to the raw product');
  assert.deepEqual((await db.query('SELECT product_id FROM regional_price WHERE source_locator=$1',[corrected])).rows,
    [{product_id:'rice'}]);
});
check('selected city overlap gate treats quarantined raw rivals as a safe superset',async()=>{
  await corabastosSetup();
  await regional({market:'Bogotá, D.C., Corabastos',quantity:70,day:-2,price:100});
  const rival=await regional({market:'Bogotá, Corabastos',quantity:70,day:-2,price:300,doc:'b'.repeat(64)});
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)',['b'.repeat(64)]);
  await classify();
  const actual=await assertCorabastosOracle();
  assert.equal(actual.history.length,1,'unpublished rival cannot quarantine the published quote');
  assert.equal(actual.history[0].price,101);
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price WHERE source_locator=$1',[rival])).rows[0].n,1);
});
check('selected city overlap gate catches a rival inserted after options but before selected SQL',async()=>{
  await corabastosSetup();
  const first=await regional({market:'Bogotá, D.C., Corabastos',quantity:70,day:-2,price:100});
  await classify();
  const query=db.query.bind(db);
  let inserted=false;
  db.query=async(statement,...args)=>{
    const answer=await query(statement,...args);
    if(!inserted && typeof statement==='string' && statement.includes('alias_candidates AS MATERIALIZED')){
      inserted=true;
      await query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,
        category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
        SELECT document_id,'rival-after-options',observed_on,product_id,product_name,'Bogotá, Corabastos',
          category,presentation,quantity,source_unit,round,round_label,200,202,unit,source_page
        FROM regional_price WHERE source_locator=$1`,[first]);
      await query(`INSERT INTO regional_classification(document_id,source_locator,category_path)
        SELECT document_id,'rival-after-options',category_path FROM regional_classification WHERE source_locator=$1`,[first]);
    }
    return answer;
  };
  let actual;
  try{actual=await quoteModule.filteredProduct('city','Bogotá, D.C.',corabastosFilters)}
  finally{db.query=query}
  assert.equal(inserted,true);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.history)),
    JSON.parse(JSON.stringify(await corabastosOracle())));
  assert.equal(actual.history.length,0);
});

// The partitioned reader uses one checked-out client for every chunk and the
// decimal merge. A TEMP schema is intentionally connection-local, so these
// tests also catch accidental use of a second pooled connection.
async function withPartitionClient(run,failOnChunk=0){
  const original=db;
  const commands=[];
  const partialRows=[];
  let released=0;
  let chunks=0;
  let checkout=0;
  db={
    query:(...args)=>original.query(...args),
    connect:async()=>{
      // Each filtered detail first checks out a transaction client for its
      // options snapshot. Only the next checkout is the partition reader.
      if(++checkout===1) return {query:(...args)=>original.query(...args),release:()=>{}};
      return {
      query:async(sql,...args)=>{
        commands.push(sql);
        if(typeof sql==='string' && sql.includes('selected AS MATERIALIZED')){
          chunks++;
          if(chunks===failOnChunk) throw new Error('injected partition failure');
        }
        const result=await original.query(sql,...args);
        if(typeof sql==='string' && sql.includes('selected AS MATERIALIZED'))
          partialRows.push(result.rows[0]);
        return result;
      },
      release:()=>{released++},
    };
    },
  };
  try{return {value:await run(),commands,chunks,partialRows,released:()=>released}}
  finally{db=original}
}
async function partitionMarkets(count){
  for(let i=0;i<count;i++){
    const id='partition-'+String(i).padStart(2,'0');
    const name='Partition market '+String(i).padStart(2,'0');
    await db.query('INSERT INTO market(id,name,city,region) VALUES($1,$2,$3,$4)',
      [id,name,'Ciudad '+i,'Partition']);
  }
}
async function partitionOracle(product='city',history='all'){
  const datePredicate=history==='all'
    ? untilToday
    : `observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND ${untilToday}`;
  return (await db.query(`WITH quotes AS (${quoteModule.PRICE_QUOTES})
    SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count,
      coalesce(jsonb_agg(DISTINCT jsonb_build_object(
        'document_id',document_id,'source_locator',source_locator,'source_page',source_page,
        'market_id',market_id,'source_market_id',source_market_id,'market_name',market_name,
        'source_units',source_units)) FILTER (WHERE document_id IS NOT NULL),'[]'::jsonb) AS sources
    FROM quotes WHERE product_id=$1 AND series='city' AND presentation='Bulto'
      AND units='25 Kilogramo' AND ${datePredicate}
    GROUP BY observed_on ORDER BY observed_on`,[product])).rows;
}
const stableHistory=rows=>JSON.parse(JSON.stringify(rows.map(row=>({
  ...row,sources:[...row.sources].sort((a,b)=>
    [a.market_id,a.document_id,a.source_locator].join('|').localeCompare(
      [b.market_id,b.document_id,b.source_locator].join('|'))),
}))));

check('partitioned city history exactly merges unequal dated counts and 21 source identities over seven chunks',async()=>{
  await partitionMarkets(21);
  const names=Array.from({length:21},(_,i)=>'Partition market '+String(i).padStart(2,'0'));
  for(let i=0;i<20;i++) await regional({market:names[i],day:-1,price:10+i+0.125});
  for(let i of [0,20]) await regional({market:names[i],day:-500,price:4+i+0.25});
  const revision=await regional({market:names[0],day:-1,price:100.625,round:2,doc:'b'.repeat(64)});
  const held=await regional({market:names[1],day:-1,price:900.875,doc:'b'.repeat(64)});
  // Keep the published revision in b and quarantine the held rival in c.
  await db.query('INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at) VALUES($1,$2,$3,$4,$5,$6,$7,decode($8,\'hex\'),now())',
    ['c'.repeat(64),'Held','DANE','https://example.invalid/held','application/pdf','original','','00']);
  await db.query('UPDATE regional_price SET document_id=$1 WHERE source_locator=$2',['c'.repeat(64),held]);
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)',['c'.repeat(64)]);
  const corrected=await regional({product:'rice',market:names[20],day:-1,price:30.375});
  await db.query(`INSERT INTO regional_price_product_correction
    SELECT document_id,source_locator,'city','Corrected city' FROM regional_price WHERE source_locator=$1`,[corrected]);
  await classify();
  const {value:actual,commands,chunks,partialRows,released}=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}));
  assert.equal(chunks,7,'21 market IDs at chunk size 3 require seven chunks');
  assert.equal(released(),1);
  assert.equal(commands.filter(sql=>sql==='BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY').length,1);
  assert.equal(commands.filter(sql=>sql==='COMMIT').length,1);
  assert.equal(actual.markets.length,21);
  assert.ok(partialRows.every(row=>row.history.every(point=>
    typeof point.price_sum==='string' && Number.isInteger(point.price_count))));
  assert.ok(partialRows.some(row=>row.history.some(point=>point.price_sum.includes('.'))),
    'fractional decimal sums survive every chunk as text before the SQL merge');
  assert.deepEqual(stableHistory(actual.history),stableHistory(await partitionOracle()));
  assert.ok(actual.history.some(row=>!Number.isInteger(Number(row.price))));
  assert.deepEqual(actual.history.map(row=>row.market_count),[2,21]);
  assert.ok(actual.history.at(-1).sources.some(source=>source.source_locator===revision));
  assert.ok(actual.history.at(-1).sources.every(source=>source.source_locator!==held));
  assert.ok(actual.history.at(-1).sources.some(source=>source.source_locator===corrected));
  assert.equal((await db.query('SELECT product_id FROM regional_price WHERE source_locator=$1',[corrected])).rows[0].product_id,'rice');
  const recent=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'recent'}));
  assert.equal(recent.chunks,7);
  assert.deepEqual(stableHistory(recent.value.history),stableHistory(await partitionOracle('city','recent')));
  assert.equal(recent.value.history.length,1,'the old sparse date is outside the recent window');
});

check('partitioned city alias preserves one canonical winner, source literal, and verified latest category',async()=>{
  await partitionMarkets(10);
  await corabastosSetup();
  for(let i=0;i<10;i++) await regional({market:'Partition market '+String(i).padStart(2,'0'),day:-1,price:20+i});
  const alias=await regional({market:'Bogotá, Corabastos',day:-1,price:40,doc:'b'.repeat(64)});
  await classify();
  await db.query(`CREATE OR REPLACE TEMP VIEW verified_regional_category_overlay AS
    SELECT document_id,source_locator,'Frutas > Otras frutas'::text AS corrected_category
    FROM regional_price WHERE source_locator='${alias}'`);
  await db.query('UPDATE regional_classification SET category_path=ARRAY[$1,$2] WHERE source_locator=$3',
    ['Frutas','Otras frutas',alias]);
  const {value:actual,chunks}=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}));
  assert.equal(chunks,4);
  assert.deepEqual(stableHistory(actual.history),stableHistory(await partitionOracle()));
  const source=actual.history[0].sources.find(s=>s.market_id===corabastosMarket);
  assert.deepEqual([source.document_id,source.source_locator,source.market_name],
    ['b'.repeat(64),alias,'Bogotá, Corabastos']);
  const latest=actual.markets.find(row=>row.market_id===corabastosMarket);
  assert.deepEqual(latest.category_path,['Frutas','Otras frutas']);
  assert.equal(actual.markets.length,11);
});

check('chunk size 3 merges five markets, unequal date density, exact weighted means, and canonical alias provenance',async()=>{
  await partitionMarkets(4);
  await corabastosSetup();
  const names=Array.from({length:4},(_,i)=>'Partition market '+String(i).padStart(2,'0'));
  const latestPrices=[10.125,20.25,30.375,40.5,50.625];
  for(let i=0;i<4;i++) await regional({market:names[i],day:-1,price:latestPrices[i]});
  const alias=await regional({market:'Bogotá, Corabastos',day:-1,price:latestPrices[4],doc:'b'.repeat(64)});
  // Two markets contribute to the older date, while all five contribute to the recent date.
  for(const i of [0,3]) await regional({market:names[i],day:-20,price:2.125+i});
  await classify();
  const {value:actual,chunks,partialRows}=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}));
  assert.equal(chunks,2,'five canonical market IDs must split 3+2');
  assert.deepEqual(stableHistory(actual.history),stableHistory(await partitionOracle()));
  assert.deepEqual(actual.history.map(row=>row.market_count),[2,5]);
  assert.equal(Number(actual.history.at(-1).price),31.375);
  assert.equal(Number(actual.history[0].price),4.625);
  assert.ok(partialRows.every(row=>row.history.every(point=>typeof point.price_sum==='string')));
  const canonical=actual.history.at(-1).sources.find(source=>source.market_id===corabastosMarket);
  assert.deepEqual([canonical.document_id,canonical.source_locator,canonical.market_name],
    ['b'.repeat(64),alias,'Bogotá, Corabastos']);
  assert.equal(actual.markets.length,5);
});

check('partition failure rolls back and releases the same client without partial prices',async()=>{
  await partitionMarkets(11);
  for(let i=0;i<11;i++) await regional({market:'Partition market '+String(i).padStart(2,'0'),price:20+i});
  await classify();
  const original=db;
  const commands=[];
  let released=0,chunk=0;
  let checkout=0;
  db={query:(...args)=>original.query(...args),connect:async()=>{
    if(++checkout===1) return {query:(...args)=>original.query(...args),release:()=>{}};
    return {
    query:async(sql,...args)=>{
      commands.push(sql);
      if(typeof sql==='string' && sql.includes('selected AS MATERIALIZED') && ++chunk===2)
        throw new Error('second chunk failed');
      return original.query(sql,...args);
    },release:()=>{released++},
  }}};
  try{
    await assert.rejects(quoteModule.filteredProduct('city','',
      {series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}),
      error=>error.stage==='selected_quotes' && error.message==='PRODUCT_DETAIL_STAGE_FAILED');
  }finally{db=original}
  assert.equal(chunk,2);
  assert.equal(released,1);
  assert.deepEqual(commands.filter(sql=>sql==='ROLLBACK'),['ROLLBACK']);
  assert.equal(commands.includes('COMMIT'),false);
  const resumed=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}));
  assert.equal(resumed.chunks,4,'eleven markets at chunk size 3 require four chunks on retry');
  assert.equal(resumed.value.markets.length,11,'a failed request cannot cache partial results');
  assert.equal(resumed.value.history[0].market_count,11);
});

check('partition merge failure also rolls back and never returns a partial history',async()=>{
  await partitionMarkets(11);
  for(let i=0;i<11;i++) await regional({market:'Partition market '+String(i).padStart(2,'0'),price:30+i});
  await classify();
  const original=db;
  let released=0;
  const commands=[];
  let checkout=0;
  db={query:(...args)=>original.query(...args),connect:async()=>{
    if(++checkout===1) return {query:(...args)=>original.query(...args),release:()=>{}};
    return {
    query:async(sql,...args)=>{
      commands.push(sql);
      if(typeof sql==='string' && sql.startsWith('WITH partial AS ('))
        throw new Error('decimal merge failed');
      return original.query(sql,...args);
    },release:()=>{released++},
  }}};
  try{
    await assert.rejects(quoteModule.filteredProduct('city','',
      {series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}),
      error=>error.stage==='selected_quotes' && error.message==='PRODUCT_DETAIL_STAGE_FAILED');
  }finally{db=original}
  assert.equal(commands.filter(sql=>typeof sql==='string' && sql.includes('selected AS MATERIALIZED')).length,4);
  assert.equal(commands.filter(sql=>sql==='ROLLBACK').length,1);
  assert.equal(commands.includes('COMMIT'),false);
  assert.equal(released,1);
  const resumed=await withPartitionClient(()=>
    quoteModule.filteredProduct('city','',{series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'}));
  assert.equal(resumed.value.history[0].market_count,11);
});

check('one-market, monthly, and ambiguous-package selections never check out a partition client',async()=>{
  await regional({market:'A',price:10});
  await monthly({product:'monthly',market:'a',price:100});
  await monthly({product:'monthly',market:'b',price:300});
  await regional({market:'A',price:20,presentation:' Bulto',round:2,doc:'b'.repeat(64)});
  await classify();
  const original=db;
  let partitionReads=0;
  db={query:(...args)=>original.query(...args),connect:async()=>({
    query:async(sql,...args)=>{
      if(typeof sql==='string' && sql.includes('selected AS MATERIALIZED') &&
        Array.isArray(args[0]) && args[0].length===7){
        partitionReads++;
        throw new Error('unexpected partition checkout');
      }
      return original.query(sql,...args);
    },release:()=>{},
  })};
  try{
    const one=await quoteModule.filteredProduct('city','Uno',
      {series:'city',market:'a',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    const monthlyResult=await quoteModule.filteredProduct('monthly','',
      {series:'monthly',units:'1 kg',history:'all'});
    const ambiguous=await quoteModule.filteredProduct('city','',
      {series:'city',presentation:'Bulto',units:'25 Kilogramo',history:'all'});
    assert.equal(one.markets.length,1);
    assert.equal(monthlyResult.current.price,200);
    assert.equal(ambiguous.options.presentations.length,1);
    assert.equal(partitionReads,0);
  }finally{db=original}
});


check('latest eligible city package is default, old package and selected market remain available', async () => {
  const old = await regional({ market: 'A', day: -1800, quantity: 69, price: 100 });
  const newest = await regional({ market: 'B', day: -1, quantity: 70, price: 200 });
  const future = await regional({ market: 'B', day: 30, quantity: 71, price: 300 });
  const held = await regional({ market: 'B', day: -1, quantity: 72, price: 999,
    doc: 'b'.repeat(64) });
  await db.query('INSERT INTO city_pdf_publication_conflict VALUES($1)', ['b'.repeat(64)]);
  const recent = await quoteModule.filteredProduct('city', '', { series: 'city', history: 'recent' });
  assert.equal(recent.filters.presentation, 'Bulto');
  assert.equal(recent.filters.units, '70 Kilogramo');
  assert.equal(Number(recent.current.price), 201);
  assert.deepEqual(Array.from(recent.options.units), ['69 Kilogramo', '70 Kilogramo']);
  assert.deepEqual(Array.from(recent.current.sources, x => x.source_locator), [newest]);
  assert.ok(!recent.current.sources.some(x => [future, held].includes(x.source_locator)));
  const oldHistory = await quoteModule.filteredProduct('city', '', {
    series: 'city', presentation: 'Bulto', units: '69 Kilogramo', history: 'all',
  });
  assert.equal(oldHistory.filters.units, '69 Kilogramo');
  assert.equal(Number(oldHistory.current.price), 101);
  assert.deepEqual(Array.from(oldHistory.current.sources, x => x.source_locator), [old]);
  const oldRecent = await quoteModule.filteredProduct('city', '', {
    series: 'city', presentation: 'Bulto', units: '69 Kilogramo', history: 'recent',
  });
  assert.equal(oldRecent.filters.units, '69 Kilogramo');
  assert.equal(oldRecent.current, null);
  const chosenMarket = await quoteModule.filteredProduct('city', '', {
    series: 'city', market: 'a', history: 'recent',
  });
  assert.equal(chosenMarket.filters.market, 'a');
  assert.equal(chosenMarket.filters.units, '69 Kilogramo');
  assert.equal(chosenMarket.current, null);
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n, 4);
});

check('verified category paths win by document and locator across detail, catalog, classification, and Corabastos history',async()=>{
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
    ('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá, D.C.','Bogotá, D.C.','11001'),
    ('dane-city-bogota-corabastos','Bogotá, Corabastos','Bogotá, D.C.','Bogotá, D.C.','11001')`);
  const overlayDoc='a'.repeat(64), otherDoc='b'.repeat(64);
  const overlay=await regional({doc:overlayDoc,market:'Bogotá, D.C., Corabastos',name:'Yuca',price:20});
  const leaf=await regional({doc:overlayDoc,market:'Bogotá, Corabastos',name:'Ñame',price:30,quantity:26});
  const classOnly=await regional({doc:overlayDoc,market:'Bogotá, D.C., Corabastos',name:'Papa',price:40,quantity:27});
  const rawOnly=await regional({doc:overlayDoc,market:'Bogotá, D.C., Corabastos',name:'Pescado',price:50,quantity:28});
  // Same locator in a different source document proves overlay joins use both keys.
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    SELECT $1,source_locator,observed_on-1,'city','Yuca','Bogotá, D.C., Corabastos','Carnes','Caja',10,'Kilogramo',2,'Ronda 2',90,92,'package',1
    FROM regional_price WHERE document_id=$2 AND source_locator=$3`,[otherDoc,overlayDoc,overlay]);
  const sameLocator=overlay;
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path) VALUES
    ($1,$2,ARRAY['Raw wrong','Nested path']),($1,$3,ARRAY['Raw leaf stale']),
    ($1,$4,ARRAY['Classification only','Leaf']),
    ($5,$2,ARRAY['Other document','Classification'])`,[overlayDoc,overlay,leaf,classOnly,otherDoc]);
  await db.query(`INSERT INTO category_overlay_fixture(document_id,source_locator,corrected_category) VALUES
    ($1,$2,'Verduras'),($1,$3,'Tubérculos > Raíces')`,[overlayDoc,overlay,leaf]);
  const before=(await db.query(`SELECT document_id,source_locator,to_jsonb(r) AS payload,xmin::text AS xmin
    FROM regional_price r ORDER BY document_id,source_locator`)).rows;
  const classificationsBefore=(await db.query(`SELECT document_id,source_locator,to_jsonb(c) AS payload,xmin::text AS xmin
    FROM regional_classification c ORDER BY document_id,source_locator`)).rows;
  const paths=await quoteModule.withQuoteClassifications([
    {series:'city',document_id:overlayDoc,source_locator:overlay,category_path:['stale']},
    {series:'city',document_id:overlayDoc,source_locator:leaf,category_path:['stale']},
    {series:'city',document_id:overlayDoc,source_locator:classOnly,category_path:['stale']},
    {series:'city',document_id:overlayDoc,source_locator:rawOnly,category_path:['stale']},
    {series:'city',document_id:otherDoc,source_locator:sameLocator,category_path:['stale']},
  ]);
  assert.deepEqual(paths.map(row=>row.category_path),[
    ['Verduras'],['Tubérculos','Raíces'],['Classification only','Leaf'],['Frutas'],['Other document','Classification'],
  ]);
  const loose=(await db.query(quoteModule.CITY_LOOSE_LATEST_QUOTES,[['city']])).rows;
  const looseBySource=new Map(loose.map(row=>[row.document_id+':'+row.source_locator,row.category_path]));
  assert.deepEqual(looseBySource.get(overlayDoc+':'+overlay),['Verduras']);
  assert.deepEqual(looseBySource.get(overlayDoc+':'+leaf),['Tubérculos','Raíces']);
  assert.deepEqual(looseBySource.get(overlayDoc+':'+classOnly),['Classification only','Leaf']);
  assert.deepEqual(looseBySource.get(overlayDoc+':'+rawOnly),['Frutas']);
  const publishedPaths=(await db.query(quoteModule.PRODUCT_CLASSIFICATIONS_SQL,['city'])).rows.map(row=>row.category_path);
  assert.ok(publishedPaths.some(path=>JSON.stringify(path)==='["Verduras"]'));
  assert.ok(publishedPaths.some(path=>JSON.stringify(path)==='["Tubérculos","Raíces"]'));
  const catalogNames=(await db.query(catalogModule.CITY_CATALOG_NAMES_SQL)).rows;
  const yuca=catalogNames.find(row=>row.product_id==='city');
  const catalog=(await db.query(catalogModule.CITY_CATALOG_SQL,['Bogotá, D.C.',JSON.stringify([{product_id:'city',latest_date:yuca.latest_date}])])).rows[0];
  const catalogPaths=catalog.category_paths;
  assert.ok(catalogPaths.some(path=>JSON.stringify(path)==='["Verduras"]'),JSON.stringify({catalogNames,catalog}));
  const selected=(await db.query(allHistoryModule.CORABASTOS_SELECTED_CLASSIFICATIONS_SQL,
    [[overlayDoc,overlayDoc,overlayDoc,overlayDoc,otherDoc],[overlay,leaf,classOnly,rawOnly,sameLocator]])).rows;
  const selectedMap=new Map(selected.map(row=>[row.document_id+':'+row.source_locator,row.category_path]));
  assert.deepEqual(selectedMap.get(overlayDoc+':'+overlay),['Verduras']);
  assert.deepEqual(selectedMap.get(overlayDoc+':'+leaf),['Tubérculos','Raíces']);
  assert.deepEqual(selectedMap.get(overlayDoc+':'+classOnly),['Classification only','Leaf']);
  assert.deepEqual(selectedMap.get(overlayDoc+':'+rawOnly),['Frutas']);
  assert.deepEqual(selectedMap.get(otherDoc+':'+sameLocator),['Other document','Classification']);
  const allHistory=await allHistoryModule.corabastosAllHistoryQuotes();
  assert.deepEqual(allHistory.find(row=>row.document_id===overlayDoc&&row.source_locator===overlay)?.category_path,['Verduras']);
  assert.deepEqual(allHistory.find(row=>row.document_id===overlayDoc&&row.source_locator===leaf)?.category_path,['Tubérculos','Raíces']);
  const after=(await db.query(`SELECT document_id,source_locator,to_jsonb(r) AS payload,xmin::text AS xmin
    FROM regional_price r ORDER BY document_id,source_locator`)).rows;
  const classificationsAfter=(await db.query(`SELECT document_id,source_locator,to_jsonb(c) AS payload,xmin::text AS xmin
    FROM regional_classification c ORDER BY document_id,source_locator`)).rows;
  assert.deepEqual(after,before,'all raw prices and row versions remain unchanged');
  assert.deepEqual(classificationsAfter,classificationsBefore,'raw classification history and row versions remain unchanged');
});

check('city alias conflict gate compares verified paths while preserving real price disagreements',async()=>{
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id) VALUES
    ('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá, D.C.','Bogotá, D.C.','11001'),
    ('dane-city-bogota-corabastos','Bogotá, Corabastos','Bogotá, D.C.','Bogotá, D.C.','11001')`);
  const a=await regional({market:'Bogotá, D.C., Corabastos',doc:'a'.repeat(64),price:20,name:'Arracacha'});
  const b=await regional({market:'Bogotá, Corabastos',doc:'b'.repeat(64),price:20,name:'Arracacha'});
  await db.query(`INSERT INTO regional_classification(document_id,source_locator,category_path) VALUES
    ($1,$2,ARRAY['Incorrect','Nested']),($3,$4,ARRAY['Different stale'])`,['a'.repeat(64),a,'b'.repeat(64),b]);
  await db.query(`INSERT INTO category_overlay_fixture VALUES($1,$2,'Tubérculos > Raíces'),($3,$4,'Tubérculos > Raíces')`,['a'.repeat(64),a,'b'.repeat(64),b]);
  const gateSql=`SELECT NOT ${cityAlias.cityCrossAliasConflictSql('r','m')} AS allowed
    FROM regional_price r JOIN market m ON m.name=r.market_name WHERE r.source_locator=$1`;
  let results=await db.query(gateSql,[a]);
  assert.equal(results.rows[0].allowed,true,'stale raw paths do not exclude equal verified category evidence');
  assert.equal((await db.query(`SELECT * FROM (${quoteModule.CITY_PRICE_QUOTES}) AS quotes WHERE product_id='city'`)).rows.length,1,
    'compatible aliases retain their canonical winner');
  await db.query('UPDATE category_overlay_fixture SET corrected_category=$1 WHERE document_id=$2 AND source_locator=$3',
    ['Tubérculos > Legumbres','b'.repeat(64),b]);
  results=await db.query(gateSql,[a]);
  assert.equal(results.rows[0].allowed,false,'a real verified category disagreement remains quarantined');
  assert.equal((await db.query(`SELECT * FROM (${quoteModule.CITY_PRICE_QUOTES}) AS quotes WHERE product_id='city'`)).rows.length,0);
  await db.query('UPDATE category_overlay_fixture SET corrected_category=$1 WHERE document_id=$2 AND source_locator=$3',
    ['Tubérculos > Raíces','b'.repeat(64),b]);
  await db.query('UPDATE regional_price SET min_price=21,max_price=23 WHERE document_id=$1 AND source_locator=$2',['b'.repeat(64),b]);
  results=await db.query(gateSql,[a]);
  assert.equal(results.rows[0].allowed,false,'a real per-unit price disagreement remains quarantined');
});

check('indexed alias-date conflict gate matches preserved legacy SQL for compatible and conflicting same-day quotes',async()=>{
  const names=['Bogotá, D.C., Corabastos','Bogotá, Corabastos'];
  const ids=['sipsa-bogota-d-c-corabastos','dane-city-bogota-corabastos'];
  for(let i=0;i<2;i++) await db.query('INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  const conflictA=await regional({market:names[0],product:'same-day-conflict',name:'Conflicto',quantity:10,price:100});
  const conflictB=await regional({market:names[1],product:'same-day-conflict',name:'Conflicto',quantity:10,price:200});
  const compatibleA=await regional({market:names[0],product:'same-day-compatible',name:'Compatible',quantity:12,price:50});
  const compatibleB=await regional({market:names[1],product:'same-day-compatible',name:'Compatible',quantity:12,price:50});
  const legacy=(await db.query(regionalOracleSQL)).rows;
  const actual=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  const semantic=rows=>rows.map(({market_name,source_market_id,source_locator,...row})=>row)
    .sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
  assert.deepEqual(semantic(actual),semantic(legacy));
  assert.ok(!actual.some(x=>x.source_locator===conflictA||x.source_locator===conflictB));
  const shown=actual.filter(x=>x.source_locator===compatibleA||x.source_locator===compatibleB);
  assert.equal(shown.length,1);
  assert.ok([[names[0],ids[0]],[names[1],ids[1]]].some(([name,id])=>
    name===shown[0].market_name&&id===shown[0].source_market_id));
});

check('indexed alias conflict gate keeps an uncurated NULL-market quote visible',async()=>{
  const names=['Bogotá, D.C., Corabastos','Bogotá, Corabastos'];
  for(const [i,name] of names.entries()) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [i?'dane-city-bogota-corabastos':'sipsa-bogota-d-c-corabastos',name,'Bogotá','Bogotá, D.C.','11001']);
  const aliasA=await regional({market:names[0],product:'unknown-control',name:'Misma clave',quantity:14,price:100});
  const aliasB=await regional({market:names[1],product:'unknown-control',name:'Misma clave',quantity:14,price:200});
  const uncurated=await regional({market:'Corabastos sin ubicación curada',product:'unknown-control',name:'Misma clave',quantity:14,price:777});
  const legacy=(await db.query(regionalOracleSQL)).rows;
  const actual=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  const semantic=rows=>rows.map(({market_name,source_market_id,source_locator,...row})=>row)
    .sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
  assert.deepEqual(semantic(actual),semantic(legacy));
  assert.ok(!actual.some(x=>x.source_locator===aliasA||x.source_locator===aliasB));
  const row=actual.find(x=>x.source_locator===uncurated);
  assert.ok(row);
  assert.equal(row.market_id,null);
  assert.equal(row.source_market_id,null);
  assert.equal(row.market_name,'Corabastos sin ubicación curada');
});

check('indexed alias-date seeks retain stale same-day rivals when a newer alias report omits that product',async()=>{
  const names=['Bogotá, D.C., Corabastos','Bogotá, Corabastos'];
  for(const [i,name] of names.entries()) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [i?'dane-city-bogota-corabastos':'sipsa-bogota-d-c-corabastos',name,'Bogotá','Bogotá, D.C.','11001']);
  const staleA=await regional({market:names[0],product:'dated-x',name:'Producto X',quantity:11,price:100});
  const staleB=await regional({market:names[1],product:'dated-x',name:'Producto X',quantity:11,price:200});
  const newerB=await regional({market:names[1],product:'dated-y',name:'Producto Y',quantity:12,price:300});
  await db.query('UPDATE regional_price SET observed_on=CURRENT_DATE-2 WHERE source_locator=ANY($1::text[])',[[staleA,staleB]]);
  await db.query('UPDATE regional_price SET observed_on=CURRENT_DATE-1 WHERE source_locator=$1',[newerB]);
  const legacy=(await db.query(regionalOracleSQL)).rows;
  const actual=(await db.query(regionalModule.LATEST_REGIONAL_PRICES_SQL)).rows;
  const semantic=rows=>rows.map(({market_name,source_market_id,source_locator,...row})=>row)
    .sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
  assert.deepEqual(semantic(actual),semantic(legacy));
  assert.ok(!actual.some(x=>x.source_locator===staleA||x.source_locator===staleB),
    'older product X remains quarantined by the historical same-day rival');
  assert.equal(actual.filter(x=>x.product_id==='dated-y').length,1);
  assert.equal(actual.find(x=>x.product_id==='dated-y').source_locator,newerB);
});
