"""Owned-full-schema retention tests for DANE context PDFs."""
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
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from unittest.mock import patch

import pdfplumber
import psycopg
from pypdf import PdfReader, PdfWriter
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
REPO = next(parent for parent in HERE.parents if (parent / "pipelines/ingestion/schema.sql").is_file())
FIXTURES = HERE / "testdata/input_pdf_v17_generic_context"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
CONSOLIDATED_DID = "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"
CONSOLIDATED_SHA256 = "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"
CONSOLIDATED_XLSX = FIXTURES / MANIFEST["consolidated_source"]["path"]
CANDIDATE = Path(os.environ.get("AGRO_CONTEXT_CANDIDATE", str(HERE / "input_pdf_v17_replay.py")))
CANDIDATE_WORKER = Path(os.environ.get("AGRO_CONTEXT_WORKER", str(HERE / "worker.py")))
MODULE_KEY = "pipelines.ingestion.input_pdf_v17_replay"
WORKER_KEY = "pipelines.ingestion.worker"


class _RollbackProbe(Exception):
    pass


@contextmanager
def rollback_probe(conn):
    """Run deliberate bad-state probes without committing their mutations."""
    try:
        with conn.transaction():
            yield
            raise _RollbackProbe()
    except _RollbackProbe:
        pass


