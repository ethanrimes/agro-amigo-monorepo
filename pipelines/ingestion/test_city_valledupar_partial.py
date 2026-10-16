"""Independent exact-source Valledupar grid and append-only partial replay."""
import copy
import io
import json
import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb

from . import city_reports, city_valledupar_partial as exact, queue_plan, worker
from . import test_city_publication as publication_tests
from .city_exact_source_dispatch_v44_b import maybe_publish_exact_city_zip, retained_exact_city_zip


DATA = Path(__file__).resolve().parent / 'testdata'
ZIP = DATA / 'city_valledupar_20220107.zip'
ORACLE = DATA / 'city_valledupar_20220107_oracle.json'


def originals():
    parent = ZIP.read_bytes()
    assert sha256(parent).hexdigest() == exact.PARENT
    with zipfile.ZipFile(io.BytesIO(parent)) as archive:
        child = archive.read(exact.ENTRY)
    assert sha256(child).hexdigest() == exact.CHILD
    return parent, child


class ValleduparPartialSourceTests(unittest.TestCase):
    def test_all_35_independent_17_field_rows_and_unpriced_coco(self):
        _, child = originals()
        proof = json.loads(ORACLE.read_text())
        self.assertEqual(proof['parent_sha256'], exact.PARENT)
        self.assertEqual(proof['child_sha256'], exact.CHILD)
        self.assertEqual((proof['price_line_count'], proof['recoverable_quote_count'],
                          proof['coco_unresolved_literal']), (36, 35, exact.COCO))
        rows, review = exact.parse_exact_child(child)
        self.assertEqual(len(rows), 35)
        self.assertEqual([[str(v) if isinstance(v, (date, Decimal)) else v for v in r] for r in rows],
                         proof['rows'])
        self.assertEqual(review['error_type'], 'SourceQuantityOmitted')
        self.assertEqual(review['document_id'], exact.CHILD)
        self.assertIn('sin cantidad numérica', review['error'])
        self.assertNotIn('PDF page 1,table 1,row 6,round 1', [r[0] for r in rows])

    def test_generic_parser_unchanged_and_exact_grid_rejects_any_cell_mutation(self):
        _, child = originals()
        self.assertEqual(sha256(Path(city_reports.__file__).read_bytes()).hexdigest(),
                         'e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0')
        with self.assertRaises(ValueError):
            list(city_reports.parse_city_pdf(child, exact.DAY))
        original = city_reports._city_tables
        def changed(page):
            tables = copy.deepcopy(original(page))
            if page.page_number == 1:
                tables[0][5][3] = '3.551'
            return tables
        with patch.object(city_reports, '_city_tables', side_effect=changed), self.assertRaises(ValueError):
            exact.parse_exact_child(child)
        with self.assertRaises(ValueError):
            exact.parse_exact_child(child + b'changed')

    def test_parent_zip_member_crc_size_header_day_and_version_are_bound(self):
        parent, child = originals()
        member, actual = exact.exact_member(parent)
        self.assertEqual((member.filename, member.CRC, member.file_size, actual),
                         (exact.ENTRY, exact.CRC, exact.SIZE, child))
        self.assertEqual(city_reports._member_step(member, exact.DAY), queue_plan.VALLEDUPAR_EXACT_STEP)
        self.assertEqual(worker.asset_parser_version('city-zip', exact.URL), exact.VERSION)
        self.assertIn((exact.URL, 'city-zip', exact.PARENT), queue_plan.PRIORITY_SOURCE_REPAIRS)
        self.assertIsNone(maybe_publish_exact_city_zip(None, exact.URL + '?other', parent, exact.PARENT))
        with self.assertRaises(ValueError):
            exact.publish_exact_parent(None, exact.URL, parent, 'other')
        with self.assertRaises(ValueError):
            exact.exact_member(parent + b'changed')


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit isolated PostgreSQL opt-in')
class ValleduparPartialPostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_tests.CityPublicationPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.enterContext(patch.object(worker, 'archive', side_effect=self.local_archive))
        self.parent, self.child = originals()
        self.did = self.local_archive(self.fixture.db, exact.URL, self.parent, 'city-zip', exact.DAY)
        self.fixture.db.execute('CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL)')
        self.fixture.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'review',%s,0,'city-v8',now()-interval '7 hours')''',
          (exact.URL, exact.DAY, self.did))

    @staticmethod
    def local_archive(db, url, data, kind, day=None, *, filename=None, parents=None, **kwargs):
        did = sha256(data).hexdigest()
        metadata = {'ingestion_kind': kind, 'retention': 'permanent',
                    'original_filename': url.rsplit('/', 1)[-1]}
        if parents:
            metadata.update({'parents': parents, 'archive_entry': filename})
        db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s) ON CONFLICT DO NOTHING''',
          (did, filename or kind, url,
           'application/pdf' if kind == 'city-pdf' else 'application/zip',
           str(day or 'Serie histórica completa'), data, Jsonb(metadata)))
        return did

    @property
    def db(self):
        return self.fixture.db

    def publish(self):
        with self.assertRaises(city_reports.CityZipPartialReview) as result:
            maybe_publish_exact_city_zip(self.db, exact.URL, self.parent, self.did)
        self.assertEqual(result.exception.count, exact.EXPECTED_TOTAL)
        self.assertEqual(result.exception.failures, [exact.REVIEW])

    def test_real_parent_partial_publication_rerun_and_old_row_xmins(self):
        with self.assertRaises(city_reports.CityZipPartialReview) as before:
            city_reports.publish_city_zip(self.db, self.parent, self.did, exact.URL, exact.DAY)
        self.assertEqual(before.exception.count, exact.EXPECTED_SIBLINGS)
        old = self.db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()
        self.assertEqual(len(old), exact.EXPECTED_SIBLINGS)
        self.publish()
        rows = self.db.execute('SELECT source_locator,' + ','.join(city_reports._PRICE_FIELDS) +
                               ' FROM regional_price WHERE document_id=%s ORDER BY source_locator',
                               (exact.CHILD,)).fetchall()
        proof = json.loads(ORACLE.read_text())
        expected = sorted(proof['rows'], key=lambda r: r[0])
        self.assertEqual([[str(v) if isinstance(v, (date, Decimal)) else v for v in r] for r in rows], expected)
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_regional_price').fetchone()[0], 1418)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_classification WHERE document_id=%s',
                                         (exact.CHILD,)).fetchone(), (35,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price WHERE document_id=%s AND product_name='Coco'",
                                         (exact.CHILD,)).fetchone(), (0,))
        self.assertTrue(set(old) <= set(self.db.execute(
            'SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()))
        self.assertEqual(self.db.execute('''SELECT count(*),sum(records) FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%' ''',
          (self.did, exact.VERSION)).fetchone(), (18, 1418))
        self.assertEqual(self.db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (self.did, exact.VERSION, exact.REVIEW_STEP)).fetchone(), (0,))
        before_rows = self.db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()
        self.publish()
        self.assertEqual(self.db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall(), before_rows)

    def test_rollback_after_copy_then_failed_retained_retry_without_http(self):
        insert = city_reports._bulk_insert
        def crash(db, table, rows):
            rows = list(rows)
            if table == 'regional_price' and rows and rows[0][0] == exact.CHILD:
                insert(db, table, rows)
                raise RuntimeError('controlled Valle child crash after COPY')
            return insert(db, table, rows)
        with patch.object(city_reports, '_bulk_insert', side_effect=crash), self.assertRaisesRegex(RuntimeError, 'after COPY'):
            self.publish()
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                                         (exact.CHILD,)).fetchone(), (0,))
        self.db.execute('''UPDATE ingestion_asset SET status='failed',processor_version=%s,
          checked_at=now(),error='controlled crash' WHERE url=%s''', (exact.VERSION, exact.URL))
        self.assertNotIn(exact.URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (exact.URL,))
        self.assertIn(exact.URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.assertEqual(retained_exact_city_zip(self.db, exact.URL, 'city-zip', exact.VERSION), self.parent)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No HTTP on retained replay')):
            self.assertEqual(worker.process_asset(self.db, exact.URL, 'city-zip', exact.DAY), 1418)
        self.assertEqual(self.db.execute('SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s',
                                         (exact.URL,)).fetchone(), ('review', 1418, exact.VERSION))
        self.assertIn('Coco sigue pendiente de verificación', self.db.execute(
            'SELECT error FROM ingestion_asset WHERE url=%s', (exact.URL,)).fetchone()[0])
        self.assertEqual(self.db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (self.did, exact.VERSION, exact.REVIEW_STEP)).fetchone(), (0,))
        self.assertIsNone(retained_exact_city_zip(self.db, exact.URL, 'city-zip', exact.VERSION))
        self.assertNotIn(exact.URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])

    def test_bad_source_metadata_checkpoint_and_stored_money_fail_closed(self):
        for field, wrong, good in (('observed_on', date(2022, 1, 8), exact.DAY),
                                   ('document_id', self.fixture.did, self.did),
                                   ('kind', 'daily', 'city-zip')):
            self.db.execute(f'UPDATE ingestion_asset SET {field}=%s WHERE url=%s', (wrong, exact.URL))
            with self.assertRaises(ValueError):
                self.publish()
            self.db.execute(f'UPDATE ingestion_asset SET {field}=%s WHERE url=%s', (good, exact.URL))
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{original_filename}',to_jsonb('wrong.zip'::text)) WHERE id=%s", (self.did,))
        with self.assertRaises(ValueError):
            self.publish()
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{original_filename}',to_jsonb(%s::text)) WHERE id=%s", (exact.URL.rsplit('/',1)[-1], self.did))
        self.db.execute("UPDATE source_document SET media_type='application/octet-stream' WHERE id=%s", (self.did,))
        with self.assertRaises(ValueError):
            self.publish()
        self.db.execute("UPDATE source_document SET media_type='application/zip' WHERE id=%s", (self.did,))
        self.publish()
        before = self.db.execute('SELECT count(*),min(xmin::text) FROM regional_price WHERE document_id=%s', (exact.CHILD,)).fetchone()
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{archive_entry}',to_jsonb('wrong.pdf'::text)) WHERE id=%s", (exact.CHILD,))
        with self.assertRaises(ValueError):
            self.publish()
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{archive_entry}',to_jsonb(%s::text)) WHERE id=%s", (exact.ENTRY, exact.CHILD))
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{parents}',to_jsonb(ARRAY['wrong']::text[])) WHERE id=%s", (exact.CHILD,))
        with self.assertRaises(ValueError):
            self.publish()
        self.db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{parents}',to_jsonb(ARRAY[%s]::text[])) WHERE id=%s", (exact.PARENT, exact.CHILD))
        self.db.execute('UPDATE ingestion_checkpoint SET records=34 WHERE document_id=%s AND processor_version=%s AND step=%s',
                        (self.did, exact.VERSION, queue_plan.VALLEDUPAR_EXACT_STEP))
        with self.assertRaises(ValueError):
            self.publish()
        self.db.execute('UPDATE ingestion_checkpoint SET records=35 WHERE document_id=%s AND processor_version=%s AND step=%s',
                        (self.did, exact.VERSION, queue_plan.VALLEDUPAR_EXACT_STEP))
        self.db.execute("UPDATE regional_price SET product_name=product_name||' tampered' WHERE document_id=%s AND source_locator=(SELECT min(source_locator) FROM regional_price WHERE document_id=%s)",
                        (exact.CHILD, exact.CHILD))
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                                         (exact.CHILD,)).fetchone(), (35,))
        self.assertEqual(before[0], 35)
