"""A deployment package must import from an isolated directory before upload."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipelines.ingestion.worker import release_fingerprint

from .deploy_ingestion import write_runtime_archive


class WorkerPackage(unittest.TestCase):
    def test_isolated_host_import_and_release_match(self):
        with tempfile.TemporaryDirectory(prefix="agro-package-test-") as folder:
            bundle = Path(folder) / "worker.zip"
            with zipfile.ZipFile(bundle, "w") as archive:
                write_runtime_archive(archive)
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(folder)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json, function_app; "
                        "from pipelines.ingestion import dane_weekly,worker; "
                        "print(json.dumps([dane_weekly.VERSION,worker.release_fingerprint()]))"
                    ),
                ],
                cwd=folder,
                env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                capture_output=True,
                text=True,
                check=True,
            )
            version, fingerprint = json.loads(result.stdout)
            self.assertEqual(version, "dane-weekly-v1")
            self.assertEqual(fingerprint, release_fingerprint())


if __name__ == "__main__":
    unittest.main()
