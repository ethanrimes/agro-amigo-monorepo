"""Actual-original, same-URL revision publication checks in PostgreSQL TEMP tables.

HTTP 200/304 transport is covered independently by test_asset_transport_revisions.
These tests exercise each adapter's real parser, immutable archive, and publisher
on two byte-distinct originals at one URL; no production tables are written.
"""

import hashlib
import os
import re
import unittest
from datetime import date
from pathlib import Path

from . import colombia_sources, official_sources, special_prices, worker
from .test_official_catalog import install_cache

ORIGINALS = Path(__file__).parent / "testdata"
RICE = ORIGINALS / "25c9bad53ca56c0b4d6512d185cf9e5bed95afe9124e9a74fbd5c134c1d034ca.xlsx"

OFFICIAL_CASES = (
    ("colombia-agronet-cacao", "0eb1828e12b9a40e3add23c188a2becf7662accd10250a04cac9a9533687d027.html",
     "https://agronet.gov.co/noticias/precio-de-referencia-semanal-de-compra-de-cacao-fuente-industria-nacional-exportadores-0",
     "HTML table 1, row 2", date(2026, 9, 21), 14461.3),
    ("colombia-fedepalma-ffp", "50c6bc5e5a70ce7fac0d31b41cfa6defa3a7c99b809f94fb28c78a1d7f7079a1.html",
     "https://fedepalma.org/fondo-de-fomento-palmero-ffp/",
     "HTML FFP table, row 2, column 2", date(2026, 7, 1), 4054),
    ("colombia-fedegan-csv", "b9cde9b3475cafa6995fb41be34abc67609ed0e6a1054b326d37f931187a49ec.csv",
     "https://estadisticas.fedegan.org.co/DOC/export.jsp?pId=63&pSd=01-01-1900&pEd=31-12-2026&pCol=-1%2C1&pRow=-1%2C1",
     "CSV row 3, column 2", date(2006, 1, 31), 2636),
    ("colombia-pork-pdf", "b62ae36ecf41b8f68b786a170aee12c96c277b1374a7b09ed3136212bbb79ef1.pdf",
     "https://porkcolombia.co/wp-content/uploads/2026/09/Quincena20de2026.pdf",
     "PDF page 1, current prices column 1, y 566.3", date(2026, 9, 25), 6078),
    ("colombia-corabastos-pdf", "e65a3bed02c2056fdb56fd2da8d3cd390ecf26026613ec77d38eb4d1a7829208.pdf",
     "https://corabastos.com.co/wp-content/uploads/2026/09/Boletin_diario_20260925.pdf",
     "PDF page 2, table 1, row 4; price column 1", date(2026, 9, 25), 15000),
)


def changed_without_price_change(body, kind):
    """Represent a publisher's same-URL revision with a controlled edit."""
    if kind.endswith("pdf"):
        return body + b"\n% retained-revision-fixture: cosmetic footer\n"
    if kind == "colombia-fedegan-csv":
        # Independent original CSV row 3 is ene/2006;2.636;. Change exactly
        # that printed price to 2.637 while every other row stays byte-identical.
        assert body.count(b"ene/2006;2.636;") == 1
        return body.replace(b"ene/2006;2.636;", b"ene/2006;2.637;", 1)
    return body + b"\n<!-- retained-revision-fixture: cosmetic footer -->\n"


