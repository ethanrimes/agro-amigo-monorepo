const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { Client } = require('pg');

const source = fs.readFileSync(path.join(__dirname, '../src/lib/server/daily-date-note.ts'), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = { exports: {} };
vm.runInNewContext(output, context);
const { annotateDailyDateResolution } = context.exports;
const databaseURL = process.env.AGRO_DAILY_DATE_NOTE_TEST_DATABASE;

test('retained mislinked daily original visibly distinguishes archive day from validated observation',
  { skip: !databaseURL && 'Private PostgreSQL opt-in' }, async () => {
    const db = new Client({ connectionString: databaseURL });
    await db.connect();
    try {
      await db.query(`CREATE TEMP TABLE retained_record (
        table_name text, record jsonb, captured_at timestamptz DEFAULT now()
      )`);
      const did = 'fe66e1d1a39637d81bde11325ba60f8ef8c12a96fdf779f5c6ab7f3586d83e2c';
      const resolution = {
        document_id: did,
        archive_date: '2016-01-18',
        observation_date: '2017-01-18',
        printed_heading: 'Miércoles 18 de enero de 2017',
        basis: 'mislinked_identical_original',
        corroborating_url: 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_18_2016.xls',
      };
      await db.query(`INSERT INTO retained_record(table_name,record)
        VALUES('source_date_resolution',$1::jsonb)`, [JSON.stringify(resolution)]);
      const actual = (await db.query(`SELECT record AS resolution FROM retained_record
        WHERE table_name='source_date_resolution' AND record->>'document_id'=$1
        ORDER BY captured_at DESC LIMIT 1`, [did])).rows[0].resolution;
      const evidence = {
        id: did, reference_period: '2016-01-18',
        source_url: 'https://www.dane.gov.co/2016/archive', metadata: {},
      };
      annotateDailyDateResolution(evidence, actual);
      assert.equal(evidence.reference_period, '2017-01-18');
      assert.equal(evidence.metadata.original_reference_period, '2016-01-18');
      assert.equal(evidence.metadata.archive_reference_date, '2016-01-18');
      assert.match(evidence.metadata.date_resolution_note, /2016-01-18/);
      assert.match(evidence.metadata.date_resolution_note, /2017-01-18/);
      assert.match(evidence.metadata.date_resolution_note, /mismo original/);
      assert.match(evidence.metadata.date_resolution_note, /no se atribuyen al 2016-01-18/);
      assert.equal(evidence.metadata.date_evidence_url, resolution.corroborating_url);
      assert.equal(evidence.source_url, 'https://www.dane.gov.co/2016/archive');
    } finally {
      await db.end();
    }
  });

test('verified same-day heading correction keeps source reference period', () => {
  const evidence = { reference_period: '2014-10-15', metadata: {} };
  annotateDailyDateResolution(evidence, {
    archive_date: '2014-10-15', observation_date: '2014-10-15',
    printed_heading: 'Miércoles 15 de septiembre de 2014', basis: 'native_month_typo',
    corroborating_url: 'https://www.dane.gov.co/source.pdf',
  });
  assert.equal(evidence.reference_period, '2014-10-15');
  assert.equal(evidence.metadata.original_reference_period, undefined);
  assert.match(evidence.metadata.date_resolution_note, /2014-10-15/);
});
