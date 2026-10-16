"""Archive and publish official references without mixing currencies or price bases.

Source adapters own discovery and extraction. This module enforces quote identity,
validation and immutable revisions. Local wholesale projections remain separate.
"""

import hashlib
import json
import math
import re
import time
from datetime import date
from decimal import Decimal

from psycopg.types.json import Jsonb

VERSION = "official-v2"

JULY2012_REVIEW_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana14_19julio_2012.pdf"
JULY2012_REVIEW_SHA = "fd66a34201085c864a2953e2e8ae56e593f2c12d897fdcb95e14bb1589c70856"
JULY2012_REVIEW_DAY = date(2012, 7, 19)
JULY2012_REVIEW_SUFFIX = ":july2012-period-conflict-review-v1"
JULY2012_REVIEW_COUNT = 2983
JULY2012_TABLE_HEADING = "2012 (julio 14 a 20)"
JULY2012_FILENAME_START = "2012-07-14"
JULY2012_FILENAME_END = "2012-07-19"
JULY2012_REVIEW_REASON = (
    "El boletín tiene fechas discrepantes: el archivo/portada indica 19 de julio, "
    "mientras las tablas impresas abarcan del 14 al 20 de julio; se conserva "
    "la fila literal sin fecha de observación ni precio publicado para revisión."
)
JULY2012_LOCATOR_SHA256 = "a942e3d91c18ce451ee39eba4aa84f59b2c6f2c3876be00686e8a9d6fba212a3"
JULY2012_COHORT_SHA256 = "3c6091c875a94fe4d9f47fbbef7ae2d0d1600cdd0539aba7db10127d2194c663"


def is_reference_kind(kind):
    """Source families handled wholly by the official-reference publisher."""
    from . import dane_weekly

    return (
        kind.startswith(("international-", "colombia-"))
        or kind in dane_weekly.PUBLISHERS
    )


def adapter(kind):
    from . import dane_weekly

    if kind in dane_weekly.PUBLISHERS:
        return dane_weekly
    if kind in ("coffee", "coffee-pdf"):
        from . import coffee_sources

        return coffee_sources
    if kind.startswith("international-"):
        from . import international_sources

        return international_sources
    if kind.startswith("colombia-"):
        from . import colombia_sources

        return colombia_sources
    raise ValueError("Unregistered official source kind")


def discover_roots(db):
    from . import dane_weekly

    for module in (adapter("international-"), adapter("colombia-"), dane_weekly):
        for url, kind in module.discover():
            _queue_source(db, url, kind)


def _queue_source(db, url, kind):
    from . import dane_weekly, international_sources
    from .worker import queue

    if url == international_sources.USDA_MIAMI_AUG18_ALTERNATE and kind == 'international-usda-miami-flowers':
        queue(db, url, kind, date(2025, 8, 18))
    elif kind in dane_weekly.PUBLISHERS and kind not in dane_weekly.INDEX_KINDS:
        queue(db, url, kind, dane_weekly.source_date(url))
    else:
        queue(db, url, kind)


def publisher(kind):
    return adapter(kind).PUBLISHERS[kind]


NATIVE_PDF_COMPLETION_KINDS = frozenset(("dane-weekly-pdf", "colombia-corabastos-pdf", "colombia-pork-pdf"))


