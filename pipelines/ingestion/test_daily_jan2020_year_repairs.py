"""Exact Jan 7/8/9/10/13/14/15/16 2020 DANE native-year typo tests."""
import hashlib
import io
import re
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import openpyxl
from bs4 import BeautifulSoup
import pdfplumber
from pipelines.ingestion import worker, daily_recovery as daily
from pipelines.ingestion.queue_plan import PRIORITY_SOURCE_REPAIRS, expected_versions
from pipelines.ingestion.retained_date_repairs import REPAIRS

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "testdata" / "jan2020_daily_year_repairs"
ARCHIVE = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-enero-de-2020"
ARCHIVE_HTML_SHA = "80014d7da64b3bb6a843cc37c260f056c44ce0cc58b4c7a2a012954ec6462016"
CASES = (
    {
        "day": date(2020, 1, 7),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.xlsx",
        "xls": "mayoristas_enero_07_2020.xlsx",
        "xls_sha": "73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72",
        "pdf": "mayoristas_enero_07_2020.pdf",
        "pdf_sha": "2bba2c3ed056b5d2624af824c2d845aadbb16cadb31ab29e3ca26475061abaec",
        "heading": "Martes 7 de enero de 2019",
        "witnesses": [
            ("D10","E10","Chócolo mazorca","Bogotá, Corabastos",1050,-40.0,1,"40,00%"),
            ("L17","M17","Tomate*","Ibagué, La 21",770,-23.0,1,"23,00%"),
            ("F12","G12","Habichuela","Bucaramanga, Centroabastos",2500,42.86,1,"42,86%"),
            ("V12","W12","Habichuela","Pereira, La 41",1547,20.83,1,"20,83%"),
            ("H29","I29","Mango tommy","Cali, Santa Helena",1427,33.75,2,"33,75%"),
            ("T29","U29","Mango tommy","Neiva, Surabastos",1300,22.64,2,"22,64%"),
            ("V29","W29","Mango tommy","Pereira, La 41",1767,17.78,2,"17,78%"),
            ("N33","O33","Naranja*","Manizales",967,16.0,2,"16,00%"),
            ("V26","W26","Limón Tahití","Pereira, La 41",2167,41.3,2,"41,30%"),
            ("F39","G39","Papa criolla","Bucaramanga, Centroabastos",950,-40.63,3,"40,63%"),
        ],
        "excluded": ("T14","U14",1120,-25.33,1,"25,53%"),
    },
    {
        "day": date(2020, 1, 8),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_08_2020.xlsx",
        "xls": "mayoristas_enero_08_2020.xlsx",
        "xls_sha": "74f03719c5227c25c219b4b7475740b0382e61b911d025aeb5f13d71abaa81a1",
        "pdf": "mayoristas_enero_08_2020.pdf",
        "pdf_sha": "c053303f5068d234c5c9b9b3048621b305ebe4861f046055be03db8a5a8e024e",
        "heading": "Miércoles 8 de enero de 2019",
        "witnesses": [
            ("F14","G14","Pepino cohombro","Cartagena, Bazurto",840,-31.15,1,"31,15%"),
            ("N14","O14","Pepino cohombro","Popayán",615,-20.0,1,"20,00%"),
            ("R14","S14","Pepino cohombro","Sincelejo",500,-23.08,1,"23,08%"),
            ("H18","I18","Zanahoria","Medellín, CMA",569,-14.58,1,"14,58%"),
            ("T18","U18","Zanahoria","Valledupar",1375,-12.0,1,"12,00%"),
            ("D9","E9","Cebolla junca","Bogotá, Corabastos",1250,-16.67,1,"16,67%"),
            ("H32","I32","Mora de Castilla","Medellín, CMA",3050,71.83,2,"71,83%"),
            ("J32","K32","Mora de Castilla","Montería",2875,32.69,2,"32,69%"),
            ("L25","M25","Limón común","Pereira, Mercasa",2133,28.0,2,"28,00%"),
            ("V25","W25","Limón común","Villavicencio, CAV",3250,23.81,2,"23,81%"),
            ("J33","K33","Naranja*","Montería",1000,57.48,2,"57,48%"),
            ("L33","M33","Naranja*","Pereira, Mercasa",1100,50.0,2,"50,00%"),
        ],
    },

    {
        "day": date(2020, 1, 9),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_09_2020.xlsx",
        "xls": "mayoristas_enero_09_2020.xlsx", "xls_sha": "fe7ca4b678001889d58d945d2098a88877e53e35c77c74bbda0af6ea2123b7a3",
        "pdf": "mayoristas_enero_09_2020.pdf", "pdf_sha": "36c9b840561fb2e717a3b3164728a918a3c9449a607f02f450acee412e191aa0",
        "heading": "Jueves 09 de enero de 2019", "dimensions": (46,37),
        "witnesses": [
            ("B7","C7","Arveja verde en vaina","Armenia, Mercar",2347,-15.38,1,"15,38%"),
            ("J7","K7","Arveja verde en vaina","Cúcuta, Cenabastos",2500,-35.48,1,"35,48%"),
            ("D9","E9","Cebolla junca","Bogotá, Corabastos",1083,-13.33,1,"13,33%"),
        ],
    },
    {
        "day": date(2020, 1, 10),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_10_2020.xlsx",
        "xls": "mayoristas_enero_10_2020.xlsx", "xls_sha": "4632f2426dda197ff7115c7801e28bfbf8eebcf012b6343e656ac1bfdff1e538",
        "pdf": "mayoristas_enero_10_2020.pdf", "pdf_sha": "f3f6f2acb3033464a12d4c86a8f8e826be5ca5f4a9646f3b61c330ce24b06b2f",
        "heading": "Viernes 10 de enero de 2019", "dimensions": (46,43),
        "witnesses": [
            ("R7","S7","Arveja verde en vaina","Neiva, Surabastos",2000,-23.08,1,"23,08%"),
            ("R14","S14","Pepino cohombro","Neiva, Surabastos",760,-33.33,1,"33,33%"),
            ("P16","Q16","Remolacha","Montería",1000,-13.04,1,"13,04%"),
        ],
    },
    {
        "day": date(2020, 1, 13),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_13_2020.xlsx",
        "xls": "mayoristas_enero_13_2020.xlsx", "xls_sha": "eca65a7f770f62021b338f94aae46d96f6421ee5d2337f1db93de013a8c06d2b",
        "pdf": "mayoristas_enero_13_2020.pdf", "pdf_sha": "1f4a8e9af7aafd51508eae906853a4c1d3d13061d5df7dbaf5f2af63ed6e5669",
        "heading": "Lunes 13 de enero de 2019", "dimensions": (46,39),
        "witnesses": [
            ("L12","M12","Habichuela","Manizales",3200,135.29,1,"135,29%"),
            ("B12","C12","Habichuela","Armenia, Mercar",2027,40.74,1,"40,74%"),
            ("Z12","AA12","Habichuela","Valledupar",2625,16.67,1,"16,67%"),
            ("L17","M17","Tomate*","Manizales",2250,50.0,1,"50,00%"),
            ("Z17","AA17","Tomate*","Valledupar",1300,44.44,1,"44,44%"),
        ],
    },
    {
        "day": date(2020, 1, 14),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_14_2020.xlsx",
        "xls": "mayoristas_enero_14_2020.xlsx",
        "xls_sha": "872320bb98111d27365140203675f28bfbaf8856d437d977aee87de53ddfd5fb",
        "pdf": "mayoristas_enero_14_2020.pdf",
        "pdf_sha": "15bfd0fd1c6baebb34776f2841f7b95b98292f6b2fb2499ddcffe3e1e3539bc5",
        "heading": "Martes 14 de enero de 2019",
        "dimensions": (46, 33),
        "witnesses": [
            ("L12", "M12", "Habichuela", "Ibagué, La 21", 2340, 82.81, 1, "82,81%"),
            ("J12", "K12", "Habichuela", "Cúcuta, Cenabastos", 3469, 85, 1, "85,00%"),
            ("R12", "S12", "Habichuela", "Pereira, La 41", 2260, 66.18, 1, "66,18%"),
            ("R17", "S17", "Tomate*", "Pereira, La 41", 2333, 55.56, 1, "55,56%"),
            ("F17", "G17", "Tomate*", "Bucaramanga, Centroabastos", 1909, 47.37, 1, "47,37%"),
            ("H9", "I9", "Cebolla junca", "Cali, Santa Helena", 1600, 17.39, 1, "17,39%"),
            ("P13", "Q13", "Lechuga batavia", "Neiva, Surabastos", 1440, -18.18, 1, "18,18%"),
        ],
    },
    {
        "day": date(2020, 1, 15),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_15_2020.xlsx",
        "xls": "mayoristas_enero_15_2020.xlsx",
        "xls_sha": "d0eea326eb44186c3ac0be8796da460897d9b78cee3f5f885784cc42d2353219",
        "pdf": "mayoristas_enero_15_2020.pdf",
        "pdf_sha": "6e9bbe3a02eb5fb27ae9692df8bb9d94bc6499e04f889a48219a624519ab08c9",
        "heading": "Miércoles 15 de enero de 2019",
        "dimensions": (46, 33),
        "witnesses": [
            ("N12", "O12", "Habichuela", "Popayán", 2760, 40.82, 1, "40,82%"),
            ("D12", "E12", "Habichuela", "Bogotá, Corabastos", 2333, 12, 1, "12,00%"),
            ("J18", "K18", "Zanahoria", "Montería", 1206, 23.3, 1, "23,30%"),
            ("J8", "K8", "Cebolla cabezona blanca", "Montería", 990, 15.79, 1, "15,79%"),
            ("V17", "W17", "Tomate*", "Villavicencio, CAV", 2288, 12.62, 1, "12,62%"),
            ("V14", "W14", "Pepino cohombro", "Villavicencio, CAV", 1075, 22.86, 1, "22,86%"),
            ("J14", "K14", "Pepino cohombro", "Montería", 768, 10.83, 1, "10,83%"),
            ("D15", "E15", "Pimentón", "Bogotá, Corabastos", 2100, -12.5, 1, "12,50%"),
            ("V15", "W15", "Pimentón", "Villavicencio, CAV", 1875, -16.28, 1, "16,28%"),
        ],
    },
    {
        "day": date(2020, 1, 16),
        "url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_16_2020.xlsx",
        "xls": "mayoristas_enero_16_2020.xlsx",
        "xls_sha": "83885449eb25388a124efeed3fa7e642ce487cbd68a11051e6daba3ee460f787",
        "pdf": "mayoristas_enero_16_2020.pdf",
        "pdf_sha": "ca08164318e52ef85ad9cca27010e27f8d6ac2e004f12c91f44d3d45b2b26270",
        "heading": "Jueves 16 de enero de 2019",
        "dimensions": (46, 37),
        # The publisher prints this Santa Marta value as "$1000" (no thousands
        # separator); preserve that literal instead of normalizing it to "$1.000".
        "pdf_price_literals": {"X16": "1000"},
        "witnesses": [
            ("H16", "I16", "Remolacha", "Cali, Cavasa", 691, 13.71, 1, "13,71%"),
            ("X16", "Y16", "Remolacha", "Santa Marta", 1000, 27.66, 1, "27,66%"),
            ("F16", "G16", "Remolacha", "Bucaramanga, Centroabastos", 850, 13.33, 1, "13,33%"),
            ("X14", "Y14", "Pepino cohombro", "Santa Marta", 1200, 33.33, 1, "33,33%"),
            ("J14", "K14", "Pepino cohombro", "Cúcuta, Cenabastos", 700, 12, 1, "12,00%"),
            ("H7", "I7", "Arveja verde en vaina", "Cali, Cavasa", 2683, 30.89, 1, "30,89%"),
            ("L15", "M15", "Pimentón", "Manizales", 1350, -36.47, 1, "36,47%"),
        ],
    },
)

