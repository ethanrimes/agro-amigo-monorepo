/* SQL parity and covering-plan proof; PostgreSQL tests require a private local socket. */
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { Client, types } = require('pg');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/supply-sql.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const actualModule = {};
new Function('exports', compiled)(actualModule);
const { supplyQueries } = actualModule;
const all = 'observed_on<=CURRENT_DATE';
const recent = "observed_on>DATE '2025-09-27' AND observed_on<=CURRENT_DATE";
const socket = process.env.AGRO_SUPPLY_SQL_TEST_SOCKET;
const enabled = Boolean(socket?.startsWith('/tmp/agro-supply-api-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
types.setTypeParser(1082, (value) => value);
let db;

test('filter values stay bound and month parameter follows only active scope predicates', () => {
  for (const [product, market, expected] of [
    ['', '', []], ['milk', '', ['milk']], ['', 'armenia', ['armenia']], ['milk', 'armenia', ['milk', 'armenia']],
  ]) {
    const queries = supplyQueries(product, market, all);
    assert.deepEqual(queries.history.values, expected);
    assert.deepEqual(queries.month('2020-01-01').values, [...expected, '2020-01-01']);
    assert.ok(queries.month('2020-01-01').text.includes(`period_start=$${expected.length + 1}`));
    assert.ok(!queries.history.text.includes("='' OR"));
  }
  const malicious = "x' OR true --";
  const query = supplyQueries(malicious, malicious, all);
  assert.ok(!query.history.text.includes(malicious));
  assert.deepEqual(query.history.values, [malicious, malicious]);
});

before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  await db.query(`CREATE TEMP TABLE market(id text PRIMARY KEY,name text,region text);
    CREATE TEMP TABLE supply_observation(
      market_id text NOT NULL,food_id text NOT NULL,food_name text NOT NULL,product_id text,
      category text NOT NULL,period_start date NOT NULL,observed_on date NOT NULL,
      first_reported_on date NOT NULL,quantity_kg numeric NOT NULL CHECK(quantity_kg>=0),
      reporting_days integer NOT NULL CHECK(reporting_days>0),document_id text NOT NULL,
      source_rows jsonb NOT NULL,PRIMARY KEY(market_id,food_id,period_start),
      CHECK(first_reported_on<=observed_on));
    CREATE INDEX supply_market_date ON supply_observation(market_id,observed_on DESC);
    CREATE INDEX supply_product_date ON supply_observation(product_id,observed_on DESC)`);
  for (const relation of ['market', 'supply_observation']) {
    assert.equal((await db.query('SELECT relpersistence FROM pg_class WHERE oid=to_regclass($1)', [relation])).rows[0].relpersistence, 't');
  }
  await db.query(`INSERT INTO market SELECT 'market-'||n,'Market '||n,'Region '||n FROM generate_series(1,30)n;
    INSERT INTO supply_observation
    SELECT 'market-'||m,'food-'||f,'Food '||f,CASE WHEN f%7=0 THEN NULL ELSE 'product-'||f END,
      'Category',period,period+10,period+1,(m*f+month)::numeric/10,2,
      'original-'||month,jsonb_build_array(jsonb_build_object('row',m*f,'literal',repeat(md5(f::text),80)))
    FROM generate_series(1,30)m CROSS JOIN generate_series(1,24)f CROSS JOIN generate_series(0,164)month
    CROSS JOIN LATERAL (SELECT (DATE '2013-01-01'+month*INTERVAL '1 month')::date period) d;
    INSERT INTO supply_observation VALUES
      ('market-1','zero','Zero quantity','product-1','Category','2020-01-01','2020-01-03','2020-01-02',0,2,'zero-original','[{"row":17}]'),
      ('market-1','future','Future','product-1','Category','2999-01-01','2999-01-03','2999-01-01',999999,3,'future-original','[]')`);
  await db.query(fs.readFileSync(path.join(__dirname, '../../../pipelines/ingestion/migrations/20260927_009_supply_reads.sql'), 'utf8'));
  await db.query('VACUUM ANALYZE supply_observation');
});
after(async () => { if (db) await db.end(); });

