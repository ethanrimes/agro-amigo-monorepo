"""Regressions from archived originals examined during the September audit."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from . import colombia_sources as source

FIXTURES = (
    Path(__file__).resolve().parents[2] / "artifacts" / "automation-audit-2026-09-26"
)


def original(prefix):
    paths = list(FIXTURES.glob("*-failed-" + prefix + "*.pdf"))
    if len(paths) != 1:
        raise unittest.SkipTest("Official archived original is unavailable: " + prefix)
    body = paths[0].read_bytes()
    if not hashlib.sha256(body).hexdigest().startswith(prefix):
        raise AssertionError("Original bytes do not match their archived SHA256")
    return body


def corabastos(prefix):
    records = json.loads((FIXTURES / "colombia-failed-reproductions.json").read_text())
    item = next(r for r in records if r["document_id"].startswith(prefix))
    return source.parse_corabastos(original(prefix), item["url"])


class NativeLayoutRegressions(unittest.TestCase):
    def test_rotated_sidebar_cannot_merge_two_native_product_rows(self):
        rows = corabastos("f831a019a6c8")
        self.assertEqual(len(rows), 352)
        alas = [r for r in rows if r["product_id"] == "alas-de-pollo"]
        self.assertEqual(len(alas), 2)
        self.assertTrue(all(r["details"]["quantity"] == 1 for r in alas))
        self.assertFalse(any("bagre" in r["product_id"] for r in alas))

    def test_bare_integer_price_row_keeps_its_own_package(self):
        rows = corabastos("cac457de0045")
        quotes = [r for r in rows if r["product_id"] == "platano-colicero"]
        self.assertEqual(len(quotes), 2)
        self.assertEqual({r["price"] for r in quotes}, {3000})
        self.assertEqual({r["details"]["quantity"] for r in quotes}, {1})

    def test_orphan_publisher_prices_are_retained_separately_for_review(self):
        for prefix in [
            "ace2c6908cc6",
            "40b51f1dc557",
            "f779a36a6c4c",
            "9086f4610baf",
            "9292ce85ac13",
            "edf0edf60b32",
        ]:
            with self.subTest(original=prefix):
                rows = corabastos(prefix)
                orphan = [r for r in rows if r["details"].get("quality_issue")]
                expected = 4 if prefix in {"ace2c6908cc6", "40b51f1dc557"} else 2
                self.assertEqual(len(orphan), expected)
                self.assertTrue(all(r["price"] is None for r in orphan))
                self.assertEqual(len({r["source_locator"] for r in orphan}), expected)
                self.assertEqual(len([r for r in rows if r["price"] is not None]), 350)

    def test_zero_is_reviewed_and_other_products_survive(self):
        rows = corabastos("4d04806b57ca")
        zero = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(rows), 350)
        self.assertEqual(len(zero), 4)
        self.assertTrue(
            all(
                r["price"] is None and r["details"]["original_price"] == "$0"
                for r in zero
            )
        )

    def test_publisher_malformed_fish_table_is_not_relabelled_by_guess(self):
        rows = corabastos("7160b32e3f7e")
        self.assertEqual(len(rows), 350)
        reviews = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(reviews), 56)
        self.assertEqual({r["details"]["source_page"] for r in reviews}, {3})
        self.assertTrue(all(r["price"] is None for r in reviews))
        intact = [r for r in rows if r["product_id"] == "alas-de-pollo"]
        self.assertEqual([r["price"] for r in intact], [10000, 10000])

    def test_blank_publisher_template_cannot_invent_a_date_or_trigger_ocr(self):
        with self.assertRaisesRegex(ValueError, "explicit observation date"):
            source.parse_corabastos(
                original("c4f5b171fddb"),
                "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-18febrero2025-1.pdf",
            )

    def test_letter_spaced_current_and_monthly_native_prices(self):
        rows = source.parse_pork(original("8d4f4a0f69aa"))
        self.assertEqual(len(rows), 252)
        national = {
            r["product_name"]: r["price"]
            for r in rows
            if r["date"] == "2021-12-23" and r["market"] == "Colombia"
        }
        self.assertEqual(
            national,
            {
                "Cerdo en pie": 8593,
                "Cerdo · canal caliente": 10767,
                "Cerdo · canal fría": 11294,
            },
        )
        self.assertTrue(all(r["details"].get("extraction") != "ocr" for r in rows))

    def test_comma_thousands_and_adjacent_graph_ticks_are_not_prices(self):
        rows = source.parse_pork(original("4812fb72e05f"))
        self.assertEqual(len(rows), 225)
        feb = next(
            r
            for r in rows
            if r["date"] == "2022-02-28"
            and r["product_name"] == "Cerdo en pie"
            and r["market"] == "Colombia"
        )
        self.assertEqual(feb["price"], 7826)
        self.assertTrue(all(r["price"] >= 7000 for r in rows))

    def test_2020_native_matrix_keeps_publisher_period_conflict(self):
        rows = source.parse_pork(original("d9e3e3f08084"))
        self.assertEqual(sum(r["series"] != "porkcolombia-tercile" for r in rows), 288)
        self.assertEqual(sum(r["series"] == "porkcolombia-tercile" for r in rows), 15)
        reviews = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(reviews), 18)
        self.assertEqual({r["date"] for r in reviews}, {"2020-12-25"})
        current = {
            r["product_name"]: r["price"]
            for r in rows
            if r["date"] == "2020-12-23" and r["market"] == "Colombia"
        }
        self.assertEqual(
            current,
            {
                "Cerdo en pie": 7433,
                "Cerdo · canal caliente": 9268,
                "Cerdo · canal fría": 9823,
            },
        )

    def test_zero_and_overprinted_pork_prices_do_not_destroy_valid_history(self):
        rows = source.parse_pork(original("b199e40b8116"))
        self.assertGreater(len(rows), 250)
        bad = [r for r in rows if r["details"].get("quality_issue")]
        self.assertTrue(any("zero price" in r["details"]["quality_issue"] for r in bad))
        ambiguous = [r for r in bad if "overlapping" in r["details"]["quality_issue"]]
        self.assertTrue(
            any(
                r["market"] == "Colombia" and r["product_name"] == "Cerdo en pie"
                for r in ambiguous
            )
        )
        self.assertTrue(all(r["price"] is None for r in ambiguous))

    def test_broken_font_requests_cover_date_and_price_pages(self):
        with self.assertRaises(source.NormalExtractionFailed) as got:
            source.parse_pork(original("26295de6bbb0"))
        self.assertEqual(got.exception.required_pages, (1, 2, 3))
        # Literal transcription checked against the rendered original, not an
        # assertion that an OCR provider has already processed this document.
        headings = [
            "",
            "Antioquia",
            "Eje Cafetero",
            "Valle del Cauca",
            "Caribe Norte",
            "Bogotá",
            "Promedio Muestra",
        ]
        triples = [
            ("Precio en Pie", ["7.507", "7.497", "7.506", "7.372", "7.158", "7.434"]),
            (
                "Precio en Canal Caliente",
                ["9.298", "9.241", "9.266", "9.153", "9.428", "9.281"],
            ),
            (
                "Precio en Canal Fría",
                ["9.845", "9.746", "9.834", "9.610", "10.080", "9.827"],
            ),
        ]
        readings = {1: {"text": "31 de diciembre 2020", "tables": []}}
        for pn, period in [(2, "Semana Actual"), (3, "30-dic-20")]:
            readings[pn] = {
                "text": "",
                "tables": [
                    [headings, [name], [period, *prices]] for name, prices in triples
                ],
            }
        rows = source.parse_with_ocr(
            original("26295de6bbb0"),
            "https://porkcolombia.co/wp-content/uploads/2023/12/Semana52de2020-1.pdf",
            "colombia-pork-pdf",
            readings,
        )
        self.assertEqual(len(rows), 36)
        self.assertEqual({r["date"] for r in rows}, {"2020-12-30", "2020-12-31"})
        invalid = copy.deepcopy(readings)
        invalid[1]["text"] = "Fecha"
        with self.assertRaisesRegex(ValueError, "explicit observation date"):
            source.parse_with_ocr(
                original("26295de6bbb0"),
                "https://porkcolombia.co/wp-content/uploads/2023/12/Semana52de2020-1.pdf",
                "colombia-pork-pdf",
                invalid,
            )


class MoreArchivedLayouts(unittest.TestCase):
    def test_wrapped_headers_keep_native_columns(self):
        for prefix in ("8f34f4f576b0", "d7f5ff193ffa"):
            with self.subTest(original=prefix):
                rows = source.parse_corabastos(
                    original(prefix), "https://corabastos.com.co/original.pdf"
                )
                self.assertEqual(len(rows), 350)
                self.assertTrue(
                    any(r["product_id"] == "acelga" and r["price"] for r in rows)
                )

    def test_print_export_retains_columns_across_page_breaks(self):
        rows = source.parse_corabastos(
            original("7417d00f8882"), "https://corabastos.com.co/original.pdf"
        )
        self.assertEqual(len(rows), 350)
        self.assertEqual({r["details"]["source_page"] for r in rows}, set(range(1, 8)))
        first = next(
            r
            for r in rows
            if r["product_id"] == "acelga" and r["details"]["quality"] == "extra"
        )
        self.assertEqual(first["price"], 20000)
        self.assertEqual(first["details"]["unit_price_as_published"], 2000)

    def test_duplicate_printed_prices_are_not_arbitrarily_selected(self):
        rows = source.parse_corabastos(
            original("b1cbd0ebec79"), "https://corabastos.com.co/original.pdf"
        )
        self.assertEqual(len(rows), 692)
        reviews = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(reviews), 148)
        self.assertTrue(
            all("different prices" in r["details"]["quality_issue"] for r in reviews)
        )

    def test_misaligned_publisher_table_is_reviewed_without_losing_other_tables(self):
        rows = source.parse_corabastos(
            original("470ff6ce5c3f"), "https://corabastos.com.co/original.pdf"
        )
        self.assertEqual(len(rows), 350)
        reviews = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(reviews), 6)
        self.assertTrue(all(r["price"] is None for r in reviews))

    def test_scanned_report_requests_ocr_instead_of_guessing_its_date(self):
        with self.assertRaises(source.NormalExtractionFailed) as got:
            source.parse_pork(original("91882ddf654a"))
        self.assertEqual(got.exception.required_pages, (1, 2, 3, 4))

    def test_vertical_ocr_uses_actual_column_and_explicit_price_basis(self):
        from datetime import date

        table = [
            ["Cerdo en pie ($/Kilo)"],
            ["Mercado", "Semana anterior", "Semana actual", "Var %"],
            ["Antioquia", "8.490", "8.545", "0,6%"],
            ["Promedio nacional", "8.562", "8.593", "0,4%"],
        ]
        rows = source._pork_vertical_ocr(table, 1, 1, date(2021, 12, 23), {})
        self.assertEqual([r["price"] for r in rows], [8545, 8593])
        self.assertTrue(all(r["product_name"] == "Cerdo en pie" for r in rows))
        with self.assertRaisesRegex(ValueError, "explicit product title"):
            source._pork_vertical_ocr(table[1:], 1, 1, date(2021, 12, 23), {})