@unittest.skipUnless(
    os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1",
    "Explicit opt-in for private PostgreSQL TEMP-table checks",
)
class AdapterRevisionContracts(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        for table in (
            "source_document", "official_price_quote", "official_source_review",
            "ingestion_asset", "ingestion_checkpoint", "historical_price",
            "price_observation", "price_observation_review", "product", "market",
            "document_alias",
        ):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.db.execute("CREATE TEMP TABLE municipality(name text,department text)")
        self.db.execute("INSERT INTO municipality VALUES('Aguazul','Casanare'),('Bucaramanga','Santander')")
        install_cache(self.db)
        for table in ("source_document", "official_price_quote", "historical_price", "price_observation"):
            self.assertEqual(self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)", (table,),
            ).fetchone(), ("t",))

    def archived(self, url, body, kind, retrieved):
        did = worker.archive(self.db, url, body, kind, register_alias=False)
        self.db.execute("UPDATE source_document SET retrieved_at=%s WHERE id=%s", (retrieved, did))
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,%s,%s,'complete') "
            "ON CONFLICT(url) DO UPDATE SET document_id=excluded.document_id,status='complete'",
            (url, kind, did),
        )
        return did

    def test_five_colombia_adapters_keep_old_originals_and_equal_value_revision(self):
        for kind, filename, url, locator, observed_on, expected_price in OFFICIAL_CASES:
            with self.subTest(kind=kind):
                # A fresh TEMP schema per subcase prevents identical canonical
                # quote keys across unrelated publishers from hiding a defect.
                body = (ORIGINALS / filename).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), filename.split(".")[0])
                old_rows = list(colombia_sources.parse(body, url, kind))
                anchors = [r for r in old_rows if r["source_locator"] == locator
                           and date.fromisoformat(str(r["date"])) == observed_on]
                self.assertEqual(len(anchors), 1)
                self.assertAlmostEqual(anchors[0]["price"], expected_price, places=2)

                old_id = self.archived(url, body, kind, "2026-09-26T00:00:00Z")
                official_sources.publish_rows(self.db, old_rows, old_id, kind)
                old_quote = self.db.execute(
                    "SELECT quote_key,price FROM official_price_quote "
                    "WHERE document_id=%s AND source_locator=%s",
                    (old_id, locator),
                ).fetchone()
                self.assertIsNotNone(old_quote)
                self.assertAlmostEqual(float(old_quote[1]), expected_price, places=2)

                revision = changed_without_price_change(body, kind)
                revised_expected = 2637 if kind == "colombia-fedegan-csv" else expected_price
                new_rows = list(colombia_sources.parse(revision, url, kind))
                revised_anchor = [r for r in new_rows if r["source_locator"] == locator
                                  and date.fromisoformat(str(r["date"])) == observed_on]
                self.assertEqual(len(revised_anchor), 1)
                self.assertAlmostEqual(revised_anchor[0]["price"], revised_expected, places=2)
                new_id = self.archived(url, revision, kind, "2026-09-27T00:00:00Z")
                self.assertNotEqual(new_id, old_id)
                official_sources.publish_rows(self.db, new_rows, new_id, kind)

                current = self.db.execute(
                    "SELECT document_id,price FROM published_official_price "
                    "WHERE quote_key=%s AND observed_on=%s",
                    (old_quote[0], observed_on),
                ).fetchone()
                self.assertEqual(current[0], new_id)
                self.assertAlmostEqual(float(current[1]), revised_expected, places=2)
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM official_price_quote WHERE quote_key=%s "
                    "AND observed_on=%s AND document_id IN (%s,%s)",
                    (old_quote[0], observed_on, old_id, new_id),
                ).fetchone()[0], 2)
                self.assertEqual(bytes(self.db.execute(
                    "SELECT content FROM source_document WHERE id=%s", (old_id,),
                ).fetchone()[0]), body)

                before = self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0]
                official_sources.publish_rows(self.db, new_rows, new_id, kind)
                official_sources.publish_rows(self.db, old_rows, old_id, kind)
                self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], before)
                self.assertEqual(self.db.execute(
                    "SELECT document_id FROM published_official_price "
                    "WHERE quote_key=%s AND observed_on=%s",
                    (old_quote[0], observed_on),
                ).fetchone()[0], new_id)
                self.db.execute("TRUNCATE source_document, official_price_quote, official_source_review, ingestion_asset, ingestion_checkpoint, official_catalog_current RESTART IDENTITY CASCADE")

    def test_rice_same_url_revision_preserves_tonne_raw_and_kg_winner(self):
        body = RICE.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), RICE.stem)
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-arroz-sub-molinos-2013-2020.xlsx"
        cases = (("precios de arroz en molino!row 8", "Aguazul", 2464133.3333333335),
                 ("precios de arroz en molino!row 9", "Bucaramanga", 2146666.6666666665))
        for revision_no, revision in enumerate((body, changed_without_price_change(body, "rice"))):
            rows = list(special_prices.parse_special(revision, "rice"))
            for locator, market, expected in cases:
                anchors = [r for r in rows if r[0] == locator]
                self.assertEqual(len(anchors), 1)
                self.assertEqual((anchors[0][2], anchors[0][4], anchors[0][5]),
                                 (date(2013, 1, 31), market, "tonne"))
                self.assertAlmostEqual(anchors[0][6], expected, places=4)
            did = self.archived(url, revision, "rice", f"2026-09-{26+revision_no:02d}T00:00:00Z")
            with self.db.transaction():
                worker.save_rows(self.db, did, rows)
                worker.project(self.db, did, url, "rice")
            if revision_no == 0:
                old_id = did
            else:
                new_id = did
        self.assertNotEqual(old_id, new_id)
        for locator, market, expected in cases:
            raw = self.db.execute(
                "SELECT document_id,price FROM historical_price WHERE source_locator=%s "
                "AND document_id IN (%s,%s) ORDER BY document_id",
                (locator, old_id, new_id),
            ).fetchall()
            self.assertEqual({r[0] for r in raw}, {old_id, new_id})
            self.assertEqual(len(raw), 2)
            self.assertTrue(all(abs(float(r[1]) - expected) < .001 for r in raw))
            current = self.db.execute(
                "SELECT document_id,price FROM price_observation WHERE source_id='dane-rice-mill' "
                "AND observed_on='2013-01-31' AND market_id=%s AND product_id='molino-arroz-blanco-empacado'",
                ("molino-casanare-aguazul" if market == "Aguazul" else "molino-santander-bucaramanga",),
            ).fetchone()
            self.assertEqual(current[0], new_id)
            # The published COP/kg column stores two currency decimals while
            # immutable raw history keeps the original COP/tonne precision.
            self.assertAlmostEqual(float(current[1]), expected / 1000, places=2)
        before = self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0]
        with self.db.transaction():
            worker.save_rows(self.db, new_id, list(special_prices.parse_special(changed_without_price_change(body, "rice"), "rice")))
            worker.project(self.db, new_id, url, "rice")
        with self.db.transaction():
            worker.save_rows(self.db, old_id, list(special_prices.parse_special(body, "rice")))
            worker.project(self.db, old_id, url, "rice")
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], before)
        for _, market, expected in cases:
            current = self.db.execute(
                "SELECT document_id,price FROM price_observation WHERE source_id='dane-rice-mill' "
                "AND observed_on='2013-01-31' AND market_id=%s AND product_id='molino-arroz-blanco-empacado'",
                ("molino-casanare-aguazul" if market == "Aguazul" else "molino-santander-bucaramanga",),
            ).fetchone()
            self.assertEqual(current[0], new_id)
            self.assertAlmostEqual(float(current[1]), expected / 1000, places=2)
