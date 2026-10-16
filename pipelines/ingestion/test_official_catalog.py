"""Persistent official cache parity, completion, rollback and invalidation."""

import os
import re
import threading
import time
import unittest
import uuid
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psycopg import Error as DatabaseError
from psycopg.rows import dict_row

from . import dane_weekly, official_catalog, official_sources, worker, write_pacing
from .resumable_inputs import WorkDeferred

TABLES = (
    "source_document",
    "official_price_quote",
    "official_source_review",
    "ingestion_asset",
    "ingestion_checkpoint",
)
MIGRATION = Path(__file__).parent / "migrations/20260927_007_official_catalog.sql"
OLDER_INSERT = Path(__file__).parent / "migrations/20261004_054_official_catalog_previous_date.sql"
DIRTY_FIFO = Path(__file__).parent / "migrations/20261005_055_official_catalog_dirty_fifo.sql"
SUPERSESSION = Path(__file__).parent / "migrations/20260928_025_official_quote_supersession.sql"


def install_cache(db, *, temporary=True):
    migration = MIGRATION.read_text()
    migration = re.sub(r"^GRANT .*;\n", "", migration, flags=re.MULTILINE)
    if temporary:
        migration = migration.replace(
            "CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"
        )
        migration = migration.replace(
            "CREATE OR REPLACE FUNCTION dirty_",
            "CREATE OR REPLACE FUNCTION pg_temp.dirty_",
        )
        migration = migration.replace(
            "EXECUTE FUNCTION dirty_", "EXECUTE FUNCTION pg_temp.dirty_"
        )
    db.execute(migration)
    older_insert = OLDER_INSERT.read_text()
    if temporary:
        older_insert = older_insert.replace(
            "CREATE OR REPLACE FUNCTION dirty_",
            "CREATE OR REPLACE FUNCTION pg_temp.dirty_",
        )
    db.execute(older_insert)
    dirty_fifo = DIRTY_FIFO.read_text()
    if temporary:
        dirty_fifo = dirty_fifo.replace(
            "CREATE OR REPLACE FUNCTION stamp_official_catalog_dirty_since()",
            "CREATE OR REPLACE FUNCTION pg_temp.stamp_official_catalog_dirty_since()",
        ).replace(
            "EXECUTE FUNCTION stamp_official_catalog_dirty_since()",
            "EXECUTE FUNCTION pg_temp.stamp_official_catalog_dirty_since()",
        )
    db.execute(dirty_fifo)
    supersession = re.sub(r"^GRANT .*;\n", "", SUPERSESSION.read_text(), flags=re.MULTILINE)
    if temporary:
        supersession = supersession.replace(
            "CREATE OR REPLACE VIEW published_official_price",
            "CREATE OR REPLACE TEMP VIEW published_official_price",
        )
    db.execute(supersession)


def quote(day="2026-09-20", price=2000, locator="row 1", product="Cacao"):
    return {
        "source_locator": locator,
        "date": day,
        "product_id": product.lower(),
        "product_name": product,
        "category": "Cacao",
        "publisher": "Official test",
        "series": "farmgate",
        "basis": "Referencia por kilogramo",
        "currency": "COP",
        "unit": "kg",
        "market": "Colombia",
        "price": price,
        "details": {},
    }


