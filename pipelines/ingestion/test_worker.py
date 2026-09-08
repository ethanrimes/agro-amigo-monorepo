"""Parser and transaction regressions for unattended ingestion (no network required)."""

import unittest
from datetime import date, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import openpyxl

from pipelines.ingestion.city_reports import parse_city_pdf
from pipelines.ingestion.special_prices import parse_special
from pipelines.ingestion.supply import parse_supply
from pipelines.ingestion.worker import (
    date_from_text,
    discover_daily,
    fetch_asset,
    parse_coffee,
    parse_daily,
    parse_inputs,
    parse_monthly,
    record,
)


def workbook(rows, title="2026"):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    data = BytesIO()
    book.save(data)
    return data.getvalue()


class Parsers(unittest.TestCase):
    def test_milk_annex_rejects_mislabeled_month(self):
        data = workbook(
            [
                ["Precio de Leche Cruda en Finca Junio de 2026"],
                ["Nombre departamento", "Nombre municipio", "Pesos por litro", "", ""],
                ["", "", "Precio mínimo", "Precio máximo", "Precio medio"],
                ["Antioquia", "Abejorral", 1900, 2185, 2098],
            ]
        )
        self.assertEqual(
            list(parse_special(data, "milk", date(2026, 6, 30)))[0][2],
            date(2026, 6, 30),
        )
        with self.assertRaisesRegex(ValueError, "month differs"):
            list(parse_special(data, "milk", date(2026, 5, 31)))

    def test_dates_and_historical_formats(self):
        for text, want in [
            ("anex-SIPSADiario-07sep2026.xlsx", date(2026, 9, 7)),
            ("mayoristas_junio_12_2012.xls", date(2012, 6, 12)),
            ("12 de junio de 2012", date(2012, 6, 12)),
        ]:
            self.assertEqual(date_from_text(text), want)

    def test_old_monthly_headers_and_unit_preservation(self):
        rows = list(
            parse_monthly(
                workbook(
                    [
                        ["Old header"],
                        ["Fecha", "Grupo", "Producto", "Fuente", "Precio "],
                        [datetime(2013, 1, 1), "Huevos", "Huevo rojo A", "Bogotá", 212],
                        [datetime(2013, 1, 1), "Frutas", "Mango", "Cali", 1400],
                    ],
                    "1.1",
                )
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][2], date(2013, 1, 31))
        self.assertEqual(rows[0][5], "unit")
        self.assertEqual(rows[1][5], "kg")
        self.assertIn("row 3", rows[0][0])

    def test_short_daily_filenames_from_2022_2023(self):
        urls = [
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/" + name
            for name in [
                "bol_feb_28_2022.pdf",
                "anex_may_feb_09_2022.xlsx",
                "anex_abr_28_2023.xlsx",
            ]
        ]
        with (
            patch(
                "pipelines.ingestion.worker.links",
                return_value=[("Anexo", u) for u in urls],
            ),
            patch("pipelines.ingestion.worker.queue") as enqueue,
        ):
            self.assertEqual(discover_daily(None, "https://www.dane.gov.co/archive"), 3)
            self.assertEqual(
                [call.args[3] for call in enqueue.call_args_list],
                [date(2022, 2, 28), date(2022, 2, 9), date(2023, 4, 28)],
            )

    def test_schema_drift_fails(self):
        with self.assertRaisesRegex(ValueError, "Unknown monthly price column"):
            list(
                parse_monthly(
                    workbook(
                        [
                            ["Fecha", "Producto", "Mercado", "Unexpected price"],
                            [datetime(2020, 1, 1), "Papa", "Cali", 1000],
                        ]
                    )
                )
            )

    def test_daily_header_date_must_match_url(self):
        data = workbook(
            [
                ["Boletín diario"],
                ["12 de junio de 2012"],
                ["Precio $/Kg", "Bogotá", None, "Cali", None, "Medellín", None],
                [None, "Precio", "Var %", "Precio", "Var %", "Precio", "Var %"],
                ["Tomate*", 800, 0.1, 900, -0.2, "n.d.", "n.d."],
            ]
        )
        rows = list(parse_daily(data, date(2012, 6, 12)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][7], 10)
        self.assertTrue(rows[0][8]["predominant_variety"])
        with self.assertRaisesRegex(ValueError, "differs"):
            list(parse_daily(data, date(2012, 6, 13)))

    def test_daily_excel_dates_empty_sheets_and_auxiliary_columns(self):
        rows = [
            ["Boletín diario"],
            [datetime(2012, 10, 10)],
            ["Precio $/Kg", "Bogotá", None, "Cali", None, "Medellín", None, None, None],
            [None, "Precio", "Var %", "Precio", "Var %", "Precio", "Var %", None, None],
            ["Tomate", 800, 0.1, 900, -0.2, 1000, 0, 9999, None],
        ]
        with patch(
            "pipelines.ingestion.worker.workbooks",
            return_value=[("Boletín", iter(rows)), ("Hoja1", iter([]))],
        ):
            parsed = list(parse_daily(b"", date(2012, 10, 10)))
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[-1][6], 1000)

    def test_multiline_daily_city_and_market_headers(self):
        data = workbook(
            [
                ["Boletín diario"],
                ["31 de diciembre de 2012"],
                ["Precio $/Kg", "Armenia", None, "Bogotá", None, "Cali", None],
                [None, None, None, "Corabastos"],
                [None, "Precio", "Var%", "Precio", "Var%", "Precio", "Var%"],
                ["Ahuyama", 600, 0, 983, 0.06, 756, -0.01],
            ]
        )
        parsed = list(parse_daily(data, date(2012, 12, 31)))
        self.assertEqual(parsed[1][4], "Bogotá, Corabastos")
        self.assertEqual(parsed[1][6], 983)

    def test_nonfinite_and_future_data(self):
        data = workbook(
            [
                ["Fecha", "Producto", "Mercado", "Precio"],
                [datetime(2020, 1, 1), "Papa", "Cali", 0],
                [datetime(2099, 1, 1), "Papa", "Cali", 1000],
            ]
        )
        with self.assertRaisesRegex(ValueError, "No monthly"):
            list(parse_monthly(data))
        with self.assertRaisesRegex(ValueError, "Future"):
            record("test", date(2099, 1, 1), "Papa", "Cali", "kg", 1000, "row 1")

    def test_fnc_keeps_pre_2012_history(self):
        rows = list(
            parse_coffee(
                workbook(
                    [[None, datetime(2003, 1, 2), 277000]], "1. Precio Interno Diario "
                )
            )
        )
        self.assertEqual(rows[0][2], date(2003, 1, 2))
        self.assertEqual(rows[0][5], "125kg")

    def test_input_presentations_do_not_become_kilograms(self):
        data = workbook(
            [
                [
                    "Año",
                    "Mes",
                    "Artículo",
                    "Presentación del producto",
                    "Nombre departamento",
                    "Precio promedio departamento",
                ],
                [2018, "Enero", "Fertilizante", "50 kg", "Huila", 70000],
            ],
            "1.3",
        )
        rows = list(parse_inputs(data))
        self.assertEqual(rows[0][5], "50 kg")
        self.assertEqual(rows[0][6], 70000)

    def test_all_input_header_families_and_old_sheet_numbers(self):
        for title, column, name in [
            ("3.1. Arrendamiento de tierras", "Tipo de arriendo", "Pastoreo mensual"),
            ("3.2. Distritos de riego", "Distrito de riego", "Alto del Tablón"),
            ("3.6. Especies productivas", "Especie productiva", "Bovino Cebú"),
            ("3.7. Jornales", "Tipo de jornal", "Cosecha por kg"),
            ("3.9. Servicios agrícolas", "Nombre del servicio", "Arada"),
        ]:
            data = workbook(
                [
                    [title],
                    [
                        "Año",
                        "Mes",
                        "Nombre departamento",
                        "Nombre municipio",
                        column,
                        "Presentación",
                        "Precio promedio",
                    ],
                    ["2013", "Enero", "Huila", "La Plata", name, "unidad", 100],
                ],
                title[:3],
            )
            row = list(parse_inputs(data))[0]
            self.assertEqual(row[3], name)
            self.assertEqual(row[4], "La Plata")
            self.assertEqual(row[8]["category"], title[5:])

    def test_annex_month_columns_keep_distinct_dates_and_skip_footers(self):
        data = workbook(
            [
                ["1.1. Bioinsumos"],
                [
                    "Nombre departamento",
                    "Nombre municipio",
                    "Nombre del producto",
                    "Presentación del producto",
                    "Precio promedio de junio de 2026",
                    "Precio promedio de julio de 2026",
                ],
                ["Huila", "Pitalito", "Alisin", "1 litro", 100, 120],
                ["Fuente: DANE"],
                [],
            ],
            "1.1",
        )
        rows = list(parse_inputs(data))
        self.assertEqual([r[2] for r in rows], [date(2026, 6, 30), date(2026, 7, 31)])
        self.assertEqual([r[6] for r in rows], [100, 120])
        self.assertEqual(len({r[0] for r in rows}), 2)

    def test_milk_split_headers_numeric_months_and_raw_unit(self):
        data = workbook(
            [
                [
                    "Año",
                    "Mes",
                    "Nombre departamento",
                    None,
                    "Precio promedio por litro",
                ],
                [None, None, None, "Nombre municipio"],
                [2013, "01", "Antioquia", "Angostura", 882.86],
            ]
        )
        r = list(parse_special(data, "milk"))[0]
        self.assertEqual(r[4], "Angostura")
        self.assertEqual(r[5], "litre")
        self.assertEqual(r[2], date(2013, 1, 31))

    def test_mill_missing_location_is_retained_and_marked(self):
        data = workbook(
            [
                [
                    "Fecha",
                    "Producto",
                    "Municipio",
                    "Departamento",
                    "Precio por tonelada",
                ],
                [datetime(2025, 8, 1), "Arroz blanco empacado", "", "", 3643200],
            ]
        )
        r = list(parse_special(data, "rice"))[0]
        self.assertEqual(r[5], "tonne")
        self.assertEqual(r[6], 3643200)
        self.assertIsNotNone(r[8]["quality_issue"])

    def test_http_304_does_not_redownload(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            '"old"',
            "date",
            "complete",
            "a" * 64,
        )
        response = MagicMock(status_code=304)
        with patch(
            "pipelines.ingestion.worker.SESSION.get", return_value=response
        ) as get:
            self.assertIsNone(fetch_asset(db, "https://example.org/data.xlsx"))
            self.assertEqual(
                get.call_args.kwargs["headers"], {"If-None-Match": '"old"'}
            )

    def test_changed_same_url_and_failed_assets_are_read_again(self):
        for status in ["complete", "failed"]:
            db = MagicMock()
            db.execute.return_value.fetchone.return_value = (
                '"old"',
                "date",
                status,
                "a" * 64,
            )
            response = MagicMock(status_code=200, content=b"updated")
            response.headers = {"ETag": '"new"'}
            with patch(
                "pipelines.ingestion.worker.SESSION.get", return_value=response
            ) as get:
                self.assertEqual(
                    fetch_asset(db, "https://example.org/data.xlsx"), b"updated"
                )
                if status == "failed":
                    self.assertEqual(get.call_args.kwargs["headers"], {})

    def test_city_rounds_packages_and_internal_date(self):
        page = MagicMock()
        page.extract_text.return_value = "PRECIOS DE VENTA MAYORISTA\nBarranquilla, Barranquillita\nPRODUCTOS PRIMERA CALIDAD\n07 de Septiembre de 2026"
        page.extract_tables.return_value = [
            [
                [
                    "Producto",
                    "Presentación",
                    "Unidades",
                    "Ronda 1",
                    None,
                    "Ronda 2",
                    None,
                ],
                [None, None, None, "Mínimo", "Máximo", "Mínimo", "Máximo"],
                ["Frutas", None, None, None, None, None, None],
                [
                    "Mora de castilla",
                    "Caja",
                    "2.5 Kilogramo",
                    "20.000",
                    "22.000",
                    "0",
                    "0",
                ],
                [
                    "Mora de castilla",
                    "Caja",
                    "12.5 Kilogramo",
                    "79.000",
                    "80.000",
                    "0",
                    "0",
                ],
                ["Arándano", "Caja", "125 Gramo", "6.000", "6.500", "6.000", "7.000"],
            ]
        ]
        pdf = MagicMock()
        pdf.__enter__.return_value.pages = [page]
        with patch(
            "pipelines.ingestion.city_reports.pdfplumber.open", return_value=pdf
        ):
            rows = list(parse_city_pdf(b"", date(2026, 9, 7)))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0][14], 8000)
            self.assertEqual(rows[1][14], 6320)
            self.assertEqual(rows[2][14], 48000)
            with self.assertRaisesRegex(ValueError, "internal date"):
                list(parse_city_pdf(b"", date(2026, 9, 6)))

    def test_zip_links_are_discovered_even_without_national_bulletin(self):
        url = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-05sep2026.zip"
        with (
            patch(
                "pipelines.ingestion.worker.links",
                return_value=[("Informes por ciudades", url)],
            ),
            patch("pipelines.ingestion.worker.queue") as enqueue,
        ):
            self.assertEqual(discover_daily(None, "https://www.dane.gov.co/archive"), 1)
            self.assertEqual(
                enqueue.call_args.args[2:4], ("city-zip", date(2026, 9, 5))
            )

    def test_supply_2013_header_spelling_and_column_positions(self):
        data = workbook(
            [
                [],
                ["Cuidad, Mercado Mayorista", "Fecha", "Grupo", "Alimento", "Cant Kg"],
                [
                    "Bogotá, Corabastos",
                    datetime(2013, 1, 1),
                    "Verduras",
                    "Ahuyama",
                    600,
                ],
                [
                    "Bogotá, Corabastos",
                    datetime(2013, 1, 2),
                    "Verduras",
                    "Ahuyama",
                    400,
                ],
            ],
            "1.1",
        )
        group = parse_supply(data)[("Bogotá, Corabastos", "Ahuyama", date(2013, 1, 1))]
        self.assertEqual(group["kg"], 1000)
        self.assertEqual(len(group["days"]), 2)
        self.assertEqual(group["rows"]["1.1"], [[3, 4]])


if __name__ == "__main__":
    unittest.main()
