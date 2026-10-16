"""Real worker publication/replay for the eight exact Jan 2020 retained XLS sources."""
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import psycopg

from pipelines.ingestion import daily_recovery, worker
from pipelines.ingestion import queue_plan, retained_date_repairs
from pipelines.ingestion.test_input_pdf_v17_role import install
from .test_daily_jan2020_year_repairs import CASES, SOURCE


@unittest.skipUnless(os.environ.get("AGRO_JAN2020_DATE_REPAIR_PRIVATE_DSN"),
                     "Owned Unix-only PostgreSQL required")
class ActualJan2020WorkerPublication(unittest.TestCase):
    def test_eight_exact_sources_publish_full_rows_and_replay_without_mutation(self):
        dsn = os.environ["AGRO_JAN2020_DATE_REPAIR_PRIVATE_DSN"]
        with psycopg.connect(dsn, autocommit=True) as admin:
            self.assertTrue(admin.info.host.startswith("/tmp/agro-input-v17-owned-"))
            self.assertIsNone(admin.execute("SELECT inet_server_addr()").fetchone()[0])
            self.assertEqual(admin.info.dbname, "postgres")
            install(admin)
            admin.execute("SET statement_timeout=15000")
            admin.execute("SET ROLE agro_ingestor")
            forbidden = AssertionError("Network/OCR escaped exact retained native daily path")
            prepared = []
            for case in CASES:
                url, day, digest = case["url"], case["day"], case["xls_sha"]
                body = (SOURCE / case["xls"]).read_bytes()
                expected = daily_recovery.parse_daily(body, day, source_url=url)["rows"]
                self.assertTrue(expected)
                with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True):
                    self.assertEqual(worker.archive(admin, url, body, "daily", day), digest)
                admin.execute(
                    """INSERT INTO ingestion_asset
                    (url,kind,observed_on,status,processor_version,document_id,records,error)
                    VALUES(%s,'daily',%s,'failed',%s,%s,0,%s)""",
                    (url, day, worker.parser_version("daily"), digest,
                     "ValueError: Daily workbook has no verifiable publication date"),
                )
                prepared.append((case, body, expected))
            def selected_rows():
                return {(url, kind, day) for url, kind, day in
                        queue_plan.daily_candidates(admin, date(2026, 10, 16))}

            expected_repairs = {(case["url"], "daily", case["day"])
                                for case, _, _ in prepared}
            selected = selected_rows()
            self.assertTrue(expected_repairs <= selected)

            # Admission outside the ordinary 14-day window is limited to an
            # exact stale URL/kind/document binding. These adversarial rows
            # must not acquire the narrow repair lane.
            case, _, _ = prepared[0]
            url, day, digest = case["url"], case["day"], case["xls_sha"]
            wrong_digest = next(other["xls_sha"] for other in CASES if other["url"] != url)
            admin.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (wrong_digest, url))
            self.assertNotIn((url, "daily", day), selected_rows())
            admin.execute("UPDATE ingestion_asset SET document_id=%s,kind='daily-pdf' WHERE url=%s",
                          (digest, url))
            self.assertNotIn((url, "daily-pdf", day), selected_rows())
            admin.execute("UPDATE ingestion_asset SET kind='daily',document_id=%s WHERE url=%s",
                          (digest, url))
            alias_url = url + "?alias=1"
            admin.execute("UPDATE ingestion_asset SET url=%s WHERE url=%s", (alias_url, url))
            self.assertNotIn((alias_url, "daily", day), selected_rows())
            admin.execute("UPDATE ingestion_asset SET url=%s WHERE url=%s", (url, alias_url))
            admin.execute(
                "UPDATE ingestion_asset SET status='complete',processor_version=%s,checked_at=now() WHERE url=%s",
                (worker.asset_parser_version("daily", url), url),
            )
            self.assertNotIn((url, "daily", day), selected_rows())
            admin.execute(
                "UPDATE ingestion_asset SET status='failed',processor_version=%s,checked_at=NULL,error=%s WHERE url=%s",
                (worker.parser_version("daily"),
                 "ValueError: Daily workbook has no verifiable publication date", url),
            )
            self.assertIn((url, "daily", day), selected_rows())
            for case, body, expected in prepared:
                url, day, digest = case["url"], case["day"], case["xls_sha"]
                # A stale asset cannot borrow the approved body through a different DID.
                wrong_digest = next(other["xls_sha"] for other in CASES if other["url"] != url)
                admin.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (wrong_digest, url))
                expected_version = worker.asset_parser_version("daily", url)
                self.assertIsNone(retained_date_repairs.retained_exact_date_repair(
                    admin, url, "daily", expected_version))
                self.assertIsNone(retained_date_repairs.retained_exact_date_repair(
                    admin, url + "?alias=1", "daily", expected_version))
                admin.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (digest, url))
                source_before = admin.execute(
                    "SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s",
                    (digest,),
                ).fetchone()
                with patch.object(worker, "_get", side_effect=forbidden), \
                     patch.object(worker.SESSION, "request", side_effect=forbidden), \
                     patch("pipelines.ingestion.ocr.transcribe", side_effect=forbidden), \
                     patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True):
                    self.assertEqual(worker.process_asset(admin, url, "daily", day), len(expected))
                actual = admin.execute(
                    """SELECT source_locator,series,observed_on,product_name,market_name,unit,
                       price,change_percent,details FROM historical_price
                       WHERE document_id=%s ORDER BY source_locator""",
                    (digest,),
                ).fetchall()
                self.assertEqual(len(actual), len(expected), url)
                by_locator = {row[0]: row for row in expected}
                for row in actual:
                    wanted = by_locator[row[0]]
                    self.assertEqual(row[:6], wanted[:6])
                    self.assertEqual(float(row[6]), wanted[6])
                    self.assertEqual(float(row[7]) if row[7] is not None else None, wanted[7])
                    self.assertEqual(row[8], wanted[8])
                self.assertEqual(
                    admin.execute("SELECT count(*) FROM daily_price WHERE document_id=%s", (digest,)).fetchone()[0],
                    len(expected),
                )
                self.assertEqual(
                    admin.execute("SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s", (url,)).fetchone(),
                    ("complete", len(expected), worker.asset_parser_version("daily", url)),
                )
                history_before = admin.execute(
                    "SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h "
                    "WHERE document_id=%s ORDER BY source_locator", (digest,),
                ).fetchall()
                response = SimpleNamespace(status_code=200, content=body, headers={},
                                           close=lambda: None, raise_for_status=lambda: None)
                with patch.object(worker, "_get", return_value=response), \
                     patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=True), \
                     patch("pipelines.ingestion.ocr.transcribe", side_effect=forbidden):
                    self.assertEqual(worker.process_asset(admin, url, "daily", day), 0)
                self.assertEqual(
                    admin.execute("SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h "
                                  "WHERE document_id=%s ORDER BY source_locator", (digest,)).fetchall(),
                    history_before,
                )
                self.assertEqual(
                    admin.execute("SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s",
                                  (digest,)).fetchone(),
                    source_before,
                )


if __name__ == "__main__":
    unittest.main()
