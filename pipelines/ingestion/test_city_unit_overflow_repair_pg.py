"""Exact retained city ZIP repair priority without broad review requeue."""

import os
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from . import city_reports, queue_plan, worker


DATA = Path(__file__).parent / "testdata/city_unit_overflow_202201"
PARENTS = (
    ("official-jan3.zip", "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-03-01-2022.zip", date(2022, 1, 3)),
    ("official-jan4.zip", "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-04-01-2022.zip", date(2022, 1, 4)),
)


@unittest.skipUnless(os.environ.get("AGRO_CITY_POSTGRES_TEST") == "1", "Private PostgreSQL opt-in")
class CityUnitOverflowRepairPostgres(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("AGRO_REFERENCE_TEST_DSN private socket is required")
        self.db = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.db.close)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        self.db.execute("SET search_path=pg_temp")
        for name in ("source_document", "ingestion_asset", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")

    def seed(self, filename, url, day, *, digest=None, status="review", checked="2026-01-01 00:00:00+00"):
        body = (DATA / filename).read_bytes()
        actual = sha256(body).hexdigest()
        did = digest or actual
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'retained ZIP','DANE',%s,'application/zip','original','',%s,%s)",
            (did, url, body, Jsonb({"ingestion_kind": "city-zip"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,observed_on,document_id,processor_version,checked_at) "
            "VALUES(%s,'city-zip',%s,%s,%s,'city-v7',%s)",
            (url, status, day, did, checked),
        )
        return actual

    def test_only_exact_old_zip_revisions_advance_one_per_kind_without_bypassing_cooldown(self):
        first, second = PARENTS
        first_sha = self.seed(*first)
        second_sha = self.seed(*second, checked="2026-01-02 00:00:00+00")
        self.assertIn((first[1], "city-zip", first[2]), queue_plan.repair_candidates(self.db))
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s", (city_reports.VERSION, first[1]))
        self.assertIn((second[1], "city-zip", second[2]), queue_plan.repair_candidates(self.db))
        self.db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (second[1],))
        self.assertNotIn((second[1], "city-zip", second[2]), queue_plan.repair_candidates(self.db))
        self.db.execute("UPDATE ingestion_asset SET checked_at='2026-01-01',document_id=%s WHERE url=%s", ("f" * 64, second[1]))
        self.assertEqual(queue_plan.repair_candidates(self.db), [])
        self.assertEqual(first_sha, "9b7bbbcefbbddd8c023a100ea3db3032214050f44a9cef2bc9a20aabfb953878")
        self.assertEqual(second_sha, "6af11307e0ffdb6c98b36071ef134ad32110e07a4c82d6e72f2313537d23029f")
        self.assertEqual(tuple(row[0] for row in queue_plan.PRIORITY_SOURCE_REPAIRS[:2]),
                         ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf",
                          "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf"))


if __name__ == "__main__":
    unittest.main()
