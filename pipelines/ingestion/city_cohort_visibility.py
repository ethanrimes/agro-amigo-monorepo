"""Source-local visibility and acceptance rules for DANE city ZIP cohorts.

The query protocol keeps candidate revisions out of published views until a
parser-produced proof verifies the complete source cohort. Historical source
and price records remain append-only when a newer cohort is accepted.
"""

from __future__ import annotations

import hashlib
import json
import io
import re
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse
from typing import Callable


# Inline this document-key predicate into the published price view and every
# raw query that can return quote values. Existing unregistered rows remain
# visible. Both branches use source_archive_member(document_id,archive_id).
PUBLISHED_DOCUMENT_PREDICATE = """(
  NOT EXISTS (
    SELECT 1 FROM source_archive_member enrolled_member
    JOIN dane_city_revision_source enrolled_source
      ON enrolled_source.archive_id=enrolled_member.archive_id
    WHERE enrolled_member.document_id={document_alias}.document_id
  )
  OR EXISTS (
    SELECT 1 FROM source_archive_member active_member
    JOIN dane_city_cohort_current active_head
      ON active_head.archive_id=active_member.archive_id
    WHERE active_member.document_id={document_alias}.document_id
  )
  OR EXISTS (
    SELECT 1 FROM ingestion_asset direct_asset
    WHERE direct_asset.document_id={document_alias}.document_id
      AND direct_asset.kind='city-pdf'
  )
  OR EXISTS (
    SELECT 1 FROM source_archive_member legacy_member
    WHERE legacy_member.document_id={document_alias}.document_id
      AND NOT EXISTS (
        SELECT 1 FROM dane_city_revision_source enrolled_legacy_parent
        WHERE enrolled_legacy_parent.archive_id=legacy_member.archive_id
      )
  )
)"""


_VALIDATED_PROOF_SEAL = object()


@dataclass(frozen=True, init=False)
class CohortProof:
    """Opaque proof minted only by validate_complete_city_zip_cohort()."""

    source_url: str
    observed_on: date
    archive_id: str
    source_sha256: str
    processor_version: str
    member_count: int
    price_count: int
    classification_count: int
    cohort_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *, source_url, observed_on, archive_id, source_sha256,
                 processor_version, member_count, price_count,
                 classification_count, cohort_sha256, _seal=None):
        if _seal is not _VALIDATED_PROOF_SEAL:
            raise TypeError("CohortProof can only be minted by full native validation")
        for name, value in locals().copy().items():
            if name not in {"self", "_seal"}:
                object.__setattr__(self, name, value)
        object.__setattr__(self, "_seal", _seal)

    def validate(self) -> None:
        if self._seal is not _VALIDATED_PROOF_SEAL:
            raise ValueError("cohort proof was not produced by native validation")
        if not isinstance(self.observed_on, date) or isinstance(self.observed_on, datetime):
            raise ValueError("cohort proof day must be a date")
        parsed = urlparse(self.source_url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if (parsed.scheme != "https" or parsed.hostname != "www.dane.gov.co"
                or port not in (None, 443) or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or not parsed.path.startswith("/files/")
                or not parsed.path.lower().endswith(".zip")):
            raise ValueError("cohort proof source URL is not official and exact")
        if (not isinstance(self.archive_id, str) or not isinstance(self.source_sha256, str)
                or not re.fullmatch(r"[a-f0-9]{64}", self.archive_id)
                or not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256)
                or not isinstance(self.cohort_sha256, str)
                or not re.fullmatch(r"[a-f0-9]{64}", self.cohort_sha256)):
            raise ValueError("cohort proof hashes are malformed")
        if self.archive_id != self.source_sha256:
            raise ValueError("cohort proof archive/source hashes differ")
        if not isinstance(self.processor_version, str) or not self.processor_version:
            raise ValueError("cohort proof processor version is empty")
        counts = (self.member_count, self.price_count, self.classification_count)
        if any(not isinstance(count, int) or isinstance(count, bool) for count in counts):
            raise ValueError("cohort proof counts must be integer values")
        if min(counts) <= 0:
            raise ValueError("cohort proof is empty")
        if self.price_count != self.classification_count:
            raise ValueError("price and classification cohorts differ")


