"""Native source geometry, full independent grid and append-only publication."""
import copy
import io
import json
import os
import unittest
import zipfile
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from psycopg.types.json import Jsonb

from . import city_native_geometry as geometry, city_reports, city_unit_overflow, queue_plan, worker
from .city_exact_source_dispatch_v44_b import maybe_publish_exact_city_zip, retained_exact_city_zip
from . import test_city_publication as city_publication_tests

DATA = Path(__file__).resolve().parent / 'testdata'
ZIP = DATA / 'city_native_armenia_20220111.zip'
ORACLE = DATA / 'city_native_armenia_20220111_poppler.json'
URL = geometry.URL
ENTRY = geometry.ENTRY


def originals():
    body = ZIP.read_bytes()
    assert sha256(body).hexdigest() == geometry.PARENT
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        child = archive.read(ENTRY)
    assert sha256(child).hexdigest() == geometry.CHILD
    return body, child


class NativeCityGeometryTests(unittest.TestCase):
    def test_only_source_bound_wrapper_matches_all_53_independent_17_field_rows_without_http(self):
        _, child = originals()
        oracle = json.loads(ORACLE.read_text())
        self.assertEqual(oracle['source_sha256'], geometry.CHILD)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Native extraction must not use HTTP')):
            rows = geometry.parse_exact_child(child)
        self.assertEqual(len(rows), 53)
        self.assertEqual(geometry.canonical_grid(rows), geometry.canonical_grid(oracle['rows']))
        self.assertEqual(geometry.validate_rows(rows), rows)
        uva = next(r for r in rows if r[3] == 'Uva Isabela')
        self.assertEqual((str(uva[7]), uva[8], uva[13], uva[14], uva[15]),
                         ('25', 'Unidad 454 Gr', 'Unidad 454 Gr', None, None))
        self.assertEqual({r[3] for r in rows if r[0].startswith('PDF page 2') and r[3] in ('Habichuela', 'Pimentón')},
                         {'Habichuela', 'Pimentón'})

    def test_generic_parser_keeps_its_v49_source_proof_and_refuses_this_child(self):
        _, child = originals()
        self.assertEqual(sha256(Path(city_reports.__file__).read_bytes()).hexdigest(),
                         'e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0')
        with self.assertRaises(ValueError):
            list(city_reports.parse_city_pdf(child, geometry.DAY))

    def test_changed_child_bytes_cannot_use_reviewed_geometry(self):
        _, child = originals()
        with self.assertRaises(ValueError):
            geometry.parse_exact_child(child + b'changed')
        with self.assertRaises(ValueError):
            geometry.parse_exact_child(b'%PDF-other-source')

    def test_exact_parent_member_crc_size_and_child_hash_are_bound(self):
        parent, child = originals()
        member, found = geometry._exact_member(parent)
        self.assertEqual((member.filename, member.CRC, member.file_size, found),
                         (ENTRY, geometry.ENTRY_CRC, geometry.ENTRY_SIZE, child))
        self.assertEqual(queue_plan.ARMENIA_EXACT_STEP,
                         city_reports._member_step(member, geometry.DAY))
        with zipfile.ZipFile(io.BytesIO(parent)) as original:
            changed = io.BytesIO()
            with zipfile.ZipFile(changed, 'w') as rewritten:
                for item in original.infolist():
                    rewritten.writestr(item.filename + '-renamed' if item.filename == ENTRY
                                         else item.filename, original.read(item))
        with self.assertRaises(ValueError):
            geometry._exact_member(changed.getvalue())
        with self.assertRaises(ValueError):
            geometry.publish_exact_parent(None, URL, parent + b'changed', geometry.PARENT)

    def test_general_overflow_reader_remains_strict_and_row_changes_fail_closed(self):
        _, child = originals()
        with pdfplumber.open(io.BytesIO(child)) as pdf:
            page = pdf.pages[0]
            original = city_reports._city_tables(page)
            shapes = page.find_tables()
            self.assertIsNone(city_unit_overflow._one_cell(page, original[0][32], shapes[0].rows[32].cells))
            for column, value in ((0, 'Uva otra'), (2, '26 Unidad 454'), (3, 'G r 40.001'), (4, '42.001')):
                changed = copy.deepcopy(original)
                changed[0][32][column] = value
                with self.subTest(column=column), patch.object(city_reports, '_city_tables', return_value=changed), self.assertRaises(ValueError):
                    geometry.reviewed_tables(page)

    def test_whole_grid_must_be_complete_and_unchanged_before_publication(self):
        _, child = originals()
        rows = geometry.parse_exact_child(child)
        self.assertEqual(geometry.validate_rows(rows), rows)
        with self.assertRaises(ValueError):
            geometry.validate_rows(rows[:-1])
        changed = list(rows)
        first = list(changed[0]); first[11] += 1; changed[0] = tuple(first)
        with self.assertRaises(ValueError):
            geometry.validate_rows(changed)

    def test_unknown_dispatch_and_changed_parent_identity_never_enter_exact_route(self):
        parent, _ = originals()
        self.assertIsNone(maybe_publish_exact_city_zip(None, URL + '?other', parent, geometry.PARENT))
        with self.assertRaises(ValueError):
            maybe_publish_exact_city_zip(None, URL, parent, 'other')


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit opt-in for isolated PostgreSQL TEMP-table city checks')
class NativeCityGeometryPostgresTests(unittest.TestCase):
    def setUp(self):
        # Only reuse its database setup; do not depend on another test's name.
        self.fixture = city_publication_tests.CityPublicationPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.enterContext(patch.object(worker, 'archive', side_effect=self.local_archive))
        self.parent, self.child = originals()
        self.did = self.local_archive(self.fixture.db, URL, self.parent, 'city-zip', geometry.DAY)
        self.assertEqual(self.did, geometry.PARENT)
        self.fixture.db.execute('CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL)')
        self.fixture.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'review',%s,0,'city-v8',now()-interval '7 hours')''',
          (URL, geometry.DAY, self.did))

    @staticmethod
    def local_archive(db, url, data, kind, day=None, *, filename=None, parents=None, **kwargs):
        did = sha256(data).hexdigest()
        metadata = {'ingestion_kind': kind, 'retention': 'permanent'}
        if parents:
            metadata.update({'parents': parents, 'archive_entry': filename})
        db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s) ON CONFLICT DO NOTHING''',
          (did, filename or kind, url,
           'application/pdf' if kind == 'city-pdf' else 'application/zip',
           str(day or 'Serie histórica completa'), data, Jsonb(metadata)))
        return did

    def publish(self):
        return maybe_publish_exact_city_zip(self.fixture.db, URL, self.parent, self.did)

    def test_exact_parent_queue_revision_cooldown_and_retained_byte_route(self):
        db = self.fixture.db
        generic_url = 'https://www.dane.gov.co/test.zip'
        generic_did = self.fixture.local_archive(db, generic_url, self.fixture.data, 'city-zip')
        db.execute("""INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'review',%s,0,'city-v7',now()-interval '8 hours')""",
          (generic_url, date(2020, 1, 1), generic_did))
        expected = 'city-v8:jan2022-native-geometry-v1'
        self.assertEqual(worker.asset_parser_version('city-zip', URL), expected)
        self.assertIn((URL, 'city-zip', geometry.PARENT), queue_plan.PRIORITY_SOURCE_REPAIRS)
        self.assertEqual(queue_plan.repair_candidates(db, 8)[0][0], URL)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Retained source must not fetch HTTP')):
            self.assertEqual(retained_exact_city_zip(db, URL, 'city-zip', expected), self.parent)
            self.assertTrue(worker.retained_reparse_during_host_cooldown(db, URL, 'city-zip'))
        db.execute('UPDATE ingestion_asset SET checked_at=now() WHERE url=%s', (URL,))
        self.assertEqual(queue_plan.repair_candidates(db, 8)[0][0], generic_url)
        db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours',processor_version=%s WHERE url=%s", (expected, URL))
        self.assertEqual(queue_plan.repair_candidates(db, 8)[0][0], URL)
        self.assertEqual(retained_exact_city_zip(db, URL, 'city-zip', expected), self.parent)
        db.execute("UPDATE ingestion_asset SET processor_version='city-v7',document_id=%s WHERE url=%s", (generic_did, URL))
        self.assertEqual(queue_plan.repair_candidates(db, 8)[0][0], generic_url)
        self.assertIsNone(retained_exact_city_zip(db, URL, 'city-zip', expected))
        db.execute('UPDATE ingestion_asset SET document_id=%s WHERE url=%s', (self.did, URL))
        db.execute('UPDATE source_document SET content=%s WHERE id=%s', (b'tampered retained parent', self.did))
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            retained_exact_city_zip(db, URL, 'city-zip', expected)
        # A tamper is routed to the ordinary error handler, never a network
        # substitution under the publisher cooldown.
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, URL, 'city-zip'))

    def test_whole_parent_recovers_53_rows_preserves_1202_and_rolls_back_after_copy(self):
        db = self.fixture.db
        # V49 generic parser is intact and naturally retains this child.
        with self.assertRaises(city_reports.CityZipPartialReview) as first:
            city_reports.publish_city_zip(db, self.parent, self.did, URL, geometry.DAY)
        self.assertEqual(first.exception.count, 1202)
        self.assertEqual(len(first.exception.failures), 1)
        self.assertEqual(first.exception.failures[0]['document_id'], geometry.CHILD)
        before_price = db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()
        before_class = db.execute('SELECT document_id,source_locator,xmin::text FROM regional_classification ORDER BY 1,2').fetchall()
        before_cp = db.execute('SELECT document_id,processor_version,step,records,xmin::text FROM ingestion_checkpoint ORDER BY 1,2,3').fetchall()
        self.assertEqual(len(before_price), 1202)
        insert = city_reports._bulk_insert
        def crash_after_copy(connection, table, rows):
            if table == 'regional_price':
                rows = list(rows)
                if rows and rows[0][0] == geometry.CHILD:
                    insert(connection, table, rows)
                    raise RuntimeError('controlled native-child failure after COPY')
            return insert(connection, table, rows)
        with patch.object(city_reports, '_bulk_insert', side_effect=crash_after_copy), self.assertRaisesRegex(RuntimeError, 'controlled native-child'):
            self.publish()
        for table in ('regional_price', 'regional_classification'):
            self.assertEqual(db.execute('SELECT count(*) FROM ' + table + ' WHERE document_id=%s', (geometry.CHILD,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='city-v8' AND step LIKE 'city-member:%%'", (self.did,)).fetchone()[0], 11)
        self.assertEqual(self.publish(), 1255)
        actual = dict((r[0], r) for r in db.execute('SELECT source_locator,' + ','.join(city_reports._PRICE_FIELDS) + ' FROM regional_price WHERE document_id=%s', (geometry.CHILD,)).fetchall())
        expected = json.loads(ORACLE.read_text())['rows']
        self.assertEqual(geometry.canonical_grid([actual[r[0]] for r in expected]), geometry.canonical_grid(expected))
        after_price = db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()
        after_class = db.execute('SELECT document_id,source_locator,xmin::text FROM regional_classification ORDER BY 1,2').fetchall()
        after_cp = db.execute('SELECT document_id,processor_version,step,records,xmin::text FROM ingestion_checkpoint ORDER BY 1,2,3').fetchall()
        self.assertTrue(set(before_price) <= set(after_price))
        self.assertTrue(set(before_class) <= set(after_class))
        self.assertTrue(set(before_cp) <= set(after_cp))
        self.assertEqual(db.execute('SELECT count(*) FROM published_regional_price').fetchone()[0], 1255)
        self.assertEqual(self.publish(), 1255)
        self.assertEqual(after_price, db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall())
        self.assertEqual(after_cp, db.execute('SELECT document_id,processor_version,step,records,xmin::text FROM ingestion_checkpoint ORDER BY 1,2,3').fetchall())
        self.assertEqual(self.fixture.count('city_insert_attempt'), 1255)

    def test_worker_process_asset_consumes_retained_parent_without_http_and_reruns_idempotently(self):
        db = self.fixture.db
        with self.assertRaises(city_reports.CityZipPartialReview):
            city_reports.publish_city_zip(db, self.parent, self.did, URL, geometry.DAY)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No source/provider request')):
            self.assertEqual(worker.process_asset(db, URL, 'city-zip', geometry.DAY), 1255)
            self.assertEqual(self.publish(), 1255)
        self.assertEqual(db.execute('SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s',
                                    (URL,)).fetchone(),
                         ('complete', 1255, 'city-v8:jan2022-native-geometry-v1'))
        self.assertEqual(db.execute('SELECT count(*) FROM published_regional_price').fetchone()[0], 1255)

    def test_wrong_asset_day_and_parent_pointer_fail_before_native_write(self):
        db = self.fixture.db
        for field, value in (('observed_on', date(2022, 1, 10)), ('document_id', self.fixture.did),
                             ('kind', 'daily'), ('status', 'archived')):
            with self.subTest(field=field):
                db.execute(f'UPDATE ingestion_asset SET {field}=%s WHERE url=%s', (value, URL))
                with self.assertRaises(ValueError):
                    self.publish()
                db.execute(f'UPDATE ingestion_asset SET {field}=%s WHERE url=%s',
                           ({'observed_on': geometry.DAY, 'document_id': self.did,
                             'kind': 'city-zip', 'status': 'review'}[field], URL))
        self.assertEqual(db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                                    (geometry.CHILD,)).fetchone()[0], 0)

    def test_child_lineage_and_checkpoint_tamper_fail_closed(self):
        db = self.fixture.db
        self.assertEqual(self.publish(), 1255)
        before = db.execute('SELECT count(*),min(xmin::text) FROM regional_price WHERE document_id=%s',
                            (geometry.CHILD,)).fetchone()
        db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{archive_entry}',to_jsonb('other.pdf'::text)) WHERE id=%s",
                   (geometry.CHILD,))
        with self.assertRaises(ValueError):
            self.publish()
        db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{archive_entry}',to_jsonb(%s::text)) WHERE id=%s",
                   (ENTRY, geometry.CHILD))
        step = db.execute("SELECT step FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND records=53",
                          (self.did, 'city-v8:jan2022-native-geometry-v1')).fetchone()[0]
        db.execute("UPDATE ingestion_checkpoint SET records=52 WHERE document_id=%s AND processor_version=%s AND step=%s",
                   (self.did, 'city-v8:jan2022-native-geometry-v1', step))
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(db.execute('SELECT count(*),min(xmin::text) FROM regional_price WHERE document_id=%s',
                                    (geometry.CHILD,)).fetchone(), before)

    def test_failed_current_version_resumes_exact_retained_bytes_after_copy_rollback(self):
        db = self.fixture.db
        with self.assertRaises(city_reports.CityZipPartialReview):
            city_reports.publish_city_zip(db, self.parent, self.did, URL, geometry.DAY)
        old_rows = db.execute('SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()
        db.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s", (URL,))
        insert = city_reports._bulk_insert
        def crash_after_copy(connection, table, rows):
            if table == 'regional_price':
                rows = list(rows)
                if rows and rows[0][0] == geometry.CHILD:
                    insert(connection, table, rows)
                    raise RuntimeError('controlled failure after exact child COPY')
            return insert(connection, table, rows)
        with patch.object(worker, 'fetch_asset', return_value=self.parent), \
             patch.object(city_reports, '_bulk_insert', side_effect=crash_after_copy), \
             self.assertRaisesRegex(RuntimeError, 'controlled failure after exact child COPY'):
            worker.process_asset(db, URL, 'city-zip', geometry.DAY)
        self.assertEqual(db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                                    (geometry.CHILD,)).fetchone()[0], 0)
        version = worker.asset_parser_version('city-zip', URL)
        # Match the outer worker error transition after process_asset raises.
        db.execute("""UPDATE ingestion_asset SET status='failed',attempts=attempts+1,
          checked_at=now(),error=%s,processor_version=%s WHERE url=%s""",
          ('RuntimeError: controlled failure after exact child COPY', version, URL))
        self.assertNotIn(URL, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (URL,))
        self.assertIn(URL, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertEqual(retained_exact_city_zip(db, URL, 'city-zip', version), self.parent)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, URL, 'city-zip'))
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Failed retry must not fetch HTTP')):
            self.assertEqual(worker.process_asset(db, URL, 'city-zip', geometry.DAY), 1255)
        self.assertEqual(db.execute('SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s',
                                    (URL,)).fetchone(), ('complete', 1255, version))
        self.assertIsNone(retained_exact_city_zip(db, URL, 'city-zip', version))
        self.assertNotIn(URL, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertTrue(set(old_rows) <= set(db.execute(
            'SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2').fetchall()))


if __name__ == '__main__':
    unittest.main()
