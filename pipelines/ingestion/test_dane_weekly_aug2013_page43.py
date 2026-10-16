"""Source-bound period separation for the August 2013 weekly table/article page."""

import hashlib
import io
import os
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

import pdfplumber
import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly as weekly
from . import queue_plan, worker


SOURCE = Path(__file__).parent / "testdata/weekly_aug2013_page43/5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d.pdf"


class ExactAugust2013Page43Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SOURCE.read_bytes()
        cls.sha = hashlib.sha256(cls.body).hexdigest()
        if cls.sha != weekly.AUG2013_PAGE43_SHA:
            raise AssertionError("August 2013 source fixture SHA changed")
        with pdfplumber.open(io.BytesIO(cls.body)) as pdf:
            cls.page_count = len(pdf.pages)
            page = pdf.pages[42]
            cls.page_height = page.height
            cls.words = page.extract_words(extra_attrs=["fontname", "size"], return_chars=True)
            starts = sorted({
                word["top"] for word in cls.words
                if word["text"] == "Cuadro" and word["x0"] < page.width * 0.20
            })
            if len(starts) != 1:
                raise AssertionError("Expected one printed Cuadro on page 43")
            cls.table_text = page.crop((0, max(0, starts[0] - 1), page.width, page.height)).extract_text() or ""

    def test_full_native_cohort_and_four_visual_oracle_rows(self):
        rows = weekly.parse_pdf(self.body, weekly.AUG2013_PAGE43_URL)
        self.assertEqual((len(rows), self.page_count), (4297, 44))
        self.assertEqual(
            {(row["period_start"], row["date"]) for row in rows},
            {("2013-08-17", "2013-08-23")},
        )
        page43 = [row for row in rows if row["source_page"] == 43]
        self.assertEqual(len(page43), 38)
        self.assertEqual((sum(row["price"] is not None for row in rows),
                          sum(row["price"] is None for row in rows)), (4163, 134))
        visual_oracle = {
            ("Salsa de tomate doy pack", "Popayán (Cauca)"): 11519,
            ("Sardinas en lata", "Armenia, Mercar"): 4965,
            ("Sopa de pollo (caja)", "Bogotá, D. C., Corabastos"): 31695,
            ("Vinagre", "Cúcuta, Cenabastos"): 1417,
        }
        for (product, market), price in visual_oracle.items():
            with self.subTest(product=product, market=market):
                row = next(
                    row for row in page43
                    if (row["product_name"], row["market"]) == (product, market)
                )
                self.assertEqual((row["min"], row["max"]), (price, price))
                if product == "Vinagre":
                    self.assertEqual((row["price"], row["unit"]), (price, "kg"))
                    self.assertEqual(
                        row["details"]["exact_unit_evidence"],
                        "Exact page-43 Cuadro 8 header: Pesos por kilogramo",
                    )
                    self.assertEqual(row["details"]["literal_unit_heading"], "Pesos por kilogramo")
                else:
                    self.assertEqual(row["price"], price)
        vinegar = [row for row in page43 if row["product_name"] == "Vinagre"]
        self.assertEqual((len(vinegar), {row["unit"] for row in vinegar}), (8, {"kg"}))

    def test_exact_source_helper_requires_weekly_grid_and_article_structure(self):
        self.assertEqual(
            weekly._aug2013_page43_table_period_override(
                weekly.AUG2013_PAGE43_URL, self.sha, 43, 1, self.table_text, self.words
            ),
            [weekly.AUG2013_PAGE43_HEADER],
        )
        with self.assertRaisesRegex(ValueError, "caption changed"):
            weekly._aug2013_page43_table_period_override(
                weekly.AUG2013_PAGE43_URL, self.sha, 43, 1,
                self.table_text.replace("Cuadro 8.", "Cuadro 9.", 1), self.words,
            )
        words_without_trends = [
            word for word in self.words
            if not word["text"].casefold().startswith("tendencias")
        ]
        with self.assertRaisesRegex(ValueError, "anchors changed"):
            weekly._aug2013_page43_table_period_override(
                weekly.AUG2013_PAGE43_URL, self.sha, 43, 1, self.table_text, words_without_trends
            )
        altered_unit = [dict(word) for word in self.words]
        for word in altered_unit:
            if word["text"].casefold() in {"pesos", "kilogramo"}:
                word["text"] = "Unidades"
        with self.assertRaisesRegex(ValueError, "unit header changed"):
            weekly._aug2013_page43_table_period_override(
                weekly.AUG2013_PAGE43_URL, self.sha, 43, 1, self.table_text, altered_unit
            )

    def test_exact_source_boundary_excludes_the_separate_historical_article(self):
        from .weekly_boundary_review import reviewed_article_bottom

        top = min(word["top"] for word in self.words if word["text"] == "Cuadro")
        cutoff = reviewed_article_bottom(
            weekly.AUG2013_PAGE43_URL, self.sha, 43, self.words,
            max(0, top - 1), self.page_height,
        )
        self.assertLess(cutoff, self.page_height)
        self.assertGreater(cutoff, top)
        with pdfplumber.open(io.BytesIO(self.body)) as pdf:
            grid_only = pdf.pages[42].crop((0, max(0, top - 1), pdf.pages[42].width, cutoff)).extract_text() or ""
        self.assertIn("Tendencias:", grid_only)
        self.assertNotIn("Precios de la panela", grid_only)
        self.assertEqual(
            reviewed_article_bottom(weekly.AUG2013_PAGE43_URL + "?alias", self.sha, 43,
                                    self.words, max(0, top - 1), self.page_height),
            self.page_height,
        )

    def test_forged_source_hash_and_neighbor_url_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "weekly PDF bytes changed"):
            weekly.parse_pdf(self.body + b"forged", weekly.AUG2013_PAGE43_URL)
        with self.assertRaisesRegex(ValueError, "page 43 has conflicting printed periods"):
            weekly.parse_pdf(self.body, weekly.AUG2013_PAGE43_URL + "?alias")
        with self.assertRaisesRegex(ValueError, "source bytes changed"):
            weekly._aug2013_page43_table_period_override(
                weekly.AUG2013_PAGE43_URL, "0" * 64, 43, 1, self.table_text, self.words
            )
        self.assertIsNone(weekly._aug2013_page43_table_period_override(
            weekly.AUG2013_PAGE43_URL + "?alias", self.sha, 43, 1, self.table_text, self.words
        ))

    def test_queue_registers_only_the_exact_revision_and_release_module(self):
        expected = worker.parser_version("dane-weekly-pdf", weekly.AUG2013_PAGE43_URL)
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", weekly.AUG2013_PAGE43_URL), expected)
        self.assertNotEqual(
            worker.asset_parser_version("dane-weekly-pdf", weekly.AUG2013_PAGE43_URL + "?alias"),
            expected,
        )
        self.assertEqual(
            queue_plan.expected_versions().obj["url:" + weekly.AUG2013_PAGE43_URL], expected
        )


