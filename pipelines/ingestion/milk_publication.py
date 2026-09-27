"""Publish municipal milk tables and separately identified macroregion charts.

The existing municipal parser/locators are unchanged. A chart can await OCR or
require review without withdrawing independently validated municipal prices.
"""

import io
import re

import pdfplumber
from psycopg.types.json import Jsonb

MUNICIPAL_STEP = "milk:municipal"


def _municipal_coverage(data):
    """Assess absence, never infer a municipal price from cover-chart values."""
    from .pdf_sources import has_table_sized_image

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            grid = bool(
                re.search(
                    r"(?:^|\n)[ \t]*Departamentos?[ \t]*(?:y[ \t]*)?(?:\n[ \t]*)?municipios?",
                    text,
                    re.I,
                )
                and re.search(r"m[ií]nimo|m[aá]ximo|promedio|medio", text, re.I)
            )
            unknown_image = bool(
                has_table_sized_image(page)
                and not re.search(r"Gr[aá]fico\s+\d+|siguiente\s+mapa", text, re.I)
            )
            pages.append(
                {
                    "page": number,
                    "native_characters": len(text.strip()),
                    "municipal_grid_heading": grid,
                    "unclassified_large_image": unknown_image,
                }
            )
            page.close()
    absent = bool(pages) and all(
        p["native_characters"] >= 100
        and not p["municipal_grid_heading"]
        and not p["unclassified_large_image"]
        for p in pages
    )
    return absent, pages


def _review_chart_quotes(db, document_id, reason):
    """Withdraw exact old chart locators; municipal originals remain untouched."""
    from . import milk_macroregions as macro

    db.execute(
        """INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason)
        SELECT DISTINCT ON(q.source_locator) q.document_id,q.source_locator,%s,to_jsonb(q),%s
        FROM official_price_quote q WHERE q.document_id=%s AND q.series=%s
        ORDER BY q.source_locator,q.parsed_at DESC ON CONFLICT DO NOTHING""",
        (macro.VERSION, reason, document_id, macro.SERIES),
    )


def _checkpoint(db, document_id, step, records):
    from .worker import parser_version

    db.execute(
        "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
        "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (document_id, parser_version("milk-pdf"), step, records),
    )


def _date_review(db, document_id, url, reason):
    from .official_catalog import refresh_document

    with db.transaction():
        db.execute(
            "UPDATE ingestion_asset SET status='review',error=%s,checked_at=now() WHERE url=%s",
            (reason, url),
        )
        _review_chart_quotes(db, document_id, reason)
        refresh_document(db, document_id)


def finalize_macroregion_publication(db, document_id, count=None):
    """Recompute complete totals after task transitions; retries never increment.

    ``count`` is accepted for the OCR callback but is deliberately not trusted.
    Only current native completion and actually retained chart quotes count.
    """
    from . import milk_macroregions as macro
    from .official_catalog import refresh_document
    from .worker import parser_version

    version = parser_version("milk-pdf")
    with db.transaction():
        assets = db.execute(
            "SELECT status FROM ingestion_asset WHERE document_id=%s AND kind='milk-pdf' FOR UPDATE",
            (document_id,),
        ).fetchall()
        # A date-conflicting original must never leak its other chart month.
        if not assets:
            return None
        if any(row[0] == "review" for row in assets):
            _review_chart_quotes(
                db,
                document_id,
                "Milk original under document/date review; all chart months withheld",
            )
            refresh_document(db, document_id)
            return None
        checkpoints = dict(
            db.execute(
                "SELECT step,records FROM ingestion_checkpoint "
                "WHERE document_id=%s AND processor_version=%s AND step LIKE 'milk:%%'",
                (document_id, version),
            ).fetchall()
        )
        if MUNICIPAL_STEP not in checkpoints:
            return None
        municipal = checkpoints[MUNICIPAL_STEP]
        tasks = db.execute(
            "SELECT status,error FROM source_ocr_task WHERE document_id=%s "
            "AND source_kind=%s AND source_locator LIKE %s",
            (document_id, macro.KIND, "%" + macro.VERSION),
        ).fetchall()
        chart_review = "milk:chart-review" in checkpoints or (
            "milk:chart-native" not in checkpoints
            and any(state == "review" for state, _ in tasks)
        )
        if chart_review:
            _review_chart_quotes(
                db,
                document_id,
                "Current macroregion chart validation requires review; prior chart values withheld",
            )
        chart_count = db.execute(
            "SELECT count(*) FROM official_price_quote q "
            "WHERE q.document_id=%s AND q.parser_version=%s AND q.series=%s "
            "AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id "
            "AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)",
            (document_id, parser_version(macro.KIND), macro.SERIES),
        ).fetchone()[0]
        pending = not chart_count and any(
            state in ("pending", "deferred", "verified") for state, _ in tasks
        )
        total = municipal + chart_count
        status = "awaiting-ocr" if pending else "complete" if total else "processed"
        messages = []
        conflicts = checkpoints.get("milk:municipal-conflicts", 0)
        if conflicts:
            messages.append(f"Conflicting municipal source keys retained: {conflicts}")
        if "milk:municipal-review" in checkpoints:
            messages.append(
                "Municipal extraction remains under separate review; no unparsed municipal prices claimed"
            )
        if pending:
            messages.append(
                f"Native municipal rows retained: {municipal}; isolated macroregion chart awaits paired OCR"
            )
        elif chart_review:
            messages.append(
                f"Native municipal rows retained: {municipal}; macroregion chart retained for review, no chart prices published"
            )
        elif not total:
            messages.append(
                "Native narrative; no municipal or supported macroregion price table"
            )
        db.execute(
            "UPDATE ingestion_asset SET status=%s,records=%s,error=%s,checked_at=now() "
            "WHERE document_id=%s AND kind='milk-pdf'",
            (status, total, "; ".join(messages) or None, document_id),
        )
        # publish_rows also maintains this derived cache; refresh after the
        # final parent status so a formerly reviewed original becomes eligible.
        refresh_document(db, document_id)
        return total