@dataclass(frozen=True)
class RosterMember:
    entry_name: str
    header_offset: int
    crc: int
    file_size: int


def validate_member_roster(zip_body: bytes, *, max_members=500,
                           max_uncompressed_bytes=512 * 1024 * 1024):
    """Validate complete PDF roster while retaining literal (including NFD) names."""
    with zipfile.ZipFile(io.BytesIO(zip_body)) as archive:
        all_files = [item for item in archive.infolist() if not item.is_dir()]
        infos = [item for item in all_files if item.filename.lower().endswith(".pdf")]
        if not infos or len(infos) > max_members:
            raise ValueError("city ZIP PDF member count is outside its bound")
        if sum(item.file_size for item in infos) > max_uncompressed_bytes:
            raise ValueError("city ZIP uncompressed PDF bytes exceed the bound")
        raw_names = set()
        members = []
        for item in all_files:
            name = item.filename
            pieces = name.replace("\\", "/").split("/")
            if (not name or name.startswith(("/", "\\")) or "\x00" in name
                    or any(part in ("", ".", "..") for part in pieces)):
                raise ValueError("unsafe city ZIP member name")
            if name in raw_names:
                raise ValueError("duplicate literal city ZIP member name")
            raw_names.add(name)
            if item in infos:
                members.append(RosterMember(name, item.header_offset, item.CRC, item.file_size))
        return tuple(members)


def retain_member_roster(db, zip_body: bytes, archive_id: str, retain_original):
    """Retain exact children and mappings before any parsing/OCR extraction.

    `retain_original(db, body, literal_name, archive_id)` must call the existing
    SHA-bound `worker.archive` path only. This callback is intentionally
    injectable so pure tests can prove ordering without Blob or database I/O.
    """
    roster = validate_member_roster(zip_body)
    retained = []
    with zipfile.ZipFile(io.BytesIO(zip_body)) as archive:
        by_name = {member.entry_name: member for member in roster}
        for name, metadata in by_name.items():
            content = archive.read(name)
            if len(content) != metadata.file_size:
                raise ValueError("city ZIP member length changed while retaining")
            did = retain_original(db, content, name, archive_id)
            if did != hashlib.sha256(content).hexdigest():
                raise ValueError("retained city member ID differs from exact body hash")
            db.execute(
                """INSERT INTO source_archive_member(archive_id,entry_name,document_id)
                   VALUES(%s,%s,%s) ON CONFLICT(archive_id,entry_name) DO NOTHING""",
                (archive_id, name, did),
            )
            mapped = db.execute(
                """SELECT document_id FROM source_archive_member
                   WHERE archive_id=%s AND entry_name=%s""",
                (archive_id, name),
            ).fetchone()
            if mapped is None or mapped[0] != did:
                raise ValueError("retained city member map differs from exact child hash")
            retained.append((metadata, did))
    return tuple(retained)


