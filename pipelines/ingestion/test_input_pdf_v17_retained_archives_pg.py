"""Full-schema regression for retained input PDFs and interrupted worker retries."""
import gzip
import hashlib
import json
import os
import io
import unittest
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter

import psycopg
from psycopg.types.json import Jsonb

from . import input_pdf_v17_replay as replay
from . import ocr, pdf_sources, queue_plan, worker

FIXTURES = Path(__file__).parent / "testdata" / "input_pdf_v17_nov_dec_private"
META = json.loads((FIXTURES / "METADATA_ONLY_FIRST_B.json").read_text())
CASES = {
    "2012-11-30": {
        "body": "2012-11-30_original.pdf",
        "vector": "2012-11-30_V14_FULL_VECTOR_FIRST_C.json.gz",
        "new_vector": "2012-11-30_V17_FULL_VECTOR.json.gz",
        "raw": 8036, "typed": 7997, "unresolved": 39,
        "new_raw": 8221, "new_typed": 8177, "new_unresolved": 44, "added": 185,
    },
    "2012-12-31": {
        "body": "2012-12-31_original.pdf",
        "vector": "2012-12-31_V14_FULL_VECTOR_FIRST_C.json.gz",
        "new_vector": "2012-12-31_V17_FULL_VECTOR.json.gz",
        "raw": 7833, "typed": 7726, "unresolved": 107,
        "new_raw": 8005, "new_typed": 7895, "new_unresolved": 110, "added": 172,
    },
}
CASE_BY_DATE = {case["asset"]["observed_on"]: case for case in META["cases"]}


def vector_rows(path):
    obj = json.loads(gzip.decompress(path.read_bytes()))
    rows = []
    for row in obj["rows"]:
        rows.append((
            row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
            row["product_name"], row["market_name"], row["unit"], Decimal(row["price"]),
            Decimal(row["change_percent"]) if row["change_percent"] is not None else None,
            row["details"],
        ))
    return obj, rows


def publication_rows(day, kind):
    path = FIXTURES / f"{day}_{kind}_THIRTEEN_FIELDS_FIRST_A.json.gz"
    obj = json.loads(gzip.decompress(path.read_bytes()))
    rows = []
    for row in obj["rows"]:
        rows.append((row["id"], row["department"], date.fromisoformat(row["observed_on"]),
                     row["name"], row["category"], row["presentation"], Decimal(row["price"]),
                     row["document_id"], row["source_locator"], row["brand"],
                     row["registration"], row["product_line"], row["municipality"]))
    return obj, rows


def expected_v17_projection(day, *, document_id=None):
    """Map the pinned native v17 price vector through the maintained identity contract."""
    from .inputs import CATEGORIES, identity
    spec = CASES[day]
    _obj, rows = vector_rows(FIXTURES / spec["new_vector"])
    replacement_id = document_id or _obj["document_id"]
    staged = []
    aliases = set()
    for loc, series, observed, name, market, unit, price, _change, meta in rows:
        if series != "dane-inputs-pdf" or not meta.get("municipality"):
            continue
        key = identity(name, meta)
        legacy_key = identity(name, {**meta, "line": ""})
        if key != legacy_key:
            aliases.add((legacy_key, key))
        staged.append((key, meta.get("department") or market, observed, name,
                       meta.get("category") or CATEGORIES[meta["sheet"]], unit, price,
                       replacement_id, loc, meta.get("brand", ""),
                       meta.get("ica", ""), meta.get("line", ""), meta.get("municipality", "")))
    groups = {}
    for row in staged:
        groups.setdefault((row[0],row[1],row[12],row[2]), []).append(row)
    safe = {}
    for key, grouped in groups.items():
        if min(row[6] for row in grouped) == max(row[6] for row in grouped):
            safe[key] = sorted(grouped, key=lambda row:row[8])[0]
    published = []
    for key, row in safe.items():
        superseded = False
        for legacy, replacement in aliases:
            if row[0] != legacy:
                continue
            other = safe.get((replacement,row[1],row[12],row[2]))
            if other and (other[3],other[5],other[9],other[10],other[11]) == (row[3],row[5],row[9],row[10],row[11]):
                superseded = True
                break
        if not superseded:
            published.append(row)
    if document_id is not None:
        # Equal business values intentionally keep their original physical
        # source attribution. Only new or changed identities take the new DID.
        _prior_obj, prior_rows = publication_rows(day, "published_input_municipal_price")
        prior = {(row[0], row[1], row[12], row[2]): row for row in prior_rows}
        normalized = []
        for row in published:
            key = (row[0], row[1], row[12], row[2])
            old = prior.get(key)
            if old and (row[3], row[4], row[5], row[6], row[9], row[10], row[11]) == (
                    old[3], old[4], old[5], old[6], old[9], old[10], old[11]):
                row = (*row[:7], old[7], old[8], *row[9:])
            normalized.append(row)
        published = normalized
    return sorted(staged, key=lambda row:(row[0],row[1],row[12],row[2],row[8])), safe, sorted(published, key=lambda row:(row[0],row[1],row[12],row[2]))


