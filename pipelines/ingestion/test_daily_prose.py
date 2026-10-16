"""Two audited native prose originals; independent numeric and retention oracles."""

import csv
import hashlib
import os
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
import pdfplumber
from psycopg.types.json import Jsonb

from .daily_prose import (
    AUDITED, VERSION, parse_exact_daily_prose, review_unbound_daily_prose,
)
from .pdf_sources import parse_archived_price_pdf
from .retained_pdf_upgrade import retained_pdf_upgrade
from .worker import (
    asset_parser_version, project, retained_reparse_during_host_cooldown,
    retire_daily_pdf_old_cells, save_rows,
)
from .queue_plan import repair_candidates


FIXTURES = Path(__file__).parent / "testdata/daily_prose"
THIRD_SHA = "31204423a30a31493d2fe4e0608752c5ea2f76913ed3f0f4e2ebe43cde6dfaac"
SOURCES = (
    ("mayoristas_febrero_04_2020.pdf", "manually-read-prose-20200204-b.psv",
     "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf"),
    ("bol-SIPSADiario-21ago2026.pdf", "manually-read-prose-20260821-b.psv",
     "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf"),
)


def source_case(filename, url):
    body = (FIXTURES / filename).read_bytes()
    sha, day, _, _ = AUDITED[url]
    assert hashlib.sha256(body).hexdigest() == sha
    return body, sha, date.fromisoformat(day)


