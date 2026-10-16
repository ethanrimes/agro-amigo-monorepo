"""Exact September 2014 DANE PDF and append-only retained worker replay."""

import hashlib
import os
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb

from . import inputs, pdf_sources, queue_plan, worker
from .input_pdf_v17_replay import VERSION as GENERIC_INPUT_VERSION
from .reviewed_quindio_sep2014 import (
    DAY, FULL_ROWS, REVIEWED_ROWS, SHA256, URL, VERSION,
    canonical_department, parse_reviewed_quindio_sep2014,
    retained_exact_quindio_pdf, assert_stored_version_rows,
)
from .special_prices import DEPARTMENTS

PDF = Path(__file__).parent / "testdata" / f"{SHA256}.pdf"


class September2014Original(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        assert hashlib.sha256(cls.body).hexdigest() == SHA256
        cls.new = parse_reviewed_quindio_sep2014(cls.body, DAY, URL)

    def test_all_76_pages_preserve_old_rows_and_add_exactly_three(self):
        old = list(pdf_sources.parse_input_pdf(self.body, DAY))
        self.assertEqual((len(old), len(self.new)), (7242, FULL_ROWS))
        new_map = {row[0]: row for row in self.new}
        self.assertEqual(len(new_map), FULL_ROWS)
        for row in old:
            locator = row[0].replace("; inputs-pdf-v14", "; " + VERSION)
            self.assertEqual(new_map[locator], (
                locator, *row[1:-1], {**row[-1], "parser_version": VERSION}
            ))
        added = [row for row in self.new if row[-1]["printed_location_lines"] == ["Armenia (Quindio)"]]
        self.assertEqual(len(added), 3)
        self.assertEqual(Counter((r[0], r[3], r[5], r[6], r[7]) for r in added),
                         Counter(REVIEWED_ROWS))
        self.assertTrue(all(r[-1]["department"] == "Quindío" for r in added))

    def test_source_version_and_drift_guards(self):
        self.assertEqual(inputs.input_pdf_version_for_document(SHA256, URL), VERSION)
        self.assertEqual(worker.asset_parser_version("inputs-pdf", URL), VERSION)
        self.assertEqual(worker.asset_parser_version("inputs-pdf", URL + "?alias"), GENERIC_INPUT_VERSION)
        self.assertIn((URL, "inputs-pdf", SHA256), queue_plan.PRIORITY_SOURCE_REPAIRS)
        for body, day, url in (
            (self.body + b"x", DAY, URL),
            (self.body, DAY.replace(day=29), URL),
            (self.body, DAY, URL + "?alias"),
        ):
            with self.subTest(day=day, url=url), self.assertRaisesRegex(ValueError, "exact URL, date and PDF SHA"):
                parse_reviewed_quindio_sep2014(body, day, url)
        with self.assertRaisesRegex(ValueError, "exact source URL"):
            inputs.input_pdf_version_for_document(SHA256, URL + "?alias")
        with self.assertRaisesRegex(ValueError, "exact reviewed original and date"):
            list(pdf_sources.parse_input_pdf(self.body + b"x", DAY, parser_version=VERSION))

    def test_unique_canonical_department_only(self):
        self.assertEqual(len(DEPARTMENTS), 33)
        for label in DEPARTMENTS:
            self.assertEqual(canonical_department(label), label)
        self.assertEqual(canonical_department("Quindio"), "Quindío")
        self.assertEqual(canonical_department("QUINDIO"), "Quindío")
        for unknown in ("Quindoi", "Quindio vecino", "Bogotá (continuación)"):
            self.assertIsNone(canonical_department(unknown))
        self.assertEqual(pdf_sources._input_pdf_place("Armenia (Quindio)"), None)
        self.assertEqual(pdf_sources._input_pdf_place(
            "Armenia (Quindio)", department_resolver=canonical_department),
            ("Armenia", "Quindío", False))
        self.assertEqual(pdf_sources._input_pdf_place(
            "Bogotá, D.C.", department_resolver=canonical_department),
            ("Bogotá, D.C.", "Bogotá, D.C.", False))
        self.assertEqual(pdf_sources._input_pdf_place(
            "Armenia (Quindio) (continuación)", department_resolver=canonical_department),
            ("Armenia", "Quindío", True))


@unittest.skipUnless(os.environ.get("AGRO_INPUT_SEP2014_POSTGRES_TEST") == "1",
                     "Explicit owned full-schema PostgreSQL opt-in")
class September2014FullSchemaWorker(unittest.TestCase):
    def test_retained_full_source_worker_resume_and_catalog(self):
        dsn = os.environ.get("AGRO_INPUT_SEP2014_TEST_DSN") or os.environ.get("DATABASE_URL", "")
        self.assertIn("host=/tmp/agro-wuxal-sep2014-", dsn)
        self.enterContext(patch.dict(os.environ, {"DATABASE_URL": dsn}))
        with worker.connect() as db:
            self.assertTrue((db.info.host or "").startswith("/tmp/agro-wuxal-sep2014-"))
            self.assertIsNone(db.execute("SELECT inet_server_addr()").fetchone()[0])
            body = PDF.read_bytes()
            # A wrong media type or same-ID changed body cannot take the
            # retained route. Both staged fixtures roll back on this local DB.
            for media, archived_body, expected in (
                ("application/octet-stream", body, None),
                ("application/pdf", body + b"x", ValueError),
            ):
                with self.assertRaisesRegex(RuntimeError, "negative source rollback"):
                    with db.transaction():
                        db.execute("""INSERT INTO source_document
                          (id,title,publisher,source_url,media_type,kind,
                           reference_period,page_count,content,metadata)
                          VALUES(%s,'September 2014 inputs','DANE',%s,%s,'original',
                                 '2014-09',76,%s,%s)""",
                                   (SHA256, URL, media, archived_body,
                                    Jsonb({"ingestion_kind": "inputs-pdf"})))
                        db.execute("""INSERT INTO ingestion_asset
                          (url,kind,observed_on,document_id,status,processor_version,records)
                          VALUES(%s,'inputs-pdf',%s,%s,'complete','inputs-pdf-v14',7242)""",
                                   (URL, DAY, SHA256))
                        if expected is None:
                            self.assertIsNone(retained_exact_quindio_pdf(db, URL, "inputs-pdf", VERSION))
                        else:
                            with self.assertRaisesRegex(expected, "immutable SHA"):
                                retained_exact_quindio_pdf(db, URL, "inputs-pdf", VERSION)
                        raise RuntimeError("negative source rollback")
            db.execute("""INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,
               page_count,content,metadata)
              VALUES(%s,'September 2014 inputs','DANE',%s,'application/pdf',
                     'original','2014-09',76,%s,%s)""",
                       (SHA256, URL, body, Jsonb({"ingestion_kind": "inputs-pdf"})))
            db.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,document_id,status,processor_version,records)
              VALUES(%s,'inputs-pdf',%s,%s,'complete','inputs-pdf-v14',7242)""",
                       (URL, DAY, SHA256))
            self.assertIsNone(retained_exact_quindio_pdf(db, URL + "?alias", "inputs-pdf", VERSION))
            self.assertIsNone(retained_exact_quindio_pdf(db, URL, "daily-pdf", VERSION))
            self.assertIsNone(retained_exact_quindio_pdf(db, URL, "inputs-pdf", "inputs-pdf-v14"))
            for column, changed, original in (
                ("observed_on", DAY.replace(day=29), DAY),
                ("document_id", None, SHA256),
            ):
                db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (changed, URL))
                self.assertIsNone(retained_exact_quindio_pdf(db, URL, "inputs-pdf", VERSION))
                db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (original, URL))
            self.assertEqual(retained_exact_quindio_pdf(db, URL, "inputs-pdf", VERSION), body)
            old = list(pdf_sources.parse_input_pdf(body, DAY))
            with patch.object(inputs, "input_pdf_version_for_document", return_value="inputs-pdf-v14"):
                with db.transaction():
                    worker.save_rows(db, SHA256, old)
                    inputs.project_pdf_inputs(db, SHA256, source_url=URL)
            baseline = db.execute("""SELECT count(*) FROM published_input_municipal_price
              WHERE document_id=%s""", (SHA256,)).fetchone()[0]
            self.assertEqual(baseline, 7242)
            old_xmins = dict(db.execute("""SELECT source_locator,xmin::text FROM historical_price
              WHERE document_id=%s""", (SHA256,)).fetchall())
            epoch_before = db.execute("""SELECT source_epoch FROM input_latest_projection_state
              WHERE scope='municipality'""").fetchone()[0]
            revised = parse_reviewed_quindio_sep2014(body, DAY, URL)
            # A same-version locator with changed monetary data cannot be
            # silently accepted by the append-only COPY conflict clause.
            tampered = list(revised[0])
            tampered[6] += 1
            with self.assertRaisesRegex(RuntimeError, "negative row rollback"):
                with db.transaction():
                    worker.save_rows(db, SHA256, [tuple(tampered)])
                    with self.assertRaisesRegex(ValueError, "conflicts with original"):
                        assert_stored_version_rows(db, revised)
                    raise RuntimeError("negative row rollback")
            with db.transaction():
                worker.save_rows(db, SHA256, revised[:2000])
            self.assertEqual(db.execute("""SELECT count(*) FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s""", (SHA256, VERSION)).fetchone()[0], 0)
            self.assertEqual(db.execute("""SELECT count(*) FROM published_input_municipal_price
              WHERE document_id=%s""", (SHA256,)).fetchone()[0], baseline)

            real_project = inputs.project_pdf_inputs
            def crash_after_project(local_db, did, *, source_url):
                real_project(local_db, did, source_url=source_url)
                raise RuntimeError("post-publication crash")
            with patch.object(worker, "fetch_asset", side_effect=AssertionError("source HTTP forbidden")), \
                 patch.object(worker, "archive", return_value=SHA256), \
                 patch.object(pdf_sources, "extract_pages", return_value=0), \
                 patch.object(inputs, "project_pdf_inputs", side_effect=crash_after_project):
                self.assertTrue(worker.retained_reparse_during_host_cooldown(db, URL, "inputs-pdf"))
                with self.assertRaisesRegex(RuntimeError, "post-publication crash"):
                    worker.process_asset(db, URL, "inputs-pdf", DAY)
            self.assertEqual(db.execute("""SELECT count(*) FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s""", (SHA256, VERSION)).fetchone()[0], 0)
            self.assertEqual(db.execute("""SELECT count(*) FROM published_input_municipal_price
              WHERE document_id=%s""", (SHA256,)).fetchone()[0], baseline)
            self.assertEqual(db.execute("SELECT status,processor_version FROM ingestion_asset WHERE url=%s",
                                        (URL,)).fetchone(), ("pending", "inputs-pdf-v14"))
            with patch.object(worker, "fetch_asset", side_effect=AssertionError("source HTTP forbidden")) as fetch, \
                 patch.object(worker, "archive", return_value=SHA256), \
                 patch.object(pdf_sources, "extract_pages", return_value=0):
                self.assertEqual(worker.process_asset(db, URL, "inputs-pdf", DAY), FULL_ROWS)
                fetch.assert_not_called()
            self.assertEqual(db.execute("SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s",
                                        (URL,)).fetchone(), ("complete", VERSION, FULL_ROWS))
            self.assertEqual(db.execute("""SELECT records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'""",
                                        (SHA256, VERSION)).fetchone(), (FULL_ROWS,))
            self.assertEqual(db.execute("""SELECT count(*) FROM published_input_municipal_price
              WHERE document_id=%s""", (SHA256,)).fetchone()[0], FULL_ROWS)
            self.assertEqual(dict(db.execute("""SELECT source_locator,xmin::text FROM historical_price
              WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14'""",
                                             (SHA256,)).fetchall()), old_xmins)
            self.assertGreater(db.execute("""SELECT source_epoch FROM input_latest_projection_state
              WHERE scope='municipality'""").fetchone()[0], epoch_before)
            self.assertEqual(db.execute("""SELECT count(*) FROM input_latest_projection_delta
              WHERE scope='municipality' AND id='wuxal-tapa-negra-1-litro'""").fetchone()[0], 1)
            self.assertTrue(db.execute("SELECT refresh_input_latest_projection('municipality')").fetchone()[0])
            self.assertEqual(db.execute("""SELECT price FROM input_municipal_latest_raw
              WHERE id='wuxal-tapa-negra-1-litro' AND department='Quindío'
                AND municipality='Armenia'""").fetchone()[0], 30300)
            self.assertIsNone(retained_exact_quindio_pdf(db, URL, "inputs-pdf", VERSION))
            before_count = db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s",
                                      (SHA256,)).fetchone()[0]
            retained_before = db.execute("SELECT count(*) FROM retained_record").fetchone()[0]
            with db.transaction():
                worker.save_rows(db, SHA256, revised)
                inputs.project_pdf_inputs(db, SHA256, source_url=URL)
            self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s",
                                        (SHA256,)).fetchone()[0], before_count)
            self.assertEqual(db.execute("SELECT count(*) FROM retained_record").fetchone()[0], retained_before)


if __name__ == "__main__":
    unittest.main()