def _retained_parent(db, source_url: str, observed_on: date, archive_id: str):
    parsed = urlparse(source_url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (parsed.scheme != "https" or parsed.hostname != "www.dane.gov.co"
            or port not in (None, 443) or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.startswith("/files/")
            or not parsed.path.lower().endswith(".zip")):
        raise ValueError("source URL is not an exact official DANE ZIP URL")
    row = db.execute(
        """SELECT title,publisher,source_url,media_type,kind,reference_period,
                  content,metadata
           FROM source_document WHERE id=%s""",
        (archive_id,),
    ).fetchone()
    if row is None:
        raise ValueError("candidate parent original is absent")
    title, publisher, stored_url, media, kind, reference, content, metadata = row
    body = bytes(content)
    if (hashlib.sha256(body).hexdigest() != archive_id
            or stored_url != source_url
            or media != "application/zip"
            or kind != "original"
            or publisher != "DANE"
            or reference != observed_on.isoformat()
            or not isinstance(metadata, dict)
            or metadata.get("retention") != "permanent"
            or metadata.get("ingestion_kind") != "city-zip"
            or metadata.get("original_filename") != PurePosixPath(parsed.path).name
            or title != "DANE - " + PurePosixPath(parsed.path).name):
        raise ValueError("parent source identity/metadata/body mismatch")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("parent title is missing")
    return body


def register_parent_before_members(db, source_url: str, observed_on: date,
                                   archive_id: str) -> None:
    """Verify an already-retained ZIP parent and register it before child work."""
    _retained_parent(db, source_url, observed_on, archive_id)
    db.execute(
        """INSERT INTO dane_city_revision_source
             (source_url,observed_on,archive_id,source_sha256)
           VALUES(%s,%s,%s,%s) ON CONFLICT(source_url,observed_on,archive_id)
           DO NOTHING""",
        (source_url, observed_on, archive_id, archive_id),
    )


def _source_day_lock_key(db, source_url: str, observed_on: date) -> int:
    return db.execute(
        "SELECT hashtextextended('dane-city-cohort:'||%s||':'||%s,0)",
        (source_url, observed_on.isoformat()),
    ).fetchone()[0]


def _require_refresh_request(db, source_url: str, observed_on: date,
                             request_id: int) -> None:
    if not isinstance(request_id, int) or isinstance(request_id, bool) or request_id <= 0:
        raise ValueError("refresh request identity is invalid")
    row = db.execute(
        "SELECT source_url,observed_on,request_reason FROM dane_city_refresh_request "
        "WHERE request_id=%s", (request_id,),
    ).fetchone()
    if row is None or row[:2] != (source_url, observed_on) or row[2] not in (
        "label_change", "periodic_byte_verification", "worker_observed_body_change",
    ):
        raise ValueError("refresh request is not bound to this exact source and day")


@contextmanager
def lock_and_seed_accepted_head(db, source_url: str, observed_on: date,
                                request_id: int):
    """Hold one source/day transaction lock and ensure a verified old head.

    First-time enrollment is allowed only from an exact completed asset linked
    to a durable refresh request. The old source is fully reparsed and matched
    against every stored price, classification, and member checkpoint before
    it becomes the accepted head. Existing heads are revalidated by their own
    recorded parser version, independent of the mutable last-attempt pointer.
    The context remains open so candidate publication can compare and advance
    the captured head in this same transaction.
    """
    if not isinstance(observed_on, date) or isinstance(observed_on, datetime):
        raise ValueError("refresh source day must be a date")
    if not _official_zip_url(source_url):
        raise ValueError("refresh source URL is not an exact DANE ZIP URL")
    lock_key = _source_day_lock_key(db, source_url, observed_on)
    db.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
    try:
        with db.transaction():
            _require_refresh_request(db, source_url, observed_on, request_id)
            current = _current(db, source_url, observed_on, lock=True)
            if current is None:
                asset = db.execute(
                    "SELECT kind,observed_on,status,document_id,records,processor_version "
                    "FROM ingestion_asset WHERE url=%s FOR UPDATE", (source_url,),
                ).fetchone()
                if (asset is None or asset[0:2] != ("city-zip", observed_on)
                        or not isinstance(asset[3], str)
                        or not re.fullmatch(r"[a-f0-9]{64}", asset[3])):
                    raise ValueError("first enrollment requires the exact retained source asset")
                old_archive_id = asset[3]
                # The old source is legacy-visible until a complete head exists.
                # Verify its original identity even when the former parse ended in
                # review/failed, but never enroll a partial cohort as accepted.
                _retained_parent(db, source_url, observed_on, old_archive_id)
                if (asset[2] == "complete" and isinstance(asset[4], int)
                        and not isinstance(asset[4], bool) and asset[4] > 0
                        and isinstance(asset[5], str) and asset[5]):
                    try:
                        proof = validate_complete_city_zip_cohort(
                            db, source_url, observed_on, old_archive_id, asset[5],
                            require_current_complete_asset=True,
                        )
                    except ValueError as exc:
                        # A completed legacy source that cannot prove its full
                        # prior cohort is not a safe baseline for a changed ZIP.
                        # Keep the candidate retained but reject publication;
                        # do not create a second visible legacy cohort.
                        raise ValueError(
                            "completed legacy source cannot be enrolled as a verified head"
                        ) from exc
                    else:
                        register_parent_before_members(db, source_url, observed_on, old_archive_id)
                        acceptance_id = accept_full_cohort(
                            db, proof, expected_head_archive_id=None,
                            finalize_asset=lambda: None,
                        )
                        current = (acceptance_id, old_archive_id)
                else:
                    current = None
            else:
                accepted = db.execute(
                    "SELECT processor_version FROM dane_city_cohort_acceptance "
                    "WHERE acceptance_id=%s AND source_url=%s AND observed_on=%s "
                    "AND archive_id=%s",
                    (current[0], source_url, observed_on, current[1]),
                ).fetchone()
                if accepted is None or not isinstance(accepted[0], str) or not accepted[0]:
                    raise ValueError("accepted head has no exact parser-version witness")
                validate_complete_city_zip_cohort(
                    db, source_url, observed_on, current[1], accepted[0],
                )
        # Do not hold an outer transaction across parsing. Exact originals and
        # member links must commit before expensive extraction so an exception
        # cannot roll their retained evidence back. The session advisory lock
        # still serializes this source/day until final acceptance or failure.
        # A complete-status legacy source can fail native parity. In that case
        # it remains unregistered/legacy-visible and there is intentionally no
        # accepted head to capture; a separately validated candidate may still
        # establish the first head.
        yield current[1] if current is not None else None
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))


