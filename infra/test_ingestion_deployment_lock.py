"""Real PostgreSQL contention protects workers before deployment mutations."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import psycopg

from . import deploy_ingestion
from pipelines.ingestion.worker import LOCK


@unittest.skipUnless(os.environ.get("AGRO_DEPLOY_LOCK_TEST_DSN"),
                     "explicit local PostgreSQL advisory-lock test DSN required")
class IngestionDeploymentLock(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["AGRO_DEPLOY_LOCK_TEST_DSN"]
        original_connect = psycopg.connect
        self.worker = original_connect(self.dsn, autocommit=True)
        self.addCleanup(self.worker.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        local = Path(folder.name)
        (local / "database.json").write_text(json.dumps(
            {"host": "unused", "database": "unused", "user": "unused", "password": "unused"}))
        self.patch_local = patch.object(deploy_ingestion, "LOCAL", local)
        self.patch_local.start()
        self.addCleanup(self.patch_local.stop)
        self.patch_connect = patch.object(psycopg, "connect", side_effect=lambda **kwargs:
                                         original_connect(self.dsn, autocommit=True))
        self.patch_connect.start()
        self.addCleanup(self.patch_connect.stop)

    def test_active_writer_prevents_all_deployment_actions(self):
        self.assertTrue(self.worker.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0])
        try:
            with patch.object(deploy_ingestion, "_deploy") as mutation:
                with self.assertRaisesRegex(RuntimeError, "writer is active"):
                    deploy_ingestion.deploy(code_only=True)
                mutation.assert_not_called()
        finally:
            self.worker.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))

    def test_deployment_excludes_writer_and_releases_lock_after_failure(self):
        def mutation(**kwargs):
            self.assertFalse(self.worker.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0])
            raise RuntimeError("simulated package failure")
        with patch.object(deploy_ingestion, "_deploy", side_effect=mutation):
            with self.assertRaisesRegex(RuntimeError, "package failure"):
                deploy_ingestion.deploy(code_only=True)
        self.assertTrue(self.worker.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0])
        self.worker.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))


if __name__ == "__main__":
    unittest.main()
