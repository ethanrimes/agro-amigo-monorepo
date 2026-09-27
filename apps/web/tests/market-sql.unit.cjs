/* Isolated PostgreSQL equivalence for the market-detail metadata query. */
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client, types } = require('pg');
const window = "observed_on>DATE '2025-09-27' AND observed_on<=DATE '2026-09-27'";
function load(name) {
  const source = fs.readFileSync(path.join(__dirname, '../src/lib/server', name), 'utf8');
  const out = {};
  new Function('exports', 'require', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(out, () => ({ WINDOW: window }));
  return out;
}
const { marketsQuery, marketDetailQuery, marketProductsQuery } = load('market-sql.ts');
const { PRICE_QUOTES } = load('price-quotes.ts');
const socket = process.env.AGRO_MARKET_SQL_TEST_SOCKET;
const enabled = Boolean(socket?.startsWith('/tmp/agro-market-api-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
let db;
types.setTypeParser(1082, (value) => value);
test('one bound market drives identity-only aggregation without global quote payloads', () => {
  const query = marketDetailQuery(window);
  assert.ok(query.includes('WHERE m.id=$1'));
  assert.ok(query.includes('WHERE market_id=m.id'));
  assert.ok(query.includes('WHERE r.market_name=m.name'));
  assert.ok(!query.includes('regional_classification'));
  assert.ok(!query.includes('source_locator'));
});
before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65444, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  await db.query(`CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text);
    CREATE TEMP TABLE municipality(id text PRIMARY KEY,latitude numeric,longitude numeric,department_id text);
    CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text);
    CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,retrieved_at timestamptz);
    CREATE TEMP TABLE ingestion_asset(document_id text,status text,observed_on date);
    CREATE TEMP TABLE price_observation(product_id text,market_id text,source_id text,observed_on date,
      price numeric,min_price numeric,max_price numeric,unit text,document_id text,source_locator text,source_url text,period text,
      PRIMARY KEY(product_id,market_id,source_id,observed_on,period,unit));
    CREATE TEMP VIEW published_price_observation AS SELECT p.* FROM price_observation p WHERE NOT EXISTS (
      SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.status='review'
      AND (a.observed_on IS NULL OR a.observed_on=p.observed_on));
    CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,
      market_name text,category text,presentation text,quantity numeric,source_unit text,round integer,
      min_price numeric,max_price numeric,unit text,source_page integer);
    CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
    CREATE TEMP TABLE supply_observation(market_id text,observed_on date);
    INSERT INTO municipality VALUES('town',4.5,-75.6,'quindio');
    INSERT INTO market VALUES('market-1','Armenia Mercar','Armenia','Quindío','town'),
      ('supply-only','Supply only','Town','Region',NULL),('old-only','Old only','Town','Region',NULL),('empty','Empty','Town','Region',NULL);
    INSERT INTO product VALUES('foo','Food','Frutas'),('reviewed','Reviewed','Frutas'),('crossday','Dated review','Frutas'),('old','Old','Frutas');
    INSERT INTO source_document VALUES('doc','https://example.invalid/original.pdf','2026-09-01'),
      ('newdoc','https://example.invalid/original.pdf','2026-09-25');
    INSERT INTO price_observation SELECT p,'market-1','dane',d::date,100,90,110,'kg',doc,'row:1','https://example.invalid/original.xlsx','monthly'
      FROM (VALUES('foo','2026-09-25','doc'),('foo','2026-09-26','newdoc'),('reviewed','2026-09-24','reviewdoc'),
      ('crossday','2026-09-24','dateddoc'),('crossday','2026-09-23','dateddoc'),('old','2013-01-01','doc'),('old','2999-01-01','doc')) v(p,d,doc);
    INSERT INTO price_observation VALUES('old','old-only','dane','2013-01-01',100,90,110,'kg','doc','row:1','https://example.invalid/original.xlsx','monthly');
    INSERT INTO ingestion_asset VALUES('reviewdoc','review',NULL),('dateddoc','review','2026-09-24');
    INSERT INTO regional_price SELECT doc,loc,d::date,p,p,'Armenia Mercar','Frutas','Bulto',q,'Kilogramo',r,100,120,'kg',1
      FROM (VALUES('doc','r1','2026-09-26','bar',24,1),('doc','r2','2026-09-26','bar',24,2),
        ('newdoc','r1','2026-09-26','bar',24,1),('doc','r3','2026-09-26','bar',30,1),
        ('doc','r4','2026-09-24','foo',24,1),('doc','r5','2013-01-01','old',24,1),('doc','r6','2999-01-01','old',24,1))v(doc,loc,d,p,q,r);
    INSERT INTO regional_classification VALUES('doc','r1',ARRAY['Frutas','Cítricos']);
    INSERT INTO supply_observation VALUES('market-1','2026-09-20'),('supply-only','2026-09-21'),('old-only','2013-01-01');
    INSERT INTO price_observation VALUES('missing-product','market-1','dane','2026-09-27',100,90,110,'kg','doc','missing:1','https://example.invalid/original.xlsx','monthly');
    INSERT INTO regional_price VALUES(NULL,'missing-original','2026-09-27','missing-original','Missing original','Armenia Mercar','Frutas','Bulto',24,'Kilogramo',1,100,120,'kg',1);`);
  assert.equal((await db.query("SELECT relpersistence FROM pg_class WHERE oid='price_observation'::regclass")).rows[0].relpersistence, 't');
  await db.query(fs.readFileSync(path.join(__dirname, '../../../pipelines/ingestion/migrations/20260927_013_market_prices.sql'), 'utf8'));
});
after(async () => { if (db) await db.end(); });
async function equivalent(id) {
  const actual = (await db.query(marketDetailQuery(window), [id])).rows;
  const previous = (await db.query(`WITH quotes AS (${PRICE_QUOTES})
    SELECT m.*,u.latitude,u.longitude,u.department_id,coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN (SELECT market_id,count(DISTINCT product_id) product_count,max(observed_on) date
      FROM quotes WHERE ${window} GROUP BY market_id) p ON p.market_id=m.id
    LEFT JOIN (SELECT market_id,max(observed_on) supply_date FROM supply_observation WHERE ${window} GROUP BY market_id) s ON s.market_id=m.id
    WHERE (p.market_id IS NOT NULL OR s.market_id IS NOT NULL) AND m.id=$1`, [id])).rows;
  assert.deepEqual(actual, previous);
  return actual;
}
check('full market navigation matches previous counts, dates, joins, ordering and supply-only coverage', async () => {
  const previous = (await db.query(`WITH quotes AS (${PRICE_QUOTES})
    SELECT m.*,u.latitude,u.longitude,u.department_id,coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN (SELECT market_id,count(DISTINCT product_id) product_count,max(observed_on) date
      FROM quotes WHERE ${window} GROUP BY market_id) p ON p.market_id=m.id
    LEFT JOIN (SELECT market_id,max(observed_on) supply_date FROM supply_observation WHERE ${window} GROUP BY market_id) s ON s.market_id=m.id
    WHERE p.market_id IS NOT NULL OR s.market_id IS NOT NULL ORDER BY product_count DESC,m.name`)).rows;
  const actual = (await db.query(marketsQuery(window))).rows;
  assert.deepEqual(actual, previous);
  assert.deepEqual(actual.map((row) => row.id), ['market-1', 'supply-only']);
});
check('city packages, rounds and retained revisions preserve distinct product counts and latest dates', async () => {
  const [row] = await equivalent('market-1');
  assert.equal(row.product_count, '3');
  assert.equal(row.date, '2026-09-26');
  assert.equal(row.supply_date, '2026-09-20');
  assert.equal(row.department_id, 'quindio');
});
check('supply-only markets remain available while old-only, empty and missing markets stay absent', async () => {
  const [row] = await equivalent('supply-only');
  assert.equal(row.product_count, '0'); assert.equal(row.date, null);
  assert.equal(row.supply_date, '2026-09-21'); assert.equal(row.latitude, null);
  for (const id of ['old-only', 'empty', 'missing', "x' OR true --"]) assert.deepEqual(await equivalent(id), []);
});

check('winner-key fetch preserves exact latest values, units and provenance after review filtering', async () => {
  const actual = (await db.query(marketProductsQuery(window), ['market-1'])).rows;
  const previous = (await db.query(`SELECT DISTINCT ON(p.id) p.*,o.price,o.observed_on AS date,o.unit,o.period,o.document_id,o.source_locator,
    NULL AS previous_price,1 AS market_count,CASE WHEN o.source_id='fnc' THEN 'FNC' ELSE 'DANE · SIPSA' END AS source
    FROM published_price_observation o JOIN product p ON p.id=o.product_id WHERE market_id=$1 AND ${window}
    ORDER BY p.id,o.observed_on DESC`, ['market-1'])).rows;
  assert.deepEqual(actual, previous);
  assert.equal(actual.length, 2);
  assert.equal(actual.find((r) => r.id === 'foo').document_id, 'newdoc');
  assert.equal(actual.find((r) => r.id === 'crossday').date, '2026-09-23');
  assert.deepEqual((await db.query(marketProductsQuery(window), ['supply-only'])).rows, []);
});

check('unspecified same-date source/unit ties resolve to one eligible whole quote, without mixing values', async () => {
  await db.query(`INSERT INTO price_observation VALUES('foo','market-1','other-source','2026-09-26',999,990,1000,'litre','doc','other:1','https://example.invalid/other.xlsx','monthly')`);
  const rows = (await db.query(marketProductsQuery(window), ['market-1'])).rows;
  const foo = rows.find((r) => r.id === 'foo');
  assert.equal(rows.filter((r) => r.id === 'foo').length, 1);
  assert.equal(foo.date, '2026-09-26');
  assert.ok(
    (foo.price === '100' && foo.unit === 'kg' && foo.document_id === 'newdoc' && foo.source_locator === 'row:1') ||
    (foo.price === '999' && foo.unit === 'litre' && foo.document_id === 'doc' && foo.source_locator === 'other:1'),
  );
});

check('two-stage directory counts exclude null products while retaining their latest date', async () => {
  await db.query(`INSERT INTO regional_price VALUES('doc','null-product','2026-09-27',NULL,'Unmapped','Armenia Mercar','Frutas','Bulto',24,'Kilogramo',1,100,120,'kg',1)`);
  const previous = (await db.query(`WITH quotes AS (${PRICE_QUOTES})
    SELECT count(DISTINCT product_id) AS product_count,max(observed_on) AS date FROM quotes
    WHERE market_id='market-1' AND ${window}`)).rows[0];
  const actual = (await db.query(marketsQuery(window))).rows.find((row) => row.id === 'market-1');
  assert.equal(actual.product_count, previous.product_count);
  assert.equal(actual.product_count, '3');
  assert.equal(actual.date, previous.date);
  assert.equal(actual.date, '2026-09-27');
});
