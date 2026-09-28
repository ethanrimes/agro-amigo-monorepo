"""The one source-verified April 2024 DANE supply PDF recovery."""

import hashlib
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from . import supply_link_recovery as recovery
from . import supply_period_summaries, worker

ORIGINAL = (
    Path(__file__).resolve().parent
    / "testdata/bol-SIPSAabastecimiento-1raquincenaAbril2024.pdf"
)


class SupplyPDFLinkRecovery(unittest.TestCase):
    def test_only_exact_broken_pdf_and_permanent_missing_response_can_fetch(self):
        fetcher = Mock()
        for status in (200, 304, 403, 429, 500, 503):
            self.assertIsNone(recovery.recover_link(recovery.BROKEN_PDF, status, None, fetcher))
        for url in (
            recovery.BROKEN_PDF + "?download=1",
            recovery.BROKEN_PDF.replace("www.dane.gov.co", "example.org"),
            recovery.BROKEN_PDF.replace("1raquinabr", "1raquinmay"),
            recovery.FILES + "anex-SIPSAabastecimiento-1raquinabr2024.xlsx",
        ):
            self.assertIsNone(recovery.recover_link(url, 404, None, fetcher))
        with self.assertRaisesRegex(ValueError, "undated fortnight"):
            recovery.recover_link(recovery.BROKEN_PDF, 404, date(2024, 4, 30), fetcher)
        fetcher.assert_not_called()

    def test_changed_or_non_pdf_candidate_cannot_be_published(self):
        for candidate in (b"<html>not found</html>", b"%PDF-changed"):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                recovery.recover_link(
                    recovery.BROKEN_PDF, 404, None, lambda _, body=candidate: body
                )

    def test_recovery_module_is_in_worker_release_fingerprint(self):
        self.assertIn("pipelines/ingestion/supply_link_recovery.py", worker.RELEASE_FILES)

    @unittest.skipUnless(ORIGINAL.exists(), "verified DANE original unavailable")
    def test_official_pdf_bytes_date_period_and_printed_market_rows(self):
        body = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), recovery.AUDITED_SHA256)
        fetcher = Mock(return_value=body)
        result = recovery.recover_link(recovery.BROKEN_PDF, 404, None, fetcher)
        fetcher.assert_called_once_with(recovery.CANONICAL_PDF)
        self.assertEqual(result.canonical_url, recovery.CANONICAL_PDF)
        self.assertIsNone(result.archive_day)
        self.assertEqual(result.evidence["original_url"], recovery.BROKEN_PDF)
        self.assertEqual(result.evidence["original_http_status"], 404)
        self.assertEqual(result.evidence["period_start"], "2024-04-01")
        self.assertEqual(result.evidence["period_end"], "2024-04-15")
        self.assertEqual(result.evidence["printed_publication_date"], "2024-05-03")
        self.assertIn("XLSX remains HTTP 404", result.evidence["coverage_note"])
        rows, reviews = supply_period_summaries.parse_pdf(result.body)
        self.assertEqual(len(rows), 99)
        self.assertEqual(reviews, [])
        self.assertEqual(len({row["name"] for row in rows}), 33)

    @unittest.skipUnless(ORIGINAL.exists(), "verified DANE original unavailable")
    def test_hash_alone_cannot_bypass_native_period_validation(self):
        body = ORIGINAL.read_bytes()
        with (
            patch.object(
                supply_period_summaries,
                "period",
                return_value=(date(2024, 4, 1), date(2024, 4, 30), "monthly"),
            ),
            self.assertRaisesRegex(ValueError, "native report period"),
        ):
            recovery.recover_link(recovery.BROKEN_PDF, 404, None, lambda _: body)

    @unittest.skipUnless(ORIGINAL.exists(), "verified DANE original unavailable")
    def test_worker_archives_actual_url_and_leaves_incomplete_table_in_review(self):
        body = ORIGINAL.read_bytes()
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError("missing", response=response)

        class DB:
            def __init__(self):
                self.calls = []

            def execute(self, sql, args=()):
                self.calls.append((sql, args))
                if sql.startswith("SELECT processor_version"):
                    return Mock(fetchone=lambda: (worker.parser_version("supply-reference-pdf"),))
                if sql.startswith("SELECT document_id,status,records"):
                    return Mock(fetchone=lambda: ("older", "failed", 0))
                return Mock(fetchone=lambda: None)

            def transaction(self):
                return nullcontext()

        db = DB()
        with (
            patch.object(worker, "fetch_asset", side_effect=error),
            patch.object(worker, "fetch", return_value=body) as fetch,
            patch.object(worker, "archive", return_value=recovery.AUDITED_SHA256) as archive,
            patch("pipelines.ingestion.daily_publication.retain_resolution") as retain,
            patch("pipelines.ingestion.pdf_sources.extract_pages"),
            patch.object(
                supply_period_summaries,
                "publish",
                return_value=(0, ["Native market summary incomplete"]),
            ),
        ):
            self.assertEqual(
                worker._process_asset(db, recovery.BROKEN_PDF, "supply-reference-pdf", None),
                0,
            )
        fetch.assert_called_once_with(recovery.CANONICAL_PDF)
        self.assertEqual(archive.call_count, 2)
        self.assertEqual(archive.call_args_list[0].args[1], recovery.CANONICAL_PDF)
        self.assertEqual(archive.call_args_list[0].kwargs["register_alias"], False)
        self.assertEqual(archive.call_args_list[1].args[1], recovery.CANONICAL_PDF)
        resolution = [c for c in retain.call_args_list if c.args[1] == "source_link_resolution"]
        self.assertEqual(len(resolution), 1)
        self.assertEqual(resolution[0].args[2]["original_http_status"], 404)
        updates = [args for sql, args in db.calls if "SET document_id=%s,status=%s,records=%s" in sql]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], "review")
        self.assertIn("XLSX remains HTTP 404", updates[0][3])


if __name__ == "__main__":
    unittest.main()
