"""Native milk table cell binding: wrapped names and displaced trend glyphs."""

import json
import re
from collections import Counter
import unittest
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .special_prices import _milk_column_native_lines, parse_milk_pdf

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
        self.assertTrue(all("; parser milk-pdf-v7" in r[0] for r in rows))
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
