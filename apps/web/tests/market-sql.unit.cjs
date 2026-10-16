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
  new Function('exports', 'require', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(out,
    name => name === './category-path-sql' ? load('category-path-sql.ts')
      : name === './city-market-alias' ? load('city-market-alias.ts')
      : name === './city-package-equivalence' ? load('city-package-equivalence.ts')
      : name === './product-detail-diagnostics' ? load('product-detail-diagnostics.ts') : { WINDOW: window });
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
  assert.ok(query.includes("r.market_name=ANY(CASE WHEN"));
  assert.ok(query.includes("m.municipality_id='11001'"));
  assert.ok(query.includes('LEFT JOIN regional_classification rival_class'));
  assert.ok(query.includes('regional_price_product_correction'));
  assert.ok(query.includes('city_alias_witnesses AS MATERIALIZED'));
  assert.ok(query.includes('excluded_city_alias_rows AS MATERIALIZED'));
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
      min_price numeric,max_price numeric,unit text,source_page integer,
      min_unit_price numeric,max_unit_price numeric);
    CREATE TEMP TABLE regional_price_product_correction(
      document_id text,source_locator text,corrected_product_id text,corrected_product_name text,
      PRIMARY KEY(document_id,source_locator));
    CREATE TEMP TABLE city_pdf_publication_conflict(document_id text PRIMARY KEY);
    CREATE TEMP TABLE verified_city_pdf_price_overlay(document_id text,source_locator text,
      corrected_min_price numeric,corrected_max_price numeric);
    CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS (
      SELECT 1 FROM city_pdf_publication_conflict blocked WHERE blocked.document_id=r.document_id OFFSET 0);
    CREATE TEMP VIEW resolved_regional_price AS
      SELECT r.* FROM published_regional_price r WHERE NOT EXISTS(
        SELECT 1 FROM regional_price_product_correction c
        WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
      UNION ALL
      SELECT r.document_id,r.source_locator,r.observed_on,
        c.corrected_product_id,c.corrected_product_name,r.market_name,r.category,
        r.presentation,r.quantity,r.source_unit,r.round,r.min_price,r.max_price,r.unit,r.source_page,
        r.min_unit_price,r.max_unit_price
      FROM regional_price_product_correction c JOIN published_regional_price r
        ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
    CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[]);
    CREATE TEMP VIEW verified_regional_category_overlay AS
      SELECT r.document_id,r.source_locator,NULL::text AS corrected_category
      FROM regional_price r WHERE FALSE;
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
    ALTER TABLE source_document ADD COLUMN kind text NOT NULL DEFAULT 'original', ADD COLUMN media_type text NOT NULL DEFAULT 'application/pdf';
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
check('market identity totals use corrected product IDs and retain original rows', async () => {
  await db.query('BEGIN');
  try {
  const before=(await db.query(marketDetailQuery(window),['market-1'])).rows[0].product_count;
  await db.query(`INSERT INTO regional_price_product_correction
    SELECT document_id,source_locator,'foo','Corrected foo'
    FROM regional_price WHERE product_id='bar'`);
  const after=(await equivalent('market-1'))[0].product_count;
  assert.ok(after<before);
  assert.equal((await db.query("SELECT count(*)::int AS n FROM regional_price WHERE product_id='bar'")).rows[0].n,4);
  } finally { await db.query('ROLLBACK'); }
});
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
check('city directory and legacy market bookmarks group documented Corabastos labels only',async()=>{
  await db.query('BEGIN');
  try {
    const names=['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos'];
    const ids=['dane-city-bogota-corabastos','dane-city-bogota-d-c-corabastos','sipsa-bogota-d-c-corabastos'];
    for(let i=0;i<3;i++) await db.query('INSERT INTO market VALUES($1,$2,$3,$4,$5)',
      [ids[i],names[i],'Bogotá','Bogotá, D.C.','11001']);
    for(let i=0;i<3;i++) await db.query(`INSERT INTO regional_price VALUES
      ('doc',$1,$2::date,'foo','Food',$3,'Frutas','Bulto',22,'Kilogramo',2,100,120,'kg',1)`,
      ['alias-'+i,'2026-09-'+(24+i),names[i]]);
    const list=(await db.query(marketsQuery(window))).rows;
    assert.deepEqual(list.filter(x=>ids.includes(x.id)).map(x=>x.id),[ids[2]]);
    assert.equal(list.find(x=>x.id===ids[2]).product_count,'1');
    for(const id of ids) {
      const detail=(await db.query(marketDetailQuery(window),[id])).rows;
      assert.equal(detail.length,1);
      assert.equal(detail[0].product_count,'1');
      assert.equal(detail[0].date,'2026-09-26');
    }
    const original=(await db.query('SELECT DISTINCT market_name FROM regional_price WHERE source_locator LIKE $1 ORDER BY market_name',['alias-%'])).rows;
    assert.deepEqual(original.map(x=>x.market_name),[...names].sort());
    assert.equal(list.find(x=>x.id==='market-1').product_count,'3','unrelated market remains separate');
  } finally {await db.query('ROLLBACK')}
});
check('2022 native grave-accent market appears under the canonical city bookmark without a market row',async()=>{
  await db.query('BEGIN');
  try {
    const canonical='sipsa-bogota-d-c-corabastos';
    await db.query(`INSERT INTO market VALUES($1,'Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001')`,[canonical]);
    await db.query(`INSERT INTO regional_price VALUES
      ('doc','2022-native-r2','2022-01-03','foo','Food','Bogotà, Corabastos','Frutas','Canastilla',20,
       'Kilogramo',2,26000,28000,'package',1)`);
    const all="observed_on<=CURRENT_DATE";
    const list=(await db.query(marketsQuery(all))).rows;
    assert.equal(list.find(row=>row.id===canonical).product_count,'1');
    const detail=(await db.query(marketDetailQuery(all),[canonical])).rows;
    assert.equal(detail.length,1);
    assert.equal(detail[0].product_count,'1');
    assert.equal(detail[0].date,'2022-01-03');
    assert.equal((await db.query("SELECT count(*)::int n FROM market WHERE name='Bogotà, Corabastos'")).rows[0].n,0);
  } finally { await db.query('ROLLBACK'); }
});

