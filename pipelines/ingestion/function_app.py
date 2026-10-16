"""UTC timers; 23:00 UTC is 18:00 Colombia, year-round."""

import json
import logging
import time

import azure.functions as func
from psycopg.errors import QueryCanceled

from pipelines.ingestion import worker
from pipelines.ingestion.worker import connect, run

app = func.FunctionApp()
LOG = logging.getLogger(__name__)
_coverage_cache = {"at": 0.0, "rows": None}


@app.function_name(name="BugReportDelivery")
@app.timer_trigger(schedule="0 * * * * *", arg_name="timer", run_on_startup=False, use_monitor=True)
def bug_report_delivery(timer: func.TimerRequest):
    from pipelines.ingestion.bug_reports import deliver_pending
    with connect() as db:
        db.execute("SET statement_timeout='5s'")
        result = deliver_pending(db)
    # Counts only: no message, address, configuration or report payload in logs.
    if result["retry"]:
        LOG.warning("BUG_REPORT_DELIVERY_RETRY %s", json.dumps(result))


@app.route(route="bug-report-mail-check", auth_level=func.AuthLevel.FUNCTION, methods=["POST"])
def bug_report_mail_check(req: func.HttpRequest) -> func.HttpResponse:
    """Authenticate from the Azure host without creating or sending a report."""
    from pipelines.ingestion.bug_reports import check_smtp_connection
    try:
        result = check_smtp_connection()
    except Exception as exc:
        result = {"authenticated": False, "error_class": type(exc).__name__, "message_sent": False}
    return func.HttpResponse(json.dumps(result), mimetype="application/json",
                             status_code=200 if result.get("authenticated") else 503)


def automation_health(db):
    """Report execution freshness separately from database connectivity."""
    finished, discovery, stalled = db.execute(
        """SELECT max(finished_at) FILTER(WHERE status IN ('succeeded','partial')),
        max((summary->>'discovery_finished_at')::timestamptz),
        count(*) FILTER(WHERE status='running' AND started_at<now()-interval '50 minutes')
        FROM ingestion_run WHERE started_at>now()-interval '7 days'"""
    ).fetchone()
    sources = db.execute(
        """SELECT kind,max(checked_at),max(observed_on) FILTER(WHERE status IN ('complete','processed')),
        count(*) FILTER(WHERE status='failed' AND (observed_on>=CURRENT_DATE-14 OR observed_on IS NULL)),
        count(*) FILTER(WHERE status='pending' AND observed_on>=CURRENT_DATE-14),
        count(*) FILTER(WHERE status IN ('pending','failed','awaiting-ocr')
          AND observed_on>=CURRENT_DATE-14 AND discovered_at<now()-interval '1 day')
        FROM ingestion_asset GROUP BY kind ORDER BY kind"""
    ).fetchall()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    issues = []
    if finished is None or (now - finished).total_seconds() > 3 * 3600:
        issues.append("No completed ingestion run in three hours")
    if discovery is None or (now - discovery).total_seconds() > 8 * 3600:
        issues.append("Official source discovery is over eight hours old")
    if stalled:
        issues.append("An ingestion run has exceeded its execution window")
    overdue = {row[0]: row[5] for row in sources if row[5]}
    if overdue:
        issues.append(
            f"Recent published source files remain unprocessed after one day: {overdue}"
        )
    return {
        "status": "degraded" if issues else "ok",
        "issues": issues,
        "last_completed_run": finished,
        "last_discovery": discovery,
        "sources": sources,
    }


@app.function_name(name="PipelineWatchdog")
@app.timer_trigger(
    schedule="0 45 * * * *", arg_name="timer", run_on_startup=False, use_monitor=True
)
def pipeline_watchdog(timer: func.TimerRequest):
    from pipelines.ingestion.bug_reports import delivery_health
    with connect() as db:
        db.execute("SET statement_timeout='5s'")
        health = automation_health(db)
        reports = delivery_health(db)
    if reports["overdue"]:
        LOG.error("BUG_REPORT_DELIVERY_OVERDUE %s", json.dumps(reports, default=str))
    if health["issues"]:
        LOG.error("INGESTION_AUTOMATION_DEGRADED %s", json.dumps(health, default=str))
    else:
        LOG.info("Ingestion automation heartbeat is current")


