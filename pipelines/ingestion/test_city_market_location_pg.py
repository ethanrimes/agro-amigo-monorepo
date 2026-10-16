"""Local PostgreSQL proof for source-name-bound city-market location enrichment."""
import getpass
import random
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg

from pipelines.ingestion import city_reports as city


def sample_row(market_name):
    return (
        "PDF page 1,table 1,row 8,round 1", date(2021, 11, 16), "papa-capira",
        "Papa capira", market_name, "Frutas", "Bulto", 50, "Kilogramo", 1,
        "Ronda 1", 75000, 80000, "kg", 1500, 1600, 1,
    )


class CityMarketLocationProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="agro-market-location-pg-", dir="/tmp"))
        cls.addClassCleanup(cls.cleanup_owned_cluster)
        cls.data = cls.root / "data"
        cls.port = random.randrange(42000, 48000)
        subprocess.run(["initdb", "-D", str(cls.data), "--auth=trust", "--no-locale", "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["pg_ctl", "-D", str(cls.data), "-l", str(cls.root / "postgres.log"),
                        "-o", f'-k {cls.root} -p {cls.port} -h ""', "-w", "start"],
                       check=True, stdout=subprocess.DEVNULL)
        cls.server_pid = int((cls.data / "postmaster.pid").read_text().splitlines()[0])
        cls.db = psycopg.connect(
            f"host={cls.root} port={cls.port} dbname=postgres user={getpass.getuser()}",
            autocommit=True,
        )
        if not str(cls.db.info.host).startswith("/tmp/agro-market-location-pg-"):
            raise AssertionError("fixture must use its own local Unix socket")
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='10s'")
        cls.db.execute("CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text)")
        cls.db.execute("CREATE TEMP TABLE municipality(id text,name text,department text)")
        cls.db.execute("CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,market_name text,min_price numeric,max_price numeric,PRIMARY KEY(document_id,source_locator))")
        cls.db.execute("INSERT INTO municipality VALUES('66001','Pereira','Risaralda'),('11001','Bogotá, D.C.','Bogotá, D.C.'),('76001','Cali','Valle del Cauca')")
        cls.db.execute("INSERT INTO market VALUES('sipsa-pereira-la-41','Pereira, La 41','Colombia','Colombia',NULL),('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),('dane-city-cali-cavasa','Cali, Cavasa','Cali','Valle del Cauca','76001'),('sipsa-pereira-conflict','Pereira conflict','Pereira','Caldas','17001')")
        cls.db.execute("INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,market_name,min_price,max_price) VALUES('immutable-source','PDF page 1,row 8',DATE '2021-11-16','papa-capira','Pereira, La 41',75000,80000)")

    @classmethod
    def cleanup_owned_cluster(cls):
        if getattr(cls, "db", None):
            cls.db.close()
        data = getattr(cls, "data", None)
        root = getattr(cls, "root", None)
        pid = getattr(cls, "server_pid", None)
        if data and data.exists() and pid:
            def command_for(pid_value):
                result = subprocess.run(
                    ["ps", "-p", str(pid_value), "-o", "command="],
                    check=False, capture_output=True, text=True,
                )
                return result.stdout.strip() if result.returncode == 0 else ""

            command = command_for(pid)
            if command:
                if f"-D {data}" not in command:
                    raise AssertionError("refusing cleanup: PID does not belong to this test cluster")
                subprocess.run(
                    ["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"],
                    check=True, stdout=subprocess.DEVNULL,
                )
            deadline = time.monotonic() + 5
            while command_for(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if command_for(pid) or (data / "postmaster.pid").exists():
                raise AssertionError("owned PostgreSQL PID/data directory still active; preserving it")
        if root and root.exists():
            shutil.rmtree(root)

    def reset_fixture(self):
        self.db.execute("DELETE FROM market")
        self.db.execute("DELETE FROM municipality")
        self.db.execute("INSERT INTO municipality VALUES('66001','Pereira','Risaralda'),('11001','Bogotá, D.C.','Bogotá, D.C.'),('76001','Cali','Valle del Cauca')")
        self.db.execute("INSERT INTO market VALUES('sipsa-pereira-la-41','Pereira, La 41','Colombia','Colombia',NULL),('sipsa-bogota-d-c-corabastos','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),('dane-city-cali-cavasa','Cali, Cavasa','Cali','Valle del Cauca','76001'),('sipsa-pereira-conflict','Pereira conflict','Pereira','Caldas','17001')")

    def setUp(self):
        self.reset_fixture()

    def run_projection(self, market_name):
        original = city._bulk_insert
        def insert_market_only(db, table, rows):
            if table == "market":
                return original(db, table, rows)
        with patch.object(city, "_bulk_insert", insert_market_only):
            city.save_classifications(self.db, "document", [sample_row(market_name)])

    def assert_pereira_enriched(self):
        actual = self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-la-41'").fetchone()
        self.assertEqual(actual, ("Pereira", "Risaralda", "66001"))

    def assert_pereira_unchanged(self, expected):
        actual = self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-la-41'").fetchone()
        self.assertEqual(actual, expected)

    def test_unlinked_pereira_source_market_gets_unique_official_municipality(self):
        before = self.db.execute("SELECT document_id,source_locator,observed_on,product_id,market_name,min_price,max_price,xmin::text FROM regional_price WHERE document_id='immutable-source'").fetchone()
        self.run_projection("Pereira, La 41")
        self.assert_pereira_enriched()
        first_xmin = self.db.execute("SELECT xmin::text FROM market WHERE id='sipsa-pereira-la-41'").fetchone()
        self.run_projection("Pereira, La 41")
        self.assert_pereira_enriched()
        self.assertEqual(self.db.execute("SELECT xmin::text FROM market WHERE id='sipsa-pereira-la-41'").fetchone(), first_xmin,
                         "a second projection must not rewrite an already-linked market")
        after = self.db.execute("SELECT document_id,source_locator,observed_on,product_id,market_name,min_price,max_price,xmin::text FROM regional_price WHERE document_id='immutable-source'").fetchone()
        self.assertEqual(after, before, "location projection must not rewrite source quote history")

    def test_blank_and_null_placeholders_are_both_enriched(self):
        for city, region in ((None, None), ("", "")):
            with self.subTest(city=city, region=region):
                self.reset_fixture()
                self.db.execute("UPDATE market SET city=%s,region=%s WHERE id='sipsa-pereira-la-41'", (city, region))
                self.run_projection("Pereira, La 41")
                self.assert_pereira_enriched()

    def test_mismatched_nonempty_city_or_region_fail_closed(self):
        self.db.execute("UPDATE market SET city='Manizales',region='Colombia' WHERE id='sipsa-pereira-la-41'")
        self.run_projection("Pereira, La 41")
        self.assert_pereira_unchanged(("Manizales", "Colombia", None))
        self.reset_fixture()
        self.db.execute("UPDATE market SET city='Pereira',region='Caldas' WHERE id='sipsa-pereira-la-41'")
        self.run_projection("Pereira, La 41")
        self.assert_pereira_unchanged(("Pereira", "Caldas", None))

    def test_duplicate_literal_market_identity_and_unrecognized_id_fail_closed(self):
        self.db.execute("INSERT INTO market VALUES('dane-city-pereira-la-41','Pereira, La 41','Colombia','Colombia',NULL)")
        self.run_projection("Pereira, La 41")
        self.assert_pereira_unchanged(("Colombia", "Colombia", None))
        self.reset_fixture()
        self.db.execute("UPDATE market SET id='legacy-pereira-market' WHERE id='sipsa-pereira-la-41'")
        self.run_projection("Pereira, La 41")
        actual = self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='legacy-pereira-market'").fetchone()
        self.assertEqual(actual, ("Colombia", "Colombia", None))

    def test_maintained_directory_name_match_is_case_and_accent_insensitive(self):
        self.db.execute("DELETE FROM municipality WHERE id='66001'")
        self.db.execute("INSERT INTO municipality VALUES('66001','PEREÍRA','Risaralda')")
        self.run_projection("Pereira, La 41")
        self.assert_pereira_enriched()

    def test_existing_conflicting_mapping_and_direct_special_aliases_are_unchanged(self):
        self.run_projection("Pereira conflict")
        self.assertEqual(self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-conflict'").fetchone(), ("Pereira", "Caldas", "17001"))
        self.run_projection("Bogotá, D.C., Corabastos")
        self.assertEqual(self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-bogota-d-c-corabastos'").fetchone(), ("Bogotá", "Bogotá, D.C.", "11001"))
        self.run_projection("Cali, Cavasa")
        self.assertEqual(self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='dane-city-cali-cavasa'").fetchone(), ("Cali", "Valle del Cauca", "76001"))

    def test_ambiguous_directory_match_fails_closed(self):
        self.db.execute("INSERT INTO municipality VALUES('17001','Pereira','Caldas')")
        self.db.execute("INSERT INTO market VALUES('sipsa-pereira-ambiguous','Pereira, Ambiguous','Colombia','Colombia',NULL)")
        self.run_projection("Pereira, Ambiguous")
        self.assertEqual(self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-ambiguous'").fetchone(), ("Colombia", "Colombia", None))

    def test_new_city_market_keeps_existing_unique_name_mapping_behavior(self):
        self.run_projection("Pereira, New Plaza")
        self.assertEqual(self.db.execute("SELECT city,region,municipality_id FROM market WHERE id='dane-city-pereira-new-plaza'").fetchone(), ("Pereira", "Risaralda", "66001"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
