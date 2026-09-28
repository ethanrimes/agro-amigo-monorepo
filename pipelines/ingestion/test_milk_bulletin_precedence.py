"""Actual PostgreSQL view/cache parity for repeated monthly milk chart labels."""

import os
import re
import unittest
from pathlib import Path

from . import official_catalog
from . import test_official_catalog as fixtures

MIGRATION = (
    Path(__file__).parent / "migrations/20260927_019_milk_bulletin_precedence.sql"
)


def quote(day, price, locator, period=None, *, series="dane-milk-macroregion"):
    row = fixtures.quote(day, price, locator, "Leche cruda en finca")
    row.update(
        series=series,
        basis="Promedio mensual publicado en finca por macrorregión",
        unit="litro",
        market="Costa Caribe",
    )
    if period is not None:
        row["details"]["bulletin_period"] = period
    return row


@unittest.skipUnless(
    os.environ.get("AGRO_MILK_PRECEDENCE_TEST") == "1",
    "Explicit isolated PostgreSQL opt-in",
)
class MilkBulletinPrecedence(unittest.TestCase):
    original = fixtures.OfficialCatalogPostgresTests.original
    publish = fixtures.OfficialCatalogPostgresTests.publish
    cache = fixtures.OfficialCatalogPostgresTests.cache

    def setUp(self):
        fixtures.OfficialCatalogPostgresTests.setUp(self)
        migration = re.sub(
            r"^GRANT .*;\n", "", MIGRATION.read_text(), flags=re.MULTILINE
        )
        self.db.execute(migration)

    def source(self, name, period, retrieved):
        did = self.original(name, retrieved)
        self.db.execute(
            "UPDATE source_document SET reference_period=%s WHERE id=%s", (period, did)
        )
        return did

    def visible(self, day):
        return self.db.execute(
            "SELECT document_id,price FROM published_official_price WHERE observed_on=%s",
            (day,),
        ).fetchone()

    def test_newer_bulletin_wins_reversed_download_and_latest_previous_cache(self):
        later = self.source("June bulletin", "2026-06-30", "2026-09-08T00:00:00Z")
        older = self.source(
            "May bulletin fetched later", "2026-05-31", "2026-09-10T00:00:00Z"
        )
        self.publish(
            later,
            [
                quote("2026-05-31", 2110, "prior in June", "2026-06-30"),
                quote("2026-06-30", 2200, "current June", "2026-06-30"),
            ],
        )
        before = self.db.execute(
            "SELECT md5(to_jsonb(q)::text) FROM official_price_quote q"
        ).fetchall()
        self.publish(
            older,
            [
                quote("2026-04-30", 1900, "prior in May", "2026-05-31"),
                quote("2026-05-31", 2000, "current May", "2026-05-31"),
            ],
        )
        self.assertEqual(self.visible("2026-05-31"), (later, 2110))
        row = self.cache()[0][1]
        self.assertEqual(
            (row["price"], row["previous_price"], row["document_id"]),
            (2200, 2110, later),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            4,
        )
        after = self.db.execute(
            "SELECT md5(to_jsonb(q)::text) FROM official_price_quote q"
        ).fetchall()
        self.assertTrue(set(before) <= set(after))
        self.publish(older, [quote("2026-05-31", 2000, "current May", "2026-05-31")])
        self.assertEqual(self.visible("2026-05-31"), (later, 2110))

    def test_same_bulletin_newer_file_revision_wins_and_equal_value_provenance(self):
        old = self.source("June first revision", "2026-06-30", "2026-09-08T00:00:00Z")
        new = self.source(
            "June corrected revision", "2026-06-30", "2026-09-09T00:00:00Z"
        )
        self.publish(old, [quote("2026-05-31", 2110, "May in June", "2026-06-30")])
        self.publish(
            new, [quote("2026-05-31", 2110, "May in revised June", "2026-06-30")]
        )
        self.assertEqual(self.visible("2026-05-31"), (new, 2110))
        self.assertEqual(self.cache()[0][1]["document_id"], new)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            2,
        )

    def test_missing_metadata_uses_only_validated_current_or_next_source_period(self):
        older = self.source("May legacy metadata", "2026-05-31", "2026-09-20T00:00:00Z")
        later = self.source(
            "June legacy metadata", "2026-06-30", "2026-09-08T00:00:00Z"
        )
        self.publish(older, [quote("2026-05-31", 2000, "old")])
        self.publish(later, [quote("2026-05-31", 2110, "new")])
        self.assertEqual(self.visible("2026-05-31"), (later, 2110))
        self.assertEqual(self.cache()[0][1]["document_id"], later)

    def test_malformed_missing_and_nonadjacent_period_never_cast_or_gain_priority(self):
        valid = self.source("Valid May", "2026-05-31", "2026-09-01T00:00:00Z")
        self.publish(valid, [quote("2026-05-31", 2000, "verified", "2026-05-31")])
        malformed = [
            "not a date",
            "2026-99-99",
            "2026-02-31",
            "2027-05-31",
            "2026-07-31",
            "2026-04-30",
            "2026-06-15",
            {"unknown": "date"},
            ["2026-06-30"],
        ]
        for i, period in enumerate(malformed):
            with self.subTest(period=period):
                did = self.source(
                    "Malformed " + str(i), "2026-06-30", "2026-09-25T00:00:00Z"
                )
                self.publish(did, [quote("2026-05-31", 9999, "bad" + str(i), period)])
                self.assertEqual(self.visible("2026-05-31"), (valid, 2000))
                self.assertEqual(self.cache()[0][1]["document_id"], valid)
        absent = self.source("No period anywhere", "", "2026-09-26T00:00:00Z")
        self.publish(absent, [quote("2026-05-31", 9999, "absent")])
        self.assertEqual(self.visible("2026-05-31"), (valid, 2000))

    def test_non_month_end_does_not_use_milk_bulletin_priority(self):
        earlier_fetch = self.source(
            "Suspicious midmonth", "2026-06-30", "2026-09-01T00:00:00Z"
        )
        later_fetch = self.source(
            "Latest retained midmonth", "", "2026-09-25T00:00:00Z"
        )
        self.publish(earlier_fetch, [quote("2026-05-15", 1900, "old", "2026-06-30")])
        self.publish(later_fetch, [quote("2026-05-15", 2000, "new")])
        self.assertEqual(self.visible("2026-05-15"), (later_fetch, 2000))

    def test_other_series_retains_retrieval_precedence(self):
        older_fetch = self.source("Old nonmilk", "2026-06-30", "2026-09-01T00:00:00Z")
        newer_fetch = self.source("New nonmilk", "2026-05-31", "2026-09-25T00:00:00Z")
        self.publish(
            older_fetch,
            [quote("2026-05-31", 1900, "old", "2026-06-30", series="dane-weekly")],
        )
        self.publish(
            newer_fetch,
            [quote("2026-05-31", 2000, "new", "2026-05-31", series="dane-weekly")],
        )
        self.assertEqual(self.visible("2026-05-31"), (newer_fetch, 2000))
        self.assertEqual(self.cache()[0][1]["document_id"], newer_fetch)

    def test_review_exclusion_still_precedes_bulletin_priority(self):
        older = self.source("Older valid", "2026-05-31", "2026-09-25T00:00:00Z")
        newer = self.source("Newer reviewed", "2026-06-30", "2026-09-01T00:00:00Z")
        self.publish(older, [quote("2026-05-31", 2000, "old", "2026-05-31")])
        self.publish(newer, [quote("2026-05-31", 2110, "new", "2026-06-30")])
        self.db.execute(
            "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,'new','review-v2','{}','ambiguous')",
            (newer,),
        )
        official_catalog.refresh_document(self.db, newer)
        self.assertEqual(self.visible("2026-05-31"), (older, 2000))
        self.assertEqual(self.cache()[0][1]["document_id"], older)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            2,
        )

    def test_schema_view_matches_migration_and_dirty_only_milk(self):
        def view(sql):
            return (
                sql.split("CREATE OR REPLACE VIEW published_official_price AS", 1)[1]
                .split(";", 1)[0]
                .strip()
            )

        schema = (Path(__file__).parent / "schema.sql").read_text()
        self.assertEqual(view(schema), view(MIGRATION.read_text()))
        milk = self.source("Milk cache", "2026-06-30", "2026-09-01T00:00:00Z")
        other = self.source("Other cache", "", "2026-09-01T00:00:00Z")
        self.publish(milk, [quote("2026-05-31", 2000, "milk", "2026-06-30")])
        self.publish(other, [quote("2026-05-31", 3000, "other", series="dane-weekly")])
        self.db.execute(
            re.sub(r"^GRANT .*;\n", "", MIGRATION.read_text(), flags=re.MULTILINE)
        )
        states = {row[1]["series"]: row[2] for row in self.cache()}
        self.assertEqual(states, {"dane-milk-macroregion": True, "dane-weekly": False})


class MilkBulletinMetadata(unittest.TestCase):
    def test_both_observation_months_keep_validated_report_month(self):
        from . import milk_macroregions
        from .test_milk_macroregions import CHART, reading

        rows = milk_macroregions.parse_reading(CHART, reading())
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            {r["details"]["bulletin_period"] for r in rows}, {"2025-12-31"}
        )
        self.assertEqual(
            {r["date"].isoformat() for r in rows}, {"2025-11-30", "2025-12-31"}
        )
