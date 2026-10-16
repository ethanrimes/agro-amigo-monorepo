"""Exact-source Peñol printed-date adjudication for the private Jan25 candidate.

The retained ZIP day remains Jan 25. This narrowly attests that this exact
Peñol child measures Jan 23, using the root's pixel transcription, complete
archive/member/image/task bindings, paired cached OCR hashes, and all ten
manual price vectors. It does not alter generic city date validation.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

PROOF_FILE = "jan25_penol_printed_date_proof.json"
PROOF_SHA256 = "bb16f7573f08f3a5c5462bbdad15474d10ae72e1f48086caea19350848009ffc"
MANUAL_REVIEW_SHA256 = "018dda8262928e87a6ca32cb4e11b268a090fef01c62e61319ebbf61aa0aa751"
ROSTER_PAIRS_SHA256 = "70895deb08cf4c04deec1ffc730bb7eef4d002bba402eff78329fa979998d377"


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError("Exact Jan25 Peñol printed-date proof: " + detail)


def _file_sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _proof() -> dict:
    path = Path(__file__).with_name(PROOF_FILE)
    raw = path.read_bytes()
    _require(sha256(raw).hexdigest() == PROOF_SHA256, "private proof file changed")
    proof = json.loads(raw)
    review_path = Path(__file__).parent / "jan25_source_proofs/ROOT_MANUAL_TEN_ROW_DATE_REVIEW_FIRST_A.json"
    _require(_file_sha(review_path) == MANUAL_REVIEW_SHA256
             == proof["review_source"]["sha256"], "root physical transcription changed")
    return proof


def _text_projection(proof: dict, field: str, index: int, value: str) -> str:
    """Apply only reviewed source-specific spelling projections, by row/field."""
    mapping = proof.get("manual_to_projected_text", {}).get(field, {}).get(str(index))
    if mapping is None:
        return value
    _require(mapping["manual"] == value, f"manual {field} text changed at row {index}")
    return mapping["projected"]


def validate_exact_penol(source_url: str, parent_bytes: bytes, archive_day: date,
                         manifest: dict, cached_results: dict, image_to_task: dict,
                         projections: dict) -> dict:
    """Validate every binding and the full manual grid; return pinned evidence."""
    proof = _proof()
    source = proof["source"]
    _require(source_url == source["url"] == manifest["url"], "source URL changed")
    _require(archive_day.isoformat() == source["archive_publication_day"]
             == manifest["parent_publication_date"], "parent archive day changed")
    _require(sha256(parent_bytes).hexdigest() == source["archive_sha256"]
             == manifest["parent_sha256"], "parent ZIP bytes changed")

    roster = [{"entry": row["entry"], "document_id": row["member_did"]}
              for row in manifest["zip_members"]]
    _require(len(roster) == 30 and roster == source["roster"], "30-member roster changed")
    _require(_json_sha(roster) == ROSTER_PAIRS_SHA256, "exact parent roster pairs changed")
    _require(source["manifest_roster_sha256"] == manifest["source_roster_sha256"],
             "parent manifest roster digest changed")

    child = source["member_document_id"]
    entry = source["member_entry"]
    _require(child == manifest["date_mismatch_member"], "target member DID changed")
    child_spec = manifest["children"].get(child)
    _require(child_spec is not None and child_spec["entry"] == entry
             and child_spec["expected_row_count"] == 10, "target entry/row count changed")
    member = [row for row in manifest["zip_members"] if row["member_did"] == child]
    _require(len(member) == 1 and member[0]["entry"] == entry, "target member mapping changed")

    image_id = source["image_document_id"]
    page_spec = manifest["pages"].get(image_id)
    _require(page_spec is not None and page_spec["member_did"] == child
             and page_spec["entry"] == entry and page_spec["page"] == 1
             and page_spec["printed_header"]["dates"] == ["23 de Enero de 2024"]
             and page_spec["printed_header"]["market"] == source["printed_market"],
             "printed page/image binding changed")
    task = image_to_task.get(image_id)
    _require(task is not None, "exact OCR image task is absent")
    task_identity = {
        "document_id": task[0], "source_locator": task[1], "image_id": task[2],
        "source_kind": task[3], "source_page": task[4], "status": task[5], "error": task[6],
    }
    _require(task_identity == source["task"], "OCR task identity/status changed")
    _require((task[7], task[8], task[9], task[10], task[11]) ==
             ("extract", "DANE", source_url, "image/png", "Serie histórica completa"),
             "OCR image source-document identity changed")
    _require(task[12].get("parents") == [child]
             and task[12].get("ingestion_kind") == "ocr-image"
             and task[12].get("retention") == "permanent"
             and task[12].get("archive_entry") == "rendered-source.png",
             "OCR image parent/retention metadata changed")
    _require(task[12] == source["image_metadata"], "OCR image metadata changed")
    image_bytes = bytes(task[13])
    _require(len(image_bytes) == source["image_bytes"]
             and sha256(image_bytes).hexdigest() == image_id == source["image_bytes_sha256"],
             "rendered OCR image bytes changed")

    pair = cached_results.get(image_id)
    _require(isinstance(pair, dict) and set(pair) == {0, 1}, "paired OCR readings absent")
    _require(page_spec["ocr_version"] == source["ocr_version"], "OCR version changed")
    pair_hashes = {str(reading): _json_sha(result) for reading, result in pair.items()}
    _require(pair_hashes == source["reading_sha256"] == page_spec["reading_sha256"],
             "either cached OCR payload changed")
    _require(all(result.get("version") == source["ocr_version"]
                 and result.get("model") == "gemini-3.5-flash" for result in pair.values()),
             "cached OCR model/version changed")
    for field, mappings in proof["manual_to_projected_text"].items():
        for row_index, mapping in mappings.items():
            variants = mapping.get("source_ocr_variants")
            if variants is not None:
                _require(len(variants) == 2, f"source OCR variant pair changed for {field} row {row_index}")
                for reading, literal in enumerate(variants):
                    cells = [cell for table in pair[reading].get("tables", [])
                             for row in table for cell in row]
                    _require(literal in cells,
                             f"source OCR literal changed for {field} row {row_index} reading {reading}")

    rows = projections.get(child)
    _require(isinstance(rows, list) and len(rows) == 10, "projected Peñol row set changed")
    _require(_json_sha([[str(v) for v in row] for row in rows])
             == source["normalized_projection_rows_sha256"]
             == child_spec["expected_rows_sha256"], "paired 17-field projection changed")
    manual_rows = proof["manual_rows"]
    _require(len(manual_rows) == len(rows) == 10, "manual row count changed")
    for index, (row, manual) in enumerate(zip(rows, manual_rows)):
        expected_date = date.fromisoformat(source["printed_measurement_day"])
        _require(row[1] == expected_date, f"measurement date changed at row {index}")
        _require(row[4] == source["printed_market"], f"market changed at row {index}")
        product = _text_projection(proof, "product", index, manual["product"])
        _require(row[3] == product, f"product changed at row {index}")
        category = _text_projection(proof, "literal_category_path", index,
                                    " > ".join(manual["literal_category_path"]))
        _require(row[5] == category, f"category path changed at row {index}")
        presentation = _text_projection(proof, "presentation", index, manual["presentation"])
        _require(row[6] == presentation, f"presentation changed at row {index}")
        quantity = Decimal(str(manual["quantity"]))
        minimum, maximum = Decimal(str(manual["round1_min_COP"])), Decimal(str(manual["round1_max_COP"]))
        _require(row[7] == quantity and row[8] == manual["unit"], f"quantity/unit changed at row {index}")
        round_projection = proof["manual_round_time_to_projection"]
        _require(round_projection["manual"] == proof["round1_time"]
                 and row[9] == 1 and row[10] == round_projection["projected"],
                 f"round label/time changed at row {index}")
        _require(row[11:13] == (minimum, maximum), f"literal price vector changed at row {index}")
        _require(row[13] == "kg" and row[14] == minimum / quantity and row[15] == maximum / quantity,
                 f"unit-normalized price vector changed at row {index}")
        _require(row[16] == 1, f"PDF page locator changed at row {index}")
        allowed_locators = page_spec["locator_aliases"].get(str(index), [])
        _require(row[0] in allowed_locators, f"source row locator changed at row {index}")
        _require(manual["round2_min"] == manual["round2_max"] == 0,
                 f"manual round-2 cells changed at row {index}")

    return {
        "policy_version": "city-v8:armenia-jan2024-ocr-whole-v1:jan25-paired-review-v1"
        ":penol-printed-date-2024-01-23:" + PROOF_SHA256,
        "source_grid_sha256": _json_sha(manual_rows),
        "full17_sha256": source["normalized_projection_rows_sha256"],
        "records": 10,
        "provider_result_hashes": {
            "ocr_version": source["ocr_version"],
            "reading_0": pair_hashes["0"], "reading_1": pair_hashes["1"],
        },
        "prior_tasks": [source["task"]],
        "archive_id": source["archive_sha256"],
        "entry_name": entry,
        "evidence_document_id": child,
        "proof_sha256": PROOF_SHA256,
    }


def record_city_source_adjudication(db, evidence: dict) -> None:
    """Append the exact proof to the existing immutable source-review table."""
    from psycopg.types.json import Jsonb

    db.execute("""INSERT INTO city_source_adjudication
      (document_id,policy_version,archive_id,entry_name,evidence_document_id,
       source_grid_sha256,full17_sha256,provider_result_hashes,prior_tasks,records)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
      (evidence["evidence_document_id"], evidence["policy_version"], evidence["archive_id"],
       evidence["entry_name"], evidence["evidence_document_id"],
       evidence["source_grid_sha256"], evidence["full17_sha256"],
       Jsonb(evidence["provider_result_hashes"]), Jsonb(evidence["prior_tasks"]),
       evidence["records"]))
    stored = db.execute("""SELECT archive_id,entry_name,evidence_document_id,source_grid_sha256,
      full17_sha256,provider_result_hashes,prior_tasks,records
      FROM city_source_adjudication WHERE document_id=%s AND policy_version=%s""",
      (evidence["evidence_document_id"], evidence["policy_version"])).fetchone()
    expected = (evidence["archive_id"], evidence["entry_name"], evidence["evidence_document_id"],
                evidence["source_grid_sha256"], evidence["full17_sha256"],
                evidence["provider_result_hashes"], evidence["prior_tasks"], evidence["records"])
    _require(stored == expected, "append-only source-date adjudication row changed")
