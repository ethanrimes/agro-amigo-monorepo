"""Staged opt-in regression: exact three Sep 7 source children, no private files.

Copy beside the ingestion tests only after SQL059 and skip-only worker review.
AGRO_REFERENCE_TEST_DSN must point at a disposable local Unix-socket PostgreSQL.
"""
import hashlib
import io
import json
import os
import re
import unittest
import uuid
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import city_category_overlay as overlay, city_reports

HERE=Path(__file__).resolve().parent
SQL057=HERE/"migrations/20261005_057_city_category_overlay.sql"
SQL059=HERE/"migrations/20261005_059_city_category_adjudication.sql"
SQL060=HERE/"migrations/20261005_060_city_unresolved_evidence_reader.sql"
PLANNING=HERE.parents[1]/"apps/web/src/lib/server/planning.ts"
FIX=HERE/"testdata/city_category_overlay_20260907"
PARENT="12994008dc0a233459abd4edc0cc4ffdb67b6bfcfd93423ed9abfbed1611d2af"
URL="https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-07sep2026.zip"
OLD="54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2"
NEW="e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0"
THREE=(
 ("92da0fac7ad659cb73115d60efc07d66d72c0f77bc4a89490147226c828bda61","Bol-Corabastos07sep26.pdf",1,"bb7f4879f1ce021fa61015a267289dbdc8cd913f067eb85d607409254c5b05a7","3cb54db5a230e08dc872e5379eb4522d022a0efc8884f51a6a2d0b54aa5e4336","city-member:d282b5db1987b1c7eb4ec9a3d2c07c1eaab11506fbaf5b14f3137d60627885d0"),
 ("acd65fc551850af8883b86b02cd461b8f13a999657e1ff83d07ff5a1433dcc95","Bogotá, D.C., Corabastos-07-09-2026.pdf",2,"d83fe5fd51431b121ef6ebe6244da1be182411245491fa4084547e4371efd7e5","ee66f021589e7cf42806bd777f50a73e482a908b686062145f0d3f26bf423cf7","city-member:bbed9bf538638b6213bf125fd49fa27bc6e40bb780a3f11aee067556fe10ff91"),
 ("d0b02fdc617f8befed5d08a86a75a2878eb0de428f43ae4b867d42833e5225d7","Bogotá, D.C., Corabastos-07-09-2026-1.pdf",3,"42214c80e1a412f26a58f10181107f64a26b78acfcc301b9bfbde51b7a30644a","9e55007d0d76ddcd3d91084b5c1d1dca30aa3b102cc0dd070c734b301736e818","city-member:f01114709d81704ff4f8b9a0279e474cd6bbbd36c836c8e7ccb212f1e88bc3ef"),
)
CLASS_SHA="2e69045288701029aaae302b20b2ac990844939e391e4fe096687bc3d2d7b493"
NATIVE_SHA="2063fd66580cde5f12bfa6feba540de2a06d7fb47da79c272e07fd40747e971a"
STORED_SHA="5f58119f0d0e1d7c682427f127f3bfa718618f2be3de0697063582dd00984a90"
FIELDS=','.join(overlay.FIELDS)
INSERT="""INSERT INTO city_pdf_category_resolution
(document_id,conflict_id,archive_id,entry_name,source_url,proof_id,parser_code_sha256,
 raw_rows_sha256,classification_sha256,member_checkpoint_step,resolution_kind)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'reviewed-retained-pdf-category-only')"""


