"""TEMP-PostgreSQL exercise of the exact retained Wuxal worker replay route."""

import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import inputs, pdf_sources, worker
from .input_pdf_v17_replay import VERSION as GENERIC_INPUT_VERSION
from .reviewed_wuxal_apr2015 import (
    COMMERCIAL_NAME, DAY, FULL_PDF_ROWS, OLD_VERSION, PRINTED_NAME,
    SHA256, URL, VERSION,
)


PDF = Path(__file__).parent / "testdata" / f"{SHA256}.pdf"
FEB_2016_SHA = "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"
FEB_2016_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Bol_Insumos_feb_2016.pdf"
)


@unittest.skipUnless(
    os.environ.get("AGRO_WUXAL_APR2015_POSTGRES_TEST") == "1",
    "Explicit private PostgreSQL TEMP-only opt-in",
)
class ReviewedWuxalWorkerRoute(unittest.TestCase):
    def setUp(self):
        from .test_input_pdf_publication import InputPDFPublication
        from .test_reviewed_wuxal_apr2015 import require_private_temp_postgres

        dsn = os.environ.get("DATABASE_URL", "")
        self.assertTrue("host=/tmp/agro-wuxal-" in dsn or
                        "host=/tmp/agro-unified-catalog-pg-v24-20261004" in dsn)
        InputPDFPublication.setUp(self)
        require_private_temp_postgres(self.db)
        self.db.execute("SET statement_timeout='180s'")
        self.db.execute("""ALTER TABLE source_document ADD COLUMN content bytea;
            ALTER TABLE source_document ADD COLUMN kind text;
            ALTER TABLE source_document ADD COLUMN source_url text;
            ALTER TABLE source_document ADD COLUMN media_type text;
            ALTER TABLE source_document ADD COLUMN metadata jsonb;
            ALTER TABLE source_document ADD COLUMN page_count integer;
            ALTER TABLE source_document ADD COLUMN title text;
            ALTER TABLE source_document ADD COLUMN publisher text;
            ALTER TABLE source_document ADD COLUMN reference_period text;
            ALTER TABLE ingestion_asset ADD COLUMN url text UNIQUE;
            ALTER TABLE ingestion_asset ADD COLUMN observed_on date;
            ALTER TABLE ingestion_asset ADD COLUMN records bigint;
            ALTER TABLE ingestion_asset ADD COLUMN error text;
            ALTER TABLE ingestion_asset ADD COLUMN checked_at timestamptz;
            ALTER TABLE ingestion_asset ADD COLUMN attempts integer DEFAULT 0;
            CREATE TEMP TABLE input_identity_alias(legacy_id text,id text,PRIMARY KEY(legacy_id,id));""")
        self.body = PDF.read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), SHA256)
        self.db.execute(
            """INSERT INTO source_document(id,retrieved_at,content,kind,source_url,media_type,metadata)
               VALUES(%s,'2026-09-01T00:00:00Z',%s,'original',%s,'application/pdf',
                      '{"ingestion_kind":"inputs-pdf"}'::jsonb)""",
            (SHA256, self.body, URL),
        )
        self.db.execute(
            """INSERT INTO ingestion_asset(document_id,kind,processor_version,status,
                       url,observed_on,records,error,attempts)
               VALUES(%s,'inputs-pdf',%s,'complete',%s,%s,6085,NULL,0)""",
            (SHA256, OLD_VERSION, URL, DAY),
        )

    def test_process_asset_replays_exact_retained_original_and_publishes_full_v15(self):
        archived = []
        projected = []
        real_project = inputs.project_pdf_inputs

        def archive(db, url, body, kind, day):
            archived.append((url, kind, day, hashlib.sha256(body).hexdigest()))
            return SHA256

        def project(db, did, *, source_url, staged=False):
            projected.append((did, source_url, staged))
            self.assertFalse(staged, "exact v15 retained replay uses its source-bound direct projection")
            return real_project(db, did, source_url=source_url, staged=staged)

        with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")) as fetch, \
             patch.object(worker, "archive", side_effect=archive), \
             patch.object(pdf_sources, "extract_pages", return_value=0), \
             patch.object(inputs, "project_pdf_inputs", side_effect=project):
            self.assertTrue(worker.retained_reparse_during_host_cooldown(
                self.db, URL, "inputs-pdf"))
            self.assertEqual(worker.process_asset(self.db, URL, "inputs-pdf", DAY), FULL_PDF_ROWS)
            fetch.assert_not_called()
        self.assertEqual(archived, [(URL, "inputs-pdf", DAY, SHA256)])
        self.assertEqual(projected, [(SHA256, URL, False)])
        self.assertEqual(self.db.execute(
            "SELECT processor_version,status,records FROM ingestion_asset WHERE url=%s",
            (URL,),
        ).fetchone(), (VERSION, "complete", FULL_PDF_ROWS))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='inputs-pdf:published'",
            (SHA256, VERSION),
        ).fetchone(), (FULL_PDF_ROWS,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'=%s", (SHA256, VERSION),
        ).fetchone(), (FULL_PDF_ROWS,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM published_input_municipal_price WHERE name=%s",
            (COMMERCIAL_NAME,),
        ).fetchone(), (47,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM published_input_municipal_price WHERE name=%s",
            (PRINTED_NAME,),
        ).fetchone(), (0,))

    def test_corrupt_retained_pointer_fails_before_any_http_or_publication(self):
        self.db.execute("UPDATE source_document SET content=content || '\\x00'::bytea WHERE id=%s", (SHA256,))
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")) as fetch, \
             patch.object(worker, "archive", side_effect=AssertionError("archive forbidden")), \
             patch.object(pdf_sources, "extract_pages", side_effect=AssertionError("parse forbidden")):
            self.assertTrue(worker.retained_reparse_during_host_cooldown(
                self.db, URL, "inputs-pdf"))
            with self.assertRaisesRegex(ValueError, "retained|Retained"):
                worker.process_asset(self.db, URL, "inputs-pdf", DAY)
            fetch.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE processor_version=%s", (VERSION,),
        ).fetchone(), (0,))

    def test_changed_pointer_and_alias_cannot_take_retained_v15_route(self):
        with patch.object(worker, "fetch_asset", side_effect=RuntimeError("ordinary HTTP path")) as fetch, \
             patch.object(worker, "archive", side_effect=AssertionError("archive forbidden")):
            self.db.execute("UPDATE ingestion_asset SET observed_on=%s WHERE url=%s",
                            (DAY.replace(day=29), URL))
            self.assertFalse(worker.retained_reparse_during_host_cooldown(
                self.db, URL, "inputs-pdf"))
            with self.assertRaisesRegex(RuntimeError, "ordinary HTTP path"):
                worker._process_asset(self.db, URL, "inputs-pdf", DAY)
            self.db.execute("UPDATE ingestion_asset SET observed_on=%s,document_id='changed' WHERE url=%s",
                            (DAY, URL))
            with self.assertRaisesRegex(RuntimeError, "ordinary HTTP path"):
                worker._process_asset(self.db, URL, "inputs-pdf", DAY)
            fetch.assert_called()
        self.assertEqual(worker.asset_parser_version("inputs-pdf", URL + "?alias=1"), GENERIC_INPUT_VERSION)
        self.assertEqual(worker.asset_parser_version("inputs-pdf", URL), VERSION)
        self.assertEqual(pdf_sources.INPUT_PDF_VERSION, OLD_VERSION)

    def test_unrelated_real_pdf_uses_ordinary_v17_worker_route(self):
        body = (PDF.parent / f"{FEB_2016_SHA}.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), FEB_2016_SHA)
        day = date(2016, 2, 29)
        self.db.execute(
            """INSERT INTO source_document(id,retrieved_at,content,kind,source_url,media_type,metadata)
               VALUES(%s,'2026-09-03T00:00:00Z',%s,'original',%s,'application/pdf',
                      '{"ingestion_kind":"inputs-pdf"}'::jsonb)""",
            (FEB_2016_SHA, body, FEB_2016_URL),
        )
        self.db.execute(
            """INSERT INTO ingestion_asset(document_id,kind,processor_version,status,
                       url,observed_on,records,error,attempts)
               VALUES(%s,'inputs-pdf','inputs-pdf-v13','complete',%s,%s,0,NULL,0)""",
            (FEB_2016_SHA, FEB_2016_URL, day),
        )
        real_project = inputs.project_pdf_inputs
        forwarded = []

        def project(db, did, *, source_url, staged=False):
            forwarded.append((did, source_url, staged))
            self.assertTrue(staged, "generic v17 projection must stage before publication")
            return real_project(db, did, source_url=source_url, staged=staged)

        with patch.object(worker, "fetch_asset", return_value=body) as fetch, \
             patch.object(worker, "archive", return_value=FEB_2016_SHA), \
             patch.object(pdf_sources, "extract_pages", return_value=0), \
             patch.object(inputs, "project_pdf_inputs", side_effect=project):
            self.assertFalse(worker.retained_reparse_during_host_cooldown(
                self.db, FEB_2016_URL, "inputs-pdf"))
            count = worker.process_asset(self.db, FEB_2016_URL, "inputs-pdf", day)
            fetch.assert_called_once()
        self.assertGreater(count, 1000)
        self.assertEqual(forwarded, [(FEB_2016_SHA, FEB_2016_URL, True)])
        self.assertEqual(self.db.execute(
            "SELECT processor_version,status,records FROM ingestion_asset WHERE url=%s",
            (FEB_2016_URL,),
        ).fetchone(), (GENERIC_INPUT_VERSION, "complete", count))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'=%s", (FEB_2016_SHA, GENERIC_INPUT_VERSION),
        ).fetchone(), (count,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='inputs-pdf:published'",
            (FEB_2016_SHA, GENERIC_INPUT_VERSION),
        ).fetchone(), (1,))


if __name__ == "__main__":
    unittest.main()
