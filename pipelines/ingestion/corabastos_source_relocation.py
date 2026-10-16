"""Source-bound append-only relocation for six reviewed Corabastos PDFs.

The retained original and every prior quote are checked before a new source
revision becomes current. Unreviewed originals remain outside this repair.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json

from psycopg.types.json import Jsonb

from pipelines.ingestion import colombia_sources
from .corabastos_locator_geometry import FIELDS, full20, plan

MAX_QUOTES = 2000

KIND = "colombia-corabastos-pdf"
NEW_SUFFIX = ":source-bound-locator-v1"
REVIEWED_ORIGINALS = {
    "8748df4db724c07d84f92fe3a8c54473525085b34a070681a8ed230e6ea23de1":
        "https://corabastos.com.co/wp-content/uploads/2024/08/Boletin-05agosto2024.pdf",
    "5b16541ebf21a2f8f88f69ab2a7ed7f82e14b0693cee35eb67a4f77d3ce1dda1":
        "https://corabastos.com.co/wp-content/uploads/2024/08/Boletin-06agosto2024.pdf",
    "855beb303e4b3aae6abf19ea276d6186bf62b93e8018a475f15de2d313a42f6c":
        "https://corabastos.com.co/wp-content/uploads/2024/08/Boletin-08agosto2024.pdf",
    "bb77b9ac465ff2490d94cf863bcfc0ed5c49f3855dec02f8009ebe78b42789cd":
        "https://corabastos.com.co/wp-content/uploads/2024/08/Boletin-02agosto2024.pdf",
    "1cf46b5a7fc903d4c4e68c6c9164ce768a79b2c84251aa6c3b06b6a3a14e957b":
        "https://corabastos.com.co/wp-content/uploads/2024/07/Boletin-31julio2024.pdf",
    "a6bd81f0432111df60b782dc951a16603d2be06fefb146ae0494a174607782c6":
        "https://corabastos.com.co/wp-content/uploads/2024/07/Boletin-25julio2024.pdf",
    "3ed14d5ab15528b81cd87b65620fd4d5da8bfff3ff270a97a8b36e240890c3d2":
        "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-20enero2025.pdf",
    "65d27ede41a09f6d6a1be159a79d96f7aa9555c43fcfc4693cb5b6d0acdaa808":
        "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-21enero2025.pdf",
    "4e8617bbc3f6671afbbf62075e3d6dea668e640b6b28de7242c6e874a6c79035":
        "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-22enero2025.pdf",
    "078c2277b1d718a2509c47e543cd5500dd91992095222833cd3bb243d90c7fef":
        "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-23enero2025.pdf",
    "433daba55ac001707ce7df79c9ad1114aa238a828be68717451607a4a9acb474":
        "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-27enero2025.pdf",
}
HELD_NOVEL_ORIGINALS = {
    "c2e9e644d9e1f599853eba4f955b8f1a8e0954841300edbb5ed4e9dc2d344b64":
        "https://corabastos.com.co/wp-content/uploads/2024/08/Boletin-01agosto2024.pdf",
}
QUOTE_COLUMNS = ("document_id", "source_locator", "parser_version", "quote_key",
                 "product_id", "product_name", "category", "publisher", "series",
                 "basis", "currency", "unit", "market", "observed_on", "period_start",
                 "price", "min_price", "max_price", "source_page", "details")


def _stored_full20(stored):
    details = stored[19]
    return {"source_locator": stored[1], "product_id": stored[4],
            "product_name": stored[5], "category": stored[6], "publisher": stored[7],
            "series": stored[8], "basis": stored[9], "currency": stored[10],
            "unit": stored[11], "market": stored[12], "day": stored[13].isoformat(),
            "period_start": stored[14].isoformat() if stored[14] else None,
            "price": float(stored[15]),
            "min_price": float(stored[16]) if stored[16] is not None else None,
            "max_price": float(stored[17]) if stored[17] is not None else None,
            "source_page": stored[18],
            **{name: details.get(name) for name in FIELDS[15:]}}


def _key(row):
    return tuple(row[field] for field in FIELDS)


def _quote_values(db, did, revision):
    cols = ",".join(QUOTE_COLUMNS)
    return db.execute(
        f"SELECT {cols} FROM official_price_quote WHERE document_id=%s "
        "AND parser_version=%s ORDER BY source_locator LIMIT 2001", (did, revision),
    ).fetchall()


def _normalized_value(value, index):
    if index in (15, 16, 17):
        return None if value is None else Decimal(str(value))
    if index == 19:
        return value.obj if isinstance(value, Jsonb) else value
    return value


def _quote_map(rows):
    by_locator = {}
    for row in rows:
        locator = row[1]
        if locator in by_locator:
            raise ValueError("Duplicate retained source locator")
        by_locator[locator] = tuple(_normalized_value(value, i)
                                    for i, value in enumerate(row))
    return by_locator


def _quote_identity_hash(stored):
    dimensions = stored[19].get("identity_dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("Retained prior identity dimensions missing")
    identity = dict(zip(("product_id", "series", "market", "currency", "unit", "basis"),
                        (stored[4], stored[8], stored[12], stored[10], stored[11], stored[9])))
    identity["dimensions"] = dimensions
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _require_reviewed_source(did, url, *, allow_other):
    """Permit relocation only for the six paired, content-addressed originals.

    Other URLs keep ordinary append-only publication. A reviewed URL with
    different bytes, or reviewed bytes under a different URL, fail closed.
    """
    if REVIEWED_ORIGINALS.get(did) == url:
        return True
    if did in REVIEWED_ORIGINALS or url in REVIEWED_ORIGINALS.values():
        raise ValueError("Reviewed Corabastos original or URL changed")
    if allow_other:
        return False
    raise ValueError("Unreviewed Corabastos source cannot retire prior locators")


def _source_binding(db, did):
    row = db.execute(
        "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
        "retrieved_at,page_count,content,metadata FROM source_document WHERE id=%s",
        (did,),
    ).fetchone()
    if row is None or row[9] is None:
        raise ValueError("Retained original missing")
    body = bytes(row[9])
    if not 0 < len(body) <= 8_000_000 or hashlib.sha256(body).hexdigest() != did:
        raise ValueError("Retained original bytes changed")
    return row[:9] + (len(body), did, row[10]), body


def _asset_binding(db, url, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    return db.execute(
        "SELECT url,kind,status,document_id,processor_version,observed_on "
        "FROM ingestion_asset WHERE url=%s" + suffix, (url,),
    ).fetchone()


def _complete_checkpoints(db, did):
    rows = db.execute(
        "SELECT document_id,processor_version,step,records,completed_at "
        "FROM ingestion_checkpoint WHERE document_id=%s AND step='official:complete' "
        "ORDER BY processor_version LIMIT 6", (did,),
    ).fetchall()
    if len(rows) > 5:
        raise ValueError("Too many retained completion revisions")
    return rows


def select_prior_for_relocation(db, did, url, current_version, supplied):
    """Select one complete historical cohort only for an exact locator move.

    No prior rows means ordinary publication. A changed monetary/identity row,
    additional historical revision, or ambiguous same-version replay is held.
    """
    if not _require_reviewed_source(did, url, allow_other=True):
        return None
    new_version = current_version + NEW_SUFFIX
    versions = db.execute(
        "SELECT DISTINCT parser_version FROM official_price_quote "
        "WHERE document_id=%s ORDER BY parser_version LIMIT 4", (did,),
    ).fetchall()
    if not versions:
        return None
    old_versions = [row[0] for row in versions if row[0] != new_version]
    if len(versions) > 2 or len(old_versions) != 1:
        raise ValueError("Ambiguous retained Corabastos revision history")
    prior_version = old_versions[0]
    prior = _quote_values(db, did, prior_version)
    count = len(prior)
    if not 0 < count <= MAX_QUOTES or len(supplied) != count:
        raise ValueError("Retained prior or native Corabastos cohort incomplete")
    if any(row[3] != _quote_identity_hash(row) for row in prior):
        raise ValueError("Retained prior quote identity differs from stored dimensions")
    source_binding, body = _source_binding(db, did)
    if (source_binding[3:6] != (url, "application/pdf", "original")
            or source_binding[11].get("ingestion_kind") != KIND):
        raise ValueError("Retained Corabastos source binding changed")
    old_full = [_stored_full20(row) for row in prior]
    proposed_full = [full20(row) for row in supplied]
    try:
        relocation = plan(did, url, body, old_full, proposed_full)
    except ValueError as exc:
        if str(exc) == "No relocation requiring retirement" and len(versions) == 1:
            return None
        raise
    if not relocation["retirements"]:
        return None
    native = list(colombia_sources.parse(body, url, KIND))
    native_dims = {_key(full20(row)): row.get("identity_dimensions") for row in native}
    if (len(native_dims) != count or
            any(stored[19].get("identity_dimensions") != native_dims.get(_key(_stored_full20(stored)))
                for stored in prior)):
        raise ValueError("Retained prior dimensions differ from original")
    checkpoints = _complete_checkpoints(db, did)
    asset = _asset_binding(db, url, lock=False)
    if asset is None or asset[:2] != (url, KIND) or asset[3] != did:
        raise ValueError("Retained Corabastos asset binding changed")
    prior_complete = [row for row in checkpoints if row[1] == prior_version]
    if checkpoints:
        legacy_completed = (not prior_complete and len(checkpoints) == 1
                            and checkpoints[0][1] == new_version
                            and checkpoints[0][3] == count)
        if (not legacy_completed and (len(prior_complete) != 1
                                      or prior_complete[0][3] != count)
                or any(row[1] not in (prior_version, new_version) or row[3] != count
                       for row in checkpoints)):
            raise ValueError("Conflicting complete prior Corabastos checkpoint")
    elif asset[2] != "failed":
        raise ValueError("Legacy prior without completion requires failed asset")
    return prior_version


def prepare(db, did, url, prior_version, new_version, supplied, values, missing):
    _require_reviewed_source(did, url, allow_other=False)
    from pipelines.ingestion.worker import parser_version

    if new_version != parser_version(KIND) + NEW_SUFFIX:
        raise ValueError("Unexpected source-local revision")
    source_binding, body = _source_binding(db, did)
    asset_binding = _asset_binding(db, url, lock=False)
    if (source_binding[0] != did or source_binding[3:6] != (url, "application/pdf", "original")
            or source_binding[11].get("ingestion_kind") != KIND
            or asset_binding is None or asset_binding[:2] != (url, KIND)
            or asset_binding[2] not in ("pending", "complete", "failed") or asset_binding[3] != did):
        raise ValueError("Retained original or asset binding drift")
    checkpoints = _complete_checkpoints(db, did)
    pinned = [row[3] for row in checkpoints if row[1] == prior_version]
    prior = _quote_values(db, did, prior_version)
    count = len(prior)
    legacy = (not pinned and
              (not checkpoints and asset_binding[2] == "failed" or
               len(checkpoints) == 1 and checkpoints[0][1] == new_version
               and checkpoints[0][3] == count))
    if (not 0 < count <= MAX_QUOTES or not (pinned == [count] or legacy)
            or len(supplied) != count or len(values) != count):
        raise ValueError("Pinned complete prior or current source cohort missing")
    native = list(colombia_sources.parse(body, url, KIND))
    if len(native) != count:
        raise ValueError("Native source row count drift")
    old_full = [_stored_full20(row) for row in prior]
    proposed_full = [full20(row) for row in supplied]
    relocation = plan(did, url, body, old_full, proposed_full)
    native_dims = {_key(full20(row)): row.get("identity_dimensions", {})
                   for row in native}
    supplied_dims = {_key(full20(row)): row.get("identity_dimensions", {})
                     for row in supplied}
    if len(native_dims) != count or native_dims != supplied_dims:
        raise ValueError("Native or supplied identity dimensions drift")
    for stored, item in zip(prior, old_full):
        dims = stored[19].get("identity_dimensions")
        if dims != native_dims[_key(item)]:
            raise ValueError("Prior quote identity dimensions drift")
    moves = {(oldloc, newloc) for oldloc, newloc, _ in relocation["retirements"]}
    moved_old = {oldloc for oldloc, _ in moves}
    if set(missing) != moved_old:
        completed = db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (did, new_version),
        ).fetchall()
        if set(missing) or completed != [(count,)]:
            raise ValueError("Prior active missing locators differ from complete-source moves")
        prior_reviews = db.execute(
            "SELECT source_locator,record->>'retired_by' FROM official_source_review "
            "WHERE document_id=%s AND parser_version=%s", (did, new_version),
        ).fetchall()
        if set(prior_reviews) != moves:
            raise ValueError("Completed source retirement mapping drift")
    return {
        "moves": moves, "document_id": did, "source_sha256": did,
        "new_version": new_version, "expected_values": _quote_map(values),
        "prior_version": prior_version, "expected_prior": _quote_map(prior),
        "source_binding": source_binding, "asset_binding": asset_binding,
        "expected_asset_observed_on": max(value[13] for value in values),
        "checkpoints": checkpoints, "source_url": url,
        "count": count,
    }


def confirm_stored_new(db, prepared):
    found = _quote_map(_quote_values(db, prepared["document_id"],
                                   prepared["new_version"]))
    if found != prepared["expected_values"]:
        raise ValueError("Retained same-version quote differs from entire native source")
    completed = db.execute(
        "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step='official:complete'",
        (prepared["document_id"], prepared["new_version"]),
    ).fetchall()
    if completed not in ([], [(prepared["count"],)]):
        raise ValueError("New completion checkpoint drift")


def confirm_final_source_prior(db, prepared):
    """Call as the first read INSIDE the final transaction, before retirement.

    The asset lock lasts through retirement, catalog refresh and checkpoint.
    Immutable source_document is read plainly because ingestor lacks UPDATE.
    """
    did = prepared["document_id"]
    asset = _asset_binding(db, prepared["source_url"], lock=True)
    if (asset is None or asset[:5] != prepared["asset_binding"][:5]
            or asset[5] != prepared["expected_asset_observed_on"]):
        raise ValueError("Asset binding changed before final publication")
    source_binding, _ = _source_binding(db, did)
    if source_binding != prepared["source_binding"]:
        raise ValueError("Original source metadata changed before final publication")
    if _complete_checkpoints(db, did) != prepared["checkpoints"]:
        raise ValueError("Complete checkpoint history changed before final publication")
    prior = _quote_map(_quote_values(db, did, prepared["prior_version"]))
    if prior != prepared["expected_prior"] or len(prior) != prepared["count"]:
        raise ValueError("Complete prior quote details changed before final publication")


def insert_and_verify_retirements(db, prepared):
    did, revision = prepared["document_id"], prepared["new_version"]
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO official_source_review(document_id,source_locator,parser_version,"
            "record,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            ((did, oldloc, revision,
              Jsonb({"retired_by": newloc, "source_sha256": prepared["source_sha256"]}),
              "Exact whole-source Corabastos locator relocation")
             for oldloc, newloc in sorted(prepared["moves"])),
        )
    actual = db.execute(
        "SELECT source_locator,parser_version,record,reason "
        "FROM official_source_review WHERE document_id=%s "
        "AND parser_version=%s", (did, revision),
    ).fetchall()
    expected = {(oldloc, revision,
                 (("retired_by", newloc), ("source_sha256", prepared["source_sha256"])),
                 "Exact whole-source Corabastos locator relocation")
                for oldloc, newloc in prepared["moves"]}
    normalized = {(loc, rev, tuple(sorted(record.items())), reason)
                  for loc, rev, record, reason in actual}
    if normalized != expected:
        raise ValueError("Retained retirement review differs from source-bound mapping")
