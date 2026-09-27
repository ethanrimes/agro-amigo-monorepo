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
    exports, require: (name) => name === 'server-only' ? {} : mocks[name], ...globals,
  });
  return exports;
}
const sql = moduleSQL('catalog-sql.ts', { './db': { WINDOW } });
const monthlyModule = moduleSQL('monthly-catalog.ts', { './db': { WINDOW } });
const city = moduleSQL('price-quotes.ts', { './db': { WINDOW }, './summary-references': {} }).CITY_PRICE_QUOTES;
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
  await db.query("SET search_path=pg_temp; SET statement_timeout='10s'");
  for (const table of tables) await db.query(`CREATE TEMP TABLE ${table} (LIKE public.${table} INCLUDING ALL)`);
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
  await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,source_page)
    VALUES($1,$2,CURRENT_DATE+$3::integer,$4,$5,$6,'Frutas',$7,$8,$9,$10,'Ronda',$11::numeric,$11::numeric+2,'package',1)`,
    [doc, 'row-' + (++seq), day, product, name, market, presentation, quantity, unit, round, price]);
}
async function monthly({ product = 'monthly', market = 'a', month = 1, price = 100, source = 'dane-sipsa', unit = 'kg', doc = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } = {}) {
  await db.query(`INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id)
    VALUES($1,$2,$3,(date_trunc('month',CURRENT_DATE)-($4||' months')::interval+interval '1 month - 1 day')::date,'monthly',$5,$6,'https://example.invalid/',$7)`, [product, market, source, month, unit, price, doc]);
}
const sorted = (rows) => [...rows].sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
async function equivalent(region = '') {
  const names = (await db.query(sql.CITY_CATALOG_NAMES_SQL)).rows;
  const expectedNames = (await db.query("SELECT DISTINCT product_id,product_name FROM regional_price WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY product_id,product_name")).rows;
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
  assert.deepEqual(sorted(rows), sorted((await db.query(baseline.city, [region])).rows));
  return { names, base, rows };
}
check('latest round/revision and package ties retain exact card price and unit', async () => {
  await regional({ price: 10 }); await regional({ price: 20, round: 2 }); await regional({ price: 30, round: 2, doc: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' });
  await regional({ price: 40, market: 'B' }); await regional({ price: 900, quantity: 50 });
  const result = await equivalent(); assert.equal(result.rows[0].price, '36.0000000000000000'); assert.equal(result.rows[0].units, '25 Kilogramo');
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
  const serialized = JSON.stringify(plan);
  assert.ok(!serialized.includes('"Parent Relationship":"SubPlan"'), 'No scalar date subquery for nonexistent product/market pairs');
  let examined = 0;
  function visit(node) {
    if (node['Relation Name'] === 'regional_price') {
      examined += (node['Actual Rows'] + (node['Rows Removed by Filter'] || 0)) * node['Actual Loops'];
    }
    for (const child of node.Plans || []) visit(child);
  }
  visit(plan.Plan);
  assert.ok(examined <= 100001, `At most one pass over the fixture, not repeated history scans: ${examined}`);
});
check('all literal historical aliases survive; unknown markets and future-only dates do not win', async () => {
  await regional({ name: 'Antiguo*', day: -1000 }); await regional({ name: 'Nuevo', price: 50 });
  await regional({ name: 'No geografía', market: 'Unknown', day: 0 });
  await regional({ name: 'Futuro', day: 100 });
  const result = await equivalent(); assert.deepEqual(result.names.map((r) => r.product_name), ['Antiguo*', 'No geografía', 'Nuevo']);
  assert.equal(result.rows[0].price, '51.0000000000000000');
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

test('snapshot deduplicates concurrent callers, expires and never caches partial or stale failures', async () => {
  let clock = 1000, calls = 0, releases = 0, failed = false, price = '10.01';
  const transactions = [];
  class Clock extends Date { static now() { return clock; } }
  const query = async text => {
    if (/^(BEGIN|COMMIT|ROLLBACK)/.test(text)) { transactions.push(text); return { rows: [] }; }
    calls++;
    await Promise.resolve();
    if (failed && text === monthlyModule.CATALOG_PRODUCTS_SQL) throw new Error('read failed');
    if (text === monthlyModule.RECENT_MONTHLY_QUOTES_SQL) return { rows: [{product_id:'p',market_id:'m',source_id:'dane-sipsa',unit:'kg',price,observed_on:'2026-08-31',region:'R'}] };
    if (text === monthlyModule.CATALOG_PRODUCTS_SQL) return {rows:[{id:'p',name:'Producto',category:'Fruta',image_key:'produce',priority:1}]};
    return {rows:[{region:'R',has_city:false}]};
  };
  const loaded = moduleSQL('monthly-catalog.ts', { './db': { WINDOW, database: () => ({connect: async () => ({query,release: () => { releases++; }})}) } }, { Date: Clock });
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
test('outer department cache cannot extend the shared monthly snapshot expiry', async () => {
  let clock=1000, reads=0;
  class Clock extends Date { static now() { return clock; } }
  const loaded = moduleSQL('catalog.ts', {
    './city-catalog-names':{cityCatalogNames:async()=>[]},
    './queries':{catalog:async()=>{reads++;return {products:[],regions:[],latestDate:null,cacheExpiresAt:clock<301000?301000:clock+300000};}},
    './summary-references':{latestSummaryReferences:async()=>[]},
    './official-references':{latestOfficialReferences:async()=>[]},
  },{Date:Clock,URLSearchParams});
  await loaded.unifiedCatalog('First'); clock=270000;
  await loaded.unifiedCatalog('Later'); assert.equal(reads,2);
  clock=300999; await loaded.unifiedCatalog('Later'); assert.equal(reads,2);
  clock=301001; await loaded.unifiedCatalog('Later'); assert.equal(reads,3);
});
