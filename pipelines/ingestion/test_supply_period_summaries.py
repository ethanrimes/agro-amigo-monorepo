"""Independent native cells, printed tables, and non-additive SQL publication."""

import io
import os
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
import pdfplumber

from . import supply_period_summaries as adapter
from . import worker

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/source-verification-2026-09-28/supply-reference-audit/originals"
)
XLS = "anex-SIPSAabastecimiento-ago2026.xlsx"
PDF = "bol-SIPSAabastecimiento-ago2026.pdf"
APRIL_2024_PDF = (
    Path(__file__).resolve().parent
    / "testdata/bol-SIPSAabastecimiento-1raquincenaAbril2024.pdf"
)


def body(name):
    return (FIXTURES / name).read_bytes()


def mutate(action):
    book = openpyxl.load_workbook(io.BytesIO(body(XLS)), data_only=True)
    action(book)
    out = io.BytesIO()
    book.save(out)
    book.close()
    return out.getvalue()


class NativePeriodSummaries(unittest.TestCase):
    def test_april_2024_fortnight_original_printed_market_table(self):
        rows, reviews = adapter.parse_pdf(
            APRIL_2024_PDF.read_bytes(), date(2024, 4, 15)
        )
        self.assertEqual((len(rows), reviews), (99, []))
        self.assertEqual(len({r["name"] for r in rows}), 33)
        expected = {
            "Armenia, Mercar": [4821, 5088, 5.54],
            "Bucaramanga, Centroabastos": [22334, 22376, 0.19],
            "Florencia, Florencia (Caquetá)": [668, 668, 0.03],
            "Santa Marta, Santa Marta (Magdalena)": [2133, 2086, -2.18],
            "Tibasosa, Coomproriente": [3028, 3191, 5.39],
            "TOTAL": [309952, 307712, -0.72],
        }
        for name, values in expected.items():
            self.assertEqual(
                [r["details"]["value"] for r in rows if r["name"] == name], values
            )
        for row in rows:
            details = row["details"]
            self.assertEqual(details["source_page"], 4)
            self.assertEqual(details["frequency"], "first_fortnight")
            self.assertEqual(details["precision"], "printed_pdf_value")
            self.assertEqual(
                (details["period_start"], details["period_end"]),
                ("2024-03-01", "2024-03-15")
                if "column 1;" in row["source_locator"]
                else ("2024-04-01", "2024-04-15"),
            )

    def test_april_2024_market_column_crossing_boundary_is_reviewed(self):
        from contextlib import nullcontext

        with pdfplumber.open(io.BytesIO(APRIL_2024_PDF.read_bytes())) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                words = page.extract_words()
                if i == 3:
                    words = [
                        {**w, "x0": 140, "x1": 143}
                        if w["text"] == "Mercar" and abs(w["top"] - 185.75) < 2
                        else w
                        for w in words
                    ]
                text = page.extract_text()
                pages.append(
                    SimpleNamespace(
                        width=page.width,
                        extract_text=lambda text=text: text,
                        extract_words=lambda words=words: words,
                    )
                )
        with patch.object(
            adapter.pdfplumber,
            "open",
            return_value=nullcontext(SimpleNamespace(pages=pages)),
        ):
            rows, reviews = adapter.parse_pdf(APRIL_2024_PDF.read_bytes())
        self.assertEqual(rows, [])
        self.assertTrue(any("missing literal city/market binding" in x for x in reviews))

    def test_four_workbooks_independent_literals_and_full_cell_parity(self):
        fixtures = [
            (
                "anexo_abastecimiento_ene21.xlsx",
                868,
                0,
                "2021-01-31",
                10044.0664,
                -7.66206585093862,
            ),
            (
                "anexo_abastecimiento_1quincena_ene21.xlsx",
                148,
                1,
                "2021-01-15",
                4543.8124,
                -11.86737354123717,
            ),
            (XLS, 983, 0, "2026-08-31", 9639.741779999998, -4.11391870005231),
            (
                "anex-SIPSAabastecimiento-1raquinago2026.xlsx",
                983,
                0,
                "2026-08-15",
                4655.74,
                -3.52312564400511,
            ),
        ]
        for filename, count, review_count, end, tonnes, change in fixtures:
            with self.subTest(filename=filename):
                rows, reviews = adapter.parse_workbook(body(filename))
                self.assertEqual((len(rows), len(reviews)), (count, review_count))
                book = openpyxl.load_workbook(
                    io.BytesIO(body(filename)), data_only=True
                )
                for r in rows:
                    d = r["details"]
                    c = book[d["sheet"]][d["cell"]]
                    expected = c.value
                    if expected is not None and "%" in c.number_format:
                        expected *= 100
                    self.assertEqual(d["value"], expected)
                    self.assertEqual(d["literal_value"], c.value)
                    self.assertTrue(d["non_additive"])
                    self.assertNotIn("price", r)
                    self.assertEqual(d["precision"], "native_workbook_value")
                book.close()
                a = next(
                    r
                    for r in rows
                    if r["details"].get("sheet") == "1"
                    and r["details"]["cell"] == "D11"
                )
                v = next(
                    r
                    for r in rows
                    if r["details"].get("sheet") == "1"
                    and r["details"]["cell"] == "E11"
                )
                self.assertEqual(
                    (a["name"], a["observed_on"].isoformat()), ("Armenia, Mercar", end)
                )
                self.assertEqual(a["details"]["value"], tonnes)
                self.assertAlmostEqual(v["details"]["value"], change)
                self.assertEqual(
                    (a["details"]["unit"], v["details"]["unit"]),
                    ("t", "percentage_points"),
                )
                self.assertNotIn("provisional", a["details"])
                if review_count:
                    self.assertIn("column period conflicts", reviews[0])
                    self.assertFalse(any(r["details"]["sheet"] == "2" for r in rows))

    def test_old_current_pdf_visual_anchors_and_declared_counts(self):
        fixtures = [
            (
                "bol_abas_ene13.pdf",
                42,
                4,
                "2013-01-31",
                5919,
                6458,
                [323349, 361170, 11.7],
            ),
            (
                "bol_abas_1quincena_ene13.pdf",
                42,
                3,
                "2013-01-15",
                2575,
                3083,
                [164418, 159204, -3.2],
            ),
            (PDF, 99, 3, "2026-08-31", 9640, 10053, [669196, 618993, -7.5]),
            (
                "bol-SIPSAabastecimiento-1raquinago2026.pdf",
                99,
                4,
                "2026-08-15",
                4656,
                4826,
                [319999, 297464, -7.04],
            ),
        ]
        for filename, count, page, end, current, prior, totals in fixtures:
            with self.subTest(filename=filename):
                rows, reviews = adapter.parse_pdf(body(filename))
                self.assertEqual((len(rows), reviews), (count, []))
                arm = [r for r in rows if r["name"] == "Armenia, Mercar"]
                self.assertEqual(
                    [r["details"]["value"] for r in arm[:2]], [prior, current]
                )
                self.assertEqual(arm[1]["observed_on"].isoformat(), end)
                self.assertEqual(arm[0]["details"]["source_page"], page)
                self.assertEqual(
                    [
                        r["details"]["value"]
                        for r in rows
                        if r["name"].lower() == "total"
                    ],
                    totals,
                )
                self.assertTrue(
                    all(r["details"]["precision"] == "printed_pdf_value" for r in rows)
                )
                self.assertEqual(
                    min(r["details"]["period_start"] for r in rows),
                    "2012-12-01" if "13.pdf" in filename else "2026-07-01",
                )
                self.assertTrue(all(r["details"]["source_page"] >= page for r in rows))
                # Page 2 old price/kg and quantity/kg chart ticks are not table readings.
                self.assertFalse(any(r["details"]["source_page"] == 2 for r in rows))

    def test_old_pdf_all_84_printed_market_literals(self):
        # Read independently from the rendered January 2013 market tables.
        monthly = [
            [121904, 137280, 12.6],
            [53354, 59259, 11.1],
            [31771, 34785, 9.5],
            [24238, 24435, 0.8],
            [18796, 21981, 16.9],
            [12995, 15732, 21.1],
            [14237, 18885, 32.6],
            [20600, 20518, -0.4],
            [7112, 7967, 12.0],
            [6204, 6792, 9.5],
            [4441, 6479, 45.9],
            [6458, 5919, -8.3],
            [1239, 1137, -8.2],
            [323349, 361170, 11.7],
        ]
        fortnight = [
            [65621, 59102, -9.9],
            [28107, 26615, -5.3],
            [17025, 15856, -6.9],
            [9069, 10148, 11.9],
            [9123, 9515, 4.3],
            [6377, 7335, 15.0],
            [6750, 8060, 19.4],
            [10483, 10125, -3.4],
            [3612, 3691, 2.2],
            [2770, 2946, 6.4],
            [2040, 2749, 34.8],
            [3083, 2575, -16.5],
            [359, 487, 35.9],
            [164418, 159204, -3.2],
        ]
        for filename, literals in [
            ("bol_abas_ene13.pdf", monthly),
            ("bol_abas_1quincena_ene13.pdf", fortnight),
        ]:
            rows, reviews = adapter.parse_pdf(body(filename))
            self.assertEqual(reviews, [])
            self.assertEqual(
                [r["details"]["value"] for r in rows],
                [v for triple in literals for v in triple],
            )

    def test_pdf_current_entire_market_quantity_table_matches_native_rounding(self):
        for suffix in ["ago2026", "1raquinago2026"]:
            x, _ = adapter.parse_workbook(
                body("anex-SIPSAabastecimiento-" + suffix + ".xlsx")
            )
            p, _ = adapter.parse_pdf(body("bol-SIPSAabastecimiento-" + suffix + ".pdf"))
            x = [r for r in x if r["details"]["sheet"] == "1"]
            self.assertEqual(len(x), len(p))
            for xr, pr in zip(x, p):
                import re

                normalize = lambda name: re.sub(r"[^a-záéíóúñ0-9]", "", name.lower())
                self.assertEqual(normalize(xr["name"]), normalize(pr["name"]))
                self.assertEqual(xr["observed_on"], pr["observed_on"])
                self.assertEqual(xr["details"]["unit"], pr["details"]["unit"])
                # All 66 quantity cells and 33 percentages, independently printed.
                tolerance = 0.5 if xr["details"]["unit"] == "t" else 0.0051
                self.assertLessEqual(
                    abs(xr["details"]["value"] - pr["details"]["value"]), tolerance
                )

    def test_zero_blank_and_percent_are_distinct_and_blank_group_preserved(self):
        def change(b):
            b["1"]["C11"] = 0
            b["1"]["D11"] = None
            for c in range(2, 7):
                b["2"].cell(13, c).value = None

        rows, reviews = adapter.parse_workbook(mutate(change))
        self.assertEqual(reviews, [])
        lookup = {(r["details"]["sheet"], r["details"]["cell"]): r for r in rows}
        self.assertEqual(lookup["1", "C11"]["details"]["availability"], "reported")
        self.assertEqual(lookup["1", "C11"]["details"]["value"], 0)
        self.assertEqual(lookup["1", "D11"]["details"]["availability"], "not_reported")
        self.assertIsNone(lookup["2", "B13"]["details"]["value"])
        self.assertEqual(lookup["2", "B13"]["details"]["food_group"], "Frutas")

    def test_malformed_units_values_duplicates_are_reviewed_per_table(self):
        for action in [
            lambda b: b["1"].__setitem__("D10", "Agosto 2026 (pesos)"),
            lambda b: b["1"].__setitem__("D11", -1),
            lambda b: b["1"].__setitem__("D11", "9.640 aprox"),
            lambda b: (
                b["1"].__setitem__("A12", "Armenia"),
                b["1"].__setitem__("B12", "Mercar"),
            ),
        ]:
            rows, reviews = adapter.parse_workbook(mutate(action))
            self.assertEqual(len(reviews), 1)
            self.assertFalse(any(r["details"]["sheet"] == "1" for r in rows))
            self.assertEqual(len(rows), 884)

    def test_invalid_native_share_bounds_review_only_affected_table(self):
        for value in [-0.01, 1.01]:
            rows, reviews = adapter.parse_workbook(
                mutate(lambda b, value=value: b["3"].__setitem__("B11", value))
            )
            self.assertEqual(len(rows), 919)
            self.assertEqual(len(reviews), 1)
            self.assertIn("share outside", reviews[0])

    def test_explicit_periods_archive_year_and_future_are_not_guessed(self):
        self.assertEqual(
            adapter.periods("Enero de 2021", "Diciembre 2020", "Enero 2021")[0][:2],
            (date(2020, 12, 1), date(2020, 12, 31)),
        )
        with self.assertRaises(ValueError):
            adapter.periods(
                "Primera quincena de enero de 2021", "Diciembre 2020", "Enero 2020"
            )
        for expected in [date(2025, 8, 31), date(2026, 7, 31)]:
            rows, reviews = adapter.parse_workbook(body(XLS), expected)
            self.assertEqual(rows, [])
            self.assertEqual(len(reviews), 3)
        with patch.object(worker, "today", return_value=date(2026, 7, 31)):
            rows, reviews = adapter.parse_workbook(body(XLS))
            self.assertEqual(rows, [])
            self.assertEqual(len(reviews), 3)

    def test_pdf_missing_native_cell_does_not_publish_partial_table(self):
        with pdfplumber.open(io.BytesIO(body(PDF))) as pdf:
            pages = []
            for i, p in enumerate(pdf.pages):
                words = p.extract_words()
                text = p.extract_text()
                if i == 2:
                    words = [w for w in words if w["text"] != "9.640"]
                pages.append(
                    SimpleNamespace(
                        width=p.width,
                        extract_text=lambda text=text: text,
                        extract_words=lambda words=words: words,
                    )
                )
            fake = SimpleNamespace(pages=pages)
            from contextlib import nullcontext

            with patch.object(
                adapter.pdfplumber, "open", return_value=nullcontext(fake)
            ):
                rows, reviews = adapter.parse_pdf(body(PDF))
            self.assertEqual(rows, [])
            self.assertTrue(reviews)

    def test_pdf_table_year_cannot_inherit_conflicting_cover_date(self):
        from contextlib import nullcontext

        with pdfplumber.open(io.BytesIO(body(PDF))) as pdf:
            pages = []
            for i, p in enumerate(pdf.pages):
                words = p.extract_words()
                text = p.extract_text()
                if i == 2:
                    words = [
                        {**w, "text": "2025"} if w["text"] == "2026" else w
                        for w in words
                    ]
                pages.append(
                    SimpleNamespace(
                        width=p.width,
                        extract_text=lambda text=text: text,
                        extract_words=lambda words=words: words,
                    )
                )
            with patch.object(
                adapter.pdfplumber,
                "open",
                return_value=nullcontext(SimpleNamespace(pages=pages)),
            ):
                rows, reviews = adapter.parse_pdf(body(PDF))
            self.assertEqual(rows, [])
            self.assertIn("caption years conflict", reviews[0])

    def test_unknown_layout_is_not_a_false_typed_success(self):
        self.assertEqual(
            adapter.parse_workbook(b"unsupported XLS legacy"),
            ([], ["Unsupported native summary workbook format"]),
        )
        self.assertEqual(
            adapter.parse_workbook(
                mutate(
                    lambda b: [
                        b[s].__setitem__("A6", "Unknown layout")
                        for s in ["1", "2", "3"]
                    ]
                )
            ),
            ([], []),
        )
        self.assertEqual(worker.parser_version("supply-reference-pdf"), adapter.VERSION)
        self.assertTrue(
            worker.parser_version("supply-reference").endswith(":" + adapter.VERSION)
        )
        self.assertIn(
            "pipelines/ingestion/supply_period_summaries.py", worker.RELEASE_FILES
        )


