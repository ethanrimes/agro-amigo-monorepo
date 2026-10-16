"""Archive integrity and failures shared by static and recurring imports."""

import ast
import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from .blob_archive import retain_original_blob


class OriginalBlobIntegrity(unittest.TestCase):
    def test_wrong_bytes_or_extension_never_reach_storage(self):
        with patch.dict(os.environ, {"AzureWebJobsStorage": "configured"}), patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string"
        ) as connect:
            for digest, suffix in [("0" * 64, ".pdf"), (hashlib.sha256(b"original").hexdigest(), "/unsafe")]:
                with self.assertRaises(ValueError):
                    retain_original_blob(digest, b"original", suffix, "application/pdf")
            connect.assert_not_called()

    def test_changed_originals_are_kept_separately_and_replay_cannot_overwrite(self):
        from azure.core.exceptions import ResourceExistsError

        objects = {}
        def client(_container, name):
            def upload(data, *, overwrite, **_settings):
                self.assertFalse(overwrite)
                if name in objects:
                    raise ResourceExistsError("Retained original")
                objects[name] = data
            return Mock(upload_blob=upload)

        service = Mock(get_blob_client=client)
        with patch.dict(os.environ, {"AzureWebJobsStorage": "configured"}), patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string", return_value=service
        ):
            for body in [b"first published original", b"revised original", b"first published original"]:
                self.assertTrue(retain_original_blob(hashlib.sha256(body).hexdigest(), body, ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        self.assertEqual(set(objects.values()), {b"first published original", b"revised original"})

    def test_static_import_storage_failure_prevents_document_and_alias_publication(self):
        # Execute the real evidence writer without importing its obsolete local
        # bulk-import cache/bootstrap work. A failed upload must precede SQL.
        path = Path(__file__).parents[1] / "planning/import_references.py"
        writer = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == "doc")
        namespace = {"hashlib": hashlib, "Jsonb": lambda value: value}
        exec(compile(ast.Module(body=[writer], type_ignores=[]), str(path), "exec"), namespace)
        source = Mock(suffix=".json", read_bytes=lambda: b'{"source":"official"}')
        db = Mock()
        with patch("pipelines.ingestion.blob_archive.retain_original_blob", side_effect=OSError("Storage unavailable")):
            with self.assertRaisesRegex(OSError, "Storage unavailable"):
                namespace["doc"](db, source, "Official reference", "UPRA", "https://example.invalid/source.json", "2025", "eva")
        db.execute.assert_not_called()
