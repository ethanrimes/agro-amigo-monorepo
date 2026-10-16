"""Exact DANE RAR publisher tests; full-PG fixture remains in the private packet."""
from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import tempfile
import time as monotonic_time
import unittest
from datetime import date
from decimal import Decimal
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import city_rar_decoder as decoder
from . import city_rar_publication as publication


URL = decoder.AUG19_URL
DID = decoder.AUG19_DOCUMENT_ID
DAY = publication.AUG19_DAY
VERSION = publication.aug19_processor_version("city-v8", URL)
SOURCE_PATH = os.environ.get("AGRO_CITY_RAR_PRIVATE_SOURCE")
ROOT = Path(__file__).resolve().parents[2]
LOADER_PATH = ROOT / "artifacts/qa-resumed-20261001/worker-v76-independent-full-20261007-a/prepare_full_pipeline.py"


class RollbackGuardProbe(Exception):
    pass


class CityRarPublicationUnitTests(unittest.TestCase):
    def test_processor_version_suffix_is_scoped_to_exact_url(self):
        self.assertEqual(VERSION, "city-v8:aug19-rar5-publication-v1")
        self.assertEqual(publication.aug19_processor_version(VERSION, URL), VERSION)
        self.assertEqual(publication.aug19_processor_version("city-v8", URL + "?alias=1"), "city-v8")
        self.assertEqual(publication.aug19_processor_version("city-v8", "https://example.invalid/other.zip"), "city-v8")

    def test_retained_source_lookup_is_exact_source_only(self):
        class NoReadDB:
            def execute(self, *_args, **_kwargs):
                raise AssertionError("non-target source must not query retained records")

        db = NoReadDB()
        self.assertIsNone(publication.retained_aug19_original(db, URL + "?copy=1", "city-zip", DAY))
        self.assertIsNone(publication.retained_aug19_original(db, URL, "city-pdf", DAY))
        with self.assertRaisesRegex(publication.CityRarPublicationError, "date"):
            publication.retained_aug19_original(db, URL, "city-zip", date(2022, 8, 20))

    def test_wrong_processor_version_cannot_create_shared_checkpoint_namespace(self):
        with self.assertRaisesRegex(publication.CityRarPublicationError, "version suffix"):
            publication.publish_exact_aug19_rar(
                None, b"", DID, URL, DAY, processor_version="city-v8",
            )