@app.function_name(name="DailyRefresh")
@app.retry(strategy="fixed_delay", max_retry_count="2", delay_interval="00:05:00")
@app.timer_trigger(
    schedule="%DAILY_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def daily_refresh(timer: func.TimerRequest):
    run("daily", limit=30)


@app.function_name(name="HistoricalBackfill")
@app.timer_trigger(
    schedule="%BACKFILL_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def historical_backfill(timer: func.TimerRequest):
    run("backfill", limit=100)


@app.function_name(name="OcrRecovery")
@app.timer_trigger(
    schedule="%OCR_SCHEDULE%", arg_name="timer", run_on_startup=False, use_monitor=True
)
def ocr_recovery(timer: func.TimerRequest):
    # A full historical queue must not consume every provider-reading window.
    # The shared ingestion lock and existing daily request cap still apply.
    run("ocr", limit=0, time_budget=600, ocr_limit=2, ocr_scan_limit=1)


@app.route(route="run-check", auth_level=func.AuthLevel.FUNCTION, methods=["POST"])
def run_check(req: func.HttpRequest) -> func.HttpResponse:
    """Authenticated, bounded execution check using the real persistent queue."""
    asset_url = req.params.get("asset_url")
    if asset_url and len(asset_url) > 4096:
        return func.HttpResponse("Invalid source URL", status_code=400)
    try:
        time_budget = int(req.params.get("time_budget", "120"))
    except ValueError:
        return func.HttpResponse("Invalid time budget", status_code=400)
    if not 30 <= time_budget <= 2100 or (time_budget > 120 and not asset_url):
        return func.HttpResponse(
            "Use 30–120 seconds, or up to 2100 seconds for one registered source",
            status_code=400,
        )
    if asset_url:
        # A typo must not look like a successful zero-record extraction.
        # This check never registers or fetches caller-supplied URLs.
        with connect() as db:
            db.execute("SET statement_timeout='5s'")
            registered = db.execute(
                "SELECT 1 FROM ingestion_asset WHERE url=%s", (asset_url,)
            ).fetchone()
        if not registered:
            return func.HttpResponse("Source URL is not registered", status_code=404)
    result = run(
        "backfill",
        limit=4,
        time_budget=time_budget,
        ocr_limit=0,
        ocr_scan_limit=0,
        asset_url=asset_url,
    )
    return func.HttpResponse(
        json.dumps(result, default=str), mimetype="application/json"
    )


def _archive_decoder_capability():
    """Inspect this worker's native decoder without reading data or settings."""
    import ctypes
    import ctypes.util

    try:
        name = ctypes.util.find_library("archive")
        if not name:
            return {"available": False, "reason": "native_library_not_found"}
        library = ctypes.CDLL(name)
        library.archive_version_string.restype = ctypes.c_char_p
        return {
            "available": True,
            "version": library.archive_version_string().decode("ascii", errors="replace"),
            "rar5_symbol": hasattr(library, "archive_read_support_format_rar5"),
        }
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}


def _pinned_city_archive_decoder_probe():
    """Qualify the packaged decoder against one retained original, read-only."""
    from pipelines.ingestion.city_rar_probe import CityRarProbeError, run_aug19_decoder_probe

    try:
        with connect() as db:
            # connect() uses autocommit. The probe's SET LOCAL READ ONLY
            # must belong to an explicit transaction before any source read.
            with db.transaction():
                result = run_aug19_decoder_probe(db)
        return {"available": True, **result}
    except CityRarProbeError as exc:
        return {"available": False, "reason": str(exc)}


@app.route(route="status", auth_level=func.AuthLevel.FUNCTION, methods=["GET"])
def status(req: func.HttpRequest) -> func.HttpResponse:
    with connect() as db:
        # Health polling must never start a full historical table scan.
        db.execute("SET statement_timeout='5s'")
        db.execute("SELECT 1").fetchone()
        runs = db.execute(
            "SELECT id,mode,started_at,finished_at,status,summary FROM ingestion_run ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
        queue = db.execute(
            "SELECT kind,status,count(*) FROM ingestion_asset GROUP BY kind,status ORDER BY kind,status"
        ).fetchall()
        ocr = db.execute(
            "SELECT status,count(*) FROM source_ocr_task GROUP BY status"
        ).fetchall()
        health = automation_health(db)
        from pipelines.ingestion.bug_reports import delivery_health
        reports = delivery_health(db)
        coverage = _coverage_cache["rows"]
        if (
            req.params.get("coverage") == "1"
            and time.monotonic() - _coverage_cache["at"] > 900
        ):
            try:
                coverage = db.execute(
                    "SELECT series,count(*),min(observed_on),max(observed_on) FROM historical_price GROUP BY series"
                ).fetchall()
                _coverage_cache.update(at=time.monotonic(), rows=coverage)
            except QueryCanceled:
                # A large audit belongs outside the HTTP worker. Return cached
                # coverage or null and keep the liveness result useful.
                _coverage_cache["at"] = time.monotonic()
    return func.HttpResponse(
        json.dumps(
            {
                "release": worker.release_fingerprint(),
                "runs": runs,
                "queue": queue,
                "coverage": coverage,
                "ocr": ocr,
                "automation": health,
                "bug_reports": reports,
                **({"archive_decoder": _archive_decoder_capability()}
                   if req.params.get("archive-capability") == "1" else {}),
                **({"pinned_city_archive_decoder": _pinned_city_archive_decoder_probe()}
                   if req.params.get("archive-decode") == "aug19-2022" else {}),
            },
            default=str,
        ),
        mimetype="application/json",
    )


@app.route(route="workbook/{id}", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
def source_workbook(req: func.HttpRequest) -> func.HttpResponse:
    """Only public source documents already exposed by the evidence API."""
    import re
    import time

    from pipelines.ingestion.workbook_archive import OriginalUnavailable, original
    from pipelines.ingestion.workbook_preview import preview_source

    did = req.route_params.get("id", "")
    if not re.fullmatch(r"[a-f0-9]{64}", did):
        return func.HttpResponse(status_code=404)
    try:
        start = int(req.params.get("start", "1"))
        limit = int(req.params.get("limit", "100"))
        sheet = req.params.get("sheet", "")[:31]
    except ValueError:
        return func.HttpResponse(status_code=400)
    public_guard = (
        "media_type IN ('application/vnd.ms-excel',"
        "'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') "
        "AND (publisher IN ('DANE','FNC') OR metadata->>'ingestion_kind' "
        "LIKE 'international-%%' OR metadata->>'ingestion_kind' LIKE 'colombia-%%' "
        "OR metadata->>'ingestion_kind'='dane-weekly-xlsx')"
    )
    guard_started = time.monotonic()
    with connect() as db:
        row = db.execute(
            f"SELECT media_type FROM source_document WHERE id=%s AND {public_guard}",
            (did,),
        ).fetchone()
    if not row:
        return func.HttpResponse(status_code=404)
    guard_ms = (time.monotonic() - guard_started) * 1000

    def pg_original():
        with connect() as db:
            retained = db.execute(
                f"SELECT content FROM source_document WHERE id=%s AND media_type=%s AND {public_guard}",
                (did, row[0]),
            ).fetchone()
            return bytes(retained[0]) if retained else None

    try:
        preview_started = time.monotonic()
        result = preview_source(did, lambda: original(did, row[0], pg_original), sheet, start, limit)
    except OriginalUnavailable:
        return func.HttpResponse(
            json.dumps({"error": "Documento no disponible."}),
            status_code=503,
            mimetype="application/json",
        )
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Hoja no disponible."}),
            status_code=404,
            mimetype="application/json",
        )
    return func.HttpResponse(
        result,
        mimetype="application/json",
        headers={
            "Cache-Control": "public,max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Server-Timing": f"source_guard;dur={guard_ms:.1f},workbook_preview;dur={(time.monotonic() - preview_started) * 1000:.1f}",
        },
    )
