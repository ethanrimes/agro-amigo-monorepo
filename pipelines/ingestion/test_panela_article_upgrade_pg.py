"""Opt-in, real-worker retained June 2014 Cuadro to article upgrade.

The runner supplies a disposable, empty full-schema PostgreSQL database on a
Unix socket. This test never changes a production source or calls a provider.
"""

import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import (dane_weekly, official_catalog, official_sources,
               panela_article_official, worker, write_pacing)
from .panela_article_exact import ORIGINAL_SHA, SOURCE_URL


FIXTURE = Path(__file__).parent / "testdata" / "dane_date_repairs" / (ORIGINAL_SHA + ".pdf")
OLD = "official-v2:dane-weekly-v24"
BOUNDARY = OLD + ":panela-article-boundary-jun2014-v1"
ARTICLE = "official-v2:jun2014-panela-article-single-price-v1:dane-weekly-v24"


@unittest.skipUnless(os.environ.get("AGRO_PANELA_ARTICLE_TEST_DSN"), "Owned PostgreSQL fixture required")
class PanelaArticleWorkerUpgrade(unittest.TestCase):
    def test_actual_worker_retained_upgrade_and_replay(self):
        db = psycopg.connect(os.environ["AGRO_PANELA_ARTICLE_TEST_DSN"], autocommit=True)
        self.addCleanup(db.close)
        if (not db.info.host.startswith("/tmp/agro-")
                or not db.info.dbname.startswith("agro_panela_article_")
                or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            raise RuntimeError("Only owned local agro_panela_article_* PostgreSQL is allowed")
        # The disposable schema does not inherit the production bootstrap ACL.
        # Match the worker's observed scoped rights before SET ROLE below.
        db.execute("GRANT SELECT,INSERT ON source_document,official_price_quote,"
                   "official_source_review,ingestion_checkpoint TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON ingestion_asset,"
                   "official_catalog_current,source_ocr_task TO agro_ingestor")
        db.execute("GRANT SELECT ON published_official_price,source_pdf_page TO agro_ingestor")
        body = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), ORIGINAL_SHA)
        cuadro = dane_weekly.parse_pdf(body, SOURCE_URL)
        self.assertEqual((len(cuadro), sum(row["price"] is not None for row in cuadro)), (4516, 4309))
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", SOURCE_URL), ARTICLE)
        db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
          VALUES(%s,'DANE - Semana_16jun_20jun_2014.pdf','DANE',%s,
                 'application/pdf','original','2014-06-20',44,%s,%s)""",
          (ORIGINAL_SHA, SOURCE_URL, body,
           Jsonb({"ingestion_kind": "dane-weekly-pdf", "retention": "permanent",
                  "original_filename": "Semana_16jun_20jun_2014.pdf"})))
        db.execute("""INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at,error)
          VALUES(%s,'dane-weekly-pdf','2014-06-20','failed',%s,0,%s,
                 now()-interval '7 hours','Weekly PDF page 43 has conflicting printed periods')""",
          (SOURCE_URL, ORIGINAL_SHA, OLD))
        source_xmin = db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (ORIGINAL_SHA,)).fetchone()[0]
        with patch.object(write_pacing, "pause_between_batches", return_value=None), \
             patch.object(write_pacing, "yield_to_active_readers", return_value=None), \
             patch.object(official_catalog, "_sleep", return_value=None), \
             patch.object(official_catalog, "DOCUMENT_BATCH_SIZE", 512):
            self.assertEqual(official_sources.publish_rows(db, cuadro, ORIGINAL_SHA, "dane-weekly-pdf"), 4309)
        db.execute("UPDATE ingestion_asset SET status='complete',records=4309,processor_version=%s,error=NULL WHERE url=%s",
                   (BOUNDARY, SOURCE_URL))
        old_quotes = db.execute("SELECT source_locator,xmin::text FROM official_price_quote "
                                "WHERE document_id=%s AND parser_version=%s ORDER BY 1",
                                (ORIGINAL_SHA, OLD)).fetchall()
        old_reviews = db.execute("SELECT source_locator,xmin::text FROM official_source_review "
                                 "WHERE document_id=%s AND parser_version=%s ORDER BY 1",
                                 (ORIGINAL_SHA, OLD)).fetchall()
        old_checkpoint = db.execute("SELECT records,xmin::text FROM ingestion_checkpoint "
                                    "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                                    (ORIGINAL_SHA, OLD)).fetchone()
        self.assertEqual((len(old_quotes), len(old_reviews), old_checkpoint[0]), (4309, 207, 4309))
        db.execute("SET ROLE agro_ingestor")
        self.addCleanup(lambda: db.execute("RESET ROLE"))
        self.assertEqual(db.execute("SELECT current_user").fetchone()[0], "agro_ingestor")
        with patch.object(panela_article_official, "official_rows", side_effect=ValueError("changed native grid")):
            with self.assertRaisesRegex(ValueError, "changed native grid"):
                official_sources.process(db, body, ORIGINAL_SHA, SOURCE_URL, "dane-weekly-pdf")
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (ORIGINAL_SHA,)).fetchone()[0], 4309)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (ORIGINAL_SHA,)).fetchone()[0], 207)
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("source HTTP forbidden")), \
             patch.object(worker, "_request", side_effect=AssertionError("source HTTP forbidden")), \
             patch.object(write_pacing, "pause_between_batches", return_value=None), \
             patch.object(write_pacing, "yield_to_active_readers", return_value=None), \
             patch.object(official_catalog, "_sleep", return_value=None), \
             patch.object(official_catalog, "DOCUMENT_BATCH_SIZE", 512):
            self.assertEqual(worker.process_asset(db, SOURCE_URL, "dane-weekly-pdf", date(2014, 6, 20)), 4369)
        stored = db.execute("SELECT source_locator,series,price,min_price,max_price,period_start,observed_on,"
                            "source_page,details FROM published_official_price "
                            "WHERE document_id=%s AND series='dane-panela-article' ORDER BY source_locator",
                            (ORIGINAL_SHA,)).fetchall()
        self.assertEqual(len(stored), 60)
        self.assertTrue(all(row[3] is None and row[4] is None and row[8]["price_statistic"] == "published_single_price"
                            for row in stored))
        self.assertEqual(db.execute("SELECT count(*) FROM published_official_price WHERE document_id=%s AND series='dane-weekly'",
                                    (ORIGINAL_SHA,)).fetchone()[0], 4309)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s",
                                    (ORIGINAL_SHA, ARTICLE)).fetchone()[0], 207)
        self.assertEqual(db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                                    (ORIGINAL_SHA, ARTICLE)).fetchone()[0], 4369)
        self.assertEqual(db.execute("SELECT count(*) FROM official_catalog_current WHERE quote_key IN "
                                    "(SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id=%s AND series='dane-panela-article') "
                                    "AND NOT dirty AND payload IS NOT NULL", (ORIGINAL_SHA,)).fetchone()[0], 12)
        self.assertEqual(db.execute("SELECT count(*) FROM "
                                    "(SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id=%s AND series='dane-panela-article') a "
                                    "JOIN (SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id=%s AND series='dane-weekly') b USING(quote_key)",
                                    (ORIGINAL_SHA, ORIGINAL_SHA)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT source_locator,xmin::text FROM official_price_quote "
                                    "WHERE document_id=%s AND parser_version=%s ORDER BY 1", (ORIGINAL_SHA, OLD)).fetchall(), old_quotes)
        self.assertEqual(db.execute("SELECT source_locator,xmin::text FROM official_source_review "
                                    "WHERE document_id=%s AND parser_version=%s ORDER BY 1", (ORIGINAL_SHA, OLD)).fetchall(), old_reviews)
        before = db.execute("SELECT source_locator,xmin::text FROM official_price_quote "
                            "WHERE document_id=%s AND parser_version=%s ORDER BY 1", (ORIGINAL_SHA, ARTICLE)).fetchall()
        self.assertEqual(worker.process_asset(db, SOURCE_URL, "dane-weekly-pdf", date(2014, 6, 20)), 4369)
        self.assertEqual(db.execute("SELECT source_locator,xmin::text FROM official_price_quote "
                                    "WHERE document_id=%s AND parser_version=%s ORDER BY 1", (ORIGINAL_SHA, ARTICLE)).fetchall(), before)
        self.assertEqual(db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (ORIGINAL_SHA,)).fetchone()[0], source_xmin)
        self.assertEqual(db.execute("SELECT records,xmin::text FROM ingestion_checkpoint "
                                    "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                                    (ORIGINAL_SHA, OLD)).fetchone(), old_checkpoint)


if __name__ == "__main__":
    unittest.main()
