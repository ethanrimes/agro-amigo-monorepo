"""Source-bound publication bridge for DANE's retained Aug 19 2022 RAR5.

The bridge never stores a synthetic ZIP or changes the retained RAR parent.
It decodes the exact pinned source into in-memory PDF bodies and passes a
transient, uncompressed ZIP byte string to the established city ZIP publisher.
No other URL, source id, date, media type, or archive body is eligible.

The worker applies ``aug19_processor_version`` only to this exact city-zip URL,
prefers its verified retained parent before HTTP, and dispatches publication
through ``publish_exact_aug19_rar``. The source-local ``city-member:`` checkpoint
namespace cannot replay other city archives. Completed members are reparsed
and compared with their published tuples before a replay may skip them.
This bridge is never a fallback for a nonmatching URL or hash.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import zipfile

from . import city_rar_decoder as decoder

AUG19_DAY = date(2022, 8, 19)
PROCESSOR_VERSION_SUFFIX = ":aug19-rar5-publication-v1"
_CHILD_REFERENCE_PERIOD = "Serie histórica completa"


class CityRarPublicationError(ValueError):
    """Exact-source or resumable-publication integrity guard failed."""


def aug19_processor_version(base_version: str, source_url: str) -> str:
    """Return a new parser version only for this exact source URL."""
    if source_url != decoder.AUG19_URL:
        return base_version
    if base_version.endswith(PROCESSOR_VERSION_SUFFIX):
        return base_version
    return base_version + PROCESSOR_VERSION_SUFFIX


def retained_aug19_original(db, source_url: str, kind: str, source_day: date):
    """Return exact retained bytes for worker resume, or None outside this source.

    An exact-URL row that points at any other source identity/body fails closed;
    it must not silently fall through to a new network body.
    """
    if kind != "city-zip" or source_url != decoder.AUG19_URL:
        return None
    if source_day != AUG19_DAY:
        raise CityRarPublicationError("pinned DANE asset date differs from source")
    row = db.execute(
        """SELECT a.document_id,a.observed_on,a.status,d.title,d.publisher,
                  d.source_url,d.media_type,d.kind,d.reference_period,d.content,d.metadata
             FROM ingestion_asset a LEFT JOIN source_document d ON d.id=a.document_id
            WHERE a.url=%s AND a.kind=%s""",
        (source_url, kind),
    ).fetchone()
    if row is None:
        return None
    did, observed_on = row[:2]
    if did != decoder.AUG19_DOCUMENT_ID or observed_on != AUG19_DAY:
        raise CityRarPublicationError("pinned DANE asset identity or date mismatch")
    _verify_retained_parent_fields(row[3:], expected_xmin=None, require_parent_page_count=False)
    return bytes(row[9])


def _verify_retained_parent_fields(row, *, expected_xmin=None, require_parent_page_count=True):
    # Field order is title,publisher,url,media,kind,reference,content,metadata,
    # optional page_count,xmin. Kept explicit so schema TEXT period is checked
    # as its ISO value rather than coerced into a database DATE.
    title, publisher, source_url, media_type, kind, period, content, metadata = row[:8]
    expected = (
        decoder.AUG19_TITLE,
        decoder.AUG19_PUBLISHER,
        decoder.AUG19_URL,
        decoder.AUG19_MEDIA_TYPE,
        decoder.AUG19_KIND,
        decoder.AUG19_REFERENCE_PERIOD,
    )
    if (title, publisher, source_url, media_type, kind, period) != expected:
        raise CityRarPublicationError("retained DANE parent metadata does not match pinned source")
    raw = bytes(content)
    if len(raw) > decoder.MAX_ARCHIVE_BYTES or sha256(raw).hexdigest() != decoder.AUG19_SHA256:
        raise CityRarPublicationError("retained DANE parent body differs from pinned source")
    if not raw.startswith(decoder.RAR5_MAGIC):
        raise CityRarPublicationError("retained DANE parent is not the pinned RAR5 body")
    if dict(metadata or {}) != decoder.AUG19_METADATA:
        raise CityRarPublicationError("retained DANE parent retention metadata mismatch")
    tail = row[8:]
    if require_parent_page_count:
        page_count, xmin = tail
        if page_count is not None:
            raise CityRarPublicationError("retained DANE parent page count changed")
        if expected_xmin is not None and xmin != expected_xmin:
            raise CityRarPublicationError("retained DANE parent xmin changed during publication")
        return raw, xmin
    return raw


def _verify_parent(db, source_bytes: bytes, source_did: str, source_url: str,
                   source_day: date):
    if (source_url != decoder.AUG19_URL
            or source_did != decoder.AUG19_DOCUMENT_ID
            or source_day != AUG19_DAY
            or len(source_bytes) > decoder.MAX_ARCHIVE_BYTES
            or sha256(source_bytes).hexdigest() != decoder.AUG19_SHA256
            or not source_bytes.startswith(decoder.RAR5_MAGIC)):
        raise CityRarPublicationError("RAR publication is bound to exact DANE source, URL, and date")
    row = db.execute(
        """SELECT title,publisher,source_url,media_type,kind,reference_period,
                  content,metadata,page_count,xmin::text
             FROM source_document WHERE id=%s""",
        (source_did,),
    ).fetchone()
    if row is None:
        raise CityRarPublicationError("pinned DANE parent is missing")
    raw, xmin = _verify_retained_parent_fields(row, expected_xmin=None)
    if raw != source_bytes:
        raise CityRarPublicationError("provided RAR bytes differ from retained parent")
    return xmin


def _transient_zip(payloads: dict[str, bytes]) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2022, 8, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, payloads[name])
    return result.getvalue()


def _verify_existing_publication(db, source_did: str, processor_version: str,
                                 transient: bytes, payloads: dict[str, bytes]) -> None:
    from . import city_reports

    existing_members = db.execute(
        """SELECT m.entry_name,m.document_id,d.title,d.publisher,d.source_url,
                  d.media_type,d.kind,d.reference_period,d.content,d.metadata
             FROM source_archive_member m LEFT JOIN source_document d ON d.id=m.document_id
            WHERE m.archive_id=%s""",
        (source_did,),
    ).fetchall()
    mapped = {}
    for row in existing_members:
        name, did = row[:2]
        expected = decoder.AUG19_MEMBERS.get(name)
        if expected is None or did != expected[1] or row[2] is None:
            raise CityRarPublicationError("existing archive member mapping is outside exact cohort")
        if name in mapped:
            raise CityRarPublicationError("duplicate existing archive member mapping")
        title, publisher, url, media, kind, period, content, metadata = row[2:]
        expected_metadata = {
            "ingestion_kind": "city-pdf",
            "retention": "permanent",
            "original_filename": name,
            "parents": [source_did],
            "archive_entry": name,
        }
        body = bytes(content)
        if ((title, publisher, url, media, kind, period) != (
                "DANE - " + name, decoder.AUG19_PUBLISHER, decoder.AUG19_URL,
                "application/pdf", "original", _CHILD_REFERENCE_PERIOD)
                or len(body) != expected[0]
                or sha256(body).hexdigest() != expected[1]
                or body != payloads[name]
                or dict(metadata or {}) != expected_metadata):
            raise CityRarPublicationError("existing archive member bytes or metadata mismatch")
        mapped[name] = did

    # `worker.archive` is append-only and does not rewrite metadata on an
    # already stored content hash. Verify every expected child identity even
    # when it lacks an archive-member mapping; otherwise the publisher could
    # attach a preexisting, unrelated PDF record by hash alone.
    expected_names_by_id = {digest: name for name, (_, digest) in decoder.AUG19_MEMBERS.items()}
    retained_children = db.execute(
        """SELECT id,title,publisher,source_url,media_type,kind,reference_period,
                  content,metadata FROM source_document WHERE id=ANY(%s)""",
        (list(expected_names_by_id),),
    ).fetchall()
    retained_ids = set()
    for row in retained_children:
        did = row[0]
        name = expected_names_by_id.get(did)
        if name is None:
            raise CityRarPublicationError("retained child identity is outside exact DANE cohort")
        expected_size, expected_sha = decoder.AUG19_MEMBERS[name]
        title, publisher, url, media, kind, period, content, metadata = row[1:]
        expected_metadata = {
            "ingestion_kind": "city-pdf",
            "retention": "permanent",
            "original_filename": name,
            "parents": [source_did],
            "archive_entry": name,
        }
        body = bytes(content)
        if ((title, publisher, url, media, kind, period) != (
                "DANE - " + name, decoder.AUG19_PUBLISHER, decoder.AUG19_URL,
                "application/pdf", "original", _CHILD_REFERENCE_PERIOD)
                or len(body) != expected_size or sha256(body).hexdigest() != expected_sha
                or body != payloads[name] or dict(metadata or {}) != expected_metadata):
            raise CityRarPublicationError("retained child body or metadata differs from exact source")
        retained_ids.add(did)
    if not set(mapped.values()).issubset(retained_ids):
        raise CityRarPublicationError("mapped archive member is missing its exact retained PDF child")

    children = db.execute(
        "SELECT id FROM source_document WHERE metadata->'parents' ? %s",
        (source_did,),
    ).fetchall()
    if {row[0] for row in children} != retained_ids:
        raise CityRarPublicationError("orphan or untracked retained child exists for pinned parent")

    # Reject a checkpoint that could cause the ZIP publisher to skip an
    # unverified member or count. Derive steps from the exact transient archive
    # layout and require retained child rows to substantiate each saved count.
    with zipfile.ZipFile(io.BytesIO(transient)) as archive:
        step_names = {
            city_reports._member_step(member, AUG19_DAY): member.filename
            for member in archive.infolist()
            if not member.is_dir() and member.filename.lower().endswith(".pdf")
        }
    checkpoints = db.execute(
        """SELECT step,records FROM ingestion_checkpoint
            WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%'""",
        (source_did, processor_version),
    ).fetchall()
    for step, records in checkpoints:
        name = step_names.get(step)
        if name is None or name not in mapped or not isinstance(records, int) or records <= 0:
            raise CityRarPublicationError("existing source-local member checkpoint is invalid")
        child_id = mapped[name]
        # A count-only check lets a damaged same-count row set hide behind the
        # publisher's completed-member fast path. Reparse the exact pinned PDF
        # using the production native parser and compare every publication
        # tuple, including classifications, before allowing that fast path.
        expected_rows = list(city_reports.parse_archived_city_pdf(
            db, payloads[name], child_id, AUG19_DAY,
        ))
        if len(expected_rows) != records:
            raise CityRarPublicationError("source-local checkpoint count differs from native parsed rows")
        expected_prices = [
            _price_tuple((child_id, *row)) for row in expected_rows
        ]
        actual_prices = db.execute(
            """SELECT document_id,source_locator,observed_on,product_id,product_name,
                      market_name,category,presentation,quantity,source_unit,round,
                      round_label,min_price,max_price,unit,min_unit_price,max_unit_price,
                      source_page FROM regional_price WHERE document_id=%s
                 ORDER BY source_locator""",
            (child_id,),
        ).fetchall()
        # Database collation may order numbered locators differently from
        # Python (for example row 10 before row 1). Compare both cohorts in
        # the same literal-locator order, retaining exact tuple equality.
        normalized_prices = sorted(
            (_price_tuple(row) for row in actual_prices), key=lambda row: row[1]
        )
        if normalized_prices != sorted(expected_prices, key=lambda row: row[1]):
            raise CityRarPublicationError("source-local checkpoint regional price tuples differ from native PDF")
        expected_classifications = sorted(
            (child_id, row[0], tuple(row[5].split(" > "))) for row in expected_rows
        )
        actual_classifications = db.execute(
            """SELECT document_id,source_locator,category_path
                 FROM regional_classification WHERE document_id=%s
                 ORDER BY source_locator""",
            (child_id,),
        ).fetchall()
        normalized_classifications = sorted(
            (row[0], row[1], tuple(row[2])) for row in actual_classifications
        )
        if normalized_classifications != expected_classifications:
            raise CityRarPublicationError("source-local checkpoint classifications differ from native PDF")


