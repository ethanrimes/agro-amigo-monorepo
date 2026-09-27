"""Department-grouped milk reports, explicit dates and min/max boundaries."""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from .special_prices import parse_milk_pdf, parse_special
from .worker import SourceDateMismatch

HEAD = [
    [
        "Cuadro 1. Precios de leche cruda en finca",
        "TODOS LOS PRECIOS ESTÁN EN PESOS POR LITRO",
    ],
    [
        "Departamentos y municipios",
        "Precio Mínimo",
        "Precio Máximo",
        "Precio Promedio",
        "Tendencia",
    ],
]


def parse_rows(rows, sheet="Reporte Nov 2022", day=date(2022, 11, 30)):
    with patch(
        "pipelines.ingestion.worker.workbooks", return_value=[(sheet, iter(rows))]
    ):
        return list(parse_special(b"native-source", "milk", day))


class GroupedMilk(unittest.TestCase):
    def test_same_named_municipality_retains_department_context_and_litre(self):
        rows = parse_rows(
            HEAD
            + [
                ["Antioquia", None, None, None],
                ["La Unión", 1780, 2185, 2048.9697671351323],
                ["Nariño", None, None, None],
                ["La Unión", 1500, 1900, 1700],
            ]
        )
        self.assertEqual([r[-1]["department"] for r in rows], ["Antioquia", "Nariño"])
        self.assertEqual({r[5] for r in rows}, {"litre"})
        self.assertEqual({r[2] for r in rows}, {date(2022, 11, 30)})
        self.assertEqual(rows[0][6], 2048.9697671351323)
        self.assertEqual(rows[0][-1]["price_basis"], "farmgate")

    def test_sheet_date_is_required_to_agree_with_archive_date(self):
        rows = HEAD + [
            ["Antioquia", None, None, None],
            ["Abejorral", 1800, 2056, 1979.0959574269443],
        ]
        self.assertEqual(parse_rows(rows, day=None)[0][2], date(2022, 11, 30))
        with self.assertRaises(SourceDateMismatch):
            parse_rows(rows, day=date(2022, 12, 31))

    def test_unrecognized_department_never_inherits_previous_heading(self):
        with self.assertRaisesRegex(ValueError, "unverified unit or location"):
            parse_rows(
                HEAD
                + [
                    ["Antioquia", None, None, None],
                    ["Unknown department", None, None, None],
                    ["Town", 1800, 2056, 1900],
                ]
            )

    def test_only_float_representation_noise_is_tolerated(self):
        rows = HEAD + [
            ["Arauca", None, None, None],
            ["Saravena", 2000, 2000, 1999.9999999999995],
        ]
        self.assertEqual(parse_rows(rows)[0][6], 1999.9999999999995)
        rows[-1][-1] = 1999.99
        with self.assertRaisesRegex(ValueError, "minimum/maximum"):
            parse_rows(rows)

    def test_both_retained_2022_workbooks_preserve_every_positive_price_row(self):
        folder = Path("artifacts/milk-2022-layout")
        for month, day in (("nov", date(2022, 11, 30)), ("dic", date(2022, 12, 31))):
            path = folder / f"Anexo-SipsaLeche_{month}_2022.xlsx"
            if not path.exists():
                self.skipTest("Retained milk source fixture not downloaded")
            rows = list(parse_special(path.read_bytes(), "milk", day))
            self.assertEqual(len(rows), 208)
            self.assertEqual(len({r[-1]["department"] for r in rows}), 25)
            self.assertEqual(len({r[0] for r in rows}), 208)
            self.assertTrue(
                all(r[2] == day and r[-1]["quality_issue"] is None for r in rows)
            )


def milk_pdf_page(caption, prefix=""):
    text = (
        f"{prefix}\n{caption}\nPesos por litro\nDepartamentos y municipios\n"
        "Mínimo Máximo Medio\nAntioquia\nAngostura 810 943 884 ="
    )
    return SimpleNamespace(
        width=600,
        height=800,
        extract_text=lambda: text,
        crop=lambda bounds: SimpleNamespace(
            extract_text=lambda: text if bounds[0] == 0 else ""
        ),
        close=lambda: None,
    )


def parse_pdf_pages(pages, day=None):
    pdf = MagicMock()
    pdf.__enter__.return_value.pages = pages
    with patch("pdfplumber.open", return_value=pdf):
        return list(parse_milk_pdf(b"native PDF source", day))


