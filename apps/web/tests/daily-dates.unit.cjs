/* Production date-picker query against independent PostgreSQL observations. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client } = require('pg');
const moduleContext = { exports: {}, require: name => {
  if (name === 'server-only') return {};
  throw new Error(`Unexpected import ${name}`);
}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/daily-quotes.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, moduleContext);
const sql = moduleContext.exports.DAILY_DATES_SQL;
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');
const reference = `SELECT DISTINCT observed_on::text AS date FROM daily_price
  WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY date DESC`;
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, async () => {
  const db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  try {
    await db.query("SET search_path=pg_temp; SET statement_timeout='10s'");
    await db.query(`CREATE TEMP TABLE daily_price(observed_on date NOT NULL,
      product_name text NOT NULL, market_name text NOT NULL,
      PRIMARY KEY(observed_on,product_name,market_name))`);
    await fn(db);
  } finally { await db.end(); }
});
check('published day picker is complete and unique despite gaps, duplicate-day quotes, future dates and session time zones', async db => {
  await db.query(`INSERT INTO daily_price SELECT date,product,market FROM
    (VALUES ('2012-06-12'::date),('2015-12-15'::date),
      ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-1),
      ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date),
      ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date+1)) days(date),
    (VALUES ('Papa'),('Limón')) products(product), (VALUES ('Bogotá'),('Cali')) markets(market)`);
  for (const zone of ['UTC', 'America/Bogota', 'Pacific/Auckland']) {
    await db.query('SELECT set_config($1,$2,false)', ['TimeZone',zone]);
    const rows = (await db.query(sql)).rows;
    assert.deepEqual(rows, (await db.query(reference)).rows);
    assert.equal(rows.length, 4);
    assert.equal(rows.at(-1).date, '2012-06-12');
  }
});
check('empty and future-only publication returns no fictional bulletin date', async db => {
  assert.deepEqual((await db.query(sql)).rows, []);
  await db.query(`INSERT INTO daily_price VALUES
    (((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date+1),'Papa','Bogotá')`);
  assert.deepEqual((await db.query(sql)).rows, []);
});
check('large per-day quotation population preserves the full date set through bounded index seeks', async db => {
  await db.query(`INSERT INTO daily_price SELECT
    ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-d)::date,
    'Producto-' || p,'Mercado-' || m FROM generate_series(0,365) d,
    generate_series(1,50) p,generate_series(1,4) m`);
  await db.query('ANALYZE daily_price');
  const rows = (await db.query(sql)).rows;
  assert.deepEqual(rows, (await db.query(reference)).rows);
  assert.equal(rows.length, 366);
  const plan = (await db.query('EXPLAIN (FORMAT JSON) '+sql)).rows[0]['QUERY PLAN'];
  const nodes=[]; const visit = node => {nodes.push(node);for(const child of node.Plans || []) visit(child);};
  visit(plan[0].Plan);
  assert(nodes.some(node => node['Index Name'] === 'daily_price_pkey'));
  assert(!nodes.some(node => node['Relation Name'] === 'daily_price' && node['Node Type'] === 'Seq Scan'));
});
