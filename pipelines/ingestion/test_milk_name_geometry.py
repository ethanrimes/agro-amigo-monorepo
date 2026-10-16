"""Native milk table cell binding: wrapped names and displaced trend glyphs."""

import json
import re
import shutil
import subprocess
from collections import Counter
import unittest
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .special_prices import (
    MILK_PDF_VERSION,
    _milk_column_native_lines,
    _milk_department_heading,
    parse_milk_pdf,
)

FIXTURES = Path("artifacts/app-data-audit-2026-09-27/planning/milk-markets")


def word(text, x, y, height=7):
    return {
        "text": text,
        "x0": x,
        "x1": x + 8,
        "top": y,
        "bottom": y + height,
        "upright": True,
    }


def column(rows, extras=()):
    words = [
        word("Mínimo", 150, 10),
        word("Máximo", 200, 10),
        word("Promedio", 250, 10),
    ]
    for name, y, prices in rows:
        words.extend(
            word(n, 20 + index * 12, y) for index, n in enumerate(name.split())
        )
        words.extend(word(value, x, y) for x, value in zip((150, 200, 250), prices))
    words.extend(extras)
    return SimpleNamespace(height=800, extract_words=lambda: words)


class MilkNameGeometry(unittest.TestCase):
    FOLIO_PAGES = (
        ("milk_may_2018_page4.pdf", "d066cb5b1671cebb23ec1e5a61f6eff24f45c709a613a29f02ef383d423478fa", 64, "2018-05-31", ("Atlántico", "Sabanalarga", 800, 1100, 922)),
        ("milk_may_2018_page5.pdf", "c38a5208613441967760727c15442febee28050c72bda8c0dacbcc8e95dddd76", 71, "2018-05-31", ("Magdalena", "Pivijay", 850, 1000, 906)),
        ("milk_ago_2018_page4.pdf", "c3d70c3359de693ad8b6bf2a75d7ed663d5c915a8c22948a072d28ccae4ab2cf", 46, "2018-08-31", ("Arauca", "Arauquita", 650, 800, 707)),
        ("milk_ago_2018_page5.pdf", "c119cfabb0f84fbeda07a46ec87a85c8a6b20af75dde869e73e514ce33409402", 74, "2018-08-31", ("Cundinamarca", "Tabio", 860, 1065, 992)),
    )

    def test_2018_margin_folios_stay_outside_municipality_and_trend_cells(self):
        # Exact page extracts from four SHA-verified DANE originals retain
        # the outer folio glyphs and every native monetary cell on each page.
        for filename, digest, count, observed_on, oracle in self.FOLIO_PAGES:
            with self.subTest(filename=filename):
                body = (Path(__file__).parent / "testdata" / filename).read_bytes()
                self.assertEqual(sha256(body).hexdigest(), digest)
                rows = list(parse_milk_pdf(body, None))
                self.assertEqual(len(rows), count)
                self.assertEqual({str(row[2]) for row in rows}, {observed_on})
                self.assertTrue(all(row[5] == "litre" for row in rows))
                self.assertTrue(all(not re.search(r"\d", row[-1]["trend"]) for row in rows))
                department, town, low, high, mean = oracle
                matching = [row for row in rows if (row[-1]["department"], row[4]) == (department, town)]
                self.assertEqual(len(matching), 1)
                row = matching[0]
                self.assertEqual((row[-1]["min_price"], row[-1]["max_price"], row[6]), (low, high, mean))
                self.assertTrue(row[0].endswith("; parser " + MILK_PDF_VERSION))

    RECOVERED_ORIGINALS = (
        (
            "BolSipsaLeche_jun_2015.pdf",
            "6076815c704bdfef397fc19943c360652c01f27af96e9afa38f465e4379c24a5",
            186,
            "2015-06-30",
            ("Casanare", "Villanueva", "PDF page 3,col 2,line 16", 700, 900, 783),
        ),
        (
            "BolSipsaLeche_ago_2015.pdf",
            "003fa73ccacb673f0c473cc0ac4ab6aac7be11f0528a6db951dee369b4b025fc",
            186,
            "2015-08-31",
            ("Antioquia", "San Pedro de los Milagros", "PDF page 3,col 1,line 38", 890, 1020, 933),
        ),
        (
            "BolSipsaLeche_oct_2015.pdf",
            "c677d19b97d276bfe04f71a44c1c383718b3b40862298df5c3ae2bbcffe0c468",
            184,
            "2015-10-31",
            ("Boyacá", "Toca", "PDF page 3,col 2,line 23", 800, 1030, 959),
        ),
        (
            "BolSipsaLeche_mar_2016.pdf",
            "da809ab0c1c2f6dc48facc7cbb82fec908c1dbc7ecae9bebef58e3a228212cb8",
            193,
            "2016-03-31",
            ("Cundinamarca", "Madrid", "PDF page 4,col 1,line 12", 800, 910, 867),
        ),
    )

    def test_four_retained_milk_bulletins_keep_printed_towns_and_row_counts(self):
        for filename, digest, count, observed_on, oracle in self.RECOVERED_ORIGINALS:
            with self.subTest(filename=filename):
                body = (Path(__file__).parent / "testdata" / filename).read_bytes()
                self.assertEqual(sha256(body).hexdigest(), digest)
                rows = list(parse_milk_pdf(body, None))
                self.assertEqual(len(rows), count)
                self.assertEqual({str(row[2]) for row in rows}, {observed_on})
                department, town, physical, low, high, mean = oracle
                matched = [
                    row for row in rows
                    if row[-1]["department"] == department and row[4] == town
                ]
                self.assertEqual(len(matched), 1)
                row = matched[0]
                self.assertEqual(row[0], physical + "; parser " + MILK_PDF_VERSION)
                self.assertEqual((row[-1]["min_price"], row[-1]["max_price"], row[6]), (low, high, mean))
                self.assertFalse(any("continuaci" in row[4].lower() or "continauci" in row[4].lower() for row in rows))

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler pdftotext required")
    def test_four_originals_match_independent_poppler_monetary_cells(self):
        # Poppler's text layout is separate from pdfplumber's native words.
        num = r"(?:\d{1,3}(?:\.\d{3})+|\d{3,4})"
        triple = re.compile(r"(?<![\d.,])(" + num + r")\s+(" + num + r")\s+(" + num + r")(?![\d.,])")
        for filename, digest, count, _, _ in self.RECOVERED_ORIGINALS:
            with self.subTest(filename=filename):
                path = Path(__file__).parent / "testdata" / filename
                self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)
                text = subprocess.check_output(
                    ["pdftotext", "-f", "3", "-l", "4", "-layout", str(path), "-"],
                    text=True,
                )
                original = []
                for page in text.split("\f"):
                    if "Departamentos" not in page:
                        continue
                    grid = page[page.find("Departamentos"):].split("TENDENCIAS")[0]
                    original.extend(
                        tuple(float(cell.replace(".", "")) for cell in match)
                        for match in triple.findall(grid)
                    )
                parsed = list(parse_milk_pdf(path.read_bytes(), None))
                prices = [
                    (row[-1]["min_price"], row[-1]["max_price"], row[6])
                    for row in parsed
                ]
                self.assertEqual(len(original), count)
                self.assertEqual(Counter(prices), Counter(original))

    def test_typed_continuation_suffixes_require_an_exact_department(self):
        lookup = {"casanare": "Casanare", "boyaca": "Boyacá", "cundinamarca": "Cundinamarca"}
        for label, expected in (
            ("Casanare (continuacioón)", "Casanare"),
            ("Boyacá (continaución)", "Boyacá"),
            ("Cundinamarca (continaución)", "Cundinamarca"),
        ):
            with self.subTest(label=label):
                self.assertEqual(_milk_department_heading(label, lookup), expected)
        self.assertIsNone(_milk_department_heading("Casanare (continuacioón) Villanueva", lookup))

    def test_july_2015_printed_department_digits_do_not_become_yopal(self):
        # DANE's original prints "Casanare 1234" as an unpriced heading on
        # page 3, immediately above the Yopal 640 / 867 / 775 row.
        path = Path(__file__).resolve().parent / "testdata/BolSipsaLeche_jul_2015.pdf"
        data = path.read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "d06c9951f23900b0bfa59c23eb55b5edc7fa80118c5ef916fc94ccd108e561ab",
        )
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            column = pdf.pages[2].crop((306, 0, 612, 792))
            original = (column.extract_text() or "").splitlines()
            self.assertEqual(
                original[14:16], ["Casanare 1234", "Yopal 640 867 775 ="]
            )
            repaired = _milk_column_native_lines(column, original)
            self.assertEqual(repaired[14:16], original[14:16])

        rows = list(parse_milk_pdf(data, None))
        self.assertEqual(len(rows), 186)
        casanare = {
            row[4]: row for row in rows if row[-1]["department"] == "Casanare"
        }
        self.assertEqual(
            set(casanare), {"Aguazul", "Monterrey", "Tauramena", "Villanueva", "Yopal"}
        )
        yopal = casanare["Yopal"]
        self.assertEqual(str(yopal[2]), "2015-07-31")
        self.assertEqual(
            (yopal[-1]["min_price"], yopal[-1]["max_price"], yopal[6]),
            (640, 867, 775),
        )
        self.assertEqual(yopal[-1]["page"], 3)

    def test_department_digits_require_exact_known_heading(self):
        lookup = {"casanare": "Casanare"}
        self.assertEqual(_milk_department_heading("Casanare 1234", lookup), "Casanare")
        self.assertIsNone(_milk_department_heading("Casanare 640 867 775", lookup))
        self.assertIsNone(_milk_department_heading("Unknown 1234", lookup))

    def test_october_2012_unmapped_trend_glyph_keeps_literal_prices(self):
        path = Path(__file__).resolve().parent / "testdata/mensual_leche_oct_2012.pdf"
        data = path.read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "da0a7b07ad470e2ecf5f0839ce8fb873fecc1e2ecd4d2f8b77db4db36c0dbb9e",
        )
        from datetime import date

        rows = list(parse_milk_pdf(data, date(2012, 10, 31)))
        self.assertEqual(len(rows), 180)
        places = {(row[-1]["department"], row[4]): row for row in rows}
        self.assertEqual(places["Cauca", "Popayán"][6], 936)
        self.assertEqual(places["Cauca", "Popayán"][-1]["trend"], "☐")
        self.assertEqual(places["Cesar", "Chimichagua"][-1]["trend"], "☐☐")

    def test_wrapped_suffix_belongs_to_previous_price_not_next_municipality(self):
        p = column(
            [
                ("Villa de", 50, ("1.450", "2.200", "1.976")),
                ("Villapinzón", 70, ("1.500", "1.700", "1.680")),
            ],
            [
                word("San", 20, 58),
                word("Diego", 32, 58),
                word("de", 44, 58),
                word("Ubaté", 56, 58),
            ],
        )
        original = [
            "Mínimo Máximo Promedio",
            "Cundinamarca",
            "Villa de 1.450 2.200 1.976",
            "San Diego de Ubaté",
            "Villapinzón 1.500 1.700 1.680",
        ]
        parsed = _milk_column_native_lines(p, original)
        self.assertEqual(len(parsed), len(original))
        self.assertEqual(parsed[2], "Villa de San Diego de Ubaté 1.450 2.200 1.976")
        self.assertEqual(parsed[3], "")
        self.assertEqual(parsed[4], original[4])

    def test_hyphenation_joins_only_the_actual_next_native_name_line(self):
        p = column(
            [
                ("San Pedro de los Mi-", 50, ("1.000", "1.160", "1.077")),
                ("Santa Rosa de Osos", 71, ("950", "1.100", "1.019")),
            ],
            [word("lagros", 20, 58)],
        )
        rows = _milk_column_native_lines(
            p,
            [
                "Mínimo Máximo Promedio",
                "Antioquia",
                "San Pedro de los Mi- 1.000 1.160 1.077",
                "lagros",
                "Santa Rosa de Osos 950 1.100 1.019",
            ],
        )
        self.assertEqual(rows[2], "San Pedro de los Milagros 1.000 1.160 1.077")
        self.assertEqual(rows[3], "")
        self.assertEqual(rows[4], "Santa Rosa de Osos 950 1.100 1.019")

    def test_displaced_trend_is_not_a_place_prefix(self):
        p = column(
            [
                ("El Guamo", 50, ("850", "1.000", "920")),
                ("Magangué", 64, ("1.000", "1.100", "1.070")),
            ],
            [word("xx", 300, 54), word("x", 300, 64)],
        )
        rows = _milk_column_native_lines(
            p,
            [
                "Mínimo Máximo Promedio",
                "Bolívar",
                "El Guamo 850 1.000 920",
                "xx",
                "Magangué 1.000 1.100 1.070 x",
            ],
        )
        self.assertEqual(rows[2], "El Guamo 850 1.000 920 xx")
        self.assertEqual(rows[3], "")
        self.assertEqual(rows[4], "Magangué 1.000 1.100 1.070 x")

    def test_department_named_like_municipality_remains_a_heading(self):
        p = column([("Arauca", 50, ("900", "1.000", "950"))])
        rows = _milk_column_native_lines(
            p, ["Mínimo Máximo Promedio", "Arauca", "Arauca 900 1.000 950"]
        )
        self.assertEqual(rows[1], "Arauca")

    def test_missing_name_and_ambiguous_alignment_fail_closed(self):
        p = column([("", 50, ("900", "1.000", "950"))])
        with self.assertRaisesRegex(ValueError, "municipality"):
            _milk_column_native_lines(p, ["Mínimo Máximo Promedio", "900 1.000 950"])
        p = column([("Town", 50, ("900", "1.000", "950"))])
        with self.assertRaisesRegex(ValueError, "disagree"):
            _milk_column_native_lines(
                p, ["Mínimo Máximo Promedio", "Town 900 1.000 951"]
            )
        p = column(
            [
                ("First", 50, ("900", "1.000", "950")),
                ("Second", 70, ("900", "1.100", "980")),
            ],
            [word("uncertain", 20, 59.5, height=8)],
        )
        with self.assertRaisesRegex(ValueError, "equidistant"):
            _milk_column_native_lines(
                p,
                [
                    "Mínimo Máximo Promedio",
                    "First 900 1.000 950",
                    "uncertain",
                    "Second 900 1.100 980",
                ],
            )

    @unittest.skipUnless(
        (FIXTURES / "march2022.json").exists(), "retained March2022 original required"
    )
    def test_march2022_standalone_price_between_wrapped_name_lines(self):
        did = "a409579bc3e8ceb1b52e0202e1fb9dd4248879c453e0a0efcc37ee5e4e48a436"
        data = (FIXTURES / (did + ".pdf")).read_bytes()
        self.assertEqual(sha256(data).hexdigest(), did)
        rows = list(parse_milk_pdf(data, None))
        self.assertEqual(len(rows), 208)
        self.assertEqual({str(r[2]) for r in rows}, {"2022-03-31"})
        sample = {(r[-1]["department"], r[4]): r for r in rows}
        self.assertEqual(sample["Antioquia", "San Pedro de los Milagros"][6], 1823)
        self.assertEqual(sample["Antioquia", "Santa Rosa de Osos"][6], 1837)
        self.assertTrue(all("; parser " + MILK_PDF_VERSION in r[0] for r in rows))
        self.assertEqual(sample["Cundinamarca", "Villa de San Diego de Ubaté"][6], 1794)

    @unittest.skipUnless(
        (FIXTURES / "originals.json").exists(), "retained official fixtures required"
    )
    def test_nine_real_originals_preserve_all_literal_prices_and_fix_name_bindings(
        self,
    ):
        expected = {
            "7bdeb211": (208, "2024-11-30", 1976, 1680),
            "27c6b1f7": (208, "2024-12-31", 1988, 1679),
            "74de753f": (208, "2019-04-30", 1049, 1042),
            "bffc3f7f": (197, "2019-03-31", 1018, 1022),
            "888de793": (213, "2019-02-28", 980, 1024),
            "5844ef6d": (208, "2019-01-31", 980, 1007),
            "12bd5179": (208, "2019-05-31", 1064, 1037),
            "faadd1d8": (208, "2018-12-31", 980, 1011),
            "c39f07b8": (208, "2021-06-30", 1189, 1131),
        }
        total = 0
        for original in json.loads((FIXTURES / "originals.json").read_text()):
            did = original["document_id"]
            with self.subTest(document=did):
                path = FIXTURES / (did + ".pdf")
                body = path.read_bytes()
                self.assertEqual(sha256(body).hexdigest(), did)
                rows = list(parse_milk_pdf(body, None))
                count, day, ubate, villapinzon = expected[did[:8]]
                self.assertEqual(len(rows), count)
                self.assertEqual({str(row[2]) for row in rows}, {day})
                self.assertEqual({row[5] for row in rows}, {"litre"})
                self.assertEqual(
                    len({(row[-1]["department"], row[4]) for row in rows}),
                    208 if did.startswith("888de793") else count,
                )
                places = {(row[-1]["department"], row[4]): row for row in rows}
                self.assertEqual(
                    places["Cundinamarca", "Villa de San Diego de Ubaté"][6], ubate
                )
                self.assertEqual(places["Cundinamarca", "Villapinzón"][6], villapinzon)
                if did.startswith("888de793"):
                    self.assertEqual(
                        [r[6] for r in rows if r[4] == "Jamundí"], [1117, 1104]
                    )
                    self.assertEqual(
                        [r[6] for r in rows if r[4] == "Palmira"], [1070, 1115]
                    )
                    self.assertEqual(
                        [r[6] for r in rows if r[4] == "Tuluá"], [1052, 1057]
                    )
                if did.startswith("faadd1d8"):
                    self.assertEqual(
                        places["Antioquia", "San Pedro de los Milagros"][6], 1077
                    )
                    self.assertEqual(places["Antioquia", "Santa Rosa de Osos"][6], 1019)
                if did.startswith("c39f07b8"):
                    self.assertEqual(places["Bolívar", "Magangué"][6], 1070)
                    self.assertEqual(places["Bolívar", "El Guamo"][-1]["trend"], "xx")
                with patch(
                    "pipelines.ingestion.special_prices._milk_column_native_lines",
                    side_effect=lambda page, lines: lines,
                ):
                    old = list(parse_milk_pdf(body, None))

                def prices(values):
                    return [
                        (
                            r[0],
                            r[1:4],
                            r[5:7],
                            r[-1]["department"],
                            r[-1]["min_price"],
                            r[-1]["max_price"],
                        )
                        for r in values
                    ]

                self.assertEqual(prices(rows), prices(old))
                # Independent Poppler layout extraction of every monetary
                # triple; this does not reuse native word geometry or helpers.
                pages = path.with_suffix(".txt").read_text().split("\f")
                literal = []
                num = r"(?:\d{1,3}(?:\.\d{3})+|\d{3,4})"
                pattern = re.compile(
                    r"(?<![\d.,])("
                    + num
                    + r")\s+("
                    + num
                    + r")\s+("
                    + num
                    + r")(?![\d.,])"
                )
                for page in sorted({r[-1]["page"] for r in rows}):
                    text = pages[page - 1]
                    text = text[text.find("Departamentos") :].split("TENDENCIAS")[0]
                    for line in text.splitlines():
                        literal.extend(
                            tuple(int(v.replace(".", "")) for v in item)
                            for item in pattern.findall(line)
                        )
                self.assertEqual(
                    Counter(literal),
                    Counter(
                        (r[-1]["min_price"], r[-1]["max_price"], r[6]) for r in rows
                    ),
                )
                total += len(rows)
        self.assertEqual(total, 1866)


if __name__ == "__main__":
    unittest.main()