class MilkPDFMonth(unittest.TestCase):
    def test_table_observation_month_is_not_the_later_publication_date(self):
        rows = parse_pdf_pages(
            [
                milk_pdf_page(
                    "Cuadro 1. Precios de leche cruda en finca\n2014 (agosto)",
                    "8 de octubre de 2014 · Núm. 23",
                )
            ]
        )
        self.assertEqual(rows[0][2], date(2014, 8, 31))
        self.assertEqual(rows[0][4:7], ("Angostura", "litre", 884.0))

    def test_unrelated_chart_date_is_not_a_price_table_date(self):
        rows = parse_pdf_pages(
            [
                milk_pdf_page(
                    "Cuadro 1. Precios de leche cruda en finca\n2014 (agosto)",
                    "Gráfico 1. Precio de la leche\n2014 (julio)",
                )
            ]
        )
        self.assertEqual(rows[0][2], date(2014, 8, 31))
        with self.assertRaisesRegex(ValueError, "no verifiable publication month"):
            parse_pdf_pages(
                [
                    milk_pdf_page(
                        "Cuadro 1. Precios de leche cruda en finca",
                        "Gráfico 1. Precio de la leche\n2014 (julio)",
                    )
                ]
            )

    def test_masthead_or_narrative_alone_never_supplies_the_observation_month(self):
        with self.assertRaisesRegex(ValueError, "no verifiable publication month"):
            parse_pdf_pages(
                [
                    milk_pdf_page(
                        "Cuadro 1. Precios de leche cruda en finca",
                        "8 de octubre de 2014\nDurante agosto de 2014 hubo lluvias.",
                    )
                ]
            )

    def test_archive_and_every_continuation_table_must_agree(self):
        first = milk_pdf_page(
            "Cuadro 1. Precios de leche cruda en finca\n2014 (agosto)"
        )
        with self.assertRaises(SourceDateMismatch):
            parse_pdf_pages([first], date(2014, 10, 31))
        for suffix in ("continuación", "conclusión"):
            with self.subTest(suffix=suffix):
                continuation = milk_pdf_page(
                    f"Cuadro 1. Precios de leche cruda en finca ({suffix})\n2014 (Agosto)"
                )
                rows = parse_pdf_pages([first, continuation])
                self.assertEqual({r[2] for r in rows}, {date(2014, 8, 31)})
                self.assertEqual({r[-1]["page"] for r in rows}, {1, 2})
                conflict = milk_pdf_page(
                    f"Cuadro 1. Precios de leche cruda en finca ({suffix})\n2014 (septiembre)"
                )
                with self.assertRaises(SourceDateMismatch):
                    parse_pdf_pages([first, conflict])

    def test_unknown_and_future_table_months_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown observation month"):
            parse_pdf_pages(
                [milk_pdf_page("Precios de leche cruda en finca\n2014 (unknown)")]
            )
        with (
            patch("pipelines.ingestion.worker.today", return_value=date(2014, 8, 31)),
            self.assertRaisesRegex(SourceDateMismatch, "future"),
        ):
            parse_pdf_pages(
                [milk_pdf_page("Precios de leche cruda en finca\n2014 (septiembre)")]
            )

    def test_verified_archive_month_still_supports_an_undated_continuation(self):
        rows = parse_pdf_pages(
            [milk_pdf_page("Cuadro 1. Precios de leche cruda en finca")],
            date(2014, 8, 31),
        )
        self.assertEqual(rows[0][2], date(2014, 8, 31))

    def test_original_august_2014_native_table_preserves_all_prices_and_provenance(
        self,
    ):
        path = Path("artifacts/official-sources/milk-2014-aug-bulletin.pdf")
        if not path.exists():
            self.skipTest("Retained August 2014 milk PDF fixture not downloaded")
        data = path.read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "15ecb00afe7d5d9b3209ce8116ac37196afcbb00a553865a5c2926adc082ce84",
        )
        rows = list(parse_milk_pdf(data, None))
        self.assertEqual(rows, list(parse_milk_pdf(data, date(2014, 8, 31))))
        self.assertEqual(len(rows), 183)
        self.assertEqual(len({r[0] for r in rows}), 183)
        self.assertEqual(len({(r[-1]["department"], r[4]) for r in rows}), 183)
        self.assertEqual(len({r[-1]["department"] for r in rows}), 22)
        self.assertEqual({r[-1]["page"] for r in rows}, {3, 4})
        self.assertEqual({r[2] for r in rows}, {date(2014, 8, 31)})
        self.assertEqual({r[5] for r in rows}, {"litre"})
        sample = {(r[-1]["department"], r[4]): r for r in rows}
        self.assertEqual(sample["Antioquia", "Angostura"][6], 884)
        self.assertEqual(sample["Cundinamarca", "Villa de San Diego de Ubaté"][6], 946)
        self.assertEqual(sample["Quindío", "Circasia"][6], 1052)
        self.assertEqual(sample["Valle del Cauca", "Zarzal"][6], 815)
        self.assertTrue(
            all(0 < r[-1]["min_price"] <= r[6] <= r[-1]["max_price"] for r in rows)
        )

    def test_other_retained_native_pdf_dates_match_the_verified_archive_months(self):
        for name, day in (
            ("mensual_leche_dic_2012.pdf", date(2012, 12, 31)),
            ("BolSipsaLeche_dic_2020.pdf", date(2020, 12, 31)),
        ):
            with self.subTest(source=name):
                path = Path("pipelines/ingestion/cache") / name
                if not path.exists():
                    self.skipTest("Retained milk PDF fixture not downloaded")
                data = path.read_bytes()
                inferred = list(parse_milk_pdf(data, None))
                self.assertEqual(inferred, list(parse_milk_pdf(data, day)))
                self.assertTrue(inferred)
                self.assertEqual({r[2] for r in inferred}, {day})


