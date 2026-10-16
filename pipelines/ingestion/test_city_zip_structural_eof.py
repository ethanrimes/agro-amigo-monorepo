"""Maintained-module regression draft for one damaged official DANE ZIP member.

This file intentionally imports the maintained city_reports/worker modules.
The fixture is the exact retained Sep 6, 2022 ZIP and the expected JSON is a
small native-parser output manifest; no private candidate module is imported.
"""
from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdfminer.pdfparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException

from pipelines.ingestion import city_reports, worker


HERE = Path(__file__).resolve().parent
DATA = HERE / "testdata" / "city_eof_sep06_2022"
ZIP_PATH = DATA / "city-eof-sep06-2022.zip"
EXPECTED_PATH = DATA / "city-eof-sep06-2022.expected.json"
EXPECTED = json.loads(EXPECTED_PATH.read_text())
URL = EXPECTED["source_url"]
DAY = date.fromisoformat(EXPECTED["expected_archive_date"])
ZIP_SHA = EXPECTED["source_zip"]["sha256"]
BAD_MEMBER = EXPECTED["failed_members"][0]["member"]
BAD_DID = EXPECTED["failed_members"][0]["sha256"]


def _row_digest(rows):
    import re

    def locator_key(row):
        match = re.fullmatch(r"PDF page (\d+),table (\d+),row (\d+),round (\d+)", row[0])
        if not match:
            raise AssertionError(f"Unexpected source locator {row[0]!r}")
        return tuple(map(int, match.groups()))

    ordered = sorted(rows, key=locator_key)
    payload = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class CityZipStructuralEofMaintained(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = ZIP_PATH.read_bytes()
        cls.expected = {entry["member"]: entry for entry in EXPECTED["parsed_members"]}
        with zipfile.ZipFile(io.BytesIO(cls.payload)) as archive:
            cls.members = {m.filename: archive.read(m) for m in archive.infolist()
                           if not m.is_dir() and m.filename.lower().endswith(".pdf")}

    def test_01_exact_official_fixture_digest_and_crc(self):
        self.assertEqual(len(self.payload), EXPECTED["source_zip"]["bytes"])
        self.assertEqual(hashlib.sha256(self.payload).hexdigest(), ZIP_SHA)
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(self.members), EXPECTED["source_zip"]["member_count"])

    def test_02_exact_url_day_and_source_scoped_version_are_pinned(self):
        self.assertEqual(URL, "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-06-09-2022.zip")
        self.assertEqual(DAY, date(2022, 9, 6))
        self.assertEqual(
            worker.URL_SOURCE_REPAIR_VERSIONS[URL],
            ("city-zip", ":sep2022-member-structural-eof-review-v1"),
        )
        self.assertEqual(
            worker.asset_parser_version("city-zip", URL),
            "city-v8:sep2022-member-structural-eof-review-v1",
        )
        self.assertEqual(worker.asset_parser_version("city-zip", URL + "?other=1"), "city-v8")

    def test_03_failed_member_is_one_retained_original(self):
        body = self.members[BAD_MEMBER]
        self.assertEqual(hashlib.sha256(body).hexdigest(), BAD_DID)
        self.assertEqual(len(body), EXPECTED["failed_members"][0]["bytes"])

    def test_04_all_ten_native_siblings_match_independent_row_vectors(self):
        self.assertEqual(set(self.expected), set(self.members) - {BAD_MEMBER})
        for name, expected in self.expected.items():
            with self.subTest(member=name):
                rows = list(city_reports.parse_city_pdf(self.members[name], DAY))
                self.assertEqual(len(rows), expected["row_count"])
                self.assertEqual(_row_digest(rows), expected["native_row_sha256"])
        self.assertEqual(sum(item["row_count"] for item in self.expected.values()),
                         EXPECTED["total_native_rows"])

    def test_05_bad_original_fails_as_structural_pdfminer_exception(self):
        with self.assertRaises(PdfminerException) as caught:
            list(city_reports.parse_city_pdf(self.members[BAD_MEMBER], DAY))
        self.assertTrue(city_reports._is_structural_pdfminer_member_error(caught.exception))

    def test_06_direct_pseof_is_reviewable(self):
        self.assertTrue(city_reports._is_structural_pdfminer_member_error(PSEOF("eof")))

    def test_07_pdfminer_wrapped_pseof_is_reviewable(self):
        wrapped = PdfminerException(PSEOF("eof"))
        self.assertTrue(city_reports._is_structural_pdfminer_member_error(wrapped))

    def test_08_unrelated_pdfminer_runtime_failure_is_fatal(self):
        wrapped = PdfminerException(RuntimeError("database unavailable"))
        self.assertFalse(city_reports._is_structural_pdfminer_member_error(wrapped))

    def test_09_operational_failure_caused_by_pseof_is_still_fatal(self):
        try:
            try:
                raise PSEOF("earlier parser failure")
            except PSEOF as prior:
                raise OSError("disk failure") from prior
        except OSError as operational:
            wrapped = PdfminerException(operational)
        self.assertFalse(city_reports._is_structural_pdfminer_member_error(wrapped))

    def test_10_publisher_reviews_bad_member_and_publishes_all_valid_siblings(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        db.execute.return_value.fetchone.return_value = None
        archived_members = []
        archived = {}
        stored_prices = {}

        def archive(_db, requested_url, body, _kind, *_args, **_kwargs):
            self.assertEqual(requested_url, URL)
            did = hashlib.sha256(body).hexdigest()
            archived[did] = body
            return did

        def db_execute(sql, params=()):
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = None
            if sql.startswith("SELECT step,records FROM ingestion_checkpoint"):
                result.fetchall.return_value = []
            elif sql.startswith("SELECT 1 FROM source_archive_member"):
                result.fetchone.return_value = None
            elif sql.startswith("SELECT id FROM source_document WHERE id=%s"):
                result.fetchone.return_value = (params[0],)
            elif sql.startswith("INSERT INTO source_archive_member"):
                archived_members.append(tuple(params))
            return result

        db.execute.side_effect = db_execute

        def store_rows(_db, table, rows):
            for row in rows:
                if table == "regional_price":
                    stored_prices.setdefault(row[0], []).append(tuple(row))

        with (
            patch.object(worker, "archive", side_effect=archive),
            patch("pipelines.ingestion.pdf_sources.extract_pages", return_value=0),
            patch("pipelines.ingestion.city_reports.save_classifications"),
            patch("pipelines.ingestion.city_reports._bulk_insert", side_effect=store_rows),
            patch("pipelines.ingestion.city_reports._publication_conflict", return_value=None),
        ):
            with self.assertRaises(city_reports.CityZipPartialReview) as caught:
                city_reports.publish_city_zip(db, self.payload, ZIP_SHA, URL, DAY,
                                              processor_version="city-v8-structural-eof-test")

        result = caught.exception
        self.assertEqual(result.count, EXPECTED["total_native_rows"])
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0]["filename"], BAD_MEMBER)
        self.assertEqual(result.failures[0]["document_id"], BAD_DID)
        self.assertEqual(result.failures[0]["error_type"], "PSEOF")
        self.assertEqual(archived[BAD_DID], self.members[BAD_MEMBER])
        self.assertEqual(set(archived), {hashlib.sha256(body).hexdigest()
                                         for body in self.members.values()})
        self.assertEqual(len(archived_members), len(self.members))
        self.assertEqual({entry for _archive_id, entry, _did in archived_members},
                         set(self.members))
        actual_by_did = {did: [row[1:] for row in rows]
                         for did, rows in stored_prices.items()}
        self.assertEqual(sum(map(len, actual_by_did.values())), EXPECTED["total_native_rows"])
        for name, expected in self.expected.items():
            did = hashlib.sha256(self.members[name]).hexdigest()
            self.assertEqual(len(actual_by_did[did]), expected["row_count"], name)
            self.assertEqual(_row_digest(actual_by_did[did]), expected["native_row_sha256"], name)
        self.assertNotIn(BAD_DID, actual_by_did)


if __name__ == "__main__":
    unittest.main(verbosity=2)
