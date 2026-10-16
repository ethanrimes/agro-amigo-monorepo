/* Exercise the actual application pool against an explicitly isolated server. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const pg = require('pg');
const socket = process.env.AGRO_CATALOG_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-unified-catalog-pg-');

test('a queued application read survives busy clients without extending its SQL deadline', {
  skip: !enabled && 'Requires isolated PostgreSQL runner', timeout: 45000,
}, async () => {
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(path.join(__dirname,
    '../src/lib/server/db.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInNewContext(source, {
    exports, globalThis: {}, console,
    process: { env: {
      DATABASE_URL: `postgresql:///postgres?host=${encodeURIComponent(socket)}&port=65443`,
      DATABASE_SSL: 'false',
    } },
    require: name => name === 'server-only' ? {} : pg,
  });
  const pool = exports.database();
  const held = [];
  let releaseTimer;
  try {
    for (let i = 0; i < 2; i++) held.push(await pool.connect());
    const started = Date.now();
    const queued = pool.query("SELECT current_setting('statement_timeout') AS deadline, 42 AS value");
    assert.equal(pool.waitingCount, 1);
    // This exceeds the former 8-second checkout deadline. No SQL executes
    // during the wait; the statement deadline must start after checkout.
    releaseTimer = setTimeout(() => held.pop().release(), 8500);
    const result = await queued;
    assert.ok(Date.now() - started >= 8000);
    assert.equal(result.rows[0].value, 42);
    assert.equal(result.rows[0].deadline, '15s');
    assert.equal(pool.totalCount, 2);
    assert.equal(pool.waitingCount, 0);
    const clock = (await pool.query(`SELECT current_setting('TimeZone') AS zone,
      CURRENT_DATE=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AS same_day,
      (timestamptz '2026-10-01 00:30:00+00' AT TIME ZONE current_setting('TimeZone'))::date AS month_boundary,
      (timestamptz '2026-01-01 00:30:00+00' AT TIME ZONE current_setting('TimeZone'))::date AS year_boundary`)).rows[0];
    assert.equal(clock.zone, 'America/Bogota');
    assert.equal(clock.same_day, true);
    assert.equal(clock.month_boundary, '2026-09-30');
    assert.equal(clock.year_boundary, '2025-12-31');
  } finally {
    clearTimeout(releaseTimer);
    for (const client of held) client.release();
    await pool.end();
  }
});
