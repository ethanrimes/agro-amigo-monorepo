"""Exact-source, paired OCR recovery for the retained Jan 25 2024 DANE ZIP.

This private candidate never edits source originals, OCR payloads, or old
price rows. It checks all 33 image/page bindings and all 66 cached reading
hashes, appends exact source adjudications, publishes only the eleven complete
new children, and keeps the Jan 25 archive date separate from Peñol's printed
Jan 23 measurement date. Armenia Mercar's 59 existing rows are verified and
preserved; they are never inserted again.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import zipfile

import pdfplumber

from . import city_reports
from .jan25_penol_printed_date import (
    PROOF_SHA256 as PENOL_DATE_PROOF_SHA256,
    record_city_source_adjudication,
    validate_exact_penol,
)
from .jan25_armenia_mercar_review import (
    record_city_source_adjudication as record_armenia_adjudication,
    validate_exact_armenia_mercar,
)
from .ocr import VERSION as OCR_VERSION
from .pdf_sources import VerifiedPDFPage

URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip"
PARENT = "503a044d44069e1bbb39d18f5082c86cc1489ad697c823c1345920cda56b8a2b"
DAY = date(2024, 1, 25)
VERSION = "city-v8:armenia-jan2024-ocr-whole-v1:jan25-paired-review-v1"
OCR_MODEL = "gemini-3.5-flash"
MANIFEST_SHA256 = "8a74f482b469759b17dad711b268e89b7c70f3bfb81d1b4921bc4e07e41bd891"


def _manifest_bytes():
    path = Path(__file__).with_name("jan25_paired_projection_manifest.json")
    data = path.read_bytes()
    if sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Jan 25 paired projection manifest changed")
    return json.loads(data)


def _fail(condition, reason):
    if not condition:
        raise ValueError("Exact Jan 25 paired OCR guard: " + reason)


def _payload_sha(result):
    return sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def _row_sha(rows):
    return sha256(json.dumps([[str(v) for v in row] for row in rows],
                             ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _printed_header(result):
    text = result.get("text")
    _fail(isinstance(text, str), "OCR text missing")
    dates = re.findall(r"\b\d{1,2} de [A-Za-zÁÉÍÓÚáéíóúÑñ]+ de \d{4}\b", text)
    title = re.search(r"PRECIOS\s+DE\s+VENTA\s+MAYORISTAS?\s+(.+)", text, re.IGNORECASE)
    market = None
    if title:
        market = re.split(
            r"\s+PRODUCTOS PRIMERA CALIDAD|\s+\d{1,2} de [A-Za-zÁÉÍÓÚáéíóúÑñ]+ de \d{4}|\s+P[aá]gina\s+\d+",
            title.group(1), maxsplit=1, flags=re.IGNORECASE,
        )[0].strip()
    page = re.search(r"P[aá]gina\s+(\d+)\s+de\s+(\d+)", text, re.IGNORECASE)
    return {"dates": dates, "market": market,
            "page": int(page.group(1)) if page else None,
            "page_count": int(page.group(2)) if page else None}


def _normalize_row(row, page_spec):
    result = list(row)
    indexes = {"product": 3, "category": 5, "presentation": 6, "round_label": 10}
    for key, index in indexes.items():
        aliases = page_spec.get("normalized_differences", {}).get(key, {})
        value = str(result[index])
        if value in aliases:
            result[index] = aliases[value]
    return tuple(result)


def _parse_member_pair(pdf_bytes, entry, page_images, results, manifest):
    parsed = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        _fail(0 < len(pdf.pages) <= 20, "member page count outside reviewed bounds")
        _fail(all(1 <= n <= len(pdf.pages) for n in page_images), "OCR page index outside PDF")
        for reading in (0, 1):
            pages = list(pdf.pages)
            for page_number, image_id in page_images.items():
                pages[page_number - 1] = VerifiedPDFPage(results[image_id][reading])
                spec = manifest["pages"][image_id]
                header = _printed_header(results[image_id][reading])
                _fail(header == spec.get("printed_header"), f"printed header changed for {entry} p{page_number}")
                expected_day = "2024-01-23" if entry == "Peñol, 25-1-2024.pdf" else DAY.isoformat()
                expected_date = "23 de Enero de 2024" if expected_day == "2024-01-23" else "25 de Enero de 2024"
                _fail(header["dates"] == [expected_date] and header["page"] == page_number,
                      f"printed date/page conflict for {entry} p{page_number}")
                _fail(bool(header["market"]) and header["page"] <= header["page_count"],
                      f"printed market/page binding absent for {entry} p{page_number}")
            heading = pages[0].extract_text() or ""
            if 1 in page_images:
                first = _printed_header(results[page_images[1]][reading])
                heading = ("PRECIOS DE VENTA MAYORISTA\n" + first["market"] +
                           "\nPRODUCTOS DE PRIMERA CALIDAD\n" + first["dates"][0])
            rows = list(city_reports.parse_city_pages(pages, DAY, heading=heading))
            parsed.append(rows)
    left, right = parsed
    _fail(len(left) == len(right), f"paired typed row count differs for {entry}")
    normalized_left = []
    normalized_right = []
    for index, (a, b) in enumerate(zip(left, right)):
        _fail(len(a) == len(b) == 17, "typed tuple no longer has 17 fields")
        page = a[16]
        _fail(page == b[16], "paired printed source page differs")
        image_id = page_images.get(page)
        if image_id is None:
            _fail(a == b, f"native page differs between OCR pair parses: {entry} p{page}")
            normalized_left.append(a)
            normalized_right.append(b)
            continue
        spec = manifest["pages"][image_id]
        a2 = _normalize_row(a, spec)
        b2 = _normalize_row(b, spec)
        aliases = spec.get("locator_aliases", {}).get(str(index))
        if aliases is not None:
            _fail([a[0], b[0]] == aliases, f"source locator alias changed: {entry} row {index}")
            b2 = (a2[0],) + b2[1:]
        else:
            _fail(a[0] == b[0], f"unreviewed source locator change: {entry} row {index}")
        _fail(a2 == b2, f"paired 17-field tuple differs after exact projection: {entry} row {index}")
        normalized_left.append(a2)
        normalized_right.append(b2)
    _fail(normalized_left == normalized_right, f"whole-child pairs differ: {entry}")
    child = manifest["children"].get(next((did for did, item in manifest["children"].items()
                                           if item["entry"] == entry), ""))
    _fail(child is not None and len(normalized_left) == child["expected_row_count"],
          f"whole-child row count changed: {entry}")
    _fail(_row_sha(normalized_left) == child["expected_rows_sha256"],
          f"whole-child full 17-field oracle changed: {entry}")
    return normalized_left


def _checked_zip(parent_bytes, manifest):
    _fail(sha256(parent_bytes).hexdigest() == PARENT == manifest["parent_sha256"], "ZIP SHA changed")
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as archive:
        actual = []
        bodies = {}
        for m in archive.infolist():
            if m.is_dir():
                continue
            body = archive.read(m)
            did = sha256(body).hexdigest()
            actual.append({"entry": m.filename, "member_did": did, "offset": m.header_offset,
                           "crc32": m.CRC, "size": m.file_size, "sha256": did})
            bodies[did] = body
        _fail(actual == manifest["zip_members"], "exact ZIP member roster/metadata/body changed")
        _fail(len(actual) == 30, "ZIP member count changed")
        return bodies


def _read_paired_inputs(db, parent_bytes, manifest):
    asset = db.execute("""SELECT a.kind,a.observed_on,a.document_id,a.status,a.records,a.processor_version,
      d.kind,d.publisher,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id WHERE a.url=%s""", (URL,)).fetchone()
    _fail(asset is not None, "parent asset/source missing")
    (akind, day, did, status, records, asset_version, dkind, publisher, source_url, media,
     period, metadata, retained) = asset
    _fail((akind, day, did, dkind, publisher, source_url, media, period) ==
          ("city-zip", DAY, PARENT, "original", "DANE", URL, "application/zip", DAY.isoformat()),
          "parent asset/source identity changed")
    _fail(status in ("review", "pending", "failed", "complete"), "parent status unknown")
    _fail(asset_version in ("city-v8:armenia-jan2024-ocr-whole-v1", VERSION),
          "parent processor revision is not the exact Jan 25 baseline or candidate")
    _fail(records in (1598, 2338), "parent record count is neither baseline nor exact Jan25 repair")
    _fail(isinstance(metadata, dict) and metadata.get("ingestion_kind") == "city-zip" and
          metadata.get("retention") == "permanent" and
          metadata.get("original_filename") == URL.rsplit("/", 1)[-1], "parent metadata changed")
    _fail(bytes(retained) == parent_bytes, "supplied parent differs from retained original")
    bodies = _checked_zip(bytes(retained), manifest)
    members = db.execute("""SELECT m.entry_name,m.document_id,d.kind,d.publisher,d.source_url,
      d.media_type,d.reference_period,d.page_count,d.metadata,d.content
      FROM source_archive_member m JOIN source_document d ON d.id=m.document_id
      WHERE m.archive_id=%s ORDER BY m.entry_name""", (PARENT,)).fetchall()
    _fail(len(members) == 30, "retained member mapping count changed")
    _fail(len({m[0] for m in members}) == 30, "duplicate retained member mapping")
    member_by_entry = {}
    for row in members:
        entry, child_id, kind, publisher, src, mt, ref, pages, meta, content = row
        _fail(child_id == sha256(bytes(content)).hexdigest() and child_id == sha256(bodies[child_id]).hexdigest(),
              "retained child ID/body does not match ZIP member")
        _fail((kind, publisher, src, mt, ref) ==
              ("original", "DANE", URL, "application/pdf", "Serie histórica completa"),
              "retained child source metadata changed")
        _fail(isinstance(meta, dict) and meta.get("ingestion_kind") == "city-pdf" and
              meta.get("retention") == "permanent" and meta.get("parents") == [PARENT] and
              meta.get("archive_entry") == entry and meta.get("original_filename") == entry,
              "retained child metadata/parent binding changed")
        _fail(entry in {x["entry"] for x in manifest["zip_members"]}, "unexpected child filename")
        member_by_entry[entry] = child_id
    roster = {x["entry"]: x["member_did"] for x in manifest["zip_members"]}
    _fail(member_by_entry == roster, "archive-member map differs from exact ZIP roster")
    # Keep a direct immutable parent body check and a second source-DID binding.
    parent_source = db.execute("SELECT content,kind,source_url,media_type,reference_period,metadata FROM source_document WHERE id=%s",
                               (PARENT,)).fetchone()
    _fail(parent_source is not None and bytes(parent_source[0]) == parent_bytes and
          parent_source[1:5] == ("original", URL, "application/zip", DAY.isoformat()) and
          parent_source[5] == metadata, "retained parent original metadata/body changed")

    task_rows = db.execute("""SELECT t.document_id,t.source_locator,t.image_id,t.source_kind,t.source_page,
      t.status,t.error,d.kind,d.publisher,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM source_ocr_task t JOIN source_document d ON d.id=t.image_id
      WHERE t.source_kind='city-pdf' AND t.document_id=ANY(%s::text[]) ORDER BY t.document_id,t.source_page""",
      ([x["member_did"] for x in manifest["zip_members"]],)).fetchall()
    _fail(len(task_rows) == 33, "OCR task count changed")
    page_specs = manifest["pages"]
    cached_results = {}
    image_to_task = {}
    for row in task_rows:
        child_id, locator, image_id, source_kind, page, status, error, ikind, publisher, src, mt, ref, imeta, image_content = row
        spec = page_specs.get(image_id)
        _fail(spec is not None, "OCR task image is not in exact page manifest")
        _fail((child_id, locator, source_kind, page, status, error) ==
              (spec["member_did"], f"PDF page {spec['page']}", "city-pdf", spec["page"],
               spec["task_status"], spec["task_error"]),
              "OCR task source page/status/error binding changed")
        _fail((ikind, publisher, src, mt, ref) ==
              ("extract", "DANE", URL, "image/png", "Serie histórica completa"),
              "OCR image source document identity changed")
        _fail(isinstance(imeta, dict) and imeta.get("ingestion_kind") == "ocr-image" and
              imeta.get("retention") == "permanent" and imeta.get("parents") == [child_id] and
              imeta.get("original_filename") == "rendered-source.png" and
              imeta.get("archive_entry") == "rendered-source.png", "OCR image metadata binding changed")
        image_bytes = bytes(image_content)
        _fail(sha256(image_bytes).hexdigest() == image_id, "OCR image DID/body SHA changed")
        image_to_task[image_id] = row
    _fail(len(image_to_task) == 33, "duplicate image task")
    result_rows = db.execute("""SELECT image_id,version,reading,result FROM source_ocr_result
      WHERE image_id=ANY(%s::text[]) AND version=%s ORDER BY image_id,reading""",
      (list(image_to_task), OCR_VERSION)).fetchall()
    _fail(len(result_rows) == 66, "cached OCR reading count changed")
    for image_id, version, reading, result in result_rows:
        spec = page_specs.get(image_id)
        _fail(spec is not None and version == OCR_VERSION and reading in (0, 1), "cached reading key changed")
        _fail(_payload_sha(result) == spec["reading_sha256"][str(reading)], "cached OCR payload hash changed")
        _fail(result.get("version") == OCR_VERSION and result.get("model") == OCR_MODEL,
              "cached OCR model/version changed")
        _fail(result.get("review_notes") == (result.get("review_notes") or []) and
              all(isinstance(x, str) for x in result.get("review_notes", [])), "OCR review note shape changed")
        cached_results.setdefault(image_id, {})[reading] = result
    _fail(set(cached_results) == set(page_specs) and all(set(p) == {0, 1} for p in cached_results.values()),
          "OCR page pair coverage changed")
    return asset, members, bodies, cached_results, image_to_task


def project_source(parent_bytes, cached_results, manifest=None):
    """Native parser-derived, full-17-field paired cohort (no SQL writes)."""
    manifest = manifest or _manifest_bytes()
    bodies = _checked_zip(parent_bytes, manifest)
    by_did = {item["member_did"]: item for item in manifest["zip_members"]}
    image_pages = defaultdict(dict)
    for image_id, spec in manifest["pages"].items():
        image_pages[spec["member_did"]][spec["page"]] = image_id
        _fail(set(cached_results.get(image_id, {})) == {0, 1}, "paired OCR page missing")
        for reading in (0, 1):
            result = cached_results[image_id][reading]
            _fail(_payload_sha(result) == spec["reading_sha256"][str(reading)], "OCR pair hash differs")
            _fail(_printed_header(result) == spec["printed_header"], "printed header differs")
    outputs = {}
    for child_id, pages in image_pages.items():
        entry = by_did[child_id]["entry"]
        rows = _parse_member_pair(bodies[child_id], entry, pages, cached_results, manifest)
        expected = manifest["children"][child_id]
        _fail(len(rows) == expected["expected_row_count"] and _row_sha(rows) == expected["expected_rows_sha256"],
              "paired child full tuple oracle differs")
        outputs[child_id] = rows
    _fail(len(outputs) == 15 and sum(len(cached_results[x]) for x in cached_results) == 66,
          "full OCR child cohort changed")
    return outputs


def _source_rows(db, parent_bytes, manifest):
    asset, members, bodies, cached, tasks = _read_paired_inputs(db, parent_bytes, manifest)
    projections = project_source(parent_bytes, cached, manifest)
    return asset, members, bodies, cached, tasks, projections


def _source_review_history(db, child_id, entry, page, task, spec, projection_sha):
    policy = f"{VERSION}:page-{page}:{projection_sha}"
    prior_status, prior_error = spec["task_status"], spec["task_error"]
    _fail(prior_status == "review" and isinstance(prior_error, str) and bool(prior_error),
          f"publish target OCR task is not the exact pinned review: {entry} p{page}")
    db.execute("""INSERT INTO source_ocr_review_history
      (document_id,source_locator,policy_version,source_kind,prior_status,prior_error,
       reading0_sha256,reading1_sha256)
      VALUES(%s,%s,%s,'city-pdf',%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
      (child_id, f"PDF page {page}", policy, prior_status, prior_error,
       spec["reading_sha256"]["0"], spec["reading_sha256"]["1"]))
    stored = db.execute("""SELECT prior_status,prior_error,reading0_sha256,reading1_sha256
      FROM source_ocr_review_history WHERE document_id=%s AND source_locator=%s AND policy_version=%s""",
      (child_id, f"PDF page {page}", policy)).fetchone()
    _fail(stored == (prior_status, prior_error, spec["reading_sha256"]["0"], spec["reading_sha256"]["1"]),
          f"append-only OCR adjudication annotation changed for {entry} p{page}")


