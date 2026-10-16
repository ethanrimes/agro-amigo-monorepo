"""Selection behavior under terminal rows and transient database timeouts."""

import unittest
import getpass
import hashlib
import random
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import city_product_backfill as backfill
from . import city_reports
from .city_product_corrections import REGIONAL_COLUMNS, verified_corrections

HERE = Path(__file__).parent
AGUACATE_DID = "d13079d8c0d0d39a2ddd51e84a0a966575ca8a66f1e9d144706261e5d2a1f93b"


class PageDatabase:
    def __init__(self, rows, *, canceled_sizes=()):
        self.rows = rows
        self.canceled_sizes = set(canceled_sizes)
        self.attempts = []

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params):
        if "set_config" in sql:
            return self
        after, size, _, _, _ = params
        self.attempts.append((after, size))
        if size in self.canceled_sizes:
            self.canceled_sizes.remove(size)
            raise psycopg.errors.QueryCanceled("statement timeout")
        self.result = [row for row in self.rows if row[0] > after][:size]
        return self

    def fetchall(self):
        return self.result


class CityProductSelectionTests(unittest.TestCase):
    def test_priority_ids_are_only_unambiguous_reviewed_food_whole_labels(self):
        self.assertIn("aguacatecomun", backfill.COMPACT_FOOD_IDS)
        self.assertIn("papacriollasucia", backfill.COMPACT_FOOD_IDS)
        self.assertNotIn("wuxaltapanegra161612", backfill.COMPACT_FOOD_IDS)
        self.assertNotIn("limon-tahiti", backfill.COMPACT_FOOD_IDS)
        self.assertEqual(len(backfill.COMPACT_FOOD_IDS), len(set(backfill.COMPACT_FOOD_IDS)))
        self.assertEqual(backfill.PRIORITY_LIMIT, 16)
        self.assertGreaterEqual(backfill.MAX_PER_RUN - backfill.PRIORITY_LIMIT, backfill.MIN_FIFO)
        self.assertEqual(backfill._priority_ids_from_products([
            ("bagrerayadoentero-congelado", "Bagrerayadoentero congelado"),
            ("aguacatecomun", "Aguacatecomún"),
            ("aguacate-comun", "Aguacate común"),
            ("wuxaltapanegra161612", "Wuxal Tapa Negra 16-16-12"),
            ("papa-r-12-roja", "Papa R-12 roja"),
            ("unrelated", "Aguacatecomún"),
        ]), ["aguacatecomun", "bagrerayadoentero-congelado"])

    def test_sincelejo_original_requires_exact_native_spacing_before_any_priority_correction(self):
        body = (HERE / "testdata/city_aguacate_sincelejo_20240703.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), AGUACATE_DID)
        with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
            old = list(city_reports.parse_city_pdf(body))
        originals = [dict(zip(REGIONAL_COLUMNS, row)) for row in old]
        found = verified_corrections(body, AGUACATE_DID,
            "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-3jul2024.zip", originals)
        target = [item for item in found if item["source_locator"] == "PDF page 1,table 1,row 36,round 1"]
        self.assertEqual(len(target), 1)
        item = target[0]
        self.assertEqual((item["old_product_id"], item["old_product_name"]), ("aguacatecomun", "Aguacatecomún"))
        self.assertEqual((item["corrected_product_id"], item["corrected_product_name"]), ("aguacate-comun", "Aguacate común"))
        source = next(row for row in originals if row["source_locator"] == item["source_locator"])
        self.assertEqual((source["observed_on"].isoformat(), source["market_name"], source["presentation"], source["quantity"],
                          source["source_unit"], source["min_price"], source["max_price"]),
                         ("2024-07-03", "Sincelejo, Nuevo Mercado", "Kilogramo", 1, "Kilogramo", 4500, 5000))
        self.assertEqual(item["source_sha256"], AGUACATE_DID)

    def test_page_query_limits_source_before_eligibility_checks(self):
        sql, params = backfill.candidate_page_query("abc", 64)
        self.assertIn("WITH page AS MATERIALIZED", sql)
        self.assertIn("d.id>%s", sql)
        self.assertIn("ORDER BY d.id LIMIT %s", sql)
        self.assertIn("FROM page p ORDER BY p.id", sql)
        self.assertEqual(params[:2], ("abc", 64))

    def test_keyset_crosses_empty_pages_without_duplicates_or_skips(self):
        rows = [(f"{i:064x}", f"url-{i}", i in (3, 67, 130)) for i in range(140)]
        db = PageDatabase(rows)
        selected, error = backfill.select_candidates(db, 3)
        self.assertIsNone(error)
        self.assertEqual([int(did, 16) for did, _ in selected], [3, 67, 130])
        self.assertEqual([after for after, _ in db.attempts], ["", rows[63][0], rows[127][0]])

    def test_canceled_page_retries_same_cursor_at_smaller_size(self):
        rows = [(f"{i:064x}", f"url-{i}", i in (0, 33)) for i in range(70)]
        db = PageDatabase(rows, canceled_sizes=(64,))
        selected, error = backfill.select_candidates(db, 2)
        self.assertIsNone(error)
        self.assertEqual([int(did, 16) for did, _ in selected], [0, 33])
        self.assertEqual(db.attempts[:2], [("", 64), ("", 32)])

    def test_single_row_timeout_returns_prior_candidates(self):
        rows = [(f"{i:064x}", f"url-{i}", i in (0, 65)) for i in range(70)]

        class StalledAfterFirstPage(PageDatabase):
            def execute(self, sql, params):
                if "set_config" not in sql and params[0]:
                    self.attempts.append((params[0], params[1]))
                    raise psycopg.errors.QueryCanceled("statement timeout")
                return super().execute(sql, params)

        db = StalledAfterFirstPage(rows)
        selected, error = backfill.select_candidates(db, 2)
        self.assertEqual(error, "QueryCanceled")
        self.assertEqual(selected, [(rows[0][0], rows[0][1])])
        self.assertEqual([size for _, size in db.attempts], [64, 64, 32, 16, 8, 4, 2, 1])


class CityProductPriorityPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-city-priority-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
                           check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                           check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}", autocommit=True)
            cls.db.execute("CREATE TABLE product(id text PRIMARY KEY,name text NOT NULL)")
            cls.db.execute("CREATE TABLE source_document(id text PRIMARY KEY,source_url text,metadata jsonb)")
            cls.db.execute("CREATE INDEX source_document_city_pdf_scan ON source_document(id) WHERE metadata->>'ingestion_kind'='city-pdf'")
            cls.db.execute("CREATE TABLE regional_price(document_id text,product_id text,source_locator text,PRIMARY KEY(document_id,source_locator))")
            cls.db.execute("CREATE INDEX regional_price_product_id ON regional_price(product_id,document_id)")
            cls.db.execute("CREATE TABLE city_product_scan(document_id text,scan_version text,status text,scanned_at timestamptz)")
            cls.db.execute("CREATE INDEX city_product_scan_terminal ON city_product_scan(document_id,scan_version) WHERE status IN ('complete','review')")
            cls.db.execute("CREATE INDEX city_product_scan_retry_recent ON city_product_scan(document_id,scan_version,scanned_at DESC) WHERE status='retry'")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute("INSERT INTO product VALUES('aguacatecomun','Aguacatecomún'),('bagrerayadoentero-congelado','Bagrerayadoentero congelado'),('wuxaltapanegra161612','Wuxal Tapa Negra 16-16-12')")
        for i in range(200):
            did = f"{i:064x}"
            self.db.execute("INSERT INTO source_document VALUES(%s,%s,'{\"ingestion_kind\":\"city-pdf\"}')", (did, f"url-{i}"))
            self.db.execute("INSERT INTO regional_price VALUES(%s,'ordinary',%s)", (did, f"row-{i}"))
        for did, product_id, kind in (
            ("a" * 64, "bagrerayadoentero-congelado", "city-pdf"),
            (AGUACATE_DID, "aguacatecomun", "city-pdf"),
            ("e" * 64, "aguacatecomun", "city-pdf"),
            ("f" * 64, "aguacatecomun", "city-pdf"),
            ("b" * 64, "wuxaltapanegra161612", "city-pdf"),
            ("c" * 64, "aguacatecomun", "other"),
        ):
            self.db.execute("INSERT INTO source_document VALUES(%s,%s,%s)", (did, "url-" + did, '{"ingestion_kind":"'+kind+'"}'))
            self.db.execute("INSERT INTO regional_price VALUES(%s,%s,'row-1')", (did, product_id))
        self.db.execute("INSERT INTO city_product_scan VALUES(%s,%s,'review',now()),(%s,%s,'retry',now())",
                        ("e" * 64, backfill.VERSION, "f" * 64, backfill.VERSION))

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def test_priority_late_source_keeps_fifo_and_eligibility(self):
        priority, error = backfill.select_priority_candidates(self.db, backfill.PRIORITY_LIMIT)
        self.assertIsNone(error)
        self.assertEqual(priority, [("a" * 64, "url-" + "a" * 64),
                                    (AGUACATE_DID, "url-" + AGUACATE_DID)])
        selected, error = backfill.select_candidates(self.db, backfill.MAX_PER_RUN)
        self.assertIsNone(error)
        self.assertEqual(selected[:2], [("a" * 64, "url-" + "a" * 64),
                                        (AGUACATE_DID, "url-" + AGUACATE_DID)])
        self.assertEqual([did for did, _ in selected[2:]],
                         [f"{i:064x}" for i in range(200)] + ["b" * 64])
        self.assertEqual(len({did for did, _ in selected}), len(selected))
        self.assertGreaterEqual(len(selected)-2, backfill.MIN_FIFO)

    def test_priority_query_preserves_scan_states_with_large_unrelated_city_tail(self):
        # Exercise the maintained query builder through the production
        # selection function.  The unrelated source tail is deliberately
        # larger than the matching product set; it must not alter row identity,
        # scan-version semantics, or deterministic document ordering.
        self.db.execute("""INSERT INTO source_document
            SELECT 'noise-'||g::text,'noise-url-'||g::text,
                   '{\"ingestion_kind\":\"city-pdf\"}'::jsonb
            FROM generate_series(1,5000) AS g""")
        selected_ids = ["1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64]
        kinds = ["city-pdf", "city-pdf", "city-pdf", "city-zip", "city-pdf"]
        self.db.cursor().executemany(
            "INSERT INTO source_document VALUES(%s,%s,%s)",
            [(did, "priority-url-" + did, '{"ingestion_kind":"' + kind + '"}')
             for did, kind in zip(selected_ids, kinds)],
        )
        self.db.cursor().executemany(
            "INSERT INTO regional_price VALUES(%s,'aguacatecomun','candidate-row-'||%s)",
            [(did, did) for did in selected_ids],
        )
        self.db.cursor().executemany(
            "INSERT INTO city_product_scan VALUES(%s,%s,%s,now()-%s*interval '1 second')",
            [
                (selected_ids[0], backfill.VERSION, "retry", 7200),
                (selected_ids[1], backfill.VERSION + ":old", "complete", 0),
                (selected_ids[2], backfill.VERSION, "failed", 0),
                (selected_ids[4], backfill.VERSION, "complete", 0),
            ],
        )

        actual, error = backfill.select_priority_candidates(self.db, backfill.PRIORITY_LIMIT)
        self.assertIsNone(error)
        expected = sorted(
            [("a" * 64, "url-" + "a" * 64),
             (AGUACATE_DID, "url-" + AGUACATE_DID)] +
            [(did, "priority-url-" + did) for did in selected_ids[:3]],
            key=lambda row: row[0],
        )
        self.assertEqual(actual, expected)
        self.assertNotIn(selected_ids[3], [did for did, _ in actual], "non-city source must stay excluded")
        self.assertNotIn(selected_ids[4], [did for did, _ in actual], "current terminal source must stay excluded")

    def test_priority_error_falls_back_to_fifo(self):
        with patch.object(backfill, "select_priority_candidates", return_value=([], "priority:QueryCanceled")):
            selected, error = backfill.select_candidates(self.db, backfill.MAX_PER_RUN)
        self.assertEqual(error, "priority:QueryCanceled")
        self.assertEqual([did for did, _ in selected],
                         [f"{i:064x}" for i in range(200)] + ["a" * 64, "b" * 64, AGUACATE_DID])

    def test_metadata_cap_uses_exact_compact_id_fallback(self):
        self.db.execute("INSERT INTO product SELECT 'zzz'||g,'Unknown'||g FROM generate_series(1,%s) g", (backfill.MAX_PRODUCT_METADATA + 1,))
        priority, error = backfill.select_priority_candidates(self.db, backfill.PRIORITY_LIMIT)
        self.assertIsNone(error)
        self.assertEqual(priority, [(AGUACATE_DID, "url-" + AGUACATE_DID)])


if __name__ == "__main__":
    unittest.main()