def register_candidate_before_members(db, source_url: str, observed_on: date,
                                      archive_id: str, *, captured_head: str | None) -> None:
    """Register a retained candidate only after an accepted baseline exists."""
    if captured_head is not None and (
        not isinstance(captured_head, str) or not re.fullmatch(r"[a-f0-9]{64}", captured_head)
    ):
        raise ValueError("candidate registration head is malformed")
    with db.transaction():
        current = _current(db, source_url, observed_on, lock=True)
        actual = current[1] if current else None
        if actual != captured_head:
            raise ValueError("accepted source head changed before candidate registration")
        register_parent_before_members(db, source_url, observed_on, archive_id)


def candidate_only_child(db, document_id: str) -> bool:
    """True only for a staged child with no active, direct, or legacy use.

    This is the OCR publication guard. Staging a new parent cannot hide a child
    still used by the accepted parent, a direct city-PDF asset, or any legacy
    unregistered archive.
    """
    if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{64}", document_id):
        raise ValueError("city child document identity is malformed")
    row = db.execute(
        """SELECT EXISTS (
             SELECT 1 FROM source_archive_member m JOIN dane_city_revision_source s
               ON s.archive_id=m.archive_id WHERE m.document_id=%s
           ), EXISTS (
             SELECT 1 FROM source_archive_member m JOIN dane_city_cohort_current h
               ON h.archive_id=m.archive_id WHERE m.document_id=%s
           ), EXISTS (
             SELECT 1 FROM ingestion_asset a WHERE a.document_id=%s AND a.kind='city-pdf'
           ), EXISTS (
             SELECT 1 FROM source_archive_member m WHERE m.document_id=%s
               AND NOT EXISTS (SELECT 1 FROM dane_city_revision_source s
                               WHERE s.archive_id=m.archive_id)
           )""",
        (document_id, document_id, document_id, document_id),
    ).fetchone()
    if row is None or len(row) != 4:
        raise ValueError("city child enrollment lookup failed")
    enrolled, accepted, direct, legacy = row
    return bool(enrolled and not accepted and not direct and not legacy)


def _official_zip_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.hostname == "www.dane.gov.co"
            and port in (None, 443) and parsed.username is None
            and parsed.password is None and not parsed.query and not parsed.fragment
            and parsed.path.startswith("/files/") and parsed.path.lower().endswith(".zip"))