def publish_exact_jan25(db, parent_bytes, parent_did, source_url, day, processor_version):
    """Publish exact paired children and both source-grounded OCR adjudications."""
    if source_url != URL:
        return None
    manifest = _manifest_bytes()
    _fail(parent_did == PARENT and day == DAY and processor_version == VERSION,
          "source URL/DID/day/parser version is not this exact repair")
    _, members, bodies, cached, tasks, projections = _source_rows(db, parent_bytes, manifest)
    child_rows = {row[1]: row for row in members}
    page_by_member = defaultdict(list)
    for image_id, spec in manifest["pages"].items():
        page_by_member[spec["member_did"]].append((spec["page"], image_id, spec))
    accepted = 0
    failures = []
    publish_ids = list(manifest["publish_member_ids"])
    _fail(len(publish_ids) == 11 and len(set(publish_ids)) == 11, "exact publish target set changed")
    penol_id = manifest["date_mismatch_member"]
    penol_rows = projections.get(penol_id)
    penol_evidence = validate_exact_penol(
        source_url, parent_bytes, day, manifest, cached, tasks, projections,
    )
    _fail(penol_rows is not None and len(penol_rows) == 10
          and all(row[1] == date(2024, 1, 23) for row in penol_rows),
          "Peñol printed Jan 23 projection changed")
    armenia_evidence, armenia_rows = validate_exact_armenia_mercar(
        source_url, parent_bytes, day, manifest, cached, tasks, projections,
    )
    armenia_id = armenia_evidence["evidence_document_id"]
    _fail(armenia_id == "f7b1980c7b511bf7a12fdfb325862df6ab64b35571a7ccd935f9306dbc21a412"
          and len(armenia_rows) == 59, "exact Armenia Mercar review target changed")
    # The 59 Armenia Mercar rows are already part of the immutable 1,598-row
    # baseline. Validate every retained field against the manually reviewed
    # projection; only append an adjudication witness, never insert or rewrite
    # those old rows. The eleven-member append target remains exactly 740.
    publish_projections = dict(projections)
    _fail(len(set(publish_ids)) == 11 and penol_id in publish_ids
          and armenia_id not in publish_ids
          and sum(len(publish_projections[did]) for did in publish_ids) == 740,
          "exact 740-row paired publication target set changed")
    armenia_entry = manifest["children"][armenia_id]["entry"]
    with db.transaction():
        existing_price_count = db.execute(
            "SELECT count(*) FROM regional_price WHERE document_id=%s", (armenia_id,),
        ).fetchone()[0]
        existing_class_count = db.execute(
            "SELECT count(*) FROM regional_classification WHERE document_id=%s", (armenia_id,),
        ).fetchone()[0]
        _fail(existing_price_count == existing_class_count == 59,
              "the 59 previously retained Armenia rows must exist before adjudication")
        _, _, parity = city_reports._publication_parity(
            db, armenia_id, armenia_rows, require_all=True,
        )
        _fail(parity["native_count"] == parity["stored_count"] ==
              parity["classification_count"] == 59 and parity["difference_count"] == 0,
              "existing Armenia 59-row full17/category projection differs from exact manual proof")
        record_armenia_adjudication(db, armenia_evidence)
        for page, image_id, spec in page_by_member[armenia_id]:
            _source_review_history(db, armenia_id, armenia_entry, page,
                                  tasks[image_id], spec, armenia_evidence["full17_sha256"])
    # Surface only exact cached child tasks that remain in review and are not
    # part of the source-bound publication set. The paired-input validator
    # above already proves each task's exact member, page, status, and error.
    published_ids = set(publish_ids) | {armenia_id}
    for child_id, child in manifest["children"].items():
        if child_id in published_ids:
            continue
        review_errors = sorted({spec["task_error"] for spec in manifest["pages"].values()
                                if spec["member_did"] == child_id
                                and spec["task_status"] == "review"
                                and isinstance(spec["task_error"], str)
                                and spec["task_error"]})
        if review_errors:
            failures.append({"filename": child["entry"],
                             "error": "; ".join(review_errors)})
    for child_id in publish_ids:
        entry, _, _, _, _, _, _, _, _, child_content = child_rows[child_id]
        expected = manifest["children"][child_id]
        rows = publish_projections[child_id]
        _fail(child_content is not None and sha256(bytes(child_content)).hexdigest() == child_id,
              f"retained target original changed: {entry}")
        from types import SimpleNamespace
        zip_member = next(x for x in manifest["zip_members"] if x["member_did"] == child_id)
        step = city_reports._member_step(SimpleNamespace(filename=entry, header_offset=zip_member["offset"], CRC=zip_member["crc32"], file_size=zip_member["size"]), DAY)
        checkpoint = db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s",
                                (PARENT, VERSION, step)).fetchone()
        existing_count = db.execute("SELECT count(*) FROM regional_price WHERE document_id=%s", (child_id,)).fetchone()[0]
        classification_count = db.execute("SELECT count(*) FROM regional_classification WHERE document_id=%s", (child_id,)).fetchone()[0]
        _fail(existing_count in (0, expected["expected_row_count"]), f"partial existing target child rows: {entry}")
        _fail(classification_count in (0, expected["expected_row_count"]), f"partial existing target child classification: {entry}")
        with db.transaction():
            if child_id == penol_id:
                # This record is append-only and binds the exact manual grid,
                # projected full17 vector, paired OCR hashes and prior task.
                record_city_source_adjudication(db, penol_evidence)
            if checkpoint is not None:
                _fail(checkpoint == (expected["expected_row_count"],) and
                      existing_count == classification_count == expected["expected_row_count"],
                      f"target child checkpoint/cohort mismatch: {entry}")
                conflict = city_reports._publication_conflict(db, child_id, rows, VERSION,
                                                              PARENT, entry, require_all=True,
                                                              native_source=(parent_bytes, bytes(child_content), URL))
                _fail(conflict is None, f"target child replay parity failed: {entry}: {conflict}")
            else:
                _fail(existing_count == classification_count == 0,
                      f"uncheckpointed target child already has publication rows: {entry}")
                conflict = city_reports._publication_conflict(db, child_id, rows, VERSION,
                                                              PARENT, entry, native_source=(parent_bytes, bytes(child_content), URL))
                _fail(conflict is None, f"target child prepublication conflict: {entry}: {conflict}")
                city_reports.save_classifications(db, child_id, rows)
                city_reports._bulk_insert(db, "regional_price", ((child_id, *row) for row in rows))
                conflict = city_reports._publication_conflict(db, child_id, rows, VERSION,
                                                              PARENT, entry, require_all=True,
                                                              native_source=(parent_bytes, bytes(child_content), URL))
                _fail(conflict is None, f"target child postpublication parity failed: {entry}: {conflict}")
                db.execute("""INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                  VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (PARENT, VERSION, step, len(rows)))
                _fail(db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s",
                                 (PARENT, VERSION, step)).fetchone() == (len(rows),),
                      f"target child checkpoint drift: {entry}")
            child_projection_sha = expected["expected_rows_sha256"]
            for page, image_id, spec in page_by_member[child_id]:
                _source_review_history(db, child_id, entry, page, tasks[image_id], spec, child_projection_sha)
        accepted += len(rows)
    penol_entry = manifest["children"][penol_id]["entry"]
    _fail(penol_evidence["policy_version"].endswith(PENOL_DATE_PROOF_SHA256),
          "Peñol date adjudication policy is not bound to the exact proof")
    if failures:
        raise city_reports.CityZipPartialReview(accepted, failures)
    return accepted