def process(db, data, document_id, url, kind, *, prior_asset_document_id=None):
    module = adapter(kind)
    for child_url, child_kind in (
        module.discover(body=data, url=url, kind=kind)
        if kind not in ("coffee", "coffee-pdf")
        else ()
    ):
        _queue_source(db, child_url, child_kind)
    if kind == "dane-weekly-xlsx":
        from .reviewed_weekly_feb2014 import PAIRS as FEB2014_PAIRS, review as review_feb2014
        if url in FEB2014_PAIRS:
            # This exact readable annex has no unit or period in its cells.
            # Keep the complete original and its native numeric-row count in a
            # source-bound review; never assign the paired PDF's kg unit.
            return publish_rows(
                db, review_feb2014(db, data, document_id, url), document_id,
                kind, source_url=url,
            )
        from .reviewed_weekly_native_context import (
            REVIEW_MARKER as NATIVE_CONTEXT_MARKER,
            URLS as NATIVE_CONTEXT_URLS,
            rows_for as native_context_rows_for,
        )
        from .worker import parser_version

        native_context_revision = parser_version(kind, url)
        if url in NATIVE_CONTEXT_URLS:
            with db.transaction():
                if not db.execute(
                    "SELECT 1 FROM ingestion_asset WHERE url=%s AND kind=%s FOR UPDATE",
                    (url, kind),
                ).fetchone():
                    raise ValueError("Native weekly review asset binding is missing")
                native_context = native_context_rows_for(
                    db, data, url, document_id, native_context_revision,
                    prior_asset_document_id=prior_asset_document_id,
                )
                if native_context is not None:
                    rows, _reason = native_context
                    count = publish_rows(db, rows, document_id, kind, source_url=url)
                    if count != 0:
                        raise ValueError("Native weekly document review unexpectedly published quotes")
                    db.execute(
                        "UPDATE ingestion_asset SET document_id=%s,status='review',records=0,"
                        "processor_version=%s,checked_at=now(),attempts=attempts+1,error=%s "
                        "WHERE url=%s AND kind=%s",
                        (document_id, native_context_revision, NATIVE_CONTEXT_MARKER, url, kind),
                    )
                    return 0
    ocr_pages = ()
    semantic_mode = None
    if kind == "colombia-corabastos-pdf":
        from .corabastos_semantic_correction import select_mode
        semantic_mode = select_mode(kind, url, document_id, data)
    try:
        rows = (module.parse(data, url, kind, semantic_mode=semantic_mode)
                if semantic_mode is not None else module.parse(data, url, kind))
    except getattr(module, "WeeklyNativeContextIncomplete", type("UnusedContextFailure", (Exception,), {})) as exc:
        if kind != "dane-weekly-xlsx":
            raise
        from .reviewed_weekly_native_context import (
            GENERIC_REVIEW_MARKER, GenericWeeklyContextBindingError,
            rows_for_generic,
        )
        from .worker import parser_version
        revision = parser_version(kind, url)
        with db.transaction():
            locked_asset = db.execute(
                "SELECT document_id,kind FROM ingestion_asset WHERE url=%s FOR UPDATE",
                (url,),
            ).fetchone()
            if locked_asset is None or locked_asset[1] != kind:
                raise GenericWeeklyContextBindingError(
                    "Generic weekly review asset binding is missing"
                ) from exc
            if locked_asset[0] != document_id:
                raise GenericWeeklyContextBindingError(
                    "Generic weekly review asset document pointer changed"
                ) from exc
            reviewed = rows_for_generic(
                db, data, url, document_id, revision,
                prior_asset_document_id=prior_asset_document_id,
            )
            if reviewed is None:
                raise exc
            rows, _reason = reviewed
            count = publish_rows(db, rows, document_id, kind, source_url=url)
            if count != 0:
                raise ValueError("Generic weekly review unexpectedly published quotes")
            db.execute(
                "UPDATE ingestion_asset SET document_id=%s,status='review',records=0,"
                "processor_version=%s,checked_at=now(),attempts=attempts+1,error=%s "
                "WHERE url=%s AND kind=%s",
                (document_id, revision, GENERIC_REVIEW_MARKER, url, kind),
            )
            return 0
    except getattr(
        module,
        "NormalExtractionFailed",
        type("UnusedExtractionFailure", (Exception,), {}),
    ) as exc:
        if semantic_mode is not None:
            raise ValueError("Pinned Corabastos semantic revision requires native extraction") from exc
        import io

        import pdfplumber

        from .ocr import VERSION as OCR_VERSION
        from .ocr import compare_pork_price_readings, compare_readings, enqueue_image

        readings = {}
        pork_pairs = {}
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for number in exc.required_pages:
                if number < 1 or number > len(pdf.pages):
                    raise ValueError("OCR requested a nonexistent page")
                page = pdf.pages[number - 1]
                enqueue_image(
                    db,
                    document_id,
                    f"PDF page {number}",
                    page.to_image(resolution=200).original,
                    kind,
                    number,
                )
                cached = db.execute(
                    "SELECT r.result FROM source_ocr_task t JOIN source_ocr_result r ON r.image_id=t.image_id WHERE t.document_id=%s AND t.source_page=%s AND r.version=%s ORDER BY r.reading",
                    (document_id, number, OCR_VERSION),
                ).fetchall()
                if len(cached) == 2:
                    if kind == "colombia-pork-pdf":
                        pork_pairs[number] = (cached[0][0], cached[1][0])
                    elif compare_readings(cached[0][0], cached[1][0]):
                        readings[number] = cached[0][0]
        if kind == "colombia-pork-pdf" and len(pork_pairs) == len(exc.required_pages):
            if compare_pork_price_readings(data, url, pork_pairs):
                readings = {page: pair[0] for page, pair in pork_pairs.items()}
        if len(readings) != len(exc.required_pages):
            return None
        rows = module.parse_with_ocr(data, url, kind, readings)
        ocr_pages = tuple(readings)
    if kind in ("coffee", "coffee-pdf"):
        rows = module.publication_rows(rows)
    if kind == "dane-weekly-xlsx":
        from .dane_weekly import RICE_MONTHLY_CONFLICTS
        conflict = RICE_MONTHLY_CONFLICTS.get(document_id)
        if conflict is not None and conflict["url"] == url:
            pdf = db.execute(
                "SELECT content FROM source_document WHERE id=%s AND source_url=%s",
                (conflict["pdf_sha256"], url[:-4] + ".pdf"),
            ).fetchone()
            if not pdf or hashlib.sha256(bytes(pdf[0])).hexdigest() != conflict["pdf_sha256"]:
                raise ValueError("Audited rice companion PDF original unavailable or changed")
    if kind == "dane-weekly-pdf":
        from .dane_weekly import (
            JANUARY_2017_JAN13_URL, NOVEMBER_2016_MEDELLIN_WRAP_URL,
            AUGUST_2015_WRAP_URL, AUG2014_PAGE43_URL, AUG2013_PAGE43_URL,
            SEP2013_PAGE43_URL, JUNE_2012_FONT_RUN_URL,
            NOV2019_COTINUACION_URL, MAY2013_WHITE_CORN_URL,
        )
        from .panela_article_official import SOURCE_URL as JUNE_2014_ARTICLE_URL
        from .panela_article_aug2014_official import SOURCE_URL as AUG2014_ARTICLE_URL
        count = (publish_rows(db, rows, document_id, kind, source_url=url)
                 if url in (AUG2014_PAGE43_URL, AUG2014_ARTICLE_URL, JUNE_2012_FONT_RUN_URL,
                            NOV2019_COTINUACION_URL, JANUARY_2017_JAN13_URL,
                            NOVEMBER_2016_MEDELLIN_WRAP_URL, AUGUST_2015_WRAP_URL,
                            JUNE_2014_ARTICLE_URL, MAY2013_WHITE_CORN_URL,
                            AUG2013_PAGE43_URL, SEP2013_PAGE43_URL,
                            JULY2012_REVIEW_URL)
                 else publish_rows(db, rows, document_id, kind))
    elif kind == "dane-weekly-xlsx":
        from .dane_weekly import RICE_MONTHLY_CONFLICT_URLS
        from .reviewed_weekly_native_context import URLS as NATIVE_CONTEXT_URLS
        count = (publish_rows(db, rows, document_id, kind, source_url=url)
                 if url in RICE_MONTHLY_CONFLICT_URLS or url in NATIVE_CONTEXT_URLS
                 else publish_rows(db, rows, document_id, kind))
    elif kind == "colombia-corabastos-pdf":
        count = publish_rows(db, rows, document_id, kind, source_url=url)
    else:
        count = publish_rows(db, rows, document_id, kind)
    if ocr_pages:
        db.execute(
            "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_page=ANY(%s::integer[])",
            (document_id, list(ocr_pages)),
        )
    elif kind in NATIVE_PDF_COMPLETION_KINDS:
        # A parser upgrade can make previously queued image readings obsolete.
        # Only retire them after the full native publication has completed;
        # deferred/failed publication must retain its outstanding work.
        db.execute(
            "UPDATE source_ocr_task SET status='review',checked_at=now(),error=%s "
            "WHERE document_id=%s AND source_kind=%s "
            "AND status IN ('pending','deferred')",
            (
                "Native extraction succeeded; no OCR needed. Original, image and prior readings retained",
                document_id,
                kind,
            ),
        )
    return count


MAY2013_WHITE_CORN_PRIOR_SHA256 = "90253a8aa3a6015af28fba53a1ee98927bd6ebdf04ad62e2350fbf40d6473ff5"
MAY2013_WHITE_CORN_TARGETS = {
    "PDF page 29,table 1,column 2,line 27": ("Maíz blanco cáscara Medellín, Central Mayorista de Antioquia", "Medellín, Central Mayorista de Antioquia", 905.0, "="),
    "PDF page 29,table 1,column 2,line 28": ("San Vicente (Antioquia)", "San Vicente (Antioquia)", 1000.0, "++"),
}
MAY2013_WHITE_CORN_SUFFIX = ":may2013-white-corn-heading-v1"
MAY2013_WHITE_CORN_REASON = "The retained May 2013 page 29 native heading is Maíz blanco cáscara; this prior locator was assigned to the preceding product block. Original and prior quote are retained."


def _may2013_json(value):
    if isinstance(value, Jsonb):
        return value.obj
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def _may2013_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_may2013_json, allow_nan=False).encode()).hexdigest()


