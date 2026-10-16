"""Read opportunities occur only after a durable, idle publication batch."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from psycopg.pq import TransactionStatus

from . import write_pacing
from .resumable_inputs import WorkDeferred


class WritePacingTests(unittest.TestCase):
    def db(self, *, autocommit=True, idle=True):
        db = SimpleNamespace(
            autocommit=autocommit,
            info=SimpleNamespace(transaction_status=(
                TransactionStatus.IDLE if idle else TransactionStatus.INTRANS
            )),
        )
        db.execute = lambda query: SimpleNamespace(fetchone=lambda: (False,))
        return db

    def test_idle_bursts_yield_bounded_read_time(self):
        for elapsed, delay in ((0, .25), (.6, 1.2), (20, 5)):
            with self.subTest(elapsed=elapsed), patch.object(write_pacing, "clock", return_value=100+elapsed), patch.object(write_pacing.time, "sleep") as sleep:
                write_pacing.pause_between_batches(self.db(), 100, None, remaining=True)
                self.assertAlmostEqual(sleep.call_args.args[0], delay)

    def test_last_batch_without_readers_and_outer_transactions_never_sleep(self):
        with patch.object(write_pacing.time, "sleep") as sleep:
            for db, remaining in ((self.db(), False), (self.db(autocommit=False), True), (self.db(idle=False), True)):
                write_pacing.pause_between_batches(db, 100, None, remaining=remaining)
            sleep.assert_not_called()

    def test_final_batch_yields_to_active_reader_before_catalog_transition(self):
        ticks = [100.0]
        db = self.db()
        states = iter([True, True, False])
        db.execute = lambda query: SimpleNamespace(fetchone=lambda: (next(states),))
        with patch.object(write_pacing, "clock", side_effect=lambda: ticks[0]), \
             patch.object(write_pacing.time, "sleep", side_effect=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)) as sleep:
            write_pacing.pause_between_batches(db, 100, None, remaining=False)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(ticks[0], 102)

    def test_reader_yield_is_bounded_and_deadline_defers_committed_batch(self):
        ticks = [100.0]
        db = self.db()
        db.execute = lambda query: SimpleNamespace(fetchone=lambda: (True,))
        with patch.object(write_pacing, "clock", side_effect=lambda: ticks[0]), \
             patch.object(write_pacing.time, "sleep", side_effect=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)):
            write_pacing.pause_between_batches(db, 100, None, remaining=False)
        self.assertEqual(ticks[0], 100 + write_pacing.READER_YIELD_LIMIT_SECONDS)
        ticks[0] = 100
        with patch.object(write_pacing, "clock", side_effect=lambda: ticks[0]), \
             patch.object(write_pacing.time, "sleep", side_effect=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)):
            with self.assertRaisesRegex(WorkDeferred, "Committed official batches retained"):
                write_pacing.pause_between_batches(db, 100, 101.5, remaining=False)
        self.assertLess(ticks[0], 101.5)

    def test_missing_visibility_helper_fails_loudly(self):
        db = self.db()
        def missing(_):
            raise RuntimeError("undefined function public.agro_readers_active")
        db.execute = missing
        with self.assertRaisesRegex(RuntimeError, "undefined function"):
            write_pacing.pause_between_batches(db, 100, None, remaining=False)

    def test_deadline_defers_before_sleep_preserving_committed_work(self):
        with patch.object(write_pacing, "clock", return_value=101), patch.object(write_pacing.time, "sleep") as sleep:
            with self.assertRaisesRegex(WorkDeferred, "Committed official quote batches retained"):
                write_pacing.pause_between_batches(self.db(), 100, 102, remaining=True)
            sleep.assert_not_called()
