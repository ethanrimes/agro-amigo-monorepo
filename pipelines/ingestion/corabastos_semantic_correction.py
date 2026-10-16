"""Private candidate API for one append-only, source-bound Corabastos revision.

This module is inert unless imported by the reviewed maintained patch. It does
not contact external services. The manifest is generated from pinned evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re

from psycopg.types.json import Jsonb

from .corabastos_semantic_manifest import EXPECTED_DIFF as _EXPECTED_DIFF, MANIFEST as _MANIFEST

KIND = "colombia-corabastos-pdf"
SUFFIX = ":source-bound-semantic-correction-v1"
PRIOR_DETAILS_VERSION = "colombia-prices-v2"
NATIVE_DETAILS_VERSION = "colombia-prices-v6"
SOURCES = {r["url"]: r for r in _MANIFEST["source_records"]}
TARGET_BY_ID = {r["document_id"]: r for r in _MANIFEST["source_records"]}

QUOTE_COLUMNS = ("document_id", "source_locator", "parser_version", "quote_key",
                 "product_id", "product_name", "category", "publisher", "series",
                 "basis", "currency", "unit", "market", "observed_on", "period_start",
                 "price", "min_price", "max_price", "source_page", "details")


def _json_value(value):
    if isinstance(value, Jsonb):
        return value.obj
    if isinstance(value, (date, datetime)):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=_json_value, allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class SourceMode:
    url: str
    document_id: str
    sha256: str


def select_mode(kind: str, url: str, document_id: str, body: bytes) -> SourceMode | None:
    """Return a parser capability only for exact source URL and content hash."""
    if kind != KIND or url not in SOURCES:
        return None
    spec = SOURCES[url]
    digest = hashlib.sha256(body).hexdigest()
    if (document_id != spec["document_id"] or digest != spec["document_id"]
            or digest != spec["source_content_sha256"] or len(body) != spec["source_bytes"]):
        raise ValueError("Pinned Corabastos semantic source bytes or document ID changed")
    return SourceMode(url, document_id, digest)


def accepts_mode(mode, kind: str, url: str, body: bytes) -> bool:
    return (isinstance(mode, SourceMode) and kind == KIND and mode.url == url
            and mode.sha256 == hashlib.sha256(body).hexdigest()
            and SOURCES.get(url, {}).get("document_id") == mode.document_id)


def revision_for(kind: str, url: str, base: str) -> str:
    """Deterministic selector, independent of pending/failed/partial state."""
    return base + SUFFIX if kind == KIND and url in SOURCES else base


def _row_dict(row):
    return {name: _json_value(row[i]) for i, name in enumerate(QUOTE_COLUMNS)}


def prior_business_digest(rows):
    material = []
    for row in rows:
        record = _row_dict(row) if not isinstance(row, dict) else dict(row)
        record.pop("xmin", None)
        material.append(record)
    material.sort(key=lambda r: (r["source_locator"], r["parser_version"]))
    return _sha(material)


def _source_binding(db, spec):
    row = db.execute(
        "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
        "retrieved_at,page_count,content,metadata FROM source_document WHERE id=%s",
        (spec["document_id"],),
    ).fetchone()
    if row is None or row[9] is None:
        raise ValueError("Pinned Corabastos source original is missing")
    body = bytes(row[9])
    if len(body) != spec["source_bytes"] or hashlib.sha256(body).hexdigest() != spec["document_id"]:
        raise ValueError("Pinned Corabastos source bytes changed")
    exported = {"id": row[0], "title": row[1], "publisher": row[2], "source_url": row[3],
                "media_type": row[4], "kind": row[5], "reference_period": row[6],
                "retrieved_at": _json_value(row[7]), "page_count": row[8],
                "metadata": row[10], "content_sha256": hashlib.sha256(body).hexdigest(),
                "content_bytes": len(body)}
    if _sha(exported) != spec["source_export_without_xmin_sha256"]:
        raise ValueError("Pinned Corabastos source metadata differs from saved export")
    if row[3] != spec["url"] or row[4:6] != ("application/pdf", "original"):
        raise ValueError("Pinned Corabastos source binding changed")
    return body


def _prior_state(db, spec):
    did = spec["document_id"]
    versions = db.execute(
        "SELECT DISTINCT parser_version FROM official_price_quote WHERE document_id=%s ORDER BY 1",
        (did,),
    ).fetchall()
    expected_old = _MANIFEST["prior_revision"]
    expected_new = _MANIFEST["normal_revision"] + SUFFIX
    if [v[0] for v in versions] not in ([expected_old], [expected_old, expected_new]):
        raise ValueError("Unexpected Corabastos quote revision set")
    old = db.execute(
        "SELECT " + ",".join(QUOTE_COLUMNS) + ",xmin::text FROM official_price_quote "
        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
        (did, expected_old),
    ).fetchall()
    if len(old) != 350 or prior_business_digest(old) != spec["prior_pg_business_vector_sha256"]:
        raise ValueError("Saved Corabastos prior business cohort differs")
    reviews = db.execute(
        "SELECT parser_version,source_locator FROM official_source_review WHERE document_id=%s ORDER BY 1,2",
        (did,),
    ).fetchall()
    if reviews and any(version != expected_new for version, _ in reviews):
        raise ValueError("Unexpected preexisting Corabastos review history")
    checkpoints = db.execute(
        "SELECT processor_version,step,records FROM ingestion_checkpoint WHERE document_id=%s ORDER BY 1,2",
        (did,),
    ).fetchall()
    # The catalog writes a durable start marker before its bounded refresh.
    # A deferred catalog refresh is resumable and does not mean the source is
    # complete. Accept only its canonical revision/version/day marker, with
    # the exact current document-key count; all other checkpoint rows remain
    # fail-closed. The independent official:complete row still means exactly
    # 350 retained quotes.
    from . import official_catalog
    catalog_prefix = f"official:catalog-start:{official_catalog.VERSION}:"
    valid_catalog_markers = []
    complete_rows = []
    expected_keys = len(official_catalog.document_keys(db, did))
    if expected_keys <= 0:
        raise ValueError("Corabastos catalog identity set is empty")
    for processor_version, step, records in checkpoints:
        if processor_version != expected_new:
            raise ValueError("Unexpected Corabastos checkpoint revision")
        if step == "official:complete":
            if records != 350:
                raise ValueError("Conflicting Corabastos completion checkpoint")
            complete_rows.append((processor_version, step, records))
            continue
        if not step.startswith(catalog_prefix):
            raise ValueError("Unexpected Corabastos checkpoint step")
        day = step[len(catalog_prefix):]
        if (re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is None or
                date.fromisoformat(day).isoformat() != day):
            raise ValueError("Malformed Corabastos catalog-start day")
        if records != expected_keys:
            raise ValueError("Corabastos catalog-start identity count differs")
        valid_catalog_markers.append((processor_version, step, records))
    if len(complete_rows) > 1 or len(valid_catalog_markers) != len({row[1] for row in valid_catalog_markers}):
        raise ValueError("Duplicate Corabastos checkpoint history")
    has_complete = bool(complete_rows)
    asset = db.execute(
        "SELECT status,document_id,processor_version,records,observed_on FROM ingestion_asset WHERE url=%s",
        (spec["url"],),
    ).fetchone()
    if asset is None or asset[1] != did or asset[0] not in {"pending", "failed", "complete"}:
        raise ValueError("Corabastos asset is outside supported retry lifecycle")
    if asset[0] != "complete" and asset[2] not in {_MANIFEST["normal_revision"], expected_new}:
        raise ValueError("Corabastos asset has a conflicting retry version")
    if asset[3] != 350 or str(asset[0]) not in {"pending", "failed", "complete"} or str(asset[4]) != spec["observed_on"]:
        raise ValueError("Corabastos asset row count/date/state differs from saved cohort")
    if asset[0] == "complete" and asset[2] != expected_new:
        raise ValueError("Completed semantic asset carries another parser revision")
    if asset[0] == "complete" and not has_complete:
        raise ValueError("Complete Corabastos asset lacks its exact completion checkpoint")
    return old, expected_new


def _exact_new_cohort(db, did, revision, expected_values):
    rows = db.execute(
        "SELECT " + ",".join(QUOTE_COLUMNS) + " FROM official_price_quote "
        "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
        (did, revision),
    ).fetchall()
    actual = sorted((_row_dict(r) for r in rows), key=lambda r: r["source_locator"])
    expected = sorted((_row_dict(v) for v in expected_values), key=lambda r: r["source_locator"])
    if len(actual) != len(expected) or _sha(actual) != _sha(expected):
        raise ValueError("Existing semantic revision is partial or conflicts with exact parsed rows")
    return actual


def _check_asset(db, spec, revision, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    asset = db.execute(
        "SELECT url,kind,status,document_id,processor_version,observed_on,records FROM ingestion_asset "
        "WHERE url=%s" + suffix, (spec["url"],),
    ).fetchone()
    if asset is None or asset[:2] != (spec["url"], KIND) or asset[3] != spec["document_id"]:
        raise ValueError("Pinned Corabastos asset binding is missing or changed")
    # First run is exactly failed/v6. Once a deterministic semantic retry starts,
    # pending/failed may carry either old or new version. Complete is handled only
    # by the verified-idempotent branch in publish_source.
    if asset[2] not in {"pending", "failed", "complete"}:
        raise ValueError("Unexpected Corabastos semantic asset lifecycle state")
    if asset[2] != "complete" and asset[4] not in {
        _MANIFEST["normal_revision"], revision,
    }:
        raise ValueError("Conflicting Corabastos asset parser revision")
    if asset[2] == "complete" and asset[4] != revision:
        raise ValueError("Completed Corabastos asset has another parser revision")
    if asset[5].isoformat() != spec["observed_on"] or asset[6] != 350:
        raise ValueError("Corabastos asset date or row count differs from pinned source")
    return asset


def _expected_quote_key(row):
    identity = {name: row[name] for name in (
        "product_id", "series", "market", "currency", "unit", "basis"
    )}
    identity["dimensions"] = row["details"].get("identity_dimensions", {})
    return hashlib.sha256(json.dumps(
        identity, sort_keys=True, ensure_ascii=False
    ).encode()).hexdigest()


def _native_v6_token_vector(values):
    """Return canonical locators, exact printed tokens and parsed prices."""
    from . import colombia_sources

    material = []
    for value in values:
        row = _row_dict(value) if not isinstance(value, dict) else value
        details = row.get("details")
        if not isinstance(details, dict):
            raise ValueError("Native Corabastos token vector has no details object")
        locator = row.get("source_locator")
        token = details.get("original_price")
        if (not isinstance(locator, str) or not locator
                or details.get("parser_version") != NATIVE_DETAILS_VERSION
                or not isinstance(token, str) or not token.strip()):
            raise ValueError("Native Corabastos token/version is missing or unexpected")
        numeric = Decimal(str(colombia_sources.colombian_number(token)))
        parsed_price = Decimal(str(row.get("price")))
        if numeric != parsed_price:
            raise ValueError("Printed Corabastos token does not match its parsed price")
        material.append([locator, token, float(parsed_price)])
    material.sort(key=lambda item: item[0])
    return material


def assert_native_v6_token_vector(spec, values):
    material = _native_v6_token_vector(values)
    expected = spec.get("native_v6_token_vector_sha256")
    if len(material) != 350 or not expected or _sha(material) != expected:
        raise ValueError("Pinned Corabastos full native token vector differs")
    return material


def validate_semantic_vectors(db, spec, supplied_rows, values, revision):
    """Validate the entire 350-row vector and exact semantic allowlists."""
    diff = _EXPECTED_DIFF
    old, expected_revision = _prior_state(db, spec)
    if revision != expected_revision or len(supplied_rows) != 350 or len(values) != 350:
        raise ValueError("Semantic publication requires one exact 350-row source cohort")
    old_by_locator = {_row_dict(r)["source_locator"]: _row_dict(r) for r in old}
    if len(old_by_locator) != 350:
        raise ValueError("Prior Corabastos cohort has duplicate source locators")
    new_by_locator = {v[1]: _row_dict(v) for v in values}
    if len(new_by_locator) != 350:
        raise ValueError("New Corabastos cohort has duplicate source locators")
    # Check all 350 literal tokens before normalizing any legacy metadata.
    assert_native_v6_token_vector(spec, values)
    moves = {r["old_locator"]: r["new_locator"] for r in diff["locator_retirement_mappings"] if r["document_id"] == spec["document_id"]}
    quantity_targets = {r["prior_quote"]["source_locator"]: r for r in diff["quantity_and_label_row_diffs"] if r["prior_quote"]["document_id"] == spec["document_id"]}
    label_targets = {entry["physical_locator_prefix"] + str(col): entry for entry in diff["february_4_label_allowlist"] if entry["document_id"] == spec["document_id"] for col in entry["quality_columns"]}
    if set(moves) & set(moves.values()):
        raise ValueError("Locator retirements overlap replacement locators and could hide new rows")
    if len(set(moves.values())) != len(moves):
        raise ValueError("Multiple prior quotes map to one replacement locator")
    found_quantity, found_labels = set(), set()
    for oldloc, prior in old_by_locator.items():
        newloc = moves.get(oldloc, oldloc)
        current = new_by_locator.get(newloc)
        if current is None:
            raise ValueError("Semantic source vector omitted a saved prior locator")
        target = quantity_targets.get(oldloc)
        label = label_targets.get(oldloc)
        before, after = dict(prior), dict(current)
        before.pop("xmin", None); after.pop("xmin", None)
        if after["quote_key"] != _expected_quote_key(after):
            raise ValueError("New semantic quote identity hash is inconsistent")
        before["parser_version"] = after["parser_version"]
        if oldloc in moves:
            before["source_locator"] = after["source_locator"]
            import re
            old_match = re.fullmatch(r"PDF page (\d+), y ([0-9]+(?:\.[0-9]+)?); price column ([12])", oldloc)
            new_match = re.fullmatch(r"PDF page (\d+), y ([0-9]+(?:\.[0-9]+)?); price column ([12])", newloc)
            if (not old_match or not new_match or old_match.group(1) != new_match.group(1)
                    or old_match.group(3) != new_match.group(3)
                    or abs(float(old_match.group(2)) - float(new_match.group(2))) > 3.0):
                raise ValueError("Pinned locator movement crossed page/column or exceeded 3 points")
        bd, ad = dict(before["details"]), dict(after["details"])
        if bd.get("parser_version") != PRIOR_DETAILS_VERSION:
            raise ValueError("Prior Corabastos nested parser version differs")
        if ad.get("parser_version") != NATIVE_DETAILS_VERSION:
            raise ValueError("New Corabastos nested parser version differs")
        if "original_price" in bd or not isinstance(ad.get("original_price"), str):
            raise ValueError("Corabastos printed-price metadata allowance is not exact")
        # The complete source token hash and numeric equality are already
        # verified, so only these two explicit details keys may normalize.
        bd["parser_version"] = ad["parser_version"]
        bd["original_price"] = ad["original_price"]
        if target:
            oldq = target["prior_quote"]["details"]["quantity"]
            if bd.get("quantity") != oldq or bd.get("identity_dimensions", {}).get("quantity") != oldq:
                raise ValueError("Pinned prior quantity differs from source proof")
            if (ad.get("quantity") != 1000.0 or
                ad.get("identity_dimensions", {}).get("quantity") != 1000.0 or
                ad.get("quantity_as_published") != "1.000"):
                raise ValueError("Reviewed grouped quantity did not normalize exactly")
            bd["quantity"] = ad["quantity"]
            bd["quantity_as_published"] = ad["quantity_as_published"]
            bdims, adims = dict(bd.get("identity_dimensions") or {}), dict(ad.get("identity_dimensions") or {})
            bdims["quantity"] = adims.get("quantity")
            bd["identity_dimensions"] = bdims
            before["quote_key"] = after["quote_key"]
            found_quantity.add(oldloc)
        elif "quantity_as_published" in ad or bd.get("quantity") != ad.get("quantity"):
            raise ValueError("Grouped quantity field changed outside the exact 36-row allowlist")
        if label:
            expected_id = ("aguacate-pieles-verdes-xtonelada" if "Pieles Verdes" in label["new_product_name"]
                           else "aguacate-hass-x-tonelada")
            if (after["product_id"] != expected_id or after["product_name"] != label["new_product_name"] or
                ad.get("original_product") != label["new_original_product"]):
                raise ValueError("Feb-4 source-anchored product text differs from reviewed print")
            before["product_id"] = after["product_id"]
            before["product_name"] = after["product_name"]
            before["quote_key"] = after["quote_key"]
            bd["original_product"] = ad.get("original_product")
            found_labels.add(oldloc)
        before["details"], after["details"] = bd, ad
        if _sha(before) != _sha(after):
            raise ValueError("Unapproved Corabastos source-vector field changed")
    expected_quantity_count = 4
    expected_label_count = 4 if spec["document_id"] == "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b" else 0
    if found_quantity != set(quantity_targets) or len(found_quantity) != expected_quantity_count or len(found_labels) != expected_label_count:
        raise ValueError("Corabastos semantic correction target count changed")
    expected_moves = {
        "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a": 16,
        "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f": 18,
        "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab": 16,
        "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90": 10,
        "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524": 14,
        "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b": 12,
        "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3": 12,
        "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade": 18,
        "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae": 16,
    }
    if len(moves) != expected_moves[spec["document_id"]]:
        raise ValueError("Corabastos locator map changed")
    return old, moves

def make_retirement_reviews(spec, prior_rows, revision, diff):
    """Build exact review rows; callers insert these in same source transaction."""
    moves = {x["old_locator"]: x["new_locator"] for x in diff["locator_retirement_mappings"] if x["document_id"] == spec["document_id"]}
    by_locator = {_row_dict(row)["source_locator"]: _row_dict(row) for row in prior_rows}
    if set(moves) - by_locator.keys():
        raise ValueError("Saved Corabastos review mapping references unknown old locator")
    output = []
    for oldloc, newloc in sorted(moves.items()):
        record = by_locator[oldloc]
        output.append((spec["document_id"], oldloc, revision,
                       Jsonb({"retired_by_verified_source": spec["document_id"],
                              "replacement_locator": newloc,
                              "prior_quote": record}),
                       "Source-bound native Corabastos geometry/semantic revision; prior row retained"))
    return output


def publish_source(db, *, url, document_id, body, rows, values, base_revision,
                   refresh_document, checkpoint=True):
    """Source-atomic quote+review write; refresh and completion happen afterward.

    All source, asset, prior-vector, parser-vector, and existing-revision checks
    run while the asset row is locked inside the same transaction as any insert.
    Catalog refresh is a separate resumable boundary; official completion is last.
    """
    mode = select_mode(KIND, url, document_id, body)
    if mode is None:
        raise ValueError("Semantic correction publisher called for an unlisted source")
    spec = SOURCES[url]
    revision = revision_for(KIND, url, base_revision)
    prior_rows = ()
    old_xmins = {}
    source_xmin_before = None

    with db.transaction():
        _check_asset(db, spec, revision, lock=True)
        locked_body = _source_binding(db, spec)
        if locked_body != body:
            raise ValueError("Worker bytes differ from the retained source original")
        prior_rows, _moves = validate_semantic_vectors(db, spec, rows, values, revision)
        existing = db.execute(
            "SELECT " + ",".join(QUOTE_COLUMNS) + " FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (document_id, revision),
        ).fetchall()
        reviews = make_retirement_reviews(spec, prior_rows, revision, _EXPECTED_DIFF)
        if len(reviews) != len(_moves):
            raise ValueError("Semantic review mapping is incomplete")
        if existing:
            _exact_new_cohort(db, document_id, revision, values)
            stored_reviews = db.execute(
                "SELECT source_locator,record,reason FROM official_source_review "
                "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                (document_id, revision),
            ).fetchall()
            wanted_reviews = {r[1]: (r[3].obj, r[4]) for r in reviews}
            if len(stored_reviews) != len(wanted_reviews) or any(
                wanted_reviews.get(locator) != (record, reason)
                for locator, record, reason in stored_reviews
            ):
                raise ValueError("Partial or conflicting semantic-review set")
        else:
            # A poisoned partial review set is never treated as retryable.
            if db.execute(
                "SELECT 1 FROM official_source_review WHERE document_id=%s AND parser_version=%s LIMIT 1",
                (document_id, revision),
            ).fetchone():
                raise ValueError("Review rows exist without the exact semantic quote cohort")
            old_xmins = {r[1]: r[-1] for r in prior_rows}
            source_xmin_before = db.execute(
                "SELECT xmin::text FROM source_document WHERE id=%s", (document_id,)
            ).fetchone()[0]
            from .official_catalog import mark_document_dirty
            mark_document_dirty(db, document_id, revision, older_only=True)
            with db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO official_price_quote (" + ",".join(QUOTE_COLUMNS) + ") VALUES (" + ",".join(["%s"] * 20) + ")",
                    values,
                )
                cur.executemany(
                    "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,%s,%s,%s,%s)",
                    reviews,
                )
            _exact_new_cohort(db, document_id, revision, values)
            if db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s",
                (document_id, revision),
            ).fetchone()[0] != len(reviews):
                raise ValueError("Semantic review write did not retain exact mapping")
            after = dict(db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version=%s",
                (document_id, _MANIFEST["prior_revision"]),
            ).fetchall())
            if after != old_xmins:
                raise ValueError("Append-only semantic publication changed prior quote xmin values")
            db.execute("UPDATE ingestion_asset SET observed_on=%s WHERE url=%s",
                       (max(v[13] for v in values), url))

    if source_xmin_before is not None:
        if db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (document_id,)).fetchone()[0] != source_xmin_before:
            raise ValueError("Append-only semantic publication changed source-document xmin")
        actual_old_xmins = dict(db.execute(
            "SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
            (document_id, _MANIFEST["prior_revision"]),
        ).fetchall())
        if actual_old_xmins != old_xmins:
            raise ValueError("Append-only semantic publication changed prior quote xmin values")
    # Catalog work can defer safely after atomic quote+review publication. The
    # source remains incomplete until all current identities refresh successfully.
    refresh_document(db, document_id, revision, older_only=True)
    if checkpoint:
        with db.transaction():
            db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,'official:complete',350) ON CONFLICT DO NOTHING",
                (document_id, revision),
            )
            cp = db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                (document_id, revision),
            ).fetchone()
            if cp != (350,):
                raise ValueError("Conflicting semantic-completion checkpoint")
    return 350


def retained_original(db, url: str, kind: str):
    """Return exact original bytes for incomplete pinned asset retries only."""
    if kind != KIND or url not in SOURCES:
        return None
    spec = SOURCES[url]
    asset = db.execute(
        "SELECT status,document_id,processor_version FROM ingestion_asset WHERE url=%s",
        (url,),
    ).fetchone()
    if asset is None:
        raise ValueError("Pinned Corabastos semantic asset is missing")
    if asset[0] == "complete":
        return None
    if asset[0] not in {"pending", "failed"} or asset[1] != spec["document_id"]:
        raise ValueError("Pinned Corabastos retry state/source binding changed")
    body = _source_binding(db, spec)
    if hashlib.sha256(body).hexdigest() != asset[1]:
        raise ValueError("Pinned Corabastos retained original changed")
    return body