@unittest.skipUnless(
    os.environ.get("AGRO_DAILY_ZIP_POSTGRES_TEST") == "1", "isolated PostgreSQL opt-in"
)
class PeriodPublicationPostgres(unittest.TestCase):
    from .test_daily_archives import ArchivePublicationPostgres as _Fixture

    setUp = _Fixture.setUp

    def test_versioned_reference_rows_idempotent_original_separation_and_review(self):
        a = body("anexo_abastecimiento_1quincena_ene21.xlsx")
        # Real archive functions retain originals; append-only references use their hashes.
        da = worker.archive(self.db, self.url, a, "supply-reference", None)
        with self.db.transaction():
            self.assertEqual(
                adapter.publish(self.db, a, da, "supply-reference")[0], 148
            )
        self.assertEqual(adapter.publish(self.db, a, da, "supply-reference")[0], 148)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_reference_row").fetchone(),
            (148,),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM retained_record WHERE table_name='supply_period_summary_review'"
            ).fetchone(),
            (1,),
        )
        b = body(XLS)
        db = worker.archive(self.db, self.url, b, "supply-reference", None)
        try:
            with self.db.transaction():
                adapter.publish(self.db, b, db, "supply-reference")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_reference_row").fetchone(),
            (148,),
        )
        adapter.publish(self.db, b, db, "supply-reference")
        self.assertEqual(
            self.db.execute(
                "SELECT count(DISTINCT document_id) FROM input_reference_row"
            ).fetchone(),
            (2,),
        )
        for table in [
            "regional_price",
            "daily_price",
            "historical_price",
            "official_price_quote",
        ]:
            self.assertEqual(
                self.db.execute("SELECT count(*) FROM " + table).fetchone(), (0,)
            )

    def test_worker_standalone_workbook_and_pdf_dispatch(self):
        for filename, kind, count in [
            (XLS, "supply-reference", 983),
            (PDF, "supply-reference-pdf", 99),
        ]:
            url = self.url.rsplit("/", 1)[0] + "/" + filename
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,status,observed_on) VALUES(%s,%s,'pending',%s)",
                (url, kind, date(2026, 8, 31)),
            )
            with (
                patch.object(worker, "fetch_asset", return_value=body(filename)),
                patch("pipelines.ingestion.pdf_sources.extract_pages") as pages,
                patch(
                    "pipelines.ingestion.ocr.scan_document",
                    side_effect=AssertionError(
                        "No new generic OCR for readable tables"
                    ),
                ),
            ):
                self.assertEqual(
                    worker.process_asset(self.db, url, kind, date(2026, 8, 31)), count
                )
                self.assertEqual(pages.call_count, int(kind.endswith("pdf")))
            self.assertEqual(
                self.db.execute(
                    "SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s",
                    (url,),
                ).fetchone(),
                ("complete", count, worker.parser_version(kind)),
            )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_reference_row").fetchone(),
            (1082,),
        )

    def test_actual_evidence_sql_exposes_period_unit_without_price_projection(self):
        import re

        data = body(XLS)
        did = worker.archive(self.db, self.url, data, "supply-reference", None)
        adapter.publish(self.db, data, did, "supply-reference")
        source = (
            Path(__file__).resolve().parents[2] / "apps/web/src/lib/server/planning.ts"
        ).read_text()
        snippets = re.findall(r"`([^`]+)`", source)
        summary = next(
            q
            for q in snippets
            if q.startswith("SELECT count(*) FILTER")
            and "kind='supply-period-summary'" in q
        )
        values = self.db.execute(summary.replace("$1", "%s"), (did,)).fetchone()
        self.assertEqual(
            values, (394, 589, 983, "2026-07-01", "2026-08-31", "1", None, "monthly")
        )
        query = next(
            q
            for q in snippets
            if q.startswith("SELECT kind,observed_on")
            and "kind='supply-period-summary'" in q
        )
        locator = "1!row 11,col 4; " + adapter.VERSION
        selected = self.db.execute(
            query.replace("$1", "%s").replace("$2", "%s"), (did, locator, locator)
        ).fetchall()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][0], adapter.KIND)
        self.assertEqual(selected[0][5:8], ("t", 9639.741779999998, "market_total"))
