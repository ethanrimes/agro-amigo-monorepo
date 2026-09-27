"""Only proven publisher typos recover; wrong dates and partial parses fail."""

import io
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zipfile import BadZipFile

from openpyxl import Workbook

from pipelines.ingestion.source_link_recovery import VERIFIED_ALIASES, recover_link

BROKEN = next(iter(VERIFIED_ALIASES))
DAY = date(2014, 8, 11)
FIXTURES = Path(__file__).resolve().parents[2] / "artifacts/source-ambiguity-2026-09-27"


def workbook(day=DAY, price=500, bad_last_market=False):
    book = Workbook()
    sheet = book.active
    sheet.title = "Boletín diario"
    sheet.append(["Boletín diario de precios mayoristas"])
    sheet.append([day])
    sheet.append(
        [
            "Precio $/Kg",
            "Armenia, Mercar",
            "",
            "Bogotá, Corabastos",
            "",
            "" if bad_last_market else "Cali, Cavasa",
        ]
    )
    sheet.append(["Producto", "Precio", "Var%", "Precio", "Var%", "Precio", "Var%"])
    sheet.append(["Ahuyama", price, 0.02, 1017, 0, 700, -0.01])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class SourceLinkRecoveryTests(unittest.TestCase):
    def test_only_missing_response_on_exact_verified_alias_fetches(self):
        fetcher = Mock(return_value=workbook())
        for status in (200, 304, 400, 401, 403, 429, 500, 503):
            self.assertIsNone(recover_link(BROKEN, status, DAY, fetcher))
        for url in (
            BROKEN.replace("www.dane.gov.co", "untrusted.example"),
            BROKEN + "?other=1",
            BROKEN.replace("11_2014s", "12_2014s"),
            VERIFIED_ALIASES[BROKEN].canonical_url,
        ):
            self.assertIsNone(recover_link(url, 404, DAY, fetcher))
        fetcher.assert_not_called()

    def test_both_missing_statuses_validate_and_preserve_alias_evidence(self):
        body = workbook()
        for status in (404, 410):
            fetcher = Mock(return_value=body)
            result = recover_link(BROKEN, status, DAY, fetcher)
            self.assertEqual(result.body, body)
            self.assertEqual(
                result.canonical_url, VERIFIED_ALIASES[BROKEN].canonical_url
            )
            self.assertEqual(result.evidence["original_url"], BROKEN)
            self.assertEqual(result.evidence["observed_on"], "2014-08-11")
            self.assertEqual(result.evidence["validated_records"], 3)
            self.assertEqual(result.evidence["original_http_status"], status)
            self.assertIn("agosto-de-2014", result.evidence["archive_url"])
            fetcher.assert_called_once_with(result.canonical_url)

    def test_wrong_requested_date_does_not_fetch(self):
        fetcher = Mock()
        with self.assertRaisesRegex(ValueError, "verified alias"):
            recover_link(BROKEN, 404, date(2014, 8, 8), fetcher)
        fetcher.assert_not_called()

    def test_wrong_printed_date_cannot_be_accepted_by_filename(self):
        with self.assertRaisesRegex(ValueError, "differs from workbook"):
            recover_link(BROKEN, 404, DAY, lambda _: workbook(date(2014, 8, 8)))

    def test_html_and_truncated_workbook_rejected(self):
        for body in (b"<html>200 OK: not a workbook</html>", b"PK\x03\x04truncated"):
            with self.subTest(body=body), self.assertRaises((ValueError, BadZipFile)):
                recover_link(BROKEN, 404, DAY, lambda _, body=body: body)

    def test_full_validation_rejects_late_missing_market(self):
        with self.assertRaisesRegex(ValueError, "unresolved daily cells"):
            recover_link(BROKEN, 404, DAY, lambda _: workbook(bad_last_market=True))

    def test_new_bytes_revalidated_instead_of_hash_pinned(self):
        first = recover_link(BROKEN, 404, DAY, lambda _: workbook(price=500))
        corrected = recover_link(BROKEN, 404, DAY, lambda _: workbook(price=550))
        self.assertNotEqual(first.evidence["sha256"], corrected.evidence["sha256"])
        self.assertFalse(corrected.evidence["matches_audited_bytes"])
        self.assertEqual(corrected.evidence["validated_records"], 3)

    def test_candidate_fetch_failure_propagates(self):
        fetcher = Mock(side_effect=RuntimeError("replacement unavailable"))
        with self.assertRaisesRegex(RuntimeError, "replacement unavailable"):
            recover_link(BROKEN, 404, DAY, fetcher)

    def test_empty_parser_result_is_not_recovery(self):
        with self.assertRaisesRegex(ValueError, "no validated daily prices"):
            recover_link(
                BROKEN, 404, DAY, lambda _: workbook(), validator=lambda *_: []
            )

    @unittest.skipUnless(
        all(
            (FIXTURES / a.canonical_url.rsplit("/", 1)[1]).exists()
            for a in VERIFIED_ALIASES.values()
        ),
        "downloaded official originals unavailable",
    )
    def test_actual_originals_match_printed_dates_counts_and_audit_hashes(self):
        for broken, alias in VERIFIED_ALIASES.items():
            with self.subTest(url=broken):
                path = FIXTURES / alias.canonical_url.rsplit("/", 1)[1]
                result = recover_link(
                    broken,
                    404,
                    alias.observed_on,
                    lambda _, path=path: path.read_bytes(),
                )
                self.assertEqual(
                    result.evidence["validated_records"], alias.audit_records
                )
                self.assertTrue(result.evidence["matches_audited_bytes"])


if __name__ == "__main__":
    unittest.main()
