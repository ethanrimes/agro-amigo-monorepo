"""Original-byte and full-grid guards for three publisher-misdated city ZIPs."""

import io
import json
import hashlib
import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from psycopg.types.json import Jsonb

from . import city_reports, queue_plan, reviewed_city_dates as reviews, worker
from .worker import SourceDateMismatch

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "testdata/city_reviewed_dates_202202"
NEXTDAY_FIXTURES = ROOT / "testdata/city_reviewed_dates_nextday"


class ReviewedCityDates(unittest.TestCase):
    def setUp(self):
        self.archives = json.loads((ROOT / "reviewed_city_dates.json").read_text())["archives"]

    def test_exact_41_originals_retain_actual_printed_dates_and_4330_prices(self):
        total = 0
        children = 0
        for archive in self.archives:
            fixture = FIXTURES / (archive["archive_id"] + ".zip")
            if not fixture.exists():
                fixture = NEXTDAY_FIXTURES / fixture.name
            body = fixture.read_bytes()
            parent = reviews.reviewed_parent(body, archive["archive_id"], archive["url"], date.fromisoformat(archive["archive_day"]))
            self.assertEqual(parent, archive)
            with zipfile.ZipFile(io.BytesIO(body)) as bundle:
                for member in archive["members"]:
                    with self.subTest(member=member["entry_name"]):
                        child = bundle.read(member["entry_name"])
                        self.assertEqual(reviews.reviewed_member(parent, member["entry_name"], child), member)
                        with self.assertRaises(SourceDateMismatch):
                            list(city_reports.parse_city_pdf(child, date.fromisoformat(archive["archive_day"])))
                        rows = list(city_reports.parse_city_pdf(child, date.fromisoformat(member["printed_day"])))
                        reviews.validate_rows(member, rows)
                        self.assertEqual(reviews.source_review(parent, member)["error_type"], "SourceDateMismatch")
                        total += len(rows)
                        children += 1
        self.assertEqual((len(self.archives), children, total), (6, 41, 4330))

    def test_changed_zip_url_day_hash_or_bytes_has_no_exception(self):
        a = self.archives[0]
        body = (FIXTURES / (a["archive_id"] + ".zip")).read_bytes()
        day = date.fromisoformat(a["archive_day"])
        for args in (
            (body, a["archive_id"], a["url"].replace("2021", "2022"), day),
            (body, a["archive_id"], a["url"], date(2022, 2, 2)),
            (body, "0" * 64, a["url"], day),
            (body + b"changed revision", a["archive_id"], a["url"], day),
        ):
            with self.subTest(args=args[1:]):
                self.assertIsNone(reviews.reviewed_parent(*args))

    def test_changed_member_name_or_pdf_has_no_exception(self):
        a = self.archives[0]
        member = a["members"][0]
        with zipfile.ZipFile(FIXTURES / (a["archive_id"] + ".zip")) as bundle:
            child = bundle.read(member["entry_name"])
        self.assertIsNone(reviews.reviewed_member(None, member["entry_name"], child))
        self.assertIsNone(reviews.reviewed_member(a, member["entry_name"].upper(), child))
        self.assertIsNone(reviews.reviewed_member(a, member["entry_name"], child + b"changed revision"))

    def test_incomplete_or_changed_typed_price_grid_cannot_publish(self):
        a = self.archives[0]
        member = a["members"][0]
        with zipfile.ZipFile(FIXTURES / (a["archive_id"] + ".zip")) as bundle:
            rows = list(city_reports.parse_city_pdf(bundle.read(member["entry_name"]), date.fromisoformat(member["printed_day"])))
        for candidate in ([], rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                reviews.validate_rows(member, candidate)
        for field in range(17):
            with self.subTest(field=field):
                first = list(rows[0])
                value = first[field]
                first[field] = (
                    date(2021, 2, 2) if isinstance(value, date)
                    else value + 1 if isinstance(value, (Decimal, int))
                    else "changed typed field" if value is not None else Decimal(1)
                )
                with self.assertRaises(ValueError):
                    reviews.validate_rows(member, [tuple(first), *rows[1:]])


@unittest.skipUnless(os.environ.get("AGRO_REPAIR_QUEUE_POSTGRES_TEST") == "1",
                     "Explicit opt-in for private PostgreSQL TEMP queue controls")
class ReviewedCityRecoveryQueue(unittest.TestCase):
    URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-10-02-2021.zip"
    SHA = "2ca39b0eacb32edb497e0be527f93e581de9edecdd5364cda7b7ba7b381a1857"

    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.assertIsNone(self.db.execute("SELECT inet_server_addr()").fetchone()[0])
        self.db.execute("SET search_path=pg_temp")
        for name in ("source_document", "ingestion_asset", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
            self.assertEqual(self.db.execute("SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                                            (name,)).fetchone()[0], "t")
        self.body = (FIXTURES / (self.SHA + ".zip")).read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), self.SHA)
        self.expected = worker.asset_parser_version("city-zip", self.URL)
        self.assertEqual(self.expected, "city-v8:reviewed-feb2022-date-v1")

    def add(self, url, body, *, hours=7):
        did = hashlib.sha256(body).hexdigest()
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,'Original','DANE',%s,'application/zip','original','2021-02-10',%s,%s)""",
          (did, url, body, Jsonb({"ingestion_kind": "city-zip"})))
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'city-zip','2021-02-10','review',%s,0,'city-v8',
                 now()-(%s*interval '1 hour'))""", (url, did, hours))
        return did

    def test_exact_repair_leads_crowded_city_backlog_and_changed_bytes_lose_priority(self):
        self.add(self.URL, self.body)
        generic = "https://www.dane.gov.co/files/operaciones/SIPSA/other-old-city.zip"
        self.add(generic, b"other retained city original", hours=100)
        self.db.execute("UPDATE ingestion_asset SET processor_version='city-v7' WHERE url=%s", (generic,))
        with self.db.cursor() as cursor:
            with cursor.copy("COPY ingestion_asset(url,kind,status,processor_version) FROM STDIN") as copy:
                for number in range(2000):
                    copy.write_row((f"https://example.invalid/pending-city-{number}",
                                    "city-zip", "pending", "city-v8"))
        before = self.db.execute("SELECT url,xmin::text FROM ingestion_asset ORDER BY url").fetchall()
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [(self.URL, "city-zip", date(2021, 2, 10))])
        self.assertEqual(before, self.db.execute("SELECT url,xmin::text FROM ingestion_asset ORDER BY url").fetchall())
        changed = self.add(self.URL + "-changed", b"changed publisher revision")
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (changed, self.URL))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], generic)
        from .city_exact_source_dispatch_v44_b import retained_exact_city_zip
        self.assertIsNone(retained_exact_city_zip(self.db, self.URL, "city-zip", self.expected))

    def test_retained_replay_rechecks_original_pointer_media_metadata_status_and_bytes(self):
        from .city_exact_source_dispatch_v44_b import retained_exact_city_zip
        self.add(self.URL, self.body)
        read = lambda: retained_exact_city_zip(self.db, self.URL, "city-zip", self.expected)
        self.assertEqual(read(), self.body)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, self.URL, "city-zip"))
        for column, candidate in (("source_url", self.URL + "?other"),
                                  ("media_type", "application/octet-stream"),
                                  ("kind", "extract"),
                                  ("metadata", Jsonb({"ingestion_kind": "daily-zip"}))):
            original = self.db.execute(f"SELECT {column} FROM source_document WHERE id=%s", (self.SHA,)).fetchone()[0]
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (candidate, self.SHA))
            self.assertIsNone(read(), column)
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s",
                            (Jsonb(original) if column == "metadata" else original, self.SHA))
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url=%s", (self.URL,))
        self.assertIsNone(read())
        self.db.execute("UPDATE ingestion_asset SET status='review' WHERE url=%s", (self.URL,))
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body + b"changed", self.SHA))
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            read()
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, self.URL, "city-zip"))
        self.assertIsNone(retained_exact_city_zip(self.db, self.URL, "daily-zip", self.expected))

    def test_recent_review_cooldown_and_completed_revision_exit_are_preserved(self):
        from .city_exact_source_dispatch_v44_b import retained_exact_city_zip
        self.add(self.URL, self.body, hours=1)
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (self.URL,))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], self.URL)
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s", (self.expected, self.URL))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [])
        self.assertIsNone(retained_exact_city_zip(self.db, self.URL, "city-zip", self.expected))


if __name__ == "__main__":
    unittest.main()
