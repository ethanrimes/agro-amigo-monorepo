"""Fresh DANE revisions retain old originals while prioritizing current bytes."""
import hashlib
import io
import os
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from . import city_reports, current_dane_sources as current, queue_plan, worker
from . import test_city_publication as publication


ZIP = Path(__file__).resolve().parent / 'testdata/city_current_oct2026.zip'
URL = 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-06oct2026.zip'
DAY = date(2026, 10, 6)
SHA = '2abd8f4fb6e30bd091e263ac9b165be5d343ad67633108ec668da767991895f1'


class CurrentDaneSourceTests(unittest.TestCase):
    def test_exact_new_original_and_all_printed_native_dates(self):
        body = ZIP.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), SHA)
        total = 0
        prior_day = {}
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = [m for m in archive.infolist() if m.filename.endswith('.pdf')]
            self.assertEqual(len(members), 29)
            for member in members:
                rows = list(city_reports.parse_city_pdf(archive.read(member), DAY))
                self.assertEqual(len(rows), len({row[0] for row in rows}))
                total += len(rows)
                days = {row[1] for row in rows}
                self.assertEqual(len(days), 1)
                if days == {DAY - timedelta(days=1)}:
                    prior_day[member.filename] = len(rows)
                else:
                    self.assertEqual(days, {DAY})
        self.assertEqual(total, 2262)
        self.assertEqual(prior_day, {
            'Chiquinquirá (Boyacá)-05-10-2026.pdf': 58,
            'Marinilla (Antioquia)-05-10-2026.pdf': 17,
            'San Gil (Santander)-05-10-2026.pdf': 56,
        })

    def test_recent_window_uses_bogota_day_and_exact_dane_host(self):
        midnight_utc = datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(midnight_utc.astimezone(ZoneInfo('America/Bogota')).date(), DAY)
        self.assertTrue(current.is_recent_dane(URL, 'city-zip', DAY, DAY))
        for kind in current.KINDS:
            for delta in range(4):
                self.assertTrue(current.is_recent_dane(URL, kind, DAY - timedelta(days=delta), DAY))
            self.assertFalse(current.is_recent_dane(URL, kind, DAY - timedelta(days=4), DAY))
            self.assertFalse(current.is_recent_dane(URL, kind, DAY + timedelta(days=1), DAY))
        for url in ('https://www.dane.gov.co.evil/files/operaciones/SIPSA/x.zip',
                    URL + '?other', URL + '#old', 'http://' + URL.removeprefix('https://')):
            self.assertFalse(current.is_recent_dane(url, 'city-zip', DAY, DAY))
        self.assertFalse(current.is_recent_dane(URL, 'dane-weekly-pdf', DAY, DAY))

    def test_daily_byte_policy_covers_mutable_current_workbooks_not_old_backlog(self):
        prefix = 'https://www.dane.gov.co/files/operaciones/SIPSA/'
        cases = (
            (prefix + 'anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx',
             'inputs', None, True),
            (prefix + 'anex-SIPSALeche-SerieHistoricaPrecios-2025.xlsx',
             'milk', None, True),
            (prefix + 'anex-SIPSALeche-SerieHistoricaPrecios-2025.xlsx?download=1',
             'milk', None, True),
            (prefix + 'anex-SIPSAMensual-ago2026.xlsx',
             'monthly-annex', DAY - timedelta(days=66), True),
            (prefix + 'anex-SIPSASemanal-19sep25sep-2026.xlsx',
             'dane-weekly-xlsx', DAY - timedelta(days=11), True),
            (prefix + 'anex-SIPSAInsumos-SeriesHistoricasDep-2018-2019.xlsx',
             'inputs', None, False),
            (prefix + 'bol-SIPSAabastecimiento-mar2020.pdf',
             'supply', date(2020, 3, 1), False),
            (prefix + 'index-2026.html', 'supply-index', DAY, False),
            ('https://www.dane.gov.co.evil/files/operaciones/SIPSA/current-2026.xlsx',
             'inputs', DAY, False),
        )
        for url, kind, observed, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(current.needs_daily_bytes(url, kind, observed, DAY), expected)

    def test_recent_byte_check_sends_no_stale_validators_and_rejects_304(self):
        db = __import__('unittest.mock', fromlist=['MagicMock']).MagicMock()
        db.execute.return_value.fetchone.return_value = ('"old"', 'Mon, 05 Oct 2026 00:00:00 GMT', 'complete', 'old-sha')
        response = SimpleNamespace(status_code=200, headers={'ETag': '"new"'},
                                   content=b'changed', raise_for_status=lambda: None, close=Mock())
        with patch.object(worker, '_get', return_value=response) as get:
            self.assertEqual(worker.fetch_asset(db, URL, require_bytes=True), b'changed')
        response.close.assert_called_once_with()
        self.assertEqual(get.call_args.kwargs['headers'],
                         {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        not_modified = SimpleNamespace(status_code=304, close=Mock())
        with patch.object(worker, '_get', return_value=not_modified):
            with self.assertRaisesRegex(ValueError, '304 to unconditional'):
                worker.fetch_asset(db, URL, require_bytes=True)
        not_modified.close.assert_called_once_with()

    def test_early_current_asset_precedes_discovery_and_old_fresh_keeps_slot(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        other = URL.replace('bol-SIPSADiario-regionales-06oct2026.zip',
                            'anex-SIPSADiario-01oct2026.xlsx')
        events = []
        with (patch.object(worker, 'connect') as connect,
              patch.object(worker, 'today', return_value=DAY),
              patch.object(worker, 'process_asset', side_effect=lambda db, url, kind, day:
                           events.append(('asset', url, worker.DANE_DAILY_BYTES.get())) or 1),
              patch.object(worker, 'discover', side_effect=lambda db: events.append(('discover', None)) or []),
              patch('pipelines.ingestion.official_sources.discover_roots',
                    side_effect=lambda db: events.append(('roots', None))),
              patch('pipelines.ingestion.queue_plan.current_dane_candidates',
                    side_effect=[[(URL, 'city-zip', DAY)], []]),
              patch('pipelines.ingestion.queue_plan.daily_candidates',
                    return_value=[(other, 'daily', DAY - timedelta(days=5))]),
              patch('pipelines.ingestion.retained_replays.drain', return_value={}),
              patch('pipelines.ingestion.ocr.drain', return_value={}),
              patch.object(worker, 'refresh_catalog', return_value={}),
              patch('pipelines.ingestion.label_normalization.drain', return_value={
                  'available': True, 'deferred': False, 'scanned': 0,
                  'changed': 0, 'cycle_complete': True, 'version': 'test'})):
            connect.return_value.__enter__.return_value = db
            result = worker.run('daily', limit=2)
        self.assertEqual(events, [('asset', URL, False), ('discover', None), ('roots', None),
                                  ('asset', other, True)])
        self.assertEqual(result['assets'], 2)
        self.assertEqual(result['errors'], [])

    def test_existing_host_cooldown_defers_current_without_starving_other_host(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        other = 'https://example.org/old-price.xls'
        events = []
        retry_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        class Cooldowns:
            def __init__(self, *_args, **_kwargs):
                pass

            def blocked(self, url):
                return retry_at if url == URL else None

        with (patch.object(worker, 'connect') as connect,
              patch.object(worker, 'today', return_value=DAY),
              patch.object(worker, 'HostCooldowns', Cooldowns),
              patch.object(worker, 'retained_reparse_during_host_cooldown', return_value=False),
              patch.object(worker, 'process_asset', side_effect=lambda db, url, kind, day:
                           events.append(url) or 1),
              patch.object(worker, 'discover', return_value=[]),
              patch('pipelines.ingestion.official_sources.discover_roots'),
              patch('pipelines.ingestion.queue_plan.current_dane_candidates',
                    side_effect=[[(URL, 'city-zip', DAY)], []]),
              patch('pipelines.ingestion.queue_plan.daily_candidates',
                    return_value=[(other, 'daily', DAY - timedelta(days=5))]),
              patch('pipelines.ingestion.retained_replays.drain', return_value={}),
              patch('pipelines.ingestion.ocr.drain', return_value={}),
              patch.object(worker, 'refresh_catalog', return_value={}),
              patch('pipelines.ingestion.label_normalization.drain', return_value={
                  'available': True, 'deferred': False, 'scanned': 0,
                  'changed': 0, 'cycle_complete': True, 'version': 'test'})):
            connect.return_value.__enter__.return_value = db
            result = worker.run('daily', limit=2)
        self.assertEqual(events, [other])
        self.assertEqual(result['assets'], 1)
        self.assertEqual(result['deferred_hosts']['www.dane.gov.co']['count'], 1)


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit private PostgreSQL opt-in')
class CurrentDanePostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture = publication.CityPublicationPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.db.execute('CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL)')
        self.enterContext(patch.object(worker, 'archive', side_effect=self.local_archive))
        self.enterContext(patch.object(worker, 'today', return_value=DAY))
        self.body = ZIP.read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), SHA)

    @staticmethod
    def local_archive(db, url, data, kind, day=None, *, filename=None, parents=None, **kwargs):
        did = hashlib.sha256(data).hexdigest()
        metadata = {'ingestion_kind': kind, 'retention': 'permanent',
                    'original_filename': filename or url.rsplit('/', 1)[-1]}
        if parents:
            metadata.update({'parents': parents, 'archive_entry': filename})
        db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s) ON CONFLICT DO NOTHING''',
          (did, filename or kind, url,
           'application/zip' if kind == 'city-zip' else 'application/pdf',
           str(day or ''), data, Jsonb(metadata)))
        return did

    def test_due_order_and_hourly_rotation_preserve_historical_lane(self):
        old = URL.replace('06oct2026', '05oct2026')
        annex = 'https://www.dane.gov.co/files/operaciones/SIPSA/mayoristas_octubre_6_2026.xlsx'
        for url, kind, when, age in ((URL, 'city-zip', DAY, 3),
                                     (annex, 'daily', DAY, 2),
                                     (old, 'city-zip', DAY - timedelta(days=1), 1)):
            self.db.execute('''INSERT INTO ingestion_asset
              (url,kind,observed_on,status,checked_at) VALUES(%s,%s,%s,'complete',now()-(%s*interval '1 hour'))''',
              (url, kind, when, age))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=2),
                         [(URL, 'city-zip', DAY), (annex, 'daily', DAY)])
        self.db.execute('UPDATE ingestion_asset SET checked_at=now() WHERE url=%s', (URL,))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=2),
                         [(annex, 'daily', DAY), (old, 'city-zip', DAY - timedelta(days=1))])

    def test_latest_city_gets_one_slot_among_twelve_and_other_slot_rotates(self):
        city = URL
        annexes = [URL.replace('bol-SIPSADiario-regionales-06oct2026.zip',
                               f'anex-SIPSADiario-{i:02d}oct2026.xlsx')
                   for i in range(1, 12)]
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,checked_at) VALUES
          (%s,'city-zip',%s,'complete',now()-interval '104 minutes')''', (city, DAY))
        for index, annex in enumerate(annexes):
            self.db.execute('''INSERT INTO ingestion_asset
              (url,kind,observed_on,status,checked_at) VALUES
              (%s,'daily',%s,'complete',now()-(%s*interval '1 minute'))''',
              (annex, DAY - timedelta(days=index % 3), 200 - index))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=2),
                         [(city, 'city-zip', DAY),
                          (annexes[0], 'daily', DAY)])
        self.db.execute('UPDATE ingestion_asset SET checked_at=now() WHERE url=%s', (city,))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=2),
                         [(annexes[0], 'daily', DAY),
                          (annexes[1], 'daily', DAY - timedelta(days=1))])
        self.assertEqual(queue_plan.current_dane_candidates(
            self.db, DAY, exclude_urls=[city, annexes[0]], limit=1),
            [(annexes[1], 'daily', DAY - timedelta(days=1))])
        exhausted = URL.replace('06oct2026', '07oct2026')
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,attempts,checked_at) VALUES
          (%s,'city-zip',%s,'failed',4,now()-interval '3 hours')''',
          (exhausted, DAY))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=1),
                         [(annexes[0], 'daily', DAY)])

    def seed_synthetic_old(self):
        synthetic = publication.bundle([('synthetic-old.pdf', publication.native_pdf('Synthetic old'))])
        old_did = self.local_archive(self.db, URL, synthetic, 'city-zip', DAY)
        old_count = city_reports.publish_city_zip(self.db, synthetic, old_did, URL, DAY)
        self.assertGreater(old_count, 0)
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'complete',%s,%s,%s,now()-interval '2 hours')''',
          (URL, DAY, old_did, old_count, worker.asset_parser_version('city-zip', URL)))
        old_rows = self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (old_did,)).fetchall()
        self.assertEqual(len(old_rows), old_count)
        return old_did, old_rows

    def test_newest_awaiting_ocr_city_reserves_slot_and_changed_native_recovers(self):
        old_did, old_rows = self.seed_synthetic_old()
        self.db.execute("UPDATE ingestion_asset SET status='awaiting-ocr',checked_at=now()-interval '104 minutes' WHERE url=%s", (URL,))
        older_city = URL.replace('06oct2026', '05oct2026')
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,checked_at) VALUES
          (%s,'city-zip',%s,'complete',now()-interval '200 minutes')''',
          (older_city, DAY - timedelta(days=1)))
        annexes = [URL.replace('bol-SIPSADiario-regionales-06oct2026.zip',
                               f'anex-SIPSADiario-{i:02d}oct2026.xlsx')
                   for i in range(1, 11)]
        for index, annex in enumerate(annexes):
            self.db.execute('''INSERT INTO ingestion_asset
              (url,kind,observed_on,status,checked_at) VALUES
              (%s,'daily',%s,'complete',now()-(%s*interval '1 minute'))''',
              (annex, DAY - timedelta(days=index % 3), 190 - index))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_asset').fetchone(), (12,))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=2),
                         [(URL, 'city-zip', DAY),
                          (older_city, 'city-zip', DAY - timedelta(days=1))])
        previous_tasks = self.db.execute('''SELECT url,status,checked_at,xmin::text FROM ingestion_asset
          WHERE url<>%s ORDER BY url''', (URL,)).fetchall()
        response = SimpleNamespace(status_code=200, headers={'ETag': '"new"'},
                                   content=self.body, raise_for_status=lambda: None)
        with patch.object(worker, '_get', return_value=response) as get:
            self.assertEqual(worker.process_asset(self.db, URL, 'city-zip', DAY), 2262)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs['headers'],
                         {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        self.assertEqual(self.db.execute('''SELECT document_id,status,records FROM ingestion_asset
          WHERE url=%s''', (URL,)).fetchone(), (SHA, 'complete', 2262))
        self.assertEqual(self.db.execute('''SELECT url,status,checked_at,xmin::text FROM ingestion_asset
          WHERE url<>%s ORDER BY url''', (URL,)).fetchall(), previous_tasks)
        self.assertEqual(self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (old_did,)).fetchall(), old_rows)

    def test_changed_parent_is_append_only_and_unchanged_rerun(self):
        old_did, old_rows = self.seed_synthetic_old()
        response = SimpleNamespace(status_code=200, headers={'ETag': '"new"'},
                                   content=self.body, raise_for_status=lambda: None)
        with patch.object(worker, '_get', return_value=response) as get:
            self.assertEqual(worker.process_asset(self.db, URL, 'city-zip', DAY), 2262)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.kwargs['headers'],
                             {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        self.assertEqual(self.db.execute('''SELECT document_id,status,records FROM ingestion_asset
          WHERE url=%s''', (URL,)).fetchone(), (SHA, 'complete', 2262))
        self.assertEqual(self.db.execute('''SELECT count(*),sum(records) FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%' ''',
          (SHA, worker.asset_parser_version('city-zip', URL))).fetchone(), (29, 2262))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_price WHERE document_id
          IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)''',
          (SHA,)).fetchone(), (2262,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_classification WHERE document_id
          IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)''',
          (SHA,)).fetchone(), (2262,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_document WHERE id=%s',
                                         (old_did,)).fetchone(), (1,))
        self.assertEqual(self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (old_did,)).fetchall(), old_rows)
        with patch.object(worker, '_get', return_value=response):
            self.assertEqual(worker.process_asset(self.db, URL, 'city-zip', DAY), 0)
        self.assertEqual(self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (old_did,)).fetchall(), old_rows)
        new_rows = self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (SHA,)).fetchall()
        self.db.execute("UPDATE ingestion_asset SET status='pending',records=0 WHERE url=%s",
                        (URL,))
        self.assertEqual(current.retained_unfinished(self.db, URL, 'city-zip', DAY,
                         worker.asset_parser_version('city-zip', URL), DAY), self.body)
        with patch.object(worker, '_get', side_effect=AssertionError('HTTP before parent finalization')):
            self.assertEqual(worker.process_asset(self.db, URL, 'city-zip', DAY), 2262)
        self.assertEqual(self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (SHA,)).fetchall(), new_rows)

    def test_failed_new_revision_resumes_retained_bytes_before_http_and_checkpoint_is_atomic(self):
        old_did, old_rows = self.seed_synthetic_old()
        insert = city_reports._bulk_insert
        failure_once = {'raised': False}

        def crash_after_copy(db, table, rows):
            rows = list(rows)
            if table == 'regional_price' and rows and not failure_once['raised']:
                failure_once['raised'] = True
                insert(db, table, rows)
                raise RuntimeError('controlled current revision crash after COPY')
            return insert(db, table, rows)

        response = SimpleNamespace(status_code=200, headers={'ETag': '"new"'},
                                   content=self.body, raise_for_status=lambda: None)
        with patch.object(worker, '_get', return_value=response), \
                patch.object(city_reports, '_bulk_insert', side_effect=crash_after_copy):
            with self.assertRaisesRegex(RuntimeError, 'after COPY'):
                worker.process_asset(self.db, URL, 'city-zip', DAY)
        self.assertEqual(self.db.execute('SELECT document_id FROM ingestion_asset WHERE url=%s',
                                         (URL,)).fetchone(), (SHA,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_price WHERE document_id
          IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)''',
          (SHA,)).fetchone(), (0,))
        self.assertEqual(self.db.execute('''SELECT count(*) FROM ingestion_checkpoint WHERE
          document_id=%s AND step LIKE 'city-member:%%' ''', (SHA,)).fetchone(), (0,))
        self.db.execute('''UPDATE ingestion_asset SET status='failed',error=%s,
          processor_version=%s WHERE url=%s''',
          ('RuntimeError: controlled current revision crash after COPY',
           worker.asset_parser_version('city-zip', URL), URL))
        with patch.object(worker, '_get', side_effect=AssertionError('HTTP before retained recovery')):
            self.assertEqual(worker.process_asset(self.db, URL, 'city-zip', DAY), 2262)
        self.assertEqual(self.db.execute('''SELECT document_id,status,records FROM ingestion_asset
          WHERE url=%s''', (URL,)).fetchone(), (SHA, 'complete', 2262))
        self.assertEqual(self.db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
          WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
          ORDER BY 1,2''', (old_did,)).fetchall(), old_rows)

    def test_retained_revision_rejects_wrong_metadata_or_checkpoint(self):
        self.local_archive(self.db, URL, self.body, 'city-zip', DAY)
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,error)
          VALUES(%s,'city-zip',%s,'failed',%s,0,%s,'RuntimeError: controlled')''',
          (URL, DAY, SHA, worker.asset_parser_version('city-zip', URL)))
        self.assertEqual(current.retained_unfinished(
            self.db, URL, 'city-zip', DAY, worker.asset_parser_version('city-zip', URL), DAY),
            self.body)
        self.db.execute('UPDATE ingestion_asset SET attempts=4 WHERE url=%s', (URL,))
        self.assertEqual(queue_plan.current_dane_candidates(self.db, DAY, limit=1), [])
        self.assertEqual(current.retained_unfinished(
            self.db, URL, 'city-zip', DAY, worker.asset_parser_version('city-zip', URL), DAY),
            self.body)
        self.db.execute("UPDATE source_document SET metadata=metadata || '{\"ingestion_kind\":\"daily\"}'::jsonb WHERE id=%s", (SHA,))
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            current.retained_unfinished(self.db, URL, 'city-zip', DAY,
                                        worker.asset_parser_version('city-zip', URL), DAY)
        self.db.execute("UPDATE source_document SET metadata=metadata || '{\"ingestion_kind\":\"city-zip\"}'::jsonb WHERE id=%s", (SHA,))
        with zipfile.ZipFile(io.BytesIO(self.body)) as archive:
            step = city_reports._member_step(archive.infolist()[0], DAY)
        self.db.execute('''INSERT INTO ingestion_checkpoint
          (document_id,processor_version,step,records) VALUES(%s,%s,%s,9)''',
          (SHA, worker.asset_parser_version('city-zip', URL), step))
        with self.assertRaisesRegex(ValueError, 'checkpoint changed'):
            current.retained_unfinished(self.db, URL, 'city-zip', DAY,
                                        worker.asset_parser_version('city-zip', URL), DAY)
