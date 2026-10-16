"""Full-schema regressions for bounded city-market location repair."""

from __future__ import annotations

import hashlib
import getpass
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb
from pipelines.ingestion import city_market_projection as projection
from pipelines.ingestion import worker

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "pipelines/ingestion/schema.sql").is_file())
PG_BIN = Path("/opt/homebrew/opt/postgresql@16/bin")
AMBIENT_DB = ("DATABASE_URL", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CityMarketProjectionFullSchemaPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        present = [name for name in AMBIENT_DB if os.environ.get(name)]
        if present:
            raise RuntimeError("ambient database configuration is forbidden: " + ",".join(present))
        if not Path(sys.executable).is_file() or not PG_BIN.joinpath("initdb").is_file():
            raise RuntimeError("pinned Python 3.11/PostgreSQL 16 binaries are unavailable")
        if min(shutil.disk_usage(path).free for path in ("/tmp", REPO)) < 7 * 1024**3:
            raise RuntimeError("free space is below the 7 GiB owned-test floor")

        cls.root = Path(tempfile.mkdtemp(prefix="agro-city-market-projection-owned-", dir="/tmp"))
        cls.addClassCleanup(cls.cleanup_owned_cluster)
        cls.data = cls.root / "data"
        cls.sock = cls.root / "socket"
        cls.sock.mkdir(mode=0o700)
        cls.log = cls.root / "postgres.log"
        cls.port = 65443
        subprocess.run(
            [str(PG_BIN / "initdb"), "-D", str(cls.data), "--auth=trust", "--no-locale", "--encoding=UTF8"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        subprocess.run(
            [str(PG_BIN / "pg_ctl"), "-D", str(cls.data), "-l", str(cls.log), "-o",
             f"-k {cls.sock} -p {cls.port} -h '' -c listen_addresses='' -c statement_timeout=10000",
             "-w", "start"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=60,
        )
        cls.pid = int((cls.data / "postmaster.pid").read_text().splitlines()[0])
        cls.db = psycopg.connect(
            host=str(cls.sock), port=cls.port, dbname="postgres", user=getpass.getuser(),
            autocommit=True, connect_timeout=5,
        )
        if cls.db.info.host != str(cls.sock) or cls.db.info.port != cls.port:
            raise RuntimeError("database connection did not use the exact private Unix socket")
        cls.db.execute("SET statement_timeout='10s'; SET lock_timeout='1s'")

        installer_path = REPO / "pipelines/ingestion/test_input_pdf_v17_role.py"
        installer_spec = importlib.util.spec_from_file_location("maintained_schema_installer", installer_path)
        installer = importlib.util.module_from_spec(installer_spec)
        installer_spec.loader.exec_module(installer)
        installer.install(cls.db)

        # The fixture uses real maintained DDL/migrations through 078; only the
        # rows are compact, source-typed witnesses for this projection helper.
        cls.seed_fixture()

    @classmethod
    def cleanup_owned_cluster(cls):
        if getattr(cls, "db", None):
            cls.db.close()
        root = getattr(cls, "root", None)
        data = getattr(cls, "data", None)
        if root and root.exists() and data and data.exists():
            pidfile = data / "postmaster.pid"
            pid = None
            if pidfile.exists():
                lines = pidfile.read_text().splitlines()
                if len(lines) < 2 or not lines[0].isdigit() or Path(lines[1]).resolve() != data.resolve():
                    raise RuntimeError("refusing cleanup: PostgreSQL PID file is not bound to this exact data directory")
                pid = int(lines[0])
                result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
                command = result.stdout.strip()
                if command and str(data) not in command:
                    raise RuntimeError("refusing to stop a PostgreSQL PID not owned by this test")
                if command:
                    subprocess.run([str(PG_BIN / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
            deadline = time.monotonic() + 5
            while pid and time.monotonic() < deadline:
                alive = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False).stdout.strip()
                if not alive:
                    break
                time.sleep(0.05)
            if (pid and alive) or pidfile.exists():
                raise RuntimeError("owned PostgreSQL process/data remains; preserving directory")
            shutil.rmtree(root)
            receipt = os.environ.get("AGRO_CITY_PROJECTION_CLEANUP_RECEIPT")
            if receipt:
                Path(receipt).write_text(json.dumps({
                    "cluster_root": str(root),
                    "server_pid": pid,
                    "exact_data_path_was_bound_to_pid": bool(pid),
                    "server_process_absent_after_stop": not bool(pid and alive),
                    "postmaster_pid_absent": not pidfile.exists(),
                    "data_directory_removed": not data.exists(),
                    "socket_directory_removed": not (root / "socket").exists(),
                    "cluster_root_removed": not root.exists(),
                }, indent=2, sort_keys=True) + "\n")

    @classmethod
    def seed_fixture(cls):
        db = cls.db

        # The real table requires a documented reference source for municipality
        # dimensions; the fixture keeps all IDs and raw values explicit.
        municipality_source = b"official municipality directory fixture"
        municipality_doc = sha(municipality_source)
        db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
            "VALUES(%s,'Municipalities','DANE','fixture://municipalities','application/octet-stream','original','2026',%s)",
            (municipality_doc, municipality_source),
        )
        db.execute(
            "INSERT INTO municipality(id,name,department,department_id,latitude,longitude,document_id) VALUES "
            "('66001','Pereira','Risaralda','66',4.81,-75.69,%s),"
            "('11001','Bogotá, D.C.','Bogotá, D.C.','11',4.65,-74.10,%s),"
            "('76001','Cali','Valle del Cauca','76',3.44,-76.52,%s)",
            (municipality_doc, municipality_doc, municipality_doc),
        )

        cls.docs = {}
        docs = {
            "pereira": b"source archive for Pereira market witness",
            "conflict": b"source archive with publication-conflicted raw quote",
            "no_witness": b"source archive without any quote witness",
        }
        for key, content in docs.items():
            doc_id = sha(content)
            parent_bytes = ("parent:" + key).encode()
            parent_id = sha(parent_bytes)
            db.execute(
                "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                "VALUES(%s,%s,'DANE',%s,'application/pdf','original','2021-11',%s)",
                (doc_id, key, "fixture://" + key + ".pdf", content),
            )
            db.execute(
                "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                "VALUES(%s,%s,'DANE',%s,'application/zip','original','2021-11',%s)",
                (parent_id, key + " archive", "fixture://" + key + ".zip", parent_bytes),
            )
            db.execute("INSERT INTO source_archive_member(archive_id,entry_name,document_id) VALUES(%s,%s,%s)",
                       (parent_id, key + ".pdf", doc_id))
            cls.docs[key] = {"id": doc_id, "parent_id": parent_id}

        db.execute(
            "INSERT INTO market(id,name,city,region,municipality_id) VALUES "
            "('sipsa-pereira-la-41','Pereira, La 41','Colombia','Colombia',NULL),"
            "('sipsa-conflict-market','Pereira Conflict, La 2','Colombia','Colombia',NULL),"
            "('sipsa-no-witness-market','Pereira No Witness, La 3','Colombia','Colombia',NULL),"
            "('legacy-pereira-manual','Pereira Manual, La 4','Colombia','Colombia',NULL),"
            "('sipsa-ambiguous-market','Pereira Ambiguous, La 5','Colombia','Colombia',NULL),"
            "('sipsa-manual-location','Pereira Manual, La 6','Pereira','Caldas',NULL),"
            "('sipsa-already-linked','Pereira Linked, La 7','Pereira','Risaralda','66001'),"
            "('sipsa-bogota-corabastos','Bogotá, D.C., Corabastos','Bogotá','Bogotá, D.C.','11001'),"
            "('sipsa-periera-la-8','Periera, La 8','Colombia','Colombia',NULL)"
        )
        def add_quote(doc_key, market_name, product_id, locator):
            document_id = cls.docs[doc_key]["id"]
            db.execute(
                """INSERT INTO regional_price(
                     document_id,source_locator,observed_on,product_id,product_name,market_name,
                     category,presentation,quantity,source_unit,round,round_label,min_price,max_price,
                     unit,min_unit_price,max_unit_price,source_page)
                   VALUES(%s,%s,DATE '2021-11-16',%s,%s,%s,'Frutas','Bulto',50,'Kilogramo',1,
                          'Ronda 1',75000,80000,'kg',1500,1600,1)""",
                (document_id, locator, product_id, "Papa capira", market_name),
            )
            db.execute("INSERT INTO regional_classification(document_id,source_locator,category_path) VALUES(%s,%s,%s)",
                       (document_id, locator, ["Frutas", "Papa"] ))

        add_quote("pereira", "Pereira, La 41", "papa-capira", "PDF page 1,row 8")
        add_quote("conflict", "Pereira Conflict, La 2", "papa-capira", "PDF page 1,row 9")
        for key in ("conflict",):
            doc_id = cls.docs[key]["id"]
            db.execute("INSERT INTO city_pdf_publication_conflict(document_id,archive_id,entry_name,processor_version,native_sha256,stored_sha256,details) VALUES(%s,%s,%s,'fixture-v1',%s,%s,'{}'::jsonb)",
                       (doc_id, cls.docs[key]["parent_id"], key + ".pdf", "1" * 64, "2" * 64))
        # The no-witness market has no quote source at all.

    def setUp(self):
        type(self).db.execute("BEGIN")

    def tearDown(self):
        type(self).db.execute("ROLLBACK")

    @classmethod
    def _connection(cls):
        return cls.db

    def snapshot_source_history(self):
        db = type(self)._connection()
        result = {}
        for table, where in (
            ("source_document", "TRUE"),
            ("source_archive_member", "TRUE"),
            ("regional_price", "TRUE"),
            ("regional_classification", "TRUE"),
        ):
            rows = db.execute(f"SELECT row_to_json(t)::text,t.xmin::text FROM {table} t WHERE {where} ORDER BY 1").fetchall()
            result[table] = rows
        return result

    def test_pereira_published_witness_repairs_only_location_then_replay_is_noop(self):
        db = type(self)._connection()
        source_before = self.snapshot_source_history()
        db.execute("UPDATE municipality SET name='PEREÍRA' WHERE id='66001'")
        market_before = db.execute(
            "SELECT (row_to_json(m)::jsonb-'city'-'region'-'municipality_id')::text "
            "FROM market m WHERE id='sipsa-pereira-la-41'"
        ).fetchone()[0]
        self.assertEqual(db.execute("SELECT count(*) FROM published_regional_price WHERE market_name='Pereira, La 41'").fetchone()[0], 1)
        first = projection.repair_published_city_market_locations(db, after_id="sipsa-pereira-la-4", limit=1, deadline=time.monotonic() + 10)
        candidates = db.execute("SELECT id,name,city,region,municipality_id FROM market WHERE municipality_id IS NULL ORDER BY id").fetchall()
        witnesses = db.execute("SELECT market_name FROM published_regional_price").fetchall()
        municipalities = db.execute("SELECT id,name,department FROM municipality ORDER BY id").fetchall()
        resolved = projection._municipality_for_market_name("Pereira, La 41", municipalities)
        self.assertEqual(first["updated"], 1, f"result={first}; candidate={candidates}; witnesses={witnesses}; municipalities={municipalities}; resolved={resolved}")
        self.assertEqual(db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-la-41'").fetchone(), ("Pereira", "Risaralda", "66001"))
        first_market_xmin = db.execute("SELECT xmin::text FROM market WHERE id='sipsa-pereira-la-41'").fetchone()[0]
        second = projection.repair_published_city_market_locations(db, limit=10, deadline=time.monotonic() + 10)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(db.execute("SELECT xmin::text FROM market WHERE id='sipsa-pereira-la-41'").fetchone()[0], first_market_xmin)
        market_after = db.execute(
            "SELECT (row_to_json(m)::jsonb-'city'-'region'-'municipality_id')::text "
            "FROM market m WHERE id='sipsa-pereira-la-41'"
        ).fetchone()[0]
        self.assertEqual(market_after, market_before)
        self.assertEqual(self.snapshot_source_history(), source_before)

    def test_conflict_excluded_raw_quote_is_not_a_published_witness(self):
        db = type(self)._connection()
        self.assertEqual(db.execute("SELECT count(*) FROM regional_price WHERE market_name='Pereira Conflict, La 2'").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT count(*) FROM published_regional_price WHERE market_name='Pereira Conflict, La 2'").fetchone()[0], 0)
        projection.repair_published_city_market_locations(db, limit=100, deadline=time.monotonic() + 10)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-conflict-market'").fetchone()[0], None)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-no-witness-market'").fetchone()[0], None)

    def test_exact_id_name_and_unique_municipality_guards_reject_manual_or_ambiguous_rows(self):
        db = type(self)._connection()
        db.execute("INSERT INTO market(id,name,city,region,municipality_id) VALUES('sipsa-duplicate-market','Pereira, La 41','Colombia','Colombia',NULL)")
        db.execute("INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page) SELECT document_id,'PDF page 2,row 1',observed_on,product_id,product_name,'Pereira Manual, La 4',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        db.execute("INSERT INTO regional_price SELECT document_id,'PDF page 2,row 2',observed_on,product_id,product_name,'Pereira Ambiguous, La 5',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        db.execute("INSERT INTO regional_price SELECT document_id,'PDF page 2,row 3',observed_on,product_id,product_name,'Pereira Linked, La 7',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        db.execute("INSERT INTO regional_price SELECT document_id,'PDF page 2,row 4',observed_on,product_id,product_name,'Periera, La 8',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        # Use a published quote for the manually conflicting location row,
        # and leave the explicitly manual ID outside the accepted ID scheme.
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 2,row 1',category_path FROM regional_classification LIMIT 1")
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 2,row 2',category_path FROM regional_classification LIMIT 1")
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 2,row 3',category_path FROM regional_classification LIMIT 1")
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 2,row 4',category_path FROM regional_classification LIMIT 1")
        db.execute("INSERT INTO municipality(id,name,department,department_id,latitude,longitude,document_id) SELECT '25001','Pereira','Cundinamarca','25',5,-74,id FROM source_document WHERE title='Municipalities'")
        # A supported sipsa-shaped market with a source witness but a conflicting
        # manual city/region must remain untouched.
        db.execute("INSERT INTO market(id,name,city,region,municipality_id) VALUES('sipsa-pereira-manual-la-4','Pereira Manual, La 4','Manizales','Caldas',NULL)")
        projection.repair_published_city_market_locations(db, limit=100, deadline=time.monotonic() + 10)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='legacy-pereira-manual'").fetchone()[0], None)
        self.assertEqual(db.execute("SELECT city,region,municipality_id FROM market WHERE id='sipsa-pereira-manual-la-4'").fetchone(), ("Manizales", "Caldas", None))
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-ambiguous-market'").fetchone()[0], None)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-already-linked'").fetchone()[0], "66001")
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-duplicate-market'").fetchone()[0], None)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-periera-la-8'").fetchone()[0], None)

    def test_keyset_cursor_advances_past_unmatched_rows_for_later_batches(self):
        db = type(self)._connection()
        # Ambiguous and duplicate rows are not rewritten, yet the durable
        # keyset cursor moves past them so later safe IDs are reached.
        db.execute("INSERT INTO market(id,name,city,region,municipality_id) VALUES('dane-city-ambiguous-plaza','Ambiguous, Plaza','Colombia','Colombia',NULL),('dane-city-duplicate-pereira','Pereira, La 41','Colombia','Colombia',NULL),('sipsa-pereira-other-plaza','Pereira, Other Plaza','Colombia','Colombia',NULL)")
        db.execute("INSERT INTO municipality(id,name,department,department_id,latitude,longitude,document_id) SELECT '25001','Ambiguous','Cundinamarca','25',5,-74,id FROM source_document WHERE title='Municipalities'")
        db.execute("INSERT INTO municipality(id,name,department,department_id,latitude,longitude,document_id) SELECT '25002','Ambiguous','Other Department','25',5,-74,id FROM source_document WHERE title='Municipalities'")
        db.execute("INSERT INTO regional_price SELECT document_id,'PDF page 3,row 1',observed_on,product_id,product_name,'Ambiguous, Plaza',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 3,row 1',category_path FROM regional_classification LIMIT 1")
        db.execute("INSERT INTO regional_price SELECT document_id,'PDF page 3,row 2',observed_on,product_id,product_name,'Pereira, Other Plaza',category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE market_name='Pereira, La 41' LIMIT 1")
        db.execute("INSERT INTO regional_classification SELECT document_id,'PDF page 3,row 2',category_path FROM regional_classification LIMIT 1")
        cursor = ""
        seen = []
        result = None
        for _ in range(10):
            result = projection.repair_published_city_market_locations(
                db, after_id=cursor, limit=1, deadline=time.monotonic() + 10,
            )
            if result["scanned"] == 0:
                self.fail(f"keyset wrapped before reaching safe later market: {seen}")
            self.assertGreater(result["cursor_after"], cursor)
            cursor = result["cursor_after"]
            seen.append(cursor)
            if result["updated"]:
                break
        self.assertIn("dane-city-ambiguous-plaza", seen)
        self.assertIn("dane-city-duplicate-pereira", seen)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(db.execute("SELECT municipality_id FROM market WHERE id='sipsa-pereira-other-plaza'").fetchone()[0], "66001")

    def test_expired_projection_deadline_does_not_change_market_or_source_history(self):
        db = type(self)._connection()
        before_market = db.execute("SELECT row_to_json(m)::text,m.xmin::text FROM market m ORDER BY id").fetchall()
        before_source = self.snapshot_source_history()
        result = projection.repair_published_city_market_locations(
            db, after_id="", limit=100, deadline=time.monotonic() - 1,
        )
        self.assertTrue(result["deadline_reached"])
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["cursor_after"], "")
        self.assertEqual(db.execute("SELECT row_to_json(m)::text,m.xmin::text FROM market m ORDER BY id").fetchall(), before_market)
        self.assertEqual(self.snapshot_source_history(), before_source)

    def test_cursor_rejects_unbounded_values_and_excludes_current_run(self):
        db = type(self)._connection()
        with self.assertRaises(ValueError):
            projection.repair_published_city_market_locations(
                db, after_id="x" * (projection.CURSOR_MAX_LENGTH + 1),
                deadline=time.monotonic() + 2,
            )
        stale_id = uuid.uuid4()
        malformed_id = uuid.uuid4()
        current_id = uuid.uuid4()
        db.execute(
            "INSERT INTO ingestion_run(id,mode,status,started_at,finished_at,summary) VALUES "
            "(%s,'daily','partial',now()-interval '2 hours',now(),%s),"
            "(%s,'daily','partial',now(),now(),%s),"
            "(%s,'daily','running',now()+interval '1 day',NULL,%s)",
            (stale_id, Jsonb({"city_market_location_projection": {"phase_completed": True, "cursor_after": "dane-city-valid"}}),
             malformed_id, Jsonb({"city_market_location_projection": {"phase_completed": True, "cursor_after": "x" * (projection.CURSOR_MAX_LENGTH + 1)}}),
             current_id, Jsonb({"city_market_location_projection": {"phase_completed": True, "cursor_after": "dane-city-current"}})),
        )
        cursor, reset = projection.load_completed_projection_cursor(db, current_id)
        self.assertEqual(cursor, "")
        self.assertTrue(reset)

    def test_worker_run_resumes_projection_from_partial_summary_and_wraps(self):
        db = type(self)._connection()
        # A completed projection phase remains a valid cursor checkpoint even
        # when unrelated DANE work made the enclosing run partial.
        prior_cursor = "dane-city-a-cursor-019"
        db.execute(
            "INSERT INTO ingestion_run(id,mode,status,started_at,finished_at,summary) "
            "VALUES(%s,'daily','partial',now()-interval '1 day',now(),%s)",
            (uuid.uuid4(), Jsonb({"city_market_location_projection": {
                "phase_completed": True, "cursor_after": prior_cursor,
            }})),
        )
        for index in range(105):
            market_id = f"dane-city-a-cursor-{index:03d}"
            db.execute(
                "INSERT INTO market(id,name,city,region,municipality_id) VALUES(%s,%s,'Colombia','Colombia',NULL)",
                (market_id, f"Cursor Fixture {index}, Plaza"),
            )

        @contextmanager
        def same_test_connection():
            yield db

        def run_once():
            with patch.object(worker, "connect", same_test_connection), \
                 patch.object(worker, "discover", return_value=[{"source": "unrelated-fixture-error", "error": "force partial status"}]), \
                 patch.object(worker, "refresh_catalog", return_value={"inputs": {"deferred": []}}), \
                 patch("pipelines.ingestion.label_normalization.drain", return_value={"available": True, "deferred": []}), \
                 patch("pipelines.ingestion.official_sources.discover_roots", return_value=[]), \
                 patch("pipelines.ingestion.retained_replays.drain", return_value={"errors": []}), \
                 patch("pipelines.ingestion.ocr.drain", return_value={"errors": []}), \
                 patch("pipelines.ingestion.queue_plan.current_dane_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.city_catchup_candidates", return_value=[]), \
                 patch("pipelines.ingestion.queue_plan.backfill_candidates", return_value=[]), \
                 patch.object(worker, "refresh_trm", return_value={}), \
                 patch.object(worker, "refresh_seasons", return_value={}):
                return worker.run(mode="daily", limit=0, time_budget=45, ocr_limit=0, ocr_scan_limit=0)

        first = run_once()
        first_row = db.execute(
            "SELECT status,summary->'city_market_location_projection' FROM ingestion_run "
            "WHERE summary ? 'city_market_location_projection' ORDER BY started_at DESC,id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(first_row[0], "partial")
        self.assertEqual(first_row[1]["cursor_before"], prior_cursor)
        self.assertTrue(first_row[1]["phase_completed"])
        self.assertEqual(first_row[1]["cursor_after"], "")
        db.execute(
            "UPDATE ingestion_run SET started_at=clock_timestamp() "
            "WHERE summary #>> '{city_market_location_projection,cursor_after}'=''")
        checkpoint_order = db.execute(
            "SELECT started_at,summary #>> '{city_market_location_projection,cursor_after}', "
            "summary #>> '{city_market_location_projection,phase_completed}' "
            "FROM ingestion_run WHERE summary ? 'city_market_location_projection' "
            "ORDER BY started_at DESC,id DESC"
        ).fetchall()
        self.assertEqual(checkpoint_order[0][1], "", repr(checkpoint_order))

        second = run_once()
        db.execute(
            "UPDATE ingestion_run SET started_at=clock_timestamp() "
            "WHERE summary #>> '{city_market_location_projection,cursor_after}'=%s",
            (second["city_market_location_projection"]["cursor_after"],),
        )
        second_row = db.execute(
            "SELECT status,summary->'city_market_location_projection' FROM ingestion_run "
            "WHERE summary ? 'city_market_location_projection' ORDER BY started_at DESC,id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(second_row[0], "partial")
        self.assertEqual(second_row[1]["cursor_before"], "")
        self.assertTrue(second_row[1]["phase_completed"])
        self.assertLessEqual(second_row[1]["scanned"], 100)
        self.assertNotEqual(second_row[1]["cursor_after"], "")
        third = run_once()
        db.execute(
            "UPDATE ingestion_run SET started_at=clock_timestamp() "
            "WHERE summary #>> '{city_market_location_projection,cursor_after}'=%s",
            (third["city_market_location_projection"]["cursor_after"],),
        )
        third_row = db.execute(
            "SELECT status,summary->'city_market_location_projection' FROM ingestion_run "
            "WHERE summary ? 'city_market_location_projection' ORDER BY started_at DESC,id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(third_row[0], "partial")
        self.assertEqual(third_row[1]["cursor_before"], second_row[1]["cursor_after"])
        self.assertTrue(third_row[1]["phase_completed"])
        self.assertLessEqual(third_row[1]["scanned"], 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
