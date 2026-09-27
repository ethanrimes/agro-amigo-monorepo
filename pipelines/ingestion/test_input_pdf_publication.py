"""Successful PDF parser revisions govern publication without losing originals."""

import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from datetime import date
from unittest.mock import patch

from . import inputs, pdf_sources, worker

HERE = Path(__file__).parent
MIGRATION = HERE / 'migrations/20260927_017_input_pdf_publication.sql'
PERIOD = date(2012, 7, 31)


class PrintedInputOriginal(unittest.TestCase):
    def test_actual_july_2012_publisher_spelling_and_six_prices_are_retained(self):
        path = Path('artifacts/app-data-audit-2026-09-27/prices/earliest-input-source.pdf')
        if not path.exists():
            self.skipTest('Locally retained authoritative original is unavailable')
        body = path.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), 'f6d511041bd29947ea6ea624739a9f7f6d2708870995ab41f9c398106fe74615')
        rows = list(pdf_sources.parse_input_pdf(body, PERIOD))
        self.assertEqual(len(rows), 3271)
        wire = [row for row in rows if row[3] == 'Alambre galonesvanizado núm. 14']
        self.assertEqual({r[4]: r[6] for r in wire}, {'Andes': 4150, 'Chiquinquirá': 4100, 'El Carmen de Viboral': 4167, 'El Santuario': 4500, 'Piedecuesta': 3400, 'San Alberto': 3500})
        for row in wire:
            self.assertEqual(row[2], PERIOD)
            self.assertEqual(row[5], 'rollo por 1 kilogramo')
            self.assertEqual(row[-1]['page'], 36)
            self.assertEqual(row[-1]['printed_heading'], 'Alambre galonesvanizado núm. 14, rollo por 1 kilogramo')