def _price_tuple(row):
    """Normalize PostgreSQL numeric values through decimal text, with no tolerance."""
    numeric_columns = {8, 12, 13, 15, 16}
    values = list(row)
    for index in numeric_columns:
        value = values[index]
        if value is not None:
            try:
                values[index] = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise CityRarPublicationError("regional price tuple contains an invalid numeric value") from exc
    return tuple(values)


def publish_exact_aug19_rar(db, source_bytes: bytes, source_did: str,
                            source_url: str, source_day: date, *,
                            processor_version: str, publish_city_zip=None) -> int:
    """Publish the exact RAR cohort via the existing ZIP member lifecycle.

    No source document is created for the temporary ZIP. The RAR remains the
    parent identity and the original 17 NFD member names and bytes remain the
    child identities. Existing per-member checkpoints are source-local and
    validated before the established publisher can resume them.
    """
    if not processor_version.endswith(PROCESSOR_VERSION_SUFFIX):
        raise CityRarPublicationError("RAR publication requires the exact-source processor version suffix")
    parent_xmin = _verify_parent(db, source_bytes, source_did, source_url, source_day)
    try:
        reader, _, _ = decoder.decode_pinned_aug19_source(source_bytes)
    except Exception as exc:
        raise CityRarPublicationError(f"pinned DANE RAR decode failed: {type(exc).__name__}") from exc
    payloads = {}
    for name, (expected_size, expected_sha) in decoder.AUG19_MEMBERS.items():
        body = reader.read(name, decoder.AUG19_MAX_MEMBER_BYTES)
        if len(body) != expected_size or sha256(body).hexdigest() != expected_sha:
            raise CityRarPublicationError("decoded member differs from exact DANE manifest")
        payloads[name] = body
    if len(payloads) != 17 or sum(map(len, payloads.values())) != decoder.AUG19_EXPANDED_BYTES:
        raise CityRarPublicationError("decoded DANE member cohort is incomplete")

    transient = _transient_zip(payloads)
    _verify_existing_publication(db, source_did, processor_version, transient, payloads)
    if publish_city_zip is None:
        from .city_reports import publish_city_zip as publish_city_zip_impl
        publish_city_zip = publish_city_zip_impl
    count = publish_city_zip(
        db, transient, source_did, source_url, source_day,
        processor_version=processor_version,
    )
    parent_row = db.execute(
        """SELECT title,publisher,source_url,media_type,kind,reference_period,
                  content,metadata,page_count,xmin::text FROM source_document WHERE id=%s""",
        (source_did,),
    ).fetchone()
    if parent_row is None:
        raise CityRarPublicationError("pinned DANE parent disappeared during publication")
    _verify_retained_parent_fields(parent_row, expected_xmin=parent_xmin)
    return count