@unittest.skipUnless(os.environ.get("AGRO_AUG2013_PRIVATE_WORKER_PG_DSN"),
                     "Explicit owned August 2013 full-schema PostgreSQL DSN required")
class August2013WorkerLifecyclePG(unittest.TestCase):
    """The retained original traverses the real worker and official publisher."""

    @classmethod
    def setUpClass(cls):
        cls.url = weekly.AUG2013_PAGE43_URL
        cls.kind = "dane-weekly-pdf"
        cls.source_id = weekly.AUG2013_PAGE43_SHA
        cls.day = date(2013, 8, 23)
        cls.body = SOURCE.read_bytes()
        cls.dsn = os.environ["AGRO_AUG2013_PRIVATE_WORKER_PG_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-aug2013-worker-")
                or not cls.db.info.dbname.startswith("agro_aug2013_worker_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only an owned local August 2013 full-schema PostgreSQL fixture is allowed")
        cls.db.execute("SET statement_timeout='180s'")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_worker_replays_exact_retained_pdf_and_is_idempotent(self):
        db, url, kind, did, day, body = (
            self.db, self.url, self.kind, self.source_id, self.day, self.body
        )
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM source_document WHERE id=%s", (did,)
        ).fetchone()[0], 0)
        metadata = {
            "retention": "permanent", "ingestion_kind": kind,
            "original_filename": "Semana_20ago_23ago_2013.pdf",
        }
        db.execute(
            "INSERT INTO source_document "
            "(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,%s,%s,'application/pdf','original','2013-08-23',44,%s,%s)",
            (did, "DANE · SIPSA - Semana_20ago_23ago_2013.pdf", "DANE · SIPSA",
             url, body, Jsonb(metadata)),
        )
        base = worker.parser_version(kind)
        revision = worker.asset_parser_version(kind, url)
        self.assertNotEqual(base, revision)
        db.execute(
            "INSERT INTO ingestion_asset "
            "(url,kind,document_id,observed_on,status,processor_version,records,error,checked_at) "
            "VALUES(%s,%s,%s,%s,'failed',%s,0,%s,now()-interval '7 hours')",
            (url, kind, did, day, base, "ValueError: Weekly PDF page 43 has conflicting printed periods"),
        )
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, kind))
        queued = queue_plan.backfill_candidates(db, 1000)
        self.assertIn((url, kind, day), queued)

        def source_snapshot():
            return db.execute(
                "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
                "page_count,content,metadata,xmin::text FROM source_document WHERE id=%s",
                (did,),
            ).fetchone()

        original = source_snapshot()
        fetch_calls = []

        def no_fetch(_db, fetch_url, force=False, *, require_bytes=False):
            fetch_calls.append((fetch_url, bool(force), bool(require_bytes)))
            raise AssertionError(f"Pinned retained Aug 2013 source must not use HTTP: {fetch_url!r}")

        from . import blob_archive

        def exact_blob(digest, data, suffix, media_type):
            self.assertEqual((digest, data, suffix, media_type),
                             (did, body, ".pdf", "application/pdf"))

        state = None
        checkpoint = None
        with patch.object(worker, "fetch_asset", side_effect=no_fetch), \
                patch.object(blob_archive, "retain_original_blob", side_effect=exact_blob):
            for pass_number in (1, 2):
                if pass_number == 2:
                    # Recreate the precise stale legacy queue state in this
                    # disposable fixture to prove append-only publication is
                    # idempotent while consuming only its pinned original.
                    db.execute(
                        "UPDATE ingestion_asset SET status='failed',processor_version=%s,"
                        "records=0,error=%s,checked_at=now()-interval '7 hours' WHERE url=%s",
                        (base, "ValueError: Weekly PDF page 43 has conflicting printed periods", url),
                    )
                    self.assertIn((url, kind, day), queue_plan.backfill_candidates(db, 1000))
                    self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, kind))
                self.assertEqual(worker.process_asset(db, url, kind, day), 4163)
                self.assertEqual(source_snapshot(), original)
                asset = db.execute(
                    "SELECT status,records,error,processor_version,document_id,observed_on "
                    "FROM ingestion_asset WHERE url=%s", (url,),
                ).fetchone()
                self.assertEqual(asset, ("complete", 4163, None, revision, did, day))
                self.assertNotIn((url, kind, day), queue_plan.backfill_candidates(db, 1000))
                prices = db.execute(
                    "SELECT count(*),count(DISTINCT source_locator) FROM official_price_quote "
                    "WHERE document_id=%s AND parser_version=%s", (did, revision),
                ).fetchone()
                reviews = db.execute(
                    "SELECT count(*),count(DISTINCT source_locator) FROM official_source_review "
                    "WHERE document_id=%s AND parser_version=%s", (did, revision),
                ).fetchone()
                self.assertEqual(prices, (4163, 4163))
                self.assertEqual(reviews, (134, 134))
                self.assertTrue(all(row[0] for row in db.execute(
                    "SELECT reason FROM official_source_review WHERE document_id=%s AND parser_version=%s",
                    (did, revision),
                ).fetchall()))
                checkpoints = db.execute(
                    "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                    "WHERE document_id=%s AND step='official:complete' ORDER BY processor_version",
                    (did,),
                ).fetchall()
                self.assertEqual(len(checkpoints), 1)
                self.assertEqual(checkpoints[0][:3], (revision, "official:complete", 4163))
                if pass_number == 1:
                    quote_state = db.execute(
                        "SELECT source_locator,xmin::text FROM official_price_quote "
                        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                        (did, revision),
                    ).fetchall()
                    review_state = db.execute(
                        "SELECT source_locator,xmin::text FROM official_source_review "
                        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                        (did, revision),
                    ).fetchall()
                    state, checkpoint = (quote_state, review_state), checkpoints
                else:
                    self.assertEqual(db.execute(
                        "SELECT source_locator,xmin::text FROM official_price_quote "
                        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                        (did, revision),
                    ).fetchall(), state[0])
                    self.assertEqual(db.execute(
                        "SELECT source_locator,xmin::text FROM official_source_review "
                        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                        (did, revision),
                    ).fetchall(), state[1])
                    self.assertEqual(checkpoints, checkpoint)
                self.assertEqual(source_snapshot(), original)
        self.assertEqual(fetch_calls, [])
        refresh_calls = []

        def exact_normal_refresh(_db, fetch_url, force=False, *, require_bytes=False):
            self.assertEqual(fetch_url, url)
            refresh_calls.append((fetch_url, bool(force), bool(require_bytes)))
            return body

        with patch.object(worker, "fetch_asset", side_effect=exact_normal_refresh), \
                patch.object(blob_archive, "retain_original_blob", side_effect=exact_blob):
            self.assertEqual(worker.process_asset(db, url, kind, day), 4163)
        self.assertEqual(len(refresh_calls), 1)
        self.assertEqual(source_snapshot(), original)
        refreshed_asset = db.execute(
            "SELECT status,records,error,processor_version,document_id,observed_on "
            "FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()
        self.assertEqual(refreshed_asset, ("complete", 4163, None, revision, did, day))
        self.assertNotIn((url, kind, day), queue_plan.backfill_candidates(db, 1000))
        self.assertEqual(db.execute(
            "SELECT source_locator,xmin::text FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (did, revision),
        ).fetchall(), state[0])
        self.assertEqual(db.execute(
            "SELECT source_locator,xmin::text FROM official_source_review "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (did, revision),
        ).fetchall(), state[1])
        self.assertEqual(db.execute(
            "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
            "WHERE document_id=%s AND step='official:complete' ORDER BY processor_version",
            (did,),
        ).fetchall(), checkpoint)




if __name__ == "__main__":
    unittest.main(verbosity=2)
