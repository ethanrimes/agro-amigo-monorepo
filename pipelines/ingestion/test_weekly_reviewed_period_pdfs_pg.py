"""Owned full-schema worker/queue controls for two reviewed weekly PDF periods."""
import contextlib
import hashlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import dane_weekly, queue_plan, worker, write_pacing


FIXTURES = Path(__file__).parent / "testdata" / "weekly_reviewed_period"
CASES = (
    (dane_weekly.APRIL_2017_EXTENDED_PERIOD_URL,
     dane_weekly.APRIL_2017_EXTENDED_PERIOD_SHA, "2017-04-21", 4472, 153),
    (dane_weekly.JANUARY_2015_SPACED_YEARS_URL,
     dane_weekly.JANUARY_2015_SPACED_YEARS_SHA, "2015-01-02", 4291, 136),
)


@unittest.skipUnless(os.environ.get("AGRO_WEEKLY_PERIOD_PDF_TEST_DSN"),
                     "Explicit fresh owned full-schema PostgreSQL DSN required")
class ReviewedWeeklyPeriodPDFPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_WEEKLY_PERIOD_PDF_TEST_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-")
                or not cls.db.info.dbname.startswith("agro_weekly_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only an owned weekly Unix-socket database is allowed")
        cls.db.execute("SET statement_timeout='90s'")
        for table in ("source_document", "ingestion_asset", "official_price_quote",
                      "official_source_review", "ingestion_checkpoint"):
            if cls.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                cls.db.close()
                raise RuntimeError("Period PDF test requires a fresh empty database")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_both_exact_originals_backfill_worker_checkpoint_and_rerun(self):
        db = self.db
        for url, did, day, priced, review in CASES:
            with self.subTest(url=url):
                body = (FIXTURES / f"{did}.pdf").read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), did)
                self.assertEqual(dane_weekly.source_date(url).isoformat(), day)
                db.execute(
                    "INSERT INTO ingestion_asset(url,kind,status,processor_version,observed_on) "
                    "VALUES(%s,'dane-weekly-pdf','pending',%s,%s)",
                    (url, worker.asset_parser_version("dane-weekly-pdf", url), day),
                )
                offered = queue_plan.backfill_candidates(db, limit=8)
                self.assertTrue(any(r[0] == url and r[1] == "dane-weekly-pdf"
                                    and str(r[2]) == day for r in offered))
                published_before = db.execute(
                    "SELECT count(*) FROM published_official_price").fetchone()[0]
                with patch.object(worker, "connect", return_value=contextlib.nullcontext(db)), \
                        patch.object(worker, "fetch_asset", return_value=body), \
                        patch("pipelines.ingestion.blob_archive.retain_original_blob"), \
                        patch("pipelines.ingestion.ocr.drain", return_value={"processed": 0}), \
                        patch.object(write_pacing.time, "sleep"), \
                        contextlib.redirect_stdout(io.StringIO()):
                    summary = worker.run(mode="discover", limit=1, time_budget=180,
                                         ocr_limit=0, ocr_scan_limit=0, asset_url=url)
                self.assertFalse(summary["errors"])
                self.assertEqual(db.execute(
                    "SELECT status,document_id,records FROM ingestion_asset WHERE url=%s",
                    (url,),
                ).fetchone(), ("complete", did, priced))
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM official_source_review WHERE document_id=%s",
                    (did,),
                ).fetchone()[0], review)
                self.assertEqual(db.execute(
                    "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
                    "AND processor_version=%s AND step='official:complete'",
                    (did, worker.asset_parser_version("dane-weekly-pdf", url)),
                ).fetchone(), (priced,))
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM published_official_price WHERE document_id=%s",
                    (did,),
                ).fetchone()[0], priced)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM published_official_price").fetchone()[0],
                    published_before + priced)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM source_document WHERE id=%s AND "
                    "source_url=%s AND kind='original' AND media_type='application/pdf'",
                    (did, url),
                ).fetchone()[0], 1)
                xmins = dict(db.execute(
                    "SELECT source_locator,xmin::text FROM official_price_quote "
                    "WHERE document_id=%s", (did,),
                ).fetchall())
                self.assertEqual(len(xmins), priced)
                with patch.object(worker, "fetch_asset", return_value=body), \
                        patch("pipelines.ingestion.blob_archive.retain_original_blob"), \
                        patch.object(write_pacing.time, "sleep"):
                    # Generic weekly refresh may reparse; its append must be
                    # idempotent even when it reports the same priced count.
                    self.assertIn(worker.process_asset(
                        db, url, "dane-weekly-pdf", dane_weekly.source_date(url)),
                        (0, priced))
                self.assertEqual(dict(db.execute(
                    "SELECT source_locator,xmin::text FROM official_price_quote "
                    "WHERE document_id=%s", (did,),
                ).fetchall()), xmins)


if __name__ == "__main__":
    unittest.main()