@unittest.skipUnless(os.environ.get('AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST') == '1', 'Explicit TEMP-only PostgreSQL opt-in')
class InputPDFPublication(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute('SET search_path=pg_temp')
        self.db.execute("SET statement_timeout='10s'")
        self.db.execute('''CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz NOT NULL);
          CREATE TEMP TABLE historical_price(document_id text,source_locator text,series text,observed_on date,product_name text,market_name text,unit text,price numeric,change_percent numeric,details jsonb,PRIMARY KEY(document_id,source_locator));
          CREATE TEMP TABLE input_price(id text,department text,observed_on date,name text,category text,presentation text,price numeric,document_id text,source_locator text,brand text,registration text,product_line text,PRIMARY KEY(id,department,observed_on));
          CREATE TEMP TABLE input_municipal_price(LIKE input_price INCLUDING DEFAULTS,municipality text,PRIMARY KEY(id,department,municipality,observed_on));
          CREATE TEMP TABLE input_revision(id text,department text,municipality text,observed_on date,retrieved_at timestamptz,PRIMARY KEY(id,department,municipality,observed_on));
          CREATE TEMP TABLE ingestion_asset(document_id text,kind text,processor_version text,status text);
          CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint,PRIMARY KEY(document_id,processor_version,step));
          CREATE TEMP TABLE retained_record(table_name text,fingerprint text,captured_at timestamptz DEFAULT now(),record jsonb,PRIMARY KEY(table_name,fingerprint));
          CREATE TEMP TABLE input_attempt(table_name text,id text,operation text);
          CREATE FUNCTION pg_temp.input_attempt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO input_attempt VALUES(TG_TABLE_NAME,NEW.id,TG_OP);RETURN NEW;END $$;''')
        schema = (HERE / 'schema.sql').read_text()
        retain = re.search(r'CREATE OR REPLACE FUNCTION preserve_record_version\(\)[\s\S]*?END \$\$;', schema).group(0)
        self.db.execute(retain.replace('preserve_record_version()', 'pg_temp.preserve_record_version()'))
        for table in ('input_price', 'input_municipal_price'):
            self.db.execute(f'''CREATE TRIGGER attempt BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION pg_temp.input_attempt();
              CREATE TRIGGER preserve AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION pg_temp.preserve_record_version()''')
        sql = MIGRATION.read_text()
        views = sql[sql.index('CREATE OR REPLACE VIEW'):sql.index('GRANT SELECT')]
        self.db.execute(views.replace('CREATE OR REPLACE VIEW', 'CREATE TEMP VIEW'))
        for table in ('source_document','historical_price','input_price','input_municipal_price','input_revision','ingestion_asset','ingestion_checkpoint','retained_record','input_attempt'):
            self.assertEqual(self.db.execute('SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)', (table,)).fetchone(), ('t',))
        for did, day in [('old', 1), ('new', 3)]:
            self.db.execute('INSERT INTO source_document VALUES(%s,%s)', (did, f'2026-09-0{day}T00:00:00Z'))

    def rows(self, version, values):
        rows = []
        for municipal in (False, True):
            for cell, name, price, valid in values:
                meta = {'parser_version': version, 'category': 'Elementos agropecuarios', 'presentation': 'kg', 'department': 'Santander', 'municipality': 'Piedecuesta' if municipal else '', 'brand': '', 'ica': ''}
                rows.append(worker.record('dane-inputs-pdf' if valid else 'dane-inputs-pdf-unresolved', PERIOD, name, meta['municipality'] or 'Santander', 'kg', price, f'PDF page {2 if municipal else 1},col 1,y {cell}; {version}', details=meta))
        return rows

    def publish(self, version, values, did='old', fail=False):
        with patch.object(pdf_sources, 'INPUT_PDF_VERSION', version):
            with self.db.transaction():
                worker.save_rows(self.db, did, self.rows(version, values))
                worker.project(self.db, did, 'https://official.example/original.pdf', 'inputs-pdf')
                if fail:
                    raise RuntimeError('forced publication rollback')

    def visible(self, table):
        return self.db.execute(f'SELECT name,price,document_id,source_locator FROM published_{table} ORDER BY name').fetchall()

    def count(self, table):
        return self.db.execute(f'SELECT count(*) FROM pg_temp.{table}').fetchone()[0]

    def test_new_version_refreshes_equal_value_and_hides_removed_or_reviewed_identity(self):
        self.publish('inputs-pdf-v4', [(1,'Same',100,True),(2,'Wrong name',200,True),(3,'Uncertain',300,True)])
        self.publish('inputs-pdf-v5', [(1,'Same',100,True),(2,'Correct name',200,True),(3,'Uncertain',300,False)])
        for table in ('input_price','input_municipal_price'):
            rows = self.visible(table)
            self.assertEqual([(r[0],r[1]) for r in rows], [('Correct name',200),('Same',100)])
            self.assertTrue(all(r[3].endswith('; inputs-pdf-v5') for r in rows))
            self.assertEqual(self.count(table), 4)  # Old identities retained, only view hides them.
        self.assertEqual(self.count('historical_price'), 12)
        self.assertEqual(self.count('retained_record'), 10)
        self.assertEqual(self.count('ingestion_checkpoint'), 2)
        before = self.count('input_attempt')
        self.publish('inputs-pdf-v5', [(1,'Same',100,True),(2,'Correct name',200,True),(3,'Uncertain',300,False)])
        self.assertEqual(self.count('input_attempt'), before)
        self.assertEqual(self.count('retained_record'), 10)

    def test_different_original_equal_price_keeps_original_attribution(self):
        self.publish('inputs-pdf-v4', [(1,'Same',100,True)])
        before = self.count('input_attempt')
        self.publish('inputs-pdf-v5', [(1,'Same',100,True)], did='new')
        self.assertEqual(self.count('input_attempt'), before)
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(self.visible(table)[0][2], 'old')
            self.assertTrue(self.visible(table)[0][3].endswith('; inputs-pdf-v4'))
        self.assertEqual(self.count('historical_price'), 4)
        self.assertEqual(self.count('ingestion_checkpoint'), 2)
        # A later revalidation of the retained original must not hide a valid
        # unchanged price merely because the newer original set its watermark.
        self.publish('inputs-pdf-v5', [(1,'Same',100,True)], did='old')
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(self.visible(table)[0][2], 'old')
            self.assertTrue(self.visible(table)[0][3].endswith('; inputs-pdf-v5'))
        self.assertTrue(self.db.execute("SELECT bool_and(retrieved_at=(SELECT retrieved_at FROM source_document WHERE id='new')) FROM input_revision").fetchone()[0])

    def test_failed_transaction_or_new_attempt_metadata_cannot_advance_eligibility(self):
        self.publish('inputs-pdf-v4', [(1,'Same',100,True)])
        with self.assertRaisesRegex(RuntimeError, 'forced publication rollback'):
            self.publish('inputs-pdf-v5', [(1,'Same',200,True)], fail=True)
        self.db.execute("INSERT INTO ingestion_asset VALUES('old','inputs-pdf','inputs-pdf-v5','failed')")
        self.assertEqual(self.count('ingestion_checkpoint'), 1)
        self.assertEqual(self.count('historical_price'), 2)
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(self.visible(table)[0][1], 100)
        self.publish('inputs-pdf-v5', [(1,'Same',200,True)])
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(self.visible(table)[0][1], 200)

    def test_all_reviewed_source_hides_old_values_and_keeps_every_original(self):
        self.publish('inputs-pdf-v4', [(1,'Uncertain',100,True)])
        self.publish('inputs-pdf-v5', [(1,'Uncertain',100,False)])
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(self.visible(table), [])
            self.assertEqual(self.count(table), 1)
        self.assertEqual(self.count('historical_price'), 4)
        self.assertEqual(self.db.execute("SELECT records FROM ingestion_checkpoint WHERE processor_version='inputs-pdf-v5'").fetchone()[0], 0)

    def test_versions_compare_numerically_and_older_replay_cannot_downgrade(self):
        self.publish('inputs-pdf-v9', [(1,'Same',100,True)])
        self.publish('inputs-pdf-v10', [(1,'Same',100,True)])
        self.publish('inputs-pdf-v9', [(2,'Old-only interpretation',50,True)])
        for table in ('input_price','input_municipal_price'):
            self.assertEqual(len(self.visible(table)), 1)
            self.assertTrue(self.visible(table)[0][3].endswith('; inputs-pdf-v10'))

    def test_registered_current_version_revalidates_without_changing_the_quote(self):
        current = pdf_sources.INPUT_PDF_VERSION
        self.assertEqual(worker.parser_version('inputs-pdf'), current)
        self.publish('inputs-pdf-v4', [(1,'Same',100,True)])
        self.publish(current, [(1,'Same',100,True)])
        for table in ('input_price','input_municipal_price'):
            row = self.visible(table)[0]
            self.assertEqual(row[:3], ('Same',100,'old'))
            self.assertTrue(row[3].endswith('; ' + current))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE processor_version=%s AND step='inputs-pdf:published'", (current,)).fetchone()[0], 1)

    def test_migration_seeds_committed_v4_without_claiming_attempted_v5(self):
        with self.db.transaction():
            worker.save_rows(self.db, 'old', self.rows('inputs-pdf-v4', [(1,'Same',100,True)]))
        self.db.execute("INSERT INTO ingestion_asset VALUES('old','inputs-pdf','inputs-pdf-v5','failed')")
        sql = MIGRATION.read_text().split('CREATE OR REPLACE VIEW')[0]
        self.db.execute(sql)
        self.db.execute(sql)
        self.assertEqual(self.db.execute('SELECT processor_version,step FROM ingestion_checkpoint').fetchall(), [('inputs-pdf-v4','inputs-pdf:published')])


if __name__ == '__main__':
    unittest.main()
