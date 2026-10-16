"""Review two missing city PDF links using separately retained originals.

This does not recover the missing PDF, publish a quote, or fetch another URL.
Legacy city-v3 parents have no member checkpoints; a same-byte city-v8 replay
requires every reviewed child to have its exact current member checkpoint.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path

from pipelines.ingestion.daily_publication import retain_resolution


VERSION = "city-pdf-related-originals-v1"
_FILE = Path(__file__).with_name("reviewed_city_pdf_related.json")
_MANIFEST_SHA = "10f691fa53eeb8080744450fae64f1835adb50123bfd816774aeabc214a20f36"


def _rules() -> dict[str, dict]:
    data = _FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != _MANIFEST_SHA:
        raise ValueError("Reviewed related-original manifest changed")
    return {r["missing_url"]: r for r in json.loads(data)["rules"]}


def _one(db, sql, args):
    row = db.execute(sql, args).fetchone()
    if row is None:
        raise ValueError("Pinned related original database row is missing")
    return row


def _source(db, did, url, media, ingestion_kind, parent=None, filename=None):
    row = _one(
        db,
        "SELECT source_url,media_type,kind,metadata,content,page_count,publisher "
        "FROM source_document WHERE id=%s",
        (did,),
    )
    source_url, actual_media, kind, metadata, raw, pages, publisher = row
    body = bytes(raw)
    if (
        source_url != url
        or actual_media != media
        or kind != "original"
        or publisher != "DANE"
        or metadata.get("ingestion_kind") != ingestion_kind
        or metadata.get("retention") != "permanent"
        or metadata.get("original_filename") != (
            filename if filename else url.rsplit("/", 1)[-1]
        )
        or metadata.get("parents") != ([parent] if parent else None)
        or metadata.get("archive_entry") != filename
        or hashlib.sha256(body).hexdigest() != did
        or (media == "application/pdf" and not pages)
    ):
        raise ValueError("Pinned related original ownership or bytes changed")
    return body


def review_after_404(db, url: str, status: int | None, day: date | None) -> bool:
    from pipelines.ingestion import city_reports

    rule = _rules().get(url)
    if rule is None or status not in (404, 410):
        return False
    if day != date.fromisoformat(rule["requested_day"]):
        raise ValueError("Missing city PDF date differs from official link")
    with db.transaction():
        previous = _one(
            db,
            "SELECT kind,observed_on,status,document_id,records,processor_version,"
            "attempts,error FROM ingestion_asset WHERE url=%s FOR UPDATE",
            (url,),
        )
        if (
            previous[0] != "city-pdf"
            or previous[1] != day
            or previous[2] not in ("pending", "failed", "review")
            or previous[3] is not None
            or previous[4] != 0
        ):
            raise ValueError("Missing city PDF asset is no longer an unpriced link")
        later = _one(
            db,
            "SELECT kind,observed_on,status,document_id,processor_version,records "
            "FROM ingestion_asset WHERE url=%s FOR SHARE",
            (rule["later_zip_url"],),
        )
        expected_later = (
            "city-zip", date.fromisoformat(rule["later_zip_day"]), "complete",
            rule["later_zip_id"],
        )
        if (
            later[:4] != expected_later
            or later[4] not in (rule["later_zip_asset_version"], city_reports.VERSION)
            or later[5] != rule["later_zip_asset_records"]
        ):
            raise ValueError("Later ZIP is not its exact completed source revision")
        body = _source(
            db, rule["later_zip_id"], rule["later_zip_url"],
            "application/zip", "city-zip",
        )
        if (
            len(body) != rule["later_zip_bytes"]
            or hashlib.sha256(body).hexdigest() != rule["later_zip_id"]
        ):
            raise ValueError("Later ZIP bytes changed")
        # These exact completed city-v3 parents predate per-member checkpoints.
        # A current-production indexed read found zero for both, so requiring
        # invented v3 steps would erase truthful historical source evidence.
        (legacy_checkpoints,) = _one(
            db,
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version='city-v3' AND step LIKE 'city-member:%%'",
            (rule["later_zip_id"],),
        )
        if legacy_checkpoints:
            raise ValueError("Legacy city-v3 checkpoint state changed")
        current_steps = dict(db.execute(
            "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step LIKE 'city-member:%%'",
            (rule["later_zip_id"], city_reports.VERSION),
        ).fetchall())
        if later[4] == rule["later_zip_asset_version"] and current_steps:
            raise ValueError("Legacy city-v3 parent has unexpected current checkpoints")
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            members = [m for m in bundle.infolist() if not m.is_dir()]
            names = [m.filename for m in members]
            if len(names) != len(set(names)):
                raise ValueError("Later ZIP has duplicate entry names")
            if len({r["document_id"] for r in rule["children"]}) != len(rule["children"]):
                raise ValueError("Reviewed child identities repeat")
            checked_rows = 0
            reviewed_steps = set()
            for child in rule["children"]:
                if child["printed_day"] != rule["requested_day"]:
                    raise ValueError("Related child printed day changed")
                member = bundle.getinfo(child["filename"])
                step = city_reports._member_step(
                    member, date.fromisoformat(rule["later_zip_day"]))
                if step in reviewed_steps:
                    raise ValueError("Reviewed city member step repeats")
                reviewed_steps.add(step)
                if later[4] == city_reports.VERSION and (
                    current_steps.get(step) != child["native_rows"]
                ):
                    raise ValueError("Current city member checkpoint missing or changed")
                member_body = bundle.read(member)
                if (
                    member.CRC != child["crc32"]
                    or len(member_body) != child["bytes"]
                    or hashlib.sha256(member_body).hexdigest() != child["document_id"]
                ):
                    raise ValueError("Related city child bytes or CRC changed")
                (mapped,) = _one(
                    db,
                    "SELECT document_id FROM source_archive_member "
                    "WHERE archive_id=%s AND entry_name=%s",
                    (rule["later_zip_id"], child["filename"]),
                )
                if mapped != child["document_id"]:
                    raise ValueError("Related child archive mapping changed")
                stored = _source(
                    db, child["document_id"], rule["later_zip_url"],
                    "application/pdf", "city-pdf", rule["later_zip_id"],
                    child["filename"],
                )
                if stored != member_body:
                    raise ValueError("Related city child differs from ZIP member")
                import pdfplumber
                from pipelines.ingestion.city_reports import (
                    _PRICE_FIELDS, _publication_parity, parse_city_pages,
                )

                with pdfplumber.open(io.BytesIO(stored)) as pdf:
                    native = list(parse_city_pages(
                        pdf.pages, date.fromisoformat(rule["later_zip_day"])))
                if (
                    len(native) != child["native_rows"]
                    or any(row[1] != day for row in native)
                ):
                    raise ValueError("Related child full native grid changed")
                _, _, parity = _publication_parity(
                    db, child["document_id"], native, require_all=True)
                if parity["difference_count"] or parity["native_count"] != child["native_rows"]:
                    raise ValueError("Related child raw/class full source parity changed")
                expected = {row[0]: row[1:] for row in native}
                conflict = db.execute(
                    "SELECT 1 FROM unresolved_city_pdf_publication_conflict "
                    "WHERE document_id=%s LIMIT 1", (child["document_id"],),
                ).fetchone()
                if conflict:
                    raise ValueError("Related child now has a publication conflict")
                for relation in ("published_regional_price", "resolved_regional_price"):
                    # Relation and columns are fixed source code, never ZIP data.
                    current = {
                        record[0]: record[1:]
                        for record in db.execute(
                            f"SELECT source_locator,{','.join(_PRICE_FIELDS)} "
                            f"FROM {relation} WHERE document_id=%s",
                            (child["document_id"],),
                        ).fetchall()
                    }
                    if current != expected:
                        raise ValueError("Related child published/resolved full grid changed")
                checked_rows += child["native_rows"]
        if (len(rule["children"]), checked_rows) != (
            rule["requested_day_child_count"], rule["requested_day_native_rows"],
        ):
            raise ValueError("Related requested-day source coverage changed")
        record = {
            "review_version": VERSION,
            "missing_url": url,
            "missing_kind": "city-pdf",
            "original_http_status": status,
            "requested_day": rule["requested_day"],
            "official_link_label": rule["official_link_label"],
            "later_zip_url": rule["later_zip_url"],
            "later_zip_document_id": rule["later_zip_id"],
            "later_zip_kind": "city-zip",
            "related_child_document_ids": rule["related_label_child_ids"],
            "other_requested_day_child_ids": sorted(
                set(c["document_id"] for c in rule["children"])
                - set(rule["related_label_child_ids"])
            ),
            "requested_day_child_count": len(rule["children"]),
            "requested_day_current_rows": checked_rows,
            "legacy_city_v3_member_checkpoints": 0,
            "current_city_member_checkpoints_checked": (
                len(reviewed_steps) if later[4] == city_reports.VERSION else 0
            ),
            "missing_pdf_bytes_recovered": False,
            "same_media_or_bytes": False,
            "missing_pdf_complete_roster_known": False,
        }
        if previous[2] == "failed" and previous[7]:
            retain_resolution(db, "source_link_initial_failure", {
                "missing_url": url,
                "requested_day": rule["requested_day"],
                "status": "failed",
                "error": previous[7][:500],
            })
        retain_resolution(db, "source_link_related_originals", record)
        updated = db.execute(
            "UPDATE ingestion_asset SET status='review',checked_at=now(),"
            "attempts=attempts+1,processor_version='city-direct-pdf-v1',"
            "error='Official city PDF link returned 404/410; distinct later ZIP "
            "retains verified requested-day originals; missing PDF remains unavailable' "
            "WHERE url=%s AND kind='city-pdf' AND observed_on=%s "
            "AND document_id IS NULL AND records=0 RETURNING url",
            (url, day),
        ).fetchone()
        if updated != (url,):
            raise ValueError("Missing city PDF changed before review commit")
    return True
