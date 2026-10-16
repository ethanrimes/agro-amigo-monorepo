"""Worker integration for verified DANE city ZIP publication cohorts.

This module connects normal and changed-body city ZIP processing to the
source-local accepted-head protocol. A publication head advances only after
the retained source, archive roster, parsed rows, and cohort proof agree.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from .city_cohort_visibility import (
    accept_full_cohort,
    lock_and_seed_accepted_head,
    register_candidate_before_members,
    register_parent_before_members,
    retain_member_roster,
    validate_complete_city_zip_cohort,
)


def _exact_refresh_request(db, request_id: int, source_url: str, day: date) -> None:
    row = db.execute(
        "SELECT source_url,observed_on,request_reason FROM dane_city_refresh_request "
        "WHERE request_id=%s", (request_id,),
    ).fetchone()
    if row is None or row[0:2] != (source_url, day) or row[2] not in (
        "label_change", "periodic_byte_verification", "worker_observed_body_change",
    ):
        raise ValueError("refresh request differs from candidate URL/day")


def _retained_body(db, source_url: str, day: date, document_id: str) -> bytes:
    if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{64}", document_id):
        raise ValueError("candidate document ID is malformed")
    row = db.execute(
        "SELECT content FROM source_document WHERE id=%s", (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError("candidate parent original is missing")
    body = bytes(row[0])
    if hashlib.sha256(body).hexdigest() != document_id:
        raise ValueError("candidate parent body differs from its SHA identity")
    # Full metadata/publisher/reference/url binding is rechecked by parent
    # registration and the full native validator.
    return body


def publish_retained_candidate(
    db, *, request_id: int, source_url: str, day: date,
    candidate_id: str, parser_version: str, prior_asset_id: str,
    prior_asset_parser_version: str,
    etag: str | None = None, last_modified: str | None = None,
    on_published=None,
) -> int:
    """Retain all exact children, parse normally, then atomically switch head.

    The candidate parent must already be durably retained and linked to this
    request. `worker.archive` is used only for child originals; tests replace
    its Blob boundary and prove the exact bytes/metadata are written locally.
    Existing `city_reports.publish_city_zip` remains the parser and checkpoint
    owner. Candidate parse rows are hidden by the source-document predicate
    until the final acceptance transaction moves the head.
    """
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValueError("city candidate day must be a date")
    if not isinstance(parser_version, str) or not parser_version:
        raise ValueError("city candidate parser version is required")
    if not isinstance(prior_asset_id, str) or not re.fullmatch(r"[a-f0-9]{64}", prior_asset_id):
        raise ValueError("prior city asset identity is malformed")
    from pipelines.ingestion import city_reports, worker
    from pipelines.ingestion.city_exact_source_dispatch_v44_b import maybe_publish_exact_city_zip

    body = _retained_body(db, source_url, day, candidate_id)
    _exact_refresh_request(db, request_id, source_url, day)
    with lock_and_seed_accepted_head(db, source_url, day, request_id) as captured_head:
        asset = db.execute(
            "SELECT kind,observed_on,status,document_id,processor_version "
            "FROM ingestion_asset WHERE url=%s FOR UPDATE", (source_url,),
        ).fetchone()
        if asset != ("city-zip", day, "complete", prior_asset_id,
                     prior_asset_parser_version):
            raise ValueError("city asset changed before retained candidate processing")
        if captured_head is not None and captured_head != prior_asset_id:
            raise ValueError("accepted source head differs from the current completed asset")
        register_candidate_before_members(
            db, source_url, day, candidate_id, captured_head=captured_head,
        )
        # This is one committed retention transaction, completed before any
        # PDF extraction. A failed parser leaves parent, all children and every
        # literal member mapping available for exact retry.
        with db.transaction():
            retained = retain_member_roster(
                db, body, candidate_id,
                lambda conn, data, name, parent: worker.archive(
                    conn, source_url, data, "city-pdf", None,
                    filename=name, parents=[parent],
                ),
            )
        if not retained:
            raise ValueError("city ZIP has no retained PDF members")

        exact_count = maybe_publish_exact_city_zip(db, source_url, body, candidate_id)
        if exact_count is None:
            count = city_reports.publish_city_zip(
                db, body, candidate_id, source_url, day,
                processor_version=parser_version,
            )
        else:
            count = exact_count
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("changed city ZIP did not produce a complete typed cohort")

        proof = validate_complete_city_zip_cohort(
            db, source_url, day, candidate_id, parser_version,
        )
        if proof.price_count != count:
            raise ValueError("city publisher count differs from full native cohort proof")

        def finalize_asset():
            db.execute(
                """INSERT INTO product(id,name,category)
                SELECT DISTINCT ON (r.product_id) r.product_id,r.product_name,
                  coalesce(c.category_path[1],r.category)
                FROM regional_price r JOIN source_archive_member m ON m.document_id=r.document_id
                LEFT JOIN regional_classification c ON c.document_id=r.document_id
                  AND c.source_locator=r.source_locator
                WHERE m.archive_id=%s ORDER BY r.product_id,r.observed_on DESC
                ON CONFLICT DO NOTHING""", (candidate_id,),
            )
            update = db.execute(
                """UPDATE ingestion_asset SET document_id=%s,status='complete',records=%s,
                   processor_version=%s,checked_at=now(),attempts=attempts+1,error=NULL,
                   http_etag=coalesce(%s,http_etag),
                   http_last_modified=coalesce(%s,http_last_modified)
                   WHERE url=%s AND kind='city-zip' AND observed_on=%s
                     AND document_id=%s AND status='complete'
                     AND processor_version=%s""",
                (candidate_id, proof.price_count, parser_version, etag, last_modified,
                 source_url, day, prior_asset_id, prior_asset_parser_version),
            )
            if update.rowcount != 1:
                raise ValueError("city asset changed before accepted-head commit")
            if on_published is not None:
                on_published(proof)

        accept_full_cohort(
            db, proof, expected_head_archive_id=captured_head,
            finalize_asset=finalize_asset,
        )
        return proof.price_count


def retain_normal_changed_zip(db, *, source_url: str, day: date,
                              candidate_id: str) -> int:
    """Send a normally discovered changed ZIP through the same head protocol.

    The parent is already durably retained by the ordinary downloader. This
    function only creates the audit request/link, then lets the regular
    retained-candidate worker prove and publish it. It never parses candidate
    rows through the legacy path.
    """
    from .city_page_refresh import (
        _official_city_zip_url,
        _link_candidate_original,
        process_refresh_request,
    )
    from .city_cohort_visibility import _source_day_lock_key, register_parent_before_members
    if not _official_city_zip_url(source_url):
        raise ValueError("normal changed city source URL is not official")
    lock_key = _source_day_lock_key(db, source_url, day)
    db.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
    try:
        register_parent_before_members(db, source_url, day, candidate_id)
        with db.transaction():
            request_id = db.execute(
                """INSERT INTO dane_city_refresh_request
                     (source_url,observed_on,request_reason)
                   VALUES(%s,%s,'worker_observed_body_change') RETURNING request_id""",
                (source_url, day),
            ).fetchone()[0]
            _link_candidate_original(db, request_id, day, candidate_id)
        outcome = process_refresh_request(
            db, request_id,
            fetcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("normal retained candidate must not fetch again")),
        )
        if outcome == "published":
            row = db.execute(
                "SELECT records FROM ingestion_asset WHERE url=%s AND document_id=%s",
                (source_url, candidate_id),
            ).fetchone()
            return int(row[0]) if row else 0
        return 0
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))


def accept_completed_first_city_zip(db, *, source_url: str, day: date,
                                    archive_id: str, parser_version: str) -> bool:
    """Enroll a normal first/unfinished ingestion only after full validation."""
    from .city_cohort_visibility import _source_day_lock_key, _current

    key = _source_day_lock_key(db, source_url, day)
    db.execute("SELECT pg_advisory_lock(%s)", (key,))
    try:
        with db.transaction():
            asset = db.execute(
                "SELECT kind,observed_on,status,document_id,records,processor_version "
                "FROM ingestion_asset WHERE url=%s FOR UPDATE", (source_url,),
            ).fetchone()
            if (asset is None or asset[0:4] !=
                    ("city-zip", day, "complete", archive_id)
                    or not isinstance(asset[4], int) or asset[4] <= 0
                    or asset[5] != parser_version):
                return False
            current = _current(db, source_url, day, lock=True)
            if current is not None:
                return current[1] == archive_id
            register_parent_before_members(db, source_url, day, archive_id)
            proof = validate_complete_city_zip_cohort(
                db, source_url, day, archive_id, parser_version,
                require_current_complete_asset=True,
            )
            accept_full_cohort(
                db, proof, expected_head_archive_id=None, finalize_asset=lambda: None,
            )
            return True
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (key,))


def should_publish_ocr_page(db, document_id: str) -> bool:
    """Hook used immediately before the existing city OCR price publisher."""
    from .city_cohort_visibility import candidate_only_child

    return not candidate_only_child(db, document_id)
