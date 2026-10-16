"""Full-schema worker qualification for exact retained Feb 2014 annexes."""

from __future__ import annotations

import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from pipelines.ingestion import dane_weekly, official_sources, queue_plan, worker
from pipelines.ingestion.reviewed_weekly_feb2014 import (
    PAIRS, REVIEW_LOCATOR, REVIEW_MARKER, VERSION_SUFFIX, review as feb_review,
)
from pipelines.ingestion.retained_weekly_feb2014 import (
    FEB8_429, KIND, retained_feb2014_original,
)


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "testdata" / "weekly_feb2014_reviewed"


@unittest.skipUnless(os.environ.get("AGRO_WEEKLY_FEB2014_RETAINED_TEST_DSN"),
                     "Explicit owned Feb 2014 disposable PostgreSQL DSN required")
class Feb2014RetainedActualWorkerPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ["AGRO_WEEKLY_FEB2014_RETAINED_TEST_DSN"], autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-feb2014-retained-")
                or not cls.db.info.dbname.startswith("agro_weekly_feb2014_retained_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only an owned local Feb 2014 full-schema PG fixture is allowed")
        cls.db.execute("SET statement_timeout='180s'")
        for table in ('source_document','ingestion_asset','official_price_quote',
                      'official_source_review','ingestion_checkpoint'):
            if cls.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                cls.db.close()
                raise RuntimeError('Fresh private Feb 2014 schema must start empty')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _put_original(self, *, did, title, url, media, kind, reference, pages, body, meta):
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,page_count,content,metadata) VALUES (%s,%s,%s,%s,%s,'original',%s,%s,%s,%s)",
            (did, title, "DANE · SIPSA", url, media, reference, pages, body, Jsonb(meta)),
        )

    def _seed_case(self, url, case):
        xname = url.rsplit("/", 1)[-1]
        pname = case["pdf_url"].rsplit("/", 1)[-1]
        xbody = (FIXTURES / xname).read_bytes()
        pbody = (FIXTURES / pname).read_bytes()
        self.assertEqual((hashlib.sha256(xbody).hexdigest(), len(xbody)),
                         (case["xls_sha"], case["xls_size"]))
        self.assertEqual(hashlib.sha256(pbody).hexdigest(), case["pdf_sha"])
        self._put_original(
            did=case["xls_sha"], title="DANE · SIPSA - " + xname, url=url,
            media="application/vnd.ms-excel", kind=KIND,
            reference="Serie histórica completa", pages=None, body=xbody,
            meta={"retention": "permanent", "ingestion_kind": KIND,
                  "original_filename": xname},
        )
        pages = 48 if url == list(PAIRS)[2] else 44
        self._put_original(
            did=case["pdf_sha"], title="DANE · SIPSA - " + pname, url=case["pdf_url"],
            media="application/pdf", kind="dane-weekly-pdf",
            reference=case["period_end"], pages=pages, body=pbody,
            meta={"retention": "permanent", "ingestion_kind": "dane-weekly-pdf",
                  "original_filename": pname},
        )
        # Seed one real parsed quote from each paired PDF so the test can prove
        # the annex worker never changes the separate priced PDF source.
        pdf_rows = dane_weekly.parse(pbody, case["pdf_url"], "dane-weekly-pdf")
        selected = [r for r in pdf_rows if r.get("source_locator") ==
                    "PDF page 6,table 1,column 1,line 2"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(official_sources.publish_rows(
            self.db, selected, case["pdf_sha"], "dane-weekly-pdf", source_url=case["pdf_url"]
        ), 1)

        asset_version = worker.parser_version(KIND)
        if url == list(PAIRS)[0]:
            state, attempts = "pending", 2
            error = "HTTP 429 from www.dane.gov.co; retry after 2026-10-12T10:36:24.071838+00:00"
        else:
            state, attempts = "failed", 1
            error = "ValueError: Weekly grouped workbook has no explicit period in cells or URL"
        self.db.execute(
            f"INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status,processor_version,records,error,attempts,checked_at) "
            f"VALUES(%s,%s,%s,NULL,%s,%s,0,%s,%s,now())",
            (url, KIND, case["xls_sha"], state, asset_version, error, attempts),
        )
        return xbody, pbody, state, error, asset_version

    def _snapshot_document(self, did):
        return self.db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,page_count,"
            "content,metadata,xmin::text FROM source_document WHERE id=%s", (did,)
        ).fetchone()

    def _snapshot_pdf_quotes(self, did):
        return self.db.execute(
            "SELECT source_locator,quote_key,price,min_price,max_price,unit,parser_version,xmin::text "
            "FROM official_price_quote WHERE document_id=%s ORDER BY source_locator,parser_version",
            (did,),
        ).fetchall()

    def test_real_retained_reviews_and_worker_replay_are_unpriced_and_immutable(self):
        db = self.db
        cases = {}
        for url, case in PAIRS.items():
            cases[url] = self._seed_case(url, case)
            rows = feb_review(db, cases[url][0], case["xls_sha"], url)
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["price"])
            self.assertIsNone(rows[0]["details"]["literal_unit_heading"])
            self.assertEqual(rows[0]["details"]["native_numeric_rows_untyped"], case["numeric_rows"])
            self.assertEqual((rows[0]["details"]["period_start"], rows[0]["details"]["period_end"]),
                             (case["period_start"], case["period_end"]))

        expected = {url: worker.asset_parser_version(KIND, url) for url in PAIRS}
        # Simulate wrong retained metadata/body readbacks without changing the
        # append-only source rows. The maintained helper must fail closed.
        first_url, first_case = next(iter(PAIRS.items()))
        first_expected = expected[first_url]

        class CorruptingReadback:
            def execute(self, sql, params=None):
                result = db.execute(sql, params)
                if "FROM ingestion_asset a JOIN source_document d" in sql:
                    row = result.fetchone()
                    changed = list(row)
                    changed[12] = "2014-02-14"
                    return OneRow(changed)
                return result

        class OneRow:
            def __init__(self, row): self.row = tuple(row)
            def fetchone(self): return self.row

        first_body = cases[first_url][0]
        source_before_guard = self._snapshot_document(first_case["xls_sha"])
        with self.assertRaisesRegex(ValueError, "XLS original metadata changed"):
            retained_feb2014_original(
                CorruptingReadback(), first_url, KIND, first_expected, first_expected
            )
        self.assertEqual(self._snapshot_document(first_case["xls_sha"]), source_before_guard)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s",
            (first_case["xls_sha"],),
        ).fetchone()[0], 0)

        class CorruptingBodyReadback:
            def execute(self, sql, params=None):
                result = db.execute(sql, params)
                if "FROM ingestion_asset a JOIN source_document d" in sql:
                    row = list(result.fetchone())
                    row[14] = bytes(row[14]) + b"wrong-body"
                    return OneRow(row)
                return result

        with self.assertRaisesRegex(ValueError, "XLS original SHA or size changed"):
            retained_feb2014_original(
                CorruptingBodyReadback(), first_url, KIND, first_expected, first_expected
            )
        class CorruptingPairPDFReadback:
            def execute(self, sql, params=None):
                result = db.execute(sql, params)
                if "FROM source_document WHERE id=%s" in sql and params == (first_case["pdf_sha"],):
                    row = list(result.fetchone())
                    row[8] = bytes(row[8]) + b"wrong-pdf-body"
                    return OneRow(row)
                return result

        with self.assertRaisesRegex(ValueError, "paired PDF SHA changed"):
            retained_feb2014_original(
                CorruptingPairPDFReadback(), first_url, KIND, first_expected, first_expected
            )

        db.execute("UPDATE ingestion_asset SET error='HTTP 429 from another-host' WHERE url=%s",
                   (first_url,))
        self.assertIsNone(retained_feb2014_original(
            db, first_url, KIND, first_expected, first_expected
        ))
        self.assertNotIn(first_url, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertFalse(worker.retained_reparse_during_host_cooldown(db, first_url + "?alias", KIND))
        self.assertFalse(worker.retained_reparse_during_host_cooldown(db, first_url, "dane-weekly-pdf"))
        # Restore only this disposable fixture's mutable asset diagnostic.
        db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s",
                   (cases[first_url][3], first_url))
        ordinary_url = "https://www.dane.gov.co/files/operaciones/SIPSA/ordinary_weekly_unrelated.xlsx"
        ordinary_version = worker.asset_parser_version(KIND, ordinary_url)
        db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,records,error,attempts,checked_at) "
            "VALUES(%s,%s,'review',%s,0,'unrelated stable review',1,now())",
            (ordinary_url, KIND, ordinary_version),
        )
        competitor = "https://www.dane.gov.co/files/operaciones/SIPSA/older-unrelated-2014.xlsx"
        db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,error,attempts,checked_at) "
            "VALUES(%s,%s,%s,'failed','legacy-xlsx-v1',0,'unrelated stale failure',1,now()-interval '7 hours')",
            (competitor, KIND, date(2014, 3, 7)),
        )

        # A recent pending 429 retains its queue cooldown. Exact stale failed
        # siblings can use the pinned local-only repair lane; the worker then
        # rechecks every source and pair guard before using retained bytes.
        offered = set(queue_plan.backfill_candidates(db, 1000))
        feb8 = list(PAIRS)[0]
        self.assertNotIn((feb8, KIND, None), offered)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, feb8, KIND))
        for url in list(PAIRS)[1:]:
            self.assertIn((url, KIND, None), offered)
            self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, KIND))
        self.assertNotIn((ordinary_url, KIND, None), offered)
        repair_selected = queue_plan.repair_candidates(db, 8)
        feb_repair = [row for row in repair_selected if row[0] in PAIRS]
        self.assertEqual(len(feb_repair), 1)
        self.assertIn(feb_repair[0][0], list(PAIRS)[1:])
        self.assertNotIn(first_url, [row[0] for row in repair_selected])
        self.assertNotIn(competitor, [row[0] for row in repair_selected])
        db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (feb8,))
        ordered_candidates = queue_plan.backfill_candidates(db, 1000)
        self.assertIn((feb8, KIND, None), set(ordered_candidates))
        # The queue's exact stale-failed repair class outranks a pending
        # retry once the latter's six-hour cooldown has elapsed.
        positions = {candidate[0]: index for index, candidate in enumerate(ordered_candidates)}
        for failed_url in list(PAIRS)[1:]:
            self.assertLess(positions[failed_url], positions[feb8])
        self.assertLess(max(positions[url] for url in PAIRS), positions[competitor])

        blobs = []
        for url, case in PAIRS.items():
            xbody, pbody, prior_state, prior_error, old_version = cases[url]
            did, pdf_did = case["xls_sha"], case["pdf_sha"]
            xdoc_before, pdoc_before = self._snapshot_document(did), self._snapshot_document(pdf_did)
            pdf_quotes_before = self._snapshot_pdf_quotes(pdf_did)
            expected_version = expected[url]
            old_review = db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)
            ).fetchone()[0]
            self.assertEqual(old_review, 0)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
            ).fetchone()[0], 0)
            self.assertIsNone(db.execute(
                "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
                "AND step='official:complete'", (did, expected_version)
            ).fetchone())

            from pipelines.ingestion import blob_archive

            def no_http(*args, **kwargs):
                raise AssertionError(f"Pinned Feb 2014 replay must not make HTTP: {args!r} {kwargs!r}")

            def retain(digest, data, suffix, media):
                self.assertEqual((digest, data, suffix, media), (did, xbody, ".xls", "application/vnd.ms-excel"))
                blobs.append(digest)

            with patch.object(worker, "fetch_asset", side_effect=no_http), \
                 patch.object(blob_archive, "retain_original_blob", side_effect=retain):
                self.assertEqual(worker.process_asset(db, url, KIND, None), 0)

            self.assertEqual(self._snapshot_document(did), xdoc_before)
            self.assertEqual(self._snapshot_document(pdf_did), pdoc_before)
            self.assertEqual(self._snapshot_pdf_quotes(pdf_did), pdf_quotes_before)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM regional_price WHERE document_id=%s", (did,)
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM historical_price WHERE document_id=%s", (did,)
            ).fetchone()[0], 0)
            asset = db.execute(
                "SELECT status,records,error,document_id,processor_version,observed_on "
                "FROM ingestion_asset WHERE url=%s", (url,)
            ).fetchone()
            self.assertEqual(asset[:2], ("review", 0))
            self.assertIn(REVIEW_MARKER, asset[2])
            self.assertIn(prior_error, asset[2])
            self.assertEqual(asset[3:], (did, expected_version, None))
            reviews = db.execute(
                "SELECT source_locator,parser_version,record,reason,xmin::text "
                "FROM official_source_review WHERE document_id=%s", (did,)
            ).fetchall()
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0][:2], (REVIEW_LOCATOR, expected_version))
            self.assertEqual(reviews[0][2], feb_review(db, xbody, did, url)[0])
            self.assertEqual(reviews[0][3], REVIEW_MARKER)
            self.assertIsNone(reviews[0][2]["price"])
            self.assertEqual(reviews[0][2]["details"]["native_numeric_rows_untyped"], case["numeric_rows"])
            self.assertEqual(reviews[0][2]["details"]["period_start"], case["period_start"])
            self.assertEqual(reviews[0][2]["details"]["period_end"], case["period_end"])
            self.assertIsNone(reviews[0][2]["details"]["literal_unit_heading"])
            cp = db.execute(
                "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (did, expected_version),
            ).fetchone()
            self.assertEqual(cp[:3], (expected_version, "official:complete", 0))
            self.assertNotIn((url, KIND, None), set(queue_plan.backfill_candidates(db, 1000)))

            # A current review is not eligible for retained fallback. It uses
            # the ordinary fetch path and keeps review/checkpoint xmins stable.
            reviews_before_replay = db.execute(
                "SELECT source_locator,parser_version,record,reason,xmin::text "
                "FROM official_source_review WHERE document_id=%s", (did,)
            ).fetchall()
            cp_before_replay = db.execute(
                "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (did, expected_version),
            ).fetchone()
            with patch.object(worker, "fetch_asset", return_value=xbody) as fetched, \
                 patch.object(blob_archive, "retain_original_blob", side_effect=retain):
                self.assertEqual(worker.process_asset(db, url, KIND, None), 0)
            self.assertTrue(fetched.called)
            self.assertEqual(db.execute(
                "SELECT source_locator,parser_version,record,reason,xmin::text "
                "FROM official_source_review WHERE document_id=%s", (did,)
            ).fetchall(), reviews_before_replay)
            self.assertEqual(db.execute(
                "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (did, expected_version),
            ).fetchone(), cp_before_replay)
            self.assertEqual(self._snapshot_document(did), xdoc_before)
            self.assertEqual(self._snapshot_document(pdf_did), pdoc_before)
            self.assertEqual(self._snapshot_pdf_quotes(pdf_did), pdf_quotes_before)

            # A current completed refresh remains on the normal fetch path.
            # The already-published review and zero-record checkpoint stay put.
            db.execute("UPDATE ingestion_asset SET status='complete' WHERE url=%s", (url,))
            with patch.object(worker, "fetch_asset", return_value=xbody) as current_fetch, \
                 patch.object(blob_archive, "retain_original_blob", side_effect=retain):
                self.assertEqual(worker.process_asset(db, url, KIND, None), 0)
            self.assertTrue(current_fetch.called)
            self.assertEqual(self._snapshot_document(did), xdoc_before)
            self.assertEqual(db.execute(
                "SELECT source_locator,parser_version,record,reason,xmin::text "
                "FROM official_source_review WHERE document_id=%s", (did,),
            ).fetchall(), reviews_before_replay)
            self.assertEqual(db.execute(
                "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (did, expected_version),
            ).fetchone(), cp_before_replay)
        self.assertEqual(set(blobs), {case["xls_sha"] for case in PAIRS.values()})

if __name__ == "__main__":
    unittest.main(verbosity=2)