class DailyProseNative(unittest.TestCase):
    def test_all_50_fresh_native_values_against_independent_manual_controls(self):
        total_rows = total_reviews = 0
        for filename, oracle, url in SOURCES:
            body, sha, day = source_case(filename, url)
            rows, reviews = parse_exact_daily_prose(body, url, sha, day)
            with pdfplumber.open(FIXTURES / filename) as original:
                all_money_spans = sum(len(re.findall(
                    r"\$\s*\d+(?:\.\d{3})*", page.extract_text() or ""))
                    for page in original.pages)
            with (FIXTURES / oracle).open() as handle:
                manual = list(csv.DictReader(handle, delimiter="|"))
            expected = {
                (r["product_literal"], r["place_literal"],
                 float(r["price_cop_per_kg"]), float(r["change_percent"]))
                for r in manual if "capital" not in r["place_literal"]
            }
            actual = {(r[3], r[4], r[6], r[7]) for r in rows}
            self.assertEqual(actual, expected)
            self.assertEqual(len(rows) + len(reviews), len(manual))
            self.assertEqual(len(rows) + len(reviews), all_money_spans)
            self.assertEqual(len({r[0] for r in rows}), len(rows))
            self.assertTrue(all(r[5] == "kg" and r[2] == day for r in rows))
            self.assertTrue(all(r[-1]["published_basis"] ==
                                "Quoted city/market price, not a mean or range" for r in rows))
            self.assertTrue(all("PDF page" in r[0] and r[-1]["source_quote"] for r in rows))
            total_rows += len(rows)
            total_reviews += len(reviews)
        self.assertEqual((total_rows, total_reviews), (48, 2))

    def test_mandarina_and_guayaba_stay_in_distinct_paragraphs(self):
        filename, _, url = SOURCES[0]
        body, sha, day = source_case(filename, url)
        rows, reviews = parse_exact_daily_prose(body, url, sha, day)
        self.assertEqual(len(reviews), 2)
        self.assertIn(("mandarina", "Medellín", 3000),
                      {(r[3], r[4], r[6]) for r in rows})
        self.assertIn(("guayaba", "Medellín", 1200),
                      {(r[3], r[4], r[6]) for r in rows})
        later_body, later_sha, later_day = source_case(SOURCES[1][0], SOURCES[1][2])
        later_rows, _ = parse_exact_daily_prose(
            later_body, SOURCES[1][2], later_sha, later_day)
        self.assertIn(("habichuela", "Villavicencio, CAV", 3333),
                      {(r[3], r[4], r[6]) for r in later_rows})

    def test_date_sha_and_unknown_layout_fail_closed(self):
        filename, _, url = SOURCES[0]
        body, sha, day = source_case(filename, url)
        rows, reviews = parse_exact_daily_prose(body, url, sha, date(2020, 2, 5))
        self.assertEqual((len(rows), len(reviews)), (0, 28))
        changed = body + b"\n% changed immutable revision\n"
        changed_sha = hashlib.sha256(changed).hexdigest()
        rows, reviews = parse_exact_daily_prose(changed, url, changed_sha, day)
        self.assertEqual((len(rows), len(reviews)), (0, 28))
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            parse_exact_daily_prose(changed, url, sha, day)
        self.assertIsNone(parse_exact_daily_prose(body, "https://unrelated.example/a.pdf", sha, day))

    def test_exact_url_versions_only(self):
        for _, _, url in SOURCES:
            self.assertTrue(asset_parser_version("daily-pdf", url).endswith(
                ":daily-prose-two-originals-v1"))
        self.assertFalse(asset_parser_version("daily-pdf", "https://unrelated.example/a.pdf").endswith(
            ":daily-prose-two-originals-v1"))

    def test_real_third_readable_original_reviews_every_unbound_money_span_without_ocr(self):
        body = (FIXTURES / "mayoristas_abril_18_2013.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), THIRD_SHA)
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_abril_18_2013.pdf"
        self.assertIsNone(parse_exact_daily_prose(body, url, THIRD_SHA, date(2013, 4, 18)))
        with pdfplumber.open(FIXTURES / "mayoristas_abril_18_2013.pdf") as pdf:
            self.assertEqual(len(pdf.pages), 4)
            self.assertTrue(all(not page.extract_tables() for page in pdf.pages))
            native = sum(len(re.findall(r"\$\s*\d+(?:\.\d{3})*",
                                        page.extract_text() or "")) for page in pdf.pages)
        reviews = review_unbound_daily_prose(body, url, THIRD_SHA, date(2013, 4, 18))
        self.assertEqual((native, len(reviews)), (31, 31))
        self.assertEqual(len({row[0] for row in reviews}), 31)
        self.assertTrue(all("span" in locator and record["native_price_literal"].startswith("$")
                            and record["source_sha256"] == THIRD_SHA
                            and record["registered_day_unverified"] == "2013-04-18"
                            for locator, record, _ in reviews))
        with patch("pipelines.ingestion.pdf_sources.verified_page",
                   side_effect=AssertionError("Readable prose is not OCR")) as ocr:
            with self.assertRaisesRegex(ValueError, "No supported price grids"):
                list(parse_archived_price_pdf(None, body, THIRD_SHA,
                                              date(2013, 4, 18), "daily-pdf"))
            ocr.assert_not_called()

    def test_changed_url_cannot_inherit_typed_prices(self):
        filename, _, url = SOURCES[0]
        body, sha, day = source_case(filename, url)
        alternate = url.replace("mayoristas_febrero_04_2020", "another_daily")
        self.assertIsNone(parse_exact_daily_prose(body, alternate, sha, day))
        reviews = review_unbound_daily_prose(body, alternate, sha, day)
        self.assertEqual(len(reviews), 28)


class DailyProsePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn and os.environ.get("AGRO_REFERENCE_TEST_SOCKET"):
            dsn = (f"host={os.environ['AGRO_REFERENCE_TEST_SOCKET']} "
                   "port=65443 dbname=postgres")
        dsn = dsn or os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("Private PostgreSQL DSN required for daily prose regression")
        cls.db = psycopg.connect(dsn, autocommit=True)
        if not str(cls.db.info.host).startswith("/tmp/agro-"):
            cls.db.close()
            raise RuntimeError("Daily prose tests require an isolated local PostgreSQL socket")
        cls.db.execute("SET search_path=pg_temp")
        cls.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
          document_id text,processor_version text,step text,records integer DEFAULT 0,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))""")
        cls.db.execute("""CREATE TEMP TABLE source_document(
          id text PRIMARY KEY,kind text,source_url text,media_type text,content bytea,
          metadata jsonb,retrieved_at timestamptz,title text,publisher text,
          reference_period text,page_count integer)""")
        cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
          url text PRIMARY KEY,kind text,status text,records integer,
          document_id text,processor_version text,checked_at timestamptz,
          observed_on date,error text)""")
        cls.db.execute("""CREATE TEMP TABLE historical_price(
          document_id text,source_locator text,series text,observed_on date,
          product_name text,market_name text,unit text,price numeric,
          change_percent numeric,details jsonb,
          PRIMARY KEY(document_id,source_locator))""")
        cls.db.execute("""CREATE TEMP TABLE historical_price_review(
          document_id text,source_locator text,validator_version text,reason text,
          PRIMARY KEY(document_id,source_locator,validator_version))""")
        cls.db.execute("""CREATE TEMP TABLE official_source_review(
          document_id text,source_locator text,parser_version text,record jsonb,
          reason text,PRIMARY KEY(document_id,source_locator,parser_version))""")
        cls.db.execute("CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)")
        cls.db.execute("""CREATE TEMP TABLE daily_price(
          observed_on date,product_name text,market_name text,product_id text,
          price numeric,change_percent numeric,document_id text,source_page integer,
          source_locator text,unit text,
          PRIMARY KEY(observed_on,product_name,market_name))""")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")
        for filename, _, url in SOURCES:
            body, sha, _ = source_case(filename, url)
            self.db.execute(
                "INSERT INTO source_document(id,kind,source_url,media_type,content,metadata,retrieved_at) VALUES(%s,'original',%s,'application/pdf',%s,%s,now())",
                (sha, url, body, Jsonb({"ingestion_kind": "daily-pdf"})))
            self.db.execute("""INSERT INTO ingestion_asset(url,kind,status,records,
              document_id,processor_version,checked_at,observed_on)
              VALUES(%s,'daily-pdf','processed',0,%s,%s,now(),%s)""",
                            (url, sha, "daily-pdf-v6:supply-daily-pdf-summary-v1",
                             AUDITED[url][1]))
        self.db.execute("INSERT INTO source_document(id,kind,source_url,media_type,content,metadata,retrieved_at) VALUES('workbook','original','workbook','xlsx',NULL,%s,now())",
                        (Jsonb({"ingestion_kind": "daily"}),))

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def _publish(self, source):
        filename, _, url = source
        body, sha, day = source_case(filename, url)
        rows, reviews = parse_exact_daily_prose(body, url, sha, day)
        with self.db.transaction():
            save_rows(self.db, sha, rows)
            retire_daily_pdf_old_cells(self.db, sha)
            for locator, record, reason in reviews:
                self.db.execute("INSERT INTO official_source_review VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                (sha, locator, VERSION, Jsonb(record), reason))
            project(self.db, sha, url, "daily-pdf", source_rows=rows)
        # Each production publication commits, dropping its ON COMMIT stage.
        # This test's outer rollback deliberately keeps the fixture isolated.
        self.db.execute("DROP TABLE IF EXISTS pg_temp.ingestion_stage")
        return sha, day, rows, reviews

    def test_retain_raw_reviews_idempotence_and_workbook_precedence(self):
        source = SOURCES[0]
        sha, day, rows, reviews = self._publish(source)
        self.assertEqual((len(rows), len(reviews)), (26, 2))
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s", (sha,)).fetchone()[0], 26)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (sha,)).fetchone()[0], 2)
        self.assertEqual(self.db.execute("""SELECT document_id,source_page,source_locator
          FROM daily_price WHERE observed_on=%s AND product_name='mandarina'
          AND market_name='Medellín'""", (day,)).fetchone()[0:2], (sha, 2))
        self._publish(source)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s", (sha,)).fetchone()[0], 26)
        self.db.execute("""UPDATE daily_price SET price=999,change_percent=1,
          document_id='workbook',source_locator='sheet1!r1'
          WHERE observed_on=%s AND product_name='mandarina' AND market_name='Medellín'""", (day,))
        self._publish(source)
        self.assertEqual(self.db.execute("SELECT price,document_id FROM daily_price WHERE observed_on=%s AND product_name='mandarina' AND market_name='Medellín'", (day,)).fetchone(), (999, 'workbook'))

    def test_processed_exact_retained_original_and_changed_pointer(self):
        filename, _, url = SOURCES[0]
        body, sha, _ = source_case(filename, url)
        self.assertEqual(retained_pdf_upgrade(self.db, url, 'daily-pdf', asset_parser_version('daily-pdf', url)), body)
        self.db.execute("UPDATE ingestion_asset SET document_id='workbook' WHERE url=%s", (url,))
        self.assertIsNone(retained_pdf_upgrade(self.db, url, 'daily-pdf', asset_parser_version('daily-pdf', url)))

    def test_recent_processed_exact_original_enters_bounded_local_repair(self):
        filename, _, url = SOURCES[0]
        body, sha, _ = source_case(filename, url)
        chosen = [row[0] for row in repair_candidates(self.db, 8)]
        self.assertIn(url, chosen)
        self.assertTrue(retained_reparse_during_host_cooldown(self.db, url, 'daily-pdf'))
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (asset_parser_version('daily-pdf', url), url))
        self.assertNotIn(url, [row[0] for row in repair_candidates(self.db, 8)])
        self.db.execute("""UPDATE ingestion_asset SET processor_version=%s,
          document_id='workbook' WHERE url=%s""",
                        ('daily-pdf-v6:supply-daily-pdf-summary-v1', url))
        self.assertNotIn(url, [row[0] for row in repair_candidates(self.db, 8)])
        self.assertFalse(retained_reparse_during_host_cooldown(self.db, url, 'daily-pdf'))

    def test_transaction_rollback_preserves_prior_publication(self):
        old_sha, _, _, _ = self._publish(SOURCES[0])
        old_count = self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s",
            (old_sha,)).fetchone()[0]
        filename, _, url = SOURCES[1]
        body, sha, day = source_case(filename, url)
        rows, _ = parse_exact_daily_prose(body, url, sha, day)
        changed = list(rows[0])
        changed[0] += ":conflicting-test-row"
        changed[6] += 1
        with self.assertRaisesRegex(ValueError, "Conflicting daily source row"):
            with self.db.transaction():
                save_rows(self.db, sha, [rows[0], tuple(changed)])
                self.db.execute(
                    "INSERT INTO official_source_review VALUES(%s,%s,%s,%s,%s)",
                    (sha, "test-review", VERSION, Jsonb({"source_sha256": sha}),
                     "transaction should roll back"))
                project(self.db, sha, url, "daily-pdf",
                        source_rows=[rows[0], tuple(changed)])
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s",
            (sha,)).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s",
            (sha,)).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s",
            (old_sha,)).fetchone()[0], old_count)

    def test_unbound_money_reviews_append_without_price_and_replay_idempotently(self):
        body = (FIXTURES / "mayoristas_abril_18_2013.pdf").read_bytes()
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_abril_18_2013.pdf"
        self.db.execute("""INSERT INTO source_document
          (id,kind,source_url,media_type,content,metadata,retrieved_at)
          VALUES(%s,'original',%s,'application/pdf',%s,%s,now())""",
                        (THIRD_SHA, url, body, Jsonb({"ingestion_kind": "daily-pdf"})))
        reviews = review_unbound_daily_prose(body, url, THIRD_SHA, date(2013, 4, 18))
        for _ in range(2):
            with self.db.transaction():
                for locator, record, reason in reviews:
                    self.db.execute("""INSERT INTO official_source_review
                      VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                    (THIRD_SHA, locator, VERSION, Jsonb(record), reason))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",
                                         (THIRD_SHA,)).fetchone()[0], 31)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s",
                                         (THIRD_SHA,)).fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM daily_price WHERE observed_on='2013-04-18'").fetchone()[0], 0)