@unittest.skipUnless(SOURCE_PATH, "set AGRO_CITY_RAR_PRIVATE_SOURCE to the private pinned RAR fixture")
class CityRarPublicationOwnedFullSchemaPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = Path(SOURCE_PATH).resolve()
        cls.body = cls.source_path.read_bytes()
        if (hashlib.sha256(cls.body).hexdigest() != decoder.AUG19_SHA256
                or not cls.body.startswith(decoder.RAR5_MAGIC)):
            raise RuntimeError("private fixture is not the exact pinned DANE RAR source")
        pg = Path("/opt/homebrew/opt/postgresql@17/bin")
        if not (pg / "initdb").is_file() or not (pg / "pg_ctl").is_file():
            raise RuntimeError("owned PostgreSQL 17 binaries unavailable; refusing shared database")
        if not LOADER_PATH.is_file():
            raise RuntimeError("private full-schema test loader is unavailable")
        import importlib.util

        spec = importlib.util.spec_from_file_location("agro_city_rar_full_schema_loader", LOADER_PATH)
        cls.schema_loader = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.schema_loader)

        cls.pg = pg
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-city-rar-publish-", dir="/tmp"))
        cls.port = cls._free_port()
        cls.dbname = "city_rar_private_" + str(random.randrange(10**8, 10**9))
        cls.started = False
        cls.stopped = False
        cls.directory_removed = False
        cls.db = None
        try:
            subprocess.run(
                [str(pg / "initdb"), "-D", str(cls.directory / "cluster"), "--auth=trust",
                 "--no-locale", "--encoding=UTF8"], check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            subprocess.run(
                [str(pg / "pg_ctl"), "-D", str(cls.directory / "cluster"), "-l",
                 str(cls.directory / "postgres.log"), "-o",
                 f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            cls.started = True
            admin_dsn = cls._dsn("postgres")
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                cls._assert_owned(admin, "postgres")
                admin.execute(f'CREATE DATABASE "{cls.dbname}"')
            cls.db = psycopg.connect(cls._dsn(cls.dbname), autocommit=True)
            cls._assert_owned(cls.db, cls.dbname)
            cls.db.execute("SET statement_timeout='180s'; SET TimeZone='UTC'")
            cls.schema_loader.load_schema(cls.db, create_roles=True)
            cls.db.execute("SET search_path=public")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _dsn(cls, dbname):
        return f"host={cls.directory} port={cls.port} dbname={dbname} user={getpass.getuser()}"

    @staticmethod
    def _free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    @staticmethod
    def _assert_owned(db, dbname):
        if (not str(db.info.host).startswith("/tmp/agro-city-rar-publish-")
                or db.info.dbname != dbname
                or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            raise RuntimeError("refusing database outside owned Unix-socket test cluster")

    @classmethod
    def tearDownClass(cls):
        if cls.db is not None:
            cls.db.close()
        if cls.started:
            subprocess.run(
                [str(cls.pg / "pg_ctl"), "-D", str(cls.directory / "cluster"), "-m", "fast", "-w", "stop"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            cls.stopped = True
        if cls.directory.exists():
            shutil.rmtree(cls.directory)
            cls.directory_removed = not cls.directory.exists()

    def setUp(self):
        self.db = type(self).db
        self.db.execute("BEGIN")
        with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False):
            from . import worker
            self.assertEqual(worker.archive(self.db, URL, self.body, "city-zip", DAY), DID)
        self.db.execute(
            """INSERT INTO ingestion_asset
               (url,kind,observed_on,status,processor_version,records,document_id)
               VALUES(%s,'city-zip',%s,'pending','city-v8',0,%s)""",
            (URL, DAY, DID),
        )
        self.parent_before = self._parent_snapshot()

    def tearDown(self):
        if self.db.info.transaction_status.name != "IDLE":
            self.db.execute("ROLLBACK")

    def _parent_snapshot(self):
        return self.db.execute(
            """SELECT id,title,publisher,source_url,media_type,kind,reference_period,
                      page_count,content,metadata,xmin::text
                 FROM source_document WHERE id=%s""", (DID,),
        ).fetchone()

    def _counts(self):
        return {
            "members": self.db.execute("SELECT count(*) FROM source_archive_member WHERE archive_id=%s", (DID,)).fetchone()[0],
            "prices": self.db.execute(
                "SELECT count(*) FROM regional_price WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)",
                (DID,),
            ).fetchone()[0],
            "classifications": self.db.execute(
                "SELECT count(*) FROM regional_classification WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)",
                (DID,),
            ).fetchone()[0],
            "checkpoints": self.db.execute(
                """SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
                     AND processor_version=%s AND step LIKE 'city-member:%%'""", (DID, VERSION),
            ).fetchone()[0],
            "children": self.db.execute("SELECT count(*) FROM source_document WHERE metadata->'parents' ? %s", (DID,)).fetchone()[0],
        }

    def _publication_xmins(self):
        return (
            self._parent_snapshot(),
            self.db.execute(
                """SELECT id,title,content,metadata,xmin::text FROM source_document
                     WHERE metadata->'parents' ? %s ORDER BY id""", (DID,),
            ).fetchall(),
            self.db.execute(
                "SELECT archive_id,entry_name,document_id,xmin::text FROM source_archive_member "
                "WHERE archive_id=%s ORDER BY entry_name", (DID,),
            ).fetchall(),
            self.db.execute(
                "SELECT *,xmin::text FROM regional_price WHERE document_id IN "
                "(SELECT document_id FROM source_archive_member WHERE archive_id=%s) ORDER BY document_id,source_locator",
                (DID,),
            ).fetchall(),
            self.db.execute(
                "SELECT *,xmin::text FROM regional_classification WHERE document_id IN "
                "(SELECT document_id FROM source_archive_member WHERE archive_id=%s) ORDER BY document_id,source_locator",
                (DID,),
            ).fetchall(),
            self.db.execute(
                "SELECT *,xmin::text FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step LIKE 'city-member:%%' ORDER BY step",
                (DID, VERSION),
            ).fetchall(),
        )

    def test_z_actual_worker_process_asset_partial_resume_replay_and_queue_version_scope(self):
        from . import city_reports, queue_plan, worker
        from .resumable_inputs import WorkDeferred

        # The base version simulates a retained pre-revision asset. The exact
        # RAR parent was inserted by setUp and is reused without HTTP.
        self.db.execute("COMMIT")
        self.assertEqual(worker.asset_parser_version("city-zip", URL), VERSION)
        neighbor_url = URL.replace("19-08-2022.zip", "18-08-2022.zip")
        neighbor_version = worker.asset_parser_version("city-zip", neighbor_url)
        self.assertEqual(neighbor_version, worker.parser_version("city-zip"))
        versions = queue_plan.expected_versions().obj
        self.assertEqual(versions["url:" + URL], VERSION)
        self.assertEqual(versions["city-zip"], neighbor_version)
        self.assertNotIn("url:" + neighbor_url, versions)

        with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), \
             patch.object(worker, "fetch_asset", side_effect=AssertionError("unexpected source HTTP")), \
             patch.object(worker, "fetch", side_effect=AssertionError("unexpected source HTTP")):
            deadline = monotonic_time.monotonic() + 120.0
            deadline_token = worker.RUN_DEADLINE.set(deadline)
            try:
                # Use an isolated monotonic clock for the city publisher only:
                # first member starts before the deadline, the next observes
                # the forced budget expiration after one committed checkpoint.
                with patch.object(city_reports, "time", SimpleNamespace(
                    monotonic=Mock(side_effect=[deadline - 1.0, deadline + 1.0]),
                )):
                    with self.assertRaises(WorkDeferred):
                        worker.process_asset(self.db, URL, "city-zip", DAY)
            finally:
                worker.RUN_DEADLINE.reset(deadline_token)

            partial = self._counts()
            self.assertEqual(partial["members"], 1)
            self.assertEqual(partial["children"], 1)
            self.assertGreater(partial["prices"], 0, (
                partial,
                self.db.execute(
                    "SELECT entry_name,document_id FROM source_archive_member WHERE archive_id=%s", (DID,),
                ).fetchall(),
                self.db.execute(
                    "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
                    (DID, VERSION),
                ).fetchall(),
                self.db.execute(
                    "SELECT error FROM ingestion_asset WHERE url=%s", (URL,),
                ).fetchone(),
            ))
            self.assertEqual(partial["checkpoints"], 1)
            self.assertEqual(self.db.execute(
                "SELECT status,document_id,processor_version FROM ingestion_asset WHERE url=%s",
                (URL,),
            ).fetchone(), ("pending", DID, "city-v8"))

            self.assertEqual(worker.process_asset(self.db, URL, "city-zip", DAY), 1400)

        expected = {"members": 17, "prices": 1400, "classifications": 1400,
                    "checkpoints": 17, "children": 17}
        self.assertEqual(self._counts(), expected)
        self.assertEqual(self.db.execute(
            "SELECT status,document_id,records,processor_version,error FROM ingestion_asset WHERE url=%s",
            (URL,),
        ).fetchone(), ("complete", DID, 1400, VERSION, None))
        after_publish = self._publication_xmins()

        # Exact RAR replay deliberately revalidates every checkpoint's native
        # price/classification cohort. The source-local semantic guard must
        # leave all immutable source and publication rows untouched.
        with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), \
             patch.object(worker, "fetch_asset", side_effect=AssertionError("unexpected source HTTP")), \
             patch.object(worker, "fetch", side_effect=AssertionError("unexpected source HTTP")):
            self.assertEqual(worker.process_asset(self.db, URL, "city-zip", DAY), 1400)
        self.assertEqual(self._publication_xmins(), after_publish)
        self.assertEqual(self._counts(), expected)

        # Queue selection sees exact URL version drift, then excludes the RAR
        # once current. Both states respect the existing six-hour cooldown;
        # an ordinary neighboring ZIP remains on city-v8.
        self.db.execute(
            "UPDATE ingestion_asset SET processor_version='city-v8',checked_at=now() WHERE url=%s", (URL,),
        )
        recent = queue_plan.repair_candidates(self.db, 8)
        self.assertNotIn((URL, "city-zip", DAY), recent)
        self.db.execute(
            "UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (URL,),
        )
        stale = queue_plan.repair_candidates(self.db, 8)
        self.assertIn((URL, "city-zip", DAY), stale)
        self.db.execute(
            "UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
            (VERSION, URL),
        )
        current = queue_plan.repair_candidates(self.db, 8)
        self.assertNotIn((URL, "city-zip", DAY), current)

    def test_same_count_wrong_price_tuple_checkpoint_fails_before_publisher_skip(self):
        from . import city_reports

        reader, _, _ = decoder.decode_pinned_aug19_source(self.body)
        payloads = {
            name: reader.read(name, decoder.AUG19_MAX_MEMBER_BYTES)
            for name in decoder.AUG19_MEMBERS
        }
        transient = publication._transient_zip(payloads)
        with zipfile.ZipFile(io.BytesIO(transient)) as archive:
            member = next(m for m in archive.infolist() if not m.is_dir() and m.filename.lower().endswith(".pdf"))
        member_name = member.filename
        child_id = decoder.AUG19_MEMBERS[member_name][1]
        body = payloads[member_name]
        metadata = {
            "ingestion_kind": "city-pdf", "retention": "permanent",
            "original_filename": member_name, "parents": [DID],
            "archive_entry": member_name,
        }
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
               VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s)""",
            (child_id, "DANE - " + member_name, URL,
             "Serie histórica completa", body, Jsonb(metadata)),
        )
        self.db.execute(
            "INSERT INTO source_archive_member VALUES(%s,%s,%s)",
            (DID, member_name, child_id),
        )
        native_rows = list(city_reports.parse_archived_city_pdf(self.db, body, child_id, DAY))
        self.assertGreater(len(native_rows), 0)
        price_rows = [(child_id, *row) for row in native_rows]
        wrong_index = next(i for i, row in enumerate(price_rows) if row[12] < row[13])
        wrong_row = list(price_rows[wrong_index])
        wrong_row[12] = Decimal(str(wrong_row[12])) + Decimal(1)
        price_rows[wrong_index] = tuple(wrong_row)
        with self.db.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO regional_price
                   (document_id,source_locator,observed_on,product_id,product_name,market_name,category,
                    presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,
                    min_unit_price,max_unit_price,source_page)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                price_rows,
            )
        class_rows = [
            (child_id, row[0], row[5].split(" > ")) for row in native_rows
        ]
        with self.db.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO regional_classification(document_id,source_locator,category_path) VALUES(%s,%s,%s)",
                class_rows,
            )
        step = city_reports._member_step(member, DAY)
        self.db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s)",
            (DID, VERSION, step, len(native_rows)),
        )

        # Same row count and checkpoint count are insufficient: exact native
        # min/max and every other tuple field must match before fast-path skip.
        count_before = self.db.execute(
            "SELECT count(*) FROM regional_price WHERE document_id=%s", (child_id,),
        ).fetchone()[0]
        self.assertEqual(count_before, len(native_rows))
        price_before = self.db.execute(
            "SELECT *,xmin::text FROM regional_price WHERE document_id=%s ORDER BY source_locator",
            (child_id,),
        ).fetchall()
        classes_before = self.db.execute(
            "SELECT *,xmin::text FROM regional_classification WHERE document_id=%s ORDER BY source_locator",
            (child_id,),
        ).fetchall()
        checkpoint_before = self.db.execute(
            "SELECT step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
            (DID, VERSION),
        ).fetchall()
        source_before = self.db.execute(
            "SELECT content,metadata,xmin::text FROM source_document WHERE id=%s", (child_id,),
        ).fetchone()
        with self.assertRaisesRegex(publication.CityRarPublicationError, "price tuples differ"):
            publication.publish_exact_aug19_rar(
                self.db, self.body, DID, URL, DAY, processor_version=VERSION,
            )
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM regional_price WHERE document_id=%s", (child_id,),
        ).fetchone()[0], count_before)
        self.assertEqual(self.db.execute(
            "SELECT *,xmin::text FROM regional_price WHERE document_id=%s ORDER BY source_locator",
            (child_id,),
        ).fetchall(), price_before)
        self.assertEqual(self.db.execute(
            "SELECT *,xmin::text FROM regional_classification WHERE document_id=%s ORDER BY source_locator",
            (child_id,),
        ).fetchall(), classes_before)
        self.assertEqual(self.db.execute(
            "SELECT step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
            (DID, VERSION),
        ).fetchall(), checkpoint_before)
        self.assertEqual(self.db.execute(
            "SELECT content,metadata,xmin::text FROM source_document WHERE id=%s", (child_id,),
        ).fetchone(), source_before)

    def test_full_cohort_publish_resume_guards_and_source_preservation(self):
        self.assertEqual(self.parent_before[1:8], (
            decoder.AUG19_TITLE, "DANE", URL, "application/zip", "original", "2022-08-19", None,
        ))
        self.assertEqual(bytes(self.parent_before[8]), self.body)
        self.assertEqual(self.parent_before[9], decoder.AUG19_METADATA)
        retained = publication.retained_aug19_original(self.db, URL, "city-zip", DAY)
        self.assertEqual(retained, self.body)
        self.assertIsNone(publication.retained_aug19_original(self.db, URL + "?alias=1", "city-zip", DAY))

        before = self._counts()
        for kwargs in (
            {"source_url": URL + "?alias=1"},
            {"source_did": "0" * 64},
            {"source_day": date(2022, 8, 20)},
            {"source_bytes": self.body[:-1] + bytes([self.body[-1] ^ 1])},
        ):
            args = {"source_bytes": self.body, "source_did": DID, "source_url": URL, "source_day": DAY}
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(publication.CityRarPublicationError):
                publication.publish_exact_aug19_rar(
                    self.db, **args, processor_version=VERSION,
                )
            self.assertEqual(self._counts(), before)

        member_name = next(iter(decoder.AUG19_MEMBERS))
        with self.assertRaises(RollbackGuardProbe):
            with self.db.transaction():
                wrong_id = "0" * 64
                self.db.execute(
                    """INSERT INTO source_document
                       (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
                       VALUES(%s,'wrong child','DANE',%s,'application/pdf','original',%s,%s,%s)""",
                    (wrong_id, URL, "Serie histórica completa", b"wrong", Jsonb({"retention": "permanent"})),
                )
                self.db.execute(
                    "INSERT INTO source_archive_member VALUES(%s,%s,%s)", (DID, member_name, wrong_id)
                )
                with self.assertRaisesRegex(publication.CityRarPublicationError, "mapping"):
                    publication.publish_exact_aug19_rar(
                        self.db, self.body, DID, URL, DAY, processor_version=VERSION,
                    )
                during_guard = self._counts()
                self.assertEqual(during_guard["members"], 1)  # the deliberately injected bad mapping
                self.assertEqual({k: v for k, v in during_guard.items() if k != "members"},
                                 {k: v for k, v in before.items() if k != "members"})
                raise RollbackGuardProbe()
        self.assertEqual(self._counts(), before)
        self.assertEqual(self._parent_snapshot(), self.parent_before)

        # A correctly named/hash-keyed mapping still fails closed if its child
        # body is not the native member bytes.
        with self.assertRaises(RollbackGuardProbe):
            with self.db.transaction():
                expected_size, expected_sha = decoder.AUG19_MEMBERS[member_name]
                expected_metadata = {
                    "ingestion_kind": "city-pdf", "retention": "permanent",
                    "original_filename": member_name, "parents": [DID],
                    "archive_entry": member_name,
                }
                self.db.execute(
                    """INSERT INTO source_document
                       (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
                       VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s)""",
                    (expected_sha, "DANE - " + member_name, URL, "Serie histórica completa",
                     b"%PDF-wrong-body", Jsonb(expected_metadata)),
                )
                self.db.execute(
                    "INSERT INTO source_archive_member VALUES(%s,%s,%s)",
                    (DID, member_name, expected_sha),
                )
                with self.assertRaisesRegex(publication.CityRarPublicationError, "bytes or metadata"):
                    publication.publish_exact_aug19_rar(
                        self.db, self.body, DID, URL, DAY, processor_version=VERSION,
                    )
                during_guard = self._counts()
                self.assertEqual(during_guard["members"], 1)
                self.assertEqual({key: during_guard[key] for key in (
                    "prices", "classifications", "checkpoints", "children",
                )}, {"prices": 0, "classifications": 0, "checkpoints": 0, "children": 1})
                raise RollbackGuardProbe()
        self.assertEqual(self._counts(), before)

        # A worker may crash after retaining a child original but before
        # inserting its source_archive_member link. An exact hash-keyed child
        # without a mapping is safe to resume only after every source field,
        # metadata field, and body is checked against the pinned manifest.
        orphan_name = next(name for name in decoder.AUG19_MEMBERS if name != member_name)
        orphan_size, orphan_sha = decoder.AUG19_MEMBERS[orphan_name]
        orphan_metadata = {
            "ingestion_kind": "city-pdf", "retention": "permanent",
            "original_filename": orphan_name, "parents": [DID],
            "archive_entry": orphan_name,
        }
        reader, _, _ = decoder.decode_pinned_aug19_source(self.body)
        orphan_body = reader.read(orphan_name, decoder.AUG19_MAX_MEMBER_BYTES)
        self.assertEqual((len(orphan_body), hashlib.sha256(orphan_body).hexdigest()),
                         (orphan_size, orphan_sha))

        # A poisoned unmapped child still fails before publication writes.
        with self.assertRaises(RollbackGuardProbe):
            with self.db.transaction():
                self.db.execute(
                    """INSERT INTO source_document
                       (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
                       VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s)""",
                    (orphan_sha, "DANE - " + orphan_name, URL,
                     "Serie histórica completa", b"%PDF-poisoned-unmapped-child",
                     Jsonb(orphan_metadata)),
                )
                with self.assertRaisesRegex(publication.CityRarPublicationError, "retained child body"):
                    publication.publish_exact_aug19_rar(
                        self.db, self.body, DID, URL, DAY, processor_version=VERSION,
                    )
                during_guard = self._counts()
                self.assertEqual(during_guard, {
                    "members": 0, "prices": 0, "classifications": 0,
                    "checkpoints": 0, "children": 1,
                })
                raise RollbackGuardProbe()
        self.assertEqual(self._counts(), before)

        # Simulate interruption immediately after retaining the exact child
        # source row and before its archive-member map is written.
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
               VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s)""",
            (orphan_sha, "DANE - " + orphan_name, URL,
             "Serie histórica completa", orphan_body, Jsonb(orphan_metadata)),
        )
        orphan_before = self.db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,content,metadata,xmin::text "
            "FROM source_document WHERE id=%s", (orphan_sha,),
        ).fetchone()
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM source_archive_member WHERE archive_id=%s AND document_id=%s",
            (DID, orphan_sha),
        ).fetchone()[0], 0)

        with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False):
            first = publication.publish_exact_aug19_rar(
                self.db, retained, DID, URL, DAY, processor_version=VERSION,
            )
        expected = {"members": 17, "prices": 1400, "classifications": 1400, "checkpoints": 17, "children": 17}
        self.assertEqual(first, 1400)
        self.assertEqual(self._counts(), expected)
        self.assertEqual(self._parent_snapshot(), self.parent_before)
        self.assertEqual(self.db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,content,metadata,xmin::text "
            "FROM source_document WHERE id=%s", (orphan_sha,),
        ).fetchone(), orphan_before)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM source_archive_member WHERE archive_id=%s AND document_id=%s",
            (DID, orphan_sha),
        ).fetchone()[0], 1)

        price_xmins = self.db.execute(
            """SELECT document_id,source_locator,xmin::text FROM regional_price
                 WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
                 ORDER BY document_id,source_locator""", (DID,),
        ).fetchall()
        class_xmins = self.db.execute(
            """SELECT document_id,source_locator,xmin::text FROM regional_classification
                 WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
                 ORDER BY document_id,source_locator""", (DID,),
        ).fetchall()
        checkpoint_xmins = self.db.execute(
            """SELECT step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s
                 AND processor_version=%s AND step LIKE 'city-member:%%' ORDER BY step""", (DID, VERSION),
        ).fetchall()
        children = self.db.execute(
            """SELECT m.entry_name,m.document_id,d.content,d.metadata,d.source_url,d.media_type,d.reference_period
                 FROM source_archive_member m JOIN source_document d ON d.id=m.document_id
                WHERE m.archive_id=%s ORDER BY m.entry_name""", (DID,),
        ).fetchall()
        self.assertEqual(len(children), 17)
        expected_names = set(decoder.AUG19_MEMBERS)
        self.assertEqual({row[0] for row in children}, expected_names)
        for name, child_id, body, metadata, url, media, period in children:
            size, digest = decoder.AUG19_MEMBERS[name]
            body = bytes(body)
            self.assertEqual(child_id, digest)
            self.assertEqual((len(body), hashlib.sha256(body).hexdigest()), (size, digest))
            self.assertEqual((url, media, period), (URL, "application/pdf", "Serie histórica completa"))
            self.assertEqual(metadata, {
                "ingestion_kind": "city-pdf", "retention": "permanent",
                "original_filename": name, "parents": [DID], "archive_entry": name,
            })

        class DifferentCollationDB:
            """Emulate a database returning a different numbered-locator order."""
            def __init__(self, db):
                self.db = db
                self.reordered_reads = 0

            def __getattr__(self, name):
                return getattr(self.db, name)

            def execute(self, query, *args, **kwargs):
                cursor = self.db.execute(query, *args, **kwargs)
                if (str(query).lstrip().startswith(
                        "SELECT document_id,source_locator,observed_on,product_id")
                        and "FROM regional_price WHERE document_id" in str(query)):
                    rows = list(reversed(cursor.fetchall()))
                    self.reordered_reads += 1
                    return SimpleNamespace(fetchall=lambda: rows)
                return cursor

        reordered_db = DifferentCollationDB(self.db)
        with patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False):
            replay = publication.publish_exact_aug19_rar(
                reordered_db, retained, DID, URL, DAY, processor_version=VERSION,
            )
        self.assertEqual(reordered_db.reordered_reads, 17)
        self.assertEqual(replay, 1400)
        self.assertEqual(self._counts(), expected)
        self.assertEqual(self._parent_snapshot(), self.parent_before)
        self.assertEqual(self.db.execute(
            """SELECT document_id,source_locator,xmin::text FROM regional_price
                 WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
                 ORDER BY document_id,source_locator""", (DID,),
        ).fetchall(), price_xmins)
        self.assertEqual(self.db.execute(
            """SELECT document_id,source_locator,xmin::text FROM regional_classification
                 WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)
                 ORDER BY document_id,source_locator""", (DID,),
        ).fetchall(), class_xmins)
        self.assertEqual(self.db.execute(
            """SELECT step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s
                 AND processor_version=%s AND step LIKE 'city-member:%%' ORDER BY step""", (DID, VERSION),
        ).fetchall(), checkpoint_xmins)
        self.assertEqual(self.parent_before, self._parent_snapshot())


if __name__ == "__main__":
    unittest.main(verbosity=2)
