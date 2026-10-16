"""Real retained city PDFs through the worker in a disposable local database."""

import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .city_native_recovery_fixture import run_fixture


@unittest.skipUnless(os.environ.get("AGRO_REFERENCE_TEST_DSN"), "Local PostgreSQL fixture required")
class CityNativeRecoveryPg(unittest.TestCase):
    def setUp(self):
        self.admin = psycopg.connect(os.environ["AGRO_REFERENCE_TEST_DSN"], autocommit=True)
        self.addCleanup(self.admin.close)
        self.assertTrue(self.admin.info.host.startswith("/"), "Never use a remote database for this test")
        self.database = "city_native_recovery_" + uuid.uuid4().hex
        self.admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))
        self.addCleanup(self.remove_database)
        self.dsn = make_conninfo(os.environ["AGRO_REFERENCE_TEST_DSN"], dbname=self.database)
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute("""DO $$ BEGIN CREATE ROLE agro_reader; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
              DO $$ BEGIN CREATE ROLE agro_ingestor; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
              CREATE TABLE source_document(id text PRIMARY KEY,title text,publisher text,source_url text,
                media_type text,kind text,reference_period text,page_count integer,content bytea,
                metadata jsonb,retrieved_at timestamptz DEFAULT now());
              CREATE TABLE source_archive_member(archive_id text REFERENCES source_document(id),entry_name text,
                document_id text REFERENCES source_document(id),PRIMARY KEY(archive_id,entry_name));
              CREATE TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer,
                PRIMARY KEY(document_id,processor_version,step));
              CREATE FUNCTION prevent_history_removal() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Retained source evidence cannot change'; END $$;""")
            here = Path(__file__).resolve().parent
            schema = (here / "schema.sql").read_text()
            # Use the actual worker schema declarations for this source path.
            for start, end in (
                ("CREATE TABLE IF NOT EXISTS ingestion_asset (", "CREATE TABLE IF NOT EXISTS historical_price ("),
                ("CREATE TABLE IF NOT EXISTS source_pdf_page (", "DROP TRIGGER IF EXISTS demo_window ON input_municipal_price;"),
                ("CREATE TABLE IF NOT EXISTS source_ocr_scan(", "CREATE TABLE IF NOT EXISTS source_ocr_review_history("),
            ):
                db.execute(schema[schema.index(start):schema.index(end)])
            db.execute("CREATE VIEW unresolved_city_pdf_publication_conflict AS SELECT ''::text AS document_id WHERE false")
            for name in ("20261005_062_city_sep2021_native_evidence.sql", "20261005_063_city_pereira_native_evidence.sql"):
                statement = (here / "migrations" / name).read_text()
                db.execute(statement)
                db.execute(statement)  # Provisioning replays additive migrations.

    def remove_database(self):
        self.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.database)))

    def test_exact_sources_resume_and_preserve_old_siblings(self):
        result = run_fixture(self.dsn)
        self.assertTrue(result["restricted_ingestor_role_publication"])
        self.assertEqual(result["sep_resumed_typed"], 865)
        self.assertEqual(result["pereira_existing_matching_two_then_typed"], 104)
        self.assertEqual(result["pereira_prior_twelve_typed"], 1435)
        self.assertEqual(result["classification_rows"], 2404)
        self.assertEqual(result["wrong_money_category_extra_held"], ["money", "category", "extra"])
        self.assertTrue(result["pereira_prior_twelve_unchanged"])
        self.assertTrue(result["raw_history_preserved"])
        self.assertTrue(result["reader_insert_denied"])
        self.assertEqual(result["sep_city_member_complete_markers"], 0)
        self.assertEqual(result["pereira_old_city_v8_member_markers"], 12)
        self.assertEqual(result["production_writes"], 0)
