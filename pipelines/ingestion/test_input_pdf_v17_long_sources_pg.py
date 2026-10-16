"""Full-schema retention and retry tests for five source-registered DANE originals."""
from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.util
import sys
import io
import json
import os
import re
import time
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
FIXTURES = HERE / "testdata" / "input_pdf_v17_long_sources"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
CONSOLIDATED_DID = "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"
CONSOLIDATED_SHA256 = "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"
CONSOLIDATED_XLSX = REPO / "pipelines/ingestion/testdata/input_pdf_v17_jan2014/2013-2020_consolidated.xlsx"
CANDIDATE = Path(os.environ.get("AGRO_LONG_PDF_CANDIDATE", str(HERE / "input_pdf_v17_replay.py")))
CANDIDATE_WORKER = Path(os.environ.get("AGRO_LONG_PDF_WORKER", str(HERE / "worker.py")))
MODULE_KEY = "pipelines.ingestion.input_pdf_v17_replay"
WORKER_KEY = "pipelines.ingestion.worker"
QUEUE_KEY = "pipelines.ingestion.queue_plan"


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


def load_candidate_queue():
    path=HERE / "queue_plan.py"
    spec=importlib.util.spec_from_file_location(QUEUE_KEY,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def candidate_module(candidate, candidate_worker, candidate_queue=None):
    package = importlib.import_module("pipelines.ingestion")
    sys = __import__("sys")
    keys=(MODULE_KEY, WORKER_KEY) + ((QUEUE_KEY,) if candidate_queue is not None else ())
    saved = {key: sys.modules.get(key) for key in keys}
    saved_attr = {"input_pdf_v17_replay": getattr(package,"input_pdf_v17_replay",None),
                  "worker": getattr(package,"worker",None),
                  **({"queue_plan":getattr(package,"queue_plan",None)} if candidate_queue is not None else {})}
    sys.modules[MODULE_KEY] = candidate
    sys.modules[WORKER_KEY] = candidate_worker
    package.input_pdf_v17_replay = candidate
    package.worker = candidate_worker
    if candidate_queue is not None:
        sys.modules[QUEUE_KEY]=candidate_queue
        package.queue_plan=candidate_queue
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
        "v14": "V14_FULL_VECTOR_FIRST_D.json.gz",
        "v17": "V17_NATIVE_VECTOR_FIRST_D.json.gz",
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
    if isinstance(raw, dict):
        raw = raw["rows"]
    if raw and isinstance(raw[0], list):
        fields = ("source_locator", "series", "observed_on", "product_name", "market_name",
                  "unit", "price", "change_percent", "details")
        raw = [dict(zip(fields, row)) for row in raw]
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



def assert_native_v17_matches_v14_without_deltas(case):
    """Require exact full-row parity when a native oracle has no reviewed additions."""
    old = old_rows(case)
    new = expected_v17_rows(case)
    typed = sum(row[1] == "dane-inputs-pdf" for row in new)
    unresolved = sum(row[1] == "dane-inputs-pdf-unresolved" for row in new)
    if (len(new), typed, unresolved) != (case["v17_raw_rows"], case["v17_typed_rows"], case["v17_unresolved_rows"]):
        raise AssertionError("native v17 typed/unresolved split differs from the source-bound manifest")
    old_by_locator = {row[0][:-len("inputs-pdf-v14")] + "inputs-pdf-v17": row for row in old}
    new_by_locator = {row[0]: row for row in new}
    if len(old_by_locator) != len(old) or len(new_by_locator) != len(new):
        raise AssertionError("v14/v17 source vector has duplicate locators")
    if set(new_by_locator) != set(old_by_locator):
        raise AssertionError("native v17 source has unreviewed additions or missing rows")
    for locator, old_row in old_by_locator.items():
        normalized_old = (locator, old_row[1], old_row[2], old_row[3], old_row[4],
                          old_row[5], old_row[6], old_row[7],
                          {**old_row[8], "parser_version": "inputs-pdf-v17"})
        if new_by_locator[locator] != normalized_old:
            raise AssertionError("native v17 changed a retained v14 row: " + locator)
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
        cls.candidate_queue = load_candidate_queue()
        dsn = os.environ.get("AGRO_LONG_PDF_TEST_DSN")
        socket_path = os.environ.get("AGRO_LONG_PDF_TEST_SOCKET")
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
            if case["observed_on"] == "2014-08-31":
                assert_august_source_delta(case)
            else:
                assert_native_v17_matches_v14_without_deltas(case)
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
                VALUES(%s,'inputs-pdf',%s,%s,%s,%s,%s,%s)""",
                (url, day, did, case.get("initial_status", "failed"),
                 case.get("initial_version", cls.candidate.VERSION), case["raw_rows"],
                 case.get("initial_error", cls.candidate._RETAINED_IDENTITY_ERROR)),
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
            "raw_public": rows("SELECT *,xmin::text AS _xmin FROM input_municipal_price WHERE observed_on=%s ORDER BY id,department,municipality,observed_on",(case["observed_on"],)),
            "published": rows("SELECT * FROM published_input_municipal_price WHERE observed_on=%s ORDER BY id,department,municipality,observed_on",(case["observed_on"],)),
            "revision": rows("SELECT *,xmin::text AS _xmin FROM input_revision WHERE observed_on=%s ORDER BY id,department,municipality,observed_on",(case["observed_on"],)),
            "pdf_pages": rows("SELECT document_id,page,text_content,tables,extraction_version,xmin::text AS _xmin FROM source_pdf_page WHERE document_id=%s ORDER BY page,extraction_version",(did,)),
            "winner_bindings": rows("""SELECT p.id,p.department,p.municipality,p.observed_on,p.name,p.category,p.presentation,p.price,p.document_id,p.source_locator,p.brand,p.registration,p.product_line,h.series AS prior_series FROM input_municipal_price p LEFT JOIN historical_price h ON h.document_id=p.document_id AND h.source_locator=p.source_locator WHERE p.observed_on=%s ORDER BY p.id,p.department,p.municipality,p.observed_on""",(case["observed_on"],)),
        }

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None):
            cls.conn.close()

    def test_a_retained_sources_and_locked_v14_publication_states(self):
        # Execute the actual candidate repair queue SQL against this isolated
        # full schema. This catches ambiguous joins and verifies all three
        # pinned long originals are eligible without network work.
        jan=next(case for case in MANIFEST["cases"] if case["observed_on"]=="2019-01-31")
        expected_jan=expected_v17_rows(jan)
        expected_jan_sha=self.candidate._retained_vector_sha256(expected_jan)
        self.assertEqual(expected_jan_sha,jan["native_v17_vector_sha256"],
                         "independent Jan native-source oracle differs from the pinned full-vector evidence")
        self.assertEqual(self.candidate.JAN2019_CONTEXT_NEW_VECTOR_SHA256,expected_jan_sha,
                         "Jan retained native-vector guard differs from the independently parsed source oracle")
        nov=next(case for case in MANIFEST["cases"] if case["observed_on"]=="2018-11-30")
        expected_nov=expected_v17_rows(nov)
        expected_nov_sha=self.candidate._retained_vector_sha256(expected_nov)
        self.assertEqual(expected_nov_sha,nov["native_v17_vector_sha256"],
                         "Nov native-source oracle differs from the pinned full-vector evidence")
        self.assertEqual(self.candidate.LONG_INPUT_PDF_REPAIRS[nov["url"]]["new_vector_sha256"],expected_nov_sha,
                         "Nov retained native-vector guard differs from the independently parsed source oracle")
        dec=next(case for case in MANIFEST["cases"] if case["observed_on"]=="2018-12-31")
        expected_dec=expected_v17_rows(dec)
        expected_dec_sha=self.candidate._retained_vector_sha256(expected_dec)
        self.assertEqual(expected_dec_sha,dec["native_v17_vector_sha256"],
                         "Dec native-source oracle differs from the independently captured full vector")
        self.assertEqual(self.candidate.LONG_INPUT_PDF_REPAIRS[dec["url"]]["new_vector_sha256"],expected_dec_sha,
                         "Dec retained native-vector guard differs from the independently captured source oracle")
        expected_urls={case["url"] for case in MANIFEST["cases"]}
        selected_urls=[]
        with candidate_module(self.candidate,self.candidate_worker,self.candidate_queue):
            with rollback_probe(self.conn):
                for _ in expected_urls:
                    queued=self.candidate_queue.repair_candidates(self.conn,limit=8)
                    selected=[row for row in queued if row[1]=="inputs-pdf"]
                    self.assertEqual(len(selected),1,"input repair lane must select one eligible source")
                    url=selected[0][0]
                    selected_urls.append(url)
                    self.conn.execute("UPDATE ingestion_asset SET status='awaiting-ocr' WHERE url=%s",(url,))
        self.assertEqual(set(selected_urls),expected_urls)
        checkpoint_cases=[case for case in MANIFEST["cases"]
                          if case.get("initial_error")=="ValueError: Retained input old publication checkpoint changed"]
        with candidate_module(self.candidate,self.candidate_worker,self.candidate_queue):
            for checkpoint_case in checkpoint_cases:
                with rollback_probe(self.conn):
                    for case in MANIFEST["cases"]:
                        if case is not checkpoint_case:
                            self.conn.execute("UPDATE ingestion_asset SET status='awaiting-ocr' WHERE url=%s",(case["url"],))
                    self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=%s WHERE url=%s",
                                      (self.candidate.VERSION,self.candidate.WORK_DEFERRED_RETRY_ERROR,checkpoint_case["url"]))
                    pending_queue=self.candidate_queue.repair_candidates(self.conn,limit=8)
                    selected=[row[0] for row in pending_queue if row[1]=="inputs-pdf"]
                    self.assertEqual(selected,[checkpoint_case["url"]],"pending budget-resume source must remain queue-eligible")
                    self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=%s WHERE url=%s",
                                      (self.candidate.VERSION,"ValueError: Retained input old publication checkpoint changed",checkpoint_case["url"]))
                    selected=[row[0] for row in self.candidate_queue.repair_candidates(self.conn,limit=8) if row[1]=="inputs-pdf"]
                    self.assertEqual(selected,[checkpoint_case["url"]],"pending captured-checkpoint source must remain queue-eligible")
        with candidate_module(self.candidate, self.candidate_worker):
            for case in MANIFEST["cases"]:
                day=date.fromisoformat(case["observed_on"]); body=fixture(case,"pdf").read_bytes()
                self.assertEqual(len(body),case["body_bytes"])
                self.assertEqual(hashlib.sha256(body).hexdigest(),case["document_id"])
                self.assertEqual(self.candidate.retained_v14_input_pdf(
                    self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                with rollback_probe(self.conn):
                    self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=NULL WHERE url=%s",
                                      (self.candidate.OLD_VERSION,case["url"]))
                    self.assertEqual(self.candidate.retained_v14_input_pdf(
                        self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                    self.candidate.assert_retained_v14_binding_locked(
                        self.conn,case["url"],"inputs-pdf",day,case["document_id"],case["raw_rows"])
                with self.subTest(url=case["url"],negative="wrong-day"):
                    with self.assertRaises(ValueError):
                        self.candidate.retained_v14_input_pdf(
                            self.conn,case["url"],"inputs-pdf",day+timedelta(days=1),self.candidate.VERSION)
                if case.get("initial_error")=="ValueError: Retained input old publication checkpoint changed":
                    captured_error="ValueError: Retained input old publication checkpoint changed"
                    with self.subTest(url=case["url"],retry="pending-captured-error-locked"):
                        with rollback_probe(self.conn):
                            self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=%s WHERE url=%s",
                                              (self.candidate.VERSION,captured_error,case["url"]))
                            self.assertEqual(self.candidate.retained_v14_input_pdf(
                                self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
                            self.candidate.assert_retained_v14_binding_locked(
                                self.conn,case["url"],"inputs-pdf",day,case["document_id"],case["raw_rows"])
                    with self.subTest(url=case["url"],negative="pending-unregistered-error"):
                        with rollback_probe(self.conn):
                            self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=%s WHERE url=%s",
                                              (self.candidate.VERSION,"ValueError: unrelated pending failure",case["url"]))
                            with self.assertRaises(ValueError):
                                self.candidate.retained_v14_input_pdf(
                                    self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                if case.get("initial_error")=="ValueError: Retained input old publication checkpoint changed":
                    with self.subTest(url=case["url"],negative="unregistered-error"):
                        with rollback_probe(self.conn):
                            self.conn.execute("UPDATE ingestion_asset SET status='failed',processor_version=%s,error=%s WHERE url=%s",
                                              (self.candidate.VERSION,"ValueError: unrelated failure",case["url"]))
                            with self.assertRaises(ValueError):
                                self.candidate.retained_v14_input_pdf(
                                    self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION)
                with self.subTest(url=case["url"],retry="pending-work-deferred"):
                    with rollback_probe(self.conn):
                        self.conn.execute("UPDATE ingestion_asset SET status='pending',processor_version=%s,error=%s WHERE url=%s",
                                          (self.candidate.VERSION,self.candidate.WORK_DEFERRED_RETRY_ERROR,case["url"]))
                        self.assertEqual(self.candidate.retained_v14_input_pdf(
                            self.conn,case["url"],"inputs-pdf",day,self.candidate.VERSION),body)
            # Force the actual parser budget check to defer after two page checks,
            # then persist the same pending marker the scheduler writes. Method B
            # retries the retained original through the real worker and verifies
            # complete publication.
            sep=next(c for c in MANIFEST["cases"] if c["observed_on"]=="2018-09-30")
            from pipelines.ingestion import ocr, pdf_sources
            from pipelines.ingestion.resumable_inputs import WorkDeferred
            before=self.capture_state(sep)
            original_budget=pdf_sources.check_run_budget
            calls={"n":0}
            def defer_on_third_page_check():
                calls["n"]+=1
                if calls["n"]==3:
                    raise WorkDeferred(self.candidate.WORK_DEFERRED_RETRY_ERROR)
                return original_budget()
            self.conn.execute("SET ROLE agro_ingestor")
            try:
                with patch.object(pdf_sources,"check_run_budget",side_effect=defer_on_third_page_check), \
                     patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network forbidden")) as fetch, \
                     patch.object(self.worker,"archive",return_value=sep["document_id"]) as archive, \
                     patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                    with self.assertRaises(WorkDeferred):
                        self.worker.process_asset(self.conn,sep["url"],"inputs-pdf",date.fromisoformat(sep["observed_on"]))
                    self.assertEqual(calls["n"],3)
                    fetch.assert_not_called(); archive.assert_called_once(); transcribe.assert_not_called()
            finally:
                self.conn.execute("RESET ROLE")
            with self.conn.transaction():
                self.conn.execute("SET LOCAL ROLE agro_ingestor")
                self.conn.execute("UPDATE ingestion_asset SET status='pending',error=%s WHERE url=%s",
                                  (self.candidate.WORK_DEFERRED_RETRY_ERROR,sep["url"]))
            deferred=self.capture_state(sep)
            for key in ("source","old_checkpoints","old_checkpoint","old_rows","foreign_source","foreign_checkpoints","foreign_history","raw_public","published","revision"):
                self.assertEqual(deferred[key],before[key],"deferred parse changed retained state: "+key)
            self.assertEqual(len(deferred["pdf_pages"]),2,"budget interruption should retain the two extracted page checkpoints")
            self.assertEqual([row["page"] for row in deferred["pdf_pages"]],[1,2])
            self.assertEqual(self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(sep["url"],)).fetchone(),
                             ("pending",self.candidate.VERSION,sep["raw_rows"],self.candidate.WORK_DEFERRED_RETRY_ERROR))
            # Only the two exact Jan aliases may use the page-cap retry reason.
            jan=next(c for c in MANIFEST["cases"] if c["observed_on"]=="2019-01-31")
            with rollback_probe(self.conn):
                self.conn.execute("UPDATE ingestion_asset SET status='failed',processor_version=%s,error=%s WHERE url=%s",
                    (self.candidate.VERSION,"ValueError: Retained input PDF page count mismatch",jan["url"]))
                self.assertEqual(self.candidate.retained_v14_input_pdf(
                    self.conn,jan["url"],"inputs-pdf",date.fromisoformat(jan["observed_on"]),self.candidate.VERSION),fixture(jan,"pdf").read_bytes())
                with self.assertRaises(ValueError):
                    self.candidate.retained_v14_input_pdf(
                        self.conn,jan["url"],"inputs-pdf",date(2019,2,1),self.candidate.VERSION)

    def test_b_actual_worker_replays_long_original_vectors(self):
        from pipelines.ingestion import ocr
        with candidate_module(self.candidate,self.candidate_worker):
            for case in MANIFEST["cases"]:
                did,url=case["document_id"],case["url"]; day=date.fromisoformat(case["observed_on"])
                body=fixture(case,"pdf").read_bytes(); before=self.capture_state(case)
                self.conn.execute("SET ROLE agro_ingestor")
                try:
                    real_archive=self.worker.archive
                    archive_events=[]
                    def checked_archive(db, archive_url, archive_data, archive_kind, archive_day=None,
                                        filename=None, parents=None, publisher_override=None, register_alias=True):
                        digest=hashlib.sha256(archive_data).hexdigest()
                        if archive_kind=="inputs-pdf":
                            if (archive_url!=url or digest!=did or len(archive_data)!=case["body_bytes"]
                                    or archive_day!=day or filename is not None or parents is not None
                                    or publisher_override is not None or register_alias is not True):
                                raise AssertionError("retained source archive binding mismatch")
                            archive_events.append((archive_kind,digest))
                            return real_archive(db,archive_url,archive_data,archive_kind,archive_day,
                                                filename=filename,parents=parents,
                                                publisher_override=publisher_override,register_alias=register_alias)
                        if archive_kind=="ocr-image":
                            if (archive_url!=url or archive_day is not None or filename!="rendered-source.png"
                                    or parents!=[did] or publisher_override!="DANE"
                                    or not archive_data.startswith(b"\x89PNG\r\n\x1a\n")):
                                raise AssertionError("OCR derivative archive is not bound to the retained parent")
                            image_id=real_archive(db,archive_url,archive_data,archive_kind,archive_day,
                                                  filename=filename,parents=parents,
                                                  publisher_override=publisher_override,register_alias=register_alias)
                            if image_id!=digest:
                                raise AssertionError("OCR derivative ID is not its content SHA-256")
                            image=self.conn.execute("SELECT media_type,kind,metadata FROM source_document WHERE id=%s",(image_id,)).fetchone()
                            if image is None or image[0]!="image/png" or image[1]!="extract" or image[2].get("parents")!=[did]:
                                raise AssertionError("retained OCR derivative metadata mismatch")
                            archive_events.append((archive_kind,image_id,did,filename))
                            return image_id
                        raise AssertionError("unexpected archive kind: "+str(archive_kind))
                    with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network forbidden")) as fetch, \
                         patch.object(self.worker,"archive",side_effect=checked_archive) as archive, \
                         patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                        result=self.worker.process_asset(self.conn,url,"inputs-pdf",day)
                        fetch.assert_not_called(); transcribe.assert_not_called()
                    self.assertEqual(archive_events.count(("inputs-pdf",did)),1,
                                     "exactly one retained source archive is required")
                    expected=expected_v17_rows(case)
                    self.assertEqual(result,len(expected))
                    self.assertEqual(self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone(),("complete",self.candidate.VERSION,len(expected),None))
                    self.assertEqual(business_vector_sha(self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,self.candidate.VERSION)).fetchall()),business_vector_sha(expected))
                    after=self.capture_state(case)
                    for key in ("source","old_checkpoints","old_checkpoint","old_rows","foreign_source","foreign_checkpoints","foreign_history"):
                        self.assertEqual(after[key],before[key],f"immutable {key} changed for {url}")
                    self.assertEqual(len(after["pdf_pages"]),case["page_count"],f"page cache incomplete for {url}")
                    after_pages={row["page"]:row for row in after["pdf_pages"]}
                    for cached in before["pdf_pages"]:
                        self.assertEqual(after_pages[cached["page"]],cached,f"cached source page changed for {url}")
                    new_locators={row[0] for row in expected}
                    assert_v17_locator_repair("raw published projection "+url,before["raw_public"],after["raw_public"],new_locators,did)
                    assert_v17_locator_repair("read published projection "+url,before["published"],after["published"],new_locators,did)
                    assert_snapshot_rows_equal("revision full-row vector "+url,after["revision"],before["revision"])
                    raw_rows=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS} FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s ORDER BY source_locator",(did,self.candidate.VERSION)).fetchall()
                    self.assertEqual(business_vector_sha(raw_rows),business_vector_sha(expected))
                finally:
                    self.conn.execute("RESET ROLE")

    def test_c_january_sibling_completion_only_changes_asset(self):
        from pipelines.ingestion import ocr
        case=next(c for c in MANIFEST["cases"] if c["observed_on"]=="2019-01-31")
        did=case["document_id"]; day=date.fromisoformat(case["observed_on"])
        alias=self.candidate.JAN2019_LITERAL_ALIAS_URL
        prior=self.capture_state(case)
        with self.conn.transaction():
            self.conn.execute("SET LOCAL ROLE agro_ingestor")
            self.conn.execute(
                """INSERT INTO ingestion_asset
                (url,kind,observed_on,document_id,status,processor_version,records,error)
                VALUES(%s,'inputs-pdf',%s,%s,'complete',%s,%s,NULL)""",
                (alias,day,did,self.candidate.OLD_VERSION,case["raw_rows"]))
        alias_before=self.conn.execute("SELECT status,processor_version,records,error,xmin::text FROM ingestion_asset WHERE url=%s",(alias,)).fetchone()
        prior_rows=self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS},xmin::text FROM historical_price WHERE document_id=%s ORDER BY details->>'parser_version',source_locator",(did,)).fetchall()
        prior_cp=self.conn.execute("SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step",(did,)).fetchall()
        prior_source=self.conn.execute("SELECT id,title,source_url,page_count,metadata,xmin::text FROM source_document WHERE id=%s",(did,)).fetchone()
        self.conn.execute("SET ROLE agro_ingestor")
        try:
            with patch.object(self.worker,"fetch_asset",side_effect=AssertionError("network forbidden")) as fetch, \
                 patch.object(self.worker,"archive",side_effect=AssertionError("archive forbidden")) as archive, \
                 patch.object(ocr,"transcribe",side_effect=AssertionError("provider forbidden")) as transcribe:
                result=self.worker.process_asset(self.conn,alias,"inputs-pdf",day)
                fetch.assert_not_called(); archive.assert_not_called(); transcribe.assert_not_called()
            self.assertEqual(result,case["raw_rows"])
        finally:
            self.conn.execute("RESET ROLE")
        self.assertEqual(self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(alias,)).fetchone(),("complete",self.candidate.VERSION,case["raw_rows"],None))
        self.assertEqual(self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(case["url"],)).fetchone(),("complete",self.candidate.VERSION,case["raw_rows"],None))
        alias_after=self.conn.execute("SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s",(alias,)).fetchone()
        self.assertEqual(alias_after,("complete",self.candidate.VERSION,case["raw_rows"],None))
        self.assertEqual(alias_before[:4],("complete",self.candidate.OLD_VERSION,case["raw_rows"],None))
        self.assertEqual(self.conn.execute(f"SELECT {self.candidate.ROW_FIELDS},xmin::text FROM historical_price WHERE document_id=%s ORDER BY details->>'parser_version',source_locator",(did,)).fetchall(),prior_rows)
        self.assertEqual(self.conn.execute("SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step",(did,)).fetchall(),prior_cp)
        self.assertEqual(self.conn.execute("SELECT id,title,source_url,page_count,metadata,xmin::text FROM source_document WHERE id=%s",(did,)).fetchone(),prior_source)
        after=self.capture_state(case)
        for key in ("raw_public","published","revision"):
            assert_snapshot_rows_equal("Jan sibling-only "+key,after[key],prior[key])

if __name__ == "__main__":
    unittest.main(verbosity=2)
