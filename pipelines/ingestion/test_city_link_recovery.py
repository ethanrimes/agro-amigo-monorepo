"""Exact ZIP recovery, printed-date coverage and immutable candidate evidence."""

import io
import os
import unittest
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

import requests

from . import worker
from .city_link_recovery import ALIASES, _validate_member, recover_link

URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-22jul2023.zip"
DAY = date(2023, 7, 22)
FEB_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-10feb2024.zip"
FEB_DAY = date(2024, 2, 10)
ROOT = Path("artifacts/source-ambiguity-2026-09-27/city-milk")
FIXTURE = ROOT / "city-24jul2023.zip"


def bundle(count=23, *, comment=b""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for index in range(count):
            archive.writestr(f"market{index}-22-07-2023.pdf", b"%PDF-mock")
        archive.comment = comment
    return buf.getvalue()


def valid_member(body, filename, archive_day):
    assert archive_day == date(2023, 7, 24)
    return {
        "filename": filename,
        "observed_on": str(DAY),
        "records": 1,
        "empty_template": False,
    }


class CityLinkRecovery(unittest.TestCase):
    def test_worker_keeps_recovered_rows_but_marks_unknown_roster_for_review(self):
        alias = ALIASES[FEB_URL]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for index in range(22):
                archive.writestr(f"market{index}-10-02-2024.pdf", b"%PDF-mock")
        body = buf.getvalue()
        response = requests.Response()
        response.status_code = 404
        missing = requests.HTTPError("missing original", response=response)

        class DB:
            def __init__(self):
                self.rows = []
                self.asset = {"status": "failed", "records": 0, "error": None}
                self.calls = []

            def execute(self, sql, args=()):
                self.calls.append((sql, args))
                if sql.startswith("SELECT processor_version"):
                    return Mock(fetchone=lambda: (worker.parser_version("city-zip"),))
                if sql.startswith("SELECT document_id,status,records"):
                    return Mock(fetchone=lambda: ("older", "failed", 0))
                if "SET document_id=%s,status=%s,records=(SELECT count(*)" in sql:
                    self.asset.update(
                        status=args[1], records=len(self.rows), error=args[3]
                    )
                return Mock(fetchone=lambda: None)

        db = DB()

        def checked_member(_body, filename, archive_day):
            self.assertEqual(archive_day, alias.archive_day)
            return {"filename": filename, "observed_on": str(FEB_DAY), "records": 1}

        def publish(_db, data, did, url, day, **kwargs):
            self.assertEqual((data, did, url, day), (body, "candidate-id", alias.canonical_url, alias.archive_day))
            db.rows.extend(range(22))
            return len(db.rows)

        with (
            patch.object(worker, "fetch_asset", side_effect=missing),
            patch.object(worker, "fetch", return_value=body) as fetch,
            patch.object(worker, "archive", return_value="candidate-id") as archive,
            patch("pipelines.ingestion.city_link_recovery._validate_member", side_effect=checked_member),
            patch("pipelines.ingestion.city_reports.publish_city_zip", side_effect=publish),
            patch("pipelines.ingestion.daily_publication.retain_resolution") as retain,
            patch("pipelines.ingestion.query_publication.recover", return_value=0),
        ):
            count = worker._process_asset(db, FEB_URL, "city-zip", FEB_DAY)

        self.assertEqual(count, 22)
        self.assertEqual(db.asset["status"], "review")
        self.assertEqual(db.asset["records"], 22)
        self.assertIn("full roster is unknown", db.asset["error"])
        fetch.assert_called_once_with(alias.canonical_url)
        self.assertEqual(archive.call_args_list[0].args[4], alias.archive_day)
        self.assertEqual(archive.call_args_list[1].args[4], alias.archive_day)
        self.assertEqual(archive.call_args_list[1].args[1], alias.canonical_url)
        resolution = [
            call.args[2]
            for call in retain.call_args_list
            if call.args[1] == "source_link_resolution"
        ]
        self.assertEqual(resolution[0]["original_url"], FEB_URL)
        self.assertEqual(resolution[0]["original_http_status"], 404)

    def test_february_alias_keeps_failed_url_and_official_archive_provenance(self):
        alias = ALIASES[FEB_URL]
        self.assertEqual(alias.archive_day, date(2024, 2, 12))
        self.assertIn("febrero-de-2024", alias.archive_url)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for index in range(22):
                archive.writestr(f"market{index}-10-02-2024.pdf", b"%PDF-mock")

        def feb_member(body, filename, archive_day):
            self.assertEqual(archive_day, alias.archive_day)
            return {"filename": filename, "observed_on": str(FEB_DAY), "records": 1}

        with patch(
            "pipelines.ingestion.city_link_recovery._validate_member",
            side_effect=feb_member,
        ):
            result = recover_link(FEB_URL, 404, FEB_DAY, lambda _: buf.getvalue())
        self.assertEqual(result.evidence["original_url"], FEB_URL)
        self.assertEqual(result.evidence["original_http_status"], 404)
        self.assertEqual(result.evidence["canonical_url"], alias.canonical_url)
        self.assertEqual(result.evidence["archive_url"], alias.archive_url)
        self.assertEqual(result.evidence["requested_day_price_members"], 22)
        self.assertIn("full roster is unknown", result.evidence["coverage_note"])

    @unittest.skipUnless(os.getenv("DANE_LIVE_CITY_RECOVERY"), "live DANE check opt-in")
    def test_live_official_february_zip_retains_original_printed_dates(self):
        alias = ALIASES[FEB_URL]
        with urlopen(alias.archive_url, timeout=45) as response:
            self.assertIn(f'href="{urlsplit(FEB_URL).path}"'.encode(), response.read())
        with self.assertRaises(HTTPError) as failed:
            urlopen(FEB_URL, timeout=45)
        self.assertEqual(failed.exception.code, 404)
        failed.exception.close()
        with urlopen(alias.canonical_url, timeout=45) as response:
            body = response.read()
        result = recover_link(FEB_URL, 404, FEB_DAY, lambda _: body)
        evidence = result.evidence
        self.assertTrue(evidence["matches_audited_bytes"])
        self.assertEqual(evidence["member_count"], 51)
        self.assertEqual(
            evidence["members_by_date"],
            {"2024-02-10": 22, "2024-02-11": 5, "2024-02-12": 24},
        )
        self.assertEqual(evidence["requested_day_price_members"], 22)
        self.assertEqual(evidence["requested_day_records"], 919)
        self.assertEqual(evidence["records"], 2342)

    def test_only_exact_missing_url_and_permanent_status_can_fetch(self):
        fetcher = Mock()
        for status in (200, 304, 403, 429, 500, 503):
            self.assertIsNone(recover_link(URL, status, DAY, fetcher))
        self.assertIsNone(
            recover_link(URL.replace("22jul", "23jul"), 404, DAY, fetcher)
        )
        fetcher.assert_not_called()
        with self.assertRaisesRegex(ValueError, "verified missing date"):
            recover_link(URL, 404, date(2023, 7, 21), fetcher)
        fetcher.assert_not_called()

    def test_archive_day_is_available_before_fetch_and_differs_from_requested_day(self):
        self.assertEqual(ALIASES[URL].archive_day, date(2023, 7, 24))
        body = bundle()
        fetcher = Mock(return_value=body)
        with patch(
            "pipelines.ingestion.city_link_recovery._validate_member",
            side_effect=valid_member,
        ):
            result = recover_link(URL, 410, DAY, fetcher)
        fetcher.assert_called_once_with(ALIASES[URL].canonical_url)
        self.assertEqual(result.archive_day, date(2023, 7, 24))
        self.assertEqual(result.body, body)
        self.assertEqual(result.evidence["requested_day_price_members"], 23)
        self.assertIn("full roster is unknown", result.evidence["coverage_note"])

    def test_changed_candidate_is_fully_revalidated_not_hash_pinned(self):
        with patch(
            "pipelines.ingestion.city_link_recovery._validate_member",
            side_effect=valid_member,
        ) as validator:
            original = recover_link(URL, 404, DAY, lambda _: bundle())
            updated = recover_link(
                URL, 404, DAY, lambda _: bundle(comment=b"publisher revision")
            )
        self.assertEqual(validator.call_count, 46)
        self.assertNotEqual(original.evidence["sha256"], updated.evidence["sha256"])
        self.assertFalse(updated.evidence["matches_audited_bytes"])

    def test_later_failure_or_missing_requested_members_rejects_entire_candidate(self):
        with (
            patch(
                "pipelines.ingestion.city_link_recovery._validate_member",
                side_effect=valid_member,
            ),
            self.assertRaisesRegex(ValueError, "all audited"),
        ):
            recover_link(URL, 404, DAY, lambda _: bundle(22))

        def changed_day(body, name, day):
            result = valid_member(body, name, day)
            if name.startswith("market22-"):
                result["observed_on"] = "2023-07-24"
            return result

        with (
            patch(
                "pipelines.ingestion.city_link_recovery._validate_member",
                side_effect=changed_day,
            ),
            self.assertRaisesRegex(ValueError, "all audited"),
        ):
            recover_link(URL, 404, DAY, lambda _: bundle())

        def late_failure(body, name, day):
            if name.startswith("market22-"):
                raise ValueError("native package identity invalid")
            return valid_member(body, name, day)

        with (
            patch(
                "pipelines.ingestion.city_link_recovery._validate_member",
                side_effect=late_failure,
            ),
            self.assertRaisesRegex(ValueError, "native package identity"),
        ):
            recover_link(URL, 404, DAY, lambda _: bundle())

    def test_non_zip_or_duplicate_members_are_not_valid_replacements(self):
        with self.assertRaisesRegex(ValueError, "bounded ZIP"):
            recover_link(URL, 404, DAY, lambda _: b"<html>not found</html>")
        with self.assertRaisesRegex(ValueError, "not a native PDF"):
            _validate_member(b"<html>", "market.pdf", date(2023, 7, 24))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("market.pdf", b"%PDF-mock")
            with self.assertWarns(UserWarning):
                archive.writestr("market.pdf", b"%PDF-other")
        with self.assertRaisesRegex(ValueError, "unexpected ZIP"):
            recover_link(URL, 404, DAY, lambda _: buf.getvalue())

    def test_native_zero_template_is_retained_but_does_not_replace_price_members(self):
        text = "PRECIOS DE VENTA MAYORISTA\nBucaramanga, Centroabastos\nPRODUCTOS PRIMERA CALIDAD\n22 de Julio de 2023"
        table = [
            ["Producto", "Presentación", "Unidades", "Ronda 1", "", "Ronda 2", ""],
            ["", "", "", "Mínimo", "Máximo", "Mínimo", "Máximo"],
            ["Ahuyama", "Kilogramo", "1 Kilogramo", "0", "0", "0", "0"],
        ]
        page = SimpleNamespace(
            extract_text=lambda: text,
            extract_tables=lambda: [table],
            images=[],
            close=lambda: None,
        )
        pdf = Mock()
        pdf.__enter__ = Mock(return_value=SimpleNamespace(pages=[page]))
        pdf.__exit__ = Mock(return_value=False)
        with patch("pdfplumber.open", return_value=pdf):
            result = _validate_member(
                b"%PDF-mock", "market-22-07-2023.pdf", date(2023, 7, 24)
            )
        self.assertTrue(result["empty_template"])
        self.assertEqual(result["records"], 0)

        def zero_member(body, name, day):
            value = valid_member(body, name, day)
            if name.startswith("market22-"):
                value.update(records=0, empty_template=True)
            return value

        with (
            patch(
                "pipelines.ingestion.city_link_recovery._validate_member",
                side_effect=zero_member,
            ),
            self.assertRaisesRegex(ValueError, "all audited"),
        ):
            recover_link(URL, 404, DAY, lambda _: bundle())
        with patch(
            "pipelines.ingestion.city_link_recovery._validate_member",
            side_effect=zero_member,
        ):
            retained = recover_link(URL, 404, DAY, lambda _: bundle(24))
        self.assertEqual(retained.evidence["member_count"], 24)
        self.assertEqual(retained.evidence["requested_day_price_members"], 23)

    @unittest.skipUnless(FIXTURE.exists(), "retained official ZIP required")
    def test_actual_official_later_zip_retains_all_23_requested_day_reports(self):
        body = FIXTURE.read_bytes()
        result = recover_link(URL, 404, DAY, lambda _: body)
        evidence = result.evidence
        self.assertTrue(evidence["matches_audited_bytes"])
        self.assertEqual(evidence["member_count"], 49)
        self.assertEqual(
            evidence["members_by_date"],
            {"2023-07-22": 23, "2023-07-23": 5, "2023-07-24": 21},
        )
        self.assertEqual(evidence["requested_day_price_members"], 23)
        self.assertEqual(evidence["requested_day_records"], 969)
        requested = [
            member
            for member in evidence["members"]
            if member["observed_on"] == str(DAY)
        ]
        self.assertEqual(
            sum(member["filename_date_verified"] for member in requested), 22
        )
        self.assertEqual(
            sum(member["empty_template"] for member in evidence["members"]), 0
        )
        self.assertEqual(len({member["sha256"] for member in evidence["members"]}), 49)
        invalid_names = [
            member for member in evidence["members"] if member["filename_date_issue"]
        ]
        self.assertEqual(len(invalid_names), 1)
        self.assertEqual(
            invalid_names[0]["filename"], "Medellín, Plaza Minorista -24-27-2023.pdf"
        )
        self.assertEqual(invalid_names[0]["observed_on"], "2023-07-24")
        self.assertFalse(invalid_names[0]["filename_date_verified"])
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            first = archive.read("Bucaramanga, Centroabastos-22-07-2023.pdf")
        with self.assertRaisesRegex(ValueError, "filename conflicts"):
            _validate_member(
                first, "Bucaramanga, Centroabastos-21-07-2023.pdf", date(2023, 7, 24)
            )
        with self.assertRaisesRegex(ValueError, "future internal date"):
            _validate_member(
                first, "Bucaramanga, Centroabastos-22-07-2023.pdf", date(2023, 7, 21)
            )


if __name__ == "__main__":
    unittest.main()
