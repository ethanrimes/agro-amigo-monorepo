"""Verify native city product spacing and append exact-source corrections.

Dry-run is the default. A correction never mutates an archived PDF or an
existing regional_price row; the SQL view overlays verified product identity.
"""

import argparse
import io
import json
import os
import re
from hashlib import sha256
from pathlib import Path

import pdfplumber
import psycopg
from azure.core.exceptions import AzureError
from pdfminer.pdfexceptions import PDFException
from psycopg.types.json import Jsonb

from .city_reports import _city_tables, parse_city_pdf
from .worker import clean, connect, slug

METHOD = "native-pdf-glyph-spacing"
VERSION = "city-product-spacing-v1"
MAX_DOCUMENTS = 100
MAX_PDF_BYTES = 16 * 1024 * 1024
REGIONAL_COLUMNS = (
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
IDENTITY_FIELDS = ("product_id", "product_name")
UNCHANGED_FIELDS = tuple(
    name for name in REGIONAL_COLUMNS if name not in IDENTITY_FIELDS
)
LOCATOR = re.compile(r"^PDF page (\d+),table (\d+),row (\d+),round [12]$")
# One immutable DANE original has a 16 KiB RTFD envelope around a readable
# three-page PDF. The full archived body, not a stripped PDF, remains the ID.
WRAPPED_CITY_PDF_DID = "373bd8410358196648af87471c9f6a061960b0d06e85ee612c1409e7635dd776"
WRAPPED_CITY_PDF_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "sipsa-16-08-2021.zip"
)
WRAPPED_CITY_PDF_BYTES = 163897
WRAPPED_CITY_PDF_HEADER_OFFSET = 16384
WRAPPED_CITY_PDF_EOF_OFFSET = 163757
MAY2021_CITY_RTFD_DID = "3f4c634f9f0c1b832594384da3ebf7c5329dd05466b28a01a12a79a161b4634b"
MAY2021_CITY_RTFD_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "sipsa-01-05-2021.zip"
)
MAY2021_CITY_RTFD_PARENT = "8bfd12b939fe292c041fa0335c4bfb3529f8b63c9cfe224201c98eae681da740"
MAY2021_CITY_RTFD_ENTRY = "Bogota\u0301, D.C., Corabastos-01-05-2021.pdf"
MAY2021_CITY_RTFD_TITLE = "DANE - " + MAY2021_CITY_RTFD_ENTRY
MAY2021_CITY_RTFD_BYTES = 165094
MAY2021_CITY_RTFD_HEADER_OFFSET = 16384
MAY2021_CITY_RTFD_EOF_OFFSET = 164954



def select_documents(db, *, limit, after="", document_ids=()):
    if not 1 <= limit <= MAX_DOCUMENTS:
        raise ValueError(f"limit must be between 1 and {MAX_DOCUMENTS}")
    if document_ids:
        if len(document_ids) > limit or len(set(document_ids)) != len(document_ids):
            raise ValueError("document ID selection exceeds the bound or repeats an ID")
        if any(not re.fullmatch(r"[a-f0-9]{64}", did) for did in document_ids):
            raise ValueError("document ID must be a SHA-256 digest")
        return db.execute(
            """SELECT d.id,d.source_url FROM source_document d
            WHERE d.id=ANY(%s) AND d.metadata->>'ingestion_kind'='city-pdf'
            AND EXISTS(SELECT 1 FROM regional_price r WHERE r.document_id=d.id)
            ORDER BY d.id LIMIT %s""",
            (list(document_ids), limit),
        ).fetchall()
    if after and not re.fullmatch(r"[a-f0-9]{64}", after):
        raise ValueError("after must be a SHA-256 digest")
    return db.execute(
        """SELECT d.id,d.source_url FROM source_document d
        WHERE d.id>%s AND d.metadata->>'ingestion_kind'='city-pdf'
        AND EXISTS(SELECT 1 FROM regional_price r WHERE r.document_id=d.id)
        ORDER BY d.id LIMIT %s""",
        (after, limit),
    ).fetchall()


