"""Real ambiguous publisher files retain dates; corroborated alternatives cover rows."""

import hashlib
import unittest
import zipfile
from datetime import date
from pathlib import Path

from . import city_reports, special_prices, worker

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/source-ambiguity-2026-09-27/city-milk"
)


def member(day, prefix):
    path = FIXTURES / f"bol-SIPSADiario-regionales-{day}sep2026.zip"
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.startswith(prefix)]
        if len(names) != 1:
            raise AssertionError("Expected one exact city member")
        return archive.read(names[0])


@unittest.skipUnless(FIXTURES.exists(), "Retained official conflict fixtures required")
class SourceDateAlternatives(unittest.TestCase):
    def test_premature_city_dates_stay_rejected_and_nextday_sources_cover_all_prices(
        self,
    ):
        for day, prefix, count, alternate_count in (
            (17, "Cúcuta, La Nueva Sexta-18-09-2026", 28, 43),
            (24, "Bogotá, D.C., Corabastos-25-09-2026", 72, 272),
        ):
            with self.subTest(city=prefix):
                original, alternative = member(day, prefix), member(day + 1, prefix)
                with self.assertRaises(worker.SourceDateMismatch):
                    list(city_reports.parse_city_pdf(original, date(2026, 9, day)))
                # Corroboration is an audit comparison, not a runtime date override.
                rows = list(
                    city_reports.parse_city_pdf(original, date(2026, 9, day + 1))
                )
                other = list(
                    city_reports.parse_city_pdf(alternative, date(2026, 9, day + 1))
                )
                self.assertEqual((len(rows), len(other)), (count, alternate_count))
                identity = lambda row: tuple(row[i] for i in (2, 4, 6, 7, 8, 9))
                prices = {identity(row): (row[11], row[12]) for row in other}
                for row in rows:
                    self.assertEqual(row[1], date(2026, 9, day + 1))
                    self.assertEqual(prices[identity(row)], (row[11], row[12]))

    def test_empty_santa_marta_template_never_creates_price_rows(self):
        body = member(17, "Santa Marta (Magdalena)-18-09-2026")
        with self.assertRaises(worker.SourceDateMismatch):
            list(city_reports.parse_city_pdf(body, date(2026, 9, 17)))
        with self.assertRaisesRegex(ValueError, "No city price ranges parsed"):
            list(city_reports.parse_city_pdf(body, date(2026, 9, 18)))

    def test_december_annex_is_november_duplicate_not_a_date_format_to_override(self):
        november = (FIXTURES / "Anexo-SipsaLeche_nov_2020.xlsx").read_bytes()
        december = (FIXTURES / "Anexo-SipsaLeche_dic_2020.xlsx").read_bytes()
        self.assertEqual(november, december)
        self.assertEqual(
            hashlib.sha256(december).hexdigest(),
            "bc9e16af972eac40d3cb876c494d38581f61927e52b8a18f645e5ee5c0447c69",
        )
        with self.assertRaises(worker.SourceDateMismatch):
            list(special_prices.parse_special(december, "milk", date(2020, 12, 31)))
        november_rows = list(
            special_prices.parse_special(november, "milk", date(2020, 11, 30))
        )
        december_pdf = list(
            special_prices.parse_milk_pdf(
                (FIXTURES / "BolSipsaLeche_dic_2020.pdf").read_bytes(),
                date(2020, 12, 31),
            )
        )
        self.assertEqual((len(november_rows), len(december_pdf)), (208, 208))
        self.assertEqual({row[2] for row in december_pdf}, {date(2020, 12, 31)})
        self.assertEqual({row[5] for row in december_pdf}, {"litre"})
        key = lambda row: (worker.slug(row[8]["department"]), worker.slug(row[4]))
        old = {key(row): row[6] for row in november_rows}
        changed = sum(
            abs(float(old[key(row)]) - float(row[6])) > 0.5000001
            for row in december_pdf
        )
        self.assertEqual(changed, 199)
        abejorral = next(
            row for row in december_pdf if key(row) == ("antioquia", "abejorral")
        )
        self.assertEqual(
            (abejorral[8]["min_price"], abejorral[8]["max_price"], abejorral[6]),
            (1020, 1200, 1121),
        )

    def test_annual_2020_file_does_not_claim_unpublished_months(self):
        body = (
            FIXTURES / "series-historicas-precios-mayoristas-leche-2020.xlsx"
        ).read_bytes()
        rows = list(special_prices.parse_special(body, "milk"))
        self.assertEqual(len(rows), 1456)
        self.assertEqual({row[2].month for row in rows}, set(range(1, 8)))


if __name__ == "__main__":
    unittest.main()
