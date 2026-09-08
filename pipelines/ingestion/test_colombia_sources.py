"""Contract, source semantics and real-fixture regressions for official Colombia prices."""

import copy
import json
import unittest
from datetime import date
from pathlib import Path

from . import colombia_sources as source

FIXTURES = Path(__file__).resolve().parents[2] / "artifacts" / "official-sources"


def fixture(name):
    path = FIXTURES / name
    if not path.exists():
        raise unittest.SkipTest("Downloaded official fixture not present: " + name)
    return path.read_bytes()


class DatesAndNumbers(unittest.TestCase):
    def test_reference_week_crosses_month_and_year(self):
        self.assertEqual(
            source.weekly_period("31 al 06 de septiembre de 202\u200b6"),
            (date(2026, 8, 31), date(2026, 9, 6)),
        )
        self.assertEqual(
            source.weekly_period("29 al 04 de enero de 2026"),
            (date(2025, 12, 29), date(2026, 1, 4)),
        )
        self.assertEqual(
            source.weekly_period("30 diciembre de 2024 al 5 enero de 2025"),
            (date(2024, 12, 30), date(2025, 1, 5)),
        )
        with self.assertRaises(ValueError):
            source.weekly_period("1 al 30 de septiembre de 2026")

    def test_colombian_decimal_conventions(self):
        self.assertEqual(source.colombian_number("$16.311,70\u200b/kg"), 16311.7)
        self.assertEqual(source.colombian_number("$33.968.30", cacao=True), 33968.3)
        self.assertEqual(source.colombian_number("4.054"), 4054)
        self.assertEqual(source._pork_ocr_number("$ 5,328"), 5328)
        with self.assertRaises(ValueError):
            source._pork_ocr_number("5,3?8")

    def test_cacao_effective_date_is_week_start(self):
        html = b"<table><tr><th>Precio</th></tr><tr><td>07 al 13 de septiembre de 2026</td><td>$16.162,00/kg</td></tr></table>"
        row = source.parse_cacao(html)[0]
        self.assertEqual(row["date"], "2026-09-07")
        self.assertEqual(row["details"]["period_end"], "2026-09-13")

    def test_ambiguous_cacao_publisher_typo_retained_for_review(self):
        rows = source.parse_cacao(fixture("agronet-cacao.html"))
        bad = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(rows), 253)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["details"]["original_price"], "$22.421.720")
        self.assertIsNone(bad[0]["price"])


class Discovery(unittest.TestCase):
    def test_leaf_files_do_not_decode_as_html(self):
        for kind in (
            "colombia-pork-pdf",
            "colombia-corabastos-pdf",
            "colombia-evidence",
            "colombia-fedegan-csv",
        ):
            self.assertEqual(
                source.discover(b"\xff\x00%PDF", source.PORK_PRICES, kind), []
            )

    def test_official_archive_contract(self):
        for url, kind in source.discover():
            self.assertIn(kind, source.PUBLISHERS)
            self.assertTrue(source._trusted(url))
        with self.assertRaises(ValueError):
            source.discover(
                b"<html/>", "https://unverified.example/prices", "colombia-pork-index"
            )

    def test_corabastos_calendar_and_media_pagination(self):
        discovered = source.discover(
            fixture("corabastos.html"),
            source.CORABASTOS_PRICES,
            "colombia-corabastos-index",
            date(2026, 9, 7),
        )
        self.assertIn(
            (
                "https://corabastos.com.co/wp-content/uploads/2026/09/Boletin_diario_20260907.pdf",
                "colombia-corabastos-pdf",
            ),
            discovered,
        )
        self.assertGreater(len(discovered), 300)
        discovered = source.discover(
            fixture("corabastos-media.json"),
            source.CORABASTOS_MEDIA,
            "colombia-corabastos-media",
        )
        self.assertTrue(
            any(
                "page=2" in url
                for url, kind in discovered
                if kind == "colombia-corabastos-media"
            )
        )

    def test_fedegan_exports_follow_published_indicator_ids(self):
        discovered = source.discover(
            fixture("fedegan-prices.html"),
            source.FEDEGAN_PRICES,
            "colombia-fedegan-index",
            date(2026, 9, 7),
        )
        self.assertEqual(len(discovered), 6)
        self.assertTrue(
            all(
                "pSd=01-01-1900" in url and "pEd=31-12-2026" in url
                for url, _ in discovered
            )
        )
        for url, kind in discovered:
            self.assertEqual(kind, "colombia-fedegan-csv")