def load_original(db, did, *, storage_connection=None, request_timeout=None,
                  expected_source_url=None):
    """Prefer the exact Azure Blob original when configured; verify its ID."""
    if not re.fullmatch(r"[a-f0-9]{64}", did):
        raise ValueError("Invalid PDF SHA-256 document ID")
    if storage_connection:
        from azure.storage.blob import BlobServiceClient

        blob = BlobServiceClient.from_connection_string(storage_connection).get_blob_client(
            "source-archive", did + ".pdf"
        )
        request_options = {"timeout": request_timeout} if request_timeout else {}
        if blob.get_blob_properties(**request_options).size > MAX_PDF_BYTES:
            raise ValueError("Archived city PDF exceeds the bounded size")
        body = blob.download_blob(max_concurrency=1, **request_options).readall()
        storage = "azure-blob"
    else:
        retained = db.execute(
            "SELECT content FROM source_document WHERE id=%s", (did,)
        ).fetchone()
        if retained is None:
            raise ValueError("Archived city PDF is missing")
        body = bytes(retained[0])
        storage = "database-archive"
    if len(body) > MAX_PDF_BYTES or sha256(body).hexdigest() != did:
        raise ValueError("Archived city PDF bytes differ from immutable SHA-256")
    if not body.startswith(b"%PDF"):
        wrapped_august_original = (
            did == WRAPPED_CITY_PDF_DID
            and expected_source_url == WRAPPED_CITY_PDF_URL
            and len(body) == WRAPPED_CITY_PDF_BYTES
            and body.startswith(b"rtfd")
            and body.find(b"%PDF") == WRAPPED_CITY_PDF_HEADER_OFFSET
            and body[WRAPPED_CITY_PDF_HEADER_OFFSET:WRAPPED_CITY_PDF_HEADER_OFFSET+8] == b"%PDF-1.3"
            and body.rfind(b"%%EOF") == WRAPPED_CITY_PDF_EOF_OFFSET
        )
        wrapped_may2021_original = (
            did == MAY2021_CITY_RTFD_DID
            and expected_source_url == MAY2021_CITY_RTFD_URL
            and len(body) == MAY2021_CITY_RTFD_BYTES
            and body.startswith(b"rtfd")
            and body.find(b"%PDF") == MAY2021_CITY_RTFD_HEADER_OFFSET
            and body[MAY2021_CITY_RTFD_HEADER_OFFSET:MAY2021_CITY_RTFD_HEADER_OFFSET+8] == b"%PDF-1.3"
            and body.rfind(b"%%EOF") == MAY2021_CITY_RTFD_EOF_OFFSET
        )
        wrapped_exact_original = wrapped_august_original or wrapped_may2021_original
        if wrapped_exact_original:
            if db is None:
                raise ValueError("Archived city original needs exact source provenance")
            if wrapped_august_original:
                owner = db.execute(
                    """SELECT 1 FROM source_document WHERE id=%s AND source_url=%s
                    AND kind='original' AND publisher='DANE'
                    AND media_type='application/pdf'
                    AND metadata->>'ingestion_kind'='city-pdf'""",
                    (did, WRAPPED_CITY_PDF_URL),
                ).fetchone()
            else:
                owner = db.execute(
                    """SELECT 1 FROM source_document WHERE id=%s AND title=%s
                    AND publisher='DANE' AND source_url=%s AND media_type='application/pdf'
                    AND kind='original' AND page_count=3
                    AND metadata->>'ingestion_kind'='city-pdf'
                    AND metadata->>'retention'='permanent'
                    AND metadata->>'original_filename'=%s
                    AND metadata->>'archive_entry'=%s
                    AND metadata->'parents'=jsonb_build_array(%s::text)""",
                    (did, MAY2021_CITY_RTFD_TITLE, MAY2021_CITY_RTFD_URL,
                     MAY2021_CITY_RTFD_ENTRY, MAY2021_CITY_RTFD_ENTRY,
                     MAY2021_CITY_RTFD_PARENT),
                ).fetchone()
            wrapped_exact_original = bool(owner)
        if not wrapped_exact_original:
            raise ValueError("Archived city original has no reviewed PDF header")
    return body, storage


