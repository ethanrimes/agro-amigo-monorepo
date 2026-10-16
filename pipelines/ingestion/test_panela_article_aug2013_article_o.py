from __future__ import annotations

import copy
import hashlib
from io import BytesIO
import json
import unittest
from pathlib import Path

import pdfplumber

from pipelines.ingestion import panela_article_aug2013_exact as adapter


PACKET = Path(__file__).resolve().parent / "testdata" / "weekly_aug2013_panela_article"
PDF = PACKET / "original.pdf"
ORACLE = PACKET / "visual_oracle.json"


def expected_cells(oracle: dict) -> list[dict]:
    cells = []
    for table in oracle["tables"]:
        for row_no, (market, prices) in enumerate(table["rows"], 1):
            for col_no, (price, (start, end)) in enumerate(zip(prices, oracle["weeks"]), 1):
                cells.append({
                    "source_sha256": oracle["source_sha256"],
                    "source_url": oracle["source_url"],
                    "source_page": table["page"],
                    "source_table": table["table"],
                    "source_row": row_no,
                    "source_column": col_no,
                    "source_locator": (
                        f"PDF page {table['page']}, Tabla {table['table']}, "
                        f"row {row_no}, week {col_no}"
                    ),
                    "series": "panela_article_single_price",
                    "product_literal": table["product"],
                    "market_literal": market,
                    "period_start": start,
                    "period_end": end,
                    "unit_literal": oracle["unit_literal"],
                    "currency": "COP",
                    "price_literal": f"{price // 1000}.{price % 1000:03d}",
                    "price_cop_per_kg": price,
                })
    return cells


class ExactArticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        cls.oracle = json.loads(ORACLE.read_text())
        manifest = json.loads((PACKET / "fixture_manifest.json").read_text())
        for name, facts in manifest.items():
            self_path = PACKET / name
            if hashlib.sha256(self_path.read_bytes()).hexdigest() != facts["sha256"]:
                raise AssertionError(f"maintained fixture hash mismatch: {name}")
        cls.cells = adapter.extract(cls.body)

    def test_exact_sixty_cells_match_visual_oracle(self):
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), self.oracle["source_sha256"])
        self.assertEqual(self.oracle["source_url"], adapter.SOURCE_URL)
        self.assertEqual(self.cells, expected_cells(self.oracle))
        self.assertEqual([sum(r["source_table"] == n for r in self.cells) for n in (1, 2, 3)],
                         [25, 30, 5])
        self.assertEqual(len({r["source_locator"] for r in self.cells}), 60)
        self.assertEqual({r["series"] for r in self.cells}, {"panela_article_single_price"})

    def test_wrong_source_url_or_body_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Exact Aug 2013"):
            adapter.extract(self.body, "https://example.invalid/not-the-source.pdf")
        with self.assertRaisesRegex(ValueError, "Exact Aug 2013"):
            adapter.extract(self.body + b" ")

    def test_title_period_market_and_month_header_guards(self):
        with pdfplumber.open(BytesIO(self.body)) as pdf:
            words43 = pdf.pages[42].extract_words()
            words44 = pdf.pages[43].extract_words()
        table = adapter.TABLES[0]
        cases = [
            ("Tabla", table.title_y, "TablaX"),
            ("kilo", table.title_y, "litro"),
            ("23", table.period_y, "24"),
            ("Mercados", table.markets_y, "Mercado"),
            ("Julio", table.month_y, "Junio"),
        ]
        for token, y, replacement in cases:
            with self.subTest(token=token):
                words = copy.deepcopy(words43)
                target = next(w for w in words if w["text"] == token
                              and abs(w["top"] - y) < 0.5)
                target["text"] = replacement
                with self.assertRaises(ValueError):
                    adapter._header(words, table)

    def test_week_header_and_price_geometry_guards(self):
        with pdfplumber.open(BytesIO(self.body)) as pdf:
            words = pdf.pages[42].extract_words()
        words = copy.deepcopy(words)
        # The date token in the first week column is physically in that column.
        first_week = next(w for w in words if w["text"] == "20" and 650 < w["top"] < 674)
        first_week["text"] = "21"
        with self.assertRaisesRegex(ValueError, "week columns"):
            adapter._header(words, adapter.TABLES[0])

        with pdfplumber.open(BytesIO(self.body)) as pdf:
            pdf_words = copy.deepcopy(pdf.pages[42].extract_words())
        price = next(w for w in pdf_words if w["text"] == "1.450" and abs(w["top"] - 684.0) < .35)
        price["x0"] += 4
        with self.assertRaisesRegex(ValueError, "column moved"):
            adapter._table_rows(pdf_words, adapter.TABLES[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)


"""Private staged-N owned-PG qualification for the Aug 2013 article revision."""

import hashlib
import json
import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from pipelines.ingestion import dane_weekly, official_sources, retained_pdf_upgrade, worker, write_pacing
from pipelines.ingestion.panela_article_aug2013_official import (
    ARTICLE_BASIS, ARTICLE_SERIES, ARTICLE_STATISTIC, SOURCE_SHA, SOURCE_URL, official_rows,
)
from pipelines.ingestion.panela_article_aug2013_exact import extract
from pipelines.ingestion.test_input_pdf_v17_role import install


HERE = Path(__file__).resolve().parent
PACKET = HERE / "testdata" / "weekly_aug2013_panela_article"
PDF = PACKET / "original.pdf"
ORACLE_PATH = PACKET / "visual_oracle.json"
NATIVE = PACKET / "m_native_expected_quotes.json"
OLD_QUOTES = PACKET / "m_database_quotes.json"
OLD_REVIEWS = PACKET / "m_source_reviews.json"
ROOT_READBACK = PACKET / "m_source_readback.json"
MAIN_DIGEST = "b299ee1e266653492c71f50721d5ab7ce91b6e8538769c094035b0c7919678bb"
ARTICLE_VERSION_SUFFIX = ":panela-article-60cells-v1"
LIFECYCLE_EVIDENCE = {}
QUOTE_FIELDS = (
    "document_id", "source_locator", "parser_version", "quote_key", "product_id",
    "product_name", "category", "publisher", "series", "basis", "currency", "unit",
    "market", "observed_on", "period_start", "price", "min_price", "max_price",
    "source_page", "details",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def xmins(db, table, version=None):
    if table == "official_price_quote":
        query = "SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s"
        args = [SOURCE_SHA]
    elif table == "official_source_review":
        query = "SELECT source_locator,xmin::text FROM official_source_review WHERE document_id=%s"
        args = [SOURCE_SHA]
    else:
        query = "SELECT step,xmin::text FROM ingestion_checkpoint WHERE document_id=%s"
        args = [SOURCE_SHA]
    if version is not None:
        query += " AND " + ("processor_version" if table == "ingestion_checkpoint" else "parser_version") + "=%s"
        args.append(version)
    query += " ORDER BY 1"
    return db.execute(query, args).fetchall()


def business_quote_rows(db, version):
    fields = ",".join(field for field in QUOTE_FIELDS if field != "parser_version")
    return db.execute(
        f"SELECT {fields} FROM official_price_quote WHERE document_id=%s AND parser_version=%s "
        "AND series='dane-weekly' ORDER BY source_locator",
        (SOURCE_SHA, version),
    ).fetchall()


@unittest.skipUnless(os.environ.get("AGRO_AUG2013_ARTICLE_PG_DSN"), "requires fresh owned full-schema PostgreSQL")
class Aug2013ArticleOwnedPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        cls.oracle = json.loads(ORACLE_PATH.read_text())
        cls.native = json.loads(NATIVE.read_text())
        cls.old_quotes = json.loads(OLD_QUOTES.read_text())
        cls.old_reviews = json.loads(OLD_REVIEWS.read_text())
        cls.readback = json.loads(ROOT_READBACK.read_text())
        cls.url = SOURCE_URL
        cls.did = SOURCE_SHA
        cls.old_version = cls.old_quotes[0][2]
        cls.new_version = worker.asset_parser_version("dane-weekly-pdf", cls.url)
        cls.db = psycopg.connect(os.environ["AGRO_AUG2013_ARTICLE_PG_DSN"], autocommit=True)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def seed_exact_m_readback(self):
        db = self.db
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), self.did)
        self.assertEqual(self.readback["source_id"], self.did)
        self.assertEqual(self.readback["source_sha256"], self.did)
        self.assertEqual(self.readback["source_bytes"], len(self.body))
        source_meta = self.readback["source_metadata_without_body"]
        self.assertEqual(source_meta[:8], [
            self.did, "DANE · SIPSA - Semana_20ago_23ago_2013.pdf", "DANE · SIPSA",
            self.url, "application/pdf", "original", "2013-08-23", 44,
        ])
        self.assertEqual(source_meta[8], {
            "retention": "permanent", "ingestion_kind": "dane-weekly-pdf",
            "original_filename": "Semana_20ago_23ago_2013.pdf",
        })
        self.assertEqual(len(self.old_quotes), 4163)
        self.assertEqual(self.native, self.old_quotes)
        self.assertEqual(len(self.old_reviews), 134)
        self.assertEqual({r[2] for r in self.old_quotes}, {self.old_version})
        self.assertEqual(self.old_version, "official-v2:aug2013-page43-grid-article-period-v1:dane-weekly-v24")
        self.assertEqual([x[:3] for x in self.readback["checkpoints"]], [
            [self.old_version, "official:catalog-start:official-catalog-v1:2026-10-12", 4163],
            [self.old_version, "official:complete", 4163],
        ])
        metadata = source_meta[8]
        db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (self.did, *source_meta[1:8], self.body, Jsonb(metadata)),
        )
        asset = self.readback["asset"]
        db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,processor_version,checked_at,error) "
            "VALUES(%s,'dane-weekly-pdf','2013-08-23',%s,%s,%s,%s,%s,%s)",
            (self.url, asset[0], self.did, asset[1], asset[3], asset[4], asset[2]),
        )
        quote_placeholders = ",".join(["%s"] * len(QUOTE_FIELDS))
        for row in self.old_quotes:
            values = list(row)
            for index in (15, 16, 17):
                values[index] = None if values[index] is None else Decimal(str(values[index]))
            values[19] = Jsonb(values[19])
            db.execute(
                f"INSERT INTO official_price_quote({','.join(QUOTE_FIELDS)}) VALUES({quote_placeholders})",
                values,
            )
        for locator, record, reason in self.old_reviews:
            db.execute(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                "VALUES(%s,%s,%s,%s,%s)",
                (self.did, locator, self.old_version, Jsonb(record), reason),
            )
        for version, step, records, completed_at in self.readback["checkpoints"]:
            db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records,completed_at) "
                "VALUES(%s,%s,%s,%s,%s)",
                (self.did, version, step, records, completed_at),
            )

    def test_exact_source_parser_and_complete_m_revision_resumes_idempotently(self):
        db = self.db
        self.seed_exact_m_readback()
        self.assertTrue(self.new_version.endswith(ARTICLE_VERSION_SUFFIX + ":dane-weekly-v24"))
        self.assertEqual(self.readback["typed_quotes"], 4163)
        self.assertEqual(self.readback["unpriced_reviews"], 134)

        # Independently check the uncombined weekly parser against its accepted
        # 4,297-row digest before adding any article data.
        weekly = dane_weekly.parse_pdf(self.body, self.url)
        self.assertEqual(len(weekly), 4297)
        self.assertEqual(sum(row["price"] is not None for row in weekly), 4163)
        self.assertEqual(len({row["source_locator"] for row in weekly}), 4297)
        self.assertEqual(digest(weekly), MAIN_DIGEST)
        cells = extract(self.body, self.url)
        self.assertEqual(len(cells), 60)
        self.assertEqual([sum(c["source_table"] == n for c in cells) for n in (1, 2, 3)], [25, 30, 5])
        self.assertEqual(sorted({row["period_start"] for row in official_rows(self.body, self.url)}), [
            "2013-07-20", "2013-07-27", "2013-08-03", "2013-08-10", "2013-08-17",
        ])
        self.assertEqual({r["series"] for r in weekly}, {"dane-weekly"})

        source_xmin = db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (self.did,)).fetchone()[0]
        prior_quote_xmins = xmins(db, "official_price_quote", self.old_version)
        prior_review_xmins = xmins(db, "official_source_review", self.old_version)
        prior_cp_xmins = xmins(db, "ingestion_checkpoint", self.old_version)
        prior_main = business_quote_rows(db, self.old_version)
        self.assertEqual(len(prior_main), 4163)

        db.execute("SET ROLE agro_ingestor")
        try:
            original_retain = retained_pdf_upgrade.retained_aug2013_page43_original(
                db, self.url, "dane-weekly-pdf", self.new_version, self.new_version,
            )
            if original_retain is None:
                diagnostic = db.execute(
                    "SELECT a.status,a.document_id,a.observed_on,a.processor_version,a.records,a.error,"
                    "d.id,d.title,d.publisher,d.source_url,d.media_type,d.kind,d.reference_period,d.page_count,d.metadata "
                    "FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id WHERE a.url=%s",
                    (self.url,),
                ).fetchone()
                diagnostic += (db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s", (self.did,self.old_version)).fetchone()[0],)
                diagnostic += (db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s", (self.did,self.old_version)).fetchone()[0],)
                diagnostic += (db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'", (self.did,self.old_version)).fetchone(),)
                self.fail("Exact completed-M original did not qualify for retained replay: " + repr(diagnostic))
            self.assertEqual(hashlib.sha256(original_retain).hexdigest(), self.did)

            # Force a genuine committed-batch interruption after one 256-row
            # batch, then resume through actual worker.process_asset using the
            # pinned retained original. The interruption is confined to this PG.
            from pipelines.ingestion.resumable_inputs import WorkDeferred
            deadline_token = worker.RUN_DEADLINE.set(__import__("time").monotonic() + 3600)
            batch_calls = {"n": 0}
            def interrupt_after_first_batch(*_args, **_kwargs):
                batch_calls["n"] += 1
                if batch_calls["n"] == 1:
                    worker.RUN_DEADLINE.set(__import__("time").monotonic() - 1)
            try:
                with patch.object(write_pacing, "pause_between_batches", side_effect=interrupt_after_first_batch):
                    with self.assertRaises(WorkDeferred):
                        official_sources.process(db, self.body, self.did, self.url, "dane-weekly-pdf")
            finally:
                worker.RUN_DEADLINE.reset(deadline_token)
            self.assertEqual(batch_calls["n"], 1)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
                (self.did, self.new_version),
            ).fetchone()[0], 256)
            self.assertFalse(db.execute(
                "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (self.did, self.new_version),
            ).fetchone())
            db.execute(
                "UPDATE ingestion_asset SET status='pending',records=0,processor_version=%s,error=%s WHERE url=%s",
                (self.new_version, "Official source validated; committed quote batches will resume", self.url),
            )
            with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), \
                 patch.object(worker, "fetch_asset", side_effect=AssertionError("retained replay attempted HTTP")), \
                 patch.object(worker, "_request", side_effect=AssertionError("retained replay attempted HTTP")), \
                 patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=None) as blob_boundary, \
                 patch.object(write_pacing, "pause_between_batches", return_value=None), \
                 patch.object(write_pacing, "yield_to_active_readers", return_value=None), \
                 patch("pipelines.ingestion.official_catalog._sleep", return_value=None):
                resumed = worker.process_asset(db, self.url, "dane-weekly-pdf", date(2013, 8, 23))
            self.assertEqual(resumed, 4223)
            self.assertEqual(blob_boundary.call_count, 1)
        finally:
            db.execute("RESET ROLE")

        new_quotes = db.execute(
            "SELECT count(*),count(*) FILTER (WHERE series='dane-weekly'),count(*) FILTER (WHERE series=%s) "
            "FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
            (ARTICLE_SERIES, self.did, self.new_version),
        ).fetchone()
        new_reviews = db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s",
            (self.did, self.new_version),
        ).fetchone()[0]
        self.assertEqual(new_quotes, (4223, 4163, 60))
        self.assertEqual(new_reviews, 134)
        self.assertEqual(db.execute(
            "SELECT count(*),min(observed_on),max(observed_on),count(*) FILTER (WHERE basis=%s AND unit='kg' "
            "AND min_price IS NULL AND max_price IS NULL AND details->>'price_statistic'=%s) "
            "FROM official_price_quote WHERE document_id=%s AND parser_version=%s AND series=%s",
            (ARTICLE_BASIS, ARTICLE_STATISTIC, self.did, self.new_version, ARTICLE_SERIES),
        ).fetchone(), (60, date(2013, 7, 26), date(2013, 8, 23), 60))
        new_main = business_quote_rows(db, self.new_version)
        self.assertEqual(new_main, prior_main)
        self.assertEqual(db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
            (self.did, self.new_version),
        ).fetchone(), (4223,))

        article_version = self.new_version
        article_rows = db.execute(
            "SELECT source_locator,product_name,market,observed_on,period_start,price,min_price,max_price,basis,unit,series,details "
            "FROM official_price_quote WHERE document_id=%s AND parser_version=%s AND series=%s ORDER BY source_locator",
            (self.did, article_version, ARTICLE_SERIES),
        ).fetchall()
        expected_article = official_rows(self.body, self.url)
        self.assertEqual(len(article_rows), len(expected_article))
        by_locator = {r["source_locator"]: r for r in expected_article}
        for actual in article_rows:
            expected = by_locator.pop(actual[0])
            self.assertEqual(actual[1:11], (
                expected["product_name"], expected["market"], date.fromisoformat(expected["date"]),
                date.fromisoformat(expected["period_start"]), Decimal(str(expected["price"])), None, None,
                ARTICLE_BASIS, "kg", ARTICLE_SERIES,
            ))
            self.assertEqual(actual[11]["price_statistic"], ARTICLE_STATISTIC)
            self.assertEqual(actual[11]["identity_dimensions"], {"published_statistic": ARTICLE_STATISTIC})
        self.assertFalse(by_locator)

        # Actual source, M quote/review rows, and old checkpoints are append-only.
        self.assertEqual(db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (self.did,)).fetchone()[0], source_xmin)
        LIFECYCLE_EVIDENCE.update({
            "seeded_native_m_quotes": len(self.old_quotes),
            "seeded_native_m_reviews": len(self.old_reviews),
            "weekly_native_grid_rows": len(weekly),
            "weekly_native_grid_sha256": digest(weekly),
            "weekly_typed_rows_new_revision": new_quotes[1],
            "article_typed_rows_new_revision": new_quotes[2],
            "new_revision_review_rows": new_reviews,
            "first_interrupted_batch_rows": 256,
            "worker_retained_resume_returned": resumed,
            "old_quote_review_checkpoint_xmins_unchanged": True,
            "source_document_xmin_unchanged": True,
            "source_byte_sha256": hashlib.sha256(self.body).hexdigest(),
            "article_dates": sorted({r["period_start"] for r in expected_article}),
            "article_series": ARTICLE_SERIES,
            "article_basis": ARTICLE_BASIS,
            "article_statistic": ARTICLE_STATISTIC,
            "new_checkpoint_records": 4223,
        })
        self.assertEqual(xmins(db, "official_price_quote", self.old_version), prior_quote_xmins)
        self.assertEqual(xmins(db, "official_source_review", self.old_version), prior_review_xmins)
        self.assertEqual(xmins(db, "ingestion_checkpoint", self.old_version), prior_cp_xmins)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (self.did,),
        ).fetchone()[0], 8386)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (self.did,),
        ).fetchone()[0], 268)

        before_new_quote_xmins = xmins(db, "official_price_quote", self.new_version)
        before_new_review_xmins = xmins(db, "official_source_review", self.new_version)
        before_new_cp_xmins = xmins(db, "ingestion_checkpoint", self.new_version)
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), \
             patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=None), \
             patch.object(write_pacing, "pause_between_batches", return_value=None), \
             patch.object(write_pacing, "yield_to_active_readers", return_value=None), \
             patch("pipelines.ingestion.official_catalog._sleep", return_value=None):
            # Reparse and republish through the staged adapter; ON CONFLICT is
            # accepted only after full stored-row equivalence checks.
            official_sources.process(db, self.body, self.did, self.url, "dane-weekly-pdf")
        self.assertEqual(xmins(db, "official_price_quote", self.new_version), before_new_quote_xmins)
        self.assertEqual(xmins(db, "official_source_review", self.new_version), before_new_review_xmins)
        self.assertEqual(xmins(db, "ingestion_checkpoint", self.new_version), before_new_cp_xmins)
        self.assertEqual(db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (self.did,)).fetchone()[0], source_xmin)
        LIFECYCLE_EVIDENCE["publication_replay_xmins_unchanged"] = True

        # A source URL mismatch fails before changing any published relation.
        before = (xmins(db, "official_price_quote", self.new_version),
                  xmins(db, "official_source_review", self.new_version),
                  xmins(db, "ingestion_checkpoint", self.new_version))
        with self.assertRaisesRegex(ValueError, "Exact August 2013"):
            official_sources.publish_rows(db, expected_article, self.did,
                                          "dane-weekly-pdf", source_url="https://example.invalid/forged.pdf")
        self.assertEqual(before, (xmins(db, "official_price_quote", self.new_version),
                                  xmins(db, "official_source_review", self.new_version),
                                  xmins(db, "ingestion_checkpoint", self.new_version)))



if __name__ == "__main__":
    unittest.main(verbosity=2)