def publish(db, data, document_id, url, day):
    from . import milk_macroregions as macro
    from .official_sources import publish_rows
    from .special_prices import MilkNarrativeOnly, parse_milk_pdf
    from .worker import SourceDateMismatch, project, save_rows

    # Full materialization preserves the former all-table validation boundary.
    municipal_error = None
    try:
        municipal_rows = list(parse_milk_pdf(data, day))
    except MilkNarrativeOnly:
        municipal_rows = []
    except SourceDateMismatch as exc:
        _date_review(db, document_id, url, str(exc))
        raise
    except ValueError as exc:
        if str(exc) != "No milk PDF price rows parsed":
            raise
        municipal_error = exc
        municipal_rows = []
    chart_error = None
    try:
        chart = macro.inspect(data, day)
    except SourceDateMismatch as exc:
        _date_review(db, document_id, url, str(exc))
        raise
    except ValueError as exc:
        chart = None
        chart_error = str(exc)
    municipal_review = None
    if municipal_error is not None:
        if chart is None:
            raise municipal_error
        absent, coverage = _municipal_coverage(data)
        if not absent:
            municipal_review = coverage
    if db.execute(
        "SELECT 1 FROM ingestion_asset WHERE document_id=%s AND kind='milk-pdf' "
        "AND url<>%s AND status='review' LIMIT 1",
        (document_id, url),
    ).fetchone():
        reason = "Milk original also has a reviewed archive link; chart publication remains blocked"
        _date_review(db, document_id, url, reason)
        raise SourceDateMismatch(reason)
    if chart is not None and not chart.native_rows:
        # Only this verified image crop is queued, never every page/logo.
        chart = macro.enqueue(db, data, document_id, day)
    with db.transaction():
        municipal = save_rows(db, document_id, municipal_rows) if municipal_rows else 0
        conflicts = project(db, document_id, url, "milk-pdf") if municipal else 0
        _checkpoint(db, document_id, MUNICIPAL_STEP, municipal)
        _checkpoint(db, document_id, "milk:municipal-conflicts", conflicts)
        if municipal_review is not None:
            from .worker import parser_version

            db.execute(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                "VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    document_id,
                    "Municipal milk table assessment; " + parser_version("milk-pdf"),
                    parser_version("milk-pdf"),
                    Jsonb({"native_page_coverage": municipal_review}),
                    "Municipal layout remains unsupported; independently verified macroregion chart is separate",
                ),
            )
            _checkpoint(db, document_id, "milk:municipal-review", 0)
        elif municipal_error is not None:
            _checkpoint(db, document_id, "milk:municipal-absent", 0)
        if chart_error:
            locator = f"PDF page 1, milk macroregion chart 1; {macro.VERSION}"
            db.execute(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                "VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    document_id,
                    locator,
                    macro.VERSION,
                    Jsonb(
                        {
                            "source_page": 1,
                            "series": macro.SERIES,
                            "native_extraction_error": chart_error,
                        }
                    ),
                    chart_error,
                ),
            )
            _checkpoint(db, document_id, "milk:chart-review", 0)
        elif chart is None:
            _checkpoint(db, document_id, "milk:chart-absent", 0)
        # The native date guards have now passed. Clear an obsolete review
        # status inside this transaction before official catalog publication.
        anticipated = municipal + len(chart.native_rows if chart else ())
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,error=NULL,"
            "checked_at=now(),attempts=attempts+1 WHERE url=%s",
            (document_id, "complete" if anticipated else "processed", anticipated, url),
        )
        if chart is not None and chart.native_rows:
            publish_rows(db, chart.native_rows, document_id, macro.KIND)
            _checkpoint(db, document_id, "milk:chart-native", len(chart.native_rows))
            db.execute(
                "UPDATE source_ocr_task SET status='review',checked_at=now(),error=%s "
                "WHERE document_id=%s AND source_kind=%s AND status IN ('pending','deferred')",
                (
                    "Native chart labels extracted successfully; no OCR needed. Original image/readings retained",
                    document_id,
                    macro.KIND,
                ),
            )
        return finalize_macroregion_publication(db, document_id)