def _validate_may2013_heading_source(db, source_url, document_id, kind):
    from .dane_weekly import MAY2013_WHITE_CORN_URL, MAY2013_WHITE_CORN_SHA, MAY2013_WHITE_CORN_SIZE
    if kind != "dane-weekly-pdf" or source_url != MAY2013_WHITE_CORN_URL or document_id != MAY2013_WHITE_CORN_SHA:
        raise ValueError("May 2013 weekly heading source binding changed")
    source = db.execute("SELECT id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata FROM source_document WHERE id=%s", (document_id,)).fetchone()
    if source is None or bytes(source[8] or b"") == b"":
        raise ValueError("May 2013 source original is missing")
    body = bytes(source[8])
    if (source[0] != MAY2013_WHITE_CORN_SHA or source[1] != "DANE · SIPSA - Semana_18may_24may_2013.pdf"
            or source[2] != "DANE · SIPSA" or source[3] != MAY2013_WHITE_CORN_URL
            or source[4:6] != ("application/pdf", "original") or str(source[6]) != "2013-05-24"
            or source[7] != 44 or len(body) != MAY2013_WHITE_CORN_SIZE
            or hashlib.sha256(body).hexdigest() != MAY2013_WHITE_CORN_SHA
            or source[9] != {
                "retention": "permanent",
                "ingestion_kind": kind,
                "original_filename": "Semana_18may_24may_2013.pdf",
            }):
        raise ValueError("Exact May 2013 original metadata or retained bytes changed")
    asset = db.execute("SELECT status,document_id,processor_version,observed_on,records,error FROM ingestion_asset WHERE url=%s", (source_url,)).fetchone()
    if asset is None:
        raise ValueError("May 2013 ingestion asset is missing")
    revision = "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24"
    prior_revision = "official-v2:dane-weekly-v24"
    marker = (prior_revision, "official:catalog-start:official-catalog-v1:2026-10-05", 4201)
    checkpoints = db.execute("SELECT processor_version,step,records FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step", (document_id,)).fetchall()
    pending = (asset == ("pending", document_id, "", date(2013, 5, 24), 0,
                         "Official catalog refresh deferred after 256 of 4201 identities")
               and checkpoints == [marker])
    # The prior catalog refresh ran twice before completing. Keep that old
    # history source-bound: Oct 5 is required, Oct 8 is the only additional
    # recognized start, and the old completion marker may appear only last.
    # This deliberately rejects arbitrary canonical-looking dates, versions,
    # counts, duplicate starts, and unknown checkpoint steps.
    old_start_steps = (
        "official:catalog-start:official-catalog-v1:2026-10-05",
        "official:catalog-start:official-catalog-v1:2026-10-08",
    )
    old_start_checkpoints = tuple((prior_revision, step, 4201) for step in old_start_steps)
    old_complete_marker = (prior_revision, "official:complete", 4201)
    accepted_old_histories = {
        (old_start_checkpoints[:1], False),
        (old_start_checkpoints[:1] + (old_complete_marker,), True),
        (old_start_checkpoints, False),
        (old_start_checkpoints + (old_complete_marker,), True),
    }
    checkpoints_tuple = tuple(checkpoints)
    old_history_valid = any(
        checkpoints_tuple == history and has_completion
        for history, has_completion in accepted_old_histories
    )
    old_history_prefix_valid = any(checkpoints_tuple == history for history, _ in accepted_old_histories)
    prior_complete_checkpoints = old_start_checkpoints + (old_complete_marker,)
    prior_complete = (asset == ("complete", document_id, prior_revision, date(2013, 5, 24), 4201, None)
                      and old_history_valid)
    prior_replay_pending = (asset == ("pending", document_id, prior_revision, date(2013, 5, 24), 4201, None)
                            and old_history_valid)
    own_lifecycle_failure = (
        asset == (
            asset[0], document_id, revision, date(2013, 5, 24), 4201,
            "ValueError: May 2013 asset is outside the pinned pending/completed lifecycle",
        )
        and asset[0] in ("failed", "pending")
        and checkpoints_tuple == prior_complete_checkpoints
    )
    from .official_catalog import VERSION as catalog_version
    start_prefix = f"official:catalog-start:{catalog_version}:"
    prior_prefixes = sorted(
        (list(history) for history, _ in accepted_old_histories),
        key=len,
        reverse=True,
    )
    base = next((prefix for prefix in prior_prefixes if checkpoints[:len(prefix)] == prefix), None)
    base_offset = len(base) if base is not None else -1
    tail = checkpoints[base_offset:] if base_offset >= 0 else []
    new_complete = (revision, "official:complete", 4201)
    has_new_complete = bool(tail and tail[-1] == new_complete)
    starts = tail[:-1] if has_new_complete else tail
    valid_starts = bool(starts) and all(
        item[0] == revision and item[1].startswith(start_prefix) and item[2] == 4203
        for item in starts
    )
    start_days = []
    if valid_starts:
        try:
            for item in starts:
                day_text = item[1][len(start_prefix):]
                parsed_day = date.fromisoformat(day_text)
                if parsed_day.isoformat() != day_text:
                    raise ValueError("noncanonical catalog start day")
                start_days.append(parsed_day)
            valid_starts = start_days == sorted(set(start_days))
        except ValueError:
            valid_starts = False
    # A valid source lifecycle has one pinned v24 prefix, followed by zero or
    # more unique canonical catalog-start days for the new revision, and
    # optionally one completion marker at the end. No other checkpoint shapes
    # are accepted.
    partial_prefix_checkpoint = old_history_prefix_valid
    partial_checkpoints = base is not None and valid_starts and not has_new_complete
    completed_checkpoints = base is not None and valid_starts and has_new_complete
    completed = (asset == ("complete", document_id, revision, date(2013, 5, 24), 4201, None)
                 and completed_checkpoints)
    replay_pending = (asset == ("pending", document_id, revision, date(2013, 5, 24), 4201, None)
                      and completed_checkpoints)
    quote_batch_defer = asset[5] == "Official source validated; committed quote batches will resume"
    catalog_defer_match = re.fullmatch(
        r"Official catalog refresh deferred after ([0-9]+) of ([0-9]+) identities", asset[5] or ""
    )
    catalog_defer = bool(catalog_defer_match and 0 <= int(catalog_defer_match.group(1)) <= int(catalog_defer_match.group(2)) <= 4203 and int(catalog_defer_match.group(2)) > 0)
    completion_defer = asset[5] == "Official quote batches retained; catalog completion will resume"
    worker_deferred = quote_batch_defer or catalog_defer or completion_defer
    partial_asset_state = (
        asset[0] == "pending" and asset[5] is None
        or asset[0] in ("pending", "failed") and worker_deferred
    )
    asset_revision_ok = asset[2] in ("", prior_revision, revision)
    asset_count_ok = (asset[4] == 0 and asset[2] in ("", revision)) or (asset[4] == 4201 and asset[2] in (prior_revision, revision))
    no_error_pending = asset[0] == "pending" and asset[5] is None
    partial_resume = (partial_asset_state and asset[1] == document_id and asset_revision_ok
                      and asset[3] == date(2013, 5, 24) and asset_count_ok
                      and ((partial_checkpoints and (catalog_defer or no_error_pending))
                           or (partial_prefix_checkpoint and (quote_batch_defer or completion_defer or no_error_pending))))
    if not (pending or prior_complete or prior_replay_pending or own_lifecycle_failure
            or completed or replay_pending or partial_resume):
        raise ValueError("May 2013 asset is outside the pinned pending/completed lifecycle")
    if completed or replay_pending:
        revised = db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s", (document_id, revision)).fetchone()[0]
        retired = db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s AND source_locator=ANY(%s::text[])", (document_id, revision, list(MAY2013_WHITE_CORN_TARGETS))).fetchone()[0]
        if revised != 4201 or retired != 2:
            raise ValueError("May 2013 completed revision does not match its pinned quote/review counts")
    old_fields = ("document_id", "source_locator", "parser_version", "quote_key", "product_id", "product_name", "category", "publisher", "series", "basis", "currency", "unit", "market", "observed_on", "period_start", "price", "min_price", "max_price", "source_page", "details")
    stored = db.execute("SELECT " + ",".join(old_fields) + ",xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version='official-v2:dane-weekly-v24' ORDER BY source_locator", (document_id,)).fetchall()
    material = []
    for stored_row in stored:
        record = dict(zip(old_fields, stored_row[:-1]))
        material.append(record)
    if len(material) != 4201 or _may2013_digest(material) != MAY2013_WHITE_CORN_PRIOR_SHA256:
        raise ValueError("Full May 2013 v24 quote cohort differs from the pinned 4,201-row source vector")
    if any(row[0] != document_id or row[2] != "official-v2:dane-weekly-v24" for row in stored):
        raise ValueError("May 2013 prior quote identity changed")
    return body


