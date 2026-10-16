"""Retained-original worker replay for six reviewed Corabastos PDFs."""
from __future__ import annotations

import hashlib

from pipelines.ingestion import colombia_sources
from pipelines.ingestion.resumable_inputs import WorkDeferred
from .corabastos_source_relocation import (KIND, NEW_SUFFIX, REVIEWED_ORIGINALS,
                                          select_prior_for_relocation)

JULY25_DID = "a6bd81f0432111df60b782dc951a16603d2be06fefb146ae0494a174607782c6"
# The exact-five reader's immutable receipt and offline source comparison
# establish each of the other five complete historical 350-row full21 cohorts.
VERIFIED_WORKER_SOURCES = dict(REVIEWED_ORIGINALS)


class CorabastosLocatorDeferred(WorkDeferred):
    """Keep a verified failed legacy asset eligible after a bounded batch pause."""


def reviewed_url(url, kind):
    return kind == KIND and url in VERIFIED_WORKER_SOURCES.values()


def retained_locator_original(db, url, kind, current_version):
    """Return an exact retained original only after whole-source prior parity.

    A registered failed asset with drift aborts. It never falls back to a
    remote request when the retained original is corrupt or incomplete.
    """
    if not reviewed_url(url, kind):
        return None
    did = next(k for k, v in VERIFIED_WORKER_SOURCES.items() if v == url)
    asset = db.execute(
        "SELECT status,document_id,processor_version,observed_on "
        "FROM ingestion_asset WHERE url=%s AND kind=%s", (url, KIND),
    ).fetchone()
    if asset is None:
        return None
    if asset[0] == "complete" and asset[2] == current_version + NEW_SUFFIX:
        return None
    if asset[0] != "failed" or asset[1] != did or asset[2] not in (
            current_version, current_version + NEW_SUFFIX):
        raise ValueError("Reviewed Corabastos retained asset binding changed")
    original = db.execute(
        "SELECT content,source_url,kind,media_type,metadata->>'ingestion_kind' "
        "FROM source_document WHERE id=%s", (did,),
    ).fetchone()
    if (original is None or original[1:] != (url, "original", "application/pdf", KIND)
            or original[0] is None):
        raise ValueError("Reviewed Corabastos retained original binding changed")
    body = bytes(original[0])
    if not 0 < len(body) <= 8_000_000 or hashlib.sha256(body).hexdigest() != did:
        raise ValueError("Reviewed Corabastos retained original bytes changed")
    native = list(colombia_sources.parse(body, url, KIND))
    if select_prior_for_relocation(db, did, url, current_version, native) is None:
        raise ValueError("Reviewed Corabastos original lacks an exact relocation")
    return body
