"""Portable source-bound pure tests for the two reviewed Jan25 OCR exceptions.

Fixtures are only the exact DANE ZIP, retained source page images, paired OCR
payloads, and the two manual source proofs shipped with the runtime. These
cases do not depend on a private QA export, repository metadata, or PostgreSQL.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import unittest
import zipfile

from . import city_jan25_ocr_whole as whole
from . import jan25_armenia_mercar_review as armenia
from . import jan25_penol_printed_date as penol
from . import worker

DATA = Path(__file__).parent / "testdata" / "city_armenia_20240125_ocr"
PARENT = DATA / f"{whole.PARENT}.zip"
PAIRED_READINGS = DATA / "cached_paired_readings.json"
ARMENIA_CHILD = armenia.CHILD
ARMENIA_IMAGES = armenia.PAGE_IMAGES
PENOL_CHILD = "922666201d68c3b53db5da45d6c489c1a2c930223891351acf2d616b2ddd7c87"
PENOL_IMAGE = "03c81e52b0b3c234c49548de93fa97d6d0ca08e8ba8109cd77a6bab4f5dfa252"


def _json_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _readings():
    readings = {}
    for image_id, version, reading, result, *_ in json.loads(PAIRED_READINGS.read_text()):
        if version == whole.OCR_VERSION:
            readings.setdefault(image_id, {})[reading] = result
    return readings


def _armenia_inputs():
    manifest = whole._manifest_bytes()
    parent_bytes = PARENT.read_bytes()
    cached = _readings()
    tasks = {}
    for page, image_id in ARMENIA_IMAGES.items():
        spec = manifest["pages"][image_id]
        image_bytes = (DATA / f"{image_id}.png").read_bytes()
        metadata = {
            "ingestion_kind": "ocr-image", "retention": "permanent",
            "parents": [ARMENIA_CHILD], "original_filename": "rendered-source.png",
            "archive_entry": "rendered-source.png",
        }
        tasks[image_id] = (
            ARMENIA_CHILD, f"PDF page {page}", image_id, "city-pdf", page,
            spec["task_status"], spec["task_error"], "extract", "DANE", whole.URL,
            "image/png", "Serie histórica completa", metadata, image_bytes,
        )
    projections = whole.project_source(parent_bytes, cached, manifest)
    return parent_bytes, manifest, cached, tasks, projections


def _penol_inputs():
    manifest = whole._manifest_bytes()
    parent_bytes = PARENT.read_bytes()
    proof_path = Path(penol.__file__).with_name(penol.PROOF_FILE)
    source = json.loads(proof_path.read_text())["source"]
    image_bytes = (DATA / f"{PENOL_IMAGE}.png").read_bytes()
    image_id = source["image_document_id"]
    task_spec = source["task"]
    metadata = source["image_metadata"]
    task = (
        task_spec["document_id"], task_spec["source_locator"], image_id,
        task_spec["source_kind"], task_spec["source_page"], task_spec["status"],
        task_spec["error"], "extract", "DANE", whole.URL, "image/png",
        "Serie histórica completa", metadata, image_bytes,
    )
    cached = {image_id: _readings()[image_id]}
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as archive:
        pdf = archive.read(source["member_entry"])
    rows = whole._parse_member_pair(pdf, source["member_entry"], {1: image_id}, cached, manifest)
    return parent_bytes, manifest, cached, {image_id: task}, {PENOL_CHILD: rows}


class Jan25SourceProofTests(unittest.TestCase):
    def test_armenia_all_59_manual_vectors_and_packaged_release_closure(self):
        parent_bytes, manifest, cached, tasks, projections = _armenia_inputs()
        evidence, rows = armenia.validate_exact_armenia_mercar(
            whole.URL, parent_bytes, whole.DAY, manifest, cached, tasks, projections)
        self.assertEqual((evidence["records"], len(rows)), (59, 59))
        self.assertEqual(sum(row[16] == 1 for row in rows), 37)
        self.assertEqual(sum(row[16] == 2 for row in rows), 22)
        self.assertEqual(rows[39][3], "Ajo importado")
        self.assertEqual(rows[39][6], "Caja de cartón")
        self.assertEqual(rows[39][11:13], (Decimal("95000"), Decimal("95000")))
        self.assertEqual(len(evidence["prior_tasks"]), 2)
        self.assertEqual([row["status"] for row in evidence["prior_tasks"]], ["review", "review"])

        runtime_root = Path(whole.__file__).parent
        self.assertEqual(worker.ROOT, runtime_root.parents[1])
        expected_members = {
            "pipelines/ingestion/jan25_armenia_mercar_review.py",
            "pipelines/ingestion/jan25_armenia_mercar_review_proof.json",
            "pipelines/ingestion/jan25_penol_printed_date.py",
            "pipelines/ingestion/jan25_penol_printed_date_proof.json",
            "pipelines/ingestion/jan25_source_proofs/ROOT_MANUAL_59_ROW_REVIEW_FIRST_A.json",
            "pipelines/ingestion/jan25_source_proofs/ROOT_MANUAL_TEN_ROW_DATE_REVIEW_FIRST_A.json",
        }
        self.assertTrue(expected_members <= set(worker.RELEASE_FILES))
        self.assertTrue(all((worker.ROOT / name).is_file() for name in expected_members))
        armenia._load_proof()
        penol._proof()

    def test_armenia_source_url_parent_day_roster_task_and_reading_bindings(self):
        parent_bytes, manifest, cached, tasks, projections = _armenia_inputs()
        validate = lambda **changes: armenia.validate_exact_armenia_mercar(
            changes.get("url", whole.URL), changes.get("parent", parent_bytes),
            changes.get("day", whole.DAY), changes.get("manifest", manifest),
            changes.get("cached", cached), changes.get("tasks", tasks),
            changes.get("projections", projections))
        with self.assertRaisesRegex(ValueError, "source URL"):
            validate(url=whole.URL + "?other")
        with self.assertRaisesRegex(ValueError, "parent ZIP bytes"):
            validate(parent=parent_bytes[:-1] + bytes([parent_bytes[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "archive publication day"):
            validate(day=date(2024, 1, 24))
        changed_manifest = deepcopy(manifest)
        changed_manifest["zip_members"][0]["entry"] += ".wrong"
        with self.assertRaisesRegex(ValueError, "member names/DIDs"):
            validate(manifest=changed_manifest)
        changed_tasks = deepcopy(tasks)
        row = list(changed_tasks[ARMENIA_IMAGES[2]])
        row[0] = "0" * 64
        changed_tasks[ARMENIA_IMAGES[2]] = tuple(row)
        with self.assertRaisesRegex(ValueError, "task identity/status"):
            validate(tasks=changed_tasks)
        changed_readings = deepcopy(cached)
        changed_readings[ARMENIA_IMAGES[1]][1]["text"] += " changed"
        with self.assertRaisesRegex(ValueError, "raw payload changed"):
            validate(cached=changed_readings)

    def test_armenia_manual_numeric_dimensions_category_and_round_are_exact(self):
        parent_bytes, manifest, cached, tasks, projections = _armenia_inputs()
        for row_index, field_index, value in (
            (0, 1, date(2024, 1, 24)), (1, 7, Decimal("2")),
            (2, 8, "Gramo"), (3, 11, Decimal("1101")),
            (4, 12, Decimal("1235")), (39, 6, "Caja de madera"),
            (40, 5, "Frutas > Otras frutas"), (58, 16, 1),
        ):
            changed = deepcopy(projections)
            row = list(changed[ARMENIA_CHILD][row_index])
            row[field_index] = value
            changed[ARMENIA_CHILD][row_index] = tuple(row)
            with self.subTest(row=row_index + 1, field=field_index):
                with self.assertRaises(ValueError):
                    armenia.validate_exact_armenia_mercar(
                        whole.URL, parent_bytes, whole.DAY, manifest, cached, tasks, changed)

    def test_penol_exact_printed_jan23_grid_is_attested_separately_from_jan25_zip(self):
        parent_bytes, manifest, cached, tasks, projections = _penol_inputs()
        evidence = penol.validate_exact_penol(
            whole.URL, parent_bytes, whole.DAY, manifest, cached, tasks, projections)
        self.assertEqual(evidence["records"], 10)
        self.assertEqual(evidence["archive_id"], whole.PARENT)
        self.assertEqual(evidence["entry_name"], "Peñol, 25-1-2024.pdf")
        self.assertIn("2024-01-23", evidence["policy_version"])
        self.assertEqual(hashlib.sha256(tasks[PENOL_IMAGE][13]).hexdigest(), PENOL_IMAGE)

    def test_penol_wrong_url_parent_archive_day_or_member_roster_rejects(self):
        parent_bytes, manifest, cached, tasks, projections = _penol_inputs()
        validate = lambda **changes: penol.validate_exact_penol(
            changes.get("url", whole.URL), changes.get("parent", parent_bytes),
            changes.get("day", whole.DAY), changes.get("manifest", manifest),
            changes.get("cached", cached), changes.get("tasks", tasks),
            changes.get("projections", projections))
        with self.assertRaisesRegex(ValueError, "source URL"):
            validate(url=whole.URL + "?different")
        with self.assertRaisesRegex(ValueError, "parent ZIP bytes"):
            validate(parent=parent_bytes[:-1] + bytes([parent_bytes[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "parent archive day"):
            validate(day=date(2024, 1, 23))
        changed = deepcopy(manifest)
        changed["zip_members"][0]["entry"] += ".changed"
        with self.assertRaisesRegex(ValueError, "roster"):
            validate(manifest=changed)

    def test_penol_exact_member_page_image_and_task_are_required(self):
        parent_bytes, manifest, cached, tasks, projections = _penol_inputs()
        changed_tasks = deepcopy(tasks)
        row = list(changed_tasks[PENOL_IMAGE])
        row[1] = "PDF page 2"
        changed_tasks[PENOL_IMAGE] = tuple(row)
        with self.assertRaisesRegex(ValueError, "OCR task identity/status"):
            penol.validate_exact_penol(whole.URL, parent_bytes, whole.DAY, manifest,
                                       cached, changed_tasks, projections)
        changed_tasks = deepcopy(tasks)
        row = list(changed_tasks[PENOL_IMAGE])
        row[13] = bytes(row[13]) + b"x"
        changed_tasks[PENOL_IMAGE] = tuple(row)
        with self.assertRaisesRegex(ValueError, "rendered OCR image bytes changed"):
            penol.validate_exact_penol(whole.URL, parent_bytes, whole.DAY, manifest,
                                       cached, changed_tasks, projections)

    def test_penol_both_cached_readings_are_exact_and_required(self):
        parent_bytes, manifest, cached, tasks, projections = _penol_inputs()
        missing = deepcopy(cached)
        del missing[PENOL_IMAGE][1]
        with self.assertRaisesRegex(ValueError, "paired OCR readings absent"):
            penol.validate_exact_penol(whole.URL, parent_bytes, whole.DAY, manifest,
                                       missing, tasks, projections)
        altered = deepcopy(cached)
        altered[PENOL_IMAGE][0]["text"] += " extra"
        with self.assertRaisesRegex(ValueError, "either cached OCR payload changed"):
            penol.validate_exact_penol(whole.URL, parent_bytes, whole.DAY, manifest,
                                       altered, tasks, projections)

    def test_penol_all_manual_fields_reject_projection_drift(self):
        parent_bytes, manifest, cached, tasks, projections = _penol_inputs()
        for row_index, field, value in (
            (0, 1, date(2024, 1, 25)), (1, 4, "Neiva (Huila)"),
            (2, 6, "Kilogramo alterno"), (3, 7, Decimal("14")),
            (4, 8, "Gramo"), (5, 11, Decimal("2201")),
            (6, 5, "Frutas > Leguminosas"), (7, 10, "Ronda 2"),
            (8, 14, Decimal("3201")), (9, 16, 2),
        ):
            changed = deepcopy(projections)
            row = list(changed[PENOL_CHILD][row_index])
            row[field] = value
            changed[PENOL_CHILD][row_index] = tuple(row)
            with self.subTest(row=row_index, field=field):
                with self.assertRaises(ValueError):
                    penol.validate_exact_penol(whole.URL, parent_bytes, whole.DAY,
                                                manifest, cached, tasks, changed)


if __name__ == "__main__":
    unittest.main()
