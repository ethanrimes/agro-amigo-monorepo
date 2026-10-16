"""Source-bound handling for one non-price PDF in a DANE city archive.

This is intentionally outside the generic city parser.  The exact original
ZIP still goes through that parser for all agricultural siblings; only its
reviewed administrative member receives a zero-row completion checkpoint.
"""

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pdfplumber

from . import city_reports


URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-31may2024.zip"
PARENT_SHA256 = "535debd86950b07758ea32115a5b6906b52885726a314b54af471572f5f7c5f5"
MEMBER_NAME = "metas2023finalf.pdf"
MEMBER_SHA256 = "2a86b7bbb51116a8cae70fb2a71ae25215f3fd44113d2ec5abb56c4e96eb30bb"
MEMBER_BYTES = 9634
DAY = date(2024, 5, 31)
VERSION = "city-v8:may2024-nonprice-context-v1"
_ANCHORS = ("FORMATO VALORACIÓN A LA GESTIÓN", "METAS ESTABLECIDAS Y LOGRADAS")
_REGISTRY = Path(__file__).resolve().parents[2] / "shared" / "source-document-scope.json"
_PARENT_FILENAME = "bol-SIPSADiario-regionales-31may2024.zip"
_PRICE_GRID = re.compile(
    r"PRECIOS\s+DE\s+VENTA\s+MAYORISTA|PRODUCTOS\s+PRIMERA\s+CALIDAD|"
    r"RONDA\s*[12]|PRODUCTO\s+PRESENTACI[OÓ]N\s+UNIDADES|"
    r"M[IÍ]NIMO\s+M[AÁ]XIMO\s+M[IÍ]NIMO\s+M[AÁ]XIMO",
    re.IGNORECASE,
)
_AGRICULTURAL_TABLES = (
    "regional_price", "regional_classification", "price_observation",
    "historical_price", "input_price", "input_municipal_price", "input_reference_row",
)
_PRICE_FIELDS = (
    "source_locator", "observed_on", "product_id", "product_name", "market_name",
    "category", "presentation", "quantity", "source_unit", "round", "round_label",
    "min_price", "max_price", "unit", "min_unit_price", "max_unit_price", "source_page",
)


@dataclass(frozen=True)
class VerifiedNonpriceMember:
    content: bytes
    step: str
    peer_steps: frozenset[str]


def _require(condition, reason):
    if not condition:
        raise ValueError("Exact non-price city source: " + reason)


