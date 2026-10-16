/* Real PostgreSQL parity with the original catalog; private local socket only. */
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');
types.setTypeParser(1082, value => value);
const root = path.join(__dirname, '../../..');
const server = path.join(__dirname, '../src/lib/server');
const WINDOW = fs.readFileSync(path.join(server, 'db.ts'), 'utf8').split('export const WINDOW =')[1].match(/"([^"]+)"/)[1];
function moduleSQL(filename, mocks, globals = {}) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(server, filename), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
    exports, require: (name) => name === 'server-only' ? {} : name === './category-path-sql' ? moduleSQL('category-path-sql.ts', {})
      : name === '../filter-labels' ? moduleSQL('../filter-labels.ts', {})
      : name === '../catalog-frequency' ? moduleSQL('../catalog-frequency.ts', {})
      : name === './city-publication-epoch' ? (mocks[name] || { cityPublicationEpoch: async () => '0' }) : mocks[name], ...globals,
  });
  return exports;
}
const cityAlias = moduleSQL('city-market-alias.ts', {});
const cityPackage = moduleSQL('city-package-equivalence.ts', {});
const detailDiagnostics = moduleSQL('product-detail-diagnostics.ts', {});
const sql = moduleSQL('catalog-sql.ts', { './db': { WINDOW }, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage });
const latestRegional = moduleSQL('regional-prices.ts', {
  './db': {}, './snapshot-cache': { snapshotCache: () => () => undefined }, './city-market-alias': cityAlias,
}).LATEST_REGIONAL_PRICES_SQL;
const monthlyModule = moduleSQL('monthly-catalog.ts', { './db': { WINDOW }, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage });
const city = moduleSQL('price-quotes.ts', { './db': { WINDOW }, './summary-references': {}, './city-market-alias': cityAlias, './city-package-equivalence': cityPackage, './product-detail-diagnostics': detailDiagnostics }).CITY_PRICE_QUOTES;
const baseline = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/catalog-query-baseline.json'), 'utf8'));
for (const key in baseline) baseline[key] = baseline[key].replaceAll('${WINDOW}', WINDOW).replaceAll('${CITY_PRICE_QUOTES}', city);
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
  await db.query('CREATE TEMP TABLE price_observation_review (LIKE public.price_observation_review INCLUDING ALL)');
  await db.query(`CREATE TEMP TABLE regional_price_product_correction (
    document_id text NOT NULL, source_locator text NOT NULL, corrected_product_id text NOT NULL,
    corrected_product_name text NOT NULL, PRIMARY KEY(document_id,source_locator));
    CREATE INDEX ON regional_price_product_correction(corrected_product_id,corrected_product_name);
    CREATE TEMP TABLE city_pdf_publication_conflict(document_id text PRIMARY KEY);
    CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
      corrected_min_price numeric,corrected_max_price numeric);
    CREATE TEMP TABLE verified_regional_category_overlay_data (
      document_id text NOT NULL, source_locator text NOT NULL, corrected_category text NOT NULL,
      PRIMARY KEY(document_id,source_locator));
    CREATE TEMP VIEW verified_regional_category_overlay AS
      SELECT document_id,source_locator,corrected_category FROM verified_regional_category_overlay_data;
    CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS (
      SELECT 1 FROM city_pdf_publication_conflict blocked WHERE blocked.document_id=r.document_id OFFSET 0);
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
  await db.query('CREATE TEMP VIEW published_price_observation AS ' + view);
  await db.query(fs.readFileSync(path.join(root, 'pipelines/ingestion/migrations/20260927_008_catalog_reads.sql'), 'utf8'));
  await db.query('CREATE INDEX regional_price_lookup ON regional_price(product_id,market_name,observed_on DESC); CREATE INDEX regional_market_latest ON regional_price(market_name,observed_on DESC)');
  await db.query(`INSERT INTO product(id,name,category) VALUES('city','Ciudad','Frutas'),('monthly','Mensual','Verduras'),('milk','Leche','Lácteos'),('rice','Arroz','Cereales');
    INSERT INTO market(id,name,city,region) VALUES('a','A','Ciudad A','Uno'),('b','B','Ciudad B','Dos'),('empty','Empty','Ciudad E','Vacía');
    INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at)
    VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','Old','DANE','https://example.invalid/old','application/pdf','original','',decode('00','hex'),'2026-09-01'),
    ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','New','DANE','https://example.invalid/new','application/pdf','original','',decode('00','hex'),'2026-09-25')`);
});
afterEach(async () => { if (db) await db.end(); db = undefined; });
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
let seq = 0;
async function regional({ product = 'city', name = 'Nombre literal', market = 'A', day = -1, price = 10, presentation = 'Bulto', quantity = 25, unit = 'Kilogramo', round = 1, doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  const locator = 'row-' + (++seq);
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    VALUES($1,$2,CURRENT_DATE+$3::integer,$4,$5,$6,'Frutas',$7,$8,$9,$10,'Ronda',$11::numeric,$11::numeric+2,'package',1)`,
    [doc, locator, day, product, name, market, presentation, quantity, unit, round, price]);
  return locator;
}
async function monthly({ product = 'monthly', market = 'a', month = 1, price = 100, source = 'dane-sipsa', unit = 'kg', doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  await db.query(`INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    VALUES($1,$2,$3,(date_trunc('month',CURRENT_DATE)-($4||' months')::interval+interval '1 month - 1 day')::date,'monthly',$5,$6,'https://example.invalid/',$7)`, [product, market, source, month, unit, price, doc]);
}
const sorted = (rows) => [...rows].sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
async function equivalent(region = '') {
  const names = (await db.query(sql.CITY_CATALOG_NAMES_SQL)).rows;
  const expectedNames = (await db.query("SELECT DISTINCT product_id,product_name FROM resolved_regional_price WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY product_id,product_name")).rows;
  assert.deepEqual(names.map(({latest_date,...row}) => row), expectedNames);
  const base = (await db.query(baseline.monthly, [region])).rows;
  const recent = await db.query(monthlyModule.RECENT_MONTHLY_QUOTES_SQL);
  const metadata = await db.query(monthlyModule.CATALOG_PRODUCTS_SQL);
  const availability = await db.query(monthlyModule.CATALOG_MARKETS_SQL);
  const aggregated = monthlyModule.aggregateMonthlyCatalog(recent.rows, metadata.rows, availability.rows);
  const numeric = rows => sorted(JSON.parse(JSON.stringify(rows)).map(row => ({ ...row,
    price: Number(row.price), previous_price: row.previous_price === null ? null : Number(row.previous_price), market_count: Number(row.market_count),
  })));
  assert.deepEqual(numeric(aggregated.products.get(region) || []), numeric(base));
  assert.deepEqual([...aggregated.regions], (await db.query(baseline.regions)).rows.map(row => row.region));

  const existing = new Set(base.map((r) => r.id));
  const dates = new Map();
  for (const r of names) if (!existing.has(r.product_id) && r.latest_date && (!dates.has(r.product_id) || r.latest_date > dates.get(r.product_id))) dates.set(r.product_id, r.latest_date);
  const candidates = [...dates].map(([product_id,latest_date]) => ({ product_id, latest_date }));
  const rows = (await db.query(sql.CITY_CATALOG_SQL, [region, JSON.stringify(candidates)])).rows;
  const withoutDisplayPaths = records => records.map(({ category_paths, ...row }) => row);
  assert.deepEqual(sorted(withoutDisplayPaths(rows)), sorted(withoutDisplayPaths((await db.query(baseline.city, [region])).rows)));
  return { names, base, rows };
}
check('city card hierarchy comes only from selected source rows, package and regional date', async () => {
  const oldLocator = await regional({ day: -5, market: 'A', price: 900, quantity: 50 });
  const firstLocator = await regional({ day: -1, market: 'A', price: 10 });
  const revisedLocator = await regional({ day: -1, market: 'A', price: 20, round: 2,
    doc: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' });
  const otherLocator = await regional({ day: -1, market: 'B', price: 30 });
  for (const [document, locator, path] of [
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', oldLocator, ['Carnes', 'Carne de res']],
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', firstLocator, ['Pescados', 'Frescos']],
    ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', revisedLocator, ['Frutas', 'Cítricos']],
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', otherLocator, ['Frutas', 'Otras frutas']],
  ]) await db.query('INSERT INTO regional_classification VALUES($1,$2,$3)', [document, locator, path]);
  const latestDay = (await db.query("SELECT (CURRENT_DATE - 1)::text AS day")).rows[0].day;
  const candidates = JSON.stringify([{ product_id: 'city', latest_date: latestDay }]);
  const all = (await db.query(sql.CITY_CATALOG_SQL, ['', candidates])).rows;
  assert.equal(all.length, 1);
  assert.equal(all[0].price, '26.0000000000000000');
  assert.equal(all[0].market_count, '2');
  assert.deepEqual(all[0].category_paths, [['Frutas', 'Cítricos'], ['Frutas', 'Otras frutas']]);
  const local = (await db.query(sql.CITY_CATALOG_SQL, ['Uno', candidates])).rows;
  assert.deepEqual(local[0].category_paths, [['Frutas', 'Cítricos']]);
  assert.equal(local[0].price, '21.0000000000000000');
  assert.ok(!JSON.stringify(all[0].category_paths).includes('Carnes'));
  assert.ok(!JSON.stringify(all[0].category_paths).includes('Pescados'));
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n, 4);
});
check('catalog counts one Corabastos city identity and excludes only a conflicting alias quote',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
  for(let i=0;i<3;i++) await db.query('INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
  for(let i=0;i<3;i++) await regional({market:names[i],day:-1,price:100});
  assert.equal((await db.query(monthlyModule.CATALOG_MARKETS_SQL)).rows
    .find(row=>row.region==='Bogotá, D.C.').has_city,true);
  await regional({market:'A',day:-1,price:200});
  const day=(await db.query('SELECT (CURRENT_DATE-1)::text AS day')).rows[0].day;
  const candidates=JSON.stringify([{product_id:'city',latest_date:day}]);
  let rows=(await db.query(sql.CITY_CATALOG_SQL,['',candidates])).rows;
  assert.equal(rows.length,1);
  assert.equal(rows[0].market_count,'2');
  assert.equal(Number(rows[0].price),151);
  await regional({market:names[0],day:-1,price:400,doc:'b'.repeat(64)});
  rows=(await db.query(sql.CITY_CATALOG_SQL,['',candidates])).rows;
  assert.equal(rows.length,1);
  assert.equal(rows[0].market_count,'1','conflicted alias group is absent, unrelated market remains');
  assert.equal(Number(rows[0].price),201);
  assert.equal((await db.query('SELECT count(*)::integer n FROM regional_price')).rows[0].n,5);
});
check('catalog alias conflicts use each literal latest eligible source before cross-literal comparison',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
  for(let i=0;i<names.length;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [`adv-alias-${i}`,names[i],'Bogotá','Bogotá, D.C.','11001']);
  await db.query("INSERT INTO product(id,name,category) VALUES('latest-pair','Latest pair','Frutas'),('genuine-conflict','Genuine conflict','Frutas'),('published-fallback','Published fallback','Frutas')");
  const c='c'.repeat(64),d='d'.repeat(64);
  await db.query("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at) VALUES($1,'Later C','DANE','https://example.invalid/c','application/pdf','original','',decode('00','hex'),'2026-10-14'),($2,'Later D','DANE','https://example.invalid/d','application/pdf','original','',decode('00','hex'),'2026-10-15')",[c,d]);
  const latestDay=(await db.query("SELECT (CURRENT_DATE-1)::text AS day")).rows[0].day;
  // Same-literal stale rows must not conflict with the latest row for that spelling.
  await regional({product:'latest-pair',name:'Latest pair',market:names[0],day:-1,price:900,doc:'a'.repeat(64)});
  await regional({product:'latest-pair',name:'Latest pair',market:names[0],day:-1,price:100,doc:c});
  await regional({product:'latest-pair',name:'Latest pair',market:names[1],day:-1,price:100,doc:'b'.repeat(64)});
  // A true disagreement between two distinct literal aliases is quarantined.
  await regional({product:'genuine-conflict',name:'Genuine conflict',market:names[0],day:-1,price:100});
  await regional({product:'genuine-conflict',name:'Genuine conflict',market:names[1],day:-1,price:150,doc:'b'.repeat(64)});
  // The latest rival for a literal is ineligible; its older published row is the winner.
  await regional({product:'published-fallback',name:'Published fallback',market:names[0],day:-1,price:100});
  await regional({product:'published-fallback',name:'Published fallback',market:names[1],day:-1,price:100,doc:'b'.repeat(64)});
  await regional({product:'published-fallback',name:'Published fallback',market:names[1],day:-1,price:700,doc:d});
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)',[d]);
  const ids=['latest-pair','genuine-conflict','published-fallback'];
  const candidates=JSON.stringify(ids.map(product_id=>({product_id,latest_date:latestDay})));
  const rows=(await db.query(sql.CITY_CATALOG_SQL,['',candidates])).rows;
  const byId=new Map(rows.map(row=>[row.id,row]));
  assert.equal(byId.get('latest-pair')?.price,'101.0000000000000000',
    'the stale same-literal price does not create a false cross-alias conflict');
  assert.equal(byId.has('genuine-conflict'),false,
    'different latest prices across literal aliases suppress the ambiguous product');
  assert.equal(byId.get('published-fallback')?.price,'101.0000000000000000',
    'a blocked newer rival does not hide the older eligible matching source');
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,8,
    'catalog selection leaves all original source rows intact');
});
check('catalog alias keys preserve corrected identity and keep distinct typed packages separate',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos'];
  for(let i=0;i<names.length;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [`typed-alias-${i}`,names[i],'Bogotá','Bogotá, D.C.','11001']);
  await db.query("INSERT INTO product(id,name,category) VALUES('corrected-alias','Corrected alias','Frutas'),('package-separated','Package separated','Frutas')");
  const day=(await db.query("SELECT (CURRENT_DATE-1)::text AS day")).rows[0].day;
  const corrected=await regional({product:'raw-alias-label',name:'Raw alias label',market:names[0],day:-1,price:100});
  await db.query('INSERT INTO regional_price_product_correction VALUES($1,$2,$3,$4)',
    ['a'.repeat(64),corrected,'corrected-alias','Corrected alias']);
  await regional({product:'corrected-alias',name:'Corrected alias',market:names[1],day:-1,price:160,doc:'b'.repeat(64)});
  await regional({product:'package-separated',name:'Package separated',market:names[0],day:-1,price:100,presentation:'Bulto',quantity:25});
  await regional({product:'package-separated',name:'Package separated',market:names[1],day:-1,price:900,presentation:'Caja',quantity:50,doc:'b'.repeat(64)});
  const candidates=JSON.stringify(['corrected-alias','package-separated'].map(product_id=>({product_id,latest_date:day})));
  const rows=(await db.query(sql.CITY_CATALOG_SQL,['',candidates])).rows;
  const byId=new Map(rows.map(row=>[row.id,row]));
  assert.equal(byId.has('corrected-alias'),false,
    'a source correction participates under its corrected product identity and conflicts with that identity');
  assert.equal(byId.has('package-separated'),true,
    'different package presentation and quantity form separate typed keys rather than a false conflict');
});
check('catalog category overlay is bound to both source document and locator during alias conflict checks',async()=>{
  const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos'];
  for(let i=0;i<names.length;i++) await db.query(
    'INSERT INTO market(id,name,city,region,municipality_id) VALUES($1,$2,$3,$4,$5)',
    [`overlay-alias-${i}`,names[i],'Bogotá','Bogotá, D.C.','11001']);
  const sharedLocator='same-locator-two-sources';
  async function sourceRow(doc,market){
    await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
      VALUES($1,$2,CURRENT_DATE-1,'overlay-leak','Overlay leakage', $3,'Frutas','Bulto',25,'Kilogramo',1,'Ronda',100,102,'package',1)`,
      [doc,sharedLocator,market]);
  }
  await db.query("INSERT INTO product(id,name,category) VALUES('overlay-leak','Overlay leakage','Frutas')");
  await sourceRow('a'.repeat(64),names[0]);
  await sourceRow('b'.repeat(64),names[1]);
  await db.query('INSERT INTO verified_regional_category_overlay_data VALUES($1,$2,$3)',
    ['a'.repeat(64),sharedLocator,'Frutas > Verified leaf']);
  const day=(await db.query("SELECT (CURRENT_DATE-1)::text AS day")).rows[0].day;
  const candidates=JSON.stringify([{product_id:'overlay-leak',latest_date:day}]);
  const rows=(await db.query(sql.CITY_CATALOG_SQL,['',candidates])).rows;
  assert.equal(rows.some(row=>row.id==='overlay-leak'),false,
    'the verified path for one document cannot leak to a different document with the same locator');
  assert.deepEqual((await db.query('SELECT document_id,source_locator,category FROM regional_price ORDER BY document_id')).rows,
    [{document_id:'a'.repeat(64),source_locator:sharedLocator,category:'Frutas'},
     {document_id:'b'.repeat(64),source_locator:sharedLocator,category:'Frutas'}],
    'the catalog reads the overlay without changing retained raw categories');
});
check('2022 uncurated Corabastos literal contributes its exact native package to the regional city catalog',async()=>{
  await db.query(`INSERT INTO market(id,name,city,region,municipality_id)
    VALUES('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`);
  const locator=await regional({market:'Bogotà, Corabastos',day:-1,price:26000,
    presentation:'Canastilla',quantity:20});
  await db.query('UPDATE regional_price SET observed_on=$1::date,min_price=26000,max_price=28000 WHERE source_locator=$2',
    ['2022-01-03',locator]);
  const names=(await db.query(sql.CITY_CATALOG_NAMES_SQL)).rows;
  const candidate=names.find(row=>row.product_id==='city');
  assert.equal(candidate.latest_date,'2022-01-03');
  const card=(await db.query(sql.CITY_CATALOG_SQL,['Bogotá, D.C.',JSON.stringify([candidate])])).rows;
  assert.equal(card.length,1);
  assert.equal(card[0].market_count,'1');
  assert.equal(Number(card[0].price),27000);
  const availability=(await db.query(monthlyModule.CATALOG_MARKETS_SQL)).rows;
  assert.equal(availability.find(row=>row.region==='Bogotá, D.C.').has_city,true);
  assert.equal(availability.find(row=>row.region==='Uno').has_city,false);
  assert.equal((await db.query('SELECT count(*)::int n FROM regional_price')).rows[0].n,1);
});
check('monthly canonical card keeps its price while current local city packages supply exact child paths', async () => {
  const old = await regional({ day: -5, market: 'A', quantity: 2.5, price: 900 });
  const citrus = await regional({ day: -1, market: 'A', quantity: 2.5, price: 20 });
  const tropical = await regional({ day: -1, market: 'A', quantity: 12.5, price: 78,
    doc: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' });
  const elsewhere = await regional({ day: -1, market: 'B', quantity: 2.5, price: 30 });
  for (const [document, locator, path] of [
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', old, ['Frutas', 'Otras frutas']],
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', citrus, ['Frutas', 'Cítricos']],
    ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', tropical, ['Frutas', 'Tropicales']],
    ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', elsewhere, ['Frutas', 'Bayas']],
  ]) await db.query('INSERT INTO regional_classification VALUES($1,$2,$3)', [document, locator, path]);
  const names = (await db.query(sql.CITY_CATALOG_NAMES_SQL)).rows;
  const monthlyCard = { id: 'city', name: 'Ciudad', category: 'Frutas', image_key: 'produce',
    price: 2471, previous_price: 2200, date: '2026-08-31', market_count: 1,
    unit: 'kg', source: 'DANE · SIPSA', period: 'monthly', series: 'monthly',
    presentation: 'Por unidad de medida', units: '1 kg' };
  const monthlySnapshot = { products: new Map([['uno', [monthlyCard]], ['dos', [monthlyCard]]]),
    regions: ['Uno', 'Dos'], expiresAt: Infinity };
  const catalogDb = { query: (query, parameters) => query.includes('FROM coffee_reference')
    ? Promise.resolve({ rows: [] }) : db.query(query, parameters) };
  const queries = moduleSQL('queries.ts', {
    './db': { database: () => catalogDb, WINDOW }, './catalog-sql': sql,
    './city-catalog-names': { cityCatalogNames: async () => names },
    './monthly-catalog': { monthlyCatalogSnapshot: async () => monthlySnapshot },
    '../label-normalization': require('./helpers/load-label-normalization.cjs')(),
  });
  const one = await queries.catalog('Uno');
  assert.equal(one.products.length, 1, 'same ID must not become a second price card');
  assert.equal(one.products[0].series, 'monthly');
  assert.equal(one.products[0].price, 2471);
  assert.equal(one.products[0].previous_price, 2200);
  assert.deepEqual(one.products[0].category_paths, [['Frutas', 'Cítricos'], ['Frutas', 'Tropicales']]);
  assert.ok(!JSON.stringify(one.products[0].category_paths).includes('Otras frutas'));
  assert.ok(!JSON.stringify(one.products[0].category_paths).includes('Bayas'));
  const two = await queries.catalog('Dos');
  assert.deepEqual(two.products[0].category_paths, [['Frutas', 'Bayas']]);
  const unified = moduleSQL('catalog.ts', {
    './queries': { catalog: async () => one },
    './city-catalog-names': { cityCatalogNames: async () => names },
    './summary-references': { latestSummaryReferences: async () => [] },
    './official-references': { latestOfficialReferenceSnapshot: async () => ({ value: [], expires: Infinity }) },
    '../label-normalization': require('./helpers/load-label-normalization.cjs')(),
  }, { URLSearchParams });
  const shown = await unified.unifiedCatalog('Uno', true);
  assert.equal(shown.products.length, 1);
  assert.equal(shown.products[0].series, 'monthly');
  assert.equal(shown.products[0].price, 2471);
  assert.deepEqual(shown.products[0].category_paths, [['Frutas', 'Cítricos'], ['Frutas', 'Tropicales']]);
  assert.match(shown.products[0].href, /series=monthly/);
  await db.query("INSERT INTO city_pdf_publication_conflict(document_id) VALUES (repeat('b',64))");
  const guarded = await queries.catalog('Uno');
  assert.equal(guarded.products[0].price, 2471);
  assert.deepEqual(guarded.products[0].category_paths, [['Frutas', 'Cítricos']],
    'unpublished city evidence cannot supply a canonical card category');
});
check('a conflicted PDF disappears from regional and catalog reads without hiding a sibling', async () => {
  const blocked = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const sibling = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  await regional({ doc: blocked, market: 'A', price: 10 });
  await regional({ doc: sibling, market: 'B', price: 30 });
  assert.equal((await db.query('SELECT count(*)::int AS n FROM regional_price')).rows[0].n, 2);
  await db.query('INSERT INTO city_pdf_publication_conflict(document_id) VALUES($1)', [blocked]);
  assert.deepEqual((await db.query('SELECT document_id FROM published_regional_price')).rows.map(row => row.document_id), [sibling]);
  const current = (await db.query(latestRegional)).rows;
  assert.deepEqual(current.map(row => row.document_id), [sibling]);
  const day = (await db.query('SELECT observed_on::text AS day FROM published_regional_price LIMIT 1')).rows[0].day;
  const candidates = JSON.stringify([{ product_id: 'city', latest_date: day }]);
  const cards = (await db.query(sql.CITY_CATALOG_SQL, ['', candidates])).rows;
  assert.ok(cards.length > 0);
  assert.ok(cards.every(card => !JSON.stringify(card).includes(blocked)));
});
check('latest round/revision and package ties retain exact card price and unit', async () => {
  await regional({ price: 10 }); await regional({ price: 20, round: 2 }); await regional({ price: 30, round: 2, doc: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' });
  await regional({ price: 40, market: 'B' }); await regional({ price: 900, quantity: 50 });
  const result = await equivalent(); assert.equal(result.rows[0].price, '36.0000000000000000'); assert.equal(result.rows[0].units, '25 Kilogramo');
});
check('one department includes every source case variant in monthly and city aggregates', async () => {
  await db.query("UPDATE market SET region=CASE id WHEN 'a' THEN 'ATLÁNTICO' WHEN 'b' THEN 'Atlántico' ELSE region END");
  await monthly({ market: 'a', price: 100 });
  await monthly({ market: 'b', price: 300 });
  await regional({ market: 'A', price: 10 });
  await regional({ market: 'B', price: 30 });
  const recent = await db.query(monthlyModule.RECENT_MONTHLY_QUOTES_SQL);
  const metadata = await db.query(monthlyModule.CATALOG_PRODUCTS_SQL);
  const availability = await db.query(monthlyModule.CATALOG_MARKETS_SQL);
  const aggregated = monthlyModule.aggregateMonthlyCatalog(recent.rows, metadata.rows, availability.rows);
  assert.deepEqual([...aggregated.regions], ['Atlántico']);
  for (const key of ['atlántico', 'ATLÁNTICO', 'Atlántico']) {
    const row = aggregated.products.get(key)[0];
    assert.equal(row.price, 200);
    assert.equal(row.market_count, 2);
  }
  const candidates = JSON.stringify([{product_id:'city',latest_date:new Date().toISOString().slice(0,10)}]);
  for (const region of ['Atlántico','ATLÁNTICO','atlántico']) {
    const rows = (await db.query(sql.CITY_CATALOG_SQL,[region,candidates])).rows;
    assert.equal(rows.length,1);
    assert.equal(Number(rows[0].price),21);
    assert.equal(Number(rows[0].market_count),2);
  }
  assert.deepEqual((await db.query('SELECT region FROM market WHERE id IN (\'a\',\'b\') ORDER BY id')).rows,
    [{region:'ATLÁNTICO'},{region:'Atlántico'}]);
});
check('newest product date beats an older package with more markets', async () => {
  await regional({ day: -10, market: 'A', quantity: 50 }); await regional({ day: -10, market: 'B', quantity: 50 });
  await regional({ day: -1, price: 700 });
  assert.equal((await equivalent()).rows[0].price, '701.0000000000000000');
});
check('region selects its own historical date and retains city fallback despite a monthly quote elsewhere', async () => {
  await monthly({ product: 'city', market: 'a' });
  await regional({ day: -1, market: 'A' }); await regional({ day: -900, market: 'B', price: 80 });
  assert.equal((await equivalent()).rows.length, 0);
  const result = await equivalent('Dos'); assert.equal(result.rows.length, 1); assert.equal(result.rows[0].price, '81.0000000000000000');
  assert.equal((await equivalent('absent')).rows.length, 0);
});
check('regional latest dates group only real pairs and preserve old local prices despite newer or future rows elsewhere', async () => {
  await regional({ product: 'city', market: 'A', day: -1, price: 900 });
  await regional({ product: 'city', market: 'B', day: -1500, price: 70 });
  await regional({ product: 'city', market: 'B', day: 30, price: 800 });
  await regional({ product: 'rice', market: 'A', day: -1, price: 50 });
  await regional({ product: 'milk', market: 'B', day: -1, price: 60 });
  // B is a valid regional market, but the candidate rice product has no B quote.
  const result = await equivalent('Dos');
  assert.equal(result.rows.find((row) => row.id === 'city').price, '71.0000000000000000');
  assert.ok(!result.rows.some((row) => row.id === 'rice'));
  assert.equal(result.rows.find((row) => row.id === 'milk').price, '61.0000000000000000');
  assert.deepEqual((await equivalent('Vacía')).rows, []);
  assert.deepEqual((await equivalent('absent')).rows, []);
});
check('sparse region with long unrelated histories never executes a per-product/per-market scalar date lookup', async () => {
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    SELECT repeat('a',64),'sparse-'||n,CURRENT_DATE-20-(n%1000),CASE n%2 WHEN 0 THEN 'city' ELSE 'rice' END,
      'Historical alias','A','Frutas','Bulto',25,'Kilogramo',1,'Ronda',10,12,'package',1 FROM generate_series(1,100000) n`);
  await regional({ product: 'milk', market: 'B' });
  await db.query('ANALYZE regional_price');
  const candidates = JSON.stringify([{ product_id: 'city', latest_date: '2020-01-01' }, { product_id: 'rice', latest_date: '2020-01-01' }]);
  assert.deepEqual((await db.query(sql.CITY_CATALOG_SQL, ['Dos', candidates])).rows, []);
  const plan = (await db.query('EXPLAIN (ANALYZE,FORMAT JSON) '+sql.CITY_CATALOG_SQL, ['Dos', candidates])).rows[0]['QUERY PLAN'][0];
  const subplans = [];
  function inspectSubplans(node) {
    if(node['Parent Relationship']==='SubPlan') subplans.push(node);
    for(const child of node.Plans || []) inspectSubplans(child);
  }
  inspectSubplans(plan.Plan);
  assert.ok(subplans.every(node => node['Relation Name']!=='regional_price' || node['Node Type']!=='Seq Scan'),
    'Alias conflict probes may be scalar, but must never scan full regional history');
  let examined = 0;
  function visit(node) {
    if (node['Relation Name'] === 'regional_price') {
      examined += (node['Actual Rows'] + (node['Rows Removed by Filter'] || 0)) * node['Actual Loops'];
    }
    for (const child of node.Plans || []) visit(child);
  }
  visit(plan.Plan);
  assert.ok(examined <= 100010, `At most one pass over the fixture plus bounded correction probes: ${examined}`);
  const latestRows = (await db.query(latestRegional)).rows;
  assert.ok(latestRows.some((row) => row.market_name === 'A' && row.product_name === 'Historical alias'));
  assert.ok(latestRows.some((row) => row.market_name === 'B' && row.product_name === 'Nombre literal'));
  const regionalPlan = (await db.query('EXPLAIN (ANALYZE,FORMAT JSON) ' + latestRegional)).rows[0]['QUERY PLAN'][0];
  function fullHistoryScan(node) {
    return (node['Node Type'] === 'Seq Scan' && node['Relation Name'] === 'regional_price') ||
      (node.Plans || []).some(fullHistoryScan);
  }
  assert.equal(fullHistoryScan(regionalPlan.Plan), false, 'Latest regional rows must avoid a full quote-history scan');
});
check('all literal historical aliases survive; unknown markets and future-only dates do not win', async () => {
  await regional({ name: 'Antiguo*', day: -1000 }); await regional({ name: 'Nuevo', price: 50 });
  await regional({ name: 'No geografía', market: 'Unknown', day: 0 });
  await regional({ name: 'Futuro', day: 100 });
  const result = await equivalent(); assert.deepEqual(result.names.map((r) => r.product_name), ['Antiguo*', 'No geografía', 'Nuevo']);
  assert.equal(result.rows[0].price, '51.0000000000000000');
});
check('correction identity reaches catalog names and quote cards while the source row stays original', async () => {
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    VALUES(repeat('a',64),'corrected-row',CURRENT_DATE-1,'rice','Raw rice label','A','Frutas','Bulto',25,'Kilogramo',1,'Ronda',10,12,'package',1)`);
  await db.query(`INSERT INTO regional_price_product_correction VALUES
    (repeat('a',64),'corrected-row','city','Corrected fruit label')`);
  const names = (await db.query(sql.CITY_CATALOG_NAMES_SQL)).rows;
  assert.deepEqual(names.map(({ product_id, product_name }) => ({ product_id, product_name })),
    [{ product_id: 'city', product_name: 'Corrected fruit label' }]);
  const selected = names.map(({ product_id, latest_date }) => ({ product_id, latest_date }));
  const cards = (await db.query(sql.CITY_CATALOG_SQL, ['', JSON.stringify(selected)])).rows;
  assert.equal(cards[0].id, 'city');
  const quotes = (await db.query(`SELECT product_id,product_name FROM (${city}) q`)).rows;
  assert.deepEqual(quotes, [{ product_id: 'city', product_name: 'Corrected fruit label' }]);
  const planningSource = fs.readFileSync(path.join(server, 'planning.ts'), 'utf8');
  const evidenceSQL = planningSource.match(/"(SELECT resolved\.product_name,resolved\.market_name,resolved\.observed_on,resolved\.presentation,resolved\.quantity,resolved\.source_unit,resolved\.round_label,resolved\.min_price,resolved\.max_price,resolved\.unit,resolved\.min_unit_price,resolved\.max_unit_price,resolved\.source_page,resolved\.source_locator FROM resolved_regional_price resolved JOIN published_regional_price accepted ON accepted\.document_id=resolved\.document_id AND accepted\.source_locator=resolved\.source_locator WHERE resolved\.document_id=\$1 ORDER BY resolved\.source_page,resolved\.source_locator)"/)[1];
  const evidence = (await db.query(evidenceSQL, ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'])).rows;
  assert.equal(evidence[0].product_name, 'Corrected fruit label');
  const regional = (await db.query(latestRegional)).rows;
  assert.equal(regional[0].product_name, 'Corrected fruit label');
  const original = (await db.query("SELECT product_id,product_name FROM regional_price WHERE source_locator='corrected-row'")).rows;
  assert.deepEqual(original, [{ product_id: 'rice', product_name: 'Raw rice label' }]);
});
check('monthly averages, previous months, litre and rice units and review exclusions remain unchanged', async () => {
  await monthly({ price: 100 }); await monthly({ month: 2, price: 80 });
  await monthly({ market: 'b', price: 120 }); await monthly({ market: 'b', month: 2, price: 100 });
  await monthly({ product: 'milk', source: 'dane-milk-farm', unit: 'litre', price: 1700 });
  await monthly({ product: 'rice', source: 'dane-rice-mill', price: 2200, doc: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' });
  await db.query("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES('https://example.invalid/new','rice','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','review')");
  const result = await equivalent(); assert.equal(result.base.find((r) => r.id === 'monthly').price, '110.0000000000000000');
  assert.equal(result.base.find((r) => r.id === 'monthly').previous_price, '90.0000000000000000');
  assert.equal(result.base.find((r) => r.id === 'milk').units, '1 litro'); assert.ok(!result.base.some((r) => r.id === 'rice'));
});
check('100000 old rows retain names and exact output while quote revision work stays on the winning date', async () => {
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    SELECT 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','history-'||n,CURRENT_DATE-20-(n%1000),'city','Alias '||(n%10),'A','Frutas','Bulto',25,'Kilogramo',1,'Ronda',10,12,'package',1 FROM generate_series(1,100000) n`);
  await regional({ day: -1, price: 99 }); await db.query('ANALYZE regional_price');
  const result = await equivalent(); assert.equal(result.names.length, 11); assert.equal(result.rows[0].price, '100.0000000000000000');
  const plan = (await db.query('EXPLAIN (FORMAT JSON) '+sql.CITY_CATALOG_NAMES_SQL)).rows[0]['QUERY PLAN'];
  assert.ok(JSON.stringify(plan).includes('regional_catalog_names'));
  const availabilityPlan=(await db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+monthlyModule.CATALOG_MARKETS_SQL)).rows[0]['QUERY PLAN'][0];
  const indexNames=[];
  const visit=node=>{if(node['Index Name']) indexNames.push(node['Index Name']);for(const child of node.Plans||[])visit(child)};
  visit(availabilityPlan.Plan);
  assert.ok(indexNames.includes('regional_market_latest'),`city availability must seek exact market names: ${indexNames}`);
  assert.ok(availabilityPlan['Execution Time']<1000,`100000 unrelated city rows made the market picker slow: ${availabilityPlan['Execution Time']}ms`);
});
check('an intermediate or missing previous month keeps the prior-price comparison unavailable', async () => {
  await monthly({ price: 100 }); await monthly({ month: 2, price: 80 });
  await db.query(`INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    SELECT product_id,market_id,source_id,observed_on+10,period,unit,90,source_url,document_id FROM price_observation WHERE price=80`);
  const result = await equivalent(); assert.equal(result.base[0].previous_price, null);
  await monthly({ product: 'milk', source: 'dane-milk-farm', unit: 'litre', price: 1700 });
  assert.equal((await equivalent()).base.find((r) => r.id === 'milk').previous_price, null);
});
check('integer-cent averages exactly match PostgreSQL across fractional and large values', async () => {
  for (const values of [['0.01','0.02','0.02'], ['100000.00','1.13','19.07'], ['99999999999999.99','99999999999999.98','0.01'], ['10000.00','10000.01'], ['0.00','0.01','0.00']]) {
    const expected = Number((await db.query('SELECT avg(value::numeric(16,2)) AS price FROM unnest($1::text[]) value', [values])).rows[0].price);
    const sum = values.reduce((total, value) => total + BigInt(value.replace('.', '')), 0n);
    assert.equal(monthlyModule.averageCents(sum, values.length), expected, values.join(','));
  }
});
check('mixed recent sources, stale/future/reviewed rows and every department match the SQL oracle', async () => {
  await db.query(`INSERT INTO product(id,name,category,priority) SELECT 'generated-'||n,'Producto '||n,'Fixture',n%4 FROM generate_series(1,15) n;
    INSERT INTO market(id,name,city,region) SELECT 'generated-'||n,'Mercado '||n,'Ciudad '||n,CASE WHEN n%4=0 THEN '' ELSE 'Departamento '||(n%4) END FROM generate_series(1,12) n;
    INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    SELECT 'generated-'||p,'generated-'||m,CASE p%3 WHEN 0 THEN 'dane-milk-farm' WHEN 1 THEN 'dane-rice-mill' ELSE 'dane-sipsa' END,
      (date_trunc('month',CURRENT_DATE)-n*interval '1 month'+interval '1 month - 1 day')::date,'monthly',
      CASE p%3 WHEN 0 THEN 'litre' ELSE 'kg' END,((p*1234567+m*13+n*29)%999999)/100.0,'https://example.invalid/',repeat('a',64)
    FROM generate_series(1,15) p CROSS JOIN generate_series(1,12) m CROSS JOIN generate_series(1,18) n
    WHERE (p+m+n)%7<>0;
    INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    VALUES('generated-1','generated-1','dane-rice-mill',CURRENT_DATE+100,'monthly','kg',9999,'https://example.invalid/',repeat('b',64));
    INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status)
    VALUES('https://example.invalid/dated-review','monthly',repeat('a',64),(date_trunc('month',CURRENT_DATE)-interval '1 day')::date,'review')`);
  for (const region of ['', 'Departamento 1', 'Departamento 2', 'Departamento 3', 'absent']) await equivalent(region);
});
check('bounded monthly pairs retain every canonical and unified source-backed card field and order', async () => {
  for (const row of [
    {product:'monthly',market:'a',month:1,price:101},
    {product:'monthly',market:'a',month:2,price:81},
    {product:'monthly',market:'a',month:3,price:61},
    {product:'monthly',market:'b',month:1,price:301},
    {product:'monthly',market:'b',month:2,price:201},
    {product:'monthly',market:'a',month:1,price:51,unit:'unit'},
    {product:'monthly',market:'a',month:2,price:41,unit:'unit'},
    {product:'monthly',market:'a',month:0,price:9999,unit:'unit'},
    {product:'milk',market:'a',month:1,price:1700,source:'dane-milk-farm',unit:'litre'},
    {product:'milk',market:'a',month:2,price:1600,source:'dane-milk-farm',unit:'litre'},
    {product:'rice',market:'b',month:1,price:700,source:'dane-rice-mill',unit:'kg'},
    {product:'rice',market:'b',month:2,price:600,source:'dane-rice-mill',unit:'kg'},
  ]) await monthly(row);
  const full = (await db.query(monthlyModule.RECENT_MONTHLY_QUOTES_SQL)).rows;
  const pairs = (await db.query(monthlyModule.RECENT_MONTHLY_PAIRS_SQL)).rows;
  assert.ok(pairs.length < full.length);
  assert.ok(pairs.every(row => Number(row.same_date_count) === 1));
  const metadata = (await db.query(monthlyModule.CATALOG_PRODUCTS_SQL)).rows;
  const markets = (await db.query(monthlyModule.CATALOG_MARKETS_SQL)).rows;
  const baseline = monthlyModule.aggregateMonthlyCatalog(full, metadata, markets);
  const current = monthlyModule.aggregateMonthlyCatalog(pairs, metadata, markets);
  const serial = result => JSON.parse(JSON.stringify({products:[...result.products],regions:result.regions}));
  assert.deepEqual(serial(current), serial(baseline));

  const source = {quote_key:'q'.repeat(64),product_id:'monthly',product_name:'Mensual',
    category:'Verduras',price:123,previous_price:null,observed_on:'2026-08-31',
    market:'A',department:'Uno',unit:'kg',publisher:'DANE · SIPSA',
    basis:'Precio semanal verificado',currency:'COP',series:'dane-weekly',
    source_url:'https://example.invalid/official',document_id:'a'.repeat(64),
    source_locator:'PDF page 1,table 1,row 1',details:{published_unit:'kg'}};
  const summary = {...source,quote_key:'summary-'+'b'.repeat(64),product_id:'summary-product:'+ 'b'.repeat(64),
    canonical_product_id:null,product_name:'Resumen literal',series:'dane-monthly-summary',
    source_locator:'Sheet1!row 2',source_url:'https://example.invalid/summary'};
  const snapshot = result => ({products:result.products.get('') || [],regions:result.regions,
    cacheExpiresAt:Infinity,latestDate:'2026-08-31'});
  const unify = result => moduleSQL('catalog.ts', {
    './queries':{catalog:async()=>snapshot(result)},
    './city-catalog-names':{cityCatalogNames:async()=>[]},
    './summary-references':{latestSummaryReferences:async()=>[summary]},
    './official-references':{latestOfficialReferenceSnapshot:async()=>({value:[source],expires:Infinity})},
    '../label-normalization':require('./helpers/load-label-normalization.cjs')(),
  }, {URLSearchParams}).unifiedCatalog();
  assert.deepEqual(JSON.parse(JSON.stringify(await unify(current))),
                   JSON.parse(JSON.stringify(await unify(baseline))));
});
check('equal-date source ties force the exact full read in one snapshot', async () => {
  await monthly({product:'monthly',market:'a',month:1,price:100,source:'dane-sipsa'});
  await monthly({product:'monthly',market:'a',month:1,price:200,source:'dane-rice-mill'});
  await monthly({product:'monthly',market:'a',month:2,price:80,source:'dane-sipsa'});
  const pairRows = (await db.query(monthlyModule.RECENT_MONTHLY_PAIRS_SQL)).rows;
  assert.ok(pairRows.some(row => Number(row.same_date_count) > 1));
  const full = (await db.query(monthlyModule.RECENT_MONTHLY_QUOTES_SQL)).rows;
  const metadata = (await db.query(monthlyModule.CATALOG_PRODUCTS_SQL)).rows;
  const markets = (await db.query(monthlyModule.CATALOG_MARKETS_SQL)).rows;
  const calls = []; let releases = 0;
  const loaded = moduleSQL('monthly-catalog.ts', { './db': {WINDOW,
    database: () => ({connect:async()=>({query:(statement)=>{
      calls.push(statement);return db.query(statement);
    },release:()=>{releases++;}})})} });
  const result = await loaded.monthlyCatalogSnapshot();
  assert.deepEqual(calls.slice(0,5), ['BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY',
    loaded.RECENT_MONTHLY_PAIRS_SQL, loaded.RECENT_MONTHLY_QUOTES_SQL,
    loaded.CATALOG_PRODUCTS_SQL, loaded.CATALOG_MARKETS_SQL]);
  assert.equal(calls.at(-1),'COMMIT');
  assert.equal(releases,1);
  const expected = monthlyModule.aggregateMonthlyCatalog(full,metadata,markets);
  assert.deepEqual(JSON.parse(JSON.stringify([...result.products])),
                   JSON.parse(JSON.stringify([...expected.products])));
});

test('snapshot deduplicates concurrent callers, expires and never caches partial or stale failures', async () => {
  let clock = 1000, calls = 0, releases = 0, failed = false, price = '10.01';
  const transactions = [];
  class Clock extends Date { static now() { return clock; } }
  const query = async text => {
    if (/^(BEGIN|COMMIT|ROLLBACK)/.test(text)) { transactions.push(text); return { rows: [] }; }
    calls++;
    await Promise.resolve();
    if (failed && text === monthlyModule.CATALOG_PRODUCTS_SQL) throw new Error('read failed');
    if (text === monthlyModule.RECENT_MONTHLY_PAIRS_SQL) return { rows: [{product_id:'p',market_id:'m',source_id:'dane-sipsa',unit:'kg',price,observed_on:'2026-08-31',region:'R',same_date_count:1}] };
    if (text === monthlyModule.CATALOG_PRODUCTS_SQL) return {rows:[{id:'p',name:'Producto',category:'Fruta',image_key:'produce',priority:1}]};
    return {rows:[{region:'R',has_city:false}]};
  };
  const loaded = moduleSQL('monthly-catalog.ts', { './db': { WINDOW, database: () => ({connect: async () => ({query,release: () => { releases++; }})}) }, './city-market-alias': cityAlias }, { Date: Clock });
  const [a,b,c] = await Promise.all([loaded.monthlyCatalogSnapshot(),loaded.monthlyCatalogSnapshot(),loaded.monthlyCatalogSnapshot()]);
  assert.equal(calls,3); assert.equal(a,b); assert.equal(b,c); assert.equal(a.products.get('')[0].price,10.01); assert.equal(a.expiresAt,301000);
  clock += 300001; failed=true; price='20.03';
  await assert.rejects(loaded.monthlyCatalogSnapshot(), /read failed/);
  await assert.rejects(loaded.monthlyCatalogSnapshot(), /read failed/); assert.equal(calls,7);
  failed=false;
  const repaired = await loaded.monthlyCatalogSnapshot(); assert.equal(calls,10); assert.equal(repaired.products.get('')[0].price,20.03);
  assert.equal(await loaded.monthlyCatalogSnapshot(), repaired); assert.equal(calls,10);
  assert.equal(releases,4); assert.equal(transactions.filter(t => t==='ROLLBACK').length,2);
  assert.equal(transactions.filter(t => t==='COMMIT').length,2);
});
test('monthly snapshot releases its database client before pure aggregation and rejects bad rows', async () => {
  const statements = []; let released = false;
  const loaded = moduleSQL('monthly-catalog.ts', { './db': { WINDOW,
    database: () => ({connect:async()=>({query:async text=>{
      statements.push(text);
      if (text === loaded.RECENT_MONTHLY_PAIRS_SQL) return {rows:[{
        product_id:'p',market_id:'m',source_id:'dane-sipsa',unit:'kg',price:'invalid',
        observed_on:'2026-08-31',region:'R',same_date_count:1,
      }]};
      if (text === loaded.CATALOG_PRODUCTS_SQL) return {rows:[{
        id:'p',name:'Producto',category:'Fruta',image_key:'produce',priority:1,
      }]};
      if (text === loaded.CATALOG_MARKETS_SQL) return {rows:[{region:'R',has_city:false}]};
      return {rows:[]};
    },release:()=>{released=true;}})})} });
  await assert.rejects(loaded.monthlyCatalogSnapshot(), /INVALID_CATALOG_PRICE/);
  assert.equal(released,true);
  assert.equal(statements.at(-1),'COMMIT');
  assert.ok(!statements.includes('ROLLBACK'));
});
test('outer department cache cannot extend the shared monthly snapshot expiry', async () => {
  let clock=1000, reads=0;
  class Clock extends Date { static now() { return clock; } }
  const loaded = moduleSQL('catalog.ts', {
    './city-catalog-names':{cityCatalogNames:async()=>[]},
    './queries':{catalog:async()=>{reads++;return {products:[],regions:[],latestDate:null,cacheExpiresAt:clock<301000?301000:clock+300000};}},
    './summary-references':{latestSummaryReferences:async()=>[]},
    './official-references':{latestOfficialReferenceSnapshot:async()=>({value:[],expires:Infinity})},
  },{Date:Clock,URLSearchParams});
  await loaded.unifiedCatalog('First'); clock=270000;
  await loaded.unifiedCatalog('Later'); assert.equal(reads,2);
  clock=300999; await loaded.unifiedCatalog('Later'); assert.equal(reads,2);
  clock=301001; await loaded.unifiedCatalog('Later'); assert.equal(reads,3);
});

test('unified cards do not retain an official catalog snapshot past its own expiry', async () => {
  let clock=1000, reads=0;
  class Clock extends Date { static now() { return clock; } }
  const loaded = moduleSQL('catalog.ts', {
    './city-catalog-names':{cityCatalogNames:async()=>[]},
    './queries':{catalog:async()=>({products:[],regions:[],latestDate:null,cacheExpiresAt:Infinity})},
    './summary-references':{latestSummaryReferences:async()=>[]},
    './official-references':{
      latestOfficialReferenceSnapshot:async()=>{reads++;return {value:[],expires:clock<10000?10000:clock+300000};},
    },
  },{Date:Clock,URLSearchParams});
  await loaded.unifiedCatalog(); clock=9999;
  await loaded.unifiedCatalog(); assert.equal(reads,1);
  clock=10001; await loaded.unifiedCatalog(); assert.equal(reads,2);
});

test('slow canonical read cannot pair old official prices with a newer concurrent deadline', async () => {
  let clock=99, reads=0, release;
  class Clock extends Date { static now() { return clock; } }
  const gate=new Promise(resolve=>{release=resolve;});
  let source={value:[{quote_key:'source-key',product_id:'pepino-cohombro',product_name:'Pepino cohombro',
    category:'Verduras',publisher:'DANE',series:'dane-weekly',basis:'Precio mayorista semanal',
    currency:'COP',unit:'kg',market:'Ibagué',observed_on:'2026-08-21',price:920,
    previous_price:null,details:{}}],expires:100};
  const loaded=moduleSQL('catalog.ts',{
    './city-catalog-names':{cityCatalogNames:async()=>[]},
    './queries':{catalog:async()=>{if(!reads)await gate;return {products:[],regions:[],latestDate:null,cacheExpiresAt:Infinity};}},
    './summary-references':{latestSummaryReferences:async()=>[]},
    './official-references':{latestOfficialReferenceSnapshot:async()=>{reads++;return source;}},
    '../label-normalization':require('./helpers/load-label-normalization.cjs')(),
  },{Date:Clock,URLSearchParams});
  const pending=loaded.unifiedCatalog();
  for(let i=0;i<10 && !reads;i++) await Promise.resolve();
  assert.equal(reads,1,'the first source read has started before advancing the clock');
  clock=100;
  source={value:[{...source.value[0],price:1075}],expires:200};
  release();
  const old=await pending;
  assert.equal(old.products[0].price,920,'the in-flight response keeps its consumed original value');
  clock=150;
  const fresh=await loaded.unifiedCatalog();
  assert.equal(fresh.products[0].price,1075,'old response expired at100, not the refreshed source deadline200');
  assert.equal(reads,2);
});
