const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client, types } = require('pg');

types.setTypeParser(1700, Number);
types.setTypeParser(1082, value => value);
const socket = process.env.AGRO_REFERENCE_TEST_SOCKET;
const enabled = Boolean(socket?.startsWith('/tmp/agro-unified-catalog-pg-'));
const check = (name, fn) => test(name, { skip: !enabled && 'Requires private unified PostgreSQL socket' }, fn);
const root = path.resolve(__dirname, '../../..');
const planning = ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/planning.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText;
const cityPartialReview = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/server/city-partial-review.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, cityPartialReview);
const filterLabels = ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../src/lib/filter-labels.ts'), 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText;
const schema = fs.readFileSync(path.join(root, 'pipelines/ingestion/schema.sql'), 'utf8');
const WINDOW = "observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

function app(db) {
  const context = { exports: {}, Date, Map, Set, Error, Promise, process,
    require: name => {
      if (name === 'server-only') return {};
      if (name === 'node:crypto' || name === 'node:timers') return require(name);
      if (name === './db') return { database: () => db, WINDOW };
      if (name === './city-partial-review') return cityPartialReview.exports;
      if (name === './input-identities') return { reconcileInputCatalog: async rows => rows };
      if (name === '../planning-math') return { fold: s => s };
      if (name === '../label-normalization') return require('./helpers/load-label-normalization.cjs')();
      if (name === '../filter-labels') {
        const labels = { exports: {} };
        vm.runInNewContext(filterLabels, labels);
        return labels.exports;
      }
      if (['./official-evidence-sql', './daily-date-note', './source-document-sql',
        './evidence-review-sql', './supply-summary-evidence', '../weather-data'].includes(name)) return {};
      throw new Error(`Unexpected import ${name}`);
    },
  };
  vm.runInNewContext(planning, context);
  return context.exports;
}

async function fixture() {
  const client = new Client({ host: socket, port: 65443, database: 'postgres', statement_timeout: 12000 });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL search_path=pg_temp');
    await client.query(`CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,retrieved_at timestamptz);
      CREATE TEMP TABLE input_price(
        id text,department text,observed_on date,name text,category text,presentation text,
        price numeric,document_id text,source_locator text,brand text,registration text,product_line text,
        PRIMARY KEY(id,department,observed_on));
      CREATE TEMP TABLE input_municipal_price(LIKE input_price INCLUDING DEFAULTS);
      ALTER TABLE input_municipal_price ADD COLUMN municipality text;
      CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text);
      CREATE TEMP TABLE input_identity_alias(legacy_id text,id text,PRIMARY KEY(legacy_id,id));
      CREATE TEMP TABLE input_latest_projection_state(scope text PRIMARY KEY,source_epoch bigint,
        projection_epoch bigint,asof_bogota date,delta_complete boolean);
      INSERT INTO input_latest_projection_state VALUES
        ('department',0,-1,CURRENT_DATE,false),('municipality',0,-1,CURRENT_DATE,false);
      CREATE TEMP TABLE input_latest_projection_delta(scope text,id text,changed_epoch bigint,
        PRIMARY KEY(scope,id));
      CREATE TEMP TABLE input_department_latest_raw(id text,department text,observed_on date,price numeric,
        name text,category text,presentation text,document_id text,source_locator text,
        brand text,registration text,product_line text);
      CREATE TEMP TABLE input_municipal_latest_raw(LIKE input_department_latest_raw);
      ALTER TABLE input_municipal_latest_raw ADD COLUMN municipality text;`);
    const ledger = schema.match(/CREATE TABLE IF NOT EXISTS input_projection_supersession \([\s\S]*?\n\);/);
    assert.ok(ledger, 'real supersession ledger schema available');
    await client.query(ledger[0].replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'));
    for (const name of ['published_input_price', 'published_input_municipal_price']) {
      const definition = schema.match(new RegExp(`CREATE OR REPLACE VIEW ${name} AS[\\s\\S]*?\\n\\);`));
      assert.ok(definition, `real ${name} definition available`);
      await client.query(definition[0].replace('CREATE OR REPLACE VIEW', 'CREATE TEMP VIEW'));
    }
    // The temporary relation has the same transition-table epoch behavior as
    // the deployed v047 trigger, without touching any public schema object.
    const migration = fs.readFileSync(path.join(root,
      'pipelines/ingestion/migrations/20261001_047_input_projection_delta.sql'), 'utf8');
    const functionSql = migration.match(/CREATE OR REPLACE FUNCTION input_latest_projection_changed\(\) RETURNS trigger[\s\S]*?END \$\$;/);
    assert.ok(functionSql, 'deployed epoch trigger function available');
    await client.query(functionSql[0].replace('CREATE OR REPLACE FUNCTION input_latest_projection_changed',
      'CREATE OR REPLACE FUNCTION pg_temp.input_latest_projection_changed')
      .replace('public.input_latest_projection_state', 'pg_temp.input_latest_projection_state')
      .replaceAll('public.input_latest_projection_delta', 'pg_temp.input_latest_projection_delta'));
    await client.query(`CREATE TRIGGER fixture_input_update AFTER UPDATE ON input_price
      REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
      EXECUTE FUNCTION pg_temp.input_latest_projection_changed('department')`);
    const calls = [];
    const db = { query: async (sql, args) => {
      if (sql.includes('SELECT s.source_epoch::text AS source_epoch')) calls.push('revision');
      if (sql.includes('FROM unnest($1::text[]) AS keys(id)')) calls.push(`publication:${args.length > 1 ? 'regional' : 'national'}:${args[0].join(',')}`);
      return client.query(sql, args);
    } };
    return { client, calls, inputs: app(db).inputs };
  } catch (error) {
    await client.query('ROLLBACK').catch(() => {});
    await client.end();
    throw error;
  }
}

