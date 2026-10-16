"""Exact-original font repair: retained versions and real derived catalog SQL."""

import hashlib
import os
import unittest
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly as weekly, official_catalog, official_sources, queue_plan, worker
from .retained_pdf_upgrade import retained_pdf_upgrade
from .resumable_inputs import WorkDeferred
from .test_official_catalog import install_cache
from .test_weekly_2012_font_run import CONTROLS, ORIGINAL, SHA


URL = weekly.JUNE_2012_FONT_RUN_URL
KIND = "dane-weekly-pdf"
OLD = "official-v2:dane-weekly-v11"
NEW = "official-v2:jun2012-native-font-run-v2:dane-weekly-v24"


class Weekly2012FontRunPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("Explicit isolated PostgreSQL DSN required")
        cls.db = psycopg.connect(dsn, autocommit=True)
        if not str(cls.db.info.host).startswith("/tmp/agro-"):
            cls.db.close()
            raise RuntimeError("Only private PostgreSQL socket is permitted")
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
        for name in ("source_document", "ingestion_asset", "official_price_quote",
                     "official_source_review", "ingestion_checkpoint", "historical_price"):
            cls.db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
        cls.db.execute("CREATE INDEX quote_identity_font_run ON official_price_quote(quote_key,observed_on DESC)")
        install_cache(cls.db)
        cls.body = ORIGINAL.read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != SHA:
            raise RuntimeError("Native original SHA changed")
        cls.rows = weekly.parse_pdf(cls.body, URL)
        cls.by_locator = {r["source_locator"]: r for r in cls.rows}
        with patch.object(weekly, "JUNE_2012_FONT_RUN_SHA", "0" * 64):
            cls.old_rows = weekly.parse_pdf(cls.body, URL)
        cls.old_by_locator = {r["source_locator"]: r for r in cls.old_rows}
        cls.changed_locators = sorted(
            loc for loc in cls.by_locator if cls.by_locator[loc] != cls.old_by_locator[loc]
        )
        if len(cls.changed_locators) != 74:
            raise RuntimeError("Audited heading/market union is not 74 rows")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2012-06-22',%s,%s)",
            (SHA, URL, self.body, Jsonb({"ingestion_kind": KIND})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at,records) "
            "VALUES(%s,%s,'complete',%s,%s,'2012-06-22',now()-interval '7 hours',1340)",
            (URL, KIND, OLD, SHA),
        )

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def test_retained_exact_bytes_and_bounded_priority(self):
        self.assertEqual(retained_pdf_upgrade(self.db, URL, KIND, NEW), self.body)
        self.assertIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (URL,))
        self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours',document_id=%s WHERE url=%s",
                        ("0" * 64, URL))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, NEW))
        self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (SHA, URL))
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body + b"changed", SHA))
        with self.assertRaisesRegex(ValueError, "invalid original SHA"):
            retained_pdf_upgrade(self.db, URL, KIND, NEW)
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body, SHA))
        self.db.execute("UPDATE source_document SET source_url=%s WHERE id=%s", (URL + ".alias", SHA))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, NEW))

    def test_74_corrected_identities_supersede_old_without_erasing_raw(self):
        old = [self.old_by_locator[locator] for locator in self.changed_locators]
        self.assertEqual(len(old), 74)
        with patch.object(worker, "parser_version", return_value=OLD):
            official_sources.publish_rows(self.db, old, SHA, KIND)
        prior = self.db.execute(
            "SELECT source_locator,quote_key,product_name,price,min_price,max_price,observed_on,unit "
            "FROM official_price_quote WHERE document_id=%s ORDER BY source_locator", (SHA,),
        ).fetchall()
        old_keys = [r[1] for r in prior]
        self.db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s", (SHA,))
        # Complete new parse includes every locator, including no-price reviews.
        with patch("pipelines.ingestion.write_pacing.pause_between_batches"):
            self.assertEqual(official_sources.publish_rows(self.db, self.rows, SHA, KIND, source_url=URL),
                             sum(r["price"] is not None for r in self.rows))
            self.assertEqual(official_sources.publish_rows(self.db, self.rows, SHA, KIND, source_url=URL),
                             sum(r["price"] is not None for r in self.rows))
        self.assertEqual(self.db.execute(
            "SELECT source_locator,quote_key,product_name,price,min_price,max_price,observed_on,unit "
            "FROM official_price_quote WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (SHA, OLD),
        ).fetchall(), prior)
        for locator in self.changed_locators:
            revised = self.db.execute(
                "SELECT product_name,market,price,min_price,max_price,parser_version,quote_key "
                "FROM published_official_price WHERE document_id=%s AND source_locator=%s",
                (SHA, locator),
            ).fetchall()
            self.assertEqual(len(revised), 1)
            self.assertEqual(revised[0][0], self.by_locator[locator]["product_name"])
            self.assertEqual(revised[0][1], self.by_locator[locator]["market"])
            self.assertEqual(tuple(float(x) if x is not None else None for x in revised[0][2:5]),
                             (self.by_locator[locator]["price"], self.by_locator[locator]["min"],
                              self.by_locator[locator]["max"]))
            self.assertEqual(revised[0][5], NEW)
        new_keys = {r[0] for r in self.db.execute(
            "SELECT quote_key FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s AND source_locator=ANY(%s::text[])",
            (SHA, NEW, self.changed_locators),
        ).fetchall()}
        self.assertEqual(len(new_keys), 74)
        self.assertFalse(new_keys & set(old_keys))
        for key in old_keys:
            self.assertEqual(self.db.execute(
                "SELECT payload,dirty,dirty_since FROM official_catalog_current WHERE quote_key=%s", (key,),
            ).fetchone(), (None, False, None))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE quote_key=ANY(%s::text[]) "
            "AND NOT dirty AND dirty_since IS NULL AND payload IS NOT NULL",
            (list(new_keys),),
        ).fetchone()[0], 74)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
            "AND step='official:complete'", (SHA, NEW),
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s",
            (SHA, NEW),
        ).fetchone()[0], 88)

    def test_wrong_original_never_gets_source_specific_quote_revision(self):
        with self.assertRaisesRegex(ValueError, "original changed"):
            official_sources.publish_rows(self.db, [], "0" * 64, KIND, source_url=URL)
        self.assertEqual(worker.parser_version(KIND, URL), NEW)
        self.assertEqual(worker.parser_version(KIND, URL + "?changed"), "official-v2:dane-weekly-v24")

    def test_interrupted_quote_batches_keep_old_identity_dirty_until_resume(self):
        # A separate autocommit connection models independently durable batches,
        # rather than the fixture's enclosing rollback transaction.
        with psycopg.connect(os.environ["AGRO_REFERENCE_TEST_DSN"], autocommit=True) as db:
            if not str(db.info.host).startswith("/tmp/agro-"):
                raise RuntimeError("Only private PostgreSQL socket is permitted")
            db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
            for name in ("source_document", "ingestion_asset", "official_price_quote",
                         "official_source_review", "ingestion_checkpoint"):
                db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
            db.execute("CREATE INDEX quote_identity_font_run_resume ON official_price_quote(quote_key,observed_on DESC)")
            install_cache(db)
            db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
                       "VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2012-06-22',%s,%s)",
                       (SHA, URL, self.body, Jsonb({"ingestion_kind": KIND})))
            db.execute("INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on) "
                       "VALUES(%s,%s,'complete',%s,%s,'2012-06-22')", (URL, KIND, OLD, SHA))
            loc = next(iter(CONTROLS))
            old = self.old_by_locator[loc]
            with patch.object(worker, "parser_version", return_value=OLD):
                official_sources.publish_rows(db, [old], SHA, KIND)
            old_key = db.execute("SELECT quote_key FROM official_price_quote WHERE parser_version=%s", (OLD,)).fetchone()[0]
            db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE parser_version=%s", (OLD,))
            subset = [self.by_locator[k] for k in self.changed_locators]
            subset += [r for r in self.rows if r["price"] is not None and r["source_locator"] not in self.changed_locators][:226]
            self.assertEqual(len(subset), 300)
            with patch("pipelines.ingestion.write_pacing.pause_between_batches",
                       side_effect=WorkDeferred("forced after first committed batch")):
                with self.assertRaises(WorkDeferred):
                    official_sources.publish_rows(db, subset, SHA, KIND, source_url=URL)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE parser_version=%s", (NEW,)
            ).fetchone()[0], 256)
            dirty, dirty_since = db.execute(
                "SELECT dirty,dirty_since FROM official_catalog_current WHERE quote_key=%s", (old_key,)
            ).fetchone()
            self.assertTrue(dirty)
            self.assertIsNotNone(dirty_since)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
                "AND step='official:complete'", (SHA, NEW)
            ).fetchone()[0], 0)
            with patch("pipelines.ingestion.write_pacing.pause_between_batches"):
                official_sources.publish_rows(db, subset, SHA, KIND, source_url=URL)
                official_sources.publish_rows(db, subset, SHA, KIND, source_url=URL)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE parser_version=%s", (NEW,)
            ).fetchone()[0], 300)
            self.assertEqual(db.execute(
                "SELECT payload,dirty,dirty_since FROM official_catalog_current WHERE quote_key=%s", (old_key,)
            ).fetchone(), (None, False, None))


if __name__ == "__main__":
    unittest.main()
