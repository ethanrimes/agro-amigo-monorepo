"""Disposable PostgreSQL replay of the retained, privately held 2024 ZIP.

The exact ZIP is deliberately absent from tracked fixtures because its
administrative member has unrelated private fields.  Without that private
original these tests skip; they never contact the publisher or production DB.
"""

import getpass
import hashlib
import io
import os
import random
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import city_nonprice_context as subject
from . import city_exact_source_dispatch_v44_b as dispatch


_PRIVATE_PARENT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/qa-resumed-20261001/ios/city-nonprice-private-20261006-i/retained-parent.zip"
)


@unittest.skipUnless(_PRIVATE_PARENT.exists(), "private exact DANE original unavailable")
class ExactNonpriceContextPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-nonprice-context-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        cls.parent = _PRIVATE_PARENT.read_bytes()
        assert hashlib.sha256(cls.parent).hexdigest() == subject.PARENT_SHA256
        try:
            subprocess.run(
                ["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
                check=True, stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                 "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                check=True, stdout=subprocess.DEVNULL,
            )
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-nonprice-context-pg-")
            assert cls.db.execute("SELECT inet_server_addr()").fetchone() == (None,)
            cls.db.execute("SET search_path=pg_temp; SET statement_timeout='60s'")
            for statement in (
                "CREATE TEMP TABLE source_document(id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,kind text,reference_period text,page_count integer,content bytea,metadata jsonb)",
                "CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY,kind text,observed_on date,status text,processor_version text,records integer,document_id text)",
                "CREATE TEMP TABLE source_archive_member(archive_id text,entry_name text,document_id text,PRIMARY KEY(archive_id,entry_name))",
                "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer,PRIMARY KEY(document_id,processor_version,step))",
                "CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round integer,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page integer,PRIMARY KEY(document_id,source_locator))",
                "CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[],PRIMARY KEY(document_id,source_locator))",
                "CREATE TEMP TABLE price_observation(document_id text)",
                "CREATE TEMP TABLE historical_price(document_id text)",
                "CREATE TEMP TABLE input_price(document_id text)",
                "CREATE TEMP TABLE input_municipal_price(document_id text)",
                "CREATE TEMP TABLE input_reference_row(document_id text)",
                "CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text)",
                "CREATE TEMP TABLE city_pdf_publication_conflict(document_id text,archive_id text,entry_name text,processor_version text,native_sha256 text,stored_sha256 text,details jsonb,UNIQUE(document_id,processor_version))",
                "CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS SELECT document_id FROM city_pdf_publication_conflict",
                "CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text)",
                "CREATE TEMP TABLE municipality(id text,name text,department text)",
                "CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)",
            ):
                cls.db.execute(statement)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,'DANE',%s,'application/zip','original',%s,NULL,%s,%s)",
            (subject.PARENT_SHA256, "DANE - original regional ZIP", subject.URL,
             str(subject.DAY), self.parent,
             Jsonb({"retention": "permanent", "ingestion_kind": "city-zip",
                    "original_filename": subject._PARENT_FILENAME})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,document_id) "
            "VALUES(%s,'city-zip',%s,'pending',NULL,0,%s)",
            (subject.URL, subject.DAY, subject.PARENT_SHA256),
        )

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def _publish(self):
        # Extraction/OCR scheduling is orthogonal to the native parser here.
        # Use real exact source bytes and generic SQL publication, with no blob
        # or external OCR/provider side effects in this disposable database.
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch(
            "pipelines.ingestion.blob_archive.retain_original_blob", return_value=False,
        ), patch("pipelines.ingestion.pdf_sources.extract_pages", return_value=0):
            return dispatch.maybe_publish_exact_city_zip(
                self.db, subject.URL, self.parent, subject.PARENT_SHA256,
            )

    def _retained(self, **overrides):
        return dispatch.retained_exact_city_zip(
            self.db, overrides.get("url", subject.URL),
            overrides.get("kind", "city-zip"),
            overrides.get("version", subject.VERSION),
        )

    def test_all_32_peers_publish_and_admin_zero_replay_idempotent(self):
        self.assertEqual(self._retained(), self.parent)
        count = self._publish()
        self.assertEqual(count, 1923)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 1923)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_classification").fetchone()[0], 1923)
        with zipfile.ZipFile(io.BytesIO(self.parent)) as bundle:
            admin = bundle.getinfo(subject.MEMBER_NAME)
            admin_step = subject.city_reports._member_step(admin, subject.DAY)
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s",
            (subject.PARENT_SHA256, subject.VERSION, admin_step),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE processor_version=%s AND step LIKE 'city-member:%%'",
            (subject.VERSION,),
        ).fetchone()[0], 33)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM regional_price WHERE document_id=%s", (subject.MEMBER_SHA256,),
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT entry_name FROM source_archive_member WHERE archive_id=%s AND document_id=%s",
            (subject.PARENT_SHA256, subject.MEMBER_SHA256),
        ).fetchone(), (subject.MEMBER_NAME,))
        retained = self.db.execute(
            "SELECT content,page_count,metadata FROM source_document WHERE id=%s",
            (subject.MEMBER_SHA256,),
        ).fetchone()
        self.assertEqual(hashlib.sha256(bytes(retained[0])).hexdigest(), subject.MEMBER_SHA256)
        self.assertEqual(retained[1], 2)
        self.assertEqual(retained[2]["archive_entry"], subject.MEMBER_NAME)
        self.assertEqual(self._publish(), 1923)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 1923)
        self.assertIsNone(self._retained())
        with zipfile.ZipFile(io.BytesIO(self.parent)) as bundle:
            first_peer = next(m for m in bundle.infolist() if m.filename != subject.MEMBER_NAME)
            first_id = hashlib.sha256(bundle.read(first_peer)).hexdigest()
        locator, amount = self.db.execute(
            "SELECT source_locator,min_price FROM regional_price WHERE document_id=%s LIMIT 1",
            (first_id,),
        ).fetchone()
        self.db.execute(
            "UPDATE regional_price SET min_price=%s WHERE document_id=%s AND source_locator=%s",
            (amount + 1, first_id, locator),
        )
        with self.assertRaisesRegex(ValueError, "17-field"):
            self._publish()
        self.db.execute(
            "UPDATE regional_price SET min_price=%s WHERE document_id=%s AND source_locator=%s",
            (amount, first_id, locator),
        )
        self.db.execute(
            "UPDATE regional_classification SET category_path=ARRAY['wrong'] WHERE document_id=%s AND source_locator=%s",
            (first_id, locator),
        )
        with self.assertRaisesRegex(ValueError, "classification"):
            self._publish()
        self.db.execute(
            "UPDATE regional_classification SET category_path=string_to_array(category,' > ') "
            "FROM regional_price WHERE regional_classification.document_id=regional_price.document_id "
            "AND regional_classification.source_locator=regional_price.source_locator "
            "AND regional_classification.document_id=%s AND regional_classification.source_locator=%s",
            (first_id, locator),
        )
        self.db.execute(
            "UPDATE source_document SET media_type='application/octet-stream' WHERE id=%s",
            (subject.MEMBER_SHA256,),
        )
        with self.assertRaisesRegex(ValueError, "retained source identity"):
            self._publish()

    def test_reject_old_admin_price_and_new_version_collision_before_write(self):
        self.db.execute(
            "INSERT INTO regional_classification VALUES(%s,'old',ARRAY['x'])",
            (subject.MEMBER_SHA256,),
        )
        with self.assertRaisesRegex(ValueError, "existing agricultural row"):
            self._publish()
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0], 0)
        self.db.execute("DELETE FROM regional_classification")
        self.db.execute(
            "INSERT INTO ingestion_checkpoint VALUES(%s,%s,'city-member:unrelated',1)",
            (subject.PARENT_SHA256, subject.VERSION),
        )
        with self.assertRaisesRegex(ValueError, "checkpoint collision"):
            self._publish()
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.db.execute(
            "UPDATE source_document SET media_type='application/octet-stream' WHERE id=%s",
            (subject.PARENT_SHA256,),
        )
        with self.assertRaisesRegex(ValueError, "retained source identity"):
            self._publish()
        self.db.execute(
            "UPDATE source_document SET media_type='application/zip' WHERE id=%s",
            (subject.PARENT_SHA256,),
        )
        self.db.execute("UPDATE ingestion_asset SET observed_on='2024-05-30'")
        with self.assertRaisesRegex(ValueError, "asset binding"):
            self._publish()
        self.db.execute("UPDATE ingestion_asset SET observed_on=%s", (subject.DAY,))
        self.db.execute(
            "INSERT INTO source_archive_member VALUES(%s,%s,%s)",
            (subject.PARENT_SHA256, subject.MEMBER_NAME, "0" * 64),
        )
        with self.assertRaisesRegex(ValueError, "archive member mapping"):
            self._publish()
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0], 0)

    def test_one_peer_review_then_resume_preserves_its_admin_checkpoint(self):
        from . import city_reports

        with zipfile.ZipFile(io.BytesIO(self.parent)) as bundle:
            first_peer = next(m for m in bundle.infolist() if m.filename != subject.MEMBER_NAME)
            first_id = hashlib.sha256(bundle.read(first_peer)).hexdigest()
            first_rows = len(list(city_reports.parse_city_pdf(bundle.read(first_peer), subject.DAY)))
            admin_step = city_reports._member_step(bundle.getinfo(subject.MEMBER_NAME), subject.DAY)
        original = city_reports.parse_archived_city_pdf

        def held_once(db, data, did, day):
            if did == first_id:
                raise ValueError("controlled disposable peer review")
            yield from original(db, data, did, day)

        with patch.object(city_reports, "parse_archived_city_pdf", side_effect=held_once):
            with self.assertRaises(city_reports.CityZipPartialReview) as caught:
                self._publish()
        self.assertEqual(caught.exception.count, 1923 - first_rows)
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s",
            (subject.PARENT_SHA256, subject.VERSION, admin_step),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM regional_price WHERE document_id=%s", (first_id,),
        ).fetchone()[0], 0)
        self.assertEqual(self._retained(), self.parent)
        self.assertEqual(self._publish(), 1923)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 1923)
        self.assertIsNone(self._retained())

    def test_central_retained_path_is_source_bound_and_corruption_fails_before_fetch(self):
        self.assertEqual(self._retained(), self.parent)
        self.assertIsNone(self._retained(version="city-v8"))
        self.assertIsNone(self._retained(kind="daily-pdf"))
        self.assertIsNone(self._retained(url=subject.URL + "-other"))
        self.db.execute(
            "UPDATE source_document SET content=%s WHERE id=%s",
            (self.parent[:-1] + bytes([self.parent[-1] ^ 1]), subject.PARENT_SHA256),
        )
        with self.assertRaisesRegex(ValueError, "parent bytes changed"):
            self._retained()
        self.db.execute(
            "UPDATE source_document SET content=%s WHERE id=%s",
            (self.parent, subject.PARENT_SHA256),
        )
        for sql, args in (
            ("UPDATE source_document SET media_type='application/octet-stream' WHERE id=%s", (subject.PARENT_SHA256,)),
            ("UPDATE source_document SET source_url='https://example.invalid/' WHERE id=%s", (subject.PARENT_SHA256,)),
            ("UPDATE ingestion_asset SET observed_on='2024-05-30' WHERE url=%s", (subject.URL,)),
            ("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", ("0" * 64, subject.URL)),
        ):
            self.db.execute(sql, args)
            self.assertIsNone(self._retained())
            self.db.execute(
                "UPDATE source_document SET media_type='application/zip',source_url=%s WHERE id=%s",
                (subject.URL, subject.PARENT_SHA256),
            )
            self.db.execute(
                "UPDATE ingestion_asset SET observed_on=%s,document_id=%s WHERE url=%s",
                (subject.DAY, subject.PARENT_SHA256, subject.URL),
            )
        self.assertEqual(self._retained(), self.parent)


if __name__ == "__main__":
    unittest.main()
