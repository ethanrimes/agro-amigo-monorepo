"""Exact official originals and opt-in isolated PostgreSQL replay checks."""

import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb

from . import colombia_sources, international_sources, official_sources, queue_plan, worker


PORK = Path(__file__).parent / "testdata/3b9009dd742d30db945636b203a20729df4d7aec19b5ffad64173f6cdba62084.pdf"
PORK_SHA = "3b9009dd742d30db945636b203a20729df4d7aec19b5ffad64173f6cdba62084"
BARE = "PDF page 3, Cerdo en pie, y 425.3"
LEGACY = BARE + ", market Caribe Norte"
CURRENT = "PDF page 1, current prices column 1, y 516.8"
OLD_FNC = "https://federaciondecafeteros.org/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Septiembre-2026-1.xlsx"
NEW_FNC = "https://federaciondecafeteros.org/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Septiembre-2026.xlsx"


class PorkOriginalCellTests(unittest.TestCase):
    def test_only_affected_parser_versions_advance_for_retained_replay(self):
        self.assertIn("legacy-cell-review-v1", worker.parser_version("colombia-pork-pdf"))
        self.assertIn("nonflower-original-c49f-v1", worker.parser_version("international-usda-miami-flowers"))
        self.assertNotIn("legacy-cell-review-v1", worker.parser_version("colombia-agronet-cacao"))
        self.assertNotIn("nonflower-original-c49f-v1", worker.parser_version("international-usda-boston-flowers"))

    def test_native_duplicate_is_preserved_as_exact_legacy_locator_review(self):
        body = PORK.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), PORK_SHA)
        rows = colombia_sources.parse_pork(body)
        current = [r for r in rows if r["source_locator"] == CURRENT]
        reviews = [r for r in rows if r["source_locator"] == LEGACY]
        self.assertEqual(len(current), 1)
        self.assertEqual(len(reviews), 1)
        self.assertEqual((current[0]["market"], current[0]["date"], current[0]["price"]),
                         ("Caribe Norte", "2024-09-06", 9319.0))
        self.assertIsNone(reviews[0]["price"])
        self.assertEqual(reviews[0]["details"]["original_price"], "9.319")
        self.assertEqual(reviews[0]["details"]["duplicate_of"], CURRENT)
        self.assertEqual(reviews[0]["details"]["original_sha256"], PORK_SHA)
        self.assertFalse(any(r["source_locator"] == BARE for r in rows))

    def test_two_page4_national_cells_are_exact_original_reviews(self):
        cases = (
            ("b92bdc9ae80330879b2f3e7039dd408836e596cea6fd1fcf0a9cbbc9c5a12393",
             "2024-07-26", 11991, "11.991", "PDF page 1, current prices column 2, y 562.5"),
            ("174627feeefd054fae66748e0b73806bea3c9bce0994ae134d5a2750de16b474",
             "2024-06-28", 12188, "12.188", "PDF page 1, current prices column 2, y 565.5"),
        )
        old = "PDF page 4, Cerdo · canal caliente, y 468.0, market Colombia"
        for sha, day, price, printed, replacement in cases:
            with self.subTest(sha=sha):
                body = (Path(__file__).parent / "testdata" / (sha + ".pdf")).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
                rows = colombia_sources.parse_pork(body)
                review = next(r for r in rows if r["source_locator"] == old)
                current = next(r for r in rows if r["source_locator"] == replacement)
                self.assertEqual((review["date"],review["market"],review["unit"],review["price"]),
                                 (day,"Colombia","kg canal",None))
                self.assertEqual((current["date"],current["market"],current["unit"],current["price"]),
                                 (day,"Colombia","kg canal",price))
                self.assertEqual(review["details"]["original_price"], printed)
                self.assertEqual(review["details"]["duplicate_of"], replacement)
                self.assertEqual(review["details"]["original_sha256"], sha)


@unittest.skipUnless(os.environ.get("AGRO_SOURCE_RECOVERY_POSTGRES_TEST") == "1",
                     "Explicit opt-in for isolated PostgreSQL TEMP tables")
class SourceRecoveryPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='60s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint", "official_catalog_current"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
            self.assertEqual(self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                (table,)).fetchone(), ("t",))
        self.enterContext(patch("pipelines.ingestion.official_catalog.refresh_document", return_value=0))
        self.enterContext(patch("pipelines.ingestion.write_pacing.pause_between_batches"))
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def seed_complete_fnc_replacement(self, url, *, records):
        body = b"private FNC replacement original fixture for " + url.encode()
        did = hashlib.sha256(body).hexdigest()
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
               VALUES(%s,%s,'FNC',%s,
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 'original','2026-09',%s,%s)""",
            (did, "September 2026 FNC replacement", url, body,
             Jsonb({"ingestion_kind": "coffee", "retention": "permanent"})),
        )
        self.db.execute(
            "UPDATE ingestion_asset SET status='complete',document_id=%s,records=%s WHERE url=%s",
            (did, records, url),
        )
        return did

    def test_pork_old_locator_is_atomic_and_reviewed_without_removing_quote(self):
        body = PORK.read_bytes()
        did = hashlib.sha256(body).hexdigest()
        self.assertEqual(did, PORK_SHA)
        url = "https://porkcolombia.co/wp-content/uploads/2024/09/Semana36de2024.pdf"
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'Semana 36','Porkcolombia / FNP',%s,'application/pdf','original','2024-09',%s,%s)",
            (did, url, body, Jsonb({"ingestion_kind": "colombia-pork-pdf"})))
        self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status) "
                        "VALUES(%s,'colombia-pork-pdf',%s,'complete')", (url, did))
        rows = colombia_sources.parse_pork(body)
        clean_rows = [r for r in rows if r["source_locator"] != LEGACY]
        official_sources.publish_rows(self.db, clean_rows, did, "colombia-pork-pdf")
        self.db.execute(
            "INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,"
            "product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,"
            "period_start,price,min_price,max_price,source_page,details) "
            "SELECT document_id,%s,'legacy-pork-v1',quote_key,product_id,product_name,category,"
            "publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,"
            "max_price,3,details FROM official_price_quote WHERE document_id=%s AND source_locator=%s",
            (LEGACY, did, CURRENT))
        before = self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0]
        with self.assertRaisesRegex(ValueError, "omitted previously published source locators"):
            official_sources.publish_rows(self.db, clean_rows, did, "colombia-pork-pdf")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], before)
        official_sources.publish_rows(self.db, rows, did, "colombia-pork-pdf")
        self.assertEqual(self.db.execute(
            "SELECT price,market,source_page FROM official_price_quote "
            "WHERE document_id=%s AND source_locator=%s AND parser_version='legacy-pork-v1'",
            (did, LEGACY)).fetchone(), (9319, "Caribe Norte", 3))
        review = self.db.execute(
            "SELECT record->>'price',record->'details'->>'duplicate_of' "
            "FROM official_source_review WHERE document_id=%s AND source_locator=%s "
            "AND parser_version=%s", (did, LEGACY, worker.parser_version("colombia-pork-pdf"))).fetchone()
        self.assertEqual(review, (None, CURRENT))
        import re

        schema = (Path(__file__).parent / "schema.sql").read_text()
        view = re.search(r"CREATE OR REPLACE VIEW published_official_price AS[\s\S]*?;", schema).group(0)
        self.db.execute(view.replace("CREATE OR REPLACE VIEW", "CREATE TEMP VIEW", 1))
        # Remove only the current quote in this TEMP fixture. The old quote
        # must remain raw while its exact market-qualified review withdraws it.
        self.db.execute("DELETE FROM pg_temp.official_price_quote WHERE document_id=%s AND source_locator=%s", (did, CURRENT))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s AND source_locator=%s",
            (did, LEGACY)).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM published_official_price WHERE document_id=%s AND source_locator=%s",
            (did, LEGACY)).fetchone()[0], 0)

    def test_fnc_stale_404_retires_only_after_official_replacement_completed(self):
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,error) VALUES(%s,'coffee','failed',%s)",
            (OLD_FNC, "HTTPError: 404 Client Error"))
        links = [("Septiembre 2026", NEW_FNC),
                 ("Precio", "https://federaciondecafeteros.org/wp-content/uploads/2026/03/precio_cafe.pdf")]
        with patch.object(worker, "links", return_value=links):
            worker.discover_coffee(self.db)
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (OLD_FNC,)).fetchone(), ("failed",))
        self.seed_complete_fnc_replacement(NEW_FNC, records=1)
        with patch.object(worker, "links", return_value=links):
            worker.discover_coffee(self.db)
        status, error = self.db.execute("SELECT status,error FROM ingestion_asset WHERE url=%s", (OLD_FNC,)).fetchone()
        self.assertEqual(status, "review")
        self.assertIn(NEW_FNC, error)
        self.assertNotIn(OLD_FNC, [r[0] for r in queue_plan.backfill_candidates(self.db, 30)])
        self.assertNotIn(OLD_FNC, [r[0] for r in queue_plan.daily_candidates(self.db, worker.today())])
        unrelated = "https://federaciondecafeteros.org/wp-content/uploads/2026/09/unrelated-review.xlsx"
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,error,checked_at,processor_version) "
            "VALUES(%s,'coffee','review',NULL,now()-interval '31 days',%s)",
            (unrelated, worker.parser_version("coffee")))
        self.assertIn(unrelated, [r[0] for r in queue_plan.backfill_candidates(self.db, 30)])
        self.assertIn(unrelated, [r[0] for r in queue_plan.daily_candidates(self.db, worker.today())])

    def test_archived_fnc_404_retires_fetch_without_hiding_retained_quotes(self):
        import re
        from datetime import date
        from . import coffee_sources

        fixture = Path(__file__).parent / "testdata/86e6373117ea-retained-fnc-old.xlsx"
        body = fixture.read_bytes()
        old_did = hashlib.sha256(body).hexdigest()
        self.assertEqual(old_did, "86e6373117ea5147a69560f4fc3f3d57c30b1a9b9493bcdc10ae6c3dbe508386")
        old_rows = coffee_sources.publication_rows(
            coffee_sources.parse(body, OLD_FNC, "coffee", as_of=date(2026, 10, 2))
        )
        self.assertEqual(len(old_rows), 11551)
        selected = next(row for row in old_rows if row["source_locator"] ==
                        "3. Precio Ex_Dock Mensual!row 1370,col 5")
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'September 2026 FNC original',"
            "'FNC',%s,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',"
            "'original','2026-09',%s,%s)",
            (old_did, OLD_FNC, body, Jsonb({"ingestion_kind": "coffee"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,error,document_id,records,processor_version) "
            "VALUES(%s,'coffee','failed','HTTPError: 404 Client Error',%s,20219,%s)",
            (OLD_FNC, old_did, worker.parser_version("coffee")),
        )
        official_sources.publish_rows(self.db, [selected], old_did, "coffee")
        schema = (Path(__file__).parent / "schema.sql").read_text()
        view = re.search(r"CREATE OR REPLACE VIEW published_official_price AS[\s\S]*?;", schema).group(0)
        self.db.execute(view.replace("CREATE OR REPLACE VIEW", "CREATE TEMP VIEW", 1))
        def published():
            return self.db.execute(
                "SELECT source_locator,price FROM published_official_price WHERE document_id=%s",
                (old_did,),
            ).fetchall()
        before = published()
        self.assertEqual(len(before), 1)
        links = [("September 2026", NEW_FNC),
                 ("Precio", "https://federaciondecafeteros.org/wp-content/uploads/2026/03/precio_cafe.pdf")]
        with patch.object(worker, "links", return_value=links):
            worker.discover_coffee(self.db)
        self.assertEqual(self.db.execute(
            "SELECT status FROM ingestion_asset WHERE url=%s", (OLD_FNC,)
        ).fetchone(), ("failed",))
        self.seed_complete_fnc_replacement(NEW_FNC, records=20249)
        with patch.object(worker, "links", return_value=links):
            worker.discover_coffee(self.db)
        status, did, records, error = self.db.execute(
            "SELECT status,document_id,records,error FROM ingestion_asset WHERE url=%s", (OLD_FNC,)
        ).fetchone()
        self.assertEqual((status, did, records), ("archived", old_did, 20219))
        self.assertIn(NEW_FNC, error)
        self.assertIn("prior error: HTTPError: 404", error)
        self.assertEqual(published(), before)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (old_did,)
        ).fetchone(), (1,))
        self.assertNotIn(OLD_FNC, [r[0] for r in queue_plan.backfill_candidates(self.db, 30)])
        self.assertNotIn(OLD_FNC, [r[0] for r in queue_plan.daily_candidates(self.db, worker.today())])

    def test_two_legacy_page4_quotes_are_retained_but_duplicate_projection_is_reviewed(self):
        import re
        cases = (
            ("b92bdc9ae80330879b2f3e7039dd408836e596cea6fd1fcf0a9cbbc9c5a12393",
             "2024-07-26", 11991, "PDF page 1, current prices column 2, y 562.5"),
            ("174627feeefd054fae66748e0b73806bea3c9bce0994ae134d5a2750de16b474",
             "2024-06-28", 12188, "PDF page 1, current prices column 2, y 565.5"),
        )
        legacy = "PDF page 4, Cerdo · canal caliente, y 468.0, market Colombia"
        schema = (Path(__file__).parent / "schema.sql").read_text()
        view = re.search(r"CREATE OR REPLACE VIEW published_official_price AS[\s\S]*?;", schema).group(0)
        self.db.execute(view.replace("CREATE OR REPLACE VIEW", "CREATE TEMP VIEW", 1))
        for sha, day, price, current in cases:
            with self.subTest(sha=sha):
                body = (Path(__file__).parent / "testdata" / (sha + ".pdf")).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
                url = "https://porkcolombia.co/wp-content/uploads/2024/07/" + (
                    "Semana30de2024.pdf" if day == "2024-07-26" else "Semana26de2024.pdf")
                self.db.execute(
                    "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
                    "reference_period,content,metadata) VALUES(%s,'Porkcolombia weekly',"
                    "'Porkcolombia / FNP',%s,'application/pdf','original',%s,%s,%s)",
                    (sha,url,day[:7],body,Jsonb({"ingestion_kind":"colombia-pork-pdf"})),
                )
                self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status) "
                                "VALUES(%s,'colombia-pork-pdf',%s,'complete')",(url,sha))
                rows = colombia_sources.parse_pork(body)
                without_review = [r for r in rows if r["source_locator"] != legacy]
                official_sources.publish_rows(self.db, without_review, sha, "colombia-pork-pdf")
                self.db.execute(
                    "INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,"
                    "product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,"
                    "period_start,price,min_price,max_price,source_page,details) "
                    "SELECT document_id,%s,'legacy-pork-v1',quote_key,product_id,product_name,category,"
                    "publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,"
                    "max_price,4,details FROM official_price_quote WHERE document_id=%s AND source_locator=%s",
                    (legacy,sha,current),
                )
                with self.assertRaisesRegex(ValueError,"omitted previously published source locators"):
                    official_sources.publish_rows(self.db, without_review, sha, "colombia-pork-pdf")
                official_sources.publish_rows(self.db, rows, sha, "colombia-pork-pdf")
                self.assertEqual(self.db.execute(
                    "SELECT price,market,source_page FROM official_price_quote WHERE document_id=%s "
                    "AND source_locator=%s AND parser_version='legacy-pork-v1'",(sha,legacy)
                ).fetchone(),(price,"Colombia",4))
                self.assertEqual(self.db.execute(
                    "SELECT record->'details'->>'duplicate_of' FROM official_source_review "
                    "WHERE document_id=%s AND source_locator=%s AND parser_version=%s",
                    (sha,legacy,worker.parser_version("colombia-pork-pdf"))
                ).fetchone(),(current,))
                self.assertEqual(self.db.execute(
                    "SELECT source_locator FROM published_official_price WHERE document_id=%s "
                    "AND quote_key=(SELECT quote_key FROM official_price_quote WHERE document_id=%s "
                    "AND source_locator=%s AND parser_version='legacy-pork-v1') AND observed_on=%s",
                    (sha,sha,legacy,day)
                ).fetchone(),(current,))

    def test_ornamental_shipment_original_publishes_only_an_immutable_review(self):
        sha = "92e10731554bdff477913b2e961ca3237d1fda2f1e4b54f87117d93bd01e2727"
        body = (Path(__file__).parent / "testdata" / (sha + "-MH_FV221.TXT")).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
        url = ("https://esmis.nal.usda.gov/sites/default/release-files/"
               "4x51hj05x/xg94jm791/bv73cx61d/MH_FV221.TXT")
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'USDA native shipment original',"
            "'USDA',%s,'text/plain','original','2021-08',%s,%s)",
            (sha, url, body, Jsonb({"ingestion_kind": "international-usda-miami-flowers"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) "
            "VALUES(%s,'international-usda-miami-flowers',%s,'failed')", (url, sha)
        )
        rows = international_sources.parse(body, url, "international-usda-miami-flowers")
        self.assertEqual(len(rows), 1)
        self.assertEqual(official_sources.publish_rows(
            self.db, rows, sha, "international-usda-miami-flowers"), 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (sha,)
        ).fetchone(), (0,))
        review = self.db.execute(
            "SELECT source_locator,record->'details'->>'native_report_code' "
            "FROM official_source_review WHERE document_id=%s AND parser_version=%s",
            (sha, worker.parser_version("international-usda-miami-flowers")),
        ).fetchone()
        self.assertEqual(review, ("TXT report MH_FV280, non-flower native header", "MH_FV280"))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (sha, worker.parser_version("international-usda-miami-flowers")),
        ).fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
