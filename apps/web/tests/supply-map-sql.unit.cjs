const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const { Client, types } = require('pg');
const code = ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/supply-sql.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exportsUnderTest = {};
new Function('exports', code)(exportsUnderTest);
const { supplyMapQuery } = exportsUnderTest;
const socket = process.env.AGRO_SUPPLY_SQL_TEST_SOCKET;
const enabled = Boolean(socket?.startsWith('/tmp/agro-supply-api-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL runner' }, fn);
const all = 'observed_on<=CURRENT_DATE';
const recent = "observed_on > CURRENT_DATE - INTERVAL '12 months' AND observed_on<=CURRENT_DATE";
const departments = ['Atlántico', 'ATLÁNTICO'];
let db;
types.setTypeParser(1082, value => value);
types.setTypeParser(1700, Number);

test('supply-map product and department values are bound in both month selection and totals', () => {
  const attack = "x' OR true --";
  const query = supplyMapQuery(attack, [attack], all);
  assert.deepEqual(query.values, [attack, [attack]]);
  assert.ok(!query.text.includes(attack));
  assert.equal((query.text.match(/s.product_id=\$1/g) || []).length, 2);
  assert.equal((query.text.match(/m.region=ANY\(\$2::text\[\]\)/g) || []).length, 2);
  assert.deepEqual(supplyMapQuery('', [], all).values, []);
});

before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65443, database: 'postgres' });
  await db.connect();
  await db.query("SET search_path=pg_temp; SET statement_timeout='12s'");
  await db.query(`CREATE TEMP TABLE municipality(id text PRIMARY KEY,department_id text,latitude numeric,longitude numeric);
    CREATE TEMP TABLE market(id text PRIMARY KEY,name text,region text,municipality_id text);
    CREATE TEMP TABLE source_document(id text PRIMARY KEY,title text);
    CREATE TEMP TABLE supply_observation(market_id text,food_id text,product_id text,
      period_start date,observed_on date,quantity_kg numeric,document_id text);
    INSERT INTO municipality VALUES ('08','08',10,-74),('05','05',6,-75);
    INSERT INTO market VALUES ('atl','Barranquillita','Atlántico','08'),
      ('atl-case','Granabastos','ATLÁNTICO','08'),('other','Medellín','Antioquia','05');
    INSERT INTO source_document VALUES ('a','Anexo A.xlsx'),('b','Anexo B.xlsx'),('old','2014.xlsx');
    INSERT INTO supply_observation VALUES
      ('atl','f1','papa',date_trunc('month',CURRENT_DATE - INTERVAL '2 months'),CURRENT_DATE - INTERVAL '40 days',10.25,'a'),
      ('atl','f2','papa',date_trunc('month',CURRENT_DATE - INTERVAL '2 months'),CURRENT_DATE - INTERVAL '39 days',20.75,'b'),
      ('atl','f3','papa',date_trunc('month',CURRENT_DATE - INTERVAL '2 months'),CURRENT_DATE - INTERVAL '39 days',0,'a'),
      ('atl-case','f1','papa',date_trunc('month',CURRENT_DATE - INTERVAL '2 months'),CURRENT_DATE - INTERVAL '39 days',7,'a'),
      ('other','f1','papa',date_trunc('month',CURRENT_DATE - INTERVAL '1 month'),CURRENT_DATE - INTERVAL '10 days',9999,'a'),
      ('atl','unrelated','tomate',date_trunc('month',CURRENT_DATE - INTERVAL '1 month'),CURRENT_DATE - INTERVAL '10 days',555,'a'),
      ('atl','old','historical-only','2014-03-01','2014-03-31',13883.25,'old'),
      ('atl','future','papa','2999-01-01','2999-01-02',999999,'a');`);
  for (const relation of ['municipality', 'market', 'source_document', 'supply_observation']) {
    assert.equal((await db.query('SELECT relpersistence FROM pg_class WHERE oid=to_regclass($1)', [relation])).rows[0].relpersistence, 't');
  }
});
after(async () => { if (db) await db.end(); });

check('regional map chooses its own latest product month and excludes other regions and products', async () => {
  const rows = (await db.query(supplyMapQuery('papa', departments, recent))).rows;
  assert.deepEqual(rows.map(row => row.id), ['atl', 'atl-case']);
  assert.deepEqual(rows.map(row => row.value), [31, 7]);
  assert.ok(rows.every(row => departments.includes(row.region) && row.unit === 'kg'));
  const expected = (await db.query("SELECT date_trunc('month',CURRENT_DATE - INTERVAL '2 months')::date::text AS period")).rows[0].period;
  assert.ok(rows.every(row => row.period_start === expected));
  assert.deepEqual(rows[0].sources.sort((a,b) => a.document_id.localeCompare(b.document_id)),
    [{ document_id: 'a', title: 'Anexo A.xlsx' }, { document_id: 'b', title: 'Anexo B.xlsx' }]);
});

check('all-history exposes an older regional product while recent scope stays empty', async () => {
  const rows = (await db.query(supplyMapQuery('historical-only', departments, all))).rows;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].period_start, '2014-03-01');
  assert.equal(rows[0].date, '2014-03-31');
  assert.equal(rows[0].value, 13883.25);
  assert.deepEqual(rows[0].sources, [{ document_id: 'old', title: '2014.xlsx' }]);
  assert.deepEqual((await db.query(supplyMapQuery('historical-only', departments, recent))).rows, []);
});

check('national latest month and absent regional matches never fall back to unrelated rows', async () => {
  const national = (await db.query(supplyMapQuery('papa', [], all))).rows;
  assert.deepEqual(national.map(row => row.id), ['other']);
  assert.equal(national[0].value, 9999);
  for (const [product, scope] of [['missing', departments], ['papa', ['missing']], ["x' OR true --", []]]) {
    assert.deepEqual((await db.query(supplyMapQuery(product, scope, all))).rows, []);
  }
});