@unittest.skipUnless(
    os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1",
    "Explicit opt-in for isolated PostgreSQL cache checks",
)
class OfficialCatalogPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='15s'")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE INDEX quote_identity ON official_price_quote(quote_key,observed_on DESC)"
        )
        install_cache(self.db)
        self.catalog_sleep = self.enterContext(patch.object(official_catalog, "_sleep"))
        self.enterContext(patch.object(write_pacing.time, "sleep"))
        self.enterContext(patch.object(write_pacing, "clock", return_value=100))
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        self.version = self.enterContext(
            patch.object(worker, "parser_version", return_value="fixture-v1")
        )

    def original(self, label, retrieved="2026-09-20T00:00:00Z"):
        did = sha256(label.encode()).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at) VALUES(%s,%s,'fixture',%s,'text/html','original','',%s,%s)",
            (did, label, "https://example.invalid/" + label, label.encode(), retrieved),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,'colombia-pork-pdf',%s,'pending')",
            ("https://example.invalid/" + label, did),
        )
        return did

    def publish(self, did, rows):
        return official_sources.publish_rows(self.db, rows, did, "colombia-pork-pdf")

    def cache(self):
        return self.db.execute(
            "SELECT quote_key,payload,dirty FROM official_catalog_current ORDER BY quote_key"
        ).fetchall()

    def assert_parity(self):
        keys = [row[0] for row in self.cache()]
        with self.db.cursor(row_factory=dict_row) as cursor:
            expected = cursor.execute(
                official_catalog.LATEST_FOR_KEYS_SQL, (keys,)
            ).fetchall()
        # JSONB's dates/timestamps are serialized; normalize through PostgreSQL.
        actual = {
            row[0]: row[1] for row in self.cache() if row[1] is not None and not row[2]
        }
        expected_json = self.db.execute(
            "SELECT to_jsonb(q) FROM (" + official_catalog.LATEST_FOR_KEYS_SQL + ") q",
            (keys,),
        ).fetchall()
        self.assertEqual(actual, {row[0]["quote_key"]: row[0] for row in expected_json})
        return expected

    def test_publication_latest_previous_and_older_replay_match_canonical_values(self):
        current = self.original("current", "2026-09-25T00:00:00Z")
        old = self.original("old", "2026-09-10T00:00:00Z")
        self.publish(
            current,
            [
                quote("2026-09-24", 2100, "latest"),
                quote("2026-09-23", 2000, "previous"),
            ],
        )
        self.publish(old, [quote("2026-09-24", 1800, "old")])
        row = self.assert_parity()[0]
        self.assertEqual(
            (row["price"], row["previous_price"], row["document_id"]),
            (2100, 2000, current),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM ingestion_checkpoint WHERE step='official:complete'"
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            3,
        )

    def test_review_only_refreshes_prior_keys_and_corrected_parse_republishes(self):
        did = self.original("review")
        self.publish(did, [quote()])
        self.version.return_value = "review-v2"
        row = quote(price=None)
        row["details"] = {"quality_issue": "Ambiguous label"}
        self.publish(did, [row])
        self.assertEqual([(p, d) for _, p, d in self.cache()], [(None, False)])
        self.version.return_value = "corrected-v3"
        self.publish(did, [quote(price=2200)])
        self.assertEqual(self.assert_parity()[0]["price"], 2200)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[
                0
            ],
            1,
        )

    def test_weekly_originals_supersede_changed_product_identity_and_replay_once(self):
        cases = (
            (
                "dane_weekly_2021_10_02_page62.pdf",
                "Sem_02oct_2021_08oct_2021.pdf",
                "PDF page 62,table 1,column 1,line 5",
                "Café molido (continución)",
                "Café molido",
                19354,
            ),
            (
                "dane_weekly_2026_01_31_page64.pdf",
                "bol-SIPSASemanal-31ene06feb-2026.pdf",
                "PDF page 64,table 1,column 1,line 10",
                "Fríjol enlatado Galletas dulces redondas con crema",
                "Galletas dulces redondas con crema",
                24000,
            ),
        )
        for fixture, url, locator, old_name, corrected_name, price in cases:
            with self.subTest(fixture=fixture):
                body = (Path(__file__).parent / "testdata" / fixture).read_bytes()
                corrected = next(
                    row for row in dane_weekly.parse_pdf(body, url)
                    if row["source_locator"] == locator
                )
                self.assertEqual((corrected["product_name"], corrected["price"]), (corrected_name, price))
                old = deepcopy(corrected)
                old["product_name"] = old_name
                old["product_id"] = worker.slug(old_name)
                old["identity_dimensions"] = {"source_product": old_name}
                did = self.original(fixture)
                self.version.return_value = "official-v2:dane-weekly-v6"
                self.publish(did, [old])
                old_key = self.db.execute(
                    "SELECT quote_key FROM official_price_quote WHERE document_id=%s",
                    (did,),
                ).fetchone()[0]
                self.version.return_value = "official-v2:dane-weekly-v7"
                self.publish(did, [corrected])
                self.publish(did, [corrected])
                self.assertEqual(
                    self.db.execute(
                        "SELECT count(*) FROM official_price_quote WHERE document_id=%s",
                        (did,),
                    ).fetchone()[0],
                    2,
                )
                self.assertEqual(
                    self.db.execute(
                        "SELECT product_name,price FROM published_official_price WHERE document_id=%s",
                        (did,),
                    ).fetchall(),
                    [(corrected_name, price)],
                )
                self.assertEqual(
                    self.db.execute(
                        "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
                        (old_key,),
                    ).fetchone(),
                    (None, False),
                )

    def test_pork_legacy_locator_retires_only_after_exact_market_row_is_retained(self):
        did = self.original("pork-legacy-market-row")
        old_locator = "PDF page 2, Cerdo en pie, y 258.8"
        old = quote("2025-07-31", 8311, old_locator, "Cerdo en pie")
        old.update(series="porkcolombia-monthly", market="Antioquia", unit="kg en pie", source_page=2)
        self.publish(did, [old])
        self.version.return_value = "fixture-v2"
        replacement = {**old, "source_locator": old_locator + ", market Antioquia"}
        self.publish(did, [replacement])
        self.assertEqual(
            self.db.execute(
                "SELECT source_locator FROM official_source_review WHERE document_id=%s",
                (did,),
            ).fetchall(),
            [(old_locator,)],
        )
        self.assertEqual(
            self.db.execute(
                "SELECT source_locator,price FROM published_official_price WHERE document_id=%s",
                (did,),
            ).fetchall(),
            [(replacement["source_locator"], 8311)],
        )
        self.publish(did, [replacement])
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s",
                (did,),
            ).fetchone()[0],
            1,
        )

    def test_pork_legacy_locator_rejects_changed_price_without_exact_match(self):
        did = self.original("pork-legacy-price-mismatch")
        old_locator = "PDF page 2, Cerdo en pie, y 258.8"
        old = quote("2025-07-31", 8311, old_locator, "Cerdo en pie")
        old.update(series="porkcolombia-monthly", market="Antioquia", unit="kg en pie", source_page=2)
        self.publish(did, [old])
        self.version.return_value = "fixture-v2"
        replacement = {**old, "price": 8312, "source_locator": old_locator + ", market Antioquia"}
        with self.assertRaisesRegex(ValueError, "omitted previously published source locators"):
            self.publish(did, [replacement])
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s",
                (did,),
            ).fetchone()[0],
            0,
        )

    def test_partial_new_parse_requires_explicit_review_for_missing_locator(self):
        did = self.original("removed-source-row")
        self.publish(
            did,
            [
                quote(locator="printed row 1", product="Old one"),
                quote(locator="printed row 2", product="Old two"),
            ],
        )
        self.version.return_value = "fixture-v2"
        corrected = quote(locator="printed row 1", product="New")
        with self.assertRaisesRegex(ValueError, "omitted previously published source locators"):
            self.publish(did, [corrected])
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_price_quote WHERE document_id=%s",
                (did,),
            ).fetchone()[0],
            2,
        )
        self.assertFalse(any(row[2] for row in self.cache()))
        self.assertEqual(
            {row[0] for row in self.db.execute(
                "SELECT product_name FROM published_official_price WHERE document_id=%s",
                (did,),
            ).fetchall()},
            {"Old one", "Old two"},
        )
        review = quote(locator="printed row 2", product="Old two", price=None)
        review["details"] = {"quality_issue": "Printed row requires source review"}
        self.publish(did, [corrected, review])
        self.publish(did, [corrected, review])
        self.assertEqual(
            self.db.execute(
                "SELECT source_locator,parser_version FROM official_source_review WHERE document_id=%s",
                (did,),
            ).fetchall(),
            [("printed row 2", "fixture-v2")],
        )
        self.assertEqual(
            self.db.execute(
                "SELECT product_name FROM published_official_price WHERE document_id=%s",
                (did,),
            ).fetchall(),
            [("New",)],
        )

    def test_asset_reviews_invalidate_and_checked_at_does_not(self):
        did = self.original("asset")
        self.publish(did, [quote()])
        before = self.db.execute(
            "SELECT xmin::text FROM official_catalog_current"
        ).fetchone()
        self.db.execute("UPDATE ingestion_asset SET checked_at=now(),status='complete'")
        self.assertEqual(
            self.db.execute(
                "SELECT xmin::text FROM official_catalog_current"
            ).fetchone(),
            before,
        )
        self.db.execute("UPDATE ingestion_asset SET status='review',observed_on=NULL")
        self.assertTrue(self.cache()[0][2])
        self.assertEqual(official_catalog.refresh_dirty(self.db), 1)
        self.assertEqual(self.cache()[0][1:], (None, False))
        self.db.execute("UPDATE ingestion_asset SET status='pending'")
        self.assertTrue(self.cache()[0][2])
        official_catalog.refresh_dirty(self.db)
        self.assertEqual(self.assert_parity()[0]["price"], 2000)

    def test_review_of_previous_price_refreshes_distinct_previous_date(self):
        did = self.original("previous")
        self.publish(
            did,
            [
                quote("2026-09-24", 2200, "new"),
                quote("2026-09-23", 2100, "prior"),
                quote("2026-09-22", 2000, "old"),
            ],
        )
        self.db.execute(
            "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,'prior','review','{}','ambiguous')",
            (did,),
        )
        self.assertTrue(self.cache()[0][2])
        official_catalog.refresh_dirty(self.db)
        self.assertEqual(self.assert_parity()[0]["previous_price"], 2000)

    def test_partial_batch_can_refresh_valid_quotes_without_original_completion(self):
        did = self.original("partial")
        rows = [quote(locator=f"row {n}", product=f"Product {n}") for n in range(2001)]
        worker.RUN_DEADLINE.set(150)
        with (
            patch.object(
                official_sources,
                "time",
                SimpleNamespace(monotonic=Mock(side_effect=[100, 200])),
            ),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, rows)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            256,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )
        self.assertTrue(all(row[2] for row in self.cache()))
        self.assertEqual(official_catalog.refresh_dirty(self.db, limit=10), 10)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )
        worker.RUN_DEADLINE.set(None)
        self.publish(did, rows)
        self.assertEqual(len(self.assert_parity()), 2001)
        self.assertFalse(any(row[2] for row in self.cache()))

    def test_document_refresh_commits_bounded_batches_and_resumes_without_false_completion(self):
        did = self.original("bounded-catalog-refresh")
        rows = [
            quote(locator=f"printed row {n}", product=f"Product {n}", price=2000 + n)
            for n in range(130)
        ]
        # A second observation verifies the complete previous-price payload too.
        rows.append(
            quote("2026-09-19", 1800, "previous printed row", "Product 0")
        )
        original_refresh = official_catalog.refresh_keys
        batches = []

        def expire_after_first_batch(db, keys):
            batches.append(len(keys))
            result = original_refresh(db, keys)
            if len(batches) == 1:
                worker.RUN_DEADLINE.set(0)
            return result

        with (
            patch.object(official_catalog, "refresh_keys", side_effect=expire_after_first_batch),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, rows)
        self.assertEqual(batches, [64])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_catalog_current WHERE NOT dirty").fetchone()[0],
            64,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FILTER (WHERE NOT dirty AND dirty_since IS NULL),"
                            "count(*) FILTER (WHERE dirty AND dirty_since IS NOT NULL) "
                            "FROM official_catalog_current").fetchone(),
            (64, 66),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE step='official:complete'").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'official:catalog-start:%'").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            131,
        )

        worker.RUN_DEADLINE.set(None)
        resumed_batches = []

        def record_batch(db, keys):
            resumed_batches.append(len(keys))
            return original_refresh(db, keys)

        with patch.object(official_catalog, "refresh_keys", side_effect=record_batch):
            self.publish(did, rows)
        self.assertEqual(resumed_batches, [64, 2])
        self.assertFalse(any(row[2] for row in self.cache()))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE dirty_since IS NOT NULL"
        ).fetchone()[0], 0)
        self.assertEqual(len(self.assert_parity()), 130)
        first = self.db.execute(
            "SELECT payload FROM official_catalog_current WHERE payload->>'product_name'='Product 0'"
        ).fetchone()[0]
        self.assertEqual((first["price"], first["previous_price"]), (2000, 1800))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE step='official:complete'").fetchone()[0],
            1,
        )
        with patch.object(official_catalog, "refresh_keys", side_effect=record_batch):
            self.publish(did, rows)
        self.assertEqual(resumed_batches, [64, 2])

    def test_revision_and_bogota_day_restart_completed_catalog_batches(self):
        did = self.original("catalog-revision-and-day")
        rows = [quote(locator=f"printed row {n}", product=f"Product {n}") for n in range(130)]
        self.publish(did, rows)
        original_refresh = official_catalog.refresh_keys
        batches = []

        def record_batch(db, keys):
            batches.append(len(keys))
            return original_refresh(db, keys)

        self.version.return_value = "fixture-v2"
        corrected = deepcopy(rows)
        corrected[0]["price"] = 2300
        with patch.object(official_catalog, "refresh_keys", side_effect=record_batch):
            self.publish(did, corrected)
        self.assertEqual(batches, [64, 64, 2])
        self.assertEqual(len(self.assert_parity()), 130)
        self.assertEqual(
            self.db.execute("SELECT payload->>'price' FROM official_catalog_current "
                            "WHERE payload->>'product_name'='Product 0'").fetchone()[0],
            "2300.0",
        )
        batches.clear()
        with patch.object(official_catalog, "_bogota_day", return_value=date.today() + timedelta(days=2)), \
             patch.object(official_catalog, "refresh_keys", side_effect=record_batch):
            self.publish(did, corrected)
        self.assertEqual(batches, [64, 64, 2])
        self.assertEqual(len(self.assert_parity()), 130)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
                            "AND processor_version='fixture-v2' AND step LIKE 'official:catalog-start:%%'",
                            (did,)).fetchone()[0],
            2,
        )

    def test_review_trigger_redirties_only_affected_completed_batch_key(self):
        did = self.original("catalog-review-after-partial-refresh")
        rows = [quote(locator=f"printed row {n}", product=f"Product {n}") for n in range(130)]
        original_refresh = official_catalog.refresh_keys

        def expire_after_first_batch(db, keys):
            result = original_refresh(db, keys)
            worker.RUN_DEADLINE.set(0)
            return result

        with patch.object(official_catalog, "refresh_keys", side_effect=expire_after_first_batch), \
             self.assertRaises(WorkDeferred):
            self.publish(did, rows)
        reviewed_key = self.db.execute(
            "SELECT quote_key FROM official_catalog_current WHERE NOT dirty ORDER BY quote_key LIMIT 1"
        ).fetchone()[0]
        locator = self.db.execute(
            "SELECT source_locator FROM official_price_quote WHERE document_id=%s AND quote_key=%s LIMIT 1",
            (did, reviewed_key),
        ).fetchone()[0]
        self.db.execute(
            "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
            "VALUES(%s,%s,'fixture-review','{}'::jsonb,'Source-backed review')",
            (did, locator),
        )
        self.assertTrue(self.db.execute(
            "SELECT dirty FROM official_catalog_current WHERE quote_key=%s", (reviewed_key,)
        ).fetchone()[0])
        worker.RUN_DEADLINE.set(None)
        batches = []

        def record_batch(db, keys):
            batches.append(list(keys))
            return original_refresh(db, keys)

        with patch.object(official_catalog, "refresh_keys", side_effect=record_batch):
            self.publish(did, rows)
        self.assertEqual(sum(map(len, batches)), 67)
        self.assertEqual(sum(reviewed_key in batch for batch in batches), 1)
        self.assertEqual(
            self.db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
                            (reviewed_key,)).fetchone(),
            (None, False),
        )
        self.assertEqual(len(self.assert_parity()), 129)

    def test_document_refresh_paces_only_between_batches(self):
        did = self.original("paced-catalog-refresh")
        self.publish(
            did,
            [quote(locator=f"row {n}", product=f"Product {n}") for n in range(194)],
        )
        self.catalog_sleep.reset_mock()
        with patch.object(official_catalog, "_clock",
                          side_effect=[0.0, 0.1, 0.1, 2.1, 2.1, 12.1, 12.1, 13.1]), \
             patch.object(write_pacing, "yield_to_active_readers") as reader_yield:
            self.assertEqual(official_catalog.refresh_document(self.db, did), 194)
        self.assertEqual(reader_yield.call_count, 4)
        self.assertEqual(
            [call.args[0] for call in self.catalog_sleep.call_args_list],
            [0.25, 2.0, 5.0],
        )
        self.assertEqual(len(self.assert_parity()), 194)

    def test_document_pacing_defers_before_sleep_without_completion(self):
        did = self.original("pace-deadline")
        rows = [quote(locator=f"row {n}", product=f"Product {n}") for n in range(130)]
        worker.RUN_DEADLINE.set(1.5)
        with (
            patch.object(official_sources, "time", SimpleNamespace(monotonic=Mock(return_value=0))),
            patch.object(write_pacing, "yield_to_active_readers"),
            patch.object(official_catalog, "_clock", side_effect=[0.0, 1.0]),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, rows)
        self.catalog_sleep.assert_not_called()
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_catalog_current WHERE NOT dirty").fetchone()[0],
            64,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND step='official:complete'", (did,)).fetchone()[0],
            0,
        )
        worker.RUN_DEADLINE.set(None)
        self.publish(did, rows)
        self.assertEqual(len(self.assert_parity()), 130)

    def test_document_refresh_never_sleeps_inside_outer_transaction(self):
        did = self.original("no-pacing-inside-outer-transaction")
        self.publish(
            did,
            [quote(locator=f"row {n}", product=f"Product {n}") for n in range(130)],
        )
        before = self.cache()
        self.catalog_sleep.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "rollback"), \
             patch.object(write_pacing, "yield_to_active_readers") as reader_yield, \
             self.db.transaction():
            self.assertEqual(official_catalog.refresh_document(self.db, did), 130)
            raise RuntimeError("rollback")
        self.catalog_sleep.assert_not_called()
        reader_yield.assert_not_called()
        self.assertEqual(self.cache(), before)

    def test_interrupted_correction_keeps_old_identity_dirty_until_tombstoned(self):
        did = self.original("corrected-late-batch")
        rows = [
            quote(locator=f"printed row {n}", product=f"Product {n}")
            for n in range(70)
        ]
        self.publish(did, rows)
        old_key, locator = self.db.execute(
            "SELECT quote_key,source_locator FROM official_price_quote "
            "WHERE document_id=%s ORDER BY quote_key DESC LIMIT 1",
            (did,),
        ).fetchone()
        self.version.return_value = "fixture-v2"
        corrected = deepcopy(rows)
        changed = next(row for row in corrected if row["source_locator"] == locator)
        changed["product_id"] = "corrected-product"
        changed["product_name"] = "Corrected product"
        original_refresh = official_catalog.refresh_keys
        batches = []

        def expire_after_first_batch(db, keys):
            batches.append(len(keys))
            result = original_refresh(db, keys)
            worker.RUN_DEADLINE.set(0)
            return result

        with (
            patch.object(official_catalog, "refresh_keys", side_effect=expire_after_first_batch),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, corrected)
        self.assertEqual(batches, [64])
        old_payload, old_dirty = self.db.execute(
            "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
            (old_key,),
        ).fetchone()
        self.assertIsNotNone(old_payload)
        self.assertTrue(old_dirty)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='fixture-v2' AND step='official:complete'", (did,)).fetchone()[0],
            0,
        )
        worker.RUN_DEADLINE.set(None)
        self.publish(did, corrected)
        self.assertEqual(
            self.db.execute(
                "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
                (old_key,),
            ).fetchone(),
            (None, False),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            140,
        )
        self.assertEqual(len(self.assert_parity()), 70)

    def test_corrected_identity_is_dirty_before_first_quote_batch_defers(self):
        did = self.original("corrected-before-first-batch")
        self.publish(did, [quote(locator="original row", product="Old product")])
        old_key = self.db.execute(
            "SELECT quote_key FROM official_price_quote WHERE document_id=%s", (did,)
        ).fetchone()[0]
        self.version.return_value = "fixture-v2"
        rows = [quote(locator="original row", product="Corrected product")]
        rows.extend(
            quote(locator=f"new row {n}", product=f"Additional product {n}")
            for n in range(2000)
        )
        worker.RUN_DEADLINE.set(150)
        with (
            patch.object(
                official_sources,
                "time",
                SimpleNamespace(monotonic=Mock(side_effect=[100, 200])),
            ),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, rows)
        old_payload, old_dirty = self.db.execute(
            "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
            (old_key,),
        ).fetchone()
        self.assertEqual(old_payload["product_name"], "Old product")
        self.assertTrue(old_dirty)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            257,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='fixture-v2' AND step='official:complete'", (did,)).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
                            "AND processor_version='fixture-v2' AND step LIKE 'official:catalog-start:%%'",
                            (did,)).fetchone()[0],
            0,
        )
        worker.RUN_DEADLINE.set(None)
        self.publish(did, rows)
        self.assertEqual(
            self.db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s", (old_key,)).fetchone(),
            (None, False),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            2002,
        )
        self.assertEqual(len(self.assert_parity()), 2001)

    def test_preinvalidation_recovers_when_quote_write_never_starts(self):
        did = self.original("deferred-before-quote-write")
        self.publish(did, [quote(locator="printed row", product="Original")])
        old_key = self.db.execute(
            "SELECT quote_key FROM official_price_quote WHERE document_id=%s", (did,)
        ).fetchone()[0]
        self.version.return_value = "fixture-v2"
        worker.RUN_DEADLINE.set(0)
        with self.assertRaises(WorkDeferred):
            self.publish(did, [quote(locator="printed row", product="Correction")])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            1,
        )
        self.assertTrue(
            self.db.execute(
                "SELECT dirty FROM official_catalog_current WHERE quote_key=%s", (old_key,)
            ).fetchone()[0]
        )
        worker.RUN_DEADLINE.set(None)
        self.assertEqual(official_catalog.refresh_dirty(self.db), 1)
        original_payload, dirty = self.db.execute(
            "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s", (old_key,)
        ).fetchone()
        self.assertEqual(original_payload["product_name"], "Original")
        self.assertFalse(dirty)
        self.publish(did, [quote(locator="printed row", product="Correction")])
        self.assertEqual(
            self.db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s", (old_key,)).fetchone(),
            (None, False),
        )
        self.assertEqual(len(self.assert_parity()), 1)

    def test_failed_final_refresh_rolls_back_completion_but_keeps_durable_quote_batches(
        self,
    ):
        did = self.original("refresh-fails")
        with (
            patch.object(
                official_catalog,
                "refresh_keys",
                side_effect=RuntimeError("cache unavailable"),
            ),
            self.assertRaisesRegex(RuntimeError, "cache unavailable"),
        ):
            self.publish(did, [quote()])
        self.assertTrue(self.cache()[0][2])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE step='official:complete'").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'official:catalog-start:%'").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            1,
        )
        self.publish(did, [quote()])
        self.assertEqual(self.assert_parity()[0]["price"], 2000)

    def test_outer_rollback_includes_quotes_cache_and_original_completion(self):
        did = self.original("rollback")
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.transaction():
            self.publish(did, [quote()])
            self.assertEqual(len(self.cache()), 1)
            raise RuntimeError("rollback")
        self.assertEqual(self.cache(), [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )

    def test_outer_rollback_restores_preinvalidation_of_existing_identity(self):
        did = self.original("rollback-existing-identity")
        self.publish(did, [quote(locator="printed row", product="Old product")])
        old_key = self.db.execute(
            "SELECT quote_key FROM official_price_quote WHERE document_id=%s", (did,)
        ).fetchone()[0]
        before = self.db.execute(
            "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
            (old_key,),
        ).fetchone()
        before_checkpoints = self.db.execute(
            "SELECT processor_version,step,records FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step",
            (did,),
        ).fetchall()
        self.version.return_value = "fixture-v2"
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.transaction():
            self.publish(did, [quote(locator="printed row", product="Corrected product")])
            raise RuntimeError("rollback")
        self.assertEqual(
            self.db.execute(
                "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
                (old_key,),
            ).fetchone(),
            before,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT processor_version,step,records FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step",
                (did,),
            ).fetchall(),
            before_checkpoints,
        )

    def test_bootstrap_batches_are_resumable_without_dropping_cache_rows(self):
        did = self.original("bootstrap")
        self.publish(
            did, [quote(product=f"P{n}", locator=f"row {n}") for n in range(5)]
        )
        self.db.execute("UPDATE official_catalog_current SET dirty=true,payload=NULL")
        result = official_catalog.bootstrap(self.db, batch_size=2)
        self.assertEqual(result["keys"], 5)
        self.assertEqual(len(self.assert_parity()), 5)
        self.assertEqual(
            official_catalog.bootstrap(self.db, after=result["last_key"])["keys"], 0
        )

    def test_migration_seeds_missing_old_quotes_without_dirtying_clean_payloads(self):
        did = self.original("migration-seed")
        self.publish(did, [quote()])
        before = self.cache()
        # This clean existing key remains intact on migration reapplication.
        install_cache(self.db)
        self.assertEqual(self.cache(), before)
        # Simulate an old database with quotes predating dirty triggers/cache.
        self.db.execute(
            "ALTER TABLE official_price_quote DISABLE TRIGGER official_catalog_quotes"
        )
        second = quote(product="Legacy", locator="legacy")
        with (
            patch.object(official_catalog, "mark_document_dirty", return_value=None),
            patch.object(official_catalog, "refresh_document", return_value=0),
        ):
            self.publish(did, [second])
        self.assertEqual(len(self.cache()), 1)
        install_cache(self.db)
        self.assertEqual(len(self.cache()), 2)
        self.assertEqual(sum(row[2] for row in self.cache()), 1)
        self.assertEqual(official_catalog.refresh_dirty(self.db), 1)
        self.assertEqual(len(self.assert_parity()), 2)

    def test_concurrent_review_cannot_be_overwritten_by_clean_stale_refresh(self):
        # TEMP relations cannot be shared across sessions. Use a disposable schema
        # only after proving this connection is the private local test cluster.
        first, second = worker.connect(), worker.connect()
        self.assertTrue(first.info.host.startswith(("/tmp/agro-catalog-pg-", "/tmp/agro-unified-catalog-pg-")))
        self.assertEqual(second.info.host, first.info.host)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        name = "cache_concurrency_" + uuid.uuid4().hex
        first.execute(f"CREATE SCHEMA {name}")
        self.addCleanup(lambda: first.execute(f"DROP SCHEMA {name} CASCADE"))
        for db in (first, second):
            db.execute(f"SET search_path={name}; SET statement_timeout='5s'")
        for table in TABLES:
            first.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        install_cache(first, temporary=False)
        self.db = first
        did = self.original("concurrent-review")
        self.publish(did, [quote()])
        key = self.cache()[0][0]
        errors = []
        started = threading.Event()

        def reviewer():
            try:
                started.set()
                second.execute(
                    "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,'row 1','review','{}','Concurrent withdrawal')",
                    (did,),
                )
            except DatabaseError as error:
                errors.append(error)

        with first.transaction():
            first.execute(
                "SELECT quote_key FROM official_catalog_current WHERE quote_key=%s FOR UPDATE",
                (key,),
            ).fetchall()
            thread = threading.Thread(target=reviewer)
            thread.start()
            self.assertTrue(started.wait(1))
            until = time.monotonic() + 3
            while time.monotonic() < until:
                waiting = first.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                    (second.info.backend_pid,),
                ).fetchone()
                if waiting and waiting[0] == "Lock":
                    break
                time.sleep(0.01)
            else:
                self.fail("Concurrent review did not wait for the cache row lock")
            official_catalog.refresh_keys(first, [key])
            self.assertFalse(self.cache()[0][2])
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(
            self.cache()[0][2],
            "Committed review must invalidate the refresh computed before it",
        )
        official_catalog.refresh_dirty(first)
        self.assertEqual(self.cache()[0][1:], (None, False))


if __name__ == "__main__":
    unittest.main()