class PriceSemantics(unittest.TestCase):
    def test_palm_regulatory_basis_and_full_history(self):
        rows = source.parse_palm(fixture("fedepalma-ffp.html"), source.FEDEPALMA_FFP)
        self.assertEqual(len(rows), 130)
        self.assertEqual(min(r["date"] for r in rows), "1994-07-01")
        current = [r for r in rows if r["date"] == "2026-07-01"]
        self.assertEqual(
            {r["product_name"]: r["price"] for r in current},
            {"Aceite de palma crudo": 4054, "Palmiste": 2126},
        )
        self.assertTrue(
            all("regulatoria" in r["basis"] and r["unit"] == "kg" for r in rows)
        )

    def test_fedegan_method_break_is_a_separate_series(self):
        rows = source.parse_fedegan(
            fixture("fedegan-74.csv"),
            "https://estadisticas.fedegan.org.co/DOC/export.jsp?pId=74",
        )
        july = next(
            r
            for r in rows
            if r["date"] == "2026-07-31" and r["market"] == "Región Caribe"
        )
        august = next(
            r
            for r in rows
            if r["date"] == "2026-08-31" and r["market"] == "Región Caribe"
        )
        self.assertEqual(july["price"], 10016)
        self.assertEqual(august["price"], 10490)
        self.assertNotEqual(july["series"], august["series"])
        self.assertIn("transición", august["basis"])
        self.assertEqual(august["unit"], "kg en pie")

    def test_fedegan_zero_is_retained_for_review(self):
        rows = source.parse_fedegan(
            fixture("fedegan-75.csv"),
            "https://estadisticas.fedegan.org.co/DOC/export.jsp?pId=75",
        )
        bad = [r for r in rows if r["details"].get("quality_issue")]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["date"], "2019-05-31")
        self.assertIsNone(bad[0]["price"])

    def test_current_bananas_keep_package_and_quality(self):
        rows = source.parse_corabastos(
            fixture("corabastos-20260907.pdf"),
            "https://corabastos.com.co/wp-content/uploads/2026/09/Boletin_diario_20260907.pdf",
        )
        self.assertEqual(len(rows), 350)
        banana = [r for r in rows if r["product_id"] == "banano-uraba"]
        self.assertEqual(
            {r["details"]["quality"]: r["price"] for r in banana},
            {"extra": 45000, "primera": 42000},
        )
        self.assertEqual(banana[0]["identity_dimensions"]["quantity"], 20)
        self.assertIn("CAJA", banana[0]["unit"])
        self.assertNotIn("kg", banana[0]["unit"])

    def test_older_corabastos_has_native_wrapped_names(self):
        rows = source.parse_corabastos(
            fixture("corabastos-20240408.pdf"),
            "https://corabastos.com.co/wp-content/uploads/2024/04/Boletin-de-precios-08abril2024.pdf",
        )
        self.assertEqual(len(rows), 352)
        white = next(
            r
            for r in rows
            if r["product_id"] == "cebolla-cabezona-blanca"
            and r["details"]["quality"] == "extra"
        )
        self.assertEqual(white["price"], 70000)
        self.assertEqual(white["details"]["published_unit"], "KILO")
        oil = next(r for r in rows if r["product_id"] == "aceite-1000-c-c")
        self.assertEqual(oil["details"]["quality"], "desde")
        self.assertEqual(oil["details"]["published_unit"], "UNIDAD")

    def test_mislabeled_pdf_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "date differs"):
            source.parse_corabastos(
                fixture("corabastos-20260907.pdf"),
                "https://corabastos.com.co/wp-content/uploads/2026/09/Boletin_diario_20260908.pdf",
            )

    def test_native_pork_prices_and_out_of_sequence_months(self):
        rows = source.parse_pork(fixture("pork-2026-18.pdf"))
        self.assertEqual(len(rows), 239)
        self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))
        self.assertEqual(sum(bool(r["details"].get("quality_issue")) for r in rows), 6)
        current = [
            r for r in rows if r["date"] == "2026-08-28" and r["market"] == "Colombia"
        ]
        self.assertEqual(
            {r["product_name"]: r["price"] for r in current},
            {
                "Cerdo en pie": 6670,
                "Cerdo · canal caliente": 9117,
                "Cerdo · canal fría": 9183,
            },
        )
        self.assertTrue(all("ocr" not in r["details"] for r in rows))

    def test_older_pork_wrapped_national_row(self):
        rows = source.parse_pork(fixture("semana-1-enero-2023.pdf"))
        self.assertEqual(len(rows), 180)
        self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))
        self.assertEqual(sum(r["series"] == "porkcolombia-monthly" for r in rows), 165)
        current = [
            r for r in rows if r["date"] == "2023-01-06" and r["market"] == "Colombia"
        ]
        self.assertEqual(
            {r["product_name"]: r["price"] for r in current},
            {
                "Cerdo en pie": 10514,
                "Cerdo · canal caliente": 13533,
                "Cerdo · canal fría": 14189,
            },
        )