async function equivalent(product, market, window, periods = ['2013-01-01', '2020-01-01', '2026-09-01']) {
  const queries = supplyQueries(product, market, window);
  const history = (await db.query(queries.history)).rows;
  const expected = (await db.query(`SELECT period_start AS date,sum(quantity_kg) quantity_kg
    FROM supply_observation WHERE ${window} AND ($1='' OR product_id=$1) AND ($2='' OR market_id=$2)
    GROUP BY period_start ORDER BY period_start`, [product, market])).rows;
  assert.deepEqual(history, expected);
  assert.ok(history.every((row) => row.date < '2999-01-01'));
  for (const period of periods) {
    const rows = (await db.query(queries.month(period))).rows;
    const previousRows = (await db.query(`SELECT s.market_id,m.name market_name,m.region,s.food_id,s.food_name,s.product_id,
      s.period_start,s.observed_on,s.first_reported_on,s.quantity_kg,s.document_id,s.reporting_days
      FROM supply_observation s JOIN market m ON m.id=s.market_id
      WHERE ${window} AND ($1='' OR product_id=$1) AND ($2='' OR market_id=$2) AND period_start=$3
      ORDER BY quantity_kg DESC,s.market_id,s.food_id`, [product, market, period])).rows;
    assert.deepEqual(rows, previousRows, `Detailed metadata mismatch for ${product}/${market}/${period}`);
    const summary = history.find((row) => row.date === period);
    assert.ok(Math.abs(rows.reduce((sum, row) => sum + Number(row.quantity_kg), 0) - Number(summary?.quantity_kg || 0)) < 1e-7);
  }
  return history;
}

check('all scopes retain every historical month, exact totals and original source metadata', async () => {
  for (const [product, market] of [['', 'market-1'], ['product-1', ''], ['product-1', 'market-1'], ['', '']]) {
    const history = await equivalent(product, market, all);
    assert.equal(history.length, 165);
    assert.equal(history[0].date, '2013-01-01');
    assert.equal(history.at(-1).date, '2026-09-01');
  }
  const rows = (await db.query(supplyQueries('product-1', 'market-1', all).month('2020-01-01'))).rows;
  const zero = rows.find((row) => row.food_id === 'zero');
  assert.equal(zero.quantity_kg, '0');
  assert.equal(zero.document_id, 'zero-original');
  assert.equal(zero.reporting_days, 2);
  assert.equal(zero.first_reported_on, '2020-01-02');
});

check('recent scope and absent filters preserve existing API semantics without future data', async () => {
  for (const [product, market] of [['', 'market-1'], ['product-1', ''], ['product-1', 'market-1'], ['', '']]) {
    assert.equal((await equivalent(product, market, recent)).length, 12);
  }
  assert.deepEqual(await equivalent('missing-product', 'market-1', all), []);
  assert.deepEqual(await equivalent("x' OR true --", '', all), []);
  const rows = (await db.query(supplyQueries('', 'market-1', all).month('2013-01-01'))).rows;
  assert.equal(rows.filter((row) => row.product_id === null).length, 3);
});

check('history uses covering indexes while only the selected month fetches detailed rows', async () => {
  const plans = [];
  for (const [product, market, index] of [
    ['', 'market-1', 'supply_market_history_cover'],
    ['product-1', '', 'supply_product_history_cover'],
    ['product-1', 'market-1', 'supply_product_history_cover'],
  ]) {
    const query = supplyQueries(product, market, all).history;
    const plan = (await db.query('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) ' + query.text, query.values)).rows[0]['QUERY PLAN'][0];
    const nodes = [];
    function visit(node) { nodes.push(node); (node.Plans || []).forEach(visit); }
    visit(plan.Plan);
    const scan = nodes.find((node) => node['Node Type'] === 'Index Only Scan');
    assert.ok(scan, JSON.stringify(plan));
    assert.equal(scan['Index Name'], index);
    assert.equal(scan['Heap Fetches'], 0);
    assert.equal(plan.Plan['Actual Rows'], 165);
    plans.push({ product, market, plan });
  }
  if (process.env.AGRO_SUPPLY_SQL_PROOF) fs.writeFileSync(process.env.AGRO_SUPPLY_SQL_PROOF, JSON.stringify({ fixture_rows: 118802, plans }, null, 2));
});
