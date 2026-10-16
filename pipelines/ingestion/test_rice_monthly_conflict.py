"""Move to pipelines/ingestion/test_rice_monthly_conflict.py only after v8 approval.

Uses SHA-verified retained public originals via SELECT only, then all mutation is
in rollback-only temporary PostgreSQL tables. No worker invocation.
"""
import hashlib
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from . import dane_weekly, official_catalog, official_sources, queue_plan, worker, write_pacing
from .test_official_catalog import TABLES, install_cache


@unittest.skipUnless(os.environ.get('AGRO_OFFICIAL_CATALOG_TEST') == '1',
                     'Explicit opt-in for isolated PostgreSQL cache checks')
class RiceMonthlyConflictPrivatePgTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET statement_timeout='25s'")
        self.originals = {}
        fixture_dir = Path(__file__).parent / 'testdata/rice_monthly_conflict'
        for sha, case in dane_weekly.RICE_MONTHLY_CONFLICTS.items():
            for did, url, suffix in (
                (sha, case['url'], '.xls'),
                (case['pdf_sha256'], case['url'][:-4] + '.pdf', '.pdf'),
            ):
                body = (fixture_dir / (did + suffix)).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), did)
                self.originals[did] = (url, body)
        self.db.execute('SET search_path=pg_temp')
        for table in TABLES:
            self.db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.db.execute('CREATE INDEX quote_identity ON official_price_quote(quote_key,observed_on DESC)')
        install_cache(self.db)
        self.enterContext(patch.object(official_catalog, '_sleep'))
        self.enterContext(patch.object(write_pacing.time, 'sleep'))
        self.enterContext(patch.object(write_pacing, 'clock', return_value=100))
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        self.addCleanup(self.db.rollback)

    def seed_source(self, did):
        url, body = self.originals[did]
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) VALUES(%s,%s,'DANE',%s,%s,'original','',%s)",
            (did, 'Retained exact original', url,
             'application/pdf' if url.endswith('.pdf') else 'application/vnd.ms-excel', body),
        )

    def test_exact_111_reviews_and_unrelated_native_price_rows(self):
        for sha, case in dane_weekly.RICE_MONTHLY_CONFLICTS.items():
            url, body = self.originals[sha]
            rows = dane_weekly.parse_workbook(body, url)
            rice = [r for r in rows if r['source_locator'].startswith('1.9!')]
            self.assertEqual(len(rice), 111)
            self.assertTrue(all(r['price'] is None and r['details']['literal_mean'] > 0
                                and r['details']['companion_pdf_sha256'] == case['pdf_sha256']
                                and r['details']['literal_pdf_table_month'] == case['table_month']
                                for r in rice))
            siblings = [r for r in rows if not r['source_locator'].startswith('1.9!')]
            self.assertGreater(len(siblings), 3000)
            self.assertFalse(any(r['details'].get('conflict_kind') == 'publisher_unit_and_period'
                                 for r in siblings))
            changed = dane_weekly.parse_workbook(body + b'\x00' * 512, url)
            changed_rice = [r for r in changed if r['source_locator'].startswith('1.9!')]
            self.assertEqual(len(changed_rice), 111)
            self.assertTrue(all(r['price'] is None and
                                r['details']['original_sha256'] == hashlib.sha256(body + b'\x00' * 512).hexdigest() and
                                'companion_pdf_sha256' not in r['details'] for r in changed_rice))

    def test_changed_prices_remain_reviewed_and_unbound_layout_fails_closed(self):
        sha, case = next(iter(dane_weekly.RICE_MONTHLY_CONFLICTS.items()))
        url, body = self.originals[sha]
        changed_body = body + b'\x00' * 512
        sheets = [(name, [list(row) for row in rows]) for name, rows in worker.workbooks(body)]
        for name, rows in sheets:
            if name == '1.9':
                rows[11][4] += 1000
        with patch.object(worker, 'workbooks', return_value=sheets):
            changed = dane_weekly.parse_workbook(changed_body, url)
        rice = [r for r in changed if r['source_locator'].startswith('1.9!')]
        self.assertEqual(len(rice), 111)
        self.assertEqual(rice[0]['details']['literal_mean'], case['first'][2] + 1000)
        self.assertTrue(all(r['price'] is None and 'companion_pdf_sha256' not in r['details'] for r in rice))
        self.assertGreater(len([r for r in changed if r['price'] is not None]), 3000)
        renamed = [('2.9' if name == '1.9' else name, rows) for name, rows in sheets]
        with patch.object(worker, 'workbooks', return_value=renamed):
            with self.assertRaises(worker.SourceRevisionNeedsReview):
                dane_weekly.parse_workbook(changed_body, url)
        moved = [(name, rows) for name, rows in sheets if name != '1.9']
        with patch.object(worker, 'workbooks', return_value=moved):
            with patch.object(official_sources, 'publish_rows', side_effect=AssertionError('published unbound original')):
                with self.assertRaises(worker.SourceRevisionNeedsReview):
                    official_sources.process(self.db, changed_body, hashlib.sha256(changed_body).hexdigest(), url, 'dane-weekly-xlsx')

    def test_exact_companion_original_required_before_publication(self):
        sha, case = next(iter(dane_weekly.RICE_MONTHLY_CONFLICTS.items()))
        self.seed_source(sha)
        self.seed_source(case['pdf_sha256'])
        url, body = self.originals[sha]
        with patch.object(official_sources, 'publish_rows', return_value=0):
            self.assertEqual(official_sources.process(self.db, body, sha, url, 'dane-weekly-xlsx'), 0)
            self.db.execute('DELETE FROM source_document WHERE id=%s', (case['pdf_sha256'],))
            with self.assertRaisesRegex(ValueError, 'companion PDF'):
                official_sources.process(self.db, body, sha, url, 'dane-weekly-xlsx')

    def test_old_quote_retained_review_withdraws_only_rice_and_replay_is_idempotent(self):
        for sha, case in dane_weekly.RICE_MONTHLY_CONFLICTS.items():
            self.seed_source(sha)
            url, body = self.originals[sha]
            reviewed = dane_weekly.parse_workbook(body, url)
            old = deepcopy(next(r for r in reviewed if r['source_locator'] == '1.9!row 12,cols C:E'))
            old['price'] = old['details']['literal_mean']
            old['details'].pop('quality_issue')
            new = next(r for r in reviewed if r['source_locator'] == old['source_locator'])
            sibling = next(r for r in reviewed if r['source_locator'].startswith('1.8!') and r['price'] is not None)
            with patch.object(worker, 'parser_version', return_value='fixture-v1'):
                self.assertEqual(official_sources.publish_rows(self.db, [old,sibling], sha, 'dane-weekly-xlsx'), 2)
            key = self.db.execute('SELECT quote_key FROM official_price_quote WHERE document_id=%s AND source_locator=%s',
                                  (sha, old['source_locator'])).fetchone()[0]
            sibling_key = self.db.execute('SELECT quote_key FROM official_price_quote WHERE document_id=%s AND source_locator=%s',
                                          (sha, sibling['source_locator'])).fetchone()[0]
            self.assertIsNotNone(self.db.execute('SELECT payload FROM official_catalog_current WHERE quote_key=%s',
                                                  (key,)).fetchone()[0])
            with patch.object(worker, 'parser_version', return_value='fixture-v2'):
                self.assertEqual(official_sources.publish_rows(self.db, [new,sibling], sha, 'dane-weekly-xlsx'), 1)
                self.assertEqual(official_sources.publish_rows(self.db, [new,sibling], sha, 'dane-weekly-xlsx'), 1)
            self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s',
                                             (sha,)).fetchone()[0], 3)
            self.assertEqual(self.db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s AND source_locator=%s',
                                             (sha, old['source_locator'])).fetchone()[0], 1)
            self.assertEqual(self.db.execute('SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s',
                                             (key,)).fetchone(), (None,False))
            self.assertIsNotNone(self.db.execute('SELECT payload FROM official_catalog_current WHERE quote_key=%s',
                                                  (sibling_key,)).fetchone()[0])

    def test_retained_exact_original_is_processed_before_any_network_refresh(self):
        sha, case = next(iter(dane_weekly.RICE_MONTHLY_CONFLICTS.items()))
        self.seed_source(sha)
        url, body = self.originals[sha]
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on,processor_version) VALUES(%s,'dane-weekly-xlsx',%s,'complete',%s,%s)",
            (url,sha,case['cover_end'],worker.parser_version('dane-weekly-xlsx')),
        )
        with (patch.object(worker, 'fetch_asset', side_effect=AssertionError('network refresh before retained review')),
              patch.object(worker, 'archive', return_value=sha),
              patch.object(official_sources, 'process', return_value=111) as published):
            self.assertEqual(worker._process_asset(self.db,url,'dane-weekly-xlsx',None),111)
        self.assertEqual(published.call_args.args[1],body)
        asset=self.db.execute('SELECT document_id,status,records FROM ingestion_asset WHERE url=%s',(url,)).fetchone()
        self.assertEqual(asset,(sha,'complete',111))

    def test_url_specific_version_replays_only_two_complete_assets(self):
        base=worker.parser_version('dane-weekly-xlsx')
        for sha,case in dane_weekly.RICE_MONTHLY_CONFLICTS.items():
            target=worker.parser_version('dane-weekly-xlsx',case['url'])
            self.assertNotEqual(base,target)
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on,checked_at,processor_version) VALUES(%s,'dane-weekly-xlsx',%s,'complete',%s,now(),%s)",
                (case['url'],sha,case['cover_end'],base),
            )
        unrelated='https://www.dane.gov.co/other-weekly.xlsx'
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at,processor_version) VALUES(%s,'dane-weekly-xlsx','complete','2021-05-07',now(),%s)",
            (unrelated,base),
        )
        newer='https://www.dane.gov.co/other-newer-weekly-2026.xlsx'
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at,processor_version) VALUES(%s,'dane-weekly-xlsx','complete','2026-09-25',now(),'old-v1')",
            (newer,),
        )
        selected={r[0] for r in queue_plan.backfill_candidates(self.db,2)}
        self.assertEqual(selected,set(c['url'] for c in dane_weekly.RICE_MONTHLY_CONFLICTS.values()))
        for case in dane_weekly.RICE_MONTHLY_CONFLICTS.values():
            self.db.execute('UPDATE ingestion_asset SET processor_version=%s WHERE url=%s',
                            (worker.parser_version('dane-weekly-xlsx',case['url']),case['url']))
        self.assertEqual([r[0] for r in queue_plan.backfill_candidates(self.db,2)],[newer])


if __name__ == '__main__':
    unittest.main()
