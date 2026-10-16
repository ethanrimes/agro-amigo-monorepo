"""Two distinct later city ZIPs related to publisher-linked missing PDFs.

Opt in with a fresh owned full-schema PostgreSQL DSN. No DANE, Blob, OCR,
provider, or production access. The caller creates/stops the disposable DB.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pdfplumber
import psycopg
import requests
from psycopg.types.json import Jsonb

from . import city_pdf_related_originals, city_reports, queue_plan, worker


FIXTURES = Path(__file__).parent / "testdata" / "city_pdf_related"
RULES = Path(__file__).with_name("reviewed_city_pdf_related.json")


def _insert_original(db, did, url, media, kind, body, pages, metadata, name):
    db.execute(
        "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
        "reference_period,page_count,content,metadata) "
        "VALUES(%s,%s,'DANE',%s,%s,'original','source-bound fixture',%s,%s,%s)",
        (did, "DANE - " + name, url, media, pages, body, Jsonb(metadata)),
    )


@unittest.skipUnless(os.environ.get("AGRO_CITY_LINK_TEST_DSN"),
                     "Fresh owned full-schema city-link DSN required")
class MissingCityPDFRelatedOriginalsPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_CITY_LINK_TEST_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (
            not str(cls.db.info.host).startswith("/tmp/agro-city-link-")
            or not cls.db.info.dbname.startswith("agro_city_link_")
            or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
        ):
            cls.db.close()
            raise RuntimeError("City-link test requires its own Unix-only database")
        for table in ("source_document", "ingestion_asset", "regional_price",
                      "regional_classification", "retained_record"):
            if cls.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                cls.db.close()
                raise RuntimeError("City-link test database must begin empty")
        cls.rules = json.loads(RULES.read_text())["rules"]
        cls.db.execute("SET statement_timeout='30s'")
        cls.db.execute("SET lock_timeout='2s'")
        cls("test_actual_worker_review_rollback_source_parity_and_rerun")._seed()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _seed(self):
        db = self.db
        for rule in self.rules:
            day = date.fromisoformat(rule["later_zip_day"])
            filename = rule["later_zip_url"].rsplit("/", 1)[-1]
            body = (FIXTURES / filename).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), rule["later_zip_id"])
            _insert_original(
                db, rule["later_zip_id"], rule["later_zip_url"],
                "application/zip", "city-zip", body, None,
                {"ingestion_kind": "city-zip", "retention": "permanent",
                 "original_filename": filename}, filename,
            )
            db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,"
                "document_id,records,checked_at) "
                "VALUES(%s,'city-zip',%s,'complete',%s,%s,%s,now())",
                (rule["later_zip_url"], day, rule["later_zip_asset_version"],
                 rule["later_zip_id"], rule["later_zip_asset_records"]),
            )
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                for child in rule["children"]:
                    member = archive.getinfo(child["filename"])
                    pdf_body = archive.read(member)
                    self.assertEqual(hashlib.sha256(pdf_body).hexdigest(), child["document_id"])
                    with pdfplumber.open(io.BytesIO(pdf_body)) as pdf:
                        rows = list(city_reports.parse_city_pages(pdf.pages, day))
                        pages = len(pdf.pages)
                    self.assertEqual(len(rows), child["native_rows"])
                    _insert_original(
                        db, child["document_id"], rule["later_zip_url"],
                        "application/pdf", "city-pdf", pdf_body, pages,
                        {"ingestion_kind": "city-pdf", "retention": "permanent",
                         "parents": [rule["later_zip_id"]],
                         "archive_entry": child["filename"],
                         "original_filename": child["filename"]}, child["filename"],
                    )
                    db.execute("INSERT INTO source_archive_member VALUES(%s,%s,%s)",
                               (rule["later_zip_id"], child["filename"], child["document_id"]))
                    with db.transaction():
                        city_reports.save_classifications(db, child["document_id"], rows)
                        city_reports._bulk_insert(
                            db, "regional_price",
                            ((child["document_id"], *row) for row in rows),
                        )
            db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,"
                "document_id,records,error,checked_at,attempts) "
                "VALUES(%s,'city-pdf',%s,'failed','city-direct-pdf-v1',NULL,0,"
                "'HTTPError: 404 Client Error: Not Found',now()-interval '7 hours',1)",
                (rule["missing_url"], date.fromisoformat(rule["requested_day"])),
            )
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE processor_version='city-v3' "
            "AND step LIKE 'city-member:%%'").fetchone()[0], 0)

    def _attempt(self, rule):
        response = requests.Response()
        response.status_code = 404
        response.url = rule["missing_url"]
        failure = requests.HTTPError("404 Client Error", response=response)
        with patch.object(worker, "fetch_asset", side_effect=failure):
            return worker.process_asset(
                self.db, rule["missing_url"], "city-pdf",
                date.fromisoformat(rule["requested_day"]),
            )

    def test_actual_worker_review_rollback_source_parity_and_rerun(self):
        db = self.db
        children = [c["document_id"] for r in self.rules for c in r["children"]]
        before = {
            "original": dict(db.execute(
                "SELECT id,xmin::text FROM source_document WHERE id=ANY(%s)",
                (children,),
            ).fetchall()),
            "raw": dict(db.execute(
                "SELECT document_id||':'||source_locator,xmin::text FROM regional_price "
                "WHERE document_id=ANY(%s)", (children,),
            ).fetchall()),
            "class": dict(db.execute(
                "SELECT document_id||':'||source_locator,xmin::text "
                "FROM regional_classification WHERE document_id=ANY(%s)",
                (children,),
            ).fetchall()),
        }
        self.assertEqual([len(before[k]) for k in before], [42, 2020, 2020])
        self.assertEqual(db.execute(
            "SELECT count(*) FROM published_regional_price WHERE document_id=ANY(%s)",
            (children,),
        ).fetchone()[0], 2020)

        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agro_ingestor")
        db.execute("GRANT UPDATE ON ingestion_asset TO agro_ingestor")
        db.execute("GRANT INSERT ON retained_record TO agro_ingestor")
        for table in ("source_document", "source_archive_member"):
            self.assertFalse(db.execute(
                "SELECT has_table_privilege('agro_ingestor',%s,'UPDATE')",
                (table,),
            ).fetchone()[0])
        db.execute("SET ROLE agro_ingestor")
        try:
            for rule in self.rules:
                url = rule["missing_url"]
                failed = db.execute(
                    "SELECT status,document_id,records,error FROM ingestion_asset "
                    "WHERE url=%s", (url,),
                ).fetchone()
                with self.assertRaisesRegex(RuntimeError, "forced rollback"):
                    with db.transaction():
                        self.assertEqual(self._attempt(rule), 0)
                        with psycopg.connect(self.dsn, autocommit=True) as reader:
                            reader.execute("SET ROLE agro_reader")
                            self.assertEqual(reader.execute(
                                "SELECT count(*) FROM published_regional_price "
                                "WHERE document_id=ANY(%s)", (children,),
                            ).fetchone()[0], 2020)
                            self.assertEqual(reader.execute(
                                "SELECT status FROM ingestion_asset WHERE url=%s",
                                (url,),
                            ).fetchone()[0], "failed")
                        raise RuntimeError("forced rollback")
                self.assertEqual(db.execute(
                    "SELECT status,document_id,records,error FROM ingestion_asset "
                    "WHERE url=%s", (url,),
                ).fetchone(), failed)
                self.assertEqual(self._attempt(rule), 0)
                status = db.execute(
                    "SELECT status,document_id,records,processor_version "
                    "FROM ingestion_asset WHERE url=%s", (url,),
                ).fetchone()
                self.assertEqual(status, ("review", None, 0, "city-direct-pdf-v1"))
                (record,) = db.execute(
                    "SELECT record FROM retained_record "
                    "WHERE table_name='source_link_related_originals' "
                    "AND record->>'missing_url'=%s", (url,),
                ).fetchone()
                self.assertEqual(record["later_zip_kind"], "city-zip")
                self.assertEqual(record["related_child_document_ids"],
                                 rule["related_label_child_ids"])
                self.assertFalse(record["missing_pdf_bytes_recovered"])
                self.assertFalse(record["missing_pdf_complete_roster_known"])
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM source_document WHERE source_url=%s",
                    (url,),
                ).fetchone()[0], 0)
                for did in record["related_child_document_ids"]:
                    self.assertEqual(db.execute(
                        "SELECT kind,media_type,source_url FROM source_document WHERE id=%s",
                        (did,),
                    ).fetchone(), ("original", "application/pdf", rule["later_zip_url"]))
                self.assertEqual(self._attempt(rule), 0)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM retained_record "
                    "WHERE table_name='source_link_related_originals' "
                    "AND record->>'missing_url'=%s", (url,),
                ).fetchone()[0], 1)
                self.assertNotIn(url, [x[0] for x in queue_plan.backfill_candidates(db, 20)])
                with self.assertRaisesRegex(RuntimeError, "cooldown rollback"):
                    with db.transaction():
                        db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '31 days' "
                                   "WHERE url=%s", (url,))
                        self.assertIn(url, [x[0] for x in queue_plan.backfill_candidates(db, 20)])
                        raise RuntimeError("cooldown rollback")
        finally:
            db.execute("RESET ROLE")
        after = {
            "original": dict(db.execute(
                "SELECT id,xmin::text FROM source_document WHERE id=ANY(%s)",
                (children,),
            ).fetchall()),
            "raw": dict(db.execute(
                "SELECT document_id||':'||source_locator,xmin::text FROM regional_price "
                "WHERE document_id=ANY(%s)", (children,),
            ).fetchall()),
            "class": dict(db.execute(
                "SELECT document_id||':'||source_locator,xmin::text "
                "FROM regional_classification WHERE document_id=ANY(%s)",
                (children,),
            ).fetchall()),
        }
        self.assertEqual(after, before)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM published_regional_price WHERE document_id=ANY(%s)",
            (children,),
        ).fetchone()[0], 2020)

    def test_later_http_200_uses_direct_pdf_route_not_related_zip(self):
        """Synthetic transport routing only; no claim that DANE's missing PDF returned."""
        from . import city_direct_pdf

        rule = self.rules[0]
        url = rule["missing_url"]
        day = date.fromisoformat(rule["requested_day"])
        synthetic_body = b"%PDF-1.4\n% synthetic future transport fixture\n"
        synthetic_id = hashlib.sha256(synthetic_body).hexdigest()
        before = self.db.execute(
            "SELECT status,document_id,records FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone()
        evidence_count = self.db.execute(
            "SELECT count(*) FROM retained_record "
            "WHERE table_name='source_link_related_originals'",
        ).fetchone()[0]
        def archive_synthetic(db, archive_url, body, kind, archive_day):
            self.assertEqual((archive_url, body, kind, archive_day),
                             (url, synthetic_body, "city-pdf", day))
            _insert_original(
                db, synthetic_id, url, "application/pdf", "city-pdf",
                synthetic_body, 1,
                {"ingestion_kind": "city-pdf", "retention": "permanent",
                 "original_filename": url.rsplit("/", 1)[-1]},
                "synthetic future response",
            )
            return synthetic_id
        with self.assertRaisesRegex(RuntimeError, "rollback synthetic HTTP 200"):
            with self.db.transaction():
                with patch.object(worker, "fetch_asset", return_value=synthetic_body), \
                     patch.object(worker, "archive", side_effect=archive_synthetic) as archive, \
                     patch.object(city_direct_pdf, "process_direct_city_pdf",
                                  return_value={"rows": 0}) as direct:
                    self.assertEqual(worker.process_asset(self.db, url, "city-pdf", day), 0)
                archive.assert_called_once()
                direct.assert_called_once_with(
                    self.db, url, synthetic_body, day, archived_did=synthetic_id,
                )
                raise RuntimeError("rollback synthetic HTTP 200")
        self.assertEqual(self.db.execute(
            "SELECT status,document_id,records FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), before)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM retained_record "
            "WHERE table_name='source_link_related_originals'",
        ).fetchone()[0], evidence_count)

    def test_same_original_current_city_version_needs_exact_member_steps(self):
        from . import city_reports

        db = self.db
        rule = self.rules[0]
        zip_id = rule["later_zip_id"]
        with self.assertRaisesRegex(RuntimeError, "rollback current-version probe"):
            with db.transaction():
                db.execute(
                    "UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                    (city_reports.VERSION, rule["later_zip_url"]),
                )
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    self._attempt(rule)
                body = (FIXTURES / rule["later_zip_url"].rsplit("/", 1)[-1]).read_bytes()
                steps = []
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    for child in rule["children"]:
                        steps.append((city_reports._member_step(
                            archive.getinfo(child["filename"]),
                            date.fromisoformat(rule["later_zip_day"])),
                            child["native_rows"]))
                self.assertEqual(len(steps), rule["requested_day_child_count"])
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                        "VALUES(%s,%s,%s,%s)",
                        [(zip_id, city_reports.VERSION, step, count)
                         for step, count in steps[:-1]],
                    )
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    self._attempt(rule)
                db.execute(
                    "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                    "VALUES(%s,%s,%s,%s)",
                    (zip_id, city_reports.VERSION, *steps[-1]),
                )
                db.execute(
                    "UPDATE ingestion_checkpoint SET records=records+1 "
                    "WHERE document_id=%s AND processor_version=%s AND step=%s",
                    (zip_id, city_reports.VERSION, steps[0][0]),
                )
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    self._attempt(rule)
                db.execute(
                    "UPDATE ingestion_checkpoint SET records=%s "
                    "WHERE document_id=%s AND processor_version=%s AND step=%s",
                    (steps[0][1], zip_id, city_reports.VERSION, steps[0][0]),
                )
                self.assertEqual(self._attempt(rule), 0)
                (record,) = db.execute(
                    "SELECT record FROM retained_record "
                    "WHERE table_name='source_link_related_originals' "
                    "AND record->>'missing_url'=%s "
                    "AND record->>'current_city_member_checkpoints_checked'=%s",
                    (rule["missing_url"], str(len(steps))),
                ).fetchone()
                self.assertEqual(record["current_city_member_checkpoints_checked"], len(steps))
                db.execute(
                    "UPDATE ingestion_asset SET processor_version='city-v9' WHERE url=%s",
                    (rule["later_zip_url"],),
                )
                with self.assertRaisesRegex(ValueError, "exact completed source revision"):
                    self._attempt(rule)
                raise RuntimeError("rollback current-version probe")


if __name__ == "__main__":
    unittest.main()