class OcrFallback(unittest.TestCase):
    @staticmethod
    def actual_readings():
        from .ocr import compare_readings

        readings = {}
        for page in (2, 3):
            first = json.loads(fixture(f"pork-2020-page{page}-reading0.json"))
            second = json.loads(fixture(f"pork-2020-page{page}-reading1.json"))
            if not compare_readings(first, second):
                raise AssertionError("Cached independent provider readings disagree")
            readings[page] = first
        return readings

    @staticmethod
    def readings():
        """Hand-checked literal cells from original 2020 pages, not a model call."""
        header = [
            "",
            "Antioquia",
            "Eje Cafetero",
            "Valle del Cauca",
            "Caribe Norte",
            "Bogotá",
            "Promedio Muestra",
        ]
        triples = [
            ("Precio en Pie", ["5,286", "5,295", "5,258", "5,263", "5,361", "5,298"]),
            (
                "Precio en Canal Caliente",
                ["6,935", "6,981", "7,083", "7,013", "7,082", "7,023"],
            ),
            (
                "Precio en Canal Fría",
                ["7,119", "7,189", "7,364", "7,251", "7,306", "7,254"],
            ),
        ]
        pages = {}
        for page in [2, 3]:
            tables = []
            for name, values in triples:
                tables.append(
                    [
                        header,
                        [name],
                        ["Semana Actual" if page == 2 else "27-mar-20", *values],
                    ]
                )
            pages[page] = {
                "text": "",
                "tables": tables,
                "review_notes": [],
                "model": "test-literal-fixture",
            }
        return pages

    def test_image_tables_with_native_headers_request_only_needed_pages(self):
        with self.assertRaises(source.NormalExtractionFailed) as caught:
            source.parse_pork(fixture("semana-4-marzo-2020.pdf"))
        self.assertEqual(caught.exception.required_pages, (2, 3))

    def test_ocr_prices_cross_check_duplicate_tables(self):
        body = fixture("semana-4-marzo-2020.pdf")
        rows = source.parse_with_ocr(
            body,
            "https://porkcolombia.co/wp-content/uploads/2023/12/Semana12de2020.pdf",
            "colombia-pork-pdf",
            self.readings(),
        )
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(r["date"] == "2020-03-27" for r in rows))
        changed = copy.deepcopy(self.readings())
        changed[3]["tables"][0][2][1] = "5,287"
        with self.assertRaisesRegex(ValueError, "disagree"):
            source.parse_with_ocr(
                body,
                "https://porkcolombia.co/wp-content/uploads/2023/12/Semana12de2020.pdf",
                "colombia-pork-pdf",
                changed,
            )

    def test_ocr_missing_page_cannot_publish_partial_report(self):
        with self.assertRaises(source.NormalExtractionFailed):
            source.parse_with_ocr(
                fixture("semana-4-marzo-2020.pdf"),
                "https://porkcolombia.co/wp-content/uploads/2023/12/Semana12de2020.pdf",
                "colombia-pork-pdf",
                {2: self.readings()[2]},
            )

    def test_actual_gemini_tables_match_explicit_native_price_headings(self):
        body = fixture("semana-4-marzo-2020.pdf")
        url = "https://porkcolombia.co/wp-content/uploads/2023/12/Semana12de2020.pdf"
        readings = self.actual_readings()
        rows = source.parse_with_ocr(body, url, "colombia-pork-pdf", readings)
        self.assertEqual(len(rows), 108)
        self.assertEqual(sum(r["series"] == "porkcolombia-monthly" for r in rows), 36)
        national = {
            (r["date"], r["product_name"]): r["price"]
            for r in rows
            if r["market"] == "Colombia"
        }
        self.assertEqual(national[("2020-01-31", "Cerdo en pie")], 5744)
        self.assertEqual(national[("2020-02-29", "Cerdo · canal caliente")], 7320)
        self.assertEqual(national[("2020-03-27", "Cerdo · canal fría")], 7254)
        # OCR emitted page 3's titles separately from its tables. Identity must
        # follow literal cross-page values, independent of the table array order.
        readings[3]["tables"].reverse()
        reordered = source.parse_with_ocr(body, url, "colombia-pork-pdf", readings)

        def observations(values):
            return sorted(
                (r["product_id"], r["series"], r["market"], r["date"], r["price"])
                for r in values
            )

        self.assertEqual(observations(rows), observations(reordered))

    def test_untitled_ocr_table_requires_exact_cross_page_values(self):
        readings = self.actual_readings()
        current = next(row for row in readings[3]["tables"][0] if "27-mar-20" in row)
        current[2] = "5,287"
        with self.assertRaisesRegex(ValueError, "uniquely linked"):
            source.parse_with_ocr(
                fixture("semana-4-marzo-2020.pdf"),
                "https://porkcolombia.co/wp-content/uploads/2023/12/Semana12de2020.pdf",
                "colombia-pork-pdf",
                readings,
            )

    def test_ocr_not_used_on_normally_readable_documents(self):
        rows = source.parse_with_ocr(
            fixture("agronet-cacao.html"),
            source.AGRONET_CACAO,
            "colombia-agronet-cacao",
            {2: {"tables": [["invented"]]}},
        )
        self.assertEqual(rows[0]["price"], 16311.7)


if __name__ == "__main__":
    unittest.main()
