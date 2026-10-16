"""Refresh failure cannot mark derived input pointers fresh or trap a caller transaction."""

from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psycopg.errors import LockNotAvailable, QueryCanceled
from psycopg.pq import TransactionStatus

from . import input_projection


class Database:
    def __init__(self, states=(), *, available=True, autocommit=True, idle=True, outcome=True):
        self.states, self.available, self.outcome = states, available, outcome
        self.autocommit = autocommit
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE if idle else TransactionStatus.INTRANS)
        self.queries, self.commits, self.rollbacks = [], 0, 0

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "to_regclass" in sql:
            return SimpleNamespace(fetchone=lambda: ("input_latest_projection_state" if self.available else None,))
        if "FROM input_latest_projection_state" in sql:
            return SimpleNamespace(fetchall=lambda: self.states)
        if "SELECT refresh_input_latest_projection" in sql:
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return SimpleNamespace(fetchone=lambda: (self.outcome,))

    @contextmanager
    def transaction(self):
        self.info.transaction_status = TransactionStatus.INTRANS
        try:
            yield
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1
        finally:
            self.info.transaction_status = TransactionStatus.IDLE


class InputProjectionTests(unittest.TestCase):
    def test_uninstalled_and_already_fresh_do_no_refresh(self):
        for db in (Database(available=False), Database([("department", True), ("municipality", True)])):
            result = input_projection.refresh(db)
            self.assertEqual(result["refreshed"], [])
            self.assertFalse(any("SELECT refresh_input" in q for q, _ in db.queries))

    def test_same_day_complete_delta_is_ready_without_full_rebuild(self):
        db = Database([("department", True), ("municipality", True)])
        result = input_projection.refresh(db)
        self.assertEqual(result["deferred"], [])
        self.assertFalse(any("SELECT refresh_input" in q for q, _ in db.queries))
        status_query = next(q for q, _ in db.queries if "FROM input_latest_projection_state" in q)
        self.assertIn("projection_epoch=source_epoch OR delta_complete", status_query)
        self.assertIn("America/Bogota", status_query)

    def test_deadline_and_caller_transaction_are_preserved(self):
        for db, deadline in ((Database([( "department", False)]), 120),
                             (Database([( "department", False)], autocommit=False), None),
                             (Database([( "department", False)], idle=False), None)):
            with patch.object(input_projection.time, "monotonic", return_value=100):
                result = input_projection.refresh(db, deadline=deadline)
            self.assertEqual(result["deferred"], ["department"])
            self.assertFalse(any("SELECT refresh_input" in q for q, _ in db.queries))
            self.assertEqual(db.commits + db.rollbacks, 0)

    def test_each_refresh_has_bounded_local_timeout_and_commits(self):
        db = Database([("department", False), ("municipality", True)])
        with patch.object(input_projection.time, "monotonic", side_effect=[100, 100, 104]):
            result = input_projection.refresh(db, deadline=180)
        self.assertEqual(result["refreshed"], [{"scope": "department", "seconds": 4}])
        self.assertIn(("SELECT set_config('statement_timeout',%s,true)", ("75000",)), db.queries)
        self.assertEqual((db.commits, db.rollbacks, db.info.transaction_status), (1, 0, TransactionStatus.IDLE))

    def test_changed_epoch_or_failed_refresh_leaves_retry_visible(self):
        for outcome in (False, LockNotAvailable("busy"), QueryCanceled("deadline")):
            db = Database([("municipality", False)], outcome=outcome)
            result = input_projection.refresh(db)
            self.assertEqual(result["refreshed"], [])
            self.assertEqual(result["deferred"], ["municipality"])
            self.assertEqual(db.info.transaction_status, TransactionStatus.IDLE)
            self.assertEqual(db.rollbacks, int(isinstance(outcome, Exception)))

    def test_unexpected_database_errors_are_not_reported_as_success(self):
        db = Database([("department", False)], outcome=RuntimeError("permission denied"))
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            input_projection.refresh(db)
        self.assertEqual(db.rollbacks, 1)
