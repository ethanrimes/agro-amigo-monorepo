"""Source-bound, append-only city category overlay eligibility.

The caller holds the child publication transaction. Native PDF, retained
originals, immutable raw rows and classifications must agree as a whole.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pdfplumber

from . import city_discovery, city_reports
from .worker import clean, slug

FIELDS = (
    "source_locator",
    "observed_on",
    "product_id",
    "product_name",
    "market_name",
    "category",
    "presentation",
    "quantity",
    "source_unit",
    "round",
    "round_label",
    "min_price",
    "max_price",
    "unit",
    "min_unit_price",
    "max_unit_price",
    "source_page",
)
PARSER_VERSION = "city-v8"
PROOF_ID_FIELDS = (
    "parent_sha256",
    "entry_name",
    "requested_entry_name",
    "source_sha256",
    "source_url",
    "parser_version",
    "parser_code_sha256",
    "raw_row_count",
    "correction_count",
    "locator_set_sha256",
    "db_locator_set_sha256",
    "db_classification_sha256",
    "unchanged_fields_sha256",
    "native_rows_sha256",
    "stored_rows_sha256",
)
MAIN_GROUPS = {
    "frutas",
    "tuberculos-raices-y-platanos",
    "verduras-y-hortalizas",
    "procesados",
    "granos-y-cereales",
    "lacteos-y-huevos",
    "pescados",
    "carnes",
}
NOV2021_SOURCE_IDS = frozenset({
    "1d8258d2fa8f22a4c7bee56e03513fa6fc80e81f7c3149caa896c89deeebfcae",
    "7872936c55b88d539388b2f27865f5866dedb97a362f2223095629d811e3930c",
    "b262c47141d6b44d1e37b0a526405f79374ce017999fe1f36facd818d7816c57",
    "4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078",
    "298f734fe2b12f4ed4ee8c9cc35541916a30d76926a36c22e83dcbf377d16c0c",
})
LOCATOR = re.compile(r"^PDF page (\d+),table (\d+),row (\d+),round ([12])$")


class Ineligible(ValueError):
    """The exact retained source does not support an automatic overlay."""


def digest(value: Any) -> str:
    def encode(item: Any):
        if isinstance(item, Decimal):
            return format(item, "f")
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError(type(item).__name__)

    body = json.dumps(
        value, default=encode, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def framed_digest(values: list[str]) -> str:
    """SQL-recomputable digest: character length before every UTF-8 value."""
    body = "".join(f"{len(value)}:{value}" for value in values)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def literal_heading_by_locator(
    child_pdf: bytes, native_rows: list[tuple], target_locators: set[str] | None = None
) -> dict[str, dict]:
    """Walk the *same* PDF table geometry and pin each row's literal heading.

    This extracts no price values. A row without exactly one parent/child
    heading on its page is ineligible for the capitalization exception.
    """
    targets = (
        {row[0] for row in native_rows} if target_locators is None else target_locators
    )
    found: dict[str, dict] = {}
    source_scoped_top_level = hashlib.sha256(child_pdf).hexdigest() in NOV2021_SOURCE_IDS
    with pdfplumber.open(io.BytesIO(child_pdf)) as pdf:
        # The publisher may continue a parent group on the next physical page.
        # Match parse_city_pages' state across pages, including page 2 Tomates.
        group = ""
        leaf = ""
        for page_no, page in enumerate(pdf.pages, 1):
            for table_no, table in enumerate(city_reports._city_tables(page), 1):
                headers = next(
                    (
                        i
                        for i, row in enumerate(table)
                        if len(row) >= 7
                        and clean(row[0]) == "Producto"
                        and clean(row[1]) == "Presentación"
                    ),
                    None,
                )
                if headers is None:
                    continue
                for row_no, row in enumerate(table[headers + 2 :], headers + 3):
                    if len(row) < 7:
                        continue
                    name, presentation, units = map(clean, row[:3])
                    if not presentation and not units:
                        unavailable = ("", "0", "-", "n.d.")
                        group_row = (
                            source_scoped_top_level
                            and name and slug(name) in (MAIN_GROUPS | {
                                "huevos",
                                "tuberculos-raices-platanos",
                                "verduras-y-hortailizas",
                            })
                            and all(clean(value) in unavailable for value in row[3:7])
                        )
                        if name and (sum(bool(clean(v)) for v in row) == 1 or group_row):
                            if slug(name) in MAIN_GROUPS or (
                                source_scoped_top_level
                                and slug(name) in {
                                    "huevos",
                                    "tuberculos-raices-platanos",
                                    "verduras-y-hortailizas",
                                }
                            ):
                                group, leaf = name, ""
                            elif not name.startswith(("*", "Fuente", "Nota")):
                                leaf = name
                        continue
                    for rnd in (1, 2):
                        locator = f"PDF page {page_no},table {table_no},row {row_no},round {rnd}"
                        if locator not in targets:
                            continue
                        if (
                            locator in found
                            or not group
                            or (not leaf and not source_scoped_top_level)
                        ):
                            raise Ineligible(
                                f"Missing/ambiguous literal heading at {locator}"
                            )
                        found[locator] = {
                            "parent_literal": group,
                            "leaf_literal": leaf,
                            "page": page_no,
                            "table": table_no,
                            "row": row_no,
                        }
    if set(found) != targets:
        raise Ineligible(
            "Literal-heading locator set differs from native price locator set"
        )
    return found


def plan(
    *,
    parent_zip: bytes,
    archive_id: str,
    entry_name: str,
    child_pdf: bytes,
    document_id: str,
    source_url: str,
    original_metadata: dict,
    native_rows: list[tuple],
    stored_rows: list[dict],
    classifications: dict[str, list[str]],
    product_corrections: dict[str, dict],
    existing_conflicts: int,
    parser_code_sha256: str,
) -> dict:
    """Return proposed exact-locator overlays, or fail closed with no changes.

    Product corrections are preexisting audited rows containing old/new ID and
    name. They are recognized solely for those two identity fields. All other
    typed fields, all locators, and all classification paths must match.
    """
    actual_parser_sha256 = hashlib.sha256(
        Path(city_reports.__file__).read_bytes()
    ).hexdigest()
    if (
        city_reports.VERSION != PARSER_VERSION
        or parser_code_sha256 != actual_parser_sha256
    ):
        raise Ineligible("Parser version/code fingerprint is not pinned")
    if existing_conflicts:
        raise Ineligible("Existing publication conflicts have no automatic resolution")
    if hashlib.sha256(parent_zip).hexdigest() != archive_id:
        raise Ineligible("Parent ZIP bytes differ from source ID")
    if hashlib.sha256(child_pdf).hexdigest() != document_id:
        raise Ineligible("Child PDF bytes differ from source ID")
    if (
        original_metadata.get("kind") != "original"
        or original_metadata.get("source_url") != source_url
    ):
        raise Ineligible("Child original source URL/kind differs")
    metadata = original_metadata.get("metadata") or {}
    primary_entry = metadata.get("archive_entry")
    if not primary_entry or archive_id not in metadata.get("parents", []):
        raise Ineligible("Child original does not identify this ZIP member")
    try:
        with zipfile.ZipFile(io.BytesIO(parent_zip)) as archive:
            for name in {primary_entry, entry_name}:
                members = [info for info in archive.infolist() if info.filename == name]
                # Two distinct member names may bind the same retained child,
                # and one name may repeat. All physical occurrences of both
                # names must validate to the same bytes and CRC. The first
                # metadata entry is never inferred from a later alias.
                if not members or any(
                    archive.read(info) != child_pdf for info in members
                ):
                    raise Ineligible("ZIP member bytes/CRC or membership differs")
    except (zipfile.BadZipFile, EOFError, RuntimeError) as exc:
        raise Ineligible("ZIP is not structurally verified") from exc
    try:
        actual_native_rows = list(
            city_reports.parse_city_pdf(
                child_pdf, city_discovery.archive_day(source_url)
            )
        )
    except (ValueError, EOFError) as exc:
        raise Ineligible(
            "Retained child cannot be parsed by the pinned native parser"
        ) from exc
    if actual_native_rows != native_rows:
        raise Ineligible(
            "Supplied native rows differ from the exact retained child parse"
        )
    native = {row[0]: dict(zip(FIELDS, row, strict=True)) for row in native_rows}
    raw = {row["source_locator"]: row for row in stored_rows}
    if (
        len(native) != len(native_rows)
        or len(raw) != len(stored_rows)
        or not native
        or set(native) != set(raw)
        or set(native) != set(classifications)
    ):
        raise Ineligible(
            "Whole-document locator sets are absent, duplicate, or unequal"
        )
    if set(product_corrections) - set(native):
        raise Ineligible("Product correction refers to an absent native locator")
    proposals = []
    unchanged = []
    mismatches: list[str] = []
    for locator in sorted(native):
        new, old = native[locator], raw[locator]
        match = LOCATOR.fullmatch(locator)
        if not match or int(match[1]) != new["source_page"]:
            raise Ineligible(f"PDF page/locator mismatch: {locator}")
        native_path = new["category"].split(" > ")
        if classifications[locator] != native_path:
            top_level_repair = (
                document_id in NOV2021_SOURCE_IDS
                and len(native_path) == 1
                and classifications[locator] == old["category"].split(" > ")
                and old["category"] != new["category"]
            )
            if not top_level_repair:
                raise Ineligible(f"Classification path differs from native PDF: {locator}")
        correction = product_corrections.get(locator)
        for field in FIELDS:
            if field == "category":
                continue
            expected = old[field]
            if field in ("product_id", "product_name") and correction:
                if old[field] != correction["old_" + field]:
                    raise Ineligible(
                        f"Product correction old identity differs: {locator}"
                    )
                expected = correction["corrected_" + field]
            if expected != new[field]:
                raise Ineligible(f"Non-category typed field {field} differs: {locator}")
        unchanged.append((locator, {k: new[k] for k in FIELDS if k != "category"}))
        if old["category"] != new["category"]:
            mismatches.append(locator)
    # Exact full-category rows, including a parent-only category, are already
    # correct and require neither an overlay nor a printed child-heading rule.
    heading = (
        literal_heading_by_locator(child_pdf, native_rows, set(mismatches))
        if mismatches
        else {}
    )
    for locator in mismatches:
        new, old = native[locator], raw[locator]
        native_path = new["category"].split(" > ")
        if len(native_path) == 1:
            printed_group = heading[locator]["parent_literal"]
            if clean(printed_group).capitalize() != native_path[0]:
                raise Ineligible(f"Printed top-level group differs: {locator}")
            rule = "literal-top-level-heading"
            literal_heading = printed_group
        else:
            if clean(heading[locator]["parent_literal"]).capitalize() != native_path[0]:
                raise Ineligible(f"Printed parent differs: {locator}")
            printed_leaf = heading[locator]["leaf_literal"]
            if clean(printed_leaf).capitalize() != native_path[-1]:
                raise Ineligible(f"Printed child differs: {locator}")
            old_leaf, native_leaf = old["category"], native_path[-1]
            if old_leaf == native_leaf:
                rule = "literal-leaf"
            elif old_leaf == printed_leaf and clean(old_leaf).capitalize() == native_leaf:
                rule = "verified-printed-leaf-capitalize"
            else:
                raise Ineligible(f"Raw leaf is not the printed/native leaf: {locator}")
            literal_heading = printed_leaf
        proposals.append(
            {
                "document_id": document_id,
                "source_locator": locator,
                "old_category": old["category"],
                "corrected_category": new["category"],
                "category_path": native_path,
                "literal_heading": literal_heading,
                "source_page": new["source_page"],
                "rule": rule,
                "parser_version": PARSER_VERSION,
                "parser_code_sha256": parser_code_sha256,
            }
        )
    proof = {
        "source_sha256": document_id,
        "parent_sha256": archive_id,
        "source_url": source_url,
        "entry_name": primary_entry,
        "requested_entry_name": entry_name,
        "locator_set_sha256": digest(sorted(native)),
        "db_locator_set_sha256": framed_digest(sorted(native)),
        "db_classification_sha256": framed_digest(
            [
                value
                for locator in sorted(native)
                for value in (locator, " > ".join(classifications[locator]))
            ]
        ),
        "unchanged_fields_sha256": digest(unchanged),
        "native_rows_sha256": digest([(loc, native[loc]) for loc in sorted(native)]),
        "stored_rows_sha256": digest([(loc, raw[loc]) for loc in sorted(raw)]),
        "raw_row_count": len(raw),
        "correction_count": len(proposals),
        "parser_version": PARSER_VERSION,
        "parser_code_sha256": parser_code_sha256,
    }
    proof["proof_id"] = framed_digest([str(proof[field]) for field in PROOF_ID_FIELDS])
    return {"proof": proof, "rows": proposals}


OVERLAY_COLUMNS = (
    "document_id",
    "source_locator",
    "old_category",
    "corrected_category",
    "category_path",
    "literal_heading",
    "heading_rule",
    "source_page",
    "source_sha256",
    "source_url",
    "unchanged_fields_sha256",
    "locator_set_sha256",
    "native_rows_sha256",
    "old_rows_sha256",
)
PROOF_COLUMNS = (
    "document_id",
    "proof_id",
    "archive_id",
    "entry_name",
    "requested_entry_name",
    "source_sha256",
    "source_url",
    "parser_version",
    "parser_code_sha256",
    "raw_row_count",
    "correction_count",
    "locator_set_sha256",
    "db_locator_set_sha256",
    "db_classification_sha256",
    "unchanged_fields_sha256",
    "native_rows_sha256",
    "old_rows_sha256",
    "verification",
)


def _overlay_values(row: dict, proof: dict) -> tuple:
    return (
        row["document_id"],
        row["source_locator"],
        row["old_category"],
        row["corrected_category"],
        row["category_path"],
        row["literal_heading"],
        row["rule"],
        row["source_page"],
        proof["source_sha256"],
        proof["source_url"],
        proof["unchanged_fields_sha256"],
        proof["locator_set_sha256"],
        proof["native_rows_sha256"],
        proof["stored_rows_sha256"],
    )


def _proof_values(proof: dict) -> tuple:
    return (
        proof["source_sha256"],
        proof["proof_id"],
        proof["parent_sha256"],
        proof["entry_name"],
        proof["requested_entry_name"],
        proof["source_sha256"],
        proof["source_url"],
        proof["parser_version"],
        proof["parser_code_sha256"],
        proof["raw_row_count"],
        proof["correction_count"],
        proof["locator_set_sha256"],
        proof["db_locator_set_sha256"],
        proof["db_classification_sha256"],
        proof["unchanged_fields_sha256"],
        proof["native_rows_sha256"],
        proof["stored_rows_sha256"],
        {"method": "retained-city-pdf-whole-source-category-only"},
    )


def _stored_plan_rows(db, document_id: str) -> tuple[list[dict], dict, dict, int]:
    raw = [
        dict(zip(FIELDS, values, strict=True))
        for values in db.execute(
            f"SELECT {','.join(FIELDS)} FROM regional_price "
            "WHERE document_id=%s ORDER BY source_locator",
            (document_id,),
        ).fetchall()
    ]
    classifications = dict(
        db.execute(
            "SELECT source_locator,category_path FROM regional_classification "
            "WHERE document_id=%s ORDER BY source_locator",
            (document_id,),
        ).fetchall()
    )
    corrections = {
        locator: dict(
            zip(
                (
                    "old_product_id",
                    "old_product_name",
                    "corrected_product_id",
                    "corrected_product_name",
                ),
                values,
                strict=True,
            )
        )
        for locator, *values in db.execute(
            "SELECT source_locator,old_product_id,old_product_name,"
            "corrected_product_id,corrected_product_name "
            "FROM regional_price_product_correction WHERE document_id=%s",
            (document_id,),
        ).fetchall()
    }
    conflict = db.execute(
        "SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s",
        (document_id,),
    ).fetchone()[0]
    return raw, classifications, corrections, conflict


def _validate_saved_plan(db, proposal: dict) -> bool:
    """Check every immutable proof/overlay field, including parser revision.

    Returns whether this exact parser attestation already exists. A previous
    parser's complete attestation may coexist, but its category rows must be
    exactly the same source-bound mapping before adding this revision.
    """
    proof = proposal["proof"]
    did = proof["source_sha256"]
    current = db.execute(
        f"SELECT {','.join(PROOF_COLUMNS)} FROM city_category_overlay_proof "
        "WHERE document_id=%s AND proof_id=%s",
        (did, proof["proof_id"]),
    ).fetchone()
    if current is not None and current != _proof_values(proof):
        raise Ineligible(
            "Existing parser attestation differs from the full current plan"
        )
    all_overlays = db.execute(
        f"SELECT {','.join(OVERLAY_COLUMNS)} FROM regional_price_category_overlay "
        "WHERE document_id=%s ORDER BY source_locator COLLATE \"C\"",
        (did,),
    ).fetchall()
    expected = sorted(
        (_overlay_values(row, proof) for row in proposal["rows"]),
        key=lambda row: row[1],
    )
    if all_overlays and all_overlays != expected:
        raise Ineligible(
            "Existing category overlays differ from current exact source plan"
        )
    if current is not None and not all_overlays:
        raise Ineligible("A finalized category proof has no overlay rows")
    return current is not None


def apply_category_overlay(
    db,
    *,
    parent_zip: bytes,
    archive_id: str,
    entry_name: str,
    child_pdf: bytes,
    document_id: str,
    source_url: str,
    native_rows: list[tuple],
) -> dict | None:
    """Attest a complete old-PDF category-only repair in the caller transaction.

    The child advisory lock is taken reentrantly, matching city_reports'
    publication lock. Never commits. Empty/new raw rows return None; partial,
    OCR-derived, conflicting, or changed rows fail closed without a proof.
    """
    from psycopg.pq import TransactionStatus
    from psycopg.types.json import Jsonb

    if db.info.transaction_status == TransactionStatus.IDLE:
        raise RuntimeError("City category overlay requires a publication transaction")
    db.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended('city-pdf-publication:' || %s,0))",
        (document_id,),
    )
    raw, classifications, corrections, conflicts = _stored_plan_rows(db, document_id)
    if not raw:
        return None
    parent = db.execute(
        "SELECT kind,media_type,source_url,content FROM source_document WHERE id=%s",
        (archive_id,),
    ).fetchone()
    child = db.execute(
        "SELECT kind,media_type,source_url,metadata,content "
        "FROM source_document WHERE id=%s",
        (document_id,),
    ).fetchone()
    member = db.execute(
        "SELECT document_id FROM source_archive_member "
        "WHERE archive_id=%s AND entry_name=%s",
        (archive_id, entry_name),
    ).fetchone()
    if (
        parent is None
        or child is None
        or member != (document_id,)
        or parent[:3] != ("original", "application/zip", source_url)
        or child[:3] != ("original", "application/pdf", source_url)
        or bytes(parent[3]) != parent_zip
        or bytes(child[4]) != child_pdf
    ):
        raise Ineligible("Retained original/parent/member differs from supplied bytes")
    primary_entry = (
        child[3].get("archive_entry") if isinstance(child[3], dict) else None
    )
    primary_member = (
        db.execute(
            "SELECT document_id FROM source_archive_member "
            "WHERE archive_id=%s AND entry_name=%s",
            (archive_id, primary_entry),
        ).fetchone()
        if primary_entry
        else None
    )
    if primary_member != (document_id,):
        raise Ineligible("Child metadata primary ZIP member is not bound to this child")
    proposed = plan(
        parent_zip=parent_zip,
        archive_id=archive_id,
        entry_name=entry_name,
        child_pdf=child_pdf,
        document_id=document_id,
        source_url=source_url,
        original_metadata={
            "kind": child[0],
            "source_url": child[2],
            "metadata": child[3],
        },
        native_rows=native_rows,
        stored_rows=raw,
        classifications=classifications,
        product_corrections=corrections,
        existing_conflicts=conflicts,
        parser_code_sha256=hashlib.sha256(
            Path(city_reports.__file__).read_bytes()
        ).hexdigest(),
    )
    if not proposed["rows"]:
        return None
    existing_exact = _validate_saved_plan(db, proposed)
    if existing_exact:
        return proposed
    did = proposed["proof"]["source_sha256"]
    prior_count = db.execute(
        "SELECT count(*) FROM city_category_overlay_proof WHERE document_id=%s",
        (did,),
    ).fetchone()[0]
    overlay_count = db.execute(
        "SELECT count(*) FROM regional_price_category_overlay WHERE document_id=%s",
        (did,),
    ).fetchone()[0]
    if overlay_count and not prior_count:
        raise Ineligible(
            "Unfinalized category rows require review, not silent adoption"
        )
    if not overlay_count:
        for row in proposed["rows"]:
            db.execute(
                f"INSERT INTO regional_price_category_overlay ({','.join(OVERLAY_COLUMNS)}) "
                f"VALUES ({','.join(['%s'] * len(OVERLAY_COLUMNS))})",
                _overlay_values(row, proposed["proof"]),
            )
    values = list(_proof_values(proposed["proof"]))
    values[-1] = Jsonb(values[-1])
    db.execute(
        f"INSERT INTO city_category_overlay_proof ({','.join(PROOF_COLUMNS)}) "
        f"VALUES ({','.join(['%s'] * len(PROOF_COLUMNS))})",
        values,
    )
    return proposed


def load_verified_prior_leaf_overlay(db, document_id: str, native_rows: list[tuple], native_source, *, archive_id: str | None = None, entry_name: str | None = None) -> dict[str, dict] | None:
    """Revalidate an immutable prior leaf proof against the full retained source.

    This compatibility path never rewrites an old proof or overlay. It returns
    a view mapping only after rechecking the complete current parse, original
    ZIP/PDF bytes, source membership, every typed raw field, all locators,
    classifications, and the prior proof digests. It accepts leaf rules only.
    """
    parent_zip, child_pdf, source_url = native_source
    did_hash = hashlib.sha256(child_pdf).hexdigest()
    if did_hash != document_id:
        return None
    raw, classifications, corrections, conflicts = _stored_plan_rows(db, document_id)
    if not raw or corrections or conflicts:
        return None
    parent_id = db.execute(
        "SELECT archive_id FROM city_category_overlay_proof WHERE document_id=%s ORDER BY proof_id LIMIT 1",
        (document_id,),
    ).fetchone()
    if parent_id is None:
        return None
    parent = db.execute(
        "SELECT kind,media_type,source_url,metadata,content FROM source_document WHERE id=%s",
        (parent_id[0],),
    ).fetchone()
    proofs = db.execute(
        f"SELECT {','.join(PROOF_COLUMNS)} FROM city_category_overlay_proof WHERE document_id=%s ORDER BY proof_id",
        (document_id,),
    ).fetchall()
    overlays = db.execute(
        f"SELECT {','.join(OVERLAY_COLUMNS)} FROM regional_price_category_overlay WHERE document_id=%s ORDER BY source_locator COLLATE \"C\"",
        (document_id,),
    ).fetchall()
    if len(proofs) != 1 or not overlays:
        return None
    proof = dict(zip(PROOF_COLUMNS, proofs[0], strict=True))
    did = proof["document_id"]
    if (
        did != document_id
        or proof["parser_version"] != PARSER_VERSION
        or (archive_id is not None and proof["archive_id"] != archive_id)
        or (entry_name is not None and proof["requested_entry_name"] != entry_name)
        or proof["parser_code_sha256"] == hashlib.sha256(Path(city_reports.__file__).read_bytes()).hexdigest()
        or proof["verification"] != {"method": "retained-city-pdf-whole-source-category-only"}
        or parent is None
        or parent[:3] != ("original", "application/zip", source_url)
        or not isinstance(parent[3], dict)
        or parent[3].get("ingestion_kind") != "city-zip"
        or bytes(parent[4]) != parent_zip
        or hashlib.sha256(parent_zip).hexdigest() != proof["archive_id"]
    ):
        return None
    source = db.execute(
        "SELECT kind,media_type,source_url,metadata,content FROM source_document WHERE id=%s",
        (document_id,),
    ).fetchone()
    if (
        source is None or source[:3] != ("original", "application/pdf", source_url)
        or bytes(source[4]) != child_pdf
        or hashlib.sha256(child_pdf).hexdigest() != proof["source_sha256"]
        or not isinstance(source[3], dict)
        or source[3].get("ingestion_kind") != "city-pdf"
        or source[3].get("archive_entry") != proof["entry_name"]
        or proof["archive_id"] not in source[3].get("parents", [])
    ):
        return None
    if any(
        db.execute("SELECT document_id FROM source_archive_member WHERE archive_id=%s AND entry_name=%s", (proof["archive_id"], entry)).fetchone() != (document_id,)
        for entry in {proof["entry_name"], proof["requested_entry_name"]}
    ):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(parent_zip)) as archive:
            for entry in {proof["entry_name"], proof["requested_entry_name"]}:
                members = [m for m in archive.infolist() if m.filename == entry]
                if not members or any(archive.read(m) != child_pdf for m in members):
                    return None
    except (zipfile.BadZipFile, EOFError, RuntimeError):
        return None
    actual = list(city_reports.parse_city_pdf(child_pdf, city_discovery.archive_day(source_url)))
    if actual != native_rows:
        return None
    native = {row[0]: dict(zip(FIELDS, row, strict=True)) for row in native_rows}
    raw_by = {row["source_locator"]: row for row in raw}
    if len(native) != len(native_rows) or set(native) != set(raw_by) or set(native) != set(classifications):
        return None
    locator_digest = digest(sorted(native))
    db_locator_digest = framed_digest(sorted(native))
    class_digest = framed_digest([v for loc in sorted(native) for v in (loc, " > ".join(classifications[loc]))])
    unchanged = [(loc, {k: native[loc][k] for k in FIELDS if k != "category"}) for loc in sorted(native)]
    if any(any(raw_by[loc][k] != native[loc][k] for k in FIELDS if k != "category") for loc in native):
        return None
    native_digest = digest([(loc, native[loc]) for loc in sorted(native)])
    stored_digest = digest([(loc, raw_by[loc]) for loc in sorted(raw_by)])
    if (
        proof["raw_row_count"] != len(native)
        or proof["locator_set_sha256"] != locator_digest
        or proof["db_locator_set_sha256"] != db_locator_digest
        or proof["db_classification_sha256"] != class_digest
        or proof["unchanged_fields_sha256"] != digest(unchanged)
        or proof["native_rows_sha256"] != native_digest
        or proof["old_rows_sha256"] != stored_digest
        or proof["correction_count"] != len(overlays)
    ):
        return None
    proof_id_fields = [
        proof["archive_id"], proof["entry_name"], proof["requested_entry_name"],
        proof["source_sha256"], proof["source_url"], proof["parser_version"],
        proof["parser_code_sha256"], proof["raw_row_count"], proof["correction_count"],
        proof["locator_set_sha256"], proof["db_locator_set_sha256"],
        proof["db_classification_sha256"], proof["unchanged_fields_sha256"],
        proof["native_rows_sha256"], proof["old_rows_sha256"],
    ]
    if proof["proof_id"] != framed_digest([str(v) for v in proof_id_fields]):
        return None
    verified = {}
    for values in overlays:
        row = dict(zip(OVERLAY_COLUMNS, values, strict=True))
        loc = row["source_locator"]
        if (
            loc not in native or row["heading_rule"] not in {"literal-leaf", "verified-printed-leaf-capitalize"}
            or row["old_category"] != raw_by[loc]["category"]
            or row["corrected_category"] != native[loc]["category"]
            or row["category_path"] != native[loc]["category"].split(" > ")
            or row["source_page"] != native[loc]["source_page"]
            or row["source_sha256"] != document_id or row["source_url"] != source_url
            or row["unchanged_fields_sha256"] != proof["unchanged_fields_sha256"]
            or row["locator_set_sha256"] != proof["locator_set_sha256"]
            or row["native_rows_sha256"] != proof["native_rows_sha256"]
            or row["old_rows_sha256"] != proof["old_rows_sha256"]
        ):
            return None
        verified[loc] = {
            "old_category": row["old_category"],
            "corrected_category": row["corrected_category"],
            "category_path": row["category_path"],
            "rule": row["heading_rule"],
        }
    if len(verified) != len(overlays):
        return None
    return verified


def _verified_category_mapping(rows: list[dict]) -> dict[str, tuple[str, str] | dict[str, object]]:
    """Keep legacy leaf tuples and attach full context to top-level headings."""
    verified = {}
    for row in rows:
        if row["rule"] == "literal-top-level-heading":
            verified[row["source_locator"]] = {
                "old_category": row["old_category"],
                "corrected_category": row["corrected_category"],
                "category_path": row["category_path"],
                "rule": row["rule"],
            }
        else:
            verified[row["source_locator"]] = (
                row["old_category"], row["corrected_category"]
            )
    return verified


def load_verified_category_overlay(
    db, document_id: str, native_rows: list[tuple], proposal: dict | None
) -> dict[str, tuple[str, str] | dict[str, object]]:
    """Return exact verified categories using the established leaf shape.

    Legacy leaf rules retain their public ``(old, new)`` tuple values. The
    source-scoped top-level heading rule needs its path and rule metadata, so
    only those rows use a mapping value. An older parser attestation never
    permits the current parity check to pass.
    """
    if proposal is None:
        return {}
    proof = proposal["proof"]
    if proof["source_sha256"] != document_id or city_reports.VERSION != PARSER_VERSION:
        raise Ineligible("Category proof document/parser version differs")
    current_sha = hashlib.sha256(Path(city_reports.__file__).read_bytes()).hexdigest()
    if proof["parser_code_sha256"] != current_sha:
        raise Ineligible("Category proof parser code changed")
    native = {row[0]: dict(zip(FIELDS, row, strict=True)) for row in native_rows}
    if (
        len(native) != len(native_rows)
        or digest([(loc, native[loc]) for loc in sorted(native)])
        != proof["native_rows_sha256"]
    ):
        raise Ineligible("Category proof native rows changed")
    if not _validate_saved_plan(db, proposal):
        raise Ineligible("No finalized current-parser category attestation")
    return _verified_category_mapping(proposal["rows"])
