"""Two retained DANE milk originals with a literal split Bolívar municipality."""

import hashlib
import os
import unittest
from datetime import date
from pathlib import Path

from . import special_prices, test_special_projection as projection_tests, worker


FIXTURES = Path(__file__).parent / "testdata"
ORIGINALS = (
    (
        "milk_jun2022_native_original.pdf",
        "a8e27086128ff3f2a3c67147dfa6782a947a6e3ad6c94b52af4c2d3537d1ab63",
        date(2022, 6, 30),
        1200.0, 1400.0, 1295.0,
    ),
    (
        "milk_jul2022_native_original.pdf",
        "4cf84658353b236e022d39c737e16975d94e22e5cde92dd96f308d3e042f6e0e",
        date(2022, 7, 31),
        1200.0, 1500.0, 1328.0,
    ),
)


class NepomucenoNativeWrapTests(unittest.TestCase):
    def test_two_full_originals_retain_printed_words_and_canonical_identity(self):
        for filename, sha, day, minimum, maximum, mean in ORIGINALS:
            with self.subTest(original=filename):
                body = (FIXTURES / filename).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
                rows = list(special_prices.parse_milk_pdf(body, day))
                self.assertEqual(len(rows), 208)
                target = [
                    row for row in rows
                    if row[-1].get("literal_municipality")
                ]
                self.assertEqual(len(target), 1)
                locator, _, observed, _, town, unit, price, _, details = target[0]
                self.assertEqual(
                    (locator, observed, town, unit, price),
                    (
                        "PDF page 5,col 2,line 18; parser " + special_prices.MILK_PDF_VERSION,
                        day, "San Juan Nepomuceno", "litre", mean,
                    ),
                )
                self.assertEqual(
                    (
                        details["department"], details["municipality"],
                        details["literal_municipality"],
                        details["literal_source_locator"], details["source_sha256"],
                        details["min_price"], details["max_price"],
                    ),
                    (
                        "Bolívar", "San Juan Nepomuceno", "San Juan Nepomu- ceno",
                        "PDF page 5,col 2,line 17-19", sha, minimum, maximum,
                    ),
                )
                self.assertFalse(any("Nepomu-" in row[4] for row in rows))

    def test_guard_does_not_strip_other_hyphens_or_guess_department(self):
        sha = ORIGINALS[0][1]
        day = ORIGINALS[0][2]
        lines = [""] * 16 + [
            "San Juan Nepomu-", "1.200 1.400 1.295 =", "ceno",
        ]
        good = (sha, day, "Bolívar", "San Juan Nepomuceno",
                "PDF page 5,col 2,line 18", (1200.0, 1400.0, 1295.0), lines)
        self.assertEqual(
            special_prices._verified_nepomuceno_wrap(*good),
            "San Juan Nepomu- ceno",
        )
        for position, replacement in (
            (0, "0" * 64),
            (2, "Antioquia"),
            (3, "San Juan Nepomu- ceno"),
        ):
            variant = list(good)
            variant[position] = replacement
            self.assertIsNone(special_prices._verified_nepomuceno_wrap(*variant))
        for position, replacement in (
            (1, date(2022, 7, 31)),
            (4, "PDF page 5,col 2,line 19"),
            (5, (1200.0, 1400.0, 1296.0)),
            (6, lines[:17] + ["1.200 1.400 1.295 =", "ceno-sur"]),
        ):
            variant = list(good)
            variant[position] = replacement
            with self.assertRaises(ValueError):
                special_prices._verified_nepomuceno_wrap(*variant)


@unittest.skipUnless(
    os.environ.get("AGRO_MILK_NEPOMUCENO_POSTGRES_TEST") == "1",
    "Explicit isolated PostgreSQL TEMP-table opt-in",
)
class NepomucenoPublicationTests(unittest.TestCase):
    def setUp(self):
        projection_tests.SpecialProjectionPostgresTests.setUp(self)
        self.db.execute("CREATE TEMP TABLE price_observation_review "
                        "(LIKE public.price_observation_review INCLUDING ALL)")
        self.db.execute("CREATE TEMP TABLE official_source_review "
                        "(LIKE public.official_source_review INCLUDING ALL)")
        self.db.execute("""CREATE TEMP VIEW published_price_observation AS
          SELECT p.* FROM price_observation p WHERE NOT EXISTS(
            SELECT 1 FROM price_observation_review r WHERE
             (r.document_id,r.source_locator,r.product_id,r.market_id,r.source_id,
              r.observed_on,r.period,r.unit)=
             (p.document_id,p.source_locator,p.product_id,p.market_id,p.source_id,
              p.observed_on,p.period,p.unit))""")

    def prepare(self, *, official=True):
        filename, sha, day, low, high, mean = ORIGINALS[1]
        body = (FIXTURES / filename).read_bytes()
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/BolSipsaLeche_jul_2022.pdf"
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content)
               VALUES(%s,'July 2022 DANE milk','DANE',%s,'application/pdf','original','2022-07',%s)""",
            (sha, url, body),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status) "
            "VALUES(%s,'milk-pdf',%s,%s,'complete')", (url, sha, day),
        )
        if official:
            self.db.execute(
                """INSERT INTO municipality
                   (id,name,department,department_id,latitude,longitude)
                   VALUES(1,'SAN JUAN NEPOMUCENO','BOLÍVAR',13,9.95,-75.08)"""
            )
        old = worker.record(
            "dane-milk-farm", day, "Leche cruda en finca",
            "San Juan Nepomu- ceno", "litre", mean,
            "PDF page 5,col 2,line 19",
            details={"department": "Bolívar", "municipality": "San Juan Nepomu- ceno",
                     "price_basis": "farmgate", "min_price": low,
                     "max_price": high, "page": 5},
        )
        current = next(row for row in special_prices.parse_milk_pdf(body, day)
                       if row[-1].get("literal_municipality"))
        return sha, url, body, old, current

    def test_old_id_is_reviewed_only_after_exact_verified_correction(self):
        sha, url, body, old, current = self.prepare()
        with self.db.transaction():
            worker.save_rows(self.db, sha, [old])
        self.assertEqual(special_prices.project_special(self.db, sha, url), 0)
        self.assertEqual(
            self.db.execute("SELECT market_id FROM published_price_observation").fetchall(),
            [("finca-bolivar-san-juan-nepomu-ceno",)],
        )
        with self.db.transaction():
            worker.save_rows(self.db, sha, [current])
        for _ in range(2):
            self.assertEqual(special_prices.project_special(self.db, sha, url), 0)
        self.assertEqual(
            self.db.execute("SELECT market_id FROM published_price_observation").fetchall(),
            [("finca-bolivar-san-juan-nepomuceno",)],
        )
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM price_observation_review"
        ).fetchone(), (1,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s", (sha,)
        ).fetchone(), (2,))
        retained = bytes(self.db.execute(
            "SELECT content FROM source_document WHERE id=%s", (sha,)
        ).fetchone()[0])
        self.assertEqual(retained, body)

    def test_canonical_replay_requires_official_municipality(self):
        sha, url, _, _, current = self.prepare(official=False)
        with self.db.transaction():
            worker.save_rows(self.db, sha, [current])
        with self.assertRaisesRegex(ValueError, "official municipality"):
            special_prices.project_special(self.db, sha, url)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM price_observation"
        ).fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