def _prepare_may2013_heading_retirements(db, document_id, source_url, revision, rows, values):
    from .dane_weekly import MAY2013_WHITE_CORN_URL, MAY2013_WHITE_CORN_SHA, MAY2013_WHITE_CORN_SIZE
    _validate_may2013_heading_source(db, source_url, document_id, "dane-weekly-pdf")
    if revision != "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24":
        raise ValueError("May 2013 source-local quote revision changed")
    expected = {
        "PDF page 29,table 1,column 2,line 27" + MAY2013_WHITE_CORN_SUFFIX: ("Medellín, Central Mayorista de Antioquia", 905.0, "="),
        "PDF page 29,table 1,column 2,line 28" + MAY2013_WHITE_CORN_SUFFIX: ("San Vicente (Antioquia)", 1000.0, "++"),
    }
    by_locator = {row.get("source_locator"): row for row in rows}
    if len(by_locator) != len(rows):
        raise ValueError("May 2013 candidate has duplicate source locators")
    native_sha = hashlib.sha256((json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()).hexdigest()
    if native_sha != "8815e38040163575f92ac220e93ac38d49cfa1bac36507800bf0f1c1bc26bb96":
        raise ValueError("Full May 2013 native 4,404-row source vector changed")
    row_by_locator = {row[1]: row for row in values}
    if len(row_by_locator) != 4201:
        raise ValueError("May 2013 candidate must project the full 4,201 priced source vector")
    stored_revision = db.execute(
        "SELECT document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,max_price,source_page,details "
        "FROM official_price_quote WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
        (document_id, revision),
    ).fetchall()
    for stored in stored_revision:
        expected_row = row_by_locator.get(stored[1])
        if expected_row is None:
            raise ValueError("Partial May 2013 revision contains an unexpected quote locator")
        for index, (actual, target) in enumerate(zip(stored, expected_row)):
            if index in (15, 16, 17):
                same = (actual is None and target is None) or (actual is not None and target is not None and Decimal(str(actual)) == Decimal(str(target)))
            elif index == 19:
                same = actual == target.obj
            else:
                same = actual == target
            if not same:
                raise ValueError("Partial May 2013 revision conflicts with the exact native source vector")
    for locator, (market, price, trend) in expected.items():
        row = by_locator.get(locator)
        if (row is None or row.get("product_id") != "maiz-blanco-cascara"
                or row.get("product_name") != "Maíz blanco cáscara"
                or row.get("category") != "granos y cereales" or row.get("market") != market
                or row.get("unit") != "kg" or row.get("date") != "2013-05-24"
                or row.get("period_start") != "2013-05-18" or row.get("price") != price
                or row.get("min") != price or row.get("max") != price
                or row.get("source_page") != 29
                or row.get("details", {}).get("trend") != trend
                or row.get("details", {}).get("native_heading_recovery") != "exact_may2013_page29_column2_heading_before_wrapped_market_v1"):
            raise ValueError("One May 2013 source-backed replacement row changed")
    old_fields = ("document_id", "source_locator", "parser_version", "quote_key", "product_id", "product_name", "category", "publisher", "series", "basis", "currency", "unit", "market", "observed_on", "period_start", "price", "min_price", "max_price", "source_page", "details")
    old_rows = db.execute("SELECT " + ",".join(old_fields) + ",xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version='official-v2:dane-weekly-v24' AND source_locator=ANY(%s::text[]) ORDER BY source_locator", (document_id, list(MAY2013_WHITE_CORN_TARGETS))).fetchall()
    if len(old_rows) != 2:
        raise ValueError("Both old May 2013 target rows must exist before review")
    replacement_by_old = {old: old + MAY2013_WHITE_CORN_SUFFIX for old in MAY2013_WHITE_CORN_TARGETS}
    reviews, retired = [], {}
    for stored in old_rows:
        record = dict(zip(old_fields, stored[:-1]))
        old_locator = record["source_locator"]
        source_market, market, price, trend = MAY2013_WHITE_CORN_TARGETS[old_locator]
        if (record["product_id"] != "maiz-amarillo-trillado" or record["product_name"] != "Maíz amarillo trillado"
                or record["market"] != source_market or float(record["price"]) != price
                or float(record["min_price"]) != price or float(record["max_price"]) != price
                or record["source_page"] != 29 or record["details"].get("trend") != trend):
            raise ValueError("Prior May 2013 target quote differs from its pinned old identity")
        replacement = by_locator[replacement_by_old[old_locator]]
        prior_quote = dict(record)
        for field in ("observed_on", "period_start"):
            prior_quote[field] = prior_quote[field].isoformat() if prior_quote[field] else None
        for field in ("price", "min_price", "max_price"):
            prior_quote[field] = str(prior_quote[field]) if prior_quote[field] is not None else None
        review = {
            "document_id": document_id, "source_url": source_url, "source_sha256": MAY2013_WHITE_CORN_SHA,
            "prior_quote_key": record["quote_key"], "prior_parser_version": record["parser_version"],
            "prior_quote": prior_quote, "prior_quote_xmin": stored[-1],
            "prior_product_id": record["product_id"], "prior_product_name": record["product_name"], "prior_market": record["market"],
            "prior_price": float(record["price"]), "prior_min_price": float(record["min_price"]), "prior_max_price": float(record["max_price"]),
            "prior_observed_on": record["observed_on"].isoformat(), "prior_source_page": record["source_page"],
            "printed_product_heading": "Maíz blanco cáscara", "printed_market": market,
            "replacement_locator": replacement_by_old[old_locator],
            "native_heading_recovery": "exact_may2013_page29_column2_heading_before_wrapped_market_v1",
        }
        reviews.append((document_id, old_locator, revision, Jsonb(review), MAY2013_WHITE_CORN_REASON))
        retired[old_locator] = replacement_by_old[old_locator]
    return reviews, retired


def _validate_july2012_review(db, rows, document_id, kind, source_url, revision):
    """Validate the exact unpriced July 2012 cohort before publication writes."""
    if document_id != JULY2012_REVIEW_SHA and source_url != JULY2012_REVIEW_URL:
        return None
    if (kind != "dane-weekly-pdf" or source_url != JULY2012_REVIEW_URL
            or document_id != JULY2012_REVIEW_SHA):
        raise ValueError("Exact July 2012 review URL, document ID, or kind changed")

    from .worker import parser_version

    expected_revision = parser_version(kind, source_url)
    if (revision != expected_revision
            or expected_revision != parser_version(kind) + JULY2012_REVIEW_SUFFIX):
        raise ValueError("Exact July 2012 review process version is not source-local")

    source = db.execute(
        "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
        "page_count,content,metadata FROM source_document WHERE id=%s",
        (document_id,),
    ).fetchone()
    if source is None:
        raise ValueError("Exact July 2012 retained source original is missing")
    body = bytes(source[8] or b"")
    metadata = source[9] or {}
    expected_title = "DANE · SIPSA - Semana14_19julio_2012.pdf"
    if (source[0] != JULY2012_REVIEW_SHA or source[1] != expected_title
            or source[2] != "DANE · SIPSA" or source[3] != JULY2012_REVIEW_URL
            or source[4:6] != ("application/pdf", "original")
            or str(source[6]) != JULY2012_REVIEW_DAY.isoformat()
            or source[7] != 34 or len(body) != 1_165_022
            or hashlib.sha256(body).hexdigest() != JULY2012_REVIEW_SHA
            or metadata.get("ingestion_kind") != kind
            or metadata.get("retention") != "permanent"
            or metadata.get("original_filename") != "Semana14_19julio_2012.pdf"):
        raise ValueError("Exact July 2012 original metadata, reference day, or bytes changed")
    asset = db.execute(
        "SELECT url,kind,document_id,observed_on FROM ingestion_asset WHERE url=%s",
        (JULY2012_REVIEW_URL,),
    ).fetchone()
    if asset != (JULY2012_REVIEW_URL, kind, JULY2012_REVIEW_SHA, JULY2012_REVIEW_DAY):
        raise ValueError("Exact July 2012 asset or reference day changed")

    rows = tuple(rows)
    if len(rows) != JULY2012_REVIEW_COUNT:
        raise ValueError("Exact July 2012 review cohort is partial")
    locators = [row.get("source_locator") for row in rows]
    if (any(not isinstance(locator, str) or not locator.strip() for locator in locators)
            or len(set(locators)) != JULY2012_REVIEW_COUNT
            or hashlib.sha256("\n".join(sorted(locators)).encode()).hexdigest()
            != JULY2012_LOCATOR_SHA256):
        raise ValueError("Exact July 2012 review locator cohort changed or duplicated")
    if any(not isinstance(row, dict) or not isinstance(row.get("details"), dict)
           for row in rows):
        raise ValueError("Exact July 2012 review row details are missing")
    tuple_fields = ("product_id", "product_name", "category", "market",
                    "source_locator", "source_page", "min", "max")
    tuple_vector = [
        [row.get(field) for field in tuple_fields]
        + [row["details"].get("literal_mean"), row["details"].get("trend")]
        for row in sorted(rows, key=lambda item: item["source_locator"])
    ]
    cohort_sha = hashlib.sha256(json.dumps(
        tuple_vector, ensure_ascii=False, separators=(",", ":"),
        default=str, allow_nan=False,
    ).encode()).hexdigest()
    if cohort_sha != JULY2012_COHORT_SHA256:
        raise ValueError("Exact July 2012 literal monetary tuple cohort changed")
    for row in rows:
        details = row.get("details") or {}
        if (row.get("price") is not None or row.get("date") is not None
                or row.get("period_start") is not None
                or details.get("quality_issue") != JULY2012_REVIEW_REASON
                or details.get("literal_printed_period_heading") != JULY2012_TABLE_HEADING
                or details.get("literal_filename_period_start") != JULY2012_FILENAME_START
                or details.get("literal_filename_period_end") != JULY2012_FILENAME_END
                or details.get("literal_document_reference_day") != "2012-07-19"
                or details.get("source_period_resolution") != "unresolved_source_conflict_review_only"
                or details.get("literal_min") != row.get("min")
                or details.get("literal_max") != row.get("max")
                or details.get("literal_mean") is not None
                   and not math.isfinite(float(details["literal_mean"]))
                or row.get("min") is None or row.get("max") is None
                or not 1 <= row.get("source_page", 0) <= 34):
            raise ValueError("Exact July 2012 row must remain fully unpriced and source-backed")

    typed_quotes = db.execute(
        "SELECT count(*) FROM official_price_quote WHERE document_id=%s",
        (JULY2012_REVIEW_SHA,),
    ).fetchone()[0]
    if typed_quotes:
        raise ValueError("Exact July 2012 source already has typed price quotes")

    existing = db.execute(
        "SELECT source_locator,record,reason FROM official_source_review "
        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
        (JULY2012_REVIEW_SHA, expected_revision),
    ).fetchall()
    if existing:
        wanted = {
            row["source_locator"]: row for row in rows
        }
        if len(existing) != JULY2012_REVIEW_COUNT:
            raise ValueError("Exact July 2012 review revision is incomplete")
        for locator, record, reason in existing:
            row = wanted.get(locator)
            if (row is None or reason != JULY2012_REVIEW_REASON
                    or json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
                    != json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)):
                raise ValueError("Exact July 2012 retained review cohort differs")
    return rows, expected_revision


