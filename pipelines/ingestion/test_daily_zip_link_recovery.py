"""A missing official ZIP can route to a verified workbook without disguising it."""

import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests

from . import worker
from .source_link_recovery import VERIFIED_ALIASES
from .test_source_link_recovery import JULY_BROKEN, JULY_ORIGINAL


class DailyZipLinkRecovery(unittest.TestCase):
    def test_missing_zip_retains_review_and_queues_real_excel_identity(self):
        day = date(2024, 7, 31)
        alias = VERIFIED_ALIASES[JULY_BROKEN]
        body = JULY_ORIGINAL.read_bytes()
        response = Mock(status_code=404)
        error = requests.HTTPError("missing", response=response)

        class DB:
            def __init__(self):
                self.updates = []

            def execute(self, sql, args=()):
                if sql.startswith("SELECT processor_version"):
                    return Mock(fetchone=lambda: (worker.parser_version("daily-zip"),))
                self.updates.append((sql, args))
                return Mock(fetchone=lambda: None)

        db = DB()
        with (
            patch.object(worker, "fetch_asset", side_effect=error),
            patch.object(worker, "fetch", return_value=body) as fetch,
            patch.object(worker, "archive", return_value="verified-workbook-id") as archive,
            patch.object(worker, "queue") as queue,
            patch("pipelines.ingestion.daily_publication.retain_resolution") as retain,
        ):
            self.assertEqual(worker._process_asset(db, JULY_BROKEN, "daily-zip", day), 0)

        fetch.assert_called_once_with(alias.canonical_url)
        self.assertEqual(archive.call_args.args[1:5], (alias.canonical_url, body, "daily", day))
        self.assertFalse(archive.call_args.kwargs["register_alias"])
        queue.assert_called_once_with(db, alias.canonical_url, "daily", day)
        self.assertEqual(retain.call_args.args[1], "source_link_resolution")
        self.assertEqual(retain.call_args.args[2]["document_id"], "verified-workbook-id")
        self.assertEqual(retain.call_args.args[2]["validated_records"], 307)
        self.assertEqual(retain.call_args.args[2]["original_url"], JULY_BROKEN)
        self.assertEqual(len(db.updates), 1)
        self.assertIn("status='review'", db.updates[0][0])
        self.assertEqual(db.updates[0][1][-1], JULY_BROKEN)


if __name__ == "__main__":
    unittest.main()
