"""Owned PostgreSQL publication of the one reviewed February 2020 original."""
import os
import hashlib
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import psycopg

from pipelines.ingestion import daily_recovery, queue_plan, retained_date_repairs, worker
from pipelines.ingestion.test_daily_feb2020_day03_year_repair import SHA, SOURCE, URL
from pipelines.ingestion.test_input_pdf_v17_role import install


@unittest.skipUnless(os.environ.get("AGRO_FEB2020_DATE_REPAIR_PRIVATE_DSN"),
                     "Owned Unix-only PostgreSQL required")
class ActualFeb2020Day03WorkerPublication(unittest.TestCase):
    def test_exact_source_publishes_384_rows_and_replays_without_mutation(self):
        dsn = os.environ["AGRO_FEB2020_DATE_REPAIR_PRIVATE_DSN"]
        day = date(2020, 2, 3)
        body = (SOURCE / "mayoristas_febrero_03_2020.xlsx").read_bytes()
        expected = daily_recovery.parse_daily(body, day, source_url=URL)["rows"]
        self.assertEqual(len(expected), 384)
        with psycopg.connect(dsn, autocommit=True) as db:
            self.assertTrue(db.info.host.startswith("/tmp/agro-feb2020-date-owned-"))
            self.assertIsNone(db.execute("SELECT inet_server_addr()").fetchone()[0])
            self.assertEqual(db.info.dbname, "postgres")
            install(db)
            db.execute("SET statement_timeout=15000")
            db.execute("SET ROLE agro_ingestor")
            with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True):
                self.assertEqual(worker.archive(db, URL, body, "daily", day), SHA)
            db.execute(
                """INSERT INTO ingestion_asset
                   (url,kind,observed_on,status,processor_version,document_id,records,error)
                   VALUES(%s,'daily',%s,'failed',%s,%s,0,%s)""",
                (URL, day, worker.parser_version("daily"), SHA,
                 "ValueError: Daily link date differs from native workbook heading"),
            )

            selected = {(u, k, d) for u, k, d in queue_plan.daily_candidates(db, date(2026, 10, 16))}
            self.assertIn((URL, "daily", day), selected)
            expected_version = worker.asset_parser_version("daily", URL)
            self.assertEqual(expected_version, worker.parser_version("daily") + ":feb2020-day03-native-year-review-v1")
            self.assertEqual(retained_date_repairs.retained_exact_date_repair(db, URL, "daily", expected_version), body)
            self.assertIsNone(retained_date_repairs.retained_exact_date_repair(db, URL + "?alias=1", "daily", expected_version))

            other_url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_19_2020.xlsx"
            other_body = (SOURCE / "mayoristas_febrero_19_2020.xlsx").read_bytes()
            other_sha = hashlib.sha256(other_body).hexdigest()
            with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True):
                self.assertEqual(worker.archive(db, other_url, other_body, "daily", date(2020, 2, 19)), other_sha)
            db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (other_sha, URL))
            selected_wrong_document = {(u, k, d) for u, k, d in queue_plan.daily_candidates(db, date(2026, 10, 16))}
            self.assertNotIn((URL, "daily", day), selected_wrong_document)
            self.assertIsNone(retained_date_repairs.retained_exact_date_repair(db, URL, "daily", expected_version))
            db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (SHA, URL))

            forbid = AssertionError("Unexpected provider or OCR call in exact retained workbook replay")
            with patch.object(worker, "_get", side_effect=forbid), \
                 patch.object(worker.SESSION, "request", side_effect=forbid), \
                 patch("pipelines.ingestion.ocr.transcribe", side_effect=forbid), \
                 patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True):
                self.assertEqual(worker.process_asset(db, URL, "daily", day), len(expected))

            rows = db.execute(
                """SELECT source_locator,series,observed_on,product_name,market_name,unit,
                          price,change_percent,details
                   FROM historical_price WHERE document_id=%s ORDER BY source_locator""",
                (SHA,),
            ).fetchall()
            self.assertEqual(len(rows), 384)
            expected_by_locator = {row[0]: row for row in expected}
            self.assertEqual(set(expected_by_locator), {row[0] for row in rows})
            for row in rows:
                wanted = expected_by_locator[row[0]]
                self.assertEqual(row[:6], wanted[:6])
                self.assertEqual(float(row[6]), wanted[6])
                self.assertEqual(float(row[7]) if row[7] is not None else None, wanted[7])
                self.assertEqual(row[8], wanted[8])
            self.assertEqual(db.execute(
                "SELECT count(*) FROM daily_price WHERE document_id=%s", (SHA,)
            ).fetchone()[0], 384)
            self.assertEqual(db.execute(
                "SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s", (URL,)
            ).fetchone(), ("complete", 384, expected_version))
            completed_selection = {(u, k, d) for u, k, d in queue_plan.daily_candidates(db, date(2026, 10, 16))}
            self.assertNotIn((URL, "daily", day), completed_selection)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s", (SHA,)
            ).fetchone()[0], 0)

            history_before = db.execute(
                "SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h "
                "WHERE document_id=%s ORDER BY source_locator", (SHA,),
            ).fetchall()
            original_before = db.execute(
                "SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s", (SHA,),
            ).fetchone()
            response = SimpleNamespace(status_code=200, content=body, headers={}, close=lambda: None,
                                       raise_for_status=lambda: None)
            with patch.object(worker, "_get", return_value=response), \
                 patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True), \
                 patch("pipelines.ingestion.ocr.transcribe", side_effect=forbid):
                self.assertEqual(worker.process_asset(db, URL, "daily", day), 0)
            self.assertEqual(db.execute(
                "SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h "
                "WHERE document_id=%s ORDER BY source_locator", (SHA,),
            ).fetchall(), history_before)
            self.assertEqual(db.execute(
                "SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s", (SHA,),
            ).fetchone(), original_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
