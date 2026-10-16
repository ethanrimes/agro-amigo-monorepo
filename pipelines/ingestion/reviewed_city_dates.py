"""Exact retained originals whose printed city dates contradict their ZIP link.

This review list never infers a date from a filename or relaxes generic date
validation. Both original hashes, the literal member name and the complete
native price grid must match. The parent remains a source-date review.
"""

import json
from datetime import date
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from pathlib import Path


def rows_digest(rows):
    def encode(value):
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        if isinstance(value, date):
            return value.isoformat()
        raise TypeError(type(value).__name__)

    return sha256(json.dumps(
        sorted(rows, key=lambda row: row[0]), ensure_ascii=False,
        separators=(",", ":"), default=encode,
    ).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _reviews():
    report = json.loads(Path(__file__).with_name("reviewed_city_dates.json").read_text())
    if report["format"] != 1:
        raise ValueError("Unsupported city source-date review format")
    return report["archives"]


def reviewed_parent(data, archive_id, source_url, archive_day):
    for review in _reviews():
        if (
            review["archive_id"] == archive_id
            and review["url"] == source_url
            and review["archive_day"] == str(archive_day)
            and sha256(data).hexdigest() == archive_id
        ):
            return review
    return None


def reviewed_member(parent, entry_name, child_pdf=None):
    if parent is None:
        return None
    matches = [member for member in parent["members"] if member["entry_name"] == entry_name]
    if len(matches) != 1:
        return None
    member = matches[0]
    if child_pdf is not None and sha256(child_pdf).hexdigest() != member["document_id"]:
        return None
    return member


def validate_rows(member, rows):
    if (
        len(rows) != member["rows"]
        or any(row[1] != date.fromisoformat(member["printed_day"])
               or row[4] != member["market_name"] for row in rows)
        or rows_digest(rows) != member["native_rows_sha256"]
    ):
        raise ValueError("Reviewed city source-date original or native price grid changed")


def source_review(parent, member):
    return {
        "filename": member["entry_name"],
        "document_id": member["document_id"],
        "error": (
            f"{member['rows']} native price ranges published at printed {member['printed_day']}; "
            f"parent ZIP link is dated {parent['archive_day']}"
        ),
        "error_type": "SourceDateMismatch",
    }
