"""TEMP-only lifecycle checks for exact retained monthly PDF OCR recovery."""

import hashlib
import io
import os
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from . import monthly_pdf_recovery, ocr, worker

FIXTURE = (
    Path(__file__).resolve().parent
    / "testdata/monthly_decorative/cp_mensual_dic_2014.pdf"
)
EXACT_SHA = "e54423fc627fbbbeede4000c0a501ffaa5b3d1dd202532f6b0821c9622588277"
EXACT_IMAGE_SHA = "8ce6fd36b6a39f233edb60d0846c46ca0e6af0b4e65005deb72ce2e38e325381"


def unknown_price_image_pdf():
    """Valid one-page PDF with a new price-body raster and a known title."""
    image = Image.new("RGB", (600, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), "BOGOTA CORABASTOS 12500 KG", fill="black")
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(600, 800))
    pdf.setFont("Helvetica", 16)
    pdf.drawString(60, 760, "Verduras y hortalizas")
    pdf.drawImage(ImageReader(image), 30, 120, width=540, height=500)
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


@unittest.skipUnless(
    os.environ.get("AGRO_MONTHLY_NATIVE_RECOVERY_POSTGRES_TEST") == "1",
    "Explicit isolated private PostgreSQL TEMP-table opt-in",
)
class MonthlyPDFRecoveryPostgresTests(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("DATABASE_URL", "")
        self.assertTrue(dsn, "Private Unix-socket DATABASE_URL required")
        connection_options = conninfo_to_dict(dsn)
        self.assertTrue(
            connection_options.get("host", "").startswith("/tmp/"),
            "Refuse a network or non-private PostgreSQL connection",
        )
        self.assertNotIn("hostaddr", connection_options)
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/"))
        self.assertIsNone(self.db.execute("SELECT inet_server_addr()").fetchone()[0])
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("""CREATE TEMP TABLE source_document(
          id text PRIMARY KEY,content bytea NOT NULL,reference_period text,
          kind text NOT NULL,media_type text NOT NULL,metadata jsonb NOT NULL)
        """)
        self.db.execute("""CREATE TEMP TABLE ingestion_asset(
          url text PRIMARY KEY,document_id text,kind text,status text,observed_on date,
          checked_at timestamptz,error text)
        """)
        self.db.execute("""CREATE TEMP TABLE source_ocr_task(
          document_id text,source_locator text,image_id text,source_kind text,
          source_page integer,status text,checked_at timestamptz,error text,
          PRIMARY KEY(document_id,source_locator))
        """)
        self.db.execute("""CREATE TEMP TABLE source_ocr_result(
          image_id text,version text,reading integer,result jsonb,
          PRIMARY KEY(image_id,version,reading))
        """)
        self.db.execute("""CREATE TEMP TABLE official_source_review(
          document_id text,source_locator text,parser_version text,record jsonb,
          reason text,PRIMARY KEY(document_id,source_locator,parser_version))
        """)
        self.db.execute("""CREATE TEMP TABLE source_ocr_scan(
          document_id text,version text,PRIMARY KEY(document_id,version))
        """)
        names = (
            "source_document", "ingestion_asset", "source_ocr_task",
            "source_ocr_result", "official_source_review", "source_ocr_scan",
        )
        for name in names:
            persistence = self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid=%s::regclass",
                (name,),
            ).fetchone()[0]
            self.assertEqual(persistence, "t", name)
        self.original = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), EXACT_SHA)

    def add_source(self, body, pages, *, did=None, status="awaiting-ocr", image_id=None):
        did = did or hashlib.sha256(body).hexdigest()
        url = f"https://example.invalid/{did}.pdf"
        image_id = image_id or hashlib.sha256(b"rendered " + body).hexdigest()
        self.db.execute(
            "INSERT INTO source_document VALUES(%s,%s,'2014-12-31','original','application/pdf',%s)",
            (did, body, Jsonb({"ingestion_kind": "monthly-pdf"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES(%s,%s,'monthly-pdf',%s,'2014-12-31',now(),NULL)",
            (url, did, status),
        )
        for page, task_status, error in pages:
            self.db.execute(
                "INSERT INTO source_ocr_task VALUES(%s,%s,%s,'monthly-pdf',%s,%s,NULL,%s)",
                (did, f"PDF page {page}", image_id, page, task_status, error),
            )
        return did, url, image_id

    def test_full_retained_original_requeues_once_and_preserves_prior_ocr_evidence(self):
        did, url, image_id = self.add_source(
            self.original,
            [(4, "pending", None), (5, "review", "Provider readings disagree")],
            image_id=EXACT_IMAGE_SHA,
        )
        for reading, text in ((0, "DANE"), (1, "DANE Colombia")):
            self.db.execute(
                "INSERT INTO source_ocr_result VALUES(%s,'provider-v1',%s,%s)",
                (image_id, reading, Jsonb({"text": text, "tables": []})),
            )
        before_results = self.db.execute(
            "SELECT reading,result FROM source_ocr_result ORDER BY reading"
        ).fetchall()
        before_original = self.db.execute(
            "SELECT md5(content) FROM source_document WHERE id=%s", (did,)
        ).fetchone()[0]

        summary = monthly_pdf_recovery.retire_tasks(self.db, document_limit=1)
        self.assertEqual(
            summary,
            {"documents": 1, "retired": 2, "eligible": 0,
             "requeued_assets": 1, "errors": 0},
        )
        self.assertEqual(
            self.db.execute("SELECT status,error FROM ingestion_asset WHERE url=%s", (url,)).fetchone(),
            ("pending", monthly_pdf_recovery.REQUEUE_REASON),
        )
        self.assertEqual(
            self.db.execute("SELECT status,error FROM source_ocr_task ORDER BY source_page").fetchall(),
            [("review", ocr.NATIVE_DAILY_REVIEW_REASON)] * 2,
        )
        reviews = self.db.execute(
            "SELECT source_locator,record FROM official_source_review ORDER BY source_locator"
        ).fetchall()
        self.assertEqual(len(reviews), 2)
        self.assertEqual(
            [(r[1]["prior_status"], r[1]["prior_error"]) for r in reviews],
            [("pending", None), ("review", "Provider readings disagree")],
        )
        self.assertEqual(
            self.db.execute("SELECT reading,result FROM source_ocr_result ORDER BY reading").fetchall(),
            before_results,
        )
        self.assertEqual(
            self.db.execute("SELECT md5(content) FROM source_document WHERE id=%s", (did,)).fetchone()[0],
            before_original,
        )
        self.assertEqual(bytes(monthly_pdf_recovery.retained_resume(self.db, url)[0]), self.original)
        self.assertEqual(monthly_pdf_recovery.retire_tasks(self.db),
                         {"documents": 0, "retired": 0, "eligible": 0,
                          "requeued_assets": 0, "errors": 0})
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 2)

    def test_unknown_new_price_raster_cannot_be_requeued(self):
        body = unknown_price_image_pdf()
        did, url, _ = self.add_source(body, [(1, "pending", None)])
        summary = monthly_pdf_recovery.retire_tasks(self.db, document_limit=1)
        self.assertEqual(summary["eligible"], 1)
        self.assertEqual(summary["requeued_assets"], 0)
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (url,)).fetchone()[0],
            "awaiting-ocr",
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s", (did,)).fetchone()[0],
            "pending",
        )
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 0)

    def test_zero_limit_and_deadline_do_not_change_tasks(self):
        did, _, _ = self.add_source(self.original, [(4, "pending", None)])
        for kwargs in ({"document_limit": 0}, {"deadline": time.monotonic() + 20}):
            self.assertEqual(
                monthly_pdf_recovery.retire_tasks(self.db, **kwargs),
                {"documents": 0, "retired": 0, "eligible": 0,
                 "requeued_assets": 0, "errors": 0},
            )
        self.assertEqual(
            self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s", (did,)).fetchone()[0],
            "pending",
        )
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_scan").fetchone()[0], 0)

    def test_batch_size_is_capped_at_eight_documents(self):
        # Distinct trailing comments keep the retained PDF layout unchanged,
        # while giving each TEMP asset a different exact body SHA-256.
        for number in range(9):
            variant = self.original + f"\n% private cap fixture {number}\n".encode()
            self.add_source(variant, [(4, "pending", None)])
        first = monthly_pdf_recovery.retire_tasks(self.db, document_limit=99)
        self.assertEqual((first["documents"], first["retired"],
                          first["requeued_assets"], first["errors"]),
                         (8, 8, 8, 0))
        self.assertEqual(
            self.db.execute("SELECT status,count(*) FROM ingestion_asset GROUP BY status ORDER BY status").fetchall(),
            [("awaiting-ocr", 1), ("pending", 8)],
        )
        second = monthly_pdf_recovery.retire_tasks(self.db, document_limit=99)
        self.assertEqual((second["documents"], second["requeued_assets"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_scan").fetchone()[0], 9)

    def test_task_changed_during_full_pdf_parse_keeps_asset_and_scan_retryable(self):
        did, url, _ = self.add_source(self.original, [(4, "pending", None)])
        parse = worker.parse_pdf_pages
        changed = False

        def interleave(*args, **kwargs):
            nonlocal changed
            if not changed:
                changed = True
                self.db.execute(
                    "UPDATE source_ocr_task SET error='changed while parsing' WHERE document_id=%s",
                    (did,),
                )
            return parse(*args, **kwargs)

        with patch.object(worker, "parse_pdf_pages", side_effect=interleave):
            summary = monthly_pdf_recovery.retire_tasks(self.db, document_limit=1)
        self.assertTrue(changed)
        self.assertEqual(summary["conflicts"], 1)
        self.assertEqual(summary["requeued_assets"], 0)
        self.assertEqual(summary["retired"], 0)
        self.assertEqual(
            self.db.execute("SELECT status,error FROM source_ocr_task WHERE document_id=%s", (did,)).fetchone(),
            ("pending", "changed while parsing"),
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (url,)).fetchone()[0],
            "awaiting-ocr",
        )
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_scan").fetchone()[0], 0)

    def test_mismatched_retained_sha_cannot_requeue_or_resume(self):
        did = "0" * 64
        did, url, _ = self.add_source(self.original, [(4, "pending", None)], did=did)
        summary = monthly_pdf_recovery.retire_tasks(self.db, document_limit=1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["requeued_assets"], 0)
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (url,)).fetchone()[0],
            "awaiting-ocr",
        )
        self.db.execute(
            "UPDATE ingestion_asset SET status='pending',error=%s WHERE url=%s",
            (monthly_pdf_recovery.REQUEUE_REASON, url),
        )
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            monthly_pdf_recovery.retained_resume(self.db, url)


if __name__ == "__main__":
    unittest.main()
