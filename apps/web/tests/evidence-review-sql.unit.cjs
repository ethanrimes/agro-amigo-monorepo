const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const ts = require('typescript');
const { Client } = require('pg');
const out = {};
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/server/evidence-review-sql.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText)(out);
const SQL = out.EVIDENCE_REVIEW_COUNT_SQL;
const socket = process.env.AGRO_REVIEW_SQL_TEST_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-input-review-');
let db;
const check = (name, fn) => test(name, { skip: !enabled && 'Requires isolated PostgreSQL' }, fn);
before(async () => {
  if (!enabled) return;
  db = new Client({ host: socket, port: 65454, database: 'postgres' }); await db.connect();
  await db.query(`SET search_path=pg_temp; SET statement_timeout='10s';
    CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text);
    CREATE TEMP TABLE historical_price(document_id text,source_locator text,series text,details jsonb,PRIMARY KEY(document_id,source_locator));
    CREATE TEMP TABLE official_source_review(document_id text,source_locator text,created_at timestamptz);
    CREATE TEMP TABLE official_price_quote(document_id text,source_locator text,parsed_at timestamptz);
    CREATE TEMP TABLE ingestion_asset(document_id text,status text,processor_version text);
    INSERT INTO ingestion_checkpoint VALUES ('input','inputs-pdf-v9','inputs-pdf:published');
    INSERT INTO historical_price SELECT 'input','v9-'||n,'dane-inputs-pdf-unresolved','{"parser_version":"inputs-pdf-v9"}' FROM generate_series(1,4)n;
    INSERT INTO historical_price SELECT 'input','v10-'||n,'dane-inputs-pdf-unresolved','{"parser_version":"inputs-pdf-v10"}' FROM generate_series(1,15)n;
    INSERT INTO historical_price SELECT 'input','v10-valid-'||n,'dane-inputs-pdf','{"parser_version":"inputs-pdf-v10"}' FROM generate_series(1,10)n;
    INSERT INTO ingestion_asset VALUES('input','failed','inputs-pdf-v11'),('input','complete','inputs-pdf-v9');
    INSERT INTO official_source_review VALUES('official','open','2026-09-01'),('official','open','2026-09-01'),('official','repaired','2026-09-01'),('official','raw-present','2026-09-01'),('input','other-review','2026-09-01');
    INSERT INTO official_price_quote VALUES('official','repaired','2026-09-02');
    INSERT INTO historical_price VALUES('official','raw-present','dane-daily','{}');`);
});
after(async () => { if (db) await db.end(); });
async function count(id) { return (await db.query(SQL, [id])).rows[0].count; }
check('attempted versions and alias states cannot change the completed count', async () => {
  assert.equal(await count('input'), 5); // Four committed PDF reviews + one official review.
  await db.query("INSERT INTO ingestion_checkpoint VALUES('input','inputs-pdf-v10','inputs-pdf:published')");
  assert.equal(await count('input'), 16); // Numeric version10 wins9; valid rows excluded.
  await db.query("UPDATE ingestion_asset SET processor_version='inputs-pdf-v99',status='review'");
  assert.equal(await count('input'), 16);
});
check('unchanged official review suppression and zero counts remain exact', async () => {
  assert.equal(await count('official'), 1);
  assert.equal(await count('missing'), 0);
});
check('later complete correction clears old input reviews without deleting raw', async () => {
  const before = (await db.query('SELECT count(*)::int n FROM historical_price')).rows[0].n;
  await db.query("INSERT INTO ingestion_checkpoint VALUES('input','inputs-pdf-v11','inputs-pdf:published')");
  assert.equal(await count('input'), 1);
  assert.equal((await db.query('SELECT count(*)::int n FROM historical_price')).rows[0].n, before);
});