def publish_rows(db, rows, document_id, kind=None, source_url=None):
    from .worker import parser_version, today

    if kind is None:
        original = db.execute(
            "SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=%s",
            (document_id,),
        ).fetchone()
        if not original:
            raise ValueError("Official source document is missing")
        kind = original[0]
    revision = parser_version(kind)
    july2012_review = _validate_july2012_review(
        db, rows, document_id, kind, source_url, parser_version(kind, source_url)
    ) if (document_id == JULY2012_REVIEW_SHA or source_url == JULY2012_REVIEW_URL) else None
    if july2012_review is not None:
        rows, revision = july2012_review
    cor_semantic = False
    source_body = None
    if kind == "colombia-corabastos-pdf" and source_url is not None:
        from .corabastos_semantic_correction import revision_for as cor_semantic_revision_for, SOURCES as COR_SEM_SOURCES, _source_binding as cor_semantic_source_binding
        if source_url in COR_SEM_SOURCES:
            source_body = cor_semantic_source_binding(db, COR_SEM_SOURCES[source_url])
            if document_id != COR_SEM_SOURCES[source_url]["document_id"]:
                raise ValueError("Pinned Corabastos semantic source ID changed")
            revision = cor_semantic_revision_for(kind, source_url, revision)
            cor_semantic = True
    cor_prior_version = None
    if kind == "colombia-corabastos-pdf":
        from .corabastos_source_relocation import (
            HELD_NOVEL_ORIGINALS, NEW_SUFFIX, select_prior_for_relocation,
        )

        rows = tuple(rows)
        held_url = HELD_NOVEL_ORIGINALS.get(document_id)
        original_url = db.execute(
            "SELECT source_url FROM source_document WHERE id=%s", (document_id,)
        ).fetchone()
        if (original_url is None or
            source_url is not None and source_url != original_url[0] or
            held_url is not None and original_url[0] != held_url):
            raise ValueError("Corabastos original URL changed")
        source_url = original_url[0]
        from .corabastos_source_relocation import REVIEWED_ORIGINALS
        reviewed_did = {v: k for k, v in REVIEWED_ORIGINALS.items()}.get(source_url)
        if reviewed_did is not None and document_id != reviewed_did:
            raise ValueError("Reviewed Corabastos URL now serves different original bytes")
        if held_url is not None:
            raise ValueError("Novel August 1 identities require separate source review")
        cor_prior_version = select_prior_for_relocation(
            db, document_id, source_url, revision, rows,
        )
        if cor_prior_version is not None:
            revision += NEW_SUFFIX
    if kind == "dane-weekly-pdf":
        from .dane_weekly import (AUGUST_2015_WRAP_SHA, AUGUST_2015_WRAP_URL,
                                  AUG2014_PAGE43_SHA, AUG2014_PAGE43_URL,
                                  JANUARY_2017_JAN13_SHA, JANUARY_2017_JAN13_URL,
                                  NOVEMBER_2016_MEDELLIN_WRAP_SHA, NOVEMBER_2016_MEDELLIN_WRAP_URL,
                                  JUNE_2012_FONT_RUN_SHA, JUNE_2012_FONT_RUN_URL,
                                  NOV2019_COTINUACION_SHA, NOV2019_COTINUACION_URL)
        from .panela_article_official import SOURCE_SHA as JUNE_2014_ARTICLE_SHA, SOURCE_URL as JUNE_2014_ARTICLE_URL
        from .dane_weekly import MAY2013_WHITE_CORN_URL, MAY2013_WHITE_CORN_SHA
        from .dane_weekly import AUG2013_PAGE43_URL, AUG2013_PAGE43_SHA
        from .dane_weekly import SEP2013_PAGE43_URL, SEP2013_PAGE43_SHA
        if source_url == MAY2013_WHITE_CORN_URL or document_id == MAY2013_WHITE_CORN_SHA:
            _validate_may2013_heading_source(db, source_url, document_id, kind)
            revision = parser_version(kind, source_url)
        if source_url == AUG2014_PAGE43_URL or document_id == AUG2014_PAGE43_SHA:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s", (document_id,),
            ).fetchone()
            if (document_id != AUG2014_PAGE43_SHA or source_url != AUG2014_PAGE43_URL
                or original is None or original[0] != AUG2014_PAGE43_URL
                or original[1:3] != ("application/pdf", "original")
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b"")).hexdigest() != document_id):
                raise ValueError("Exact August 2014 page-43 source original changed")
            revision = parser_version(kind, source_url)
        if source_url == AUG2013_PAGE43_URL or document_id == AUG2013_PAGE43_SHA:
            original = db.execute(
                "SELECT title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata "
                "FROM source_document WHERE id=%s", (document_id,),
            ).fetchone()
            metadata = original[8] if original is not None else None
            if (
                document_id != AUG2013_PAGE43_SHA or source_url != AUG2013_PAGE43_URL
                or original is None
                or original[0] != "DANE · SIPSA - Semana_20ago_23ago_2013.pdf"
                or original[1] != "DANE · SIPSA"
                or original[2] != AUG2013_PAGE43_URL
                or original[3:5] != ("application/pdf", "original")
                or str(original[5]) != "2013-08-23"
                or original[6] != 44
                or (metadata or {}).get("retention") != "permanent"
                or (metadata or {}).get("ingestion_kind") != kind
                or (metadata or {}).get("original_filename") != "Semana_20ago_23ago_2013.pdf"
                or hashlib.sha256(bytes(original[7] or b"")).hexdigest() != document_id
            ):
                details = {
                    "document_id": document_id == AUG2013_PAGE43_SHA,
                    "source_url": source_url == AUG2013_PAGE43_URL,
                    "title": original is not None and original[0] == "DANE · SIPSA - Semana_20ago_23ago_2013.pdf",
                    "publisher": original is not None and original[1] == "DANE · SIPSA",
                    "url": original is not None and original[2] == AUG2013_PAGE43_URL,
                    "media_kind": original is not None and original[3:5] == ("application/pdf", "original"),
                    "reference_period": original is not None and str(original[5]) == "2013-08-23",
                    "page_count": original is not None and original[6] == 44,
                    "retention": (metadata or {}).get("retention") == "permanent",
                    "ingestion_kind": (metadata or {}).get("ingestion_kind") == kind,
                    "filename": (metadata or {}).get("original_filename") == "Semana_20ago_23ago_2013.pdf",
                    "body_sha": original is not None and hashlib.sha256(bytes(original[7] or b"")).hexdigest() == document_id,
                }
                raise ValueError("Exact August 2013 page-43 source original changed: " + repr(details))
            revision = parser_version(kind, source_url)
        if source_url == SEP2013_PAGE43_URL or document_id == SEP2013_PAGE43_SHA:
            original = db.execute(
                "SELECT title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata "
                "FROM source_document WHERE id=%s", (document_id,),
            ).fetchone()
            metadata = original[8] if original is not None else None
            if (
                document_id != SEP2013_PAGE43_SHA or source_url != SEP2013_PAGE43_URL
                or kind != "dane-weekly-pdf" or original is None
                or original[0] != "DANE · SIPSA - Semana23_sep_27sep_2013.pdf"
                or original[1] != "DANE · SIPSA"
                or original[2] != SEP2013_PAGE43_URL
                or original[3:5] != ("application/pdf", "original")
                or str(original[5]) != "Serie histórica completa"
                or original[6] != 44
                or (metadata or {}).get("retention") != "permanent"
                or (metadata or {}).get("ingestion_kind") != kind
                or (metadata or {}).get("original_filename") != "Semana23_sep_27sep_2013.pdf"
                or hashlib.sha256(bytes(original[7] or b"")).hexdigest() != document_id
            ):
                raise ValueError("Exact September 2013 page-43 source original changed")
            if (len(rows) != 4468
                or sum(row.get("price") is not None for row in rows) != 4336
                or sum(row.get("price") is None for row in rows) != 132
                or any(row.get("date") != "2013-09-27" or row.get("period_start") != "2013-09-21"
                       for row in rows)):
                raise ValueError("Exact September 2013 source typed cohort changed")
            revision = parser_version(kind, source_url)
        if source_url == JUNE_2014_ARTICLE_URL:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s", (document_id,),
            ).fetchone()
            if (document_id != JUNE_2014_ARTICLE_SHA or original is None
                or original[0] != JUNE_2014_ARTICLE_URL
                or original[1:3] != ("application/pdf", "original")
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b"")).hexdigest() != document_id):
                raise ValueError("Exact June 2014 weekly/article PDF original changed")
            revision = parser_version(kind, source_url)
        if source_url == JUNE_2012_FONT_RUN_URL:
            if document_id != JUNE_2012_FONT_RUN_SHA:
                raise ValueError("Audited 2012 weekly PDF original changed")
            revision = parser_version(kind, source_url)
        elif source_url == NOV2019_COTINUACION_URL:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s",
                (document_id,),
            ).fetchone()
            if (document_id != NOV2019_COTINUACION_SHA or original is None
                or original[0] != NOV2019_COTINUACION_URL
                or original[1:3] != ('application/pdf', 'original')
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b'')).hexdigest() != document_id):
                raise ValueError("Audited November 2019 weekly PDF original changed")
            revision = parser_version(kind, source_url)
        elif source_url == AUGUST_2015_WRAP_URL:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s", (document_id,),
            ).fetchone()
            if (document_id != AUGUST_2015_WRAP_SHA or original is None
                or original[0] != source_url
                or original[1:3] != ("application/pdf", "original")
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b"")).hexdigest() != document_id):
                raise ValueError("Exact August 2015 official PDF original changed")
            revision = parser_version(kind, source_url)
        elif source_url == JANUARY_2017_JAN13_URL:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s",
                (document_id,),
            ).fetchone()
            if (document_id != JANUARY_2017_JAN13_SHA or original is None
                or original[0] != JANUARY_2017_JAN13_URL
                or original[1:3] != ('application/pdf', 'original')
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b'')).hexdigest() != document_id):
                raise ValueError("Audited January 13 2017 weekly PDF original changed")
            revision = parser_version(kind, source_url)
        elif source_url == NOVEMBER_2016_MEDELLIN_WRAP_URL:
            original = db.execute(
                "SELECT source_url,media_type,kind,content,metadata->>'ingestion_kind' "
                "FROM source_document WHERE id=%s",
                (document_id,),
            ).fetchone()
            if (document_id != NOVEMBER_2016_MEDELLIN_WRAP_SHA or original is None
                or original[0] != NOVEMBER_2016_MEDELLIN_WRAP_URL
                or original[1:3] != ('application/pdf', 'original')
                or original[4] != kind
                or hashlib.sha256(bytes(original[3] or b'')).hexdigest() != document_id):
                raise ValueError("Audited November 4 2016 weekly PDF original changed")
            revision = parser_version(kind, source_url)
    if kind == "dane-weekly-xlsx":
        from .dane_weekly import RICE_MONTHLY_CONFLICTS, RICE_MONTHLY_CONFLICT_URLS
        from .reviewed_weekly_feb2014 import PAIRS as FEB2014_PAIRS, REVIEW_LOCATOR as FEB2014_LOCATOR, REVIEW_MARKER as FEB2014_MARKER
        from .reviewed_weekly_native_context import URLS as NATIVE_CONTEXT_URLS
        case = RICE_MONTHLY_CONFLICTS.get(document_id)
        if case is not None:
            if source_url is None:
                source = db.execute(
                    "SELECT source_url FROM source_document WHERE id=%s", (document_id,)
                ).fetchone()
                source_url = source[0] if source else None
            if source_url != case["url"]:
                raise ValueError("Audited rice source URL changed")
        if source_url in RICE_MONTHLY_CONFLICT_URLS:
            revision = parser_version(kind, source_url)
        if source_url in FEB2014_PAIRS:
            if document_id != FEB2014_PAIRS[source_url]["xls_sha"]:
                raise ValueError("Reviewed February 2014 annex source changed")
            revision = parser_version(kind, source_url)
            # An append-only ON CONFLICT must not silently bless a poisoned
            # same-version review from a partial or prior process.
            rows = tuple(rows)
            if (len(rows) != 1 or rows[0].get("source_locator") != FEB2014_LOCATOR
                    or rows[0].get("price") is not None
                    or rows[0].get("details", {}).get("quality_issue") != FEB2014_MARKER):
                raise ValueError("Reviewed February 2014 annex projection changed")
            retained = db.execute(
                "SELECT record,reason FROM official_source_review WHERE document_id=%s "
                "AND source_locator=%s AND parser_version=%s",
                (document_id, FEB2014_LOCATOR, revision),
            ).fetchone()
            if retained is not None and retained != (rows[0], FEB2014_MARKER):
                raise ValueError("Reviewed February 2014 annex retained review differs")
        if source_url in NATIVE_CONTEXT_URLS:
            revision = parser_version(kind, source_url)

    values = []
    reviews = []
    seen = {}
    locators = {}
    for row in rows:
        literal = json.dumps(row, sort_keys=True, default=str, allow_nan=False)
        locator = row["source_locator"]
        if not isinstance(locator, str) or not locator.strip():
            raise ValueError("Official source locator must be nonempty text")
        if locator in locators and locators[locator] != literal:
            raise ValueError(
                "Source locator maps to multiple official observations; include the exact market or column"
            )
        locators[locator] = literal
        issue = row.get("details", {}).get("quality_issue")
        if issue or row.get("price") is None:
            reviews.append(
                (
                    document_id,
                    row["source_locator"],
                    revision,
                    Jsonb(json.loads(json.dumps(row, default=str))),
                    issue or "No unambiguous positive price",
                )
            )
            continue
        for field in (
            "product_id",
            "product_name",
            "category",
            "publisher",
            "series",
            "basis",
            "currency",
            "unit",
            "market",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Official {field} must be nonempty text")
        if row["currency"] not in {"COP", "USD", "EUR", "GBP"}:
            raise ValueError("Unsupported official currency")
        day = row["date"]
        if isinstance(day, str):
            day = date.fromisoformat(day)
        if not isinstance(day, date):
            raise ValueError("Official observation date is invalid")
        period_start = row.get("period_start")
        if isinstance(period_start, str):
            period_start = date.fromisoformat(period_start)
        if period_start is not None and (
            not isinstance(period_start, date) or period_start > day
        ):
            raise ValueError("Official period starts after its observation date")
        source_page = row.get("source_page") or row.get("details", {}).get(
            "source_page"
        )
        if source_page is not None and (
            type(source_page) is not int or not 1 <= source_page <= 2147483647
        ):
            raise ValueError("Official source page is invalid")
        if day > today():
            raise ValueError("Official observation is in the future")
        price = float(row["price"])
        low, high = row.get("min"), row.get("max")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Official price must be positive and finite")
        if any(
            v is not None and (not math.isfinite(float(v)) or float(v) <= 0)
            for v in (low, high)
        ):
            raise ValueError("Official price range is invalid")
        if (
            low is not None
            and high is not None
            and not float(low) <= price <= float(high)
        ):
            raise ValueError("Official price is outside the stated range")
        identity = {
            key: row[key]
            for key in ("product_id", "series", "market", "currency", "unit", "basis")
        }
        identity["dimensions"] = row.get("identity_dimensions", {})
        quote_key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        key = (quote_key, day)
        if key in seen and seen[key] != (price, low, high):
            raise ValueError(
                "Conflicting official quote identity; original retained for review"
            )
        seen[key] = (price, low, high)
        details = {
            **row.get("details", {}),
            "identity_dimensions": identity["dimensions"],
        }
        json.dumps(details, allow_nan=False)
        values.append(
            (
                document_id,
                row["source_locator"],
                revision,
                quote_key,
                row["product_id"],
                row["product_name"],
                row["category"],
                row["publisher"],
                row["series"],
                row["basis"],
                row["currency"],
                row["unit"],
                row["market"],
                day,
                period_start,
                price,
                low,
                high,
                source_page,
                Jsonb(details),
            )
        )
    if cor_semantic:
        from .corabastos_semantic_correction import publish_source as publish_corabastos_semantic
        from .official_catalog import refresh_document
        return publish_corabastos_semantic(
            db, url=source_url, document_id=document_id, body=source_body, rows=rows,
            values=values, base_revision=parser_version(kind),
            refresh_document=refresh_document,
        )
    if kind == "dane-weekly-pdf" and source_url == MAY2013_WHITE_CORN_URL:
        retirement_reviews, retired_locators = _prepare_may2013_heading_retirements(
            db, document_id, source_url, revision, rows, values
        )
        reviews.extend(retirement_reviews)
        existing_reviews = db.execute(
            "SELECT source_locator,record,reason FROM official_source_review "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (document_id, revision),
        ).fetchall()
        expected_reviews = {item[1]: (item[3].obj, item[4]) for item in reviews}
        if len(expected_reviews) != len(reviews):
            raise ValueError("May 2013 candidate has duplicate review locators")
        for locator, record, reason in existing_reviews:
            if expected_reviews.get(locator) != (record, reason):
                raise ValueError("Partial May 2013 revision contains a conflicting source review")
        for old_locator, replacement_locator in retired_locators.items():
            locators[old_locator] = json.dumps({"retired_by": replacement_locator}, sort_keys=True)
    # Every still-published source locator needs a new quote or an explicit
    # review row. A nonempty parser result can still be truncated; treating
    # absent locators as withdrawals would silently erase valid catalog rows.
    active_prior_locators = {
        locator
        for (locator,) in db.execute(
            "SELECT DISTINCT q.source_locator FROM official_price_quote q "
            "WHERE q.document_id=%s AND q.parser_version<>%s "
            "AND NOT EXISTS (SELECT 1 FROM official_source_review r "
            "WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator "
            "AND r.created_at>=q.parsed_at) "
            "AND NOT EXISTS (SELECT 1 FROM official_price_quote newer "
            "WHERE newer.document_id=q.document_id AND newer.source_locator=q.source_locator "
            "AND newer.parsed_at>q.parsed_at)",
            (document_id, revision),
        ).fetchall()
    }
    missing = active_prior_locators - locators.keys()
    retirement_reviews = []
    if missing and kind == "colombia-pork-pdf":
        # v1 used one page/heading/y locator for a printed row even though
        # that row has several market columns. v2 names the market explicitly.
        # Retire only an old quote whose complete immutable identity and
        # literal value have exactly one new source-backed counterpart.
        import re

        prior_rows = db.execute(
            "SELECT q.source_locator,q.quote_key,q.observed_on,q.market,q.price,"
            "q.min_price,q.max_price,q.source_page FROM official_price_quote q "
            "WHERE q.document_id=%s AND q.source_locator=ANY(%s::text[]) "
            "AND q.parser_version<>%s "
            "AND NOT EXISTS (SELECT 1 FROM official_source_review r "
            "WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator "
            "AND r.created_at>=q.parsed_at) "
            "AND NOT EXISTS (SELECT 1 FROM official_price_quote newer "
            "WHERE newer.document_id=q.document_id AND newer.source_locator=q.source_locator "
            "AND newer.parsed_at>q.parsed_at)",
            (document_id, list(missing), revision),
        ).fetchall()
        by_locator = {}
        for prior in prior_rows:
            by_locator.setdefault(prior[0], []).append(prior)
        for locator in sorted(missing):
            if not re.fullmatch(
                r"PDF page [1-9]\d*, Cerdo (?:en pie|· canal caliente|· canal fría), y \d+(?:\.\d+)?",
                locator,
            ) or len(by_locator.get(locator, ())) != 1:
                continue
            old = by_locator[locator][0]
            matches = [
                value for value in values
                if value[1] == locator + ", market " + old[3]
                and value[3] == old[1]
                and value[13] == old[2]
                and value[12] == old[3]
                and float(value[15]) == float(old[4])
                and all(
                    a is None and b is None
                    or a is not None and b is not None and float(a) == float(b)
                    for a, b in ((value[16], old[5]), (value[17], old[6]))
                )
                and value[18] == old[7]
            ]
            if len(matches) != 1:
                continue
            replacement = matches[0]
            locators[locator] = json.dumps({"retired_by": replacement[1]})
            retirement_reviews.append(
                (
                    document_id,
                    locator,
                    revision,
                    Jsonb({"retired_by": replacement[1], "market": old[3], "observed_on": old[2].isoformat(), "price": float(old[4]), "source_page": old[7]}),
                    "Exact Porkcolombia row retained under a new market-explicit source locator",
                )
            )
        missing = active_prior_locators - locators.keys()
    cor_prepared = None
    if cor_prior_version is not None:
        from .corabastos_source_relocation import prepare

        cor_prepared = prepare(
            db, document_id, source_url, cor_prior_version, revision,
            rows, values, missing,
        )
        for old_locator, _ in cor_prepared["moves"]:
            locators[old_locator] = json.dumps({"retired_by_verified_source": document_id})
        missing = active_prior_locators - locators.keys()
    if missing:
        raise ValueError(
            "New official parse omitted previously published source locators; "
            "emit source-backed review rows before withdrawal: "
            + ", ".join(sorted(missing)[:3])
        )
    if kind == "dane-weekly-pdf" and source_url in (
            JANUARY_2017_JAN13_URL, NOVEMBER_2016_MEDELLIN_WRAP_URL,
            AUGUST_2015_WRAP_URL):
        # The ordinary insert is append-only and skips an existing locator.
        # A resumed exact-source replay must reject a poisoned same-version
        # row instead of allowing that old value to survive silently.
        expected = {value[1]: value for value in values}
        existing = db.execute(
            "SELECT document_id,source_locator,parser_version,quote_key,"
            "product_id,product_name,category,publisher,series,basis,currency,"
            "unit,market,observed_on,period_start,price,min_price,max_price,"
            "source_page,details FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s",
            (document_id, revision),
        ).fetchall()
        for stored in existing:
            wanted = expected.get(stored[1])
            if wanted is None:
                raise ValueError("Audited January 2017 quote revision has an extra locator")
            for index, (actual, target) in enumerate(zip(stored, wanted)):
                if index in (15, 16, 17):
                    if ((actual is None) != (target is None) or
                            actual is not None and Decimal(str(actual)) != Decimal(str(target))):
                        raise ValueError("Audited January 2017 quote revision collides with a different row")
                elif index == 19:
                    if actual != target.obj:
                        raise ValueError("Audited January 2017 quote revision collides with different details")
                elif actual != target:
                    raise ValueError("Audited January 2017 quote revision collides with a different row")
    # The source is fully validated. A corrected locator may have a new
    # quote_key, and the quote insert trigger only dirties that new identity.
    # Invalidate the old identities before any revised quote batch commits.
    from .official_catalog import mark_document_dirty

    # The whole source is validated before publication. Apply the source-wide
    # strictly-older-than-prior guard to every retained version per key, including
    # reviewed or retired locators. Review/asset/quote triggers independently
    # dirty keys whose eligible winner or previous quote could change.
    older_only = True
    mark_document_dirty(db, document_id, revision, older_only=older_only)
    if reviews:
        with db.cursor() as cur:
            cur.executemany(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                reviews,
            )
    if values:
        columns = "document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,max_price,source_page,details"
        # Validate the entire source first, then retain bounded batches. Existing
        # immutable rows make a resumed asset idempotent without firing insert
        # triggers for every already-published quote. A caller's outer transaction
        # still preserves its own atomicity (for example a retained PDF replay).
        from .resumable_inputs import WorkDeferred
        from .worker import RUN_DEADLINE

        from . import write_pacing

        batch_size = 256
        for start in range(0, len(values), batch_size):
            deadline = RUN_DEADLINE.get()
            if deadline is not None and time.monotonic() >= deadline:
                raise WorkDeferred(
                    "Official source validated; committed quote batches will resume"
                )
            batch_started = write_pacing.clock()
            with db.transaction():
                db.execute(
                    "CREATE TEMP TABLE IF NOT EXISTS official_stage (LIKE official_price_quote INCLUDING DEFAULTS) ON COMMIT DROP"
                )
                db.execute("TRUNCATE pg_temp.official_stage")
                with db.cursor().copy(
                    f"COPY official_stage ({columns}) FROM STDIN"
                ) as copy:
                    for value in values[start : start + batch_size]:
                        copy.write_row(value)
                db.execute(
                    f"INSERT INTO official_price_quote ({columns}) SELECT {columns} FROM official_stage s "
                    "WHERE NOT EXISTS(SELECT 1 FROM official_price_quote q "
                    "WHERE q.document_id=s.document_id AND q.source_locator=s.source_locator "
                    "AND q.parser_version=s.parser_version) ON CONFLICT DO NOTHING"
                )
            write_pacing.pause_between_batches(
                db, batch_started, deadline,
                remaining=start + batch_size < len(values),
            )
        db.execute(
            "UPDATE ingestion_asset SET observed_on=%s WHERE document_id=%s",
            (max(value[13] for value in values), document_id),
        )
    if cor_prepared is not None:
        from .corabastos_source_relocation import (
            confirm_final_source_prior, confirm_stored_new,
            insert_and_verify_retirements,
        )
        from .official_catalog import refresh_document

        # The complete replacement cohort may have committed in several batches.
        # Only the final source-wide verification, retirement, cache and
        # completion marker share this transaction. A deferral rolls all four
        # final actions back while retaining already validated quote batches.
        with db.transaction():
            confirm_final_source_prior(db, cor_prepared)
            confirm_stored_new(db, cor_prepared)
            insert_and_verify_retirements(db, cor_prepared)
            refresh_document(db, document_id, revision, older_only=older_only)
            db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,'official:complete',%s) ON CONFLICT DO NOTHING",
                (document_id, revision, len(values)),
            )
        return len(values)
    # A resumed batch must not hide a v1 row before its exact v2 replacement
    # is retained. Ordinary review rows above are emitted as supplied by the
    # parser; these source-backed locator retirements follow all quote batches.
    if retirement_reviews:
        with db.cursor() as cur:
            cur.executemany(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                retirement_reviews,
            )
    from .resumable_inputs import WorkDeferred
    from .worker import RUN_DEADLINE

    deadline = RUN_DEADLINE.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkDeferred(
            "Official quote batches retained; catalog completion will resume"
        )
    from .official_catalog import refresh_document

    refresh_document(db, document_id, revision, older_only=older_only)
    with db.transaction():
        db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
            "VALUES(%s,%s,'official:complete',%s) ON CONFLICT DO NOTHING",
            (document_id, revision, len(values)),
        )
    return len(values)
