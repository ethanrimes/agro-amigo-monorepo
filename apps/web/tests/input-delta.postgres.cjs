/* Actual migration/role/epoch lifecycle in a disposable private PostgreSQL DB. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { Client } = require('pg');
const socket = process.env.AGRO_DELTA_SQL_SOCKET;
const enabled = socket?.startsWith('/tmp/agro-municipal-pg.');
const port = 65455;
const migration = fs.readFileSync(
  'pipelines/ingestion/migrations/20261001_047_input_projection_delta.sql', 'utf8');
const atomicRebuild = fs.readFileSync(
  'pipelines/ingestion/migrations/20261001_048_input_projection_atomic_rebuild.sql', 'utf8');

test('input projection delta migration is idempotent, transactional and role-safe',
  { skip: !enabled && 'Requires isolated private PostgreSQL socket' }, async () => {
    const name = `agro_delta_${process.pid}`;
    const admin = new Client({ host: socket, port, database: 'postgres' });
    let db, locker, refresher, writer;
    await admin.connect();
    try {
      await admin.query(`CREATE DATABASE ${name}`);
      db = new Client({ host: socket, port, database: name,
        options: '-c timezone=America/Bogota' });
      await db.connect();
      await db.query(`DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agro_reader')
          THEN CREATE ROLE agro_reader NOLOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agro_ingestor')
          THEN CREATE ROLE agro_ingestor NOLOGIN; END IF;
      END $$`);
      await db.query(`CREATE TABLE input_latest_projection_state (
        scope text PRIMARY KEY,source_epoch bigint NOT NULL DEFAULT 0,
        projection_epoch bigint NOT NULL DEFAULT 0,asof_bogota date);
      INSERT INTO input_latest_projection_state(scope,asof_bogota)
        VALUES('department',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date),
          ('municipality',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date);
      CREATE TABLE input_price (
        id text NOT NULL,department text NOT NULL,observed_on date NOT NULL,
        price numeric NOT NULL,name text NOT NULL,category text NOT NULL,
        presentation text NOT NULL,document_id text NOT NULL,
        source_locator text NOT NULL,brand text NOT NULL DEFAULT '',
        registration text NOT NULL DEFAULT '',product_line text NOT NULL DEFAULT '',
        PRIMARY KEY(id,department,observed_on));
      CREATE TABLE input_municipal_price (
        id text NOT NULL,department text NOT NULL,municipality text NOT NULL,
        observed_on date NOT NULL,price numeric NOT NULL,name text NOT NULL,
        category text NOT NULL,presentation text NOT NULL,document_id text NOT NULL,
        source_locator text NOT NULL,brand text NOT NULL DEFAULT '',
        registration text NOT NULL DEFAULT '',product_line text NOT NULL DEFAULT '',
        PRIMARY KEY(id,department,municipality,observed_on));
      CREATE MATERIALIZED VIEW input_department_latest_raw AS
        SELECT DISTINCT ON(id,department) * FROM input_price
        WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
        ORDER BY id,department,observed_on DESC,price;
      CREATE UNIQUE INDEX input_department_latest_raw_location
        ON input_department_latest_raw(id,department);
      CREATE MATERIALIZED VIEW input_municipal_latest_raw AS
        SELECT DISTINCT ON(id,department,municipality) * FROM input_municipal_price
        WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
        ORDER BY id,department,municipality,observed_on DESC,price;
      CREATE UNIQUE INDEX input_municipal_latest_raw_location
        ON input_municipal_latest_raw(id,department,municipality);
      CREATE TABLE ingestion_checkpoint(document_id text,processor_version text,step text);
      CREATE TABLE input_identity_alias(legacy_id text,id text);
      CREATE TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz);
      GRANT USAGE ON SCHEMA public TO agro_reader,agro_ingestor;
      GRANT SELECT ON input_price,input_municipal_price,input_latest_projection_state,
        input_department_latest_raw,input_municipal_latest_raw TO agro_reader;
      GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE ON input_price,input_municipal_price TO agro_ingestor;
      GRANT SELECT ON input_latest_projection_state TO agro_ingestor;`);
      await db.query(migration);
      await db.query(atomicRebuild);
      await db.query(`CREATE TRIGGER input_price_projection_insert AFTER INSERT ON input_price
        REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('department');
      CREATE TRIGGER input_price_projection_update AFTER UPDATE ON input_price
        REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('department');
      CREATE TRIGGER input_price_projection_delete AFTER DELETE ON input_price
        REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('department');
      CREATE TRIGGER input_municipal_projection_insert AFTER INSERT ON input_municipal_price
        REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('municipality');
      CREATE TRIGGER input_municipal_projection_update AFTER UPDATE ON input_municipal_price
        REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('municipality');
      CREATE TRIGGER input_municipal_projection_delete AFTER DELETE ON input_municipal_price
        REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT
        EXECUTE FUNCTION input_latest_projection_changed('municipality');
      CREATE TRIGGER input_municipal_projection_truncate BEFORE TRUNCATE ON input_municipal_price
        FOR EACH STATEMENT EXECUTE FUNCTION input_latest_projection_truncated('municipality');`);
      assert.deepEqual((await db.query('SELECT scope,delta_complete FROM input_latest_projection_state ORDER BY scope'))
        .rows.map(row => [row.scope,row.delta_complete]),
        [['department',true],['municipality',true]]);

      await db.query('SET ROLE agro_ingestor');
      await db.query(`INSERT INTO input_municipal_price
        (id,department,municipality,observed_on,price,name,category,presentation,
          document_id,source_locator)
        VALUES ('new','Cauca','Popayán',CURRENT_DATE-1,100,'Nuevo','Agrícola','1 litro','doc','row')`);
      await db.query('RESET ROLE');
      let state = (await db.query("SELECT source_epoch,projection_epoch,delta_complete FROM input_latest_projection_state WHERE scope='municipality'")).rows[0];
      assert.deepEqual([Number(state.source_epoch),Number(state.projection_epoch),state.delta_complete],
        [1,0,true]);
      assert.deepEqual((await db.query('SELECT scope,id,changed_epoch FROM input_latest_projection_delta')).rows
        .map(row => [row.scope,row.id,Number(row.changed_epoch)]),[['municipality','new',1]]);

      await db.query('SET ROLE agro_ingestor');
      await db.query("UPDATE input_municipal_price SET price=price WHERE id='new'");
      await db.query('RESET ROLE');
      assert.equal(Number((await db.query("SELECT source_epoch FROM input_latest_projection_state WHERE scope='municipality'"))
        .rows[0].source_epoch),1,'equal-value update leaves epoch unchanged');
      await db.query('SET ROLE agro_ingestor');
      await db.query("UPDATE input_municipal_price SET id='renamed',price=120 WHERE id='new'");
      await db.query('RESET ROLE');
      assert.deepEqual((await db.query('SELECT id FROM input_latest_projection_delta ORDER BY id')).rows
        .map(row => row.id),['new','renamed'],'both old and new update IDs are covered');
      await db.query(migration);
      await db.query(atomicRebuild);
      assert.equal((await db.query('SELECT count(*)::int AS n FROM input_latest_projection_delta')).rows[0].n,2,
        'reapplication does not erase pending IDs');
      await db.query('SET ROLE agro_reader');
      assert.equal((await db.query('SELECT count(*)::int AS n FROM input_latest_projection_delta')).rows[0].n,2);
      await assert.rejects(db.query("SELECT refresh_input_latest_projection('municipality')"),
        error => error.code === '42501');
      await db.query('RESET ROLE');
      await db.query('SET ROLE agro_ingestor');
      assert.equal((await db.query("SELECT refresh_input_latest_projection('municipality') AS ok")).rows[0].ok,true);
      await db.query('RESET ROLE');
      state = (await db.query("SELECT source_epoch,projection_epoch,delta_complete FROM input_latest_projection_state WHERE scope='municipality'")).rows[0];
      assert.deepEqual([Number(state.source_epoch),Number(state.projection_epoch),state.delta_complete],
        [2,2,true]);
      assert.equal((await db.query('SELECT count(*)::int AS n FROM input_latest_projection_delta')).rows[0].n,0);
      assert.equal((await db.query("SELECT has_table_privilege('agro_reader','input_municipal_latest_raw','SELECT') AS allowed"))
        .rows[0].allowed,true,'replacement preserves reader grant');
      assert.equal((await db.query("SELECT has_table_privilege('agro_ingestor','input_municipal_latest_raw','SELECT') AS allowed"))
        .rows[0].allowed,true,'replacement preserves worker grant');
      assert.deepEqual((await db.query(`SELECT indexname FROM pg_indexes WHERE tablename='input_municipal_latest_raw'
        ORDER BY indexname`)).rows.map(row => row.indexname),[
        'input_municipal_latest_raw_catalog','input_municipal_latest_raw_location',
        'input_municipal_latest_raw_named','input_municipal_latest_raw_place'],
      'replacement has the same production index names');

      await db.query('SET ROLE agro_ingestor');
      await db.query('BEGIN');
      await db.query(`INSERT INTO input_municipal_price
        (id,department,municipality,observed_on,price,name,category,presentation,
          document_id,source_locator)
        VALUES ('rolled-back','Cauca','Popayán',CURRENT_DATE,100,'Rollback','Agrícola','1 litro','doc','row')`);
      await db.query('ROLLBACK');
      await db.query('RESET ROLE');
      assert.equal(Number((await db.query("SELECT source_epoch FROM input_latest_projection_state WHERE scope='municipality'"))
        .rows[0].source_epoch),2,'rolled-back input transaction cannot publish epoch or delta');
      assert.equal((await db.query('SELECT count(*)::int AS n FROM input_latest_projection_delta')).rows[0].n,0);

      await db.query('SET ROLE agro_ingestor');
      await db.query("DELETE FROM input_municipal_price WHERE id='renamed'");
      await db.query('RESET ROLE');
      assert.deepEqual((await db.query('SELECT id,changed_epoch FROM input_latest_projection_delta')).rows
        .map(row => [row.id,Number(row.changed_epoch)]),[['renamed',3]],
        'delete invalidates the stale pointer identity');
      await db.query('SET ROLE agro_ingestor');
      assert.equal((await db.query("SELECT refresh_input_latest_projection('municipality') AS ok")).rows[0].ok,true);
      await db.query(`INSERT INTO input_municipal_price
        (id,department,municipality,observed_on,price,name,category,presentation,
          document_id,source_locator)
        VALUES ('truncate-me','Cauca','Popayán',CURRENT_DATE,100,'Truncate','Agrícola','1 litro','doc','row')`);
      await db.query('TRUNCATE input_municipal_price');
      await db.query('RESET ROLE');
      state = (await db.query("SELECT delta_complete FROM input_latest_projection_state WHERE scope='municipality'")).rows[0];
      assert.equal(state.delta_complete,false,'truncate forces exact full fallback');

      await db.query("UPDATE input_latest_projection_state SET asof_bogota=CURRENT_DATE-1 WHERE scope='municipality'");
      assert.equal((await db.query(`SELECT delta_complete AND
        asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AS usable
        FROM input_latest_projection_state WHERE scope='municipality'`)).rows[0].usable,false);

      // Keep a reader on the old relation while a staging rebuild finishes.
      // A writer commits at the final swap boundary: the captured epoch remains
      // the baseline and its new identity stays in the delta overlay.
      for (const [label, assign] of [
        ['locker', client => { locker = client; }],
        ['refresher', client => { refresher = client; }],
        ['writer', client => { writer = client; }],
      ]) {
        const client = new Client({ host: socket, port, database: name,
          application_name: `agro_delta_${label}_${process.pid}` });
        await client.connect(); assign(client);
      }
      await db.query("UPDATE input_latest_projection_state SET asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date WHERE scope='municipality'");
      const captured = Number((await db.query("SELECT source_epoch FROM input_latest_projection_state WHERE scope='municipality'"))
        .rows[0].source_epoch);
      await locker.query('BEGIN');
      await locker.query('SELECT count(*) FROM input_municipal_latest_raw');
      const pending = refresher.query("SELECT refresh_input_latest_projection('municipality') AS ok");
      let waiting = false;
      for (let attempt = 0; attempt < 100; attempt++) {
        const active = await db.query(`SELECT wait_event_type FROM pg_stat_activity
          WHERE application_name=$1 AND query LIKE 'SELECT refresh_input_latest_projection%'
            AND state='active'`,[`agro_delta_refresher_${process.pid}`]);
        if (active.rows.some(row => row.wait_event_type === 'Lock')) { waiting = true; break; }
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      assert.equal(waiting,true,'rebuild waits only at the old-view swap');
      await writer.query(`INSERT INTO input_municipal_price
        (id,department,municipality,observed_on,price,name,category,presentation,
          document_id,source_locator)
        VALUES ('during-refresh','Cauca','Popayán',CURRENT_DATE,130,
          'Interleaved','Agrícola','1 litro','doc','row')`);
      await locker.query('COMMIT');
      assert.equal((await pending).rows[0].ok,true);
      state = (await db.query(`SELECT source_epoch,projection_epoch,delta_complete
        FROM input_latest_projection_state WHERE scope='municipality'`)).rows[0];
      assert.deepEqual([Number(state.source_epoch),Number(state.projection_epoch),state.delta_complete],
        [captured+1,captured,true]);
      assert.equal((await db.query(`SELECT (projection_epoch=source_epoch OR delta_complete)
        AND asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AS ready
        FROM input_latest_projection_state WHERE scope='municipality'`)).rows[0].ready,true,
      'same-day delta overlay is usable even after an interleaved writer');
      assert.deepEqual((await db.query("SELECT id FROM input_latest_projection_delta WHERE scope='municipality'"))
        .rows.map(row => row.id),['during-refresh']);
      await db.query('SET ROLE agro_reader');
      assert.equal((await db.query('SELECT count(*)::int n FROM input_municipal_latest_raw')).rows[0].n,0);
      assert.equal((await db.query('SELECT count(*)::int n FROM input_latest_projection_delta')).rows[0].n,1);
      await db.query('RESET ROLE');

      // A failed final lock rolls the staged DDL back, retaining the old view.
      await locker.query('BEGIN');
      await locker.query('SELECT count(*) FROM input_municipal_latest_raw');
      await refresher.query("SET lock_timeout='100ms'");
      await assert.rejects(refresher.query("SELECT refresh_input_latest_projection('municipality')"),
        error => error.code === '55P03');
      await locker.query('COMMIT');
      assert.equal((await db.query(`SELECT to_regclass('input_municipal_latest_raw') IS NOT NULL AS live,
        to_regclass('input_municipal_latest_raw_next') IS NOT NULL AS staging`)).rows[0].live,true);
      assert.equal((await db.query(`SELECT to_regclass('input_municipal_latest_raw_next') IS NOT NULL AS staging`)).rows[0].staging,false);
    } finally {
      await locker?.end(); await refresher?.end(); await writer?.end();
      await db?.end();
      await admin.query(`DROP DATABASE IF EXISTS ${name} WITH (FORCE)`);
      await admin.end();
    }
  });