@unittest.skipUnless(os.environ.get("AGRO_INPUT2012_PRIVATE_TEST_DSN"),
                     "owned full-schema private PG16 required")
class Input2012V17PrivatePG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ["AGRO_INPUT2012_PRIVATE_TEST_DSN"], autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-input2012-")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.db.execute("SHOW server_version").fetchone()[0].startswith("16.")):
            cls.db.close()
            raise RuntimeError("only the owned Unix-socket PG16 cluster is allowed")
        cls.db.execute("SET ROLE agro_ingestor")
        if cls.db.execute("SELECT current_user").fetchone()[0] != "agro_ingestor":
            cls.db.close()
            raise RuntimeError("canonical agro_ingestor role is required")
        cls.db.execute("SET TIME ZONE 'UTC'")
        cls.db.execute("SET statement_timeout='240s'")
        for table in ("source_document", "ingestion_asset", "ingestion_checkpoint",
                      "historical_price", "official_source_review"):
            if cls.db.execute("SELECT count(*) FROM " + table).fetchone()[0]:
                cls.db.close()
                raise RuntimeError("owned schema must begin empty")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute("SET LOCAL statement_timeout='240s'")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def _case(self, day):
        return CASE_BY_DATE[day]

    def _seed(self, day):
        spec = CASES[day]
        source_case = self._case(day)
        asset = source_case["asset"]
        source = source_case["source"]
        body = (FIXTURES / spec["body"]).read_bytes()
        vector_path = FIXTURES / spec["vector"]
        vector, rows = vector_rows(vector_path)
        did = hashlib.sha256(body).hexdigest()
        self.assertEqual(did, asset["document_id"])
        self.assertEqual(did, source["id"])
        self.assertEqual(len(body), source["bytes"])
        self.assertEqual(len(rows), spec["raw"])
        self.assertEqual(vector["observed_on"], day)
        self.assertEqual(vector["document_id"], did)
        self.assertEqual(sum(row[1] == "dane-inputs-pdf" for row in rows), spec["typed"])
        self.assertEqual(sum(row[1] == "dane-inputs-pdf-unresolved" for row in rows), spec["unresolved"])
        self.assertTrue(all("xmin" in row for row in vector["rows"]))
        self.db.execute(
            """INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (source["id"], source["title"], source["publisher"], source["source_url"],
             source["media_type"], source["kind"], source["reference_period"],
             source["page_count"], body, Jsonb(source["metadata"])),
        )
        self.db.execute(
            """INSERT INTO ingestion_asset
            (url,kind,observed_on,status,document_id,records,error,processor_version,attempts,checked_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,now()-interval '2 days')""",
            (asset["url"], asset["kind"], date.fromisoformat(day), asset["status"],
             asset["document_id"], asset["records"], asset["error"], asset["processor_version"]),
        )
        with self.db.cursor() as cur:
            cur.executemany(
                """INSERT INTO historical_price
                (document_id,source_locator,series,observed_on,product_name,market_name,unit,
                 price,change_percent,details)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(did, *row[:-1], Jsonb(row[-1])) for row in rows],
            )
        for checkpoint in source_case["checkpoints"]:
            self.db.execute(
                """INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                VALUES(%s,%s,%s,%s)""",
                (did, checkpoint["processor_version"], checkpoint["step"], checkpoint["records"]),
            )
        raw_obj, raw_projection = publication_rows(day, "input_municipal_price")
        self.assertEqual(len(raw_obj["rows"]), len(raw_projection))
        self.assertEqual((raw_obj["document_id"], raw_obj["observed_on"]), (did, day))
        self.assertTrue(all(row[7] == did and row[2].isoformat() == day for row in raw_projection))
        with self.db.cursor() as cur:
            cur.executemany(
                """INSERT INTO input_municipal_price
                (id,department,observed_on,name,category,presentation,price,document_id,source_locator,
                 brand,registration,product_line,municipality)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                raw_projection,
            )
        pub_obj, expected_published = publication_rows(day, "published_input_municipal_price")
        self.assertEqual(len(pub_obj["rows"]), len(expected_published))
        self.assertEqual((pub_obj["document_id"], pub_obj["observed_on"]), (did, day))
        self.assertEqual(
            sorted(self._municipal_snapshot(did, published=True), key=lambda row:(row[0],row[1],row[12],row[2])),
            sorted(expected_published, key=lambda row:(row[0],row[1],row[12],row[2])),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*),count(*) FILTER(WHERE series='dane-inputs-pdf'),"
                "count(*) FILTER(WHERE series='dane-inputs-pdf-unresolved') "
                "FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14'",
                (did,),
            ).fetchone(),
            (spec["raw"], spec["typed"], spec["unresolved"]),
        )
        return asset, source, body, vector, rows

    def _seed_2016_retained_case(self, day):
        witnesses = Path(__file__).parent / "testdata" / "input_pdf_v17_retained_witnesses"
        receipt = json.loads((witnesses / "WITNESSES_FIRST_B.json").read_text())
        case = next(item for item in receipt["cases"] if item["observed_on"] == day)
        source, asset = case["source"], case["asset"]
        body = (witnesses / f"{day}_original.pdf").read_bytes()
        vector_path = witnesses / case["vector_file"]
        vector, rows = vector_rows(vector_path)
        did = hashlib.sha256(body).hexdigest()
        self.assertEqual((did, source["id"], asset["document_id"]),
                         (case["document_id"], case["document_id"], case["document_id"]))
        self.assertEqual(len(rows), case["v14_rows"])
        self.assertEqual(replay._retained_vector_sha256(rows),
                         replay._registered_v14_replacement_spec(asset["url"])["old_vector_sha256"])
        self.db.execute(
            """INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (source["id"], source["title"], source["publisher"], source["source_url"],
             source["media_type"], source["kind"], source["reference_period"],
             source["page_count"], body, Jsonb(source["metadata"])),
        )
        self.db.execute(
            """INSERT INTO ingestion_asset
            (url,kind,observed_on,status,document_id,records,error,processor_version,attempts,checked_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,now()-interval '2 days')""",
            (asset["url"], asset["kind"], date.fromisoformat(day), asset["status"],
             asset["document_id"], asset["records"], asset["error"], asset["processor_version"]),
        )
        with self.db.cursor() as cur:
            cur.executemany(
                """INSERT INTO historical_price
                (document_id,source_locator,series,observed_on,product_name,market_name,unit,
                 price,change_percent,details)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(did, *row[:-1], Jsonb(row[-1])) for row in rows],
            )
        for checkpoint in case["checkpoints"]:
            self.db.execute(
                """INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                VALUES(%s,%s,%s,%s)""",
                (did, checkpoint[0], checkpoint[1], checkpoint[2]),
            )
        return case, body, rows

    def _old_rows_snapshot(self, did):
        return self.db.execute(
            """SELECT source_locator,series,observed_on,product_name,market_name,unit,
                      price,change_percent,details,xmin::text
               FROM historical_price WHERE document_id=%s
                 AND details->>'parser_version'='inputs-pdf-v14'
               ORDER BY source_locator""", (did,),
        ).fetchall()

    def _old_checkpoint_snapshot(self, did):
        return self.db.execute(
            """SELECT processor_version,step,records,xmin::text
               FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step""",
            (did,),
        ).fetchall()

    def _source_snapshot(self, did):
        return self.db.execute(
            """SELECT xmin::text,title,publisher,source_url,media_type,kind,reference_period,
                      page_count,metadata,content
               FROM source_document WHERE id=%s""", (did,),
        ).fetchone()

    def _municipal_snapshot(self, did, *, published=False):
        relation = "published_input_municipal_price" if published else "input_municipal_price"
        xmin = "" if published else "xmin::text,"
        return self.db.execute(
            f"""SELECT {xmin}id,department,observed_on,name,category,presentation,price,document_id,
                       source_locator,brand,registration,product_line,municipality
                FROM {relation} WHERE document_id=%s ORDER BY id,department,municipality,observed_on""",
            (did,),
        ).fetchall()

    def _published_day_snapshot(self, day):
        return self.db.execute(
            """SELECT id,department,observed_on,name,category,presentation,price,document_id,
                      source_locator,brand,registration,product_line,municipality
               FROM published_input_municipal_price WHERE observed_on=%s
               ORDER BY id,department,municipality,observed_on""", (date.fromisoformat(day),),
        ).fetchall()

    @staticmethod
    def _append_blank_page(body):
        reader = PdfReader(io.BytesIO(body))
        writer = PdfWriter()
        writer.append(reader)
        last = reader.pages[-1]
        writer.add_blank_page(width=float(last.mediabox.width), height=float(last.mediabox.height))
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue(), len(reader.pages) + 1

    def test_full_v14_vectors_are_exact_v17_subsets_with_only_verified_additions(self):
        added_total = 0
        actual_added_fields = []
        for day, spec in CASES.items():
            source_case = self._case(day)
            body = (FIXTURES / spec["body"]).read_bytes()
            old_vector, old_rows = vector_rows(FIXTURES / spec["vector"])
            new_rows = list(pdf_sources.parse_input_pdf(
                body, date.fromisoformat(day), parser_version=replay.VERSION
            ))
            stored_v17, stored_v17_rows = vector_rows(FIXTURES / spec["new_vector"])
            self.assertEqual(stored_v17["document_id"], source_case["asset"]["document_id"])
            self.assertEqual(stored_v17["parser_version"], replay.VERSION)
            self.assertEqual([replay._as_vector(row) for row in new_rows], stored_v17_rows)
            old = {replay._normalized_old(row)[0]: replay._normalized_old(row) for row in old_rows}
            new = {row[0]: replay._as_vector(row) for row in new_rows}
            self.assertEqual((len(old_rows), len(new_rows)), (spec["raw"], spec["new_raw"]))
            self.assertEqual({key: new[key] for key in old}, old)
            added_keys = new.keys() - old.keys()
            self.assertEqual(len(added_keys), spec["added"])
            for row in new_rows:
                if row[0] in added_keys:
                    actual_added_fields.append({
                        "source_locator": row[0], "series": row[1],
                        "observed_on": row[2].isoformat(), "product_name": row[3],
                        "market_name": row[4], "unit": row[5], "price": str(row[6]),
                        "change_percent": None if row[7] is None else str(row[7]),
                        "details": row[8], "source_date": day,
                        "document_id": source_case["asset"]["document_id"],
                    })
            self.assertEqual(
                {name: sum(row[1] == name for row in new_rows)
                 for name in ("dane-inputs-pdf", "dane-inputs-pdf-unresolved")},
                {"dane-inputs-pdf": spec["new_typed"],
                 "dane-inputs-pdf-unresolved": spec["new_unresolved"]},
            )
            self.assertEqual(old_vector["document_id"], source_case["asset"]["document_id"])
            added_total += spec["added"]
        self.assertEqual(added_total, 357)
        saved_added = json.loads((FIXTURES / "ALL_357_ADDED_LOCATORS_NINE_FIELDS.json").read_text())
        self.assertEqual((saved_added["count"], saved_added["typed"], saved_added["unresolved"]),
                         (357, 349, 8))
        self.assertEqual(actual_added_fields, saved_added["rows"])
        printed = json.loads((FIXTURES / "ROOT_2012_ADDITIONS_PRINTED_SPOTS_FIRST_C.json").read_text())
        self.assertEqual(len(printed["spots"]), 15)
        by_locator = {row["source_locator"]: row for row in actual_added_fields}
        for spot in printed["spots"]:
            row = by_locator[spot["locator"]]
            self.assertEqual((row["observed_on"], row["product_name"], row["unit"], Decimal(row["price"])),
                             (spot["observation_month_end_anchor"], spot["product"], spot["unit"], Decimal(str(spot["price"]))))
            self.assertEqual(row["details"].get("municipality"), spot["printed_municipality"])
            self.assertEqual(Decimal(row["change_percent"]), Decimal(str(spot["percent_change"])))

    def _exercise_failed_asset_resume(self, day, *, initial_error=None):
        spec = CASES[day]
        asset, source, body, vector, old_rows = self._seed(day)
        did, url = asset["document_id"], asset["url"]
        def retained_archive(db, archive_url, archive_body, kind, archived_day=None, **kwargs):
            self.assertEqual((archive_url, archive_body, kind), (url, body, "inputs-pdf"))
            archived = db.execute(
                "SELECT source_url,kind,media_type,content FROM source_document WHERE id=%s",
                (did,),
            ).fetchone()
            self.assertEqual(archived, (source["source_url"], "original", "application/pdf", body))
            return did

        if initial_error is not None:
            from .resumable_inputs import WorkDeferred
            token = worker.RUN_DEADLINE.set(time.monotonic() - 1)
            try:
                with patch.object(worker, "fetch_asset", side_effect=AssertionError("network fetch forbidden")), \
                        patch.object(worker, "archive", side_effect=retained_archive), \
                        patch.object(ocr, "transcribe", side_effect=AssertionError("provider calls forbidden")), \
                        self.assertRaises(WorkDeferred) as budget_error:
                    worker.process_asset(self.db, url, "inputs-pdf", date.fromisoformat(day))
            finally:
                worker.RUN_DEADLINE.reset(token)
            self.assertEqual(str(budget_error.exception), initial_error)
            # This is the same durable state transition used by run_ingestion
            # after WorkDeferred; the following call is a separate worker pass.
            self.db.execute(
                "UPDATE ingestion_asset SET status=CASE WHEN status='review' THEN 'review' "
                "WHEN %s AND status='failed' THEN 'failed' ELSE 'pending' END,"
                "checked_at=now()-interval '6 hours',error=%s WHERE url=%s",
                (False, str(budget_error.exception), url),
            )
            state = self.db.execute(
                "SELECT status,records,error,document_id,processor_version FROM ingestion_asset WHERE url=%s",
                (url,),
            ).fetchone()
            self.assertEqual(state, ("pending", spec["raw"], initial_error, did, replay.VERSION))
            asset = {**asset, "status": "pending", "processor_version": replay.VERSION,
                     "records": spec["raw"], "error": initial_error}
        before_old = self._old_rows_snapshot(did)
        before_cp = self._old_checkpoint_snapshot(did)
        before_source = self._source_snapshot(did)
        raw_obj, _ = publication_rows(day, "input_municipal_price")
        pub_obj, _ = publication_rows(day, "published_input_municipal_price")
        before_municipal = self._municipal_snapshot(did)
        before_published = self._municipal_snapshot(did, published=True)
        self.assertEqual(len(before_municipal), len(raw_obj["rows"]))
        self.assertEqual(len(before_published), len(pub_obj["rows"]))
        self.assertEqual(
            sorted([row[1:] for row in before_municipal], key=lambda row:(row[0],row[1],row[12],row[2])),
            sorted(publication_rows(day, "input_municipal_price")[1], key=lambda row:(row[0],row[1],row[12],row[2])),
        )
        unresolved_before = sum(row[1] == "dane-inputs-pdf-unresolved" for row in old_rows)
        self.assertEqual(len(before_old), spec["raw"])
        self.assertEqual(unresolved_before, spec["unresolved"])

        # The current production error must be reproduced as an atomic
        # publication interruption after native extraction and row COPY.
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("network fetch forbidden")), \
                patch.object(worker, "archive", side_effect=retained_archive), \
                patch.object(worker, "project", side_effect=RuntimeError("synthetic publication interruption")), \
                patch.object(ocr, "transcribe", side_effect=AssertionError("provider calls forbidden")):
            with self.assertRaisesRegex(RuntimeError, "synthetic publication interruption"):
                worker.process_asset(self.db, url, "inputs-pdf", date.fromisoformat(day))
        self.assertEqual(self.db.execute(
            "SELECT status,records,error,document_id,processor_version FROM ingestion_asset WHERE url=%s",
            (url,),
        ).fetchone(), ("pending", asset["records"], asset["error"], did, asset["processor_version"]))
        self.assertEqual(self._old_rows_snapshot(did), before_old)
        self.assertEqual(self._old_checkpoint_snapshot(did), before_cp)
        self.assertEqual(self._source_snapshot(did), before_source)
        self.assertEqual(self._municipal_snapshot(did), before_municipal)
        self.assertEqual(self._municipal_snapshot(did, published=True), before_published)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
            (did, replay.VERSION),
        ).fetchone()[0], 0)
        self.assertIsNone(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
            "AND step='inputs-pdf:published'", (did, replay.VERSION),
        ).fetchone())

        with patch.object(worker, "fetch_asset", side_effect=AssertionError("retained retry attempted network")), \
                patch.object(worker, "archive", side_effect=retained_archive), \
                patch.object(ocr, "transcribe", side_effect=AssertionError("provider calls forbidden")):
            count = worker.process_asset(self.db, url, "inputs-pdf", date.fromisoformat(day))
        self.assertEqual(count, spec["new_raw"])
        self.assertEqual(self._old_rows_snapshot(did), before_old)
        after_cp = self._old_checkpoint_snapshot(did)
        self.assertEqual([row for row in after_cp if row[0] != replay.VERSION], before_cp)
        new_checkpoints = [row for row in after_cp if row[0] == replay.VERSION]
        self.assertEqual(len(new_checkpoints), 1)
        self.assertEqual(new_checkpoints[0][2], spec["new_typed"])
        self.assertEqual(self._source_snapshot(did), before_source)
        stage_rows = self.db.execute(
            """SELECT id,department,observed_on,name,category,presentation,price,document_id,
                      source_locator,brand,registration,product_line,municipality
               FROM input_stage WHERE municipality<>'' ORDER BY id,department,municipality,observed_on,source_locator"""
        ).fetchall()
        by_key = {}
        for row in stage_rows:
            key = (row[0], row[1], row[12], row[2])
            by_key.setdefault(key, []).append(row)
        safe_stage = {}
        ambiguous_stage = set()
        for key, rows in by_key.items():
            if min(row[6] for row in rows) == max(row[6] for row in rows):
                safe_stage[key] = rows[0]
            else:
                ambiguous_stage.add(key)
        after_municipal = self._municipal_snapshot(did)
        old_by_key = {(row[1], row[2], row[13], row[3]): row for row in before_municipal}
        actual_by_key = {(row[1], row[2], row[13], row[3]): row for row in after_municipal}
        self.assertEqual(len(actual_by_key), len(after_municipal))
        for key, expected in safe_stage.items():
            self.assertIn(key, actual_by_key)
            actual = actual_by_key[key][1:]
            self.assertEqual(actual, expected)
        for key, actual in actual_by_key.items():
            if key not in safe_stage:
                self.assertIn(key, old_by_key)
                if key in ambiguous_stage:
                    # A conflicting group is deliberately withheld from this v17 publication.
                    pass
                else:
                    # A prior projection may contain identities absent from the new parsed source;
                    # publication leaves those physical rows intact, while the checkpoint hides them.
                    self.assertNotIn(key, by_key)
                self.assertEqual(actual[1:], old_by_key[key][1:])
        expected_stage, expected_safe, expected_published = expected_v17_projection(day)
        actual_stage = self.db.execute(
            """SELECT id,department,observed_on,name,category,presentation,price,document_id,
                      source_locator,brand,registration,product_line,municipality
               FROM input_stage WHERE municipality<>'' ORDER BY id,department,municipality,observed_on,source_locator"""
        ).fetchall()
        self.assertEqual(actual_stage, expected_stage)
        after_published = self._municipal_snapshot(did, published=True)
        self.assertEqual(
            sorted(after_published, key=lambda row:(row[0],row[1],row[12],row[2])),
            expected_published,
        )
        expected_error = "Conflicting source keys retained but excluded from app: 3" if day == "2012-11-30" else None
        self.assertEqual(self.db.execute(
            "SELECT status,records,error,document_id,processor_version FROM ingestion_asset WHERE url=%s",
            (url,),
        ).fetchone(), ("complete", spec["new_raw"], expected_error, did, asset["processor_version"]))
        self.assertEqual(self.db.execute(
            """SELECT count(*),count(*) FILTER(WHERE series='dane-inputs-pdf'),
               count(*) FILTER(WHERE series='dane-inputs-pdf-unresolved')
               FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s""",
            (did, replay.VERSION),
        ).fetchone(), (spec["new_raw"], spec["new_typed"], spec["new_unresolved"]))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
            "AND step='inputs-pdf:published'", (did, replay.VERSION),
        ).fetchone(), (spec["new_typed"],))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'='inputs-pdf-v14' AND series='dane-inputs-pdf-unresolved'",
            (did,),
        ).fetchone()[0], unresolved_before)
        # Ordinary scheduling must not retry a completed source.
        self.assertNotIn(url, [candidate[0] for candidate in queue_plan.backfill_candidates(self.db, 1000)])

    def test_registered_source_specs_are_complete_and_hash_pinned(self):
        urls = (set(replay.RETAINED_2012_CONTEXTS)
                | set(replay.RETAINED_2013_CONTEXTS)
                | {replay.AUG2012_ALIAS_ASSET_URL, replay.FEB2016_CONTEXT_URL, replay.APR2016_CONTEXT_URL})
        self.assertEqual(len(urls), 17)
        required = {"document_id", "day", "pages", "bytes", "raw_rows", "typed_rows",
                    "unresolved_rows", "title", "filename", "metadata", "source_url",
                    "old_vector_sha256"}
        for url in sorted(urls):
            with self.subTest(url=url):
                spec = replay._registered_v14_replacement_spec(url)
                self.assertIsNotNone(spec)
                self.assertTrue(required.issubset(spec))
                self.assertRegex(spec["old_vector_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(spec["raw_rows"], spec["typed_rows"] + spec["unresolved_rows"])

    def test_registered_prefetch_rejects_wrong_binding_and_pending_reason(self):
        asset, source, _body, _vector, _rows = self._seed("2012-11-30")
        url, day, did = asset["url"], date.fromisoformat("2012-11-30"), asset["document_id"]

        class ReadOverride:
            def __init__(self, connection, transform):
                self.connection, self.transform = connection, transform
            def execute(self, query, params=None):
                cursor = self.connection.execute(query, params)
                if "SELECT kind,source_url,media_type,page_count,content,metadata" in query:
                    row = cursor.fetchone()
                    return OneRow(self.transform(row)) if row is not None else OneRow(None)
                return cursor

        class OneRow:
            def __init__(self, row): self.row = row
            def fetchone(self): return self.row

        def mutate(index, value):
            def apply(row):
                row = list(row); row[index] = value; return tuple(row)
            return apply

        for label, proxy, supplied_day in (
            ("metadata", ReadOverride(self.db, mutate(5, {"ingestion_kind": "wrong"})), day),
            ("body", ReadOverride(self.db, mutate(4, b"%PDF-corrupted")), day),
            ("date", self.db, date.fromisoformat("2012-12-01")),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                replay.retained_v14_input_pdf(proxy, url, "inputs-pdf", supplied_day, replay.VERSION)

        url_spec = replay.RETAINED_2012_CONTEXTS[url]
        altered = {**url_spec, "old_vector_sha256": "0" * 64}
        with self.subTest(label="full-old-vector"), patch.dict(
            replay.RETAINED_2012_CONTEXTS, {url: altered}
        ), self.assertRaises(ValueError):
            replay.retained_v14_input_pdf(self.db, url, "inputs-pdf", day, replay.VERSION)

        wrong_body = b"%PDF-1.4\nvalid foreign source identity for FK negative\n"
        wrong_did = hashlib.sha256(wrong_body).hexdigest()
        self.db.execute(
            """INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (wrong_did, "Negative pointer source", source["publisher"], source["source_url"],
             "application/pdf", "original", day, 1, wrong_body, Jsonb(source["metadata"])),
        )
        self.db.execute(
            "UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (wrong_did, url)
        )
        with self.subTest(label="asset-pointer"), self.assertRaises(ValueError):
            replay.retained_v14_input_pdf(self.db, url, "inputs-pdf", day, replay.VERSION)
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (did, url))

        for status, reason in (("failed", replay.WORK_DEFERRED_RETRY_ERROR),
                               ("pending", "unrecognized pending error")):
            self.db.execute(
                "UPDATE ingestion_asset SET status=%s,error=%s WHERE url=%s",
                (status, reason, url),
            )
            with self.subTest(status=status, reason=reason), self.assertRaises(ValueError):
                replay.retained_v14_input_pdf(self.db, url, "inputs-pdf", day, replay.VERSION)

    def test_pending_workdeferred_budget_state_resumes_from_exact_retained_source(self):
        # The real budget check raises WorkDeferred; the existing interruption
        # helper then retries through process_asset and completes publication.
        self._exercise_failed_asset_resume(
            "2012-11-30", initial_error=replay.WORK_DEFERRED_RETRY_ERROR
        )

    def test_february_pending_budget_and_april_failed_prefetch_are_exact(self):
        for day in ("2016-02-29", "2016-04-30"):
            with self.subTest(day=day):
                case, body, rows = self._seed_2016_retained_case(day)
                did, url = case["document_id"], case["asset"]["url"]
                source_before = self._source_snapshot(did)
                old_rows_before = self._old_rows_snapshot(did)
                checkpoints_before = self._old_checkpoint_snapshot(did)
                asset_before = self.db.execute(
                    "SELECT status,records,error,document_id,processor_version,xmin::text "
                    "FROM ingestion_asset WHERE url=%s", (url,),
                ).fetchone()
                self.assertEqual(len(rows), replay._registered_v14_replacement_spec(url)["raw_rows"])
                actual = replay.retained_v14_input_pdf(
                    self.db, url, "inputs-pdf", date.fromisoformat(day), replay.VERSION
                )
                self.assertEqual(actual, body)
                self.assertEqual(hashlib.sha256(actual).hexdigest(), did)
                self.assertEqual(self._source_snapshot(did), source_before)
                self.assertEqual(self._old_rows_snapshot(did), old_rows_before)
                self.assertEqual(self._old_checkpoint_snapshot(did), checkpoints_before)
                self.assertEqual(self.db.execute(
                    "SELECT status,records,error,document_id,processor_version,xmin::text "
                    "FROM ingestion_asset WHERE url=%s", (url,),
                ).fetchone(), asset_before)
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
                    "AND processor_version=%s AND step='inputs-pdf:published'",
                    (did, replay.VERSION),
                ).fetchone(), (0,))

    def test_november_failed_asset_resumes_from_retained_original(self):
        self._exercise_failed_asset_resume("2012-11-30")

    def test_december_failed_asset_resumes_from_retained_original(self):
        self._exercise_failed_asset_resume("2012-12-31")

    def _exercise_registered_changed_body_retry(self, day, first_status):
        asset, source, original, _vector, _old_rows = self._seed(day)
        old_did, url = asset["document_id"], asset["url"]
        old_rows_before = self._old_rows_snapshot(old_did)
        old_cp_before = self._old_checkpoint_snapshot(old_did)
        old_source_before = self._source_snapshot(old_did)
        old_projection_before = self._published_day_snapshot(day)
        changed_body, changed_pages = self._append_blank_page(original)
        changed_did = hashlib.sha256(changed_body).hexdigest()
        self.assertNotEqual(changed_did, old_did)
        self.db.execute(
            """INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (changed_did, source["title"], source["publisher"], url, "application/pdf",
             "original", day, changed_pages, changed_body, Jsonb(source["metadata"])),
        )
        changed_source_before = self._source_snapshot(changed_did)
        retry_error = "ValueError: retained registered body interrupted before retry"
        self.db.execute(
            """UPDATE ingestion_asset SET document_id=%s,status=%s,processor_version=%s,
               records=%s,error=%s WHERE url=%s""",
            (changed_did, first_status, replay.VERSION, asset["records"], retry_error, url),
        )
        self.assertIsNone(replay.retained_v14_input_pdf(
            self.db, url, "inputs-pdf", date.fromisoformat(day), replay.VERSION))

        def exact_fetch(db, fetch_url, *args, **kwargs):
            self.assertEqual(fetch_url, url)
            return changed_body

        def exact_archive(db, archive_url, body, kind, archived_day=None, **kwargs):
            self.assertEqual((archive_url, body, kind), (url, changed_body, "inputs-pdf"))
            return changed_did

        with patch.object(worker, "fetch_asset", side_effect=exact_fetch) as fetch_mock, \
                patch.object(worker, "archive", side_effect=exact_archive) as archive_mock, \
                patch.object(ocr, "transcribe", side_effect=AssertionError("provider calls forbidden")) as transcribe_mock:
            self.assertEqual(worker.process_asset(
                self.db, url, "inputs-pdf", date.fromisoformat(day)), CASES[day]["new_raw"])
        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(archive_mock.call_count, 1)
        transcribe_mock.assert_not_called()

        self.assertEqual(self._source_snapshot(old_did), old_source_before)
        self.assertEqual(self._source_snapshot(changed_did), changed_source_before)
        self.assertEqual(self._old_rows_snapshot(old_did), old_rows_before)
        self.assertEqual(self._old_checkpoint_snapshot(old_did), old_cp_before)
        actual_new_rows = self.db.execute(
            f"SELECT {replay.ROW_FIELDS} FROM historical_price WHERE document_id=%s "
            "AND details->>'parser_version'=%s ORDER BY source_locator",
            (changed_did, replay.VERSION),
        ).fetchall()
        expected_obj, expected_new_rows = vector_rows(FIXTURES / CASES[day]["new_vector"])
        self.assertEqual(sorted(actual_new_rows, key=lambda row: row[0]), sorted(expected_new_rows, key=lambda row: row[0]))
        self.assertEqual(len(actual_new_rows), CASES[day]["new_raw"])
        self.assertEqual(self.db.execute(
            "SELECT status,records,document_id,processor_version FROM ingestion_asset WHERE url=%s",
            (url,),
        ).fetchone(), ("complete", CASES[day]["new_raw"], changed_did, replay.VERSION))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='inputs-pdf:published'",
            (changed_did, replay.VERSION),
        ).fetchone(), (CASES[day]["new_typed"],))
        expected_stage, _safe, expected_public = expected_v17_projection(day, document_id=changed_did)
        staged = self.db.execute(
            """SELECT id,department,observed_on,name,category,presentation,price,document_id,
                      source_locator,brand,registration,product_line,municipality
               FROM input_stage WHERE municipality<>''
               ORDER BY id,department,municipality,observed_on,source_locator"""
        ).fetchall()
        self.assertEqual(staged, expected_stage)
        self.assertEqual(self._published_day_snapshot(day), expected_public)
        self.assertNotEqual(self._published_day_snapshot(day), old_projection_before)

        after_rows = self.db.execute(
            """SELECT source_locator,series,observed_on,product_name,market_name,unit,price,
                      change_percent,details,xmin::text FROM historical_price
               WHERE document_id=%s ORDER BY details->>'parser_version',source_locator""",
            (changed_did,),
        ).fetchall()
        after_cp = self._old_checkpoint_snapshot(old_did)
        after_new_cp = self.db.execute(
            "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (changed_did,),
        ).fetchall()
        public_once = self._published_day_snapshot(day)
        with patch.object(worker, "fetch_asset", side_effect=exact_fetch) as repeat_fetch, \
                patch.object(worker, "archive", side_effect=exact_archive) as repeat_archive, \
                patch.object(ocr, "transcribe", side_effect=AssertionError("provider calls forbidden")) as repeat_transcribe:
            self.assertEqual(worker.process_asset(
                self.db, url, "inputs-pdf", date.fromisoformat(day)), 0)
        self.assertEqual(repeat_fetch.call_count, 1)
        self.assertEqual(repeat_archive.call_count, 1)
        repeat_transcribe.assert_not_called()
        self.assertEqual(self._published_day_snapshot(day), public_once)
        self.assertEqual(self._source_snapshot(old_did), old_source_before)
        self.assertEqual(self._source_snapshot(changed_did), changed_source_before)
        self.assertEqual(self.db.execute(
            """SELECT source_locator,series,observed_on,product_name,market_name,unit,price,
                      change_percent,details,xmin::text FROM historical_price
               WHERE document_id=%s ORDER BY details->>'parser_version',source_locator""",
            (changed_did,),
        ).fetchall(), after_rows)
        self.assertEqual(self._old_checkpoint_snapshot(old_did), after_cp)
        self.assertEqual(self.db.execute(
            "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (changed_did,),
        ).fetchall(), after_new_cp)

    def test_november_changed_body_failed_asset_retries_normally(self):
        self._exercise_registered_changed_body_retry("2012-11-30", "failed")

    def test_december_changed_body_pending_asset_retries_normally(self):
        self._exercise_registered_changed_body_retry("2012-12-31", "pending")