class MilkNarrativeClassification(unittest.TestCase):
    def narrative_page(self, extra="", *, image=False):
        text = (
            "Boletín técnico\nPrecios de Leche Cruda en Finca (SIPSA-L)\nJulio de 2026\n"
            "Contenido\nIntroducción\nFicha metodológica\n"
            "Comportamiento de los precios promedio y condiciones de producción.\n"
            + extra
        )
        return SimpleNamespace(
            width=600,
            height=800,
            images=[{"x0": 0, "x1": 600, "top": 200, "bottom": 700}] if image else [],
            extract_text=lambda: text,
            close=lambda: None,
        )

    def test_explicit_native_narrative_has_a_distinct_non_price_outcome(self):
        from .special_prices import MilkNarrativeOnly

        with self.assertRaises(MilkNarrativeOnly):
            parse_pdf_pages(
                [self.narrative_page("Gráfico 1. Tendencia de precios", image=True)],
                date(2026, 7, 31),
            )
        with self.assertRaises(SourceDateMismatch):
            parse_pdf_pages([self.narrative_page()], date(2026, 8, 31))

    def test_announced_table_or_unlabelled_image_stays_a_parser_failure(self):
        from .special_prices import MilkNarrativeOnly

        for page in (
            self.narrative_page("Cuadro 1. Precios de leche cruda en finca"),
            self.narrative_page(image=True),
            SimpleNamespace(
                width=600,
                height=800,
                images=[],
                extract_text=lambda: "",
                close=lambda: None,
            ),
        ):
            with self.subTest(page=page):
                with self.assertRaises(ValueError) as error:
                    parse_pdf_pages([page], date(2026, 7, 31))
                self.assertNotIsInstance(error.exception, MilkNarrativeOnly)

    def test_current_july_2026_original_is_readable_narrative(self):
        from .special_prices import MilkNarrativeOnly

        path = Path(
            "artifacts/automation-audit-2026-09-26/dane/originals/bol-SIPSALeche-jul2026.pdf"
        )
        if not path.exists():
            self.skipTest("Current DANE original not downloaded")
        data = path.read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "83679d9a32073fe406bf45e1b56d01ca427ffda81a711819ea8c4cd459e0c912",
        )
        with self.assertRaises(MilkNarrativeOnly):
            list(parse_milk_pdf(data, date(2026, 7, 31)))

    def test_worker_records_only_explicit_narrative_as_processed(self):
        from .special_prices import MilkNarrativeOnly
        from .worker import _process_asset

        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            ("old-parser",),
            ("old-document", "failed", 0),
        ]
        with (
            patch(
                "pipelines.ingestion.worker.fetch_asset", return_value=b"native report"
            ),
            patch(
                "pipelines.ingestion.worker.archive", return_value="retained-original"
            ),
            patch("pipelines.ingestion.pdf_sources.extract_pages"),
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                side_effect=MilkNarrativeOnly("native narrative"),
            ),
            patch("pipelines.ingestion.worker.save_rows") as save,
        ):
            self.assertEqual(
                _process_asset(
                    db,
                    "https://www.dane.gov.co/report.pdf",
                    "milk-pdf",
                    date(2026, 7, 31),
                ),
                0,
            )
        save.assert_not_called()
        self.assertTrue(
            any(
                "status='processed'" in call.args[0]
                for call in db.execute.call_args_list
            )
        )
        self.assertTrue(
            any(
                "Native narrative; no municipal price table" in str(call.args)
                for call in db.execute.call_args_list
            )
        )
        self.assertFalse(
            any(
                "UPDATE source_document" in call.args[0]
                for call in db.execute.call_args_list
            )
        )

    def test_worker_does_not_swallow_other_missing_table_failures(self):
        from .worker import _process_asset

        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            ("old-parser",),
            ("old-document", "failed", 0),
        ]
        with (
            patch(
                "pipelines.ingestion.worker.fetch_asset", return_value=b"unknown report"
            ),
            patch(
                "pipelines.ingestion.worker.archive", return_value="retained-original"
            ),
            patch("pipelines.ingestion.pdf_sources.extract_pages"),
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                side_effect=ValueError("Unknown grid"),
            ),
            self.assertRaisesRegex(ValueError, "Unknown grid"),
        ):
            _process_asset(
                db, "https://www.dane.gov.co/report.pdf", "milk-pdf", date(2026, 7, 31)
            )
        self.assertFalse(
            any(
                "status='processed'" in call.args[0]
                for call in db.execute.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
