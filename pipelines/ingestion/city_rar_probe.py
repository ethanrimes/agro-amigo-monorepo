"""Read-only protected-runtime qualification for DANE's Aug 19 2022 RAR body."""
from __future__ import annotations

from hashlib import sha256
from time import monotonic

from . import city_rar_decoder as decoder


class CityRarProbeError(RuntimeError):
    """A concise fail-closed error from the protected RAR capability probe."""


_PARENT_SELECT = """SELECT title,publisher,source_url,media_type,kind,
       reference_period,content,metadata,xmin::text
  FROM source_document WHERE id=%s"""


def _parent_snapshot(db):
    row = db.execute(_PARENT_SELECT, (decoder.AUG19_DOCUMENT_ID,)).fetchone()
    if row is None:
        raise CityRarProbeError("pinned DANE source row is missing")
    expected = (
        decoder.AUG19_TITLE,
        decoder.AUG19_PUBLISHER,
        decoder.AUG19_URL,
        decoder.AUG19_MEDIA_TYPE,
        decoder.AUG19_KIND,
        decoder.AUG19_REFERENCE_PERIOD,
    )
    if tuple(row[:6]) != expected:
        raise CityRarProbeError("pinned DANE source metadata mismatch")
    body = bytes(row[6])
    digest = sha256(body).hexdigest()
    if digest != decoder.AUG19_SHA256 or not body.startswith(decoder.RAR5_MAGIC):
        raise CityRarProbeError("pinned DANE source body hash or RAR5 signature mismatch")
    if dict(row[7] or {}) != decoder.AUG19_METADATA:
        raise CityRarProbeError("pinned DANE source retention metadata mismatch")
    return body, row[8]


def run_aug19_decoder_probe(db) -> dict:
    """Read the pinned row, decode/hash its cohort, and verify no SQL change.

    The caller supplies only its existing database connection. A URL, document
    id, source bytes, decoder choice, and archive member cannot be supplied by a
    request. Call this with a connection whose current transaction has not yet
    performed another statement; the transaction is made read-only before any
    source row is read.
    """
    started = monotonic()
    try:
        db.execute("SET LOCAL TRANSACTION READ ONLY")
        source_body, initial_xmin = _parent_snapshot(db)
        reader, native_version, runtime_platform = decoder.decode_pinned_aug19_source(
            source_body
        )
        member_hashes = []
        for name in sorted(decoder.AUG19_MEMBERS):
            payload = reader.read(name, decoder.AUG19_MAX_MEMBER_BYTES)
            size, expected_sha = decoder.AUG19_MEMBERS[name]
            digest = sha256(payload).hexdigest()
            if len(payload) != size or digest != expected_sha:
                raise CityRarProbeError("decoded DANE member differs from pinned manifest")
            member_hashes.append({"name": name, "bytes": len(payload), "sha256": digest})

        _, final_xmin = _parent_snapshot(db)
        if final_xmin != initial_xmin:
            raise CityRarProbeError("pinned DANE source xmin changed during read-only probe")
        return {
            "source_sha256": decoder.AUG19_SHA256,
            "native_decoder_version": ".".join(map(str, native_version)),
            "platform": runtime_platform,
            "member_count": len(member_hashes),
            "expanded_bytes": sum(item["bytes"] for item in member_hashes),
            "member_hashes": member_hashes,
            "elapsed_ms": round((monotonic() - started) * 1000, 3),
        }
    except CityRarProbeError:
        raise
    except Exception as exc:
        # Keep protected status output useful without returning native backtraces,
        # source bytes, filesystem paths, or request-controlled content.
        raise CityRarProbeError(
            f"RAR decoder probe failed: {type(exc).__name__}"
        ) from exc