def validate_complete_city_zip_cohort(db, source_url: str, observed_on: date,
                                      archive_id: str, processor_version: str,
                                      *, require_current_complete_asset=False) -> CohortProof:
    from pipelines.ingestion import city_reports
    from pipelines.ingestion.ocr import needs_ocr
    from pipelines.ingestion.worker import date_from_text

    return _validate_complete_city_zip_cohort(
        db, source_url, observed_on, archive_id, processor_version,
        parse_member=city_reports.parse_archived_city_pdf,
        member_step=city_reports._member_step,
        parity=city_reports._publication_parity,
        member_printed_days=lambda body, did, page_numbers: _member_printed_days(
            db, body, did, page_numbers, needs_ocr=needs_ocr,
            date_from_text=date_from_text,
        ),
        require_current_complete_asset=require_current_complete_asset,
    )


def _member_printed_days(db, body: bytes, document_id: str, page_numbers, *, needs_ocr,
                         date_from_text):
    """Read first/priced-page dates using only native text or agreed cached OCR."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(body)) as pdf:
        if not pdf.pages:
            return {}
        requested = set(page_numbers) | {1}
        if any(not isinstance(number, int) or isinstance(number, bool)
               or number < 1 or number > len(pdf.pages) for number in requested):
            raise ValueError("priced row references a missing PDF page")
        from pipelines.ingestion.ocr import (
            VERSION as OCR_VERSION, compare_city_price_readings,
        )
        results = {}
        for number in sorted(requested):
            page = pdf.pages[number - 1]
            text = page.extract_text() or ""
            if needs_ocr(page, text):
                # Validation must never enqueue a new OCR job. A successful
                # native parse already requires cached agreement for OCR pages.
                cached = db.execute(
                    """SELECT r.result FROM source_ocr_task t
                       JOIN source_ocr_result r ON r.image_id=t.image_id
                       WHERE t.document_id=%s AND t.source_page=%s AND r.version=%s
                       ORDER BY r.reading""",
                    (document_id, number, OCR_VERSION),
                ).fetchall()
                if len(cached) != 2:
                    results[number] = None
                    continue
                first, second = cached[0][0], cached[1][0]
                if not compare_city_price_readings(
                    first, second, native_heading=pdf.pages[0].extract_text() or None,
                ):
                    results[number] = None
                    continue
                text = first.get("text", "") if isinstance(first, dict) else ""
            results[number] = date_from_text(text)
        return results


def _validate_complete_city_zip_cohort(
    db, source_url: str, observed_on: date, archive_id: str,
    processor_version: str, *, parse_member, member_step, parity,
    member_printed_days,
    require_current_complete_asset=False,
) -> CohortProof:
    """Reparse every exact retained member and compare all immutable DB rows.

    This does not trust caller-supplied booleans or row counts. It uses the
    normal city parser (including verified cached OCR when present), checks
    exact parent/member metadata, requires every member checkpoint, and calls
    the maintained full-tuple/category parity comparison in read-only form.
    It intentionally fails closed on cross-day members; reviewed exceptions
    require their own exact source rule before an enrolled cohort can use them.
    """
    parent_body = _retained_parent(db, source_url, observed_on, archive_id)
    roster = validate_member_roster(parent_body)
    mapped = db.execute(
        """SELECT m.entry_name,m.document_id,d.title,d.publisher,d.source_url,
                  d.media_type,d.kind,d.reference_period,d.content,d.metadata
           FROM source_archive_member m
           JOIN source_document d ON d.id=m.document_id
           WHERE m.archive_id=%s ORDER BY m.entry_name""",
        (archive_id,),
    ).fetchall()
    if len(mapped) != len(roster):
        raise ValueError("retained city member mapping count differs from source roster")
    mapped_by_name = {row[0]: row for row in mapped}
    if len(mapped_by_name) != len(mapped) or set(mapped_by_name) != {
        item.entry_name for item in roster
    }:
        raise ValueError("retained city member names differ from source roster")
    with zipfile.ZipFile(io.BytesIO(parent_body)) as archive:
        info_by_name = {item.filename: item for item in archive.infolist()
                        if not item.is_dir() and item.filename.lower().endswith(".pdf")}
        cohort_records = []
        price_count = 0
        class_count = 0
        for member in roster:
            row = mapped_by_name[member.entry_name]
            (_, child_id, title, publisher, stored_url, media_type, kind,
             reference_period, content, metadata) = row
            child_body = bytes(content)
            if (hashlib.sha256(child_body).hexdigest() != child_id
                    or publisher != "DANE" or stored_url != source_url
                    or media_type != "application/pdf" or kind != "original"
                    or reference_period != "Serie histórica completa"
                    or not isinstance(metadata, dict)
                    or metadata.get("retention") != "permanent"
                    or metadata.get("ingestion_kind") != "city-pdf"
                    or not isinstance(metadata.get("original_filename"), str)
                    or not metadata.get("original_filename")
                    or PurePosixPath(metadata["original_filename"]).name
                       != metadata["original_filename"]
                    or not isinstance(metadata.get("archive_entry"), str)
                    or PurePosixPath(metadata["archive_entry"]).is_absolute()
                    or ".." in PurePosixPath(metadata["archive_entry"]).parts
                    or PurePosixPath(metadata["archive_entry"]).name
                       != metadata["original_filename"]
                    or title != "DANE - " + metadata["original_filename"]):
                raise ValueError("retained city child identity or metadata mismatch")
            # source_document is SHA-deduplicated and immutable. A byte-identical
            # child can be shared by an older accepted ZIP, so its original
            # `parents` metadata may name that first parent. The exact mapping
            # row above, not rewritten source metadata, binds this member to the
            # candidate parent.
            expected_rows = list(parse_member(
                db, child_body, child_id, observed_on,
            ))
            priced_pages = set()
            for price in expected_rows:
                locator_match = re.match(r"PDF page ([1-9][0-9]*),", str(price[0]))
                if locator_match is None:
                    raise ValueError("native city row locator has no PDF page identity")
                priced_pages.add(int(locator_match[1]))
            # Check the first-page identity even for an empty grid, since such
            # a member has no price tuple to carry a day. Archive members can
            # legitimately predate the ZIP publication day; rows must carry
            # that member's date and later priced pages may not contradict it.
            printed_days = member_printed_days(child_body, child_id, priced_pages)
            printed_day = printed_days.get(1)
            if printed_day is None or printed_day > observed_on:
                raise ValueError("retained city member first-page date is absent or future")
            if any(price[1] != printed_day for price in expected_rows):
                raise ValueError("retained city member rows differ from its printed day")
            if any(day is not None and day != printed_day
                   for number, day in printed_days.items() if number in priced_pages):
                raise ValueError("priced city page prints a date different from its member")
            checkpoint = db.execute(
                """SELECT records FROM ingestion_checkpoint
                   WHERE document_id=%s AND processor_version=%s AND step=%s""",
                (archive_id, processor_version,
                 member_step(info_by_name[member.entry_name], observed_on)),
            ).fetchone()
            if checkpoint is None or checkpoint[0] != len(expected_rows):
                raise ValueError("retained city member lacks its exact complete checkpoint")
            _, _, detail = parity(
                db, child_id, expected_rows, require_all=True,
            )
            if (detail["difference_count"] != 0
                    or detail["native_count"] != len(expected_rows)
                    or detail["stored_count"] != len(expected_rows)
                    or detail["classification_count"] != len(expected_rows)):
                raise ValueError("retained city member rows/classifications differ from native parse")
            price_count += len(expected_rows)
            class_count += len(expected_rows)
            cohort_records.append((member.entry_name, child_id, expected_rows))
    if not price_count or price_count != class_count:
        raise ValueError("retained city source has no complete typed cohort")
    if require_current_complete_asset:
        asset = db.execute(
            """SELECT kind,observed_on,status,document_id,records
               FROM ingestion_asset WHERE url=%s""",
            (source_url,),
        ).fetchone()
        if asset != ("city-zip", observed_on, "complete", archive_id, price_count):
            raise ValueError("baseline is not the exact complete current city source")
    return CohortProof(
        source_url=source_url, observed_on=observed_on, archive_id=archive_id,
        source_sha256=archive_id, processor_version=processor_version,
        member_count=len(roster), price_count=price_count,
        classification_count=class_count,
        cohort_sha256=cohort_digest(cohort_records),
        _seal=_VALIDATED_PROOF_SEAL,
    )


def _current(db, source_url: str, observed_on: date, *, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    return db.execute(
        """SELECT acceptance_id,archive_id FROM dane_city_cohort_current
           WHERE source_url=%s AND observed_on=%s""" + suffix,
        (source_url, observed_on),
    ).fetchone()


def accept_full_cohort(db, proof: CohortProof, *, expected_head_archive_id: str | None,
                       finalize_asset: Callable[[], None]):
    """Atomically append proof and move head after checking stale work.

    Caller must hold the same source/day transaction advisory lock during the
    entire parse and must already have inserted every raw row/checkpoint in this
    final transaction. This helper refuses count-only proofs.
    """
    proof.validate()
    if not callable(finalize_asset):
        raise ValueError("asset finalizer is required for atomic cohort acceptance")
    with db.transaction():
        lock_key = db.execute(
            "SELECT hashtextextended('dane-city-cohort:'||%s||':'||%s,0)",
            (proof.source_url, proof.observed_on.isoformat()),
        ).fetchone()[0]
        db.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        _retained_parent(db, proof.source_url, proof.observed_on, proof.archive_id)
        registered = db.execute(
            """SELECT 1 FROM dane_city_revision_source
               WHERE source_url=%s AND observed_on=%s AND archive_id=%s
                 AND source_sha256=%s""",
            (proof.source_url, proof.observed_on, proof.archive_id, proof.source_sha256),
        ).fetchone()
        if registered is None:
            raise ValueError("candidate parent was not registered before member processing")
        old = _current(db, proof.source_url, proof.observed_on, lock=True)
        actual_head = old[1] if old else None
        if actual_head != expected_head_archive_id:
            raise ValueError("accepted cohort head changed during candidate parse")
        if old and actual_head == proof.archive_id:
            existing = db.execute(
                """SELECT cohort_sha256,processor_version,member_count,price_count,
                          classification_count
                   FROM dane_city_cohort_acceptance WHERE acceptance_id=%s""",
                (old[0],),
            ).fetchone()
            if existing == (proof.cohort_sha256, proof.processor_version,
                            proof.member_count, proof.price_count,
                            proof.classification_count):
                return old[0]
        acceptance_id = db.execute(
            """INSERT INTO dane_city_cohort_acceptance
                 (source_url,observed_on,archive_id,source_sha256,processor_version,
                  member_count,price_count,classification_count,cohort_sha256)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING acceptance_id""",
            (proof.source_url, proof.observed_on, proof.archive_id, proof.source_sha256,
             proof.processor_version, proof.member_count, proof.price_count,
             proof.classification_count, proof.cohort_sha256),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO dane_city_cohort_current
                 (source_url,observed_on,acceptance_id,archive_id)
               VALUES(%s,%s,%s,%s)
               ON CONFLICT(source_url,observed_on) DO UPDATE SET
                 acceptance_id=excluded.acceptance_id,
                 archive_id=excluded.archive_id,updated_at=clock_timestamp()""",
            (proof.source_url, proof.observed_on, acceptance_id, proof.archive_id),
        )
        # The asset pointer/status and public head change share one transaction.
        # The caller must use a conditional UPDATE and raise unless one row
        # matches the captured pre-parse state.
        finalize_asset()
        return acceptance_id


def cohort_digest(rows) -> str:
    """Stable utility for expected tuple witnesses; not a parser validator."""
    serialized = json.dumps(list(rows), ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()

