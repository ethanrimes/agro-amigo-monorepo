const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client } = require('pg');

const databaseURL = process.env.AGRO_SUPPLY_VERSION_TEST_DATABASE;
const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/supply-summary-evidence.ts'), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = { exports: {}, URLSearchParams };
vm.runInNewContext(output, context);
const {
  SUPPLY_PERIOD_CANONICAL_VERSION_SQL: versionSQL,
  SUPPLY_PERIOD_SUMMARY_SQL: summarySQL,
  SUPPLY_PERIOD_ROWS_SQL: rowsSQL,
  showsSupplySummaryRecords,
} = context.exports;

test('exact printed-row OCR locators open supply cells, while unrelated filters stay excluded', () => {
  for (const column of [2, 3, 4]) {
    const locator = `PDF page 4, OCR table 1, row 2, column ${column}; printed-row-v2; supply-period-summary-v8`;
    assert.equal(showsSupplySummaryRecords(new URLSearchParams({ locator })), true);
    assert.equal(showsSupplySummaryRecords(new URLSearchParams({ locator, product: 'Papa' })), false);
  }
  assert.equal(showsSupplySummaryRecords(new URLSearchParams({ locator:
    'PDF page 4, OCR table 1, row 2, column 1; printed-row-v2; supply-period-summary-v8' })), false);
  assert.equal(showsSupplySummaryRecords(new URLSearchParams({ locator:
    '1!row 11,col 4; printed-row-v2; supply-period-summary-v8' })), false);
});

test('complete v8 supply source wins default evidence while 163 old cells remain addressable',
  { skip: !databaseURL && 'Private PostgreSQL opt-in' }, async () => {
    const db = new Client({ connectionString: databaseURL });
    await db.connect();
    try {
      await db.query(`CREATE TEMP TABLE ingestion_asset (
        document_id text, kind text, status text, records int,
        checked_at timestamptz, processor_version text
      )`);
      await db.query(`CREATE TEMP TABLE input_reference_row (
        document_id text, kind text, source_locator text,
        observed_on date, name text, category text, details jsonb
      )`);
      const did = '6d6de4015c62cae7aefe0deb5365963092a5340c41333486a5cbe5ed073a37bc';
      const oldLocator = '1!row 11,col 3; supply-period-summary-v1';
      const newLocator = '1!row 11,col 3; supply-period-summary-v8';
      await db.query(`INSERT INTO ingestion_asset
        (document_id,kind,status,records,checked_at,processor_version)
        VALUES($1,'supply-reference','review',163,now(),
        'supply-daily-summary-v1:supply-period-summary-workbook-v2')`, [did]);
      await db.query(`INSERT INTO input_reference_row
        SELECT $1,'supply-period-summary',
         '1!row '||(10+n)::text||',col 3; supply-period-summary-v1',
         date '2023-06-15','Armenia, Mercar','Abastecimiento',
         jsonb_build_object('unit','t','value',n+1000,'period_start','2023-06-01',
           'period_end','2023-06-15','frequency','first_fortnight')
        FROM generate_series(1,163) n`, [did]);
      const version = async () => (await db.query(versionSQL, [did])).rows[0]?.version;
      const summary = async selected => (await db.query(summarySQL, [did, selected])).rows[0];
      const rows = async (locator, selected) => (await db.query(rowsSQL, [did, locator, selected])).rows;
      assert.equal(await version(), 1);
      assert.equal((await summary(1)).cells, 163);

      // Even exactly 163 staged new cells must not displace the retained v1
      // revision while the durable asset still points to 163 older cells.
      await db.query(`INSERT INTO input_reference_row
        SELECT $1,'supply-period-summary',
         '1!row '||(10+n)::text||',col 3; supply-period-summary-v8',
         date '2023-06-15','Armenia, Mercar','Abastecimiento',
         jsonb_build_object('unit','t','value',n,'period_start','2023-06-01',
           'period_end','2023-06-15','frequency','first_fortnight')
        FROM generate_series(1,163) n`, [did]);
      assert.equal(await version(), 1);
      assert.equal((await summary(1)).cells, 163);
      assert.equal((await rows(oldLocator, 1))[0].value, 1001);
      assert.equal((await rows(newLocator, 1))[0].value, 1);
      await db.query(`INSERT INTO input_reference_row
        SELECT $1,'supply-period-summary',
         '1!row '||(10+n)::text||',col 3; supply-period-summary-v8',
         date '2023-06-15','Armenia, Mercar','Abastecimiento',
         jsonb_build_object('unit','t','value',n,'period_start','2023-06-01',
           'period_end','2023-06-15','frequency','first_fortnight')
        FROM generate_series(164,983) n`, [did]);
      await db.query(`UPDATE ingestion_asset SET status='complete',records=983,checked_at=now() WHERE document_id=$1`, [did]);

      assert.equal(await version(), 8);
      assert.equal((await summary(8)).cells, 983);
      assert.equal((await db.query(`SELECT count(*)::int total FROM input_reference_row WHERE document_id=$1`, [did])).rows[0].total, 1146);
      const visible = await rows('', 8);
      assert.equal(visible.length, 100);
      assert.ok(visible.every(row => row.source_locator.endsWith('supply-period-summary-v8')));
      const old = await rows(oldLocator, 8);
      assert.equal(old.length, 1);
      assert.equal(old[0].source_locator, oldLocator);
      const updated = await rows(newLocator, 8);
      assert.equal(updated.length, 1);
      assert.equal(updated[0].source_locator, newLocator);

      // A PDF with equal-sized revisions follows the explicitly durable
      // parser version; an OCR-only complete source has no legacy ambiguity.
      const pdfDid = 'a'.repeat(64), ocrDid = 'b'.repeat(64);
      await db.query(`INSERT INTO ingestion_asset
        (document_id,kind,status,records,checked_at,processor_version)
        VALUES($1,'supply-reference-pdf','complete',90,now(),'supply-period-summary-v1'),
              ($2,'supply-reference-pdf','complete',90,now(),'supply-period-summary-v1')`, [pdfDid, ocrDid]);
      await db.query(`INSERT INTO input_reference_row
        SELECT $1,'supply-period-summary',
         'PDF page 2, row y'||n::text||'.00, column 1; supply-period-summary-v'||v::text,
         date '2021-06-30','Armenia, Mercar','Abastecimiento',
         jsonb_build_object('unit','t','value',n)
        FROM generate_series(1,90) n CROSS JOIN (VALUES(1),(8)) versions(v)`, [pdfDid]);
      await db.query(`INSERT INTO input_reference_row
        SELECT $1,'supply-period-summary',
         'PDF page 4, OCR table 1, row '||n::text||', column 2; printed-row-v2; supply-period-summary-v8',
         date '2021-06-30','Armenia, Mercar','Abastecimiento',
         jsonb_build_object('unit','t','value',n)
        FROM generate_series(1,90) n`, [ocrDid]);
      assert.equal((await db.query(versionSQL, [pdfDid])).rows[0].version, 1);
      assert.equal((await db.query(versionSQL, [ocrDid])).rows[0].version, 8);
      await db.query(`UPDATE ingestion_asset SET status='review' WHERE document_id=$1`, [ocrDid]);
      assert.equal((await db.query(versionSQL, [ocrDid])).rows.length, 0,
        'a reviewed partial v8 revision cannot become the default merely by matching records');
      await db.query(`UPDATE ingestion_asset SET status='complete' WHERE document_id=$1`, [ocrDid]);
      assert.equal((await db.query(versionSQL, [ocrDid])).rows[0].version, 8);
    } finally {
      await db.end();
    }
  });
