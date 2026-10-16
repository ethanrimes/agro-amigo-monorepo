"""One-time exact-original requeue for the two audited weekly date conflicts."""

import os
import unittest
from datetime import date
from pathlib import Path

from . import worker
from .dane_weekly import MARCH_2024_ANNEX_SHA, MARCH_2024_ANNEX_URL


@unittest.skipUnless(
    os.environ.get("AGRO_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-table PostgreSQL opt-in",
)
class WeeklyMarchAssetMigration(unittest.TestCase):
    def test_exact_original_only_and_idempotent(self):
        db = worker.connect()
        self.addCleanup(db.close)
        db.execute("SET search_path=pg_temp")
        db.execute(
            "CREATE TEMP TABLE ingestion_asset("
            "url text,kind text,document_id text,observed_on date,"
            "status text,records integer,error text,processor_version text)"
        )
        march_error = (
            "SourceDateMismatch: Weekly printed period conflicts with the "
            "dated source URL: printed 2024-03-09–2024-03-15; filename "
            "2024-03-09–2024-03-16"
        )
        july_error = (
            "SourceDateMismatch: Weekly printed period conflicts with the "
            "dated source URL"
        )
        july_url = (
            "https://www.dane.gov.co/files/operaciones/SIPSA/"
            "bol-SIPSASemanal-22jul-28jul-2023.pdf"
        )
        july_sha = "7bd0545a892e3a95cbaa9333510161ed14b7753949ac0fae3c24aa419729d088"
        rows = [
            (MARCH_2024_ANNEX_URL, "dane-weekly-xlsx", MARCH_2024_ANNEX_SHA,
             "2024-03-16", "review", 0, march_error, "official-v2:dane-weekly-v16"),
            (july_url, "dane-weekly-pdf", july_sha, "2023-07-28", "review", 0,
             july_error, "official-v2:dane-weekly-v16"),
            (MARCH_2024_ANNEX_URL, "dane-weekly-xlsx", "changed-byte",
             "2024-03-16", "review", 0, march_error, "official-v2:dane-weekly-v16"),
            (july_url, "dane-weekly-pdf", "changed-byte", "2023-07-28",
             "review", 0, july_error, "official-v2:dane-weekly-v16"),
            (july_url, "dane-weekly-pdf", july_sha, "2023-07-28", "review", 1,
             july_error, "official-v2:dane-weekly-v16"),
            (july_url, "dane-weekly-pdf", july_sha, "2023-07-28", "review", 0,
             "a different review", "official-v2:dane-weekly-v16"),
            (july_url, "dane-weekly-pdf", july_sha, "2023-07-28", "review", 0,
             july_error, "official-v2:dane-weekly-v17"),
        ]
        for row in rows:
            db.execute("INSERT INTO ingestion_asset VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", row)
        sql = (
            Path(__file__).parent
            / "migrations/20261001_043_weekly_march_source_period.sql"
        ).read_text()
        db.execute(sql)
        first = db.execute(
            "SELECT url,document_id,observed_on,status,records,error,processor_version "
            "FROM ingestion_asset ORDER BY url,document_id,records,error,processor_version"
        ).fetchall()
        db.execute(sql)
        second = db.execute(
            "SELECT url,document_id,observed_on,status,records,error,processor_version "
            "FROM ingestion_asset ORDER BY url,document_id,records,error,processor_version"
        ).fetchall()
        self.assertEqual(first, second)
        self.assertEqual(
            [(r[0], r[2], r[3]) for r in first if r[3] == "pending"],
            [(MARCH_2024_ANNEX_URL, date(2024, 3, 15), "pending"),
             (july_url, date(2023, 7, 28), "pending")],
        )
        self.assertEqual(sum(r[3] == "review" for r in first), 5)
        self.assertEqual(
            [r[2] for r in first if r[0] == MARCH_2024_ANNEX_URL
             and r[1] == "changed-byte"],
            [date(2024, 3, 16)],
        )
