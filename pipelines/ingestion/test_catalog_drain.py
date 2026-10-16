"""Bounded official-catalog drain behavior and owned-PG reader pacing tests."""

import os
import threading
import time
import unittest
from unittest.mock import patch

import psycopg

from . import catalog_drain, official_catalog
from . import test_official_catalog_dirty_fifo_pg as fifo_tests


class DrainCoreTests(unittest.TestCase):
    def run_window(self, counts, *, pending=True, run_deadline=None, batch_size=2, max_batches=3):
        calls = []
        pauses = []
        clock_values = iter([float(i) for i in range(100)])

        def clock():
            return next(clock_values)

        def refresh(_db, *, limit, priority_keys):
            calls.append((limit, priority_keys))
            return counts[len(calls) - 1]

        result = catalog_drain._drain_window(
            object(), refresh_dirty=refresh, priority_keys=("a", "b"),
            run_deadline=run_deadline,
            has_pending=lambda _db: pending,
            pause_between_batches=lambda *_args: pauses.append(True),
            time_budget_seconds=30, batch_size=batch_size, max_batches=max_batches,
            clock=clock,
        )
        return result, calls, pauses

    def test_priorities_are_only_passed_to_first_batch(self):
        result, calls, pauses = self.run_window([2, 2, 1], batch_size=2)
        self.assertEqual(calls, [(2, ("a", "b")), (2, ()), (2, ())])
        self.assertEqual(len(pauses), 2)
        self.assertEqual((result.refreshed, result.batches, result.status), (5, 3, "drained"))

    def test_queue_exhaustion_does_not_pause_after_final_batch(self):
        result, calls, pauses = self.run_window([1], batch_size=2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(pauses, [])
        self.assertEqual((result.stop_reason, result.more_may_remain), ("queue_exhausted", False))

    def test_batch_cap_reports_remaining_work(self):
        result, _calls, pauses = self.run_window([2, 2, 2], batch_size=2, max_batches=2)
        self.assertEqual(len(pauses), 1)
        self.assertEqual((result.stop_reason, result.more_may_remain), ("batch_cap", True))

    def test_run_deadline_is_checked_after_committed_batch(self):
        ticks = iter([10.0, 10.0, 12.0, 12.0])
        result = catalog_drain._drain_window(
            object(), refresh_dirty=lambda *_a, **_k: 2, priority_keys=(),
            run_deadline=11.0, has_pending=lambda _db: self.fail("deadline should stop before probe"),
            pause_between_batches=lambda *_a: self.fail("deadline should stop before pause"),
            time_budget_seconds=30, batch_size=2, max_batches=2,
            clock=lambda: next(ticks),
        )
        self.assertEqual(result.stop_reason, "run_deadline")
        self.assertEqual((result.refreshed, result.batches, result.more_may_remain), (2, 1, True))

    def test_priority_count_is_bounded_and_deduplicated(self):
        self.assertEqual(catalog_drain._drain_window(
            object(), refresh_dirty=lambda *_a, **_k: 0,
            priority_keys=("a", "a"), run_deadline=None,
            has_pending=lambda _db: False, pause_between_batches=lambda *_a: None,
            time_budget_seconds=30, batch_size=2, max_batches=1,
        ).status, "drained")
        with self.assertRaises(ValueError):
            catalog_drain._drain_window(
                object(), refresh_dirty=lambda *_a, **_k: 0,
                priority_keys=tuple("abcdef"), run_deadline=None,
                has_pending=lambda _db: False, pause_between_batches=lambda *_a: None,
                time_budget_seconds=30, batch_size=2, max_batches=1,
            )


@unittest.skipUnless(os.environ.get("AGRO_CATALOG_DRAIN_TEST") == "1",
                     "Explicit owned Unix PostgreSQL opt-in")
class CatalogDrainReaderPacingPostgres(unittest.TestCase):
    """The real worker helper must yield to an active agro_reader between commits."""

    def setUp(self):
        fifo_tests.DirtyCatalogFifoPostgres.setUp(self)
        fifo_tests.DirtyCatalogFifoPostgres.install_fifo(self)

    def tearDown(self):
        fifo_tests.DirtyCatalogFifoPostgres.tearDown(self)

    def seed_history(self, size):
        old_doc = "d" * 64
        new_doc = "f" * 64
        keys = [f"{n:064x}" for n in range(1, size + 1)]
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
            "VALUES(%s,'older drain fixture','DANE','https://example.invalid/drain-old.pdf',"
            "'application/pdf','original','2026-10-01',%s),"
            "(%s,'current drain fixture','DANE','https://example.invalid/drain-current.pdf',"
            "'application/pdf','original','2026-10-08',%s)",
            (old_doc, b"retained old source", new_doc, b"retained current source"),
        )
        insert_quotes = """INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,details)
          SELECT %s,'row-'||k,'fixture-v1',k,'item-'||k,'Drain item '||k,
           'Produce','DANE','dane-weekly','Precio mayorista semanal','COP','kg',
           'Mercado fixture',%s::date,%s+n,'{}'::jsonb
          FROM unnest(%s::text[]) WITH ORDINALITY AS x(k,n)"""
        self.db.execute(insert_quotes, (old_doc, "2026-10-01", 1000, keys))
        self.db.execute(insert_quotes, (new_doc, "2026-10-08", 2000, keys))
        quote_before = self.db.execute(
            "SELECT to_jsonb(q)::text,xmin::text FROM official_price_quote q "
            "ORDER BY quote_key,observed_on"
        ).fetchall()
        source_before = self.db.execute(
            "SELECT to_jsonb(d)::text,xmin::text FROM source_document d ORDER BY id"
        ).fetchall()
        return quote_before, source_before

    def assert_raw_history_unchanged(self, quote_before, source_before):
        self.assertEqual(self.db.execute(
            "SELECT to_jsonb(q)::text,xmin::text FROM official_price_quote q "
            "ORDER BY quote_key,observed_on"
        ).fetchall(), quote_before)
        self.assertEqual(self.db.execute(
            "SELECT to_jsonb(d)::text,xmin::text FROM source_document d ORDER BY id"
        ).fetchall(), source_before)

    def test_adapter_waits_for_real_reader_between_committed_chunks(self):
        quote_before, source_before = self.seed_history(201)

        reader_dsn = psycopg.conninfo.make_conninfo(self.dsn, user="agro_reader")
        reader_started = threading.Event()
        reader_finished = threading.Event()
        reader_error = []
        reader_finished_at = []

        def occupy_read_session():
            try:
                with psycopg.connect(reader_dsn, autocommit=True) as reader:
                    if (reader.info.user != "agro_reader"
                            or reader.info.host != self.db.info.host
                            or reader.info.port != self.db.info.port
                            or reader.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
                        raise AssertionError("Reader did not connect to the same owned Unix socket")
                    reader_started.set()
                    reader.execute("SELECT pg_sleep(4)")
            except Exception as exc:  # surfaced on the main test thread
                reader_error.append(exc)
            finally:
                reader_finished_at.append(time.monotonic())
                reader_finished.set()

        reader_thread = threading.Thread(target=occupy_read_session, daemon=True)
        reader_thread.start()
        self.assertTrue(reader_started.wait(5), "reader session did not start")
        active_deadline = time.monotonic() + 5
        while time.monotonic() < active_deadline:
            active = self.db.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='agro_reader' "
                "AND state='active' AND query LIKE 'SELECT pg_sleep%')"
            ).fetchone()[0]
            if active:
                break
            time.sleep(0.02)
        else:
            self.fail("could not observe the owned agro_reader query before the drain")

        actual_refresh = official_catalog.refresh_dirty
        refresh_starts = []

        def measured_refresh(db, *, limit, priority_keys):
            refresh_starts.append(time.monotonic())
            return actual_refresh(db, limit=limit, priority_keys=priority_keys)

        try:
            with patch.object(catalog_drain.official_catalog, "refresh_dirty", measured_refresh):
                result = catalog_drain.drain_official_catalog(
                    self.db, priority_keys=(), run_deadline=time.monotonic() + 20,
                )
        finally:
            reader_thread.join(timeout=8)

        self.assertFalse(reader_thread.is_alive(), "reader thread did not finish")
        self.assertEqual(reader_error, [])
        self.assertEqual(len(refresh_starts), 3)
        self.assertGreaterEqual(refresh_starts[1], reader_finished_at[0])
        self.assertGreaterEqual(refresh_starts[2], reader_finished_at[0])
        self.assertEqual((result.batches, result.refreshed, result.stop_reason),
                         (3, 201, "queue_exhausted"))
        self.assertFalse(result.more_may_remain)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE dirty"
        ).fetchone()[0], 0)
        published = self.db.execute(
            "SELECT payload->>'price',payload->>'previous_price',payload->>'document_id' "
            "FROM official_catalog_current WHERE NOT dirty ORDER BY quote_key"
        ).fetchall()
        self.assertEqual(len(published), 201)
        self.assertEqual({int(row[0]) for row in published}, set(range(2001, 2202)))
        self.assertEqual({int(row[1]) for row in published}, set(range(1001, 1202)))
        self.assertEqual({row[2] for row in published}, {"f" * 64})
        self.assert_raw_history_unchanged(quote_before, source_before)

    def test_adapter_exhaustion_stops_without_unneeded_pacing(self):
        quote_before, source_before = self.seed_history(3)
        with patch.object(catalog_drain.write_pacing, "pause_between_batches",
                          side_effect=AssertionError("no pause after short final batch")):
            result = catalog_drain.drain_official_catalog(
                self.db, priority_keys=(), run_deadline=time.monotonic() + 20,
            )
        self.assertEqual((result.batches, result.refreshed, result.status,
                          result.stop_reason, result.more_may_remain),
                         (1, 3, "drained", "queue_exhausted", False))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE dirty"
        ).fetchone()[0], 0)
        self.assert_raw_history_unchanged(quote_before, source_before)

    def test_adapter_checks_run_deadline_after_committed_chunk(self):
        quote_before, source_before = self.seed_history(201)
        actual_refresh = official_catalog.refresh_dirty
        deadline = time.monotonic() + 2.0

        def finish_after_deadline(db, *, limit, priority_keys):
            count = actual_refresh(db, limit=limit, priority_keys=priority_keys)
            time.sleep(max(0.0, deadline + 0.05 - time.monotonic()))
            return count

        with patch.object(catalog_drain.official_catalog, "refresh_dirty", finish_after_deadline):
            result = catalog_drain.drain_official_catalog(
                self.db, priority_keys=(), run_deadline=deadline,
            )
        self.assertEqual((result.batches, result.refreshed, result.status,
                          result.stop_reason, result.more_may_remain),
                         (1, 100, "bounded", "run_deadline", True))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE dirty"
        ).fetchone()[0], 101)
        self.assert_raw_history_unchanged(quote_before, source_before)


if __name__ == "__main__":
    unittest.main()