def _native_name_changes(body):
    changes = {}
    table_count = 0
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            original = page.extract_tables()
            corrected = _city_tables(page, repair_prices=False)
            table_count += len(original)
            if len(original) != len(corrected):
                raise ValueError("Native city table count changed")
            for table_no, (old_table, new_table) in enumerate(
                zip(original, corrected), 1
            ):
                if len(old_table) != len(new_table):
                    raise ValueError("Native city row count changed")
                for row_no, (old_row, new_row) in enumerate(
                    zip(old_table, new_table), 1
                ):
                    if old_row[1:] != new_row[1:]:
                        raise ValueError("City product correction changed other cells")
                    old, new = clean(old_row[0]), clean(new_row[0])
                    if old != new:
                        if (
                            len(new.split()) <= len(old.split())
                            or "".join(new.split()) != "".join(old.split())
                        ):
                            raise ValueError("City product correction changed glyphs")
                        # A merged category heading has no package, units or
                        # price cells. It cannot have a published price locator.
                        # Keep the strict unmatched-row guard for all data rows.
                        if not any(clean(cell) for cell in old_row[1:]):
                            continue
                        changes[(page_no, table_no, row_no)] = (old, new)
    return changes, table_count


def _unchanged_digest(row):
    values = [row[name] for name in UNCHANGED_FIELDS]
    return sha256(
        json.dumps(values, default=str, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def verified_corrections(body, did, source_url, originals):
    """Require native word gaps and exact equality of every other price cell."""
    if sha256(body).hexdigest() != did:
        raise ValueError("Source PDF SHA-256 mismatch")
    changes, table_count = _native_name_changes(body)
    if originals and not table_count:
        raise ValueError("Published city rows have no verifiable native PDF tables")
    if not changes:
        return []
    by_locator = {row["source_locator"]: row for row in originals}
    if len(by_locator) != len(originals):
        raise ValueError("Duplicate original city source locator")
    corrections = []
    matched_changes = set()
    for parsed in parse_city_pdf(body):
        new_row = dict(zip(REGIONAL_COLUMNS, parsed))
        match = LOCATOR.fullmatch(new_row["source_locator"])
        if not match:
            raise ValueError("Unexpected city PDF source locator")
        native_key = tuple(map(int, match.groups()[:3]))
        old_new = changes.get(native_key)
        if not old_new:
            continue
        matched_changes.add(native_key)
        old_name, new_name = old_new
        if new_row["product_name"] != new_name:
            raise ValueError("Parser name differs from native glyph reading")
        old = by_locator.get(new_row["source_locator"])
        if old is None:
            raise ValueError("Corrected PDF row is absent from retained prices")
        if (
            old["product_name"] == new_name
            and old["product_id"] == new_row["product_id"]
        ):
            # A newly published document may already use the corrected parser.
            continue
        if (
            old["product_name"] != old_name
            or old["product_id"] != slug(old_name)
            or new_row["product_id"] != slug(new_name)
            or any(old[name] != new_row[name] for name in UNCHANGED_FIELDS)
        ):
            raise ValueError("Corrected row differs in identity or non-name price fields")
        corrections.append(
            {
                "document_id": did,
                "source_locator": new_row["source_locator"],
                "old_product_id": old["product_id"],
                "old_product_name": old_name,
                "corrected_product_id": new_row["product_id"],
                "corrected_product_name": new_name,
                "source_sha256": did,
                "source_url": source_url,
                "source_page": new_row["source_page"],
                "category": new_row["category"].split(" > ")[0],
                "verification": {
                    "method": METHOD,
                    "version": VERSION,
                    "native_text_x_tolerance": 1,
                    "original_text_x_tolerance": 3,
                    "unchanged_fields_sha256": _unchanged_digest(new_row),
                },
            }
        )
    if matched_changes != changes.keys():
        raise ValueError("Changed native product row has no parsed price locator")
    return corrections


def _regional_rows(db, did):
    columns = ",".join(REGIONAL_COLUMNS)
    rows = db.execute(
        f"SELECT {columns} FROM regional_price WHERE document_id=%s ORDER BY source_locator",
        (did,),
    ).fetchall()
    return [dict(zip(REGIONAL_COLUMNS, row)) for row in rows]


def apply_corrections(db, corrections):
    """Insert only absent exact-source corrections; conflicting history fails."""
    inserted = 0
    with db.transaction():
        for item in corrections:
            key = (item["document_id"], item["source_locator"])
            existing = db.execute(
                """SELECT old_product_id,old_product_name,corrected_product_id,
                corrected_product_name,source_sha256,source_url,source_page,verification
                FROM regional_price_product_correction
                WHERE document_id=%s AND source_locator=%s""",
                key,
            ).fetchone()
            expected = tuple(
                item[name]
                for name in (
                    "old_product_id", "old_product_name", "corrected_product_id",
                    "corrected_product_name", "source_sha256", "source_url",
                    "source_page", "verification",
                )
            )
            if existing:
                if tuple(existing) != expected:
                    raise ValueError("Existing immutable correction conflicts with candidate")
                continue
            db.execute(
                """INSERT INTO product(id,name,category)
                VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (
                    item["corrected_product_id"],
                    item["corrected_product_name"],
                    item["category"],
                ),
            )
            result = db.execute(
                """INSERT INTO regional_price_product_correction(
                document_id,source_locator,old_product_id,old_product_name,
                corrected_product_id,corrected_product_name,source_sha256,
                source_url,source_page,verification)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(document_id,source_locator) DO NOTHING
                RETURNING document_id""",
                (*key, *expected[:-1], Jsonb(item["verification"])),
            ).fetchone()
            if result is None:
                raise ValueError("Concurrent city product correction needs review")
            inserted += 1
    return inserted


def run(db, *, limit=10, after="", document_ids=(), apply=False, storage_connection=None):
    if not apply:
        db.execute("SET default_transaction_read_only=on")
    documents = select_documents(
        db, limit=limit, after=after, document_ids=document_ids
    )
    report = {
        "dry_run": not apply,
        "documents": [],
        "corrections": 0,
        "inserted": 0,
        "review_errors": 0,
    }
    for did, source_url in documents:
        entry = {"document_id": did, "source_url": source_url}
        try:
            body, storage = load_original(
                db, did, storage_connection=storage_connection,
                expected_source_url=source_url
            )
            candidates = verified_corrections(
                body, did, source_url, _regional_rows(db, did)
            )
            inserted = apply_corrections(db, candidates) if apply else 0
            report["corrections"] += len(candidates)
            report["inserted"] += inserted
            entry.update(
                status="verified",
                storage=storage,
                candidates=[
                    {
                        "source_locator": c["source_locator"],
                        "old_product_name": c["old_product_name"],
                        "corrected_product_name": c["corrected_product_name"],
                    }
                    for c in candidates
                ],
                inserted=inserted,
            )
        except (psycopg.OperationalError, psycopg.InterfaceError):
            raise
        except (ValueError, PDFException, AzureError, psycopg.Error, OSError) as exc:
            # One malformed/OCR source or stale database row must not stall the
            # keyset. Do not emit raw blob/DB exception text that could contain
            # credentials; the document ID is enough for a targeted retry.
            report["review_errors"] += 1
            entry.update(
                status="review",
                error_type=type(exc).__name__,
                error=(
                    str(exc)[:300]
                    if isinstance(exc, ValueError)
                    else "Source read, parse, or correction insert failed"
                ),
                inserted=0,
            )
        report["documents"].append(entry)
    report["next_after"] = documents[-1][0] if documents and not document_ids else None
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-documents", type=int, default=10)
    parser.add_argument("--after-document-id", default="")
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.apply and os.environ.get("AGRO_CITY_PRODUCT_CORRECTION_APPLY") != "1":
        parser.error("--apply requires AGRO_CITY_PRODUCT_CORRECTION_APPLY=1")
    with connect() as db:
        result = run(
            db,
            limit=args.limit_documents,
            after=args.after_document_id,
            document_ids=args.document_id,
            apply=args.apply,
            storage_connection=os.environ.get("AzureWebJobsStorage"),
        )
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
