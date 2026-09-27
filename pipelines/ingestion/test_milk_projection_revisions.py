"""A native parser upgrade retains old raw rows but projects one physical row."""

import unittest
from psycopg.errors import CheckViolation

from . import special_prices, worker
from .test_special_projection import SpecialProjectionPostgresTests, milk


class MilkProjectionRevisionTests(SpecialProjectionPostgresTests):
    def setUp(self):
        super().setUp()
        self.db.execute("""CREATE TEMP TABLE price_observation_review(
          document_id text,source_locator text,product_id text,market_id text,source_id text,
          observed_on date,period text,unit text,reason text,evidence jsonb,
          PRIMARY KEY(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit));
          CREATE TEMP VIEW published_price_observation AS SELECT p.* FROM price_observation p
          WHERE NOT EXISTS(SELECT 1 FROM price_observation_review r
           WHERE (r.document_id,r.source_locator,r.product_id,r.market_id,r.source_id,r.observed_on,r.period,r.unit)
             =(p.document_id,p.source_locator,p.product_id,p.market_id,p.source_id,p.observed_on,p.period,p.unit))""")

    def test_published_malformed_identity_gets_exact_review_with_correction_atomically(
        self,
    ):
        physical = "PDF page 6,col 2,line 30"
        original = self.original(
            "published-native-upgrade",
            [milk(town="Villa de", locator=physical)],
            media="application/pdf",
        )
        self.publish(original)
        old = self.db.execute(
            "SELECT source_locator,market_id FROM price_observation"
        ).fetchone()
        with self.db.transaction():
            worker.save_rows(
                self.db,
                original[0],
                [
                    milk(
                        town="Villa de San Diego de Ubaté",
                        locator=physical + "; parser milk-pdf-v7",
                    )
                ],
            )
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.count("historical_price"), 2)
        self.assertEqual(self.count("price_observation"), 2)
        self.assertEqual(self.count("price_observation_review"), 1)
        self.assertEqual(self.count("published_price_observation"), 1)
        review = self.db.execute(
            "SELECT source_locator,market_id,evidence FROM price_observation_review"
        ).fetchone()
        self.assertEqual(review[:2], old)
        self.assertEqual(review[2]["physical_source_locator"], physical)
        self.assertEqual(
            review[2]["corrected_market_id"],
            "finca-antioquia-villa-de-san-diego-de-ubate",
        )
        self.assertEqual(review[2]["literal_price"], 2100)
        self.publish(original)
        self.assertEqual(self.count("price_observation_review"), 1)

    def test_correct_name_with_conflicting_price_still_reviews_proven_old_identity(
        self,
    ):
        physical = "PDF page 6,col 2,line 30"
        original = self.original(
            "conflicted-native-upgrade",
            [milk(town="Villa de", locator=physical)],
            media="application/pdf",
        )
        self.publish(original)
        with self.db.transaction():
            worker.save_rows(
                self.db,
                original[0],
                [
                    milk(
                        town="Villa de San Diego de Ubaté",
                        locator=physical + "; parser milk-pdf-v7",
                    ),
                    milk(
                        2150,
                        town="Villa de San Diego de Ubaté",
                        locator="PDF page 7,col 1,line 4; parser milk-pdf-v7",
                    ),
                ],
            )
        self.assertEqual(self.publish(original), 1)
        self.assertEqual(self.count("price_observation_review"), 1)
        self.assertEqual(self.count("published_price_observation"), 0)
        self.assertEqual(self.count("price_observation"), 1)
        self.assertEqual(self.count("historical_price"), 3)
        review = self.db.execute(
            "SELECT evidence FROM price_observation_review"
        ).fetchone()[0]
        self.assertTrue(review["canonical_price_conflict"])
        self.assertEqual(
            review["corrected_market_id"], "finca-antioquia-villa-de-san-diego-de-ubate"
        )

    def test_failed_correction_rolls_back_automatic_reviews_together_with_prices(self):
        physical = "PDF page 6,col 2,line 30"
        original = self.original(
            "invalid-native-upgrade",
            [milk(town="Villa de", locator=physical)],
            media="application/pdf",
        )
        self.publish(original)
        with self.db.transaction():
            worker.save_rows(
                self.db,
                original[0],
                [
                    milk(
                        town="Villa de San Diego de Ubaté",
                        low=3000,
                        locator=physical + "; parser milk-pdf-v7",
                    )
                ],
            )
        with self.assertRaises(CheckViolation):
            self.publish(original)
        self.assertEqual(self.count("price_observation_review"), 0)
        self.assertEqual(self.count("price_observation"), 1)
        self.assertEqual(self.count("historical_price"), 2)

    def test_latest_native_names_win_without_conflicting_with_retained_old_names(self):
        physical = "PDF page 6,col 2,line 30"
        original = self.original(
            "native-name-upgrade",
            [milk(town="Villa de", locator=physical)],
            media="application/pdf",
        )
        fixed = milk(
            town="Villa de San Diego de Ubaté",
            locator=physical + "; parser " + special_prices.MILK_PDF_VERSION,
        )
        with self.db.transaction():
            worker.save_rows(self.db, original[0], [fixed])
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.count("historical_price"), 2)
        self.assertEqual(self.count("price_observation"), 1)
        self.assertEqual(
            self.db.execute("SELECT market_id FROM price_observation").fetchone()[0],
            "finca-antioquia-villa-de-san-diego-de-ubate",
        )
        self.assertIn("; parser milk-pdf-v7", self.prices()[0][-1])
        retained = self.count("retained_record")
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.count("retained_record"), retained)
        self.assertEqual(self.count("historical_price"), 2)

    def test_revisions_do_not_become_false_conflicts_and_version_sort_is_numeric(self):
        physical = "PDF page 6,col 2,line 30"
        original = self.original(
            "native-values-upgrade",
            [
                milk(2100, locator=physical),
                milk(2150, locator=physical + "; parser milk-pdf-v7"),
                milk(2175, locator=physical + "; parser milk-pdf-v10"),
            ],
            media="application/pdf",
        )
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.prices()[0][0], 2175)
        self.assertEqual(self.count("historical_price"), 3)
        self.assertIn("; parser milk-pdf-v10", self.prices()[0][-1])


if __name__ == "__main__":
    unittest.main()
