"""Exact ZIP recovery, printed-date coverage and immutable candidate evidence."""

import io
import unittest
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from .city_link_recovery import ALIASES, _validate_member, recover_link

URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-22jul2023.zip"
DAY = date(2023, 7, 22)
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
