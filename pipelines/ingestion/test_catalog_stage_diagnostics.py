"""Catalog errors identify the failed stage without leaking source payloads."""
import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from psycopg.errors import QueryCanceled
from . import catalog_stage as stage, catalog_repair_priority, catalog_drain, input_projection
from . import official_catalog as catalog, worker
from . import official_catalog as tracked_catalog
from .resumable_inputs import WorkDeferred

SECRET = 'postgresql://secret-password@private-host SELECT sensitive_payload'


class FakeDB:
    def __init__(self, fail_at):
        self.fail_at = fail_at
        self.calls = 0
        self.rolled_back = False

    @contextmanager
    def transaction(self):
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise

    def execute(self, _sql, _args=()):
        self.calls += 1
        if self.calls == self.fail_at:
            raise QueryCanceled(SECRET)
        return self

    def fetchall(self):
        return []


class CatalogStageDiagnostics(unittest.TestCase):
    def check_failure(self, fn, expected_stage, expected_count):
        with self.assertRaises(stage.CatalogStageFailure) as caught:
            fn()
        exc = caught.exception
        self.assertEqual((exc.stage, exc.sqlstate, exc.key_count),
                         (expected_stage, '57014', expected_count))
        self.assertGreaterEqual(exc.elapsed_ms, 0)
        self.assertLessEqual(exc.elapsed_ms, 999999)
        self.assertEqual(set(stage.catalog_error_record(exc)), {'source', 'error'})
        self.assertNotIn('secret-password', json.dumps(stage.catalog_error_record(exc)))
        self.assertNotIn('sensitive_payload', str(exc))

    def test_input_projection_query_canceled(self):
        with patch.object(input_projection, 'refresh', side_effect=QueryCanceled(SECRET)):
            self.check_failure(lambda: worker.refresh_catalog(None), 'input_projection', 0)

    def test_repair_priority_query_canceled_uses_sanitized_fifo_fallback(self):
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', side_effect=QueryCanceled(SECRET)), patch.object(
            catalog_drain, 'drain_official_catalog', return_value=SimpleNamespace(
                refreshed=100, as_record=lambda: {'status': 'bounded', 'refreshed': 100})) as drain:
            result = worker.refresh_catalog(None)
        drain.assert_called_once_with(None, priority_keys=(), run_deadline=None)
        self.assertEqual(result['official'], 100)
        self.assertEqual(result['official_drain']['refreshed'], 100)
        self.assertEqual(result['repair_priority']['status'], 'fifo_fallback')
        diagnostic = result['repair_priority']['diagnostic']
        self.assertEqual(diagnostic['source'], 'official_catalog')
        self.assertIn('stage=repair_priority', diagnostic['error'])
        self.assertIn('sqlstate=57014', diagnostic['error'])
        self.assertNotIn('secret-password', json.dumps(result))
        self.assertNotIn('sensitive_payload', json.dumps(result))

    def test_priority_timeout_rolls_back_before_fifo_selection(self):
        db = FakeDB(2)
        def canceled_priority(*_args, **_kwargs):
            with db.transaction():
                db.execute('set timeout')
                db.execute('priority select')
        def fifo(*_args, **_kwargs):
            self.assertTrue(db.rolled_back)
            return SimpleNamespace(refreshed=3, as_record=lambda: {'status': 'drained'})
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', side_effect=canceled_priority), patch.object(
            catalog_drain, 'drain_official_catalog', side_effect=fifo):
            self.assertEqual(worker.refresh_catalog(db)['official'], 3)

    def test_priority_non_timeout_and_wrong_stage_do_not_fallback(self):
        for problem in (stage.CatalogStageFailure('repair_priority', 1, 0, '42501'),
                        stage.CatalogStageFailure('winner_upsert', 1, 1, '57014')):
            with self.subTest(stage=problem.stage, state=problem.sqlstate), patch.object(
                input_projection, 'refresh', return_value={}), patch.object(
                catalog_repair_priority, 'changed_identity_priority', side_effect=problem), patch.object(
                catalog_drain, 'drain_official_catalog') as drain:
                with self.assertRaises(stage.CatalogStageFailure) as caught:
                    worker.refresh_catalog(None)
                self.assertIs(caught.exception, problem)
                drain.assert_not_called()

    def test_priority_timeout_after_run_deadline_defers_without_fifo(self):
        token = worker.RUN_DEADLINE.set(1)
        try:
            with patch.object(input_projection, 'refresh', return_value={}), patch.object(
                catalog_repair_priority, 'changed_identity_priority', side_effect=QueryCanceled(SECRET)), patch.object(
                catalog_drain, 'drain_official_catalog') as drain:
                with self.assertRaises(WorkDeferred):
                    worker.refresh_catalog(None)
                drain.assert_not_called()
        finally:
            worker.RUN_DEADLINE.reset(token)

    def test_priority_work_deferred_never_falls_back(self):
        marker = WorkDeferred('source selection deferred')
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', side_effect=marker), patch.object(
            catalog_drain, 'drain_official_catalog') as drain:
            with self.assertRaises(WorkDeferred) as caught:
                worker.refresh_catalog(None)
            self.assertIs(caught.exception, marker)
            drain.assert_not_called()

    def test_fifo_fallback_failure_keeps_its_actual_stage(self):
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', side_effect=QueryCanceled(SECRET)), patch.object(
            tracked_catalog, 'refresh_dirty', side_effect=QueryCanceled(SECRET)):
            self.check_failure(lambda: worker.refresh_catalog(None), 'dirty_refresh', 0)

    def test_successful_priority_is_preserved_without_fallback_label(self):
        keys = ('a' * 64, 'b' * 64)
        telemetry = {'status': 'drained', 'refreshed': 100}
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', return_value=keys), patch.object(
            catalog_drain, 'drain_official_catalog', return_value=SimpleNamespace(
                refreshed=100, as_record=lambda: telemetry)) as drain:
            result = worker.refresh_catalog(None)
        drain.assert_called_once_with(None, priority_keys=keys, run_deadline=None)
        self.assertEqual(result, {'inputs': {}, 'official': 100, 'official_drain': telemetry})

    def test_dirty_refresh_query_canceled(self):
        with patch.object(input_projection, 'refresh', return_value={}), patch.object(
            catalog_repair_priority, 'changed_identity_priority', return_value=('a' * 64,)), patch.object(
            tracked_catalog, 'refresh_dirty', side_effect=QueryCanceled(SECRET)):
            self.check_failure(lambda: worker.refresh_catalog(None), 'dirty_refresh', 1)

    def test_dirty_selection_query_canceled(self):
        self.check_failure(lambda: catalog.refresh_dirty(FakeDB(1),
                           priority_keys=('a' * 64,)), 'dirty_selection', 1)

    def test_cache_lock_query_canceled_rolls_back(self):
        db = FakeDB(1)
        self.check_failure(lambda: catalog.refresh_keys(db, ['a' * 64, 'b' * 64]), 'cache_lock', 2)
        self.assertTrue(db.rolled_back)

    def test_winner_upsert_query_canceled_rolls_back(self):
        db = FakeDB(3)
        self.check_failure(lambda: catalog.refresh_keys(db, ['a' * 64, 'b' * 64]), 'winner_upsert', 2)
        self.assertTrue(db.rolled_back)

    def test_nested_stage_preserves_inner_attribution(self):
        with self.assertRaises(stage.CatalogStageFailure) as caught:
            with stage.catalog_stage('dirty_refresh', 4):
                with stage.catalog_stage('cache_lock', 2):
                    raise QueryCanceled(SECRET)
        self.assertEqual((caught.exception.stage, caught.exception.key_count), ('cache_lock', 2))

    def test_work_deferred_identity_is_unchanged(self):
        marker = WorkDeferred('bounded deferral')
        with self.assertRaises(WorkDeferred) as caught:
            with stage.catalog_stage('dirty_refresh', 3):
                with stage.catalog_stage('cache_lock', 2):
                    raise marker
        self.assertIs(caught.exception, marker)

    def test_invalid_sqlstate_and_message_are_sanitized(self):
        problem = RuntimeError(SECRET)
        problem.sqlstate = '57014;secret'
        with self.assertRaises(stage.CatalogStageFailure) as caught:
            with stage.catalog_stage('repair_priority', 999999):
                raise problem
        exc = caught.exception
        self.assertEqual(exc.sqlstate, 'UNKNOWN')
        self.assertEqual(exc.key_count, 2000)
        self.assertNotIn(SECRET, json.dumps(stage.catalog_error_record(exc)))

    def test_unattributed_exception_is_not_mislabeled(self):
        self.assertEqual(stage.catalog_error_record(RuntimeError(SECRET)),
            {'source': 'official_catalog',
             'error': 'stage=unattributed elapsed_ms=0 key_count=0 sqlstate=UNKNOWN'})

    def test_worker_first_error_then_successful_final_refresh(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        with patch.object(worker, 'connect') as connection, patch.object(
            worker, 'refresh_catalog', side_effect=[
                stage.CatalogStageFailure('repair_priority', 4012, 0, '57014'),
                {'inputs': {'deferred': []}, 'official': 0},
            ]), patch('pipelines.ingestion.ocr.drain', return_value={}):
            connection.return_value.__enter__.return_value = db
            summary = worker.run('ocr', limit=0, time_budget=600)
        self.assertEqual(summary['errors'], [{'source': 'official_catalog',
            'error': 'stage=repair_priority elapsed_ms=4012 key_count=0 sqlstate=57014'}])
        self.assertEqual(summary['catalog_after_publication']['official'], 0)
        self.assertTrue(any(
            call.args[0].startswith('UPDATE ingestion_run SET status=%s')
            and call.args[1][0] == 'partial'
            for call in db.execute.call_args_list
        ))
        self.assertNotIn('secret-password', json.dumps(summary))


if __name__ == '__main__':
    unittest.main()