@unittest.skipUnless(os.environ.get("AGRO_REFERENCE_TEST_DSN"),"Disposable local PostgreSQL required")
class CityCategoryAdjudicationPg(unittest.TestCase):
    def connect(self,autocommit=False):
        db=psycopg.connect(self.dsn,autocommit=autocommit,
                           options="-c statement_timeout=20000 -c lock_timeout=8000")
        if not db.info.host.startswith("/tmp/agro-") or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None:
            db.close()
            raise RuntimeError("adjudication test requires private local Unix socket")
        db.execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(self.schema)))
        return db

    def setUp(self):
        self.dsn=os.environ["AGRO_REFERENCE_TEST_DSN"]
        self.schema="category_resolution_"+uuid.uuid4().hex[:12]
        self.fixture=json.loads((FIX/"corabastos_198_rows.json").read_text())
        self.data=(FIX/(PARENT+".zip")).read_bytes()
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),PARENT)
        self.admin=psycopg.connect(self.dsn,autocommit=True)
        self.addCleanup(self.cleanup)
        self.assertTrue(self.admin.info.host.startswith("/tmp/agro-"))
        self.assertIsNone(self.admin.execute("SELECT inet_server_addr()").fetchone()[0])
        self.admin.execute("DO $$ BEGIN CREATE ROLE agro_reader; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        self.admin.execute("DO $$ BEGIN CREATE ROLE agro_ingestor; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        self.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.admin.execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(self.schema)))
        self.admin.execute("CREATE COLLATION shifted_locator (provider=icu,locale='en-u-ka-shifted')")
        self.admin.execute("""CREATE TABLE source_document(id text PRIMARY KEY,kind text,media_type text,source_url text,metadata jsonb,content bytea);
          CREATE TABLE source_archive_member(archive_id text,entry_name text,document_id text,PRIMARY KEY(archive_id,entry_name));
          CREATE TABLE regional_price(document_id text,source_locator text COLLATE shifted_locator,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round integer,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page integer,PRIMARY KEY(document_id,source_locator));
          CREATE TABLE regional_classification(document_id text,source_locator text COLLATE shifted_locator,category_path text[],PRIMARY KEY(document_id,source_locator));
          CREATE TABLE city_pdf_publication_conflict(id bigint PRIMARY KEY,document_id text,archive_id text,entry_name text,processor_version text,native_sha256 text,stored_sha256 text,details jsonb);
          CREATE TABLE regional_price_product_correction(document_id text,source_locator text,old_product_id text,old_product_name text,corrected_product_id text,corrected_product_name text,PRIMARY KEY(document_id,source_locator));
          CREATE TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer,PRIMARY KEY(document_id,processor_version,step));
          CREATE VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS(SELECT 1 FROM city_pdf_publication_conflict c WHERE c.document_id=r.document_id);
          CREATE FUNCTION prevent_history_removal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable'; END $$;""")
        # This test intentionally gives source locators a non-default ICU
        # collation. Keep the exact SQL057 overlay table constraints, but give
        # its locator the same test-only collation before the migration's
        # IF NOT EXISTS so SQL059's UNION view can replace SQL057's view on PG16.
        table = re.search(
            r"(?ms)^CREATE TABLE IF NOT EXISTS regional_price_category_overlay \(.*?^\);",
            SQL057.read_text(),
        ).group()
        self.admin.execute(table.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE", 1)
                           .replace("source_locator text NOT NULL",
                                    "source_locator text COLLATE shifted_locator NOT NULL", 1))
        self.admin.execute(SQL057.read_text())
        self.admin.execute((HERE/"migrations/20261005_058_city_category_proof_collation.sql").read_text())
        self.admin.execute("INSERT INTO source_document VALUES(%s,'original','application/zip',%s,%s,%s)",
                           (PARENT,URL,Jsonb(self.fixture["parent"]["metadata"]),self.data))
        self.native={}
        raw=[]
        for item in self.fixture["raw_rows"]:
            row=dict(item)
            row["observed_on"]=date.fromisoformat(row["observed_on"])
            for field in ("quantity","min_price","max_price","min_unit_price","max_unit_price"):
                if row[field] is not None:row[field]=Decimal(row[field])
            raw.append(row)
        with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
            assert len(archive.infolist())==51
            assert sum(len(list(city_reports.parse_city_pdf(archive.read(info),date(2026,9,7))))
                       for info in archive.infolist() if info.filename.lower().endswith(".pdf"))==3077
            for did,entry,cid,proof,raw_hash,step in THREE:
                body=archive.read(entry)
                self.assertEqual(hashlib.sha256(body).hexdigest(),did)
                self.native[did]=sorted(city_reports.parse_city_pdf(body,date(2026,9,7)),key=lambda r:r[0].encode())
                self.assertEqual(len(self.native[did]),198)
                meta=dict(self.fixture["child"]["metadata"])
                meta["archive_entry"]=meta["original_filename"]=entry
                self.admin.execute("INSERT INTO source_document VALUES(%s,'original','application/pdf',%s,%s,%s)",
                                   (did,URL,Jsonb(meta),body))
                self.admin.execute("INSERT INTO source_archive_member VALUES(%s,%s,%s)",(PARENT,entry,did))
                with self.admin.cursor() as cur:
                    cur.executemany("INSERT INTO regional_price VALUES("+",".join(["%s"]*18)+")",
                                    [(did,*[r[f] for f in overlay.FIELDS]) for r in raw])
                    cur.executemany("INSERT INTO regional_classification VALUES(%s,%s,%s)",
                                    [(did,loc,path) for loc,path in self.fixture["classifications"].items()])
                details={"difference_fields":["category"],"difference_count":198,"native_count":198,
                         "stored_count":198,"classification_count":198}
                self.admin.execute("INSERT INTO city_pdf_publication_conflict VALUES(%s,%s,%s,%s,'city-v8',%s,%s,%s)",
                                   (cid,did,PARENT,entry,NATIVE_SHA,STORED_SHA,Jsonb(details)))
        self.assertEqual(self.admin.execute("SELECT count(*) FROM published_regional_price").fetchone()[0],0)

    def cleanup(self):
        try:
            self.admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
        finally:self.admin.close()

    @staticmethod
    def resolution(item):
        did,entry,cid,proof,raw_hash,step=item
        return (did,cid,PARENT,entry,URL,proof,OLD,raw_hash,CLASS_SHA,step)

    def apply(self,db):
        db.execute(SQL059.read_text())
        for item in THREE:
            db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,'city-v8',%s,198)",(PARENT,item[5]))
            db.execute(INSERT,self.resolution(item))

    def assert_native(self,db):
        self.assertEqual(db.execute("SELECT count(*) FROM resolved_regional_price").fetchone()[0],594)
        self.assertEqual(db.execute("SELECT count(*) FROM city_pdf_publication_conflict").fetchone()[0],3)
        self.assertEqual(db.execute("SELECT count(*) FROM unresolved_city_pdf_publication_conflict").fetchone()[0],0)
        for did,*_ in THREE:
            got=db.execute(f'SELECT {FIELDS} FROM resolved_regional_price WHERE document_id=%s ORDER BY source_locator COLLATE "C"',(did,)).fetchall()
            self.assertEqual(got,self.native[did])

    def test_evidence_warning_uses_unresolved_view_and_reader_acl(self):
        # Execute the exact SQL used by evidence(), not a mirrored hold predicate.
        evidence=PLANNING.read_text().split("export async function evidence(",1)[1]
        match=re.search(r'"(SELECT EXISTS \(SELECT 1 FROM unresolved_city_pdf_publication_conflict WHERE document_id=\$1\) AS held)"',evidence)
        self.assertIsNotNone(match)
        self.assertIn("if (conflict)",evidence)
        self.assertIn("city_pdf_publication_note",evidence)
        held_sql=match.group(1).replace("$1","%s")
        with self.connect(autocommit=True) as db:
            db.execute(SQL059.read_text())
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO agro_reader").format(sql.Identifier(self.schema)))
            self.assertFalse(db.execute("SELECT has_table_privilege('agro_reader','unresolved_city_pdf_publication_conflict','SELECT')").fetchone()[0])
            db.execute("SET ROLE agro_reader")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute(held_sql,(THREE[0][0],))
            db.execute("RESET ROLE")
            db.execute(SQL060.read_text())
            db.execute(SQL060.read_text())  # migration replay is safe
            db.execute("SET ROLE agro_reader")
            for item in THREE:
                self.assertTrue(db.execute(held_sql,(item[0],)).fetchone()[0])
            db.execute("RESET ROLE")
            for item in THREE:
                db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,'city-v8',%s,198)",(PARENT,item[5]))
                db.execute(INSERT,self.resolution(item))
            db.execute("SET ROLE agro_reader")
            for item in THREE:
                self.assertFalse(db.execute(held_sql,(item[0],)).fetchone()[0])
            db.execute("RESET ROLE")
            did,entry,_,_,_,step=THREE[0]
            db.execute("UPDATE ingestion_checkpoint SET records=197 WHERE document_id=%s AND step=%s",(PARENT,step))
            db.execute("SET ROLE agro_reader")
            self.assertTrue(db.execute(held_sql,(did,)).fetchone()[0])
            self.assertFalse(db.execute(held_sql,(THREE[1][0],)).fetchone()[0])
            db.execute("RESET ROLE")
            db.execute("UPDATE ingestion_checkpoint SET records=198 WHERE document_id=%s AND step=%s",(PARENT,step))
            db.execute("SET ROLE agro_reader")
            self.assertFalse(db.execute(held_sql,(did,)).fetchone()[0])
            db.execute("RESET ROLE")
            db.execute("INSERT INTO city_pdf_publication_conflict VALUES(4,%s,%s,%s,'city-v8',%s,%s,%s)",
                       (did,PARENT,entry,NATIVE_SHA,STORED_SHA,Jsonb({"difference_fields":["price"],"difference_count":1})))
            db.execute("SET ROLE agro_reader")
            self.assertTrue(db.execute(held_sql,(did,)).fetchone()[0])
            self.assertFalse(db.execute(held_sql,(THREE[1][0],)).fetchone()[0])
            db.execute("RESET ROLE")
            self.assertEqual(db.execute("SELECT count(*) FROM regional_price").fetchone()[0],594)
            self.assertEqual(db.execute("SELECT count(*) FROM regional_classification").fetchone()[0],594)
            self.assertEqual(db.execute("SELECT count(*) FROM city_pdf_publication_conflict").fetchone()[0],4)
            self.assertEqual(db.execute("SELECT count(*) FROM city_pdf_category_resolution").fetchone()[0],3)

    def test_all_three_atomic_rollback_commit_acl_and_requarantine(self):
        with self.connect() as db:
            self.apply(db)
            self.assert_native(db)
            db.rollback()
        self.assertIsNone(self.admin.execute("SELECT to_regclass(%s)",(self.schema+".city_pdf_category_resolution",)).fetchone()[0])
        self.assertEqual(self.admin.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],0)
        self.assertEqual(self.admin.execute("SELECT count(*) FROM published_regional_price").fetchone()[0],0)
        with self.connect() as db:
            self.apply(db)
            self.assert_native(db)
            db.commit()
        audit_before=self.admin.execute("SELECT * FROM city_pdf_category_resolution ORDER BY document_id").fetchall()
        proof_check_before=self.admin.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='city_category_overlay_proof'::regclass AND conname='city_category_overlay_proof_parser_code_sha256_check' AND convalidated").fetchone()[0]
        # The deployment manager replays every migration on later deployments.
        # Replaying SQL057/058/059 must preserve immutable audit rows and
        # restore the resolved views after SQL057 temporarily replaces one.
        with self.connect() as db:
            db.execute(SQL057.read_text())
            db.execute((HERE/"migrations/20261005_058_city_category_proof_collation.sql").read_text())
            db.execute(SQL059.read_text())
            self.assert_native(db)
            db.commit()
        self.assertEqual(self.admin.execute("SELECT * FROM city_pdf_category_resolution ORDER BY document_id").fetchall(),audit_before)
        self.assertEqual(self.admin.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='city_category_overlay_proof'::regclass AND conname='city_category_overlay_proof_parser_code_sha256_check' AND convalidated").fetchone()[0],proof_check_before)
        # A third, broadened or unvalidated CHECK is not a replay state.
        with self.connect() as db:
            db.execute("ALTER TABLE city_category_overlay_proof DROP CONSTRAINT city_category_overlay_proof_parser_code_sha256_check")
            db.execute(f"ALTER TABLE city_category_overlay_proof ADD CONSTRAINT city_category_overlay_proof_parser_code_sha256_check CHECK (parser_code_sha256 IN ('{OLD}','{NEW}','unreviewed'))")
            with self.assertRaises(psycopg.Error):
                db.execute(SQL059.read_text())
            db.rollback()
        self.assertEqual(self.admin.execute("SELECT * FROM city_pdf_category_resolution ORDER BY document_id").fetchall(),audit_before)
        self.assert_native(self.admin)
        self.assertFalse(self.admin.execute("SELECT has_table_privilege('agro_ingestor','city_pdf_category_resolution','INSERT')").fetchone()[0])
        self.assertFalse(self.admin.execute("SELECT has_table_privilege('agro_reader','city_pdf_category_resolution','INSERT')").fetchone()[0])
        self.assertEqual(self.admin.execute("SELECT count(*) FROM regional_price").fetchone()[0],594)
        self.assertEqual(self.admin.execute("SELECT count(*) FROM regional_classification").fetchone()[0],594)
        with self.connect() as db:
            with self.assertRaises(psycopg.Error):
                db.execute("DELETE FROM city_pdf_category_resolution")
            db.rollback()
        with self.connect() as db:
            did,entry,*_=THREE[0]
            db.execute("INSERT INTO city_pdf_publication_conflict VALUES(4,%s,%s,%s,'city-v8',%s,%s,%s)",
                       (did,PARENT,entry,NATIVE_SHA,STORED_SHA,Jsonb({"difference_fields":["price"],"difference_count":1})))
            self.assertEqual(db.execute("SELECT count(*) FROM unresolved_city_pdf_publication_conflict").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM resolved_regional_price WHERE document_id=%s",(did,)).fetchone()[0],0)
            db.rollback()
        self.assert_native(self.admin)