def load_candidate():
    spec = importlib.util.spec_from_file_location(MODULE_KEY, CANDIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_candidate_worker():
    spec = importlib.util.spec_from_file_location(WORKER_KEY, CANDIDATE_WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def candidate_module(candidate, candidate_worker):
    package = importlib.import_module("pipelines.ingestion")
    sys = __import__("sys")
    saved = {key: sys.modules.get(key) for key in (MODULE_KEY, WORKER_KEY)}
    saved_attr = {"input_pdf_v17_replay": getattr(package,"input_pdf_v17_replay",None),
                  "worker": getattr(package,"worker",None)}
    sys.modules[MODULE_KEY] = candidate
    sys.modules[WORKER_KEY] = candidate_worker
    package.input_pdf_v17_replay = candidate
    package.worker = candidate_worker
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key,None)
            else:
                sys.modules[key]=value
        for name,value in saved_attr.items():
            if value is None:
                if hasattr(package,name): delattr(package,name)
            else:
                setattr(package,name,value)


def fixture(case, label):
    prefix = case["fixture_prefix"]
    if label == "pdf":
        return FIXTURES / f"{prefix}original_FIRST_A.pdf"
    suffix = {
        "v14": "V14_FULL_VECTOR_FIRST_A.json.gz",
        "v17": "V17_NATIVE_VECTOR_FIRST_A.json.gz",
        "input": "input_municipal_price_FIRST_D.json.gz",
        "published": "published_input_municipal_price_FIRST_D.json.gz",
        "revision": "input_revision_FIRST_D.json.gz",
        "history": "exact_historical_witnesses_FIRST_D.json.gz",
        "checkpoints": "checkpoints_FIRST_D.json.gz",
        "metadata": "source_document_metadata_FIRST_D.json.gz",
    }[label]
    return FIXTURES / f"{prefix}{suffix}"


def read_gzip_json(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def primitive(value):
    if isinstance(value, Decimal):
        value = Decimal(str(value))
        return "0" if value == 0 else format(value.normalize(), "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def row_hash(rows):
    values=[]
    for row in rows:
        if isinstance(row, dict):
            values.append(row)
        else:
            values.append({})
    payload=json.dumps(sorted((primitive(r) for r in values),
        key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)),
        sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return hashlib.sha256(payload).hexdigest()


def business_vector_sha(rows):
    values=[]
    for row in rows:
        values.append([row[0],row[1],row[2].isoformat() if hasattr(row[2],"isoformat") else row[2],
                       row[3],row[4],row[5],primitive(Decimal(str(row[6]))),
                       primitive(Decimal(str(row[7]))) if row[7] is not None else None,row[8]])
    values.sort(key=lambda r:r[0])
    payload=json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(payload).hexdigest()


def canonical_capture_row(raw):
    """Normalize only typed SQL `price` and `retrieved_at` fields."""
    row=dict(raw); row.pop("xmin",None); row.pop("_xmin",None)
    if row.get("price") is not None:
        row["price"]=primitive(Decimal(str(row["price"])))
    if row.get("retrieved_at") is not None:
        value=row["retrieved_at"]
        parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
        if not isinstance(parsed,datetime) or parsed.tzinfo is None:
            raise AssertionError("retrieved_at fixture/SQL value is not an aware timestamp")
        row["retrieved_at"]=parsed.astimezone(timezone.utc).isoformat()
    return {key:primitive(value) for key,value in row.items()}


def capture_rows_hash(rows):
    cleaned=[canonical_capture_row(row) for row in rows]
    return row_hash(cleaned)


def assert_capture_rows_equal(label, actual, expected):
    actual_rows=[canonical_capture_row(row) for row in actual]
    expected_rows=[canonical_capture_row(row) for row in expected]
    if row_hash(actual_rows)==row_hash(expected_rows):
        return
    key_fields=("id","department","municipality","observed_on")
    def key(row):
        return tuple(row.get(name) for name in key_fields)
    actual_by_key={key(row):row for row in actual_rows}
    expected_by_key={key(row):row for row in expected_rows}
    for business_key in sorted(set(actual_by_key)|set(expected_by_key),key=repr):
        left=actual_by_key.get(business_key); right=expected_by_key.get(business_key)
        if left==right:
            continue
        if left is None or right is None:
            raise AssertionError(f"{label} mismatch key={business_key!r} field=<row> expected={str(right)[:180]} actual={str(left)[:180]}")
        for field in sorted(set(left)|set(right)):
            if left.get(field)!=right.get(field):
                raise AssertionError(f"{label} mismatch key={business_key!r} field={field} expected={str(right.get(field))[:180]} actual={str(left.get(field))[:180]}")
    raise AssertionError(f"{label} row multiplicity differs: expected={len(expected_rows)} actual={len(actual_rows)}")


def snapshot_diff(actual, expected, limit=12):
    """Order-insensitive full-row diff; unlike fixture normalization, retains xmin."""
    actual_rows=[primitive(dict(row)) for row in actual]
    expected_rows=[primitive(dict(row)) for row in expected]
    keys=("id","department","municipality","observed_on")
    def business_key(row): return tuple(row.get(name) for name in keys)
    def grouped(rows):
        result={}
        for row in rows: result.setdefault(business_key(row),[]).append(row)
        for values in result.values(): values.sort(key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))
        return result
    left,right=grouped(actual_rows),grouped(expected_rows)
    field_counts={}; examples=[]; changed_keys=0
    for key in sorted(set(left)|set(right),key=repr):
        a,b=left.get(key,[]),right.get(key,[])
        if a==b: continue
        changed_keys+=1
        if not a or not b:
            field_counts["<row>"]=field_counts.get("<row>",0)+max(len(a),len(b))
            if len(examples)<limit: examples.append({"key":key,"expected":b[:1],"actual":a[:1],"difference":"missing/extra row"})
            continue
        for idx in range(max(len(a),len(b))):
            av=a[idx] if idx<len(a) else None; bv=b[idx] if idx<len(b) else None
            if av is None or bv is None:
                field_counts["<multiplicity>"]=field_counts.get("<multiplicity>",0)+1
                if len(examples)<limit: examples.append({"key":key,"expected":bv,"actual":av,"difference":"duplicate count"})
                continue
            for field in sorted(set(av)|set(bv)):
                if av.get(field)!=bv.get(field):
                    field_counts[field]=field_counts.get(field,0)+1
                    if len(examples)<limit: examples.append({"key":key,"field":field,"expected":str(bv.get(field))[:160],"actual":str(av.get(field))[:160]})
    return {"changed_keys":changed_keys,"field_change_counts":field_counts,"examples":examples,
            "actual_rows":len(actual_rows),"expected_rows":len(expected_rows),
            "actual_hash":row_hash(actual_rows),"expected_hash":row_hash(expected_rows)}


def assert_snapshot_rows_equal(label, actual, expected):
    diff=snapshot_diff(actual,expected)
    if diff["actual_hash"]!=diff["expected_hash"]:
        raise AssertionError(label+" full-row snapshot difference: "+json.dumps(diff,sort_keys=True,ensure_ascii=False))


def keyed_snapshot(rows):
    result={}
    for raw in rows:
        row=primitive(dict(raw)); key=tuple(row.get(name) for name in ("id","department","municipality","observed_on"))
        result.setdefault(key,[]).append(row)
    for values in result.values(): values.sort(key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))
    return result


def assert_v17_locator_repair(label, before, after, new_locators, did, expected_additions=()):
    old,new=keyed_snapshot(before),keyed_snapshot(after)
    expected_by_key={}
    for row in expected_additions:
        key=tuple(primitive(row.get(name)) for name in ("id","department","municipality","observed_on"))
        if key in expected_by_key:
            raise AssertionError(f"{label} expected additions contain duplicate identity {key!r}")
        expected_by_key[key]=row
    added_keys=set(new)-set(old)
    if added_keys != set(expected_by_key):
        diff=snapshot_diff(after,before)
        raise AssertionError(label+" business-key additions differ: "+json.dumps(diff,sort_keys=True,ensure_ascii=False))
    if set(old)-set(new):
        diff=snapshot_diff(after,before)
        raise AssertionError(label+" existing business keys disappeared: "+json.dumps(diff,sort_keys=True,ensure_ascii=False))
    for key, expected in expected_by_key.items():
        actual_rows=new[key]
        if len(actual_rows)!=1:
            raise AssertionError(f"{label} source-backed addition multiplicity changed {key!r}")
        actual=actual_rows[0]
        for field,value in expected.items():
            if primitive(actual.get(field))!=primitive(value):
                raise AssertionError(f"{label} source-backed addition differs key={key!r} field={field} expected={value!r} actual={actual.get(field)!r}")
        if "_xmin" in actual and not actual["_xmin"]:
            raise AssertionError(f"{label} source-backed addition lacks xmin {key!r}")
    changed=0; examples=[]
    for key in sorted(old,key=repr):
        left,right=old[key],new[key]
        if len(left)!=len(right):
            raise AssertionError(f"{label} key multiplicity changed {key!r}: {len(left)} to {len(right)}")
        for oldrow,newrow in zip(left,right):
            fields=set(oldrow)|set(newrow)
            for field in sorted(fields-{"source_locator","_xmin"}):
                if oldrow.get(field)!=newrow.get(field):
                    raise AssertionError(f"{label} disallowed field change key={key!r} field={field} old={str(oldrow.get(field))[:160]} new={str(newrow.get(field))[:160]}")
            oldloc,newloc=oldrow.get("source_locator"),newrow.get("source_locator")
            if oldloc==newloc:
                if "_xmin" in oldrow and oldrow.get("_xmin")!=newrow.get("_xmin"):
                    raise AssertionError(f"{label} xmin changed without locator repair key={key!r} locator={oldloc!r}")
                continue
            if not (oldrow.get("document_id")==did
                    and isinstance(oldloc,str) and oldloc.endswith("; inputs-pdf-v14")
                    and isinstance(newloc,str) and newloc==oldloc[:-len("inputs-pdf-v14")]+"inputs-pdf-v17"
                    and newloc in new_locators):
                raise AssertionError(f"{label} unverified locator change key={key!r} old={oldloc!r} new={newloc!r}")
            if "_xmin" in oldrow and oldrow.get("_xmin")==newrow.get("_xmin"):
                raise AssertionError(f"{label} locator changed without tuple xmin change key={key!r}")
            changed+=1
            if len(examples)<5: examples.append({"key":key,"old_locator":oldloc,"new_locator":newloc})
    return {"rows":sum(map(len,old.values())),"locator_repairs":changed,
            "source_backed_additions":len(added_keys),"examples":examples}


def _aware_dt(value):
    result=datetime.fromisoformat(value) if isinstance(value,str) else value
    if not isinstance(result,datetime) or result.tzinfo is None:
        raise AssertionError("watermark value is not an aware timestamp")
    return result.astimezone(timezone.utc)


def assert_watermarks_after_replacement(label, before, after, new_rows, winner_bindings, source_retrieved_at, inputs_module):
    """Check the exact revision-key set/time/xmin effects of project_pdf_inputs."""
    old,new=keyed_snapshot(before),keyed_snapshot(after)
    stage={}
    for row in new_rows:
        locator,series,day,product,market,unit,price,change,details=row
        ident=inputs_module.identity(product,details)
        municipality=details.get("municipality","") if series!="dane-inputs" else ""
        key=(ident,details.get("department") or market,municipality,day.isoformat() if hasattr(day,"isoformat") else str(day))
        stage.setdefault(key,[]).append({
            "series":series,"price":Decimal(str(price)),"name":product,
            "category":details.get("category") or inputs_module.CATEGORIES[details["sheet"]],
            "presentation":unit,"brand":details.get("brand",""),
            "registration":details.get("ica",""),"product_line":details.get("line","")})
    winners=keyed_snapshot(winner_bindings)
    source_time=_aware_dt(source_retrieved_at)
    eligible={}; preserve={}
    for key,rows in stage.items():
        unambiguous=bool(rows) and min(row["price"] for row in rows)==max(row["price"] for row in rows)
        excel=False
        prior_rows=winners.get(key,[])
        if unambiguous and len(prior_rows)==1:
            current=prior_rows[0]; target=rows[0]
            same_identity=all(current.get(field)==target[field] for field in
                              ("name","category","presentation","brand","registration","product_line"))
            prior_series=current.get("prior_series")
            integer_price=target["price"]==target["price"].to_integral_value()
            current_price=Decimal(str(current["price"]))
            excel=(same_identity and prior_series in ("dane-inputs","dane-inputs-municipal")
                   and integer_price and target["price"]==current_price.quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        eligible[key]=unambiguous and not excel
        preserve[key]=excel

    expected_keys=set(old)
    for key in stage:
        if eligible[key]: expected_keys.add(key)
    if set(new)!=expected_keys:
        raise AssertionError(f"{label} revision key set differs: "
            +json.dumps(snapshot_diff(after,before),sort_keys=True,ensure_ascii=False))
    advanced=held=0; examples=[]
    for key in sorted(expected_keys,key=repr):
        oldgroup=old.get(key,[]); newgroup=new.get(key,[])
        if len(newgroup)!=1 or len(oldgroup)>1:
            raise AssertionError(f"{label} duplicate/missing revision key {key!r}")
        oldrow=oldgroup[0] if oldgroup else None; newrow=newgroup[0]
        should_advance=eligible.get(key,False)
        expected_time=(max(_aware_dt(oldrow["retrieved_at"]),source_time) if oldrow else source_time) if should_advance else _aware_dt(oldrow["retrieved_at"])
        actual_time=_aware_dt(newrow["retrieved_at"])
        if oldrow is not None:
            for field in sorted((set(oldrow)|set(newrow))-{"retrieved_at","_xmin"}):
                if oldrow.get(field)!=newrow.get(field):
                    raise AssertionError(f"{label} non-time watermark field changed key={key!r} field={field} old={str(oldrow.get(field))[:120]} new={str(newrow.get(field))[:120]}")
        if actual_time!=expected_time:
            raise AssertionError(f"{label} watermark differs from finite expected value key={key!r} expected={expected_time.isoformat()} actual={actual_time.isoformat()} eligible={should_advance} preserve_excel={preserve.get(key,False)}")
        if oldrow is None or actual_time>_aware_dt(oldrow["retrieved_at"]):
            if oldrow is not None and newrow.get("_xmin")==oldrow.get("_xmin"):
                raise AssertionError(f"{label} advanced watermark xmin did not change key={key!r}")
            advanced+=1
            if len(examples)<5: examples.append({"key":key,"old":_aware_dt(oldrow["retrieved_at"]).isoformat() if oldrow else None,"new":actual_time.isoformat()})
        else:
            if oldrow is not None and newrow.get("_xmin")!=oldrow.get("_xmin"):
                raise AssertionError(f"{label} held watermark xmin changed key={key!r}")
            held+=1
    # An ambiguous new stage key is deliberately absent from the watermark table.
    forbidden_new={key for key in stage if not eligible[key] and key not in old}
    if set(new)&forbidden_new:
        raise AssertionError(f"{label} ambiguous or precision-held new keys created watermarks: {sorted(forbidden_new & set(new),key=repr)[:5]!r}")
    return {"advanced":advanced,"held":held,"source_retrieved_at":source_time.isoformat(),"examples":examples,
            "eligible_stage_keys":sum(eligible.values()),"preserve_excel_keys":sum(preserve.values()),
            "ambiguous_stage_keys":sum(bool(stage[k]) and min(x["price"] for x in stage[k])!=max(x["price"] for x in stage[k]) for k in stage)}

def old_rows(case):
    raw = read_gzip_json(fixture(case, "v14"))["rows"]
    return [(
        row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
        row["product_name"], row["market_name"], row["unit"],
        Decimal(str(row["price"])),
        Decimal(str(row["change_percent"])) if row["change_percent"] is not None else None,
        row["details"],
    ) for row in raw]


def native_v17_rows(case):
    """Read a complete independently pinned native v17 source vector."""
    raw = read_gzip_json(fixture(case, "v17"))
    return [(
        row["source_locator"], row["series"], date.fromisoformat(row["observed_on"]),
        row["product_name"], row["market_name"], row["unit"],
        Decimal(str(row["price"])),
        Decimal(str(row["change_percent"])) if row["change_percent"] is not None else None,
        row["details"],
    ) for row in raw]


def expected_v17_rows(case):
    if case.get("v17_fixture"):
        rows = native_v17_rows(case)
        if (len(rows) != case["v17_raw_rows"]
                or business_vector_sha(rows) != case["v17_canonical_sha256"]):
            raise AssertionError("pinned full native v17 source vector changed")
        return rows
    return [
        (row[0][:-len("inputs-pdf-v14")] + "inputs-pdf-v17", *row[1:8],
         {**row[8], "parser_version": "inputs-pdf-v17"})
        for row in old_rows(case)
    ]


def assert_august_source_delta(case):
    """Allow only the two independently printed, native page-55/page-60 rows."""
    old = old_rows(case)
    new = expected_v17_rows(case)
    typed=sum(row[1]=="dane-inputs-pdf" for row in new)
    unresolved=sum(row[1]=="dane-inputs-pdf-unresolved" for row in new)
    if (len(new),typed,unresolved)!=(case["v17_raw_rows"],case["v17_typed_rows"],case["v17_unresolved_rows"]):
        raise AssertionError("August v17 typed/unresolved split differs from the source-bound manifest")
    old_by_locator = {row[0][:-len("inputs-pdf-v14")] + "inputs-pdf-v17": row
                      for row in old}
    new_by_locator = {row[0]: row for row in new}
    if len(old_by_locator) != len(old) or len(new_by_locator) != len(new):
        raise AssertionError("August v14/v17 source vector has duplicate locators")
    additions = {locator: row for locator, row in new_by_locator.items()
                 if locator not in old_by_locator}
    for locator, old_row in old_by_locator.items():
        actual = new_by_locator.get(locator)
        normalized_old = (locator, old_row[1], old_row[2], old_row[3], old_row[4],
                          old_row[5], old_row[6], old_row[7],
                          {**old_row[8], "parser_version": "inputs-pdf-v17"})
        if actual != normalized_old:
            raise AssertionError("August v17 changed an immutable v14 row: " + locator)
    exact = {
        "PDF page 55,col 1,y 363.3; inputs-pdf-v17": (
            "dane-inputs-pdf", date(2014, 8, 31), "Específico Coopers", "Quimbaya",
            "120 centímetros cúbicos", Decimal("3933"), Decimal("-3.3"),
            "Antisépticos, desinfectantes e higiene", "Quindío", 55,
            "Específico Coopers, 120 centímetros cúbicos"),
        "PDF page 60,col 2,y 203.3; inputs-pdf-v17": (
            "dane-inputs-pdf", date(2014, 8, 31), "Hectárea mensual para maíz", "Armenia",
            "terreno quebrado sin agua", Decimal("70000"), Decimal("0.0"),
            "Arrendamiento de tierras", "Quindío", 60,
            "Hectárea mensual para maíz, terreno quebrado sin agua"),
    }
    if set(additions) != set(exact):
        raise AssertionError(f"August native v17 additions differ: {sorted(additions)!r}")
    for locator, expected in exact.items():
        row = additions[locator]
        details = row[8]
        actual = (row[1], row[2], row[3], row[4], row[5], row[6], row[7],
                  details.get("category"), details.get("department"), details.get("page"),
                  details.get("printed_heading"))
        if actual != expected:
            raise AssertionError(f"August source-backed addition differs at {locator}: {actual!r}")
    return new


def expected_projection_additions(case, inputs_module):
    if case.get("observed_on") != "2014-08-31":
        return []
    expected_rows = assert_august_source_delta(case)
    rows = []
    exact_locators = {
        "PDF page 55,col 1,y 363.3; inputs-pdf-v17",
        "PDF page 60,col 2,y 203.3; inputs-pdf-v17",
    }
    for row in expected_rows:
        locator, _series, day, name, market, unit, price, _change, details = row
        if locator not in exact_locators:
            continue
        rows.append({
            "id": inputs_module.identity(name, details),
            "department": details["department"], "municipality": details["municipality"],
            "observed_on": day, "name": name, "category": details["category"],
            "presentation": details["presentation"], "price": price,
            "document_id": case["document_id"], "source_locator": locator,
            "brand": details.get("brand", ""), "registration": details.get("ica", ""),
            "product_line": details.get("line", ""),
        })
    if len(rows) != 2 or len({(r["id"], r["department"], r["municipality"], r["observed_on"]) for r in rows}) != 2:
        raise AssertionError("August additions do not map to two unique public identities")
    return rows


def phase(case, marker):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {case} {marker}", flush=True)


class ContextGeneralCandidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = load_candidate()
        cls.candidate_worker = load_candidate_worker()
        dsn = os.environ.get("AGRO_CONTEXT_TEST_DSN")
        socket_path = os.environ.get("AGRO_CONTEXT_TEST_SOCKET")
        if not dsn or not socket_path:
            raise RuntimeError("Dedicated owned Unix-socket PostgreSQL DSN and socket path required")
        cls.conn = psycopg.connect(dsn, autocommit=True)
        if (str(cls.conn.info.host) != socket_path
                or cls.conn.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.conn.execute("SHOW server_version").fetchone()[0].startswith("16.")
                or cls.conn.execute("SHOW TimeZone").fetchone()[0] != "UTC"
                or cls.conn.execute("SELECT current_user").fetchone()[0] != "postgres"):
            cls.conn.close()
            raise AssertionError("expected the owned local PostgreSQL 16 Unix-socket database")
        from pipelines.ingestion import inputs, worker
        cls.inputs, cls.worker = inputs, cls.candidate_worker
        cls.old_by_url = {}
        cls.baseline = {}
        cls.seeded_checkpoint_sources = set()
        cls.consolidated_body = CONSOLIDATED_XLSX.read_bytes()
        if (len(cls.consolidated_body) != 54_065_498
                or hashlib.sha256(cls.consolidated_body).hexdigest() != CONSOLIDATED_SHA256):
            raise AssertionError("consolidated XLSX original bytes changed")
        cls.case_by_url = {case["url"]: case for case in MANIFEST["cases"]}
        # Seed each source in its own transaction so ON COMMIT DROP input stages
        # do not leak between PDFs. The production source bodies/SQL vectors and
        # public winner snapshots are pinned in this private packet.
        for case in MANIFEST["cases"]:
            for name, expected_sha in case["fixture_sha256"].items():
                actual=hashlib.sha256((FIXTURES/name).read_bytes()).hexdigest()
                if actual != expected_sha:
                    raise AssertionError(f"fixture drift: {name}")
        with candidate_module(cls.candidate,cls.candidate_worker):
            for case in MANIFEST["cases"]:
                cls.seed_case(case)
        for case in MANIFEST["cases"]:
            cls.baseline[case["document_id"]] = cls.capture_state(case)
            expected_input=read_gzip_json(fixture(case,"input"))
            expected_published=read_gzip_json(fixture(case,"published"))
            expected_revision=read_gzip_json(fixture(case,"revision"))
            actual=cls.baseline[case["document_id"]]
            assert_capture_rows_equal(case["observed_on"]+" raw projection",actual["raw_public"],expected_input)
            assert_capture_rows_equal(case["observed_on"]+" published projection",actual["published"],expected_published)
            assert_capture_rows_equal(case["observed_on"]+" freshness watermarks",actual["revision"],expected_revision)

    @classmethod
    def seed_case(cls, case):
        url, did = case["url"], case["document_id"]
        day = date.fromisoformat(case["observed_on"])
        body = fixture(case, "pdf").read_bytes()
        if (len(body) != case["body_bytes"] or hashlib.sha256(body).hexdigest() != did):
            raise AssertionError("pinned original PDF changed")
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            if len(pdf.pages) != case["page_count"]:
                raise AssertionError("pinned source page count changed")
        old = old_rows(case)
        if (len(old) != case["raw_rows"]
                or business_vector_sha(old) != case["v14_canonical_sha256"]):
            raise AssertionError("full old v14 vector fixture changed")
        if case.get("v17_fixture"):
            assert_august_source_delta(case)
        cls.old_by_url[url] = old
        metadata_rows = read_gzip_json(fixture(case, "metadata"))
        snapshot_rows = read_gzip_json(fixture(case, "input"))
        revisions = read_gzip_json(fixture(case, "revision"))
        history_rows = read_gzip_json(fixture(case, "history"))
        with cls.conn.transaction():
            for source in metadata_rows:
                if source["id"] == did:
                    source_content = body
                elif source["id"] == CONSOLIDATED_DID:
                    source_content = cls.consolidated_body
                else:
                    source_content = b""
                cls.conn.execute(
                    """INSERT INTO source_document
                    (id,title,publisher,source_url,media_type,kind,reference_period,page_count,
                     content,metadata,retrieved_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(id) DO NOTHING""",
                    (source["id"], source["title"], source["publisher"], source["source_url"],
                     source["media_type"], source["kind"], source["reference_period"],
                     source["page_count"], source_content, Jsonb(source["metadata"]),
                     source["retrieved_at"]),
                )
                bound = cls.conn.execute(
                    """SELECT title,publisher,source_url,media_type,kind,reference_period,
                              page_count,metadata,retrieved_at,content
                       FROM source_document WHERE id=%s""",
                    (source["id"],),
                ).fetchone()
                expected_period = source["reference_period"]
                expected_retrieved = datetime.fromisoformat(source["retrieved_at"]) if source["retrieved_at"] else None
                expected_bound = (source["title"],source["publisher"],source["source_url"],
                                  source["media_type"],source["kind"],expected_period,
                                  source["page_count"],source["metadata"],expected_retrieved)
                if (bound is None or bound[:9] != expected_bound
                        or bytes(bound[9] or b"") != source_content):
                    raise AssertionError("seeded retained source metadata/body differs from pinned case")
            cls.conn.execute(
                """INSERT INTO ingestion_asset
                (url,kind,observed_on,document_id,status,processor_version,records,error)
                VALUES(%s,'inputs-pdf',%s,%s,'failed',%s,%s,%s)""",
                (url, day, did, cls.candidate.VERSION, case["raw_rows"],
                 cls.candidate._RETAINED_IDENTITY_ERROR),
            )
            cls.conn.execute("SET LOCAL ROLE agro_ingestor")
            with patch.object(cls.inputs, "input_pdf_version_for_document", return_value=cls.candidate.OLD_VERSION):
                cls.worker.save_rows(cls.conn, did, old)
                cls.inputs.project_pdf_inputs(cls.conn, did, source_url=url)
            # Add current state from the independent read-only capture.
            # This is exact source data, not a predicted projection.
            for history in history_rows:
                if history["document_id"] == did:
                    continue
                cls.conn.execute(
                    f"INSERT INTO historical_price({cls.candidate.ROW_FIELDS},document_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (history["source_locator"], history["series"], history["observed_on"],
                     history["product_name"], history["market_name"], history["unit"],
                     history["price"], history["change_percent"], Jsonb(history["details"]),
                     history["document_id"]),
                )
            for row in snapshot_rows:
                cls.conn.execute(
                    """INSERT INTO input_municipal_price
                    (id,department,observed_on,name,category,presentation,price,document_id,
                     source_locator,brand,registration,product_line,municipality)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(id,department,municipality,observed_on) DO UPDATE SET
                      name=excluded.name,category=excluded.category,presentation=excluded.presentation,
                      price=excluded.price,document_id=excluded.document_id,
                      source_locator=excluded.source_locator,brand=excluded.brand,
                      registration=excluded.registration,product_line=excluded.product_line""",
                    (row["id"],row["department"],row["observed_on"],row["name"],row["category"],
                     row["presentation"],row["price"],row["document_id"],row["source_locator"],
                     row.get("brand", ""),row.get("registration", ""),row.get("product_line", ""),
                     row["municipality"]),
                )
            for row in revisions:
                cls.conn.execute(
                    """INSERT INTO input_revision(id,department,municipality,observed_on,retrieved_at)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id,department,municipality,observed_on)
                    DO UPDATE SET retrieved_at=excluded.retrieved_at""",
                    (row["id"],row["department"],row["municipality"],row["observed_on"],row["retrieved_at"]),
                )
            checkpoint = cls.conn.execute(
                """SELECT records FROM ingestion_checkpoint
                   WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'""",
                (did, cls.candidate.OLD_VERSION),
            ).fetchone()
            if checkpoint != (case["typed_rows"],):
                raise AssertionError("real v14 projection did not create the captured published checkpoint")
            foreign_source_ids = {source["id"] for source in metadata_rows
                                  if source["id"] != did and source["id"] not in cls.seeded_checkpoint_sources}
            for checkpoint in read_gzip_json(fixture(case, "checkpoints")):
                if ((checkpoint["document_id"] == did and checkpoint["step"] != "inputs-pdf:published")
                        or checkpoint["document_id"] in foreign_source_ids):
                    cls.conn.execute(
                        """INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                        VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (checkpoint["document_id"],checkpoint["processor_version"],checkpoint["step"],checkpoint["records"]),
                    )
            cls.seeded_checkpoint_sources.update(foreign_source_ids)

    @classmethod
    def capture_state(cls, case):
        did, url = case["document_id"], case["url"]
        def rows(sql, args):
            cursor = cls.conn.execute(sql, args)
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        source_row=cls.conn.execute("""SELECT id,title,source_url,page_count,content,metadata,xmin::text
            FROM source_document WHERE id=%s""",(did,)).fetchone()
        source=(source_row[0],source_row[1],source_row[2],source_row[3],hashlib.sha256(bytes(source_row[4] or b"")).hexdigest(),source_row[5],source_row[6]) if source_row else None
        foreign_row=cls.conn.execute("""SELECT id,title,source_url,page_count,content,metadata,xmin::text
            FROM source_document WHERE id=%s""",(CONSOLIDATED_DID,)).fetchone()
        foreign_source=(foreign_row[0],foreign_row[1],foreign_row[2],foreign_row[3],hashlib.sha256(bytes(foreign_row[4] or b"")).hexdigest(),foreign_row[5],foreign_row[6]) if foreign_row else None
        foreign_checkpoints=cls.conn.execute("""SELECT document_id,processor_version,step,records,xmin::text
            FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step""",(CONSOLIDATED_DID,)).fetchall()
        foreign_history=cls.conn.execute(f"""SELECT {cls.candidate.ROW_FIELDS},xmin::text
            FROM historical_price WHERE document_id=%s ORDER BY source_locator""",(CONSOLIDATED_DID,)).fetchall()
        old_checkpoints=cls.conn.execute("""SELECT processor_version,step,records,xmin::text
            FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s
            ORDER BY step""",(did,cls.candidate.OLD_VERSION)).fetchall()
        return {
            "source": source,
            "foreign_source": foreign_source,
            "foreign_checkpoints": foreign_checkpoints,
            "foreign_history": foreign_history,
            "old_checkpoints": old_checkpoints,
            "old_checkpoint": cls.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,cls.candidate.OLD_VERSION)).fetchone(),
            "old_rows": cls.conn.execute(f"SELECT {cls.candidate.ROW_FIELDS},xmin::text FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,cls.candidate.OLD_VERSION)).fetchall(),
            "raw_public": rows("SELECT *,xmin::text AS _xmin FROM input_municipal_price WHERE observed_on=%s",(case["observed_on"],)),
            "published": rows("SELECT * FROM published_input_municipal_price WHERE observed_on=%s",(case["observed_on"],)),
            "revision": rows("SELECT *,xmin::text AS _xmin FROM input_revision WHERE observed_on=%s",(case["observed_on"],)),
            "winner_bindings": rows("""SELECT p.id,p.department,p.municipality,p.observed_on,p.name,p.category,p.presentation,p.price,p.document_id,p.source_locator,p.brand,p.registration,p.product_line,h.series AS prior_series FROM input_municipal_price p LEFT JOIN historical_price h ON h.document_id=p.document_id AND h.source_locator=p.source_locator WHERE p.observed_on=%s ORDER BY p.id,p.department,p.municipality,p.observed_on""",(case["observed_on"],)),
        }

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None):
            cls.conn.close()

    def test_a_generic_context_v14_binding_and_ordinary_nonregression(self):
        with candidate_module(self.candidate,self.candidate_worker):
            for case in MANIFEST["cases"]:
                day = date.fromisoformat(case["observed_on"])
                body = fixture(case, "pdf").read_bytes()
                self.assertEqual(self.candidate.retained_v14_input_pdf(
                    self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                # The general context binding must also accept the valid old
                # v14 completed/pending lifecycle, independently of the v17
                # failed retry state used by the four production witnesses.
                for status in ("complete", "processed", "pending"):
                    with self.subTest(url=case["url"], old_v14_status=status):
                        with rollback_probe(self.conn):
                            self.conn.execute(
                                "UPDATE ingestion_asset SET status=%s,processor_version=%s,error=NULL WHERE url=%s",
                                (status,self.candidate.OLD_VERSION,case["url"]),
                            )
                            self.assertEqual(self.candidate.retained_v14_input_pdf(
                                self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                            self.candidate.assert_retained_v14_binding_locked(
                                self.conn,case["url"],"inputs-pdf",day,
                                case["document_id"],case["raw_rows"])
                with self.subTest(url=case["url"],negative="date"):
                    with self.assertRaises(ValueError):
                        self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day+timedelta(days=1),self.candidate.VERSION)
                with self.subTest(url=case["url"],negative="unknown-retry-error"):
                    with rollback_probe(self.conn):
                        self.conn.execute("UPDATE ingestion_asset SET error='unrecognized' WHERE url=%s",(case["url"],))
                        with self.assertRaises(ValueError):
                            self.candidate.retained_v14_input_pdf(self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
            # Ordinary input-PDF metadata at a generic-looking DANE filename
            # remains on its own v14 path, never the context metadata branch.
            case=MANIFEST["cases"][0]; day=date.fromisoformat(case["observed_on"])
            ordinary_url=case["url"].rsplit("/",1)[0]+"/insumos_factores_de_produccion_ordinary.pdf"
            original_body=fixture(case,"pdf").read_bytes()
            writer=PdfWriter()
            for page in PdfReader(io.BytesIO(original_body)).pages: writer.add_page(page)
            writer.add_blank_page(width=612,height=792)
            writer.add_blank_page(width=612,height=792)
            buffer=io.BytesIO(); writer.write(buffer); ordinary_body=buffer.getvalue()
            ordinary_did=hashlib.sha256(ordinary_body).hexdigest()
            type(self).ordinary_control_did=ordinary_did
            self.assertNotEqual(ordinary_did,hashlib.sha256(original_body).hexdigest())
            ordinary_rows=[(row[0],row[1],day,*row[3:]) for row in old_rows(case)]
            with self.conn.transaction():
                self.conn.execute("""INSERT INTO source_document
                    (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
                    VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,%s,%s,%s)""",
                    (ordinary_did,"DANE - insumos_factores_de_produccion_ordinary.pdf",ordinary_url,
                     day,case["page_count"]+2,ordinary_body,Jsonb({"retention":"permanent","ingestion_kind":"inputs-pdf","original_filename":"insumos_factores_de_produccion_ordinary.pdf"})))
                self.conn.execute("""INSERT INTO ingestion_asset(url,kind,observed_on,document_id,status,processor_version,records)
                    VALUES(%s,'inputs-pdf',%s,%s,'complete',%s,%s)""",
                    (ordinary_url,day,ordinary_did,self.candidate.OLD_VERSION,len(ordinary_rows)))
                self.conn.execute("SET ROLE agro_ingestor")
                try:
                    self.worker.save_rows(self.conn,ordinary_did,ordinary_rows)
                    self.conn.execute("""INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                        VALUES(%s,%s,'inputs-pdf:published',%s)""",
                        (ordinary_did,self.candidate.OLD_VERSION,len(ordinary_rows)))
                    self.assertEqual(self.candidate.retained_v14_input_pdf(
                        self.conn,ordinary_url,"inputs-pdf",day,self.candidate.VERSION),ordinary_body)
                finally:
                    self.conn.execute("RESET ROLE")
            with rollback_probe(self.conn):
                self.conn.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s",(ordinary_url,))
                self.candidate.assert_retained_v14_binding_locked(
                    self.conn,ordinary_url,"inputs-pdf",day,ordinary_did,len(ordinary_rows))
            # A context asset may not be redirected to an unrelated ordinary
            # original, even if that original has a plausible DANE filename.
            case=MANIFEST["cases"][0]; day=date.fromisoformat(case["observed_on"])
            with rollback_probe(self.conn):
                self.conn.execute("""UPDATE ingestion_asset SET document_id=%s,status='complete',
                    processor_version=%s,records=0,error=NULL WHERE url=%s""",
                    (ordinary_did,self.candidate.OLD_VERSION,case["url"]))
                with self.assertRaises(ValueError):
                    self.candidate.retained_v14_input_pdf(
                        self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                with self.assertRaises(ValueError):
                    self.candidate.assert_retained_v14_binding_locked(
                        self.conn,case["url"],"inputs-pdf",day,ordinary_did,0)

    def test_b_actual_worker_replays_all_four_pinned_vectors(self):
        from pipelines.ingestion import ocr
        with candidate_module(self.candidate,self.candidate_worker):
            for case in MANIFEST["cases"]:
                phase(case["observed_on"],"replay-start")
                did,url=case["document_id"],case["url"]
                day=date.fromisoformat(case["observed_on"])
                body=fixture(case,"pdf").read_bytes()
                self.conn.execute("SET ROLE agro_ingestor")
                try:
                    with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network forbidden")) as fetch, \
                         patch.object(self.worker,"archive",return_value=did) as archive, \
                         patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                        result=self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                        fetch.assert_not_called()
                        archive.assert_called_once_with(self.conn,url,body,"inputs-pdf",day)
                        transcribe.assert_not_called()
                    expected=expected_v17_rows(case)
                    expected_raw=case.get("v17_raw_rows",case["raw_rows"])
                    expected_typed=case.get("v17_typed_rows",case["typed_rows"])
                    self.assertEqual(result,expected_raw)
                    asset=self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone()
                    self.assertEqual(asset,("complete",self.candidate.VERSION,expected_raw,None))
                    self.assertEqual(self.conn.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,self.candidate.VERSION)).fetchone(),(expected_typed,))
                    old_now=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,self.candidate.OLD_VERSION)).fetchall()
                    self.assertEqual(business_vector_sha(old_now),case["v14_canonical_sha256"])
                    new_now=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,self.candidate.VERSION)).fetchall()
                    self.assertEqual(len(new_now),expected_raw)
                    if case.get("v17_canonical_sha256"):
                        self.assertEqual(business_vector_sha(new_now),case["v17_canonical_sha256"])
                    self.assertEqual(self.candidate.assert_retained_v14_vectors(self.conn,did,self.old_by_url[url],expected,complete=True),expected_raw)
                    self.assertEqual(self.candidate.assert_v17_existing_rows(self.conn,did,expected,complete=True),expected_raw)
                    old_state=self.baseline[did]
                    now=self.capture_state(case)
                    self.assertEqual(now["source"],old_state["source"])
                    for key in ("foreign_source","foreign_checkpoints","foreign_history","old_checkpoints"):
                        self.assertEqual(now[key],old_state[key])
                    self.assertEqual(now["old_checkpoint"],old_state["old_checkpoint"])
                    self.assertEqual(now["old_rows"],old_state["old_rows"])
                    new_locators={row[0] for row in new_now}
                    additions=expected_projection_additions(case,self.inputs)
                    raw_repair=assert_v17_locator_repair("same-body raw public",old_state["raw_public"],now["raw_public"],new_locators,did,additions)
                    published_repair=assert_v17_locator_repair("same-body published",old_state["published"],now["published"],new_locators,did,additions)
                    if additions:
                        source_time=self.conn.execute("SELECT retrieved_at FROM source_document WHERE id=%s",(did,)).fetchone()[0]
                        watermark_result=assert_watermarks_after_replacement("same-body revision rows/xmins",old_state["revision"],now["revision"],expected,self.baseline[did]["winner_bindings"],source_time,self.inputs)
                        self.assertEqual(watermark_result["advanced"],len(additions))
                        self.assertEqual(watermark_result["held"],len(old_state["revision"]))
                    else:
                        assert_snapshot_rows_equal("same-body revision rows/xmins",now["revision"],old_state["revision"])
                    phase(case["observed_on"],f"verified-locator-repairs raw={raw_repair['locator_repairs']} published={published_repair['locator_repairs']} source-backed-additions={len(additions)}")
                finally:
                    self.conn.execute("RESET ROLE")
                phase(case["observed_on"],"replay-end")

    def test_c_changed_body_interruption_then_locked_retry(self):
        from pipelines.ingestion import ocr
        with candidate_module(self.candidate,self.candidate_worker):
            case=MANIFEST["cases"][0]
            did,url=case["document_id"],case["url"]
            day=date.fromisoformat(case["observed_on"])
            original=fixture(case,"pdf").read_bytes()
            # The new body is the exact same printed source plus one blank PDF page.
            writer=PdfWriter()
            for page in PdfReader(io.BytesIO(original)).pages:
                writer.add_page(page)
            writer.add_blank_page(width=612,height=792)
            out=io.BytesIO(); writer.write(out); replacement=out.getvalue()
            new_did=hashlib.sha256(replacement).hexdigest()
            control_writer=PdfWriter()
            for page in PdfReader(io.BytesIO(original)).pages: control_writer.add_page(page)
            control_writer.add_blank_page(width=612,height=792)
            control_writer.add_blank_page(width=612,height=792)
            control_out=io.BytesIO(); control_writer.write(control_out)
            ordinary_control_did=hashlib.sha256(control_out.getvalue()).hexdigest()
            self.assertNotEqual(new_did,ordinary_control_did,"ordinary fixture body aliases changed-body body")
            def replacement_source_state():
                row=self.conn.execute("""SELECT id,title,source_url,media_type,kind,reference_period,
                    page_count,metadata,content,xmin::text FROM source_document WHERE id=%s""",(new_did,)).fetchone()
                if row is None:
                    return None
                return (*row[:8],len(bytes(row[8] or b"")),hashlib.sha256(bytes(row[8] or b"")).hexdigest(),row[9])
            before=self.capture_state(case)
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                # First ordinary mutable-URL fetch archives the changed DID, then a
                # simulated interruption before save_rows leaves an empty pending
                # v17 cohort. The exact old source/history/public state stays put.
                with patch.object(self.worker,"fetch_asset",return_value=replacement) as fetch, \
                     patch.object(self.worker,"archive",wraps=self.worker.archive) as archive, \
                     patch.object(self.worker,"save_rows",side_effect=RuntimeError("owned test interruption")), \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                    with self.assertRaises(RuntimeError):
                        self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                    fetch.assert_called_once()
                    archive.assert_called_once()
                    transcribe.assert_not_called()
                self.assertEqual(self.conn.execute("SELECT document_id,status,processor_version FROM ingestion_asset WHERE url=%s",(url,)).fetchone(),(new_did,"pending",self.candidate.VERSION))
                self.assertIsNone(self.conn.execute("SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(new_did,self.candidate.VERSION)).fetchone())
                replacement_after_interrupt=replacement_source_state()
                self.assertIsNotNone(replacement_after_interrupt)
                self.assertEqual(replacement_after_interrupt[0],new_did)
                self.assertEqual(replacement_after_interrupt[1],"DANE - "+url.rsplit("/",1)[-1])
                self.assertEqual(replacement_after_interrupt[2],url)
                self.assertEqual(replacement_after_interrupt[3],"application/pdf")
                self.assertEqual(replacement_after_interrupt[4],"original")
                self.assertEqual(str(replacement_after_interrupt[5]),day.isoformat())
                self.assertEqual(replacement_after_interrupt[6],case["page_count"]+1)
                self.assertEqual(replacement_after_interrupt[7],{
                    "retention":"permanent","ingestion_kind":"inputs-pdf",
                    "original_filename":url.rsplit("/",1)[-1]})
                self.assertEqual(replacement_after_interrupt[8],len(replacement))
                self.assertEqual(replacement_after_interrupt[9],hashlib.sha256(replacement).hexdigest())
                after_interrupt=self.capture_state(case)
                for key in ("source","foreign_source","foreign_checkpoints","foreign_history",
                            "old_checkpoints","old_checkpoint","old_rows"):
                    self.assertEqual(after_interrupt[key],before[key])
                for key in ("raw_public","published","revision"):
                    assert_snapshot_rows_equal(key+" changed before retry",after_interrupt[key],before[key])
                # Retry under the same current pointer; this invokes the candidate
                # worker and requires its locked replacement/full-old-vector guards.
                with patch.object(self.worker,"fetch_asset",return_value=replacement) as fetch, \
                     patch.object(self.worker,"archive",wraps=self.worker.archive) as archive, \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                    result=self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                    self.assertEqual(result,case["raw_rows"])
                    transcribe.assert_not_called()
                self.assertEqual(fetch.call_count,1)
                self.assertEqual(archive.call_count,1)
                asset=self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone()
                self.assertEqual(asset,("complete",self.candidate.VERSION,case["raw_rows"],None))
                old_rows=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,self.candidate.OLD_VERSION)).fetchall()
                self.assertEqual(business_vector_sha(old_rows),case["v14_canonical_sha256"])
                new_rows=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(new_did,self.candidate.VERSION)).fetchall()
                self.assertEqual(len(new_rows),case["raw_rows"])
                self.assertEqual(self.candidate.assert_retained_context_replacement_vectors(self.conn,did,new_rows),case["raw_rows"])
                self.assertEqual(replacement_source_state(),replacement_after_interrupt)
                after=self.capture_state(case)
                assert_snapshot_rows_equal("completed changed-body raw public values/provenance/xmins",after["raw_public"],before["raw_public"])
                assert_snapshot_rows_equal("completed changed-body published values/provenance",after["published"],before["published"])
                new_source_time=self.conn.execute("SELECT retrieved_at FROM source_document WHERE id=%s",(new_did,)).fetchone()[0]
                watermark_result=assert_watermarks_after_replacement("completed changed-body watermarks",before["revision"],after["revision"],new_rows,before["winner_bindings"],new_source_time,self.inputs)
                phase(case["observed_on"],f"verified-watermarks advanced={watermark_result['advanced']} held={watermark_result['held']}")
                for key in ("source","foreign_source","foreign_checkpoints","foreign_history",
                            "old_checkpoints","old_checkpoint","old_rows"):
                    self.assertEqual(after[key],before[key])
            finally:
                self.conn.execute("RESET ROLE")

if __name__ == "__main__":
    unittest.main(verbosity=2)
