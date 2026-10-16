"""Full-schema lifecycle regression for eleven retained 2013 input PDFs."""
from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pdfplumber
import psycopg
from pypdf import PdfReader, PdfWriter
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
REPO = next(parent for parent in HERE.parents if (parent / "pipelines/ingestion/schema.sql").is_file())
PRESERVED_TEMP_DIRS = []
CANDIDATE = HERE / "input_pdf_v17_replay.py"
MANIFEST = json.loads((HERE / "testdata" / "2013_source_manifest.json").read_text())
MODULE_KEY = "pipelines.ingestion.input_pdf_v17_replay"


def load_candidate():
    spec = importlib.util.spec_from_file_location(MODULE_KEY, CANDIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def candidate_module(candidate):
    package = importlib.import_module("pipelines.ingestion")
    previous_module = __import__("sys").modules.get(MODULE_KEY)
    previous_attr = getattr(package, "input_pdf_v17_replay", None)
    __import__("sys").modules[MODULE_KEY] = candidate
    package.input_pdf_v17_replay = candidate
    try:
        yield
    finally:
        if previous_module is None:
            __import__("sys").modules.pop(MODULE_KEY, None)
        else:
            __import__("sys").modules[MODULE_KEY] = previous_module
        if previous_attr is None:
            delattr(package, "input_pdf_v17_replay")
        else:
            package.input_pdf_v17_replay = previous_attr


def canonical_number(value):
    if value is None:
        return None
    number = Decimal(str(value))
    return "0" if number == 0 else format(number.normalize(), "f")


def old_sql_vector_hash(case):
    keys = [key for key in ("v14_business_vector_sha256_sql", "old_v14_business_vector_sha256_sql") if key in case]
    if len(keys) == 1:
        return case[keys[0]]
    if len(keys) == 2 and case[keys[0]] == case[keys[1]]:
        return case[keys[0]]
    raise AssertionError(f"old SQL vector hash metadata is absent or inconsistent: {case.get('month')}")


def canonical_business_sha(rows):
    result = []
    for row in rows:
        result.append([
            row[0], row[1], row[2].isoformat() if hasattr(row[2], "isoformat") else row[2],
            row[3], row[4], row[5], canonical_number(row[6]), canonical_number(row[7]), row[8],
        ])
    result.sort(key=lambda row: row[0])
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def v17_rows_as_v14(rows):
    return [
        (row[0][:-len("inputs-pdf-v17")] + "inputs-pdf-v14", *row[1:8],
         {**row[8], "parser_version": "inputs-pdf-v14"})
        for row in rows
    ]


def old_v14_rows(case):
    path = HERE / "testdata" / f"{case['month']}2013_v14_rows.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    return [tuple(row[:2] + [date.fromisoformat(row[2])] + row[3:]) for row in raw]


def full_sql_v14_rows(case):
    path = HERE / "testdata" / f"{case['month']}2013_v14_sql_full.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        export = json.load(stream)
    raw = export.get("rows", [])
    if len(raw) != case["raw_rows"]:
        raise AssertionError(f"full SQL old-row export shape changed: {case['month']}")
    if raw and isinstance(raw[0], dict):
        return [(
            row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
            row["product_name"], row["market_name"], row["unit"], row["price"],
            row["change_percent"], row["details"],
        ) for row in raw]
    if export.get("columns", [])[-1:] != ["xmin"]:
        raise AssertionError(f"full SQL old-row export lacks xmin: {case['month']}")
    return [tuple(row[:2] + [date.fromisoformat(row[2])] + row[3:9]) for row in raw]


def expected_v17_rows(case, old_rows):
    path = HERE / "testdata" / f"{case['month']}2013_v17_rows.json.gz"
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            raw = json.load(stream)
        return [tuple(row[:2] + [date.fromisoformat(row[2])] + row[3:8] + [row[8]]) for row in raw]
    return [
        (row[0][:-len("inputs-pdf-v14")] + "inputs-pdf-v17", *row[1:8],
         {**row[8], "parser_version": "inputs-pdf-v17"})
        for row in old_rows
    ]


def phase(test_name, month, state):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {test_name} {month} {state}", flush=True)


class AlteredSourceResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class AlteredReadOnlySource:
    """Return a corrupted read view without updating immutable source_document."""
    def __init__(self, conn, did, mode):
        self.conn, self.did, self.mode = conn, did, mode

    def execute(self, query, params=None):
        row = self.conn.execute(query, params)
        if (self.mode in ("old-price", "old-details") and params
                and params[0] == self.did
                and query.lstrip().startswith("SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details FROM historical_price")):
            values = [list(value) for value in row.fetchall()]
            if values:
                if self.mode == "old-price":
                    values[0][6] = Decimal(str(values[0][6])) + Decimal("1")
                else:
                    values[0][8] = {**values[0][8], "quality_issue": "unreviewed same-count mutation"}
            return AlteredSourceResult([tuple(value) for value in values])
        if params and params[0] == self.did and "FROM source_document WHERE id=%s" in query:
            values = row.fetchone()
            if values is None:
                return AlteredSourceResult([])
            values = list(values)
            if query.lstrip().startswith("SELECT kind,source_url,media_type,page_count,content,metadata"):
                if self.mode == "body":
                    values[4] = bytes(values[4]) + b"tampered"
                elif self.mode == "page-count":
                    values[3] = max(1, values[3] - 1)
                elif self.mode == "metadata":
                    values[5] = {**values[5], "original_filename": "unreviewed.pdf"}
                elif self.mode == "source-url":
                    values[1] = "https://unregistered.example/changed.pdf"
            elif query.lstrip().startswith("SELECT title,publisher,reference_period"):
                values[0] = "unreviewed title"
            return AlteredSourceResult([tuple(values)])
        return row


@unittest.skipUnless(os.environ.get("AGRO_INPUT_2013_TEST_DSN"), "Disposable local full-schema PostgreSQL DSN required")
class Retained2013InputPDFRole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = load_candidate()
        dsn = os.environ["AGRO_INPUT_2013_TEST_DSN"]
        cls.conn = psycopg.connect(dsn, autocommit=True)
        socket_path = str(cls.conn.info.host)
        if (not socket_path.startswith("/tmp/agro-input-2013-")
                or cls.conn.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.conn.execute("SHOW server_version").fetchone()[0].startswith("16.")
                or cls.conn.execute("SHOW TimeZone").fetchone()[0] != "UTC"
                or cls.conn.execute("SELECT current_user").fetchone()[0] != "postgres"):
            cls.conn.close()
            raise AssertionError("expected the owned local PostgreSQL 16 Unix-socket database")
        from pipelines.ingestion import inputs, worker
        cls.inputs, cls.worker = inputs, worker
        cls.rows_by_month = {}
        for case in MANIFEST["cases"]:
            body = (HERE / "testdata" / f"{case['month']}2013_original.pdf").read_bytes()
            if len(body) != case["body_bytes"] or hashlib.sha256(body).hexdigest() != case["document_id"]:
                raise AssertionError(f"original fixture drift: {case['month']}")
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                if len(pdf.pages) != case["page_count"]:
                    raise AssertionError(f"page count drift: {case['month']}")
            old_rows = old_v14_rows(case)
            sql_rows = full_sql_v14_rows(case)
            old_sha = old_sql_vector_hash(case)
            if (len(old_rows) != case["raw_rows"] or
                    sum(row[1] == "dane-inputs-pdf" for row in old_rows) != case["typed_rows"] or
                    sum(row[1] == "dane-inputs-pdf-unresolved" for row in old_rows) != case["unresolved_rows"] or
                    canonical_business_sha(old_rows) != old_sha):
                raise AssertionError(f"pinned SQL full-vector fixture drift: {case['month']}")
            if canonical_business_sha(sql_rows) != old_sha or canonical_business_sha(sql_rows) != canonical_business_sha(old_rows):
                raise AssertionError(f"saved full SQL export differs from the seeded old cohort: {case['month']}")
            cls.rows_by_month[case["month"]] = old_rows
            source_meta = case["source_metadata"]
            # Each source's rows and publication are one fixture transaction.
            # ON COMMIT DROP then removes save_rows' temp stage before the next PDF.
            with cls.conn.transaction():
                cls.conn.execute("""INSERT INTO source_document
                    (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
                    VALUES(%s,%s,%s,%s,'application/pdf','original',%s,%s,%s,%s)""",
                    (case["document_id"],case["title"],case["publisher"],case["url"],
                     date.fromisoformat(case["observed_on"]),case["page_count"],body,Jsonb(source_meta)))
                old_asset = case["expected_old_asset"]
                cls.conn.execute("""INSERT INTO ingestion_asset
                    (url,kind,observed_on,document_id,status,processor_version,records,error)
                    VALUES(%s,'inputs-pdf',%s,%s,%s,%s,%s,%s)""",
                    (case["url"],date.fromisoformat(case["observed_on"]),case["document_id"],
                     old_asset["status"],old_asset["processor_version"],old_asset["records"],old_asset["error"]))
                cls.conn.execute("SET ROLE agro_ingestor")
                try:
                    with patch.object(cls.inputs, "input_pdf_version_for_document", return_value=cls.candidate.OLD_VERSION):
                        cls.worker.save_rows(cls.conn,case["document_id"],old_rows)
                        cls.inputs.project_pdf_inputs(cls.conn,case["document_id"],source_url=case["url"])
                finally:
                    cls.conn.execute("RESET ROLE")
        cls.initial = {}
        for case in MANIFEST["cases"]:
            did, url = case["document_id"], case["url"]
            cls.initial[did] = {
                "source_xmin": cls.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],
                "old_checkpoint": cls.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,cls.candidate.OLD_VERSION)).fetchone(),
                "old_xmins": cls.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,cls.candidate.OLD_VERSION)).fetchone()[0],
                "old_rows": cls.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,cls.candidate.OLD_VERSION)).fetchone()[0],
                "body_sha": hashlib.sha256(cls.conn.execute("SELECT content FROM source_document WHERE id=%s",(did,)).fetchone()[0]).hexdigest(),
                "published_vector": cls.published_vector(did),
            }
            if cls.initial[did]["published_vector"] != cls.expected_published_vector(cls.rows_by_month[case["month"]], did):
                raise AssertionError(f"v14 baseline projection differs from exact SQL source vector: {case['month']}")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None):
            cls.conn.close()

    @classmethod
    def published_vector(cls, did):
        cursor = cls.conn.execute("SELECT * FROM published_input_municipal_price WHERE document_id=%s",(did,))
        columns = [item.name for item in cursor.description]
        rows = [dict(zip(columns,row)) for row in cursor.fetchall()]
        return cls.canonical_dicts(rows)

    @classmethod
    def canonical_dicts(cls, rows):
        normalized=[]
        for row in rows:
            row=dict(row)
            if "source_locator" in row and isinstance(row["source_locator"],str):
                row["source_locator"] = re.sub(r"inputs-pdf-v\d+$","inputs-pdf-v14",row["source_locator"])
            if row.get("parser_version") == "inputs-pdf-v17":
                row["parser_version"] = "inputs-pdf-v14"
            normalized.append(row)
        def primitive(value):
            if hasattr(value,"isoformat"):
                return value.isoformat()
            if isinstance(value,(int,float,Decimal)) and not isinstance(value,bool):
                return canonical_number(value)
            if isinstance(value,dict):
                return {key:primitive(item) for key,item in value.items()}
            if isinstance(value,(list,tuple)):
                return [primitive(item) for item in value]
            return value
        return sorted((primitive(row) for row in normalized),key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))

    @classmethod
    def expected_published_vector(cls, rows, did):
        """Apply the maintained identity/grouping rules to the pinned native vector."""
        mapped = []
        for row in rows:
            loc, series, day, name, market, unit, price, _variation, meta = row
            if series != "dane-inputs-pdf":
                continue
            if not meta.get("municipality"):
                continue
            item = (
                cls.inputs.identity(name, meta), meta.get("department") or market,
                day, name, meta.get("category") or cls.inputs.CATEGORIES[meta["sheet"]],
                unit, Decimal(str(price)), did, loc, meta.get("brand", ""), meta.get("ica", ""),
                meta.get("line", ""), meta.get("municipality", ""),
            )
            mapped.append(item)
        by_key = {}
        for row in mapped:
            key = (row[0], row[1], row[12], row[2])
            by_key.setdefault(key, []).append(row)
        expected = []
        for values in by_key.values():
            if len({Decimal(str(row[6])) for row in values}) != 1:
                continue
            expected.append(min(values, key=lambda row: row[8]))
        columns = ("id", "department", "observed_on", "name", "category", "presentation", "price",
                   "document_id", "source_locator", "brand", "registration", "product_line", "municipality")
        return cls.canonical_dicts([dict(zip(columns, row)) for row in expected])

    @classmethod
    def expected_conflict_count(cls, rows):
        prices = {}
        for row in rows:
            if row[1] != "dane-inputs-pdf":
                continue
            meta = row[8]
            key = (cls.inputs.identity(row[3], meta), meta.get("department") or row[4],
                   meta.get("municipality", ""), row[2])
            prices.setdefault(key, set()).add(Decimal(str(row[6])))
        return sum(len(values) > 1 for values in prices.values())

    @classmethod
    def published_day_vector(cls, day):
        cursor = cls.conn.execute(
            "SELECT * FROM published_input_municipal_price WHERE observed_on=%s", (day,)
        )
        columns = [item.name for item in cursor.description]
        return cls.canonical_dicts([dict(zip(columns, row)) for row in cursor.fetchall()])

    @classmethod
    def published_day_xmins(cls, day):
        cursor = cls.conn.execute(
            """SELECT id,department,municipality,observed_on,name,category,presentation,price,
                      document_id,source_locator,brand,registration,product_line,xmin::text AS xmin
               FROM input_municipal_price WHERE observed_on=%s
               ORDER BY id,department,municipality,observed_on""", (day,)
        )
        columns = [item.name for item in cursor.description]
        return cls.canonical_dicts([dict(zip(columns, row)) for row in cursor.fetchall()])

    @classmethod
    def source_state(cls, did):
        source = cls.conn.execute(
            "SELECT xmin::text,content,metadata,source_url,reference_period,page_count "
            "FROM source_document WHERE id=%s", (did,)
        ).fetchone()
        if source is None:
            return None
        return {
            "source_xmin": source[0],
            "body_sha256": hashlib.sha256(source[1]).hexdigest(),
            "metadata": source[2], "source_url": source[3],
            "reference_period": str(source[4]), "page_count": source[5],
            "rows": cls.conn.execute(
                """SELECT count(*),md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator))
                   FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v17'""",
                (did,),
            ).fetchone(),
            "checkpoint": cls.conn.execute(
                """SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s
                   AND processor_version='inputs-pdf-v17' AND step='inputs-pdf:published'""", (did,)
            ).fetchone(),
            "published": cls.published_vector(did),
        }

    def test_d_registered_mutable_url_updates_continue_through_normal_worker(self):
        """Changed same-URL originals are archived and parsed as new v17 bodies."""
        from pipelines.ingestion import ocr
        registered_urls = (list(self.candidate.RETAINED_2013_CONTEXTS)
                           + list(self.candidate.RETAINED_2012_CONTEXTS)
                           + [self.candidate.AUG2012_ALIAS_ASSET_URL,
                              self.candidate.FEB2016_CONTEXT_URL,
                              self.candidate.APR2016_CONTEXT_URL])
        self.assertEqual(len(registered_urls), 17)
        for registered_url in registered_urls:
            registered = self.candidate._registered_v14_replacement_spec(registered_url)
            self.assertIsNotNone(registered)
            for key in ("document_id", "day", "pages", "bytes", "raw_rows", "typed_rows",
                        "unresolved_rows", "title", "filename", "metadata", "source_url",
                        "old_vector_sha256"):
                self.assertIn(key, registered, (registered_url, key))
            self.assertRegex(registered["old_vector_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(registered["source_url"],
                             self.candidate.AUG2012_ALIAS_SOURCE_URL if registered_url == self.candidate.AUG2012_ALIAS_ASSET_URL
                             else registered_url)
        for manifest_case in MANIFEST["cases"]:
            registered_hash = self.candidate.RETAINED_2013_OLD_VECTOR_SHA256[manifest_case["url"]]
            self.assertEqual(
                self.candidate._retained_vector_sha256(full_sql_v14_rows(manifest_case)),
                registered_hash,
                f"registered old full-vector pin differs for {manifest_case['month']}",
            )
            self.candidate._assert_2013_registered_old_witness(
                self.conn, manifest_case["url"], self.candidate.RETAINED_2013_CONTEXTS[manifest_case["url"]]
            )
        # The registered 2012 witnesses share the same strict full-vector
        # validator; verify its embedded pins against the independent SQL exports.
        nov_dec = HERE / "testdata" / "input_pdf_v17_nov_dec_private"
        for day, expected in (("2012-11-30", "c655ba0caf0ccd8b8feb1b7ff4d77f805cbbc55d44afbcb340eb83ad1c5706e9"),
                              ("2012-12-31", "cfabc31d2a30c6108b37c218377ce6fd00a5b3d0cd9939bc7c9bbed627417bdc")):
            export = json.loads(gzip.decompress(
                (nov_dec / f"{day}_V14_FULL_VECTOR_FIRST_C.json.gz").read_bytes()))
            exported_rows = [(
                row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
                row["product_name"], row["market_name"], row["unit"], Decimal(row["price"]),
                Decimal(row["change_percent"]) if row["change_percent"] is not None else None,
                row["details"],
            ) for row in export["rows"]]
            registered_url = next(url for url, spec in self.candidate.RETAINED_2012_CONTEXTS.items()
                                  if spec["day"] == day)
            self.assertEqual(self.candidate._retained_vector_sha256(exported_rows), expected)
            self.assertEqual(self.candidate.RETAINED_2012_CONTEXTS[registered_url]["old_vector_sha256"], expected)
        def seed_and_validate_old_witness(spec, source, body, rows):
            self.assertEqual(hashlib.sha256(body).hexdigest(), spec["document_id"])
            self.assertEqual(len(rows), spec["raw_rows"])
            with self.conn.transaction():
                self.conn.execute("""INSERT INTO source_document
                    (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (source["id"],source["title"],source["publisher"],source["source_url"],
                     source["media_type"],source["kind"],date.fromisoformat(spec["day"]),
                     source["page_count"],body,Jsonb(source["metadata"])))
                with self.conn.cursor() as cursor:
                    cursor.executemany("""INSERT INTO historical_price
                        (document_id,source_locator,series,observed_on,product_name,market_name,unit,
                         price,change_percent,details)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [(source["id"],*row[:-1],Jsonb(row[-1])) for row in rows])
                self.conn.execute("""INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                    VALUES(%s,%s,'inputs-pdf:published',%s)""",
                    (source["id"],self.candidate.OLD_VERSION,spec["typed_rows"]))
            self.candidate._assert_registered_v14_source_witness(self.conn, spec["source_url"], spec)
            for altered in ("old-price", "old-details", "source-url"):
                with self.subTest(negative=f"registered-v14-{spec['day']}-{altered}"):
                    with self.assertRaises(ValueError):
                        self.candidate._assert_registered_v14_source_witness(
                            AlteredReadOnlySource(self.conn, spec["document_id"], altered),
                            spec["source_url"], spec,
                        )
        nov_dec_meta = json.loads((nov_dec / "METADATA_ONLY_FIRST_B.json").read_text())
        for old_case in nov_dec_meta["cases"]:
            source, bodyday = old_case["source"], old_case["asset"]["observed_on"]
            old_spec = self.candidate._registered_v14_replacement_spec(old_case["asset"]["url"])
            export = json.loads(gzip.decompress(
                (nov_dec / f"{bodyday}_V14_FULL_VECTOR_FIRST_C.json.gz").read_bytes()))
            rows = [(
                row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
                row["product_name"], row["market_name"], row["unit"], Decimal(row["price"]),
                Decimal(row["change_percent"]) if row["change_percent"] is not None else None,
                row["details"],
            ) for row in export["rows"]]
            seed_and_validate_old_witness(old_spec, source,
                (nov_dec / f"{bodyday}_original.pdf").read_bytes(), rows)
        august_export = json.loads((HERE / "testdata" / "AUG2012_PRIOR_RAW_FIRST_B.json").read_text())
        august_rows = [(
            row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
            row["product_name"], row["market_name"], row["unit"], Decimal(row["price"]),
            Decimal(row["change_percent"]) if row["change_percent"] is not None else None,
            row["details"],
        ) for row in august_export["rows"]]
        august_spec = self.candidate._registered_v14_replacement_spec(
            self.candidate.AUG2012_ALIAS_ASSET_URL)
        self.assertEqual(self.candidate._retained_vector_sha256(august_rows), august_spec["old_vector_sha256"])
        august_source = {"id": august_spec["document_id"], "title": august_spec["title"],
            "publisher": "DANE", "source_url": august_spec["source_url"],
            "media_type": "application/pdf", "kind": "original", "page_count": august_spec["pages"],
            "metadata": august_spec["metadata"]}
        seed_and_validate_old_witness(august_spec, august_source,
            (HERE / "testdata" / "AUG2012_ALIAS_ORIGINAL.body").read_bytes(), august_rows)
        case = next(item for item in MANIFEST["cases"] if item["month"] == "octubre")
        did, url = case["document_id"], case["url"]
        day = date.fromisoformat(case["observed_on"])
        original = (HERE / "testdata" / "octubre2013_original.pdf").read_bytes()
        old_rows = self.rows_by_month["octubre"]
        expected_v17 = expected_v17_rows(case, old_rows)
        initial_source = self.source_state(did)
        old_before = {
            "source": {key:value for key,value in initial_source.items()
                       if key in ("source_xmin","body_sha256","metadata","source_url","reference_period","page_count")},
            "v14_checkpoint": self.conn.execute(
                """SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s
                   AND processor_version='inputs-pdf-v14' AND step='inputs-pdf:published'""", (did,)
            ).fetchone(),
            "v14_xmins": self.conn.execute(
                """SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator))
                   FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14'""",
                (did,),
            ).fetchone()[0],
        }
        self.assertEqual(old_before["source"]["body_sha256"], did)
        self.assertEqual(initial_source["rows"][0], 0)
        spec = self.candidate.RETAINED_2013_CONTEXTS[url]
        writer = PdfWriter()
        source_reader = PdfReader(io.BytesIO(original))
        for page in source_reader.pages:
            writer.add_page(page)
        writer.add_blank_page(width=612, height=792)
        page_buffer = io.BytesIO()
        writer.write(page_buffer)
        extra_page_body = page_buffer.getvalue()
        extra_page_did = hashlib.sha256(extra_page_body).hexdigest()
        extra_page_count = len(PdfReader(io.BytesIO(extra_page_body)).pages)
        self.assertEqual(extra_page_count, case["page_count"] + 1)
        class _ExpectedFixtureRollback(Exception):
            pass
        with self.assertRaises(_ExpectedFixtureRollback):
            with self.conn.transaction():
                filename = url.rsplit("/",1)[-1]
                self.conn.execute("""INSERT INTO source_document
                    (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
                    VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s,%s)""",
                    (extra_page_did,"DANE - "+filename,url,day,extra_page_count,extra_page_body,
                     Jsonb({"ingestion_kind":"inputs-pdf","retention":"permanent","original_filename":filename})))
                self.conn.execute("""UPDATE ingestion_asset SET document_id=%s,status='pending',
                    processor_version=%s,records=0,error=NULL WHERE url=%s""",
                    (extra_page_did,self.candidate.VERSION,url))
                self.assertEqual(self.candidate._registered_replacement_old_did(self.conn,extra_page_did),did)
                with self.subTest(negative="registered-replacement-wrong-stored-page-count"):
                    with self.assertRaises(ValueError):
                        self.candidate._registered_replacement_old_did(
                            AlteredReadOnlySource(self.conn,extra_page_did,"page-count"),extra_page_did)
                raise _ExpectedFixtureRollback()
        self.assertEqual(self.conn.execute("SELECT document_id FROM ingestion_asset WHERE url=%s",(url,)).fetchone()[0],did)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM source_document WHERE id=%s",(extra_page_did,)).fetchone())
        for altered in ("old-price", "old-details", "source-url"):
            with self.subTest(negative=f"registered-old-{altered}"):
                with self.assertRaises(ValueError):
                    self.candidate._assert_2013_registered_old_witness(
                        AlteredReadOnlySource(self.conn, did, altered), url, spec
                    )
        b_body = original + b"\n% source revision B: valid trailing PDF comment\n"
        c_body = original + b"\n% source revision C: second valid trailing PDF comment\n"
        self.assertNotEqual(hashlib.sha256(b_body).hexdigest(), hashlib.sha256(c_body).hexdigest())
        for body in (b_body, c_body):
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                self.assertEqual(len(pdf.pages), case["page_count"])

        def archive_fixture(db, archive_url, data, archive_kind, archive_day):
            self.assertEqual((archive_url, archive_kind, archive_day), (url, "inputs-pdf", day))
            digest = hashlib.sha256(data).hexdigest()
            filename = url.rsplit("/", 1)[-1]
            page_count = len(PdfReader(io.BytesIO(data)).pages)
            db.execute(
                """INSERT INTO source_document
                   (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
                   VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s,%s)
                   ON CONFLICT(id) DO NOTHING""",
                (digest, "DANE - " + filename, url, day.isoformat(), page_count, data,
                 Jsonb({"ingestion_kind":"inputs-pdf","retention":"permanent","original_filename":filename})),
            )
            return digest

        # First bring the exact old retained source through its reviewed v17
        # migration so the next fetch is an ordinary mutable-URL refresh.
        with candidate_module(self.candidate):
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("retained old replay must not fetch")) as fetch, \
                     patch.object(self.worker,"archive",side_effect=archive_fixture), \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider forbidden")):
                    self.assertEqual(self.worker.process_asset(self.conn,url,"inputs-pdf",day),case["raw_rows"])
                    fetch.assert_not_called()
            finally:
                self.conn.execute("RESET ROLE")

            old_after_migration = self.source_state(did)
            old_before["v17_rows"] = old_after_migration["rows"]
            old_before["v17_checkpoint"] = old_after_migration["checkpoint"]
            # Capture the complete 13-field public projection after the
            # v14-to-v17 migration. For these content-only replacements, the
            # exact business values and original publication provenance should
            # remain the same even though successful reprojection may assign
            # new physical xmins.
            expected_public = self.expected_published_vector(expected_v17, did)
            self.assertEqual(old_after_migration["published"], expected_public)
            public_day_before = self.published_day_vector(day)
            public_day_xmins_before = self.published_day_xmins(day)
            self.assertEqual(public_day_before, expected_public)

            # A genuine source refresh changes the content hash and follows
            # the normal archive/parse path. Simulate an interruption after
            # parsing to prove its empty pending cohort can resume safely.
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(self.worker,"fetch_asset",return_value=b_body) as fetch, \
                     patch.object(self.worker,"archive",side_effect=archive_fixture) as archive, \
                     patch.object(self.worker,"project",side_effect=RuntimeError("simulated interruption")), \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider forbidden")):
                    with self.assertRaisesRegex(RuntimeError,"simulated interruption"):
                        self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                    fetch.assert_called_once_with(self.conn,url,force=False)
                    archive.assert_called_once()
            finally:
                self.conn.execute("RESET ROLE")
            b_did = hashlib.sha256(b_body).hexdigest()
            self.assertNotEqual(b_did,did)
            pending = self.conn.execute(
                "SELECT status,processor_version,document_id FROM ingestion_asset WHERE url=%s",(url,)
            ).fetchone()
            self.assertEqual(pending,("pending",self.candidate.VERSION,b_did))
            self.assertEqual(self.published_day_vector(day), public_day_before)
            self.assertEqual(self.published_day_xmins(day), public_day_xmins_before)
            self.assertIsNone(self.candidate.retained_v14_input_pdf(
                self.conn,url,"inputs-pdf",day,self.candidate.VERSION))
            self.conn.execute("UPDATE ingestion_asset SET status='failed',error='simulated retry state' WHERE url=%s",(url,))
            self.assertIsNone(self.candidate.retained_v14_input_pdf(
                self.conn,url,"inputs-pdf",day,self.candidate.VERSION))

            # The failed new revision retries from the normal fetch and then
            # the next exact-body refresh is a zero-row no-op.
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(self.worker,"fetch_asset",return_value=b_body) as fetch, \
                     patch.object(self.worker,"archive",side_effect=archive_fixture), \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider forbidden")):
                    self.assertEqual(self.worker.process_asset(self.conn,url,"inputs-pdf",day),case["raw_rows"])
                    fetch.assert_called_once_with(self.conn,url,force=False)
            finally:
                self.conn.execute("RESET ROLE")
            b_state = self.source_state(b_did)
            self.assertEqual(b_state["rows"][0],case["new_raw_rows"])
            self.assertEqual(b_state["checkpoint"][0],case["new_typed_rows"])
            self.assertEqual(canonical_business_sha(self.conn.execute(
                f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",
                (b_did,self.candidate.VERSION),
            ).fetchall()),case["expected_new_v17_vector_sha256"])
            # A content-only revision has identical business values, so the
            # maintained upsert deliberately keeps the earlier source
            # attribution. The new historical cohort is still independently
            # checked above; the public day projection remains exact.
            self.assertEqual(self.published_day_vector(day), public_day_before)
            self.assertEqual(b_state["published"], [])
            with self.subTest(negative="replacement-source-metadata"):
                with self.assertRaises(ValueError):
                    self.candidate.retained_v14_input_pdf(
                        AlteredReadOnlySource(self.conn,b_did,"metadata"),url,"inputs-pdf",day,self.candidate.VERSION
                    )
            with self.subTest(negative="replacement-pointer"):
                wrong_did = next(item["document_id"] for item in MANIFEST["cases"]
                                 if item["month"] == "febrero")
                with self.assertRaises(ValueError):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s",(wrong_did,url))
                        self.candidate.retained_v14_input_pdf(self.conn,url,"inputs-pdf",day,self.candidate.VERSION)
            with self.subTest(negative="replacement-record-count"):
                with self.assertRaises(ValueError):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET records=records+1 WHERE url=%s",(url,))
                        self.candidate.retained_v14_input_pdf(self.conn,url,"inputs-pdf",day,self.candidate.VERSION)
            with self.subTest(negative="replacement-v14-cohort"):
                with self.assertRaises(ValueError):
                    with self.conn.transaction():
                        self.conn.execute(
                            """INSERT INTO historical_price(document_id,source_locator,series,observed_on,
                               product_name,market_name,unit,price,change_percent,details)
                               SELECT %s,source_locator,series,observed_on,product_name,market_name,unit,
                                      price,change_percent,details
                               FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s LIMIT 1""",
                            (b_did,did,self.candidate.OLD_VERSION),
                        )
                        self.candidate.retained_v14_input_pdf(self.conn,url,"inputs-pdf",day,self.candidate.VERSION)
            # The v17 publisher may exclude only conflict groups already
            # retained under the exact registered old DID. Exercise its full
            # group comparison with a fresh transaction-local stage each time.
            def stage_and_check(mutation=None, *, altered_db=None, registry_spec=None):
                with self.conn.transaction():
                    self.inputs.prepare_input_stage(self.conn,b_did,source_url=url)
                    target = self.conn.execute(
                        """SELECT s.source_locator FROM input_stage s WHERE EXISTS (
                           SELECT 1 FROM input_stage x WHERE
                           (x.id,x.department,x.municipality,x.observed_on)=
                           (s.id,s.department,s.municipality,s.observed_on)
                           GROUP BY x.id,x.department,x.municipality,x.observed_on
                           HAVING min(x.price)<>max(x.price)) LIMIT 1"""
                    ).fetchone()
                    self.assertIsNotNone(target,"October fixture must contain a retained conflict group")
                    if mutation:
                        mutation(self.conn,target[0])
                    with patch.dict(self.candidate.RETAINED_2013_CONTEXTS,
                                    {url:registry_spec} if registry_spec is not None else {}):
                        self.candidate.assert_v17_public_stage_safe(altered_db or self.conn,b_did)

            # The unmodified replacement passes the registered old-source
            # comparison before testing fail-closed mutations.
            stage_and_check()
            with self.subTest(negative="conflict-price-change"):
                with self.assertRaises(ValueError):
                    stage_and_check(lambda db,loc: db.execute(
                        "UPDATE input_stage SET price=price+1 WHERE source_locator=%s",(loc,)))
            with self.subTest(negative="conflict-member-deletion"):
                with self.assertRaises(ValueError):
                    stage_and_check(lambda db,loc: db.execute(
                        "DELETE FROM input_stage WHERE source_locator=%s",(loc,)))
            with self.subTest(negative="conflict-member-addition"):
                def add_member(db,loc):
                    db.execute(
                        """INSERT INTO input_stage(id,department,municipality,observed_on,name,category,
                           presentation,price,document_id,source_locator,brand,registration,product_line)
                           SELECT id,department,municipality,observed_on,name,category,presentation,price,
                                  document_id,source_locator||'; unregistered-added-member',brand,registration,product_line
                           FROM input_stage WHERE source_locator=%s""",(loc,))
                with self.assertRaises(ValueError):
                    stage_and_check(add_member)
            with self.subTest(negative="wrong-replacement-source-binding"):
                with self.assertRaises(ValueError):
                    stage_and_check(altered_db=AlteredReadOnlySource(self.conn,b_did,"source-url"))
            with self.subTest(negative="wrong-registered-old-witness"):
                other = next(item for item in MANIFEST["cases"] if item["month"] == "febrero")
                wrong_spec = self.candidate.RETAINED_2013_CONTEXTS[other["url"]]
                with self.assertRaises(ValueError):
                    stage_and_check(registry_spec=wrong_spec)
            b_before_noop = self.source_state(b_did)
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(self.worker,"fetch_asset",return_value=b_body) as fetch, \
                     patch.object(self.worker,"archive",side_effect=archive_fixture), \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider forbidden")):
                    self.assertEqual(self.worker.process_asset(self.conn,url,"inputs-pdf",day),0)
                    fetch.assert_called_once_with(self.conn,url,force=False)
            finally:
                self.conn.execute("RESET ROLE")
            self.assertEqual(self.source_state(b_did),b_before_noop)

            # A second distinct valid body follows the same ordinary refresh
            # route; earlier originals and row/checkpoint xmins remain intact.
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(self.worker,"fetch_asset",return_value=c_body) as fetch, \
                     patch.object(self.worker,"archive",side_effect=archive_fixture) as archive, \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider forbidden")):
                    self.assertEqual(self.worker.process_asset(self.conn,url,"inputs-pdf",day),case["raw_rows"])
                    fetch.assert_called_once_with(self.conn,url,force=False)
                    archive.assert_called_once()
            finally:
                self.conn.execute("RESET ROLE")
            c_did = hashlib.sha256(c_body).hexdigest()
            c_state = self.source_state(c_did)
            self.assertEqual(c_state["rows"][0],case["new_raw_rows"])
            self.assertEqual(c_state["checkpoint"][0],case["new_typed_rows"])
            self.assertEqual(self.published_day_vector(day), public_day_before)
            self.assertEqual(c_state["published"], [])
            self.assertEqual(self.source_state(b_did),b_before_noop)

        old_after = {
            "source": {key:value for key,value in self.source_state(did).items()
                       if key in ("source_xmin","body_sha256","metadata","source_url","reference_period","page_count")},
            "v14_checkpoint": self.conn.execute(
                """SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s
                   AND processor_version='inputs-pdf-v14' AND step='inputs-pdf:published'""", (did,)
            ).fetchone(),
            "v14_xmins": self.conn.execute(
                """SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator))
                   FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14'""",
                (did,),
            ).fetchone()[0],
            "v17_rows": self.source_state(did)["rows"],
            "v17_checkpoint": self.source_state(did)["checkpoint"],
        }
        self.assertEqual(old_after,old_before)

    def test_a_exact_source_guards_are_fail_closed(self):
        source_price_forms = (41500, 41500.0, "41500.0", Decimal("41500.000"))
        self.assertEqual({canonical_number(value) for value in source_price_forms}, {"41500"})
        self.assertNotEqual(self.canonical_dicts([{"price": True}]), self.canonical_dicts([{"price": 1}]))
        with candidate_module(self.candidate):
            for case in MANIFEST["cases"]:
                day = date.fromisoformat(case["observed_on"])
                body = (HERE / "testdata" / f"{case['month']}2013_original.pdf").read_bytes()
                self.assertEqual(self.candidate.retained_v14_input_pdf(
                    self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                with self.subTest(month=case["month"],negative="date"):
                    with self.assertRaises(ValueError):
                        self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day+timedelta(days=1),self.candidate.VERSION)
                with self.subTest(month=case["month"],negative="unknown-url"):
                    self.assertIsNone(self.candidate.retained_v14_input_pdf(
                        self.conn,case["url"]+"?unreviewed=1","inputs-pdf",day,self.candidate.VERSION))
                with self.subTest(month=case["month"],negative="asset-version"):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET processor_version='inputs-pdf-v16' WHERE url=%s",(case["url"],))
                        with self.assertRaises(ValueError):
                            self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                        self.conn.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                                          (case["expected_old_asset"]["processor_version"],case["url"]))
                with self.subTest(month=case["month"],negative="noncanonical-lifecycle"):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET status='complete',processor_version='inputs-pdf-v17',error=NULL WHERE url=%s",(case["url"],))
                        with self.assertRaises(ValueError):
                            self.candidate.assert_retained_v14_binding_locked(
                                self.conn,case["url"],"inputs-pdf",day,case["document_id"],case["raw_rows"]
                            )
                        self.conn.execute("UPDATE ingestion_asset SET status=%s,processor_version=%s,records=%s,error=%s WHERE url=%s",
                                          (case["expected_old_asset"]["status"],case["expected_old_asset"]["processor_version"],case["raw_rows"],case["expected_old_asset"]["error"],case["url"]))
                with self.subTest(month=case["month"],negative="raw-count"):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET records=records+1 WHERE url=%s",(case["url"],))
                        with self.assertRaises(ValueError):
                            self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                        self.conn.execute("UPDATE ingestion_asset SET records=%s WHERE url=%s",(case["raw_rows"],case["url"]))
                with self.subTest(month=case["month"],negative="retry-error"):
                    with self.conn.transaction():
                        self.conn.execute("UPDATE ingestion_asset SET error='unrecognized failure' WHERE url=%s",(case["url"],))
                        with self.assertRaises(ValueError):
                            self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                        self.conn.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s",
                                          (case["expected_old_asset"]["error"],case["url"]))
                for corruption in ("body", "metadata"):
                    with self.subTest(month=case["month"],negative=f"source-{corruption}"):
                        with self.assertRaises(ValueError):
                            self.candidate.retained_v14_input_pdf(
                                AlteredReadOnlySource(self.conn, case["document_id"], corruption),
                                case["url"], "inputs-pdf", day, self.candidate.VERSION,
                            )
            september = next(case for case in MANIFEST["cases"] if case["month"] == "septiembre")
            old_rows = self.rows_by_month[september["month"]]
            new_rows = expected_v17_rows(september, old_rows)
            bad = list(new_rows[0])
            bad[6] = Decimal(str(bad[6])) + 1
            new_rows[0] = tuple(bad)
            with self.subTest(negative="changed-new-vector"):
                with self.assertRaises(ValueError):
                    self.candidate.assert_retained_v14_vectors(
                        self.conn, september["document_id"], old_rows, new_rows
                    )
            august = next(case for case in MANIFEST["cases"] if case["month"] == "agosto")
            with self.subTest(month="agosto", negative="unexpected-v17-checkpoint"):
                with self.conn.transaction():
                    self.conn.execute(
                        "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,'inputs-pdf:published',%s)",
                        (august["document_id"], self.candidate.VERSION, august["new_typed_rows"]),
                    )
                    with self.assertRaises(ValueError):
                        self.candidate.retained_v14_input_pdf(
                            self.conn, august["url"], "inputs-pdf",
                            date.fromisoformat(august["observed_on"]), self.candidate.VERSION,
                        )
                    self.conn.execute(
                        "DELETE FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",
                        (august["document_id"], self.candidate.VERSION),
                    )

    def test_b_worker_replays_eleven_full_vectors_without_external_access_or_old_row_changes(self):
        from pipelines.ingestion import ocr
        added_locator_count = 0
        with candidate_module(self.candidate):
            for case in MANIFEST["cases"]:
                phase("test_b",case["month"],"start")
                did, url = case["document_id"], case["url"]
                day = date.fromisoformat(case["observed_on"])
                body = (HERE / "testdata" / f"{case['month']}2013_original.pdf").read_bytes()
                old_rows = self.rows_by_month[case["month"]]
                expected_new = expected_v17_rows(case, old_rows)
                expected_raw = case["new_raw_rows"]
                expected_typed = case["new_typed_rows"]
                expected_unresolved = case["new_unresolved_rows"]
                expected_sha = case["expected_new_v17_vector_sha256"]
                def as_v17_locator(locator):
                    return re.sub(r"; inputs-pdf-v14$", "; inputs-pdf-v17", locator)
                old_typed_locators = {as_v17_locator(row[0]) for row in old_rows if row[1] == "dane-inputs-pdf"}
                new_typed_locators = {row[0] for row in expected_new if row[1] == "dane-inputs-pdf"}
                added_locators = new_typed_locators - old_typed_locators
                expected_added = set(case["expected_added_typed_locators"])
                self.assertEqual(len(added_locators), case["expected_added_typed_rows"])
                self.assertEqual(added_locators, expected_added)
                self.assertEqual(case["expected_added_typed_rows"], {"septiembre": 15, "noviembre": 1}.get(case["month"], 0))
                added_locator_count += len(added_locators)
                if case["month"] in {"junio", "septiembre", "octubre"}:
                    # Simulate an interrupted publication through the real
                    # worker after retained-source parsing, then resume via
                    # the worker from its actual pending lifecycle state.
                    phase("test_b_interruption",case["month"],"start")
                    interruption_before = {
                        "source_xmin":self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],
                        "old_checkpoint":self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.OLD_VERSION)).fetchone(),
                        "old_xmins":self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],
                        "published":self.published_vector(did),
                    }
                    self.conn.execute("SET ROLE agro_ingestor")
                    try:
                        with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network access forbidden")) as fetch, \
                             patch.object(self.worker,"archive",return_value=did) as archive, \
                             patch.object(self.worker,"project",side_effect=RuntimeError("simulated interrupted publication")), \
                             patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider access forbidden")) as transcribe:
                            with self.assertRaisesRegex(RuntimeError,"simulated interrupted publication"):
                                self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                            fetch.assert_not_called()
                            archive.assert_called_once_with(self.conn,url,body,"inputs-pdf",day)
                            transcribe.assert_not_called()
                    finally:
                        self.conn.execute("RESET ROLE")
                    expected_old_asset = case["expected_old_asset"]
                    pending = self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone()
                    self.assertEqual(pending,("pending",expected_old_asset["processor_version"],case["raw_rows"],expected_old_asset["error"]))
                    self.assertEqual(self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],0)
                    self.assertEqual(self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],interruption_before["source_xmin"])
                    self.assertEqual(self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.OLD_VERSION)).fetchone(),interruption_before["old_checkpoint"])
                    self.assertEqual(self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],interruption_before["old_xmins"])
                    self.assertEqual(self.published_vector(did),interruption_before["published"])
                    phase("test_b_interruption",case["month"],"pending-resume")
                self.conn.execute("SET ROLE agro_ingestor")
                try:
                    with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network access forbidden")) as fetch, \
                         patch.object(self.worker,"archive",return_value=did) as archive, \
                         patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider access forbidden")) as transcribe:
                        imported = self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                        fetch.assert_not_called()
                        archive.assert_called_once()
                        self.assertEqual(archive.call_args.args[1:],(url,body,"inputs-pdf",day))
                        transcribe.assert_not_called()
                    self.assertEqual(imported,expected_raw)
                    asset = self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone()
                    conflicts = self.expected_conflict_count(expected_new)
                    expected_error = f"Conflicting source keys retained but excluded from app: {conflicts}" if conflicts else None
                    self.assertEqual(asset,("complete",self.candidate.VERSION,expected_raw,expected_error))
                    self.assertEqual(self.conn.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.VERSION)).fetchone()[0],expected_typed)
                    old_current=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchall()
                    self.assertEqual(len(old_current),case["raw_rows"])
                    self.assertEqual(canonical_business_sha(old_current),old_sql_vector_hash(case))
                    self.assertEqual(self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],expected_raw)
                    rows_new=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchall()
                    self.assertEqual(canonical_business_sha(rows_new),expected_sha)
                    self.assertEqual(sum(row[1]=="dane-inputs-pdf" for row in rows_new),expected_typed)
                    self.assertEqual(sum(row[1]=="dane-inputs-pdf-unresolved" for row in rows_new),expected_unresolved)
                    self.assertEqual(self.candidate.assert_retained_v14_vectors(
                        self.conn,did,old_rows,expected_new,complete=True),expected_raw)
                    self.assertEqual(self.candidate.assert_v17_existing_rows(self.conn,did,expected_new,complete=True),expected_raw)
                    self.assertIsNone(self.candidate.retained_v14_input_pdf(
                        self.conn,url,"inputs-pdf",day,self.candidate.VERSION))
                    current = self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0]
                    self.assertEqual(current,self.initial[did]["source_xmin"])
                    self.assertEqual(hashlib.sha256(self.conn.execute("SELECT content FROM source_document WHERE id=%s",(did,)).fetchone()[0]).hexdigest(),self.initial[did]["body_sha"])
                    self.assertEqual(self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.OLD_VERSION)).fetchone(),self.initial[did]["old_checkpoint"])
                    self.assertEqual(self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],self.initial[did]["old_xmins"])
                    after_vector = self.published_vector(did)
                    self.assertEqual(after_vector,self.expected_published_vector(expected_new,did))
                    published_locs = {row["source_locator"] for row in after_vector}
                    normalized_additions = {
                        loc[:-len("inputs-pdf-v17")] + "inputs-pdf-v14" for loc in added_locators
                    }
                    self.assertTrue(normalized_additions.issubset(published_locs),
                                    f"source-bound additions missing from publication: {case['month']}")
                    self.assertEqual(self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],self.initial[did]["source_xmin"])
                finally:
                    self.conn.execute("RESET ROLE")
                phase("test_b",case["month"],"end")
            self.assertEqual(added_locator_count, 16)

    def test_c_completed_same_body_normal_worker_refetch_is_idempotent(self):
        from pipelines.ingestion import ocr
        with candidate_module(self.candidate):
            for case in MANIFEST["cases"]:
                phase("test_c",case["month"],"start")
                did,url=case["document_id"],case["url"]
                day=date.fromisoformat(case["observed_on"])
                body=(HERE/"testdata"/f"{case['month']}2013_original.pdf").read_bytes()
                before={
                    "source_xmin":self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],
                    "source_body_sha":hashlib.sha256(self.conn.execute("SELECT content FROM source_document WHERE id=%s",(did,)).fetchone()[0]).hexdigest(),
                    "old_rows":self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],
                    "old_xmins":self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],
                    "new_rows":self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],
                    "new_xmins":self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],
                    "old_checkpoint":self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.OLD_VERSION)).fetchone(),
                    "new_checkpoint":self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.VERSION)).fetchone(),
                    "published":self.published_vector(did),
                }
                self.conn.execute("SET ROLE agro_ingestor")
                try:
                    with patch.object(self.worker,"fetch_asset",return_value=body) as fetch, \
                         patch.object(self.worker,"archive",return_value=did) as archive, \
                         patch.object(ocr,"transcribe",side_effect=AssertionError("OCR/provider access forbidden")) as transcribe:
                        imported=self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                        # A same-body completed PDF refetch takes the ordinary
                        # worker's validated no-op path and reports zero rows.
                        self.assertEqual(imported,0)
                        fetch.assert_called_once_with(self.conn,url,force=False)
                        archive.assert_called_once_with(self.conn,url,body,"inputs-pdf",day)
                        transcribe.assert_not_called()
                finally:
                    self.conn.execute("RESET ROLE")
                after={
                    "source_xmin":self.conn.execute("SELECT xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()[0],
                    "source_body_sha":hashlib.sha256(self.conn.execute("SELECT content FROM source_document WHERE id=%s",(did,)).fetchone()[0]).hexdigest(),
                    "old_rows":self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],
                    "old_xmins":self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.OLD_VERSION)).fetchone()[0],
                    "new_rows":self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],
                    "new_xmins":self.conn.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,self.candidate.VERSION)).fetchone()[0],
                    "old_checkpoint":self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.OLD_VERSION)).fetchone(),
                    "new_checkpoint":self.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.VERSION)).fetchone(),
                    "published":self.published_vector(did),
                }
                self.assertEqual(after,before)
                phase("test_c",case["month"],"end")


if __name__ == "__main__":
    unittest.main(verbosity=2)
