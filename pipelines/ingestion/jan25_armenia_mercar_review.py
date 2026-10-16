"""Exact-source text adjudication for the 59-row Armenia, Mercar child.

This private peer proof never edits source documents, OCR tasks, or cached OCR
payloads. It validates the retained parent/member/page/task/paired-reading
identities and all 59 independent manual vectors before returning the one
source-specific display correction authorized by the physical review.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

PROOF_FILE = "jan25_armenia_mercar_review_proof.json"
PROOF_SHA256 = "d9c8d7f5bd045c7ca792b7855c85083f56478e9cfb0108b9a0683c51aa587712"
MANUAL_REVIEW_SHA256 = "45ef651698eaf9c47bd6c529bb4681c46b8e25752b612a379c30ee3c34f5f03c"
MANIFEST_SHA256 = "8a74f482b469759b17dad711b268e89b7c70f3bfb81d1b4921bc4e07e41bd891"
MANUAL_REVIEW_RUNTIME_PATH = "jan25_source_proofs/ROOT_MANUAL_59_ROW_REVIEW_FIRST_A.json"
ENTRY = "Armenia, Mercar 25-1-2024.pdf"
CHILD = "f7b1980c7b511bf7a12fdfb325862df6ab64b35571a7ccd935f9306dbc21a412"
PAGE_IMAGES = {
    1: "c448dee7e0e84b348c13789bcef36edc92594e1b38c8e616007637d83c04f1f3",
    2: "b011257b884b377b07c4e8479efda3193feacb5f2c9f8399d4aa08132f93ae7b",
}
PRESENTATION_NORMALIZATION_ORDINALS = (10, 17, 18, 19, 25, 28, 40)
CANONICAL_CATEGORY_PATHS = {
    "Tuberculos, raices y platanos > Otros tuberculos":
        "Tubérculos, raíces y plátanos > Otros tubérculos",
    "Tuberculos, raices y platanos > Plátano":
        "Tubérculos, raíces y plátanos > Plátano",
    "Tuberculos, raices y platanos > Papa":
        "Tubérculos, raíces y plátanos > Papa",
    "Tuberculos, raices y platanos > Yuca":
        "Tubérculos, raíces y plátanos > Yuca",
}


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError("Exact Jan25 Armenia Mercar source-text proof: " + detail)


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _row_sha(rows) -> str:
    return sha256(json.dumps([[str(value) for value in row] for row in rows],
                             ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _load_proof():
    proof_path = Path(__file__).with_name(PROOF_FILE)
    raw = proof_path.read_bytes()
    _require(sha256(raw).hexdigest() == PROOF_SHA256, "private proof file changed")
    proof = json.loads(raw)
    manual_path = Path(__file__).parent / MANUAL_REVIEW_RUNTIME_PATH
    _require(_sha_file(manual_path) == MANUAL_REVIEW_SHA256 == proof["manual_review_sha256"],
             "root physical 59-row oracle changed")
    manifest_path = Path(__file__).with_name("jan25_paired_projection_manifest.json")
    _require(_sha_file(manifest_path) == MANIFEST_SHA256 == proof["manifest_sha256"],
             "paired source manifest changed")
    return proof, json.loads(manual_path.read_text())


def _raw_cells(result):
    return [str(cell) for table in result.get("tables", [])
            for row in table for cell in row if cell is not None]


def validate_exact_armenia_mercar(source_url, parent_bytes, archive_day, manifest,
                                   cached_results, image_to_task, projections):
    """Validate all retained source bindings and return (evidence, rows)."""
    proof, oracle = _load_proof()
    source = proof["source"]
    _require(source_url == source["url"] == manifest["url"], "source URL changed")
    _require(archive_day.isoformat() == source["archive_publication_day"]
             == manifest["parent_publication_date"], "archive publication day changed")
    _require(sha256(parent_bytes).hexdigest() == source["archive_sha256"]
             == manifest["parent_sha256"], "parent ZIP bytes changed")
    _require(len(manifest["zip_members"]) == 30
             and manifest["source_roster_sha256"] == proof["roster_sha256"],
             "exact 30-member roster changed")
    roster = [{"entry": row["entry"], "document_id": row["member_did"]}
              for row in manifest["zip_members"]]
    _require(_json_sha(roster) == proof["roster_pairs_sha256"], "member names/DIDs changed")
    _require(oracle["parent_archive_sha256"] == source["archive_sha256"]
             and oracle["archive_entry"] == ENTRY and oracle["child_sha256"] == CHILD,
             "physical oracle source binding changed")
    child = manifest["children"].get(CHILD)
    _require(child is not None and child["entry"] == ENTRY
             and child["expected_row_count"] == 59
             and len(child["pages"]) == 2, "exact target child or row count changed")
    _require(child["pages"] == {str(page): image for page, image in PAGE_IMAGES.items()},
             "PDF page/image mapping changed")
    _require(len(oracle["manual_rows"]) == 59 and oracle["manual_row_count"] == 59
             and oracle["page_counts"] == {"1": 37, "2": 22},
             "independent manual row/page counts changed")
    _require(source["printed_market"] == oracle["printed_market"] == "Armenia, Mercar"
             and source["printed_date"] == oracle["printed_date"] == "2024-01-25"
             and oracle["printed_round1_hours"] == "05:00 - 07:00",
             "manual printed market/date/round changed")

    pair_hashes = {}
    prior_tasks = []
    for page, image_id in PAGE_IMAGES.items():
        spec = manifest["pages"].get(image_id)
        _require(spec is not None and spec["member_did"] == CHILD
                 and spec["entry"] == ENTRY and spec["page"] == page,
                 f"page {page} OCR task/image is not bound to the exact child")
        _require(spec["ocr_version"] == "gemini-image-ocr-v2"
                 and spec["printed_header"] == {
                     "dates": ["25 de Enero de 2024"], "market": "Armenia, Mercar",
                     "page": page, "page_count": 2,
                 }, f"page {page} printed header changed")
        task = image_to_task.get(image_id)
        _require(task is not None, f"page {page} task is missing")
        _require((task[0], task[1], task[2], task[3], task[4], task[5], task[6]) ==
                 (CHILD, f"PDF page {page}", image_id, "city-pdf", page,
                  "review", "Independent OCR readings disagree or contain uncertainty; not published as prices"),
                 f"page {page} task identity/status changed")
        _require((task[7], task[8], task[9], task[10], task[11]) ==
                 ("extract", "DANE", source_url, "image/png", "Serie histórica completa"),
                 f"page {page} image source identity changed")
        _require(task[12].get("parents") == [CHILD]
                 and task[12].get("retention") == "permanent"
                 and task[12].get("ingestion_kind") == "ocr-image"
                 and sha256(bytes(task[13])).hexdigest() == image_id,
                 f"page {page} rendered image identity changed")
        readings = cached_results.get(image_id)
        _require(isinstance(readings, dict) and set(readings) == {0, 1},
                 f"page {page} paired readings are missing")
        read_hashes = {}
        for reading in (0, 1):
            result = readings[reading]
            digest = _json_sha(result)
            _require(digest == spec["reading_sha256"][str(reading)],
                     f"page {page} reading {reading} raw payload changed")
            _require(result.get("version") == "gemini-image-ocr-v2"
                     and result.get("model") == "gemini-3.5-flash",
                     f"page {page} reading {reading} version/model changed")
            read_hashes[str(reading)] = digest
        pair_hashes[image_id] = {"page": page, "image_sha256": image_id,
                                 "reading_sha256": read_hashes}
        prior_tasks.append({"document_id": task[0], "source_locator": task[1],
                            "image_id": task[2], "source_kind": task[3],
                            "source_page": task[4], "status": task[5], "error": task[6]})

    # These exact raw OCR literals are pinned by the full JSON hashes above.
    carton_variants = {page: [_raw_cells(cached_results[image][reading])
                              for reading in (0, 1)]
                       for page, image in PAGE_IMAGES.items()}
    for page, product in ((1, "Fresa"), (1, "Manzana roja importada"),
                          (1, "Manzana royal gala importada"), (1, "Manzana verde importada"),
                          (1, "Pera importada"), (1, "Uva red globe nacional"),
                          (2, "Ajo importado")):
        observed = []
        for reading in (0, 1):
            tables = cached_results[PAGE_IMAGES[page]][reading].get("tables", [])
            cells = [row[1] for table in tables for row in table
                     if len(row) > 1 and row[0] == product]
            _require(len(cells) == 1, f"printed product/presentation row changed for {product}")
            observed.append(cells[0])
        allowed = {"Caja de cartÓn", "Caja de cartón"} if page == 1 else {"Caja de cartÓn"}
        _require(set(observed) <= allowed,
                 f"exact printed presentation variant changed for {product}")
        if page == 1:
            _require(set(observed) == {"Caja de cartÓn", "Caja de cartón"},
                     f"paired presentation correction changed for {product}")
        else:
            _require(observed == ["Caja de cartÓn", "Caja de cartÓn"],
                     f"page-2 printed presentation variant changed for {product}")
    page1_cells = carton_variants[1]
    _require(any("PIÁtano" in cells for cells in page1_cells)
             and any("PlÁtano" in cells for cells in page1_cells),
             "paired OCR plantain-heading variants changed")

    rows = projections.get(CHILD)
    _require(isinstance(rows, list) and len(rows) == 59,
             "exact native paired projection does not contain 59 rows")
    normalized = []
    seen_locators = set()
    for index, (row, manual) in enumerate(zip(rows, oracle["manual_rows"]), 1):
        _require(manual["ordinal"] == index and len(row) == 17,
                 f"manual row ordering/17-field tuple changed at ordinal {index}")
        page = int(manual["page"])
        _require(row[1] == date(2024, 1, 25) and row[4] == "Armenia, Mercar"
                 and row[16] == page and row[0].startswith(f"PDF page {page},"),
                 f"source date/market/page locator changed at ordinal {index}")
        _require(row[3] == manual["product"], f"product differs from manual row {index}")
        manual_category = " > ".join(manual["category_path_manual_display"])
        canonical_category = CANONICAL_CATEGORY_PATHS.get(manual_category, manual_category)
        _require(row[5] == canonical_category,
                 f"category differs from exact parser taxonomy mapping at row {index}")
        expected_presentation = manual["presentation"]
        if index in PRESENTATION_NORMALIZATION_ORDINALS:
            _require(expected_presentation == "Caja de cartón" and row[6] == "Caja de cartÓn"
                     or expected_presentation == row[6] == "Caja de cartón",
                     f"reviewed packaging glyph changed at row {index}")
            expected_presentation = "Caja de cartón"
        _require(row[6] == expected_presentation or
                 (index == 40 and row[6] == "Caja de cartÓn"),
                 f"presentation differs from manual row {index}")
        quantity = Decimal(str(manual["quantity"]))
        minimum = Decimal(str(manual["r1_min_cop"]))
        maximum = Decimal(str(manual["r1_max_cop"]))
        _require(row[7] == quantity and row[8] == manual["source_unit"],
                 f"quantity/source unit differs from manual row {index}")
        _require(row[9] == 1 and row[10] == "Ronda 1 05:00 - 07:00",
                 f"round label differs from manual row {index}")
        _require(row[11:13] == (minimum, maximum)
                 and row[13] == "kg"
                 and row[14] == minimum / quantity
                 and row[15] == maximum / quantity,
                 f"full numeric vector differs from manual row {index}")
        _require(manual["r2_min_cop"] == manual["r2_max_cop"] == 0,
                 f"round-2 zero marker changed at row {index}")
        _require(row[0] not in seen_locators, f"duplicate source locator at row {index}")
        seen_locators.add(row[0])
        if index == 40 and row[6] == "Caja de cartÓn":
            adjusted = list(row)
            adjusted[6] = "Caja de cartón"
            row = tuple(adjusted)
        normalized.append(row)

    _require(len(normalized) == 59 and
             sum(1 for row in normalized if row[16] == 1) == 37 and
             sum(1 for row in normalized if row[16] == 2) == 22,
             "full manual page allocation changed")
    full17 = _row_sha(normalized)
    evidence = {
        "policy_version": ("city-v8:armenia-jan2024-ocr-whole-v1:jan25-paired-review-v1"
                           ":armenia-mercar-manual-59-v1:" + MANUAL_REVIEW_SHA256),
        "source_grid_sha256": _json_sha(oracle["manual_rows"]),
        "full17_sha256": full17,
        "records": 59,
        "provider_result_hashes": {
            "ocr_version": "gemini-image-ocr-v2",
            "ocr_model": "gemini-3.5-flash",
            "manual_review_path": MANUAL_REVIEW_RUNTIME_PATH,
            "manual_review_sha256": MANUAL_REVIEW_SHA256,
            "manifest_sha256": MANIFEST_SHA256,
            "roster_sha256": proof["roster_sha256"],
            "pages": pair_hashes,
            "text_adjudication": proof["text_adjudication"],
        },
        "prior_tasks": prior_tasks,
        "archive_id": source["archive_sha256"],
        "entry_name": ENTRY,
        "evidence_document_id": CHILD,
        "proof_sha256": PROOF_SHA256,
    }
    return evidence, normalized


def record_city_source_adjudication(db, evidence):
    from .jan25_penol_printed_date import record_city_source_adjudication as record
    record(db, evidence)