check('batched alias checks preserve latest-source conflicts, corrected identities and every package dimension', async () => {
  await db.query('BEGIN');
  try {
    const canonical='sipsa-bogota-d-c-corabastos';
    const names=['Bogotá, Corabastos','Bogotá, D.C., Corabastos'];
    await db.query(`INSERT INTO market VALUES
      ('dane-city-bogota-corabastos',$1,'Bogotá','Bogotá, D.C.','11001'),
      ($2,$3,'Bogotá','Bogotá, D.C.','11001')`,[names[0],canonical,names[1]]);
    async function pair({price=100,category='Cítricos',product='foo',quantity=20,round=1,
      presentation='Bulto',sourceUnit='Kilogramo',unit='package',document='doc',date='2026-09-26',converted=5}={}) {
      await db.query("DELETE FROM regional_price WHERE source_locator LIKE 'batched-%'");
      await db.query("DELETE FROM regional_classification WHERE source_locator LIKE 'batched-%'");
      await db.query("DELETE FROM regional_price_product_correction WHERE source_locator LIKE 'batched-%'");
      await db.query(`INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,
        market_name,category,presentation,quantity,source_unit,round,min_price,max_price,unit,source_page,min_unit_price,max_unit_price)
        VALUES('doc','batched-a','2026-09-26','foo','Food',$1,'Frutas','Bulto',20,'Kilogramo',1,100,120,'package',1,5,6),
        ($2,'batched-b',$3::date,$4,'Food',$5,'Frutas',$6,$7,$8,$9,$10,120,$11,1,$12,6)`,
        [names[0],document,date,product,names[1],presentation,quantity,sourceUnit,round,price,unit,converted]);
      await db.query(`INSERT INTO regional_classification VALUES
        ('doc','batched-a',ARRAY['Frutas','Cítricos']),($1,'batched-b',ARRAY['Frutas',$2])`,[document,category]);
    }
    async function checkCount(expected) {
      const actual=(await equivalent(canonical))[0];
      assert.equal(actual?.product_count || '0',String(expected));
      const directory=(await db.query(marketsQuery(window))).rows.find(row=>row.id===canonical);
      assert.deepEqual(directory,actual);
    }
    await pair(); await checkCount(1); // Identical literals can share a canonical facility.
    await pair({price:101}); await checkCount(0);
    await pair({category:'Otras frutas'}); await checkCount(0);
    await pair({converted:5.1}); await checkCount(0);
    for(const dimensions of [{quantity:30},{round:2},{presentation:'Canastilla'},
      {sourceUnit:'Gramo'},{unit:'kg'},{date:'2026-09-25'}]) {
      await pair({...dimensions,price:101}); await checkCount(1);
    }
    await pair({presentation:' bUlTo ',sourceUnit:' kIlOgRaMo ',price:101}); await checkCount(0);
    await pair({product:'bar',price:101}); await checkCount(2);
    await db.query(`INSERT INTO regional_price_product_correction VALUES('doc','batched-b','foo','Food')`);
    await checkCount(0);
    await pair({price:101});
    await db.query(`INSERT INTO regional_price SELECT 'newdoc','batched-new',observed_on,product_id,product_name,
      market_name,category,presentation,quantity,source_unit,round,100,max_price,unit,source_page,min_unit_price,max_unit_price
      FROM regional_price WHERE source_locator='batched-b'`);
    await db.query(`INSERT INTO regional_classification VALUES('newdoc','batched-new',ARRAY['Frutas','Cítricos'])`);
    await checkCount(1); // An old disagreement cannot override a newer identical witness.
    await db.query(`INSERT INTO city_pdf_publication_conflict VALUES('newdoc')`);
    await checkCount(0); // A blocked newer witness cannot hide the retained conflict.
  } finally { await db.query('ROLLBACK'); }
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
