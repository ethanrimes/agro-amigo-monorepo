"""Private exact-original Corabastos OCR publication tests on owned TEMP PG."""

import io
import json
import os
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from psycopg.types.json import Jsonb
from psycopg.errors import CheckViolation

from . import city_reports, worker, queue_plan as queue
from . import city_corabastos_ocr_proof as proof
from . import city_corabastos_ocr_whole as whole
from . import city_exact_source_dispatch_v44_b as dispatch
from .test_city_publication import CityPublicationPostgresTests

FIXTURES = Path(__file__).resolve().parent / 'testdata/city_corabastos_20231019_ocr'


class ControlledRollback(Exception):
    pass


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit opt-in for isolated TEMP PostgreSQL')
class CorabastosOCRWholePostgresTests(unittest.TestCase):
    def setUp(self):
        dsn = urlparse(os.environ['DATABASE_URL'])
        host = parse_qs(dsn.query).get('host', [''])[0]
        self.assertTrue(host.startswith(('/tmp/agro-', '/private/tmp/agro-')))
        self.assertEqual(dsn.path, '/postgres')
        self.fixture = CityPublicationPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.assertEqual(self.db.info.host, host)
        self.assertIsNone(self.db.execute('SELECT inet_server_addr()').fetchone()[0])
        for table in ('document_alias', 'ingestion_asset', 'source_ocr_task', 'source_ocr_result',
                      'city_corabastos_ocr_adjudication'):
            self.db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.parent = (FIXTURES / (proof.PARENT + '.zip')).read_bytes()
        self.member, self.pdf = proof.checked_member(self.parent)
        self.images = {p: (FIXTURES / (image + '.png')).read_bytes()
                       for p, image in proof.IMAGES.items()}
        for page, body in self.images.items():
            self.assertEqual(sha256(body).hexdigest(), proof.IMAGES[page])
        self.cached = json.loads((FIXTURES / 'five_cached_results.json').read_text())
        self.assertEqual(len(self.cached), 5)
        self.enterContext(patch.object(worker, 'archive', side_effect=self.local_archive))
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,
           content,metadata) VALUES(%s,%s,'DANE',%s,'application/zip','original',
           %s,%s,%s)''',
          (proof.PARENT, proof.URL.rsplit('/', 1)[-1], proof.URL,
           proof.DAY.isoformat(), self.parent,
           Jsonb({'ingestion_kind': 'city-zip', 'retention': 'permanent',
                  'original_filename': proof.URL.rsplit('/', 1)[-1]})))
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,
           page_count,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/pdf','original',
           'Serie histórica completa',3,%s,%s)''',
          (proof.CHILD, proof.ENTRY, proof.URL, self.pdf,
           Jsonb({'ingestion_kind': 'city-pdf', 'retention': 'permanent',
                  'parents': [proof.PARENT], 'archive_entry': proof.ENTRY,
                  'original_filename': proof.ENTRY})))
        self.db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                        (proof.PARENT, proof.ENTRY, proof.CHILD))
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'review',%s,'city-v8',now()-interval '7 hours')''',
          (proof.URL, proof.DAY, proof.PARENT))
        for page, image in proof.IMAGES.items():
            self.db.execute('''INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,
               content,metadata)
              VALUES(%s,'rendered-source.png','DANE',%s,'image/png','extract',
               'Serie histórica completa',%s,%s)''',
              (image, proof.URL, self.images[page],
               Jsonb({'ingestion_kind': 'ocr-image', 'retention': 'permanent',
                      'parents': [proof.CHILD], 'archive_entry': 'rendered-source.png',
                      'original_filename': 'rendered-source.png'})))
            self.db.execute('''INSERT INTO source_ocr_task
              (document_id,source_locator,image_id,source_kind,source_page,
               status,error)
              VALUES(%s,%s,%s,'city-pdf',%s,'review',%s)''',
              (proof.CHILD, f'PDF page {page}', image, page, proof.OLD_ERRORS[page]))
        for result in self.cached:
            self.db.execute('''INSERT INTO source_ocr_result
              (image_id,version,reading,result) VALUES(%s,%s,%s,%s)''',
              (result['image_id'], result['version'], result['reading'],
               Jsonb(result['result'])))
        self.before_tasks = self.db.execute('''SELECT source_page,status,error,image_id
          FROM source_ocr_task WHERE document_id=%s ORDER BY source_page''',
          (proof.CHILD,)).fetchall()
        self.before_results = self.db.execute('''SELECT image_id,version,reading,result
          FROM source_ocr_result ORDER BY image_id,version,reading''').fetchall()
        original_mapping = dict(worker.URL_SOURCE_REPAIR_VERSIONS)
        worker.URL_SOURCE_REPAIR_VERSIONS[proof.URL] = (
            'city-zip', ':corabastos-oct2023-ocr-whole-v1')
        self.addCleanup(lambda: (worker.URL_SOURCE_REPAIR_VERSIONS.clear(),
                                 worker.URL_SOURCE_REPAIR_VERSIONS.update(original_mapping)))

    @staticmethod
    def local_archive(db, url, data, kind, day=None, *, filename=None,
                      parents=None, **_):
        did = sha256(data).hexdigest()
        suffix = 'pdf' if kind == 'city-pdf' else 'png' if kind == 'ocr-image' else 'zip'
        metadata = {'ingestion_kind': kind, 'retention': 'permanent',
                    'original_filename': filename or url.rsplit('/', 1)[-1]}
        if parents:
            metadata.update({'parents': parents, 'archive_entry': filename})
        db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,
           content,metadata)
          VALUES(%s,%s,'DANE',%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
          (did, filename or kind, url,
           {'pdf': 'application/pdf', 'png': 'image/png',
            'zip': 'application/zip'}[suffix],
           'extract' if kind == 'ocr-image' else 'original',
           str(day or 'Serie histórica completa'), data, Jsonb(metadata)))
        return did

    def target_counts(self):
        return tuple(self.db.execute(f'SELECT count(*) FROM {table} WHERE document_id=%s',
                                     (proof.CHILD,)).fetchone()[0]
                     for table in ('regional_price', 'regional_classification',
                                   'city_corabastos_ocr_adjudication'))

    def checkpoint(self):
        return self.db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (proof.PARENT, proof.VERSION, proof.MEMBER_STEP)).fetchone()

    def assert_history_unchanged(self):
        self.assertEqual(self.db.execute('''SELECT source_page,status,error,image_id
          FROM source_ocr_task WHERE document_id=%s ORDER BY source_page''',
          (proof.CHILD,)).fetchall(), self.before_tasks)
        self.assertEqual(self.db.execute('''SELECT image_id,version,reading,result
          FROM source_ocr_result ORDER BY image_id,version,reading''').fetchall(),
          self.before_results)

    def test_exact_196_atomic_publication_and_truthful_local_attribution(self):
        result = whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(result['rows'], 196)
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.assertEqual(self.checkpoint(), (196,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM published_regional_price
          WHERE document_id=%s''', (proof.CHILD,)).fetchone(), (196,))
        self.assertEqual(self.db.execute('''SELECT provider_result_hashes->'p2_r1',
          evidence_method,evidence_document_id,records
          FROM city_corabastos_ocr_adjudication WHERE document_id=%s''',
          (proof.CHILD,)).fetchone(),
          (None, 'local_retained_source_geometry_plus_five_cached_provider_readings',
           proof.EVIDENCE_SHA, 196))
        self.assertEqual(self.db.execute('''SELECT media_type,kind,octet_length(content)
          FROM source_document WHERE id=%s''', (proof.EVIDENCE_SHA,)).fetchone(),
          ('application/zip', 'extract', 3519183))
        self.assertEqual(self.db.execute('''SELECT publisher,media_type,kind,
          metadata->>'ingestion_kind' FROM source_document WHERE id=%s''',
          (proof.CHILD,)).fetchone(),
          ('DANE', 'application/pdf', 'original', 'city-pdf'))
        self.assertEqual(self.db.execute('''SELECT publisher,metadata->>'ingestion_kind'
          FROM source_document WHERE id=%s''',
          (proof.EVIDENCE_SHA,)).fetchone(),
          ('AgroAmigo source review', 'city-ocr-local-geometry-proof'))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_price
          WHERE document_id=%s''', (proof.EVIDENCE_SHA,)).fetchone(), (0,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM published_regional_price
          WHERE document_id=%s''', (proof.EVIDENCE_SHA,)).fetchone(), (0,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM document_alias
          WHERE document_id=%s''', (proof.EVIDENCE_SHA,)).fetchone(), (0,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM source_document
          WHERE id=%s AND kind='original' ''', (proof.EVIDENCE_SHA,)).fetchone(), (0,))
        self.assert_history_unchanged()
        rows = self.db.execute('''SELECT source_locator,observed_on,market_name,
          product_name,presentation,quantity,source_unit,round,min_price,max_price,
          source_page FROM regional_price WHERE document_id=%s ORDER BY source_locator''',
          (proof.CHILD,)).fetchall()
        self.assertEqual(len(rows), 196)
        self.assertEqual([sum(r[0].startswith(f'PDF page {p},') for r in rows)
                          for p in (1, 2, 3)], [86, 78, 32])
        # These are printed source cells in the independent page-2 local grid,
        # not a second expected vector generated by the same parser.
        uva = [r for r in rows if r[3] == 'Uva red globe nacional'
               and r[6] == 'Kilogramo' and r[4] == 'Caja de icopor']
        self.assertEqual([(r[7], r[8], r[9]) for r in uva],
                         [(1, 74000, 75000), (2, 73000, 75000)])

    def test_after_copy_crash_rolls_back_rows_proof_and_checkpoint_then_resumes(self):
        real = city_reports._bulk_insert
        def crash(db, table, values):
            real(db, table, values)
            if table == 'regional_price':
                raise RuntimeError('controlled after COPY crash')
        with patch.object(city_reports, '_bulk_insert', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'after COPY'):
                whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(self.target_counts(), (0, 0, 0))
        self.assertIsNone(self.checkpoint())
        self.assertIsNone(self.db.execute('SELECT id FROM source_document WHERE id=%s',
                                          (proof.EVIDENCE_SHA,)).fetchone())
        self.assert_history_unchanged()
        self.assertEqual(whole.publish_exact_child(self.db, proof.URL,
                                                   self.parent, proof.PARENT)['rows'], 196)
        self.assertEqual(self.target_counts(), (196, 196, 1))

    def test_idempotence_and_changed_stored_tuple_fail_closed(self):
        whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        before = self.db.execute('''SELECT source_locator,xmin::text FROM regional_price
          WHERE document_id=%s ORDER BY source_locator''', (proof.CHILD,)).fetchall()
        self.assertEqual(whole.publish_exact_child(self.db, proof.URL,
                                                   self.parent, proof.PARENT)['rows'], 196)
        self.assertEqual(before, self.db.execute('''SELECT source_locator,xmin::text
          FROM regional_price WHERE document_id=%s ORDER BY source_locator''',
          (proof.CHILD,)).fetchall())
        self.db.execute('''UPDATE regional_price SET product_name=product_name||' altered'
          WHERE document_id=%s AND source_locator=(SELECT min(source_locator)
          FROM regional_price WHERE document_id=%s)''', (proof.CHILD, proof.CHILD))
        with self.assertRaises(ValueError):
            whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.assertEqual(self.checkpoint(), (196,))

    def test_checkpoint_cannot_recreate_missing_append_only_evidence(self):
        whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.db.execute('''DELETE FROM city_corabastos_ocr_adjudication
          WHERE document_id=%s''', (proof.CHILD,))
        with self.assertRaises(ValueError):
            whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(self.target_counts(), (196, 196, 0))
        self.assertEqual(self.checkpoint(), (196,))

    def test_source_drift_and_extra_provider_result_rejected_without_rows(self):
        cases = [
            ("UPDATE ingestion_asset SET observed_on='2023-10-20' WHERE url=%s", (proof.URL,)),
            ("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s", (proof.CHILD,)),
            ("UPDATE source_archive_member SET document_id=%s WHERE archive_id=%s AND entry_name=%s",
             (proof.PARENT, proof.PARENT, proof.ENTRY)),
            ("UPDATE source_document SET content='bad'::bytea WHERE id=%s", (proof.IMAGES[2],)),
            ("UPDATE source_ocr_task SET error='changed' WHERE document_id=%s AND source_page=2", (proof.CHILD,)),
            ("UPDATE source_ocr_result SET result=jsonb_set(result,'{review_notes}',\
              '[\"uncertain monetary cell\"]'::jsonb) WHERE image_id=%s AND reading=0",
             (proof.IMAGES[2],)),
            ("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES(%s,'gemini-image-ocr-v2',1,'{}'::jsonb)",
             (proof.IMAGES[2],)),
        ]
        for sql, params in cases:
            with self.subTest(sql=sql):
                try:
                    with self.db.transaction():
                        self.db.execute(sql, params)
                        with self.assertRaises((ValueError, TypeError, KeyError)):
                            whole.publish_exact_child(self.db, proof.URL,
                                                      self.parent, proof.PARENT)
                        self.assertEqual(self.target_counts(), (0, 0, 0))
                        self.assertIsNone(self.checkpoint())
                        raise ControlledRollback()
                except ControlledRollback:
                    pass
        self.assert_history_unchanged()

    def test_adjudication_insert_failure_rolls_back_complete_child(self):
        self.db.execute('''CREATE FUNCTION pg_temp.reject_corabastos_adjudication()
          RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'controlled adjudication storage failure';
          END $$''')
        self.db.execute('''CREATE TRIGGER reject_insert BEFORE INSERT
          ON city_corabastos_ocr_adjudication FOR EACH ROW
          EXECUTE FUNCTION pg_temp.reject_corabastos_adjudication()''')
        with self.assertRaises(Exception):
            whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(self.target_counts(), (0, 0, 0))
        self.assertIsNone(self.checkpoint())
        self.assertIsNone(self.db.execute('SELECT id FROM source_document WHERE id=%s',
                                          (proof.EVIDENCE_SHA,)).fetchone())

    def test_same_version_generic_loop_handles_all_27_distinct_siblings(self):
        # Give every unrelated member a controlled ordinary review, proving
        # iteration and parent partial status without publishing guessed rows.
        with patch.object(city_reports, 'parse_archived_city_pdf',
                          side_effect=ValueError('controlled ordinary sibling review')):
            with self.assertRaises(city_reports.CityZipPartialReview) as raised:
                whole.publish_exact_parent(self.db, proof.URL, self.parent,
                                           proof.PARENT)
        self.assertEqual(raised.exception.count, 196)
        self.assertEqual(len(raised.exception.failures), 27)
        self.assertIn(proof.OTHER_CORABASTOS,
                      [r['filename'] for r in raised.exception.failures])
        self.assertNotIn(proof.ENTRY,
                         [r['filename'] for r in raised.exception.failures])
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.assertEqual(self.checkpoint(), (196,))
        self.assert_history_unchanged()

    def test_retained_route_dispatch_and_exact_queue_pin(self):
        self.assertEqual(worker.asset_parser_version('city-zip', proof.URL),
                         proof.VERSION)
        self.assertIn((proof.URL, 'city-zip', proof.PARENT),
                      queue.PRIORITY_SOURCE_REPAIRS)
        self.assertIsNone(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'daily', proof.VERSION))
        self.assertEqual(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'city-zip', proof.VERSION), self.parent)
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(
            self.db, proof.URL + '?different', self.parent, proof.PARENT))
        with patch.object(city_reports, 'parse_archived_city_pdf',
                          side_effect=ValueError('controlled ordinary sibling review')):
            with self.assertRaises(city_reports.CityZipPartialReview) as raised:
                dispatch.maybe_publish_exact_city_zip(
                    self.db, proof.URL, self.parent, proof.PARENT)
        self.assertEqual(raised.exception.count, 196)
        self.assertEqual(len(raised.exception.failures), 27)
        self.db.execute('''UPDATE ingestion_asset SET processor_version=%s,
          records=196,status='review' WHERE url=%s''',
          (proof.VERSION, proof.URL))
        self.assertEqual(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'city-zip', proof.VERSION), self.parent)
        self.assert_history_unchanged()

    def test_pending_old_asset_version_requires_committed_child_and_resumes_siblings(self):
        self.db.execute('''UPDATE ingestion_asset SET status='pending',
          processor_version='city-v8',checked_at=now()-interval '7 hours'
          WHERE url=%s''', (proof.URL,))
        with self.assertRaisesRegex(ValueError, 'pending child checkpoint absent'):
            dispatch.retained_exact_city_zip(
                self.db, proof.URL, 'city-zip', proof.VERSION)
        self.assertNotIn((proof.URL, 'city-zip', proof.DAY),
                         queue.repair_candidates(self.db, limit=8))
        with self.assertRaisesRegex(ValueError, 'first publication'):
            whole.publish_exact_child(self.db, proof.URL, self.parent,
                                      proof.PARENT)
        self.assertEqual(self.target_counts(), (0, 0, 0))
        self.db.execute("UPDATE ingestion_asset SET status='review' WHERE url=%s",
                        (proof.URL,))
        self.assertEqual(whole.publish_exact_child(
            self.db, proof.URL, self.parent, proof.PARENT)['rows'], 196)
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.db.execute('''UPDATE ingestion_asset SET status='pending',
          processor_version='city-v8',checked_at=now()-interval '7 hours'
          WHERE url=%s''', (proof.URL,))
        self.assertIn((proof.URL, 'city-zip', proof.DAY),
                      queue.repair_candidates(self.db, limit=8))
        self.assertEqual(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'city-zip', proof.VERSION), self.parent)
        total = dispatch.maybe_publish_exact_city_zip(
            self.db, proof.URL, self.parent, proof.PARENT)
        self.assertGreater(total, 196)
        self.assertEqual(self.db.execute('''SELECT count(*),sum(records)
          FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s
          AND step LIKE 'city-member:%%' ''',
          (proof.PARENT, proof.VERSION)).fetchone(), (28, total))
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.assert_history_unchanged()

    def test_pending_exact_proof_or_adjudication_drift_never_fetches(self):
        whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        self.db.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s",
                        (proof.URL,))
        for sql, params in (
            ("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s",
             (proof.EVIDENCE_SHA,)),
            ("UPDATE regional_price SET min_price=min_price+1 WHERE document_id=%s AND source_locator=(SELECT min(source_locator) FROM regional_price WHERE document_id=%s AND min_price<max_price)",
             (proof.CHILD, proof.CHILD)),
        ):
            with self.subTest(sql=sql):
                try:
                    with self.db.transaction():
                        self.db.execute(sql, params)
                        with self.assertRaises(ValueError):
                            dispatch.retained_exact_city_zip(
                                self.db, proof.URL, 'city-zip', proof.VERSION)
                        raise ControlledRollback()
                except ControlledRollback:
                    pass
        self.assertEqual(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'city-zip', proof.VERSION), self.parent)

    def test_adjudication_schema_rejects_wrong_prior_and_full_vector_hash(self):
        whole.publish_exact_child(self.db, proof.URL, self.parent, proof.PARENT)
        valid = self.db.execute('''SELECT archive_id,entry_name,evidence_document_id,
          evidence_method,image_ids,provider_result_hashes,prior_tasks,
          full17_sha256,records FROM city_corabastos_ocr_adjudication
          WHERE document_id=%s''', (proof.CHILD,)).fetchone()
        for field, replacement in (('prior_tasks', []),
                                   ('full17_sha256', '0' * 64)):
            changed = list(valid)
            changed[6 if field == 'prior_tasks' else 7] = replacement
            try:
                with self.db.transaction():
                    self.db.execute('DELETE FROM city_corabastos_ocr_adjudication')
                    changed[5] = Jsonb(changed[5])
                    changed[6] = Jsonb(changed[6])
                    with self.assertRaises(CheckViolation) as rejected:
                        self.db.execute('''INSERT INTO city_corabastos_ocr_adjudication
                          (document_id,policy_version,archive_id,entry_name,
                           evidence_document_id,evidence_method,image_ids,
                           provider_result_hashes,prior_tasks,full17_sha256,records)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                          (proof.CHILD, proof.VERSION, *changed))
                    self.assertEqual(rejected.exception.sqlstate, '23514')
                    raise ControlledRollback()
            except ControlledRollback:
                pass
            self.assertEqual(self.db.execute('''SELECT count(*) FROM
              city_corabastos_ocr_adjudication WHERE document_id=%s''',
              (proof.CHILD,)).fetchone(), (1,))
            self.assertEqual(self.db.execute('''SELECT evidence_document_id,
              prior_tasks,full17_sha256 FROM city_corabastos_ocr_adjudication
              WHERE document_id=%s''', (proof.CHILD,)).fetchone(),
              (proof.EVIDENCE_SHA, valid[6], proof.ROWS_SHA))
            self.assertEqual(self.db.execute('''SELECT metadata->>'ingestion_kind'
              FROM source_document WHERE id=%s''',
              (proof.EVIDENCE_SHA,)).fetchone(),
              ('city-ocr-local-geometry-proof',))
        self.assert_history_unchanged()

    def test_actual_27_native_siblings_complete_and_cold_replay_shortcut(self):
        total = whole.publish_exact_parent(self.db, proof.URL,
                                           self.parent, proof.PARENT)
        self.assertGreater(total, 196)
        self.assertEqual(self.target_counts(), (196, 196, 1))
        self.assertEqual(self.checkpoint(), (196,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM source_archive_member
          WHERE archive_id=%s''', (proof.PARENT,)).fetchone(), (28,))
        cp_count, cp_sum = self.db.execute('''SELECT count(*),sum(records)
          FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s
          AND step LIKE 'city-member:%%' ''',
          (proof.PARENT, proof.VERSION)).fetchone()
        self.assertEqual(cp_count, 28)
        self.assertEqual(cp_sum, total)
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_price r
          JOIN source_archive_member m ON m.document_id=r.document_id
          WHERE m.archive_id=%s''', (proof.PARENT,)).fetchone(), (total,))
        with zipfile.ZipFile(io.BytesIO(self.parent)) as archive:
            sibling = sha256(archive.read(proof.OTHER_CORABASTOS)).hexdigest()
        self.assertEqual(sibling, proof.OTHER_CORABASTOS_SHA)
        self.assertGreater(self.db.execute('''SELECT count(*) FROM regional_price
          WHERE document_id=%s''', (sibling,)).fetchone()[0], 0)
        before = self.db.execute('''SELECT document_id,source_locator,xmin::text
          FROM regional_price ORDER BY document_id,source_locator''').fetchall()
        self.db.execute('''UPDATE ingestion_asset SET status='complete',
          records=%s,processor_version=%s WHERE url=%s''',
          (total, proof.VERSION, proof.URL))
        self.assertIsNone(dispatch.retained_exact_city_zip(
            self.db, proof.URL, 'city-zip', proof.VERSION))
        self.assertEqual(before, self.db.execute('''SELECT document_id,source_locator,xmin::text
          FROM regional_price ORDER BY document_id,source_locator''').fetchall())
        self.assert_history_unchanged()