def normalize(value):
    return " ".join(str(value or "").split())


def native_matrix(body):
    book = openpyxl.load_workbook(io.BytesIO(body), data_only=True, read_only=True)
    try:
        sheet = book["Boletín diario"]
        rows = list(sheet.iter_rows(values_only=True))
        cols = [i for i, val in enumerate(rows[3]) if normalize(val).lower() == "precio"]
        expected = {}
        for row_index, row in enumerate(rows[4:], 5):
            for col in cols:
                price = row[col] if col < len(row) else None
                if isinstance(price, (int, float)) and price > 0:
                    variation = row[col + 1] if col + 1 < len(row) else None
                    expected[f"Boletín diario!row {row_index},col {col + 1}"] = (
                        normalize(row[0]), normalize(rows[2][col]), price,
                        variation if isinstance(variation, (int, float)) else None,
                        variation,
                    )
        return sheet.max_row, sheet.max_column, sheet["A2"].value, expected
    finally:
        book.close()


class Jan2020DateRecovery(unittest.TestCase):
    def test_exact_archive_rows_pdf_dates_and_cell_witnesses(self):
        archive_body = (SOURCE / "official-archive-page.html").read_bytes()
        self.assertEqual(hashlib.sha256(archive_body).hexdigest(), ARCHIVE_HTML_SHA)
        html = archive_body.decode("utf-8")
        archive_links = {urljoin("https://www.dane.gov.co", node.get("href", "")) for node in BeautifulSoup(html, "html.parser").select("a[href]")}
        for case in CASES:
            day_text = f"{case['day'].day:02d} de enero de 2020"
            self.assertIn(day_text, " ".join(html.split()))
            self.assertIn(case["url"], archive_links)
            body = (SOURCE / case["xls"]).read_bytes()
            pdf_body = (SOURCE / case["pdf"]).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), case["xls_sha"])
            self.assertEqual(hashlib.sha256(pdf_body).hexdigest(), case["pdf_sha"])
            with pdfplumber.open(io.BytesIO(pdf_body)) as pdf:
                self.assertGreaterEqual(len(pdf.pages), 3)
                title = normalize(pdf.pages[0].extract_text() or "")
                self.assertIn(f"{case['day'].day} de enero de 2020", title)
                self.assertIn("28 de agosto de 2018", title)  # hidden stationery text; visual render is root-reviewed
                for price_cell, variation_cell, product, market, price, variation, page, pct in case["witnesses"]:
                    text = normalize(pdf.pages[page - 1].extract_text() or "")
                    self.assertIn(pct, text, (case["day"], page, product, market))
                    formatted = case.get("pdf_price_literals", {}).get(
                        price_cell, format(price, ",").replace(",", ".")
                    )
                    self.assertIn(formatted, text, (case["day"], page, product, market))
                    self.assertIn(product.replace("*","").strip().split()[0].lower(), text.lower(), (case["day"], page, product, market))
                if "excluded" in case:
                    pc, vc, price, variation, page, pdf_pct = case["excluded"]
                    text = normalize(pdf.pages[page-1].extract_text() or "")
                    self.assertIn(pdf_pct, text)
                    self.assertNotEqual(variation, -25.53)
            book = openpyxl.load_workbook(io.BytesIO(body), data_only=True, read_only=True)
            try:
                ws = book["Boletín diario"]
                self.assertEqual(ws["A2"].value, case["heading"])
                for price_cell, variation_cell, product, market, price, variation, _, _ in case["witnesses"]:
                    row = ws[price_cell].row
                    self.assertEqual(normalize(ws[f"A{row}"].value), product)
                    self.assertEqual(float(ws[price_cell].value), price)
                    self.assertAlmostEqual(float(ws[variation_cell].value), variation, places=2)
                if "excluded" in case:
                    pc, vc, price, variation, _, _ = case["excluded"]
                    self.assertEqual(ws[pc].value, price)
                    self.assertEqual(ws[vc].value, variation)
            finally:
                book.close()

    def test_maintained_parser_preserves_every_numeric_price_and_variation(self):
        for case in CASES:
            with self.subTest(day=case["day"]):
                body = (SOURCE / case["xls"]).read_bytes()
                rows, cols, heading, expected = native_matrix(body)
                self.assertEqual((rows, cols), case.get("dimensions", (46, 37) if case["day"].day == 7 else (46, 33)))
                self.assertEqual(heading, case["heading"])
                result = daily.parse_daily(body, case["day"], source_url=case["url"])
                actual = {}
                for row in result["rows"]:
                    locator = row[0]
                    m = re.fullmatch(r"Boletín diario!row (\d+),col (\d+)", locator)
                    self.assertIsNotNone(m, locator)
                    actual[locator] = (normalize(row[3]), normalize(row[4]), row[6], row[7], row[-1].get("raw_change"))
                    self.assertEqual(row[2], case["day"])
                    self.assertEqual(row[-1]["date_resolution"], daily.VERIFIED_DATE_RECOVERIES[case["xls_sha"]])
                self.assertEqual(len(actual), len(expected))
                self.assertEqual(actual, expected)
                self.assertEqual(result["reviews"], [])
                self.assertEqual(result["date_resolutions"], [daily.VERIFIED_DATE_RECOVERIES[case["xls_sha"]]])

    def test_exact_hash_heading_day_and_source_url_are_all_required(self):
        for case in CASES:
            body = (SOURCE / case["xls"]).read_bytes()
            good = daily.parse_daily(body, case["day"], source_url=case["url"])
            self.assertTrue(good["rows"])
            other = CASES[1 if case["day"].day == 7 else 0]["url"]
            for wrong_url in (case["url"] + "?alias=1", other):
                with self.assertRaisesRegex(worker.SourceDateMismatch, "source URL"):
                    daily.parse_daily(body, case["day"], source_url=wrong_url)
            with self.assertRaises((ValueError, worker.SourceDateMismatch)):
                daily.parse_daily(body + b"changed", case["day"], source_url=case["url"])
            with self.assertRaises(worker.SourceDateMismatch):
                daily.parse_daily(body, date(2020, 1, case["day"].day + 1), source_url=case["url"])
            book = openpyxl.load_workbook(io.BytesIO(body), data_only=True, read_only=True)
            try:
                rows = [list(row) for row in book["Boletín diario"].iter_rows(max_row=4, values_only=True)]
            finally:
                book.close()
            rows[1][0] = rows[1][0].replace("enero", "febrero")
            with self.assertRaisesRegex(worker.SourceDateMismatch, "heading"):
                daily._publication_day(body, rows, case["day"], source_url=case["url"])


    def test_only_eight_exact_hash_bound_versions_receive_priority(self):
        expected = {case["url"]: case["xls_sha"] for case in CASES}
        priorities = {url: (kind, sha) for url, kind, sha in PRIORITY_SOURCE_REPAIRS}
        versions = expected_versions().obj
        for case in CASES:
            with self.subTest(url=case["url"]):
                self.assertEqual(priorities[case["url"]], ("daily", case["xls_sha"]))
                self.assertEqual(REPAIRS[case["url"]][1], case["xls_sha"])
                self.assertIn("url:" + case["url"], versions)
                self.assertEqual(versions["url:" + case["url"]], worker.asset_parser_version("daily", case["url"]))
                self.assertEqual(worker.asset_parser_version("daily", case["url"] + "?alias=1"),
                                 worker.parser_version("daily"))
                self.assertNotIn((case["url"], "daily", "0" * 64), PRIORITY_SOURCE_REPAIRS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