def _scope():
    """Require the shared display scope to agree with this immutable route."""
    try:
        data = json.loads(_REGISTRY.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("Exact non-price city source: scope registry unavailable") from exc
    expected = {
        "document_id": MEMBER_SHA256,
        "bytes": MEMBER_BYTES,
        "media_type": "application/pdf",
        "publisher": "DANE",
        "source_url": URL,
        "archive_id": PARENT_SHA256,
        "archive_entry": MEMBER_NAME,
        "scope": "non-agricultural-administration",
        "native_pages": 2,
        "native_anchors": list(_ANCHORS),
    }
    documents = data.get("documents")
    _require(data.get("format") == 1 and isinstance(documents, list), "scope registry changed")
    _require(all(isinstance(item, dict) for item in documents), "scope registry documents changed")
    identities = [item.get("document_id") for item in documents]
    archive_keys = [(item.get("archive_id"), item.get("archive_entry")) for item in documents
                    if item.get("archive_id") is not None or item.get("archive_entry") is not None]
    _require(
        all(isinstance(identity, str) and identity for identity in identities)
        and len(set(identities)) == len(identities)
        and len(set(archive_keys)) == len(archive_keys),
        "duplicate scoped document identity",
    )
    matched = [item for item in documents if item.get("document_id") == MEMBER_SHA256
               or (item.get("archive_id"), item.get("archive_entry")) == (PARENT_SHA256, MEMBER_NAME)]
    _require(matched == [expected], "exact non-price scope changed")


def _verify_native_nonprice_pdf(content):
    _require(len(content) == MEMBER_BYTES, "member byte length changed")
    _require(hashlib.sha256(content).hexdigest() == MEMBER_SHA256, "member SHA-256 changed")
    _require(content.startswith(b"%PDF-"), "member is not a PDF")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        _require(len(pdf.pages) == 2, "native page count changed")
        texts = [page.extract_text() or "" for page in pdf.pages]
        _require(all(len(text) >= 100 for text in texts), "native text unavailable")
        _require(all(anchor in texts[0] for anchor in _ANCHORS), "native subject anchors changed")
        _require(not any(_PRICE_GRID.search(text) for text in texts), "price-grid heading present")
        for page in pdf.pages:
            for table in page.extract_tables():
                cells = [str(cell or "") for row in table for cell in row]
                joined = " ".join(cells)
                _require(not _PRICE_GRID.search(joined), "price-grid table present")


def verify_exact_nonprice_parent(source_url, parent_bytes, parent_sha256, archive_day):
    """Pure exact-byte proof; unrelated publisher URLs delegate normally."""
    if source_url != URL:
        return None
    _scope()
    _require(archive_day == DAY, "publisher date changed")
    _require(parent_sha256 == PARENT_SHA256, "parent identity changed")
    _require(hashlib.sha256(parent_bytes).hexdigest() == PARENT_SHA256, "parent bytes changed")
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        members = [m for m in bundle.infolist() if not m.is_dir()]
        _require(len(members) == 33, "archive member count changed")
        _require(len({m.filename for m in members}) == len(members), "duplicate ZIP names")
        _require(all(m.filename.lower().endswith(".pdf") for m in members), "non-PDF ZIP member")
        _require(bundle.testzip() is None, "ZIP member CRC failed")
        selected = [m for m in members if m.filename == MEMBER_NAME]
        _require(len(selected) == 1, "administrative member missing or duplicated")
        member = selected[0]
        _require(member.file_size == MEMBER_BYTES, "member ZIP size changed")
        content = bundle.read(member)
        _verify_native_nonprice_pdf(content)
        peer_steps = frozenset(city_reports._member_step(m, DAY) for m in members if m is not member)
        _require(len(peer_steps) == 32, "peer checkpoint identities collide")
        step = city_reports._member_step(member, DAY)
        _require(step not in peer_steps, "administrative checkpoint identity collides")
        return VerifiedNonpriceMember(content, step, peer_steps)


def _check_retained_document(row, *, digest, url, media, size, pages, metadata):
    _require(row is not None, "retained source document missing")
    _require(row[0] == digest and row[1] == url and row[2] == media and row[3] == "original", "retained source identity changed")
    _require(row[4] == size and hashlib.sha256(bytes(row[5])).hexdigest() == digest, "retained source bytes changed")
    _require(row[7] == pages, "retained source page count changed")
    actual = row[6] or {}
    _require(all(actual.get(key) == value for key, value in metadata.items()), "retained source metadata changed")


def _source_row(db, digest):
    return db.execute(
        "SELECT id,source_url,media_type,kind,octet_length(content),content,metadata,page_count "
        "FROM source_document WHERE id=%s", (digest,),
    ).fetchone()


def _check_no_agricultural_rows(db):
    for table in _AGRICULTURAL_TABLES:
        _require(
            db.execute(f"SELECT 1 FROM {table} WHERE document_id=%s LIMIT 1", (MEMBER_SHA256,)).fetchone() is None,
            "existing agricultural row in " + table,
        )


def _check_existing_peer_parity(db, parent_bytes, checkpoints):
    """Require every old price/classification row to equal the native 17 fields.

    A checkpoint from an earlier partial run may be skipped by the generic
    publisher.  It is safe to skip only when its entire original grid and
    classification still match the retained PDF.
    """
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        for member in bundle.infolist():
            if member.is_dir() or member.filename == MEMBER_NAME:
                continue
            content = bundle.read(member)
            digest = hashlib.sha256(content).hexdigest()
            native_rows = list(city_reports.parse_city_pdf(content, DAY))
            native = {row[0]: row for row in native_rows}
            _require(len(native) == len(native_rows), "duplicate peer price locator")
            stored_rows = db.execute(
                f"SELECT {','.join(_PRICE_FIELDS)} FROM regional_price WHERE document_id=%s",
                (digest,),
            ).fetchall()
            stored = {row[0]: row for row in stored_rows}
            _require(len(stored) == len(stored_rows), "duplicate retained peer price locator")
            _require(
                all(locator in native and values == native[locator] for locator, values in stored.items()),
                "retained peer 17-field price differs from native original",
            )
            paths = dict(db.execute(
                "SELECT source_locator,category_path FROM regional_classification WHERE document_id=%s",
                (digest,),
            ).fetchall())
            _require(
                set(paths) == set(stored)
                and all(paths[locator] == native[locator][5].split(" > ") for locator in paths),
                "retained peer classification differs from native original",
            )
            step = city_reports._member_step(member, DAY)
            if step in checkpoints:
                _require(
                    checkpoints[step] == len(native) == len(stored),
                    "completed peer checkpoint does not cover full native grid",
                )


def maybe_publish_exact_nonprice_city_zip(
    db, source_url, parent_bytes, parent_sha256, archive_day, *, processor_version=VERSION,
):
    """Retain/checkpoint only the exact administrative member, then parse peers.

    Returns ``None`` for other URLs.  The generic city publisher retains its
    normal per-member transactions, price parity checks, review and resume.
    """
    verified = verify_exact_nonprice_parent(source_url, parent_bytes, parent_sha256, archive_day)
    if verified is None:
        return None
    _require(processor_version == VERSION, "processor version changed")
    from .worker import archive

    with db.transaction():
        asset = db.execute(
            "SELECT url,kind,observed_on,document_id,status FROM ingestion_asset "
            "WHERE url=%s FOR UPDATE", (URL,),
        ).fetchone()
        _require(
            asset is not None and asset[0] == URL and asset[1] == "city-zip"
            and asset[2] == DAY and asset[3] == PARENT_SHA256
            and asset[4] in ("pending", "review", "failed", "complete", "processing"),
            "ingestion asset binding changed",
        )
        _check_retained_document(
            _source_row(db, PARENT_SHA256), digest=PARENT_SHA256, url=URL,
            media="application/zip", size=len(parent_bytes), pages=None,
            metadata={"retention": "permanent", "ingestion_kind": "city-zip", "original_filename": _PARENT_FILENAME},
        )
        child = _source_row(db, MEMBER_SHA256)
        if child is not None:
            _check_retained_document(
                child, digest=MEMBER_SHA256, url=URL, media="application/pdf",
                size=MEMBER_BYTES, pages=2,
                metadata={
                    "retention": "permanent", "ingestion_kind": "city-pdf",
                    "original_filename": MEMBER_NAME, "archive_entry": MEMBER_NAME,
                    "parents": [PARENT_SHA256],
                },
            )
        mapping = db.execute(
            "SELECT document_id FROM source_archive_member WHERE archive_id=%s AND entry_name=%s",
            (PARENT_SHA256, MEMBER_NAME),
        ).fetchone()
        _require(mapping is None or mapping[0] == MEMBER_SHA256, "archive member mapping changed")
        _check_no_agricultural_rows(db)
        checkpoints = db.execute(
            "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
            (PARENT_SHA256, VERSION),
        ).fetchall()
        values = dict(checkpoints)
        _require(len(values) == len(checkpoints), "duplicate checkpoint steps")
        _require(not values or values.get(verified.step) == 0, "new-version checkpoint collision")
        _require(
            all(
                (step == verified.step and count == 0)
                or (step in verified.peer_steps and count > 0)
                or (step.startswith("review:") and count == 0)
                for step, count in checkpoints
            ),
            "new-version checkpoint set changed",
        )
        _check_existing_peer_parity(db, parent_bytes, values)
        if child is None:
            did = archive(
                db, URL, verified.content, "city-pdf", None,
                filename=MEMBER_NAME, parents=[PARENT_SHA256],
            )
            _require(did == MEMBER_SHA256, "archived member identity changed")
            _check_retained_document(
                _source_row(db, MEMBER_SHA256), digest=MEMBER_SHA256, url=URL,
                media="application/pdf", size=MEMBER_BYTES, pages=2,
                metadata={
                    "retention": "permanent", "ingestion_kind": "city-pdf",
                    "original_filename": MEMBER_NAME, "archive_entry": MEMBER_NAME,
                    "parents": [PARENT_SHA256],
                },
            )
        if mapping is None:
            db.execute(
                "INSERT INTO source_archive_member(archive_id,entry_name,document_id) "
                "VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (PARENT_SHA256, MEMBER_NAME, MEMBER_SHA256),
            )
        linked = db.execute(
            "SELECT document_id FROM source_archive_member WHERE archive_id=%s AND entry_name=%s",
            (PARENT_SHA256, MEMBER_NAME),
        ).fetchone()
        _require(linked == (MEMBER_SHA256,), "archive member did not retain exact identity")
        db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
            "VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING",
            (PARENT_SHA256, VERSION, verified.step),
        )
        marker = db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s",
            (PARENT_SHA256, VERSION, verified.step),
        ).fetchone()
        _require(marker == (0,), "administrative zero-row checkpoint changed")

    return city_reports.publish_city_zip(
        db, parent_bytes, PARENT_SHA256, URL, DAY, processor_version=VERSION,
    )