async function close(f) {
  if (!f) return;
  await f.client.query('ROLLBACK');
  await f.client.end();
}
async function document(f, id, retrieved = '2026-09-30T12:00:00Z') {
  await f.client.query('INSERT INTO source_document VALUES($1,$2,$3)',
    [id, `https://example.invalid/${id}.xlsx`, retrieved]);
}
async function price(f, id, documentId, locator, amount, date = '2026-09-30') {
  await f.client.query(`INSERT INTO input_price VALUES($1,'Antioquia',$2,'Same product','Fertilizantes',
    '1 litro',$3,$4,$5,'Marca','ICA123','Línea')`, [id, date, amount, documentId, locator]);
}
function own(rows, id) { return rows.find(row => row.id === id); }
function regionalPublication(calls, id) {
  return calls.some(call => call === `publication:regional:${id}`);
}

check('physical price update advances the real epoch trigger and a stale negative cannot hide the new regional winner', async () => {
  let f;
  try {
    f = await fixture();
    await document(f, 'old');
    await document(f, 'new');
    await price(f, 'legacy', 'old', 'p1; inputs-pdf-v1', 50);
    await f.client.query("INSERT INTO input_identity_alias VALUES('legacy','not-a-replacement')");
    await f.client.query("INSERT INTO ingestion_checkpoint VALUES('old','inputs-pdf-v2','inputs-pdf:published')");
    assert.equal(own(await f.inputs('', 'department', true, '', true), 'legacy'), undefined);
    const before = Number((await f.client.query("SELECT source_epoch FROM input_latest_projection_state WHERE scope='department'")).rows[0].source_epoch);
    await f.client.query(`UPDATE input_price SET document_id='new',source_locator='p1; inputs-pdf-v2',price=87 WHERE id='legacy'`);
    const after = Number((await f.client.query("SELECT source_epoch FROM input_latest_projection_state WHERE scope='department'")).rows[0].source_epoch);
    assert.ok(after > before, 'physical row update must advance the transactional source epoch');
    const regional = own(await f.inputs('Antioquia', 'department', true, '', true), 'legacy');
    assert.equal(regional?.price, 87);
    assert.equal(regional?.document_id, 'new');
    assert.equal(regional?.source_locator, 'p1; inputs-pdf-v2');
    assert.ok(regionalPublication(f.calls, 'legacy'), 'changed epoch forces authoritative regional lookup');
  } finally { await close(f); }
});

check('alias insertion changes real published eligibility and invalidates a completed national winner', async () => {
  let f;
  try {
    f = await fixture();
    await document(f, 'old', '2026-09-29T12:00:00Z');
    await document(f, 'replacement', '2026-09-30T12:00:00Z');
    await price(f, 'legacy', 'old', 'r1', 50);
    await price(f, 'replacement', 'replacement', 'r1', 70);
    await f.client.query("INSERT INTO input_identity_alias VALUES('legacy','unmatched')");
    assert.equal(own(await f.inputs('', 'department', true, '', true), 'legacy')?.price, 50);
    await f.client.query("INSERT INTO input_identity_alias VALUES('legacy','replacement')");
    assert.equal(own((await f.client.query("SELECT * FROM published_input_price WHERE id='legacy'")).rows, 'legacy'), undefined);
    assert.equal(own(await f.inputs('Antioquia', 'department', true, '', true), 'legacy'), undefined);
    assert.ok(regionalPublication(f.calls, 'legacy'), 'new alias prevents reuse of stale national winner');
  } finally { await close(f); }
});

check('PDF publication checkpoint insertion withdraws a real row and invalidates a completed national winner', async () => {
  let f;
  try {
    f = await fixture();
    await document(f, 'pdf');
    await price(f, 'legacy', 'pdf', 'p1; inputs-pdf-v1', 50);
    await f.client.query("INSERT INTO input_identity_alias VALUES('legacy','unmatched')");
    assert.equal(own(await f.inputs('', 'department', true, '', true), 'legacy')?.price, 50);
    await f.client.query("INSERT INTO ingestion_checkpoint VALUES('pdf','inputs-pdf-v2','inputs-pdf:published')");
    assert.equal(own((await f.client.query("SELECT * FROM published_input_price WHERE id='legacy'")).rows, 'legacy'), undefined);
    assert.equal(own(await f.inputs('Antioquia', 'department', true, '', true), 'legacy'), undefined);
    assert.ok(regionalPublication(f.calls, 'legacy'), 'new checkpoint prevents reuse of stale national winner');
  } finally { await close(f); }
});
