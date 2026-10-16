"""Retire obsolete monthly PDF OCR tasks after complete native revalidation.

Originals, rendered pages and provider readings remain immutable. A bounded
scan records the prior task state before requeuing the exact retained PDF.
"""

import hashlib
import io
import time
from datetime import date

import pdfplumber
from pdfminer.pdfexceptions import PDFException
from psycopg.types.json import Jsonb

VERSION = "monthly-native-recovery-v1-verified-decoration"
DOCUMENT_LIMIT = 8
PAGE_LIMIT = 64
REQUEUE_REASON = "Native monthly PDF pages cleared OCR; replay exact retained original"


def retained_resume(db, url):
    result = db.execute(
        """SELECT d.id,d.content FROM ingestion_asset a
        JOIN source_document d ON d.id=a.document_id
        WHERE a.url=%s AND a.kind='monthly-pdf' AND a.status='pending'
          AND a.error=%s AND d.kind='original'
          AND d.metadata->>'ingestion_kind'='monthly-pdf'""",
        (url, REQUEUE_REASON),
    ).fetchone()
    if result is None:
        return None
    if hashlib.sha256(bytes(result[1])).hexdigest() != result[0]:
        raise ValueError("Retained monthly PDF original SHA-256 mismatch")
    return (result[1],)


def retire_tasks(db, *, deadline=None, document_limit=DOCUMENT_LIMIT):
    """Check every page before a reviewed/awaiting source can resume natively."""
    from .ocr import NATIVE_DAILY_REVIEW_REASON
    from .pdf_sources import native_price_page_failure
    from .worker import parse_pdf_pages

    summary = {"documents": 0, "retired": 0, "eligible": 0,
               "requeued_assets": 0, "errors": 0}
    limit = max(0, min(int(document_limit), DOCUMENT_LIMIT))

    def expired():
        return deadline is not None and time.monotonic() >= deadline - 30

    if not limit or expired():
        return summary
    documents = db.execute(
        """SELECT DISTINCT a.document_id FROM ingestion_asset a
        JOIN source_document d ON d.id=a.document_id
        WHERE a.kind='monthly-pdf' AND a.status='awaiting-ocr'
          AND d.media_type='application/pdf' AND d.kind='original'
          AND d.metadata->>'ingestion_kind'='monthly-pdf'
          AND EXISTS(SELECT 1 FROM source_ocr_task t
              WHERE t.document_id=a.document_id AND t.source_kind='monthly-pdf'
                AND t.status IN ('pending','deferred','review'))
          AND NOT EXISTS(SELECT 1 FROM source_ocr_scan s
              WHERE s.document_id=a.document_id AND s.version=%s)
        ORDER BY a.document_id LIMIT %s""",
        (VERSION, limit),
    ).fetchall()
    for (did,) in documents:
        if expired():
            break
        source = db.execute(
            """SELECT d.content,d.reference_period,a.observed_on FROM source_document d
            JOIN ingestion_asset a ON a.document_id=d.id AND a.kind='monthly-pdf'
            WHERE d.id=%s ORDER BY a.checked_at DESC NULLS LAST LIMIT 1""",
            (did,),
        ).fetchone()
        tasks = db.execute(
            """SELECT source_locator,image_id,source_page,status,error FROM source_ocr_task
            WHERE document_id=%s AND source_kind='monthly-pdf'
            ORDER BY source_page,source_locator""", (did,),
        ).fetchall()
        if not source or not tasks or hashlib.sha256(bytes(source[0])).hexdigest() != did:
            summary["errors"] += 1
            continue
        try:
            day = source[2] or date.fromisoformat(source[1])
            body = bytes(source[0])
            failed_pages = set()
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                if not 1 <= len(pdf.pages) <= PAGE_LIMIT or any(
                    not isinstance(t[2], int) or not 1 <= t[2] <= len(pdf.pages)
                    for t in tasks
                ):
                    raise ValueError("Monthly native recovery needs bounded valid pages")
                previous = False
                for number, page in enumerate(pdf.pages, 1):
                    if expired():
                        return summary
                    native = list(parse_pdf_pages([page], day, True, allow_empty=True))
                    if native_price_page_failure(page, page.extract_text() or "", native, previous):
                        failed_pages.add(number)
                    previous = bool(native)
                    page.close()
        except (TypeError, ValueError, PDFException, OSError):
            summary["errors"] += 1
            continue
        retired = 0
        changed_during_scan = False
        with db.transaction():
            for locator, image_id, page, status, error in tasks:
                if page in failed_pages:
                    summary["eligible"] += 1
                    continue
                if status not in ("pending", "deferred", "review") or (
                    status == "review" and error == NATIVE_DAILY_REVIEW_REASON
                ):
                    continue
                updated = db.execute(
                    """UPDATE source_ocr_task SET status='review',checked_at=now(),error=%s
                    WHERE document_id=%s AND source_locator=%s AND image_id=%s
                      AND source_kind='monthly-pdf' AND status=%s
                      AND error IS NOT DISTINCT FROM %s
                    RETURNING source_locator""",
                    (NATIVE_DAILY_REVIEW_REASON, did, locator, image_id, status, error),
                ).fetchone()
                if updated is None:
                    changed_during_scan = True
                    summary["conflicts"] = summary.get("conflicts", 0) + 1
                    continue
                db.execute(
                    """INSERT INTO official_source_review
                    (document_id,source_locator,parser_version,record,reason)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (did, locator, VERSION,
                     Jsonb({"image_id": image_id, "source_page": page,
                            "prior_status": status, "prior_error": error,
                            "source_kind": "monthly-pdf"}),
                     "Native revalidation found no failed price extraction on this page; prior OCR state retained"),
                )
                retired += 1
            if not failed_pages and not changed_during_scan:
                result = db.execute(
                    """UPDATE ingestion_asset a SET status='pending',checked_at=NULL,error=%s
                    WHERE a.document_id=%s AND a.kind='monthly-pdf' AND a.status='awaiting-ocr'
                      AND NOT EXISTS(SELECT 1 FROM source_ocr_task t
                        WHERE t.document_id=a.document_id AND t.source_kind='monthly-pdf'
                          AND (t.status<>'review' OR t.error IS DISTINCT FROM %s))
                    RETURNING a.url""",
                    (REQUEUE_REASON, did, NATIVE_DAILY_REVIEW_REASON),
                ).fetchall()
                summary["requeued_assets"] += len(result)
            if not changed_during_scan:
                db.execute(
                    "INSERT INTO source_ocr_scan(document_id,version) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    (did, VERSION),
                )
        summary["retired"] += retired
        summary["documents"] += 1
    return summary
