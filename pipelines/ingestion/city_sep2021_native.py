"""PRIVATE exact-original Sep 2021 city ZIP fallback, derived from input bytes.

This is a staging module outside tracked runtime. Fresh pdfplumber geometry
is checked against a code-pinned, independently Poppler-audited source registry.
No mutable candidate/geometry JSON is used as parser input.
"""
import bisect
import hashlib
import io
import json
import pathlib
import re
import statistics
import zipfile
from datetime import date
from decimal import Decimal

import pdfplumber

from .worker import clean, slug
from .city_sep2021_heading import EXPECTED_MARKETS, accepted

P = pathlib.Path(__file__).resolve().parent
PARENT_SHA = "cbd378bc2d1863439c9e0a806dcdaa5026ebdd9e920fbd9c63dc1473de589edf"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-01-09-2021.zip"
MANIFEST_SHA = "f8614c18434d6d5261bf0a79c3f6badf3019503061d72bd17d10e538d7afd8f7"
HEADING_CODE_SHA = "0771038295be4ac82ab76f613483d990f305e5ecd1c0566ecad9a2bbf2860e89"
VERSION = "city-v8:sep2021-native-pinned-oracle-private-v2"
PIN_SHA = "d4618d25807e20cb742074fd24b5faa5f5cee7278e47d91ac6908625c2010062"
KNOWN = {"Verduras", "Frutas", "Tubérculos", "Túberculos", "Granos y cereales",
         "Lácteos y huevos", "Carne de res", "Carne de cerdo", "Pollo", "Pescados",
         "Procesados", "Carnes", "Huevos y lácteos", "Procesado"}
NUM = re.compile(r"^\d+(?:\.\d{3})*$")
QTY = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([A-Za-zÀ-ÿ].*)$")
BASE = {"kilogramo": ("kg", Decimal(1)), "gramo": ("kg", Decimal(".001")),
        "litro": ("litre", Decimal(1)), "mililitro": ("litre", Decimal(".001")),
        "unidad": ("unit", Decimal(1)), "unidades": ("unit", Decimal(1))}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def registry():
    path = P / "city_sep2021_members.json"
    if digest(path.read_bytes()) != MANIFEST_SHA:
        raise ValueError("Sep 2021 exact source registry changed")
    if digest((P / "city_sep2021_heading.py").read_bytes()) != HEADING_CODE_SHA:
        raise ValueError("Sep 2021 heading gate changed")
    value = json.loads(path.read_text())
    if value["url"] != URL or value["parent_document_id"] != PARENT_SHA or len(value["children"]) != 11:
        raise ValueError("Sep 2021 registry identity changed")
    if {c["document_id"] for c in value["children"]} != set(EXPECTED_MARKETS):
        raise ValueError("Sep 2021 market/member registry changed")
    return value


def _bounds(page):
    table = page.find_tables()[0]
    head = next(i for i, row in enumerate(table.extract()) if row and row[0] == "Producto")
    first = table.rows[head].cells
    second = table.rows[head + 1].cells
    result = [first[0][0], first[0][2], first[1][2], first[2][2],
              second[3][2], second[4][2], second[5][2], second[6][2]]
    if len(result) != 8 or any(a >= b for a, b in zip(result, result[1:])):
        raise ValueError("Invalid source-native city grid bounds")
    return result


def _column(bounds, word):
    return bisect.bisect_right(bounds, (word["x0"] + word["x1"]) / 2) - 1


def _source_amount(token):
    return bool(re.fullmatch(r"(?:\d+(?:[.,]\d{3})*|[-–]|n\.d\.|0)", token, re.I))


def _geometry_pages(pdf):
    bounds = _bounds(pdf.pages[0])
    pages = []
    for page_no, page in enumerate(pdf.pages, 1):
        words = [w for w in page.extract_words() if 150 <= w["top"] <= page.height - 18]
        money = [w for w in words if 3 <= _column(bounds, w) <= 6 and _source_amount(w["text"])]
        groups = []
        for word in sorted(money, key=lambda w: (w["top"], w["x0"])):
            group = next((g for g in groups if abs(statistics.median(v["top"] for v in g) - word["top"]) <= 2.5), None)
            if group is None:
                group = []
                groups.append(group)
            group.append(word)
        groups = [g for g in groups if len(g) >= 2 and
                  ({3, 4} <= {_column(bounds, w) for w in g} or
                   {5, 6} <= {_column(bounds, w) for w in g})]
        anchors = [statistics.median(w["top"] for w in g) for g in groups]
        lines = [{"top": round(top, 2), "words": []} for top in anchors]
        unmatched = []
        for word in words:
            near = [(abs(word["top"] - top), i) for i, top in enumerate(anchors)
                    if abs(word["top"] - top) <= 6]
            (lines[min(near)[1]]["words"] if near else unmatched).append(word)
        for line in lines:
            cells = [[] for _ in range(7)]
            for word in sorted(line.pop("words"), key=lambda w: w["x0"]):
                col = _column(bounds, word)
                if 0 <= col < 7:
                    cells[col].append(word["text"])
            line["cells"] = [" ".join(cell) for cell in cells]
        leftovers = []
        for word in sorted(unmatched, key=lambda w: (w["top"], w["x0"])):
            group = next((g for g in leftovers if abs(g["top"] - word["top"]) <= 2.5), None)
            if group is None:
                group = {"top": word["top"], "words": []}
                leftovers.append(group)
            group["words"].append(word)
        headings = []
        for group in leftovers:
            cells = [[] for _ in range(7)]
            for word in sorted(group["words"], key=lambda w: w["x0"]):
                col = _column(bounds, word)
                if 0 <= col < 7:
                    cells[col].append(word["text"])
            if any(cells):
                headings.append({"top": round(group["top"], 2),
                                 "cells": [" ".join(cell) for cell in cells]})
        pages.append({"page": page_no, "price_anchor_lines": lines,
                      "unmatched_native_lines": headings})
    return bounds, pages


def canonical(obj):
    def enc(x):
        if isinstance(x, Decimal): return format(x, "f")
        if isinstance(x, date): return x.isoformat()
        raise TypeError(type(x).__name__)
    return json.loads(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=enc))


def object_digest(obj):
    return digest(json.dumps(canonical(obj), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode())


def pins():
    path = P / "city_sep2021_oracle.json"
    if digest(path.read_bytes()) != PIN_SHA:
        raise ValueError("Sep 2021 independent oracle registry changed")
    data = json.loads(path.read_text())
    if data["source_parent_sha256"] != PARENT_SHA or data["source_url"] != URL:
        raise ValueError("Sep 2021 pinned oracle source changed")
    if len(data["children"]) != 11 or len(data["review_identity_hints"]) != 47:
        raise ValueError("Sep 2021 pinned oracle coverage changed")
    return data


def _pinned_cross(child_sha, pages, pin_data):
    """Re-evaluate every line from current geometry; hints downgrade ambiguity only.

    The 47 exact line hints store independent identity cells for previously
    audited ambiguous geometry. They never supply a priced answer. Every hint
    is bound to the current source line's literal seven-cell digest, and the
    resulting complete row/evidence/heading digests are checked below.
    """
    hints = {(h["page"], h["native_y"]): h for h in pin_data["review_identity_hints"]
             if h["child_sha256"] == child_sha}
    used = set(); result = []
    for page in pages:
        money = []
        for line in page["price_anchor_lines"]:
            key = (page["page"], line["top"])
            cells = list(line["cells"])
            hint = hints.get(key)
            if hint:
                if object_digest(cells) != hint["literal_cells_sha256"]:
                    raise ValueError("Sep 2021 independent ambiguous geometry changed")
                cells[:3] = hint["independent_poppler_identity_cells"]
                used.add(key)
            money.append({"top": line["top"], "cells": cells})
        headings = [{"top": line["top"], "literal": clean(line["cells"][0])}
                    for line in page["unmatched_native_lines"]
                    if clean(line["cells"][0]) in KNOWN and not any(line["cells"][1:])]
        result.append({"money": money, "headings": headings})
    if used != set(hints):
        raise ValueError("Sep 2021 independently audited ambiguous line missing")
    return result


def _range(a, b):
    if NUM.fullmatch(a) and NUM.fullmatch(b):
        low, high = Decimal(a.replace(".", "")), Decimal(b.replace(".", ""))
        if low == high == 0:
            return "noquote", None, None
        if 0 < low <= high:
            return "positive", low, high
        return "review", None, None
    if all(v in ("", "0", "-", "n.d.") for v in (a, b)):
        return "noquote", None, None
    return "review", None, None


def _row(page, top, round_no, category, cells, market, low, high):
    product, presentation, unit_cell = [clean(v) for v in cells[:3]]
    quantity_match = QTY.fullmatch(unit_cell)
    if not product or not presentation or not quantity_match or not category:
        return None
    quantity = Decimal(quantity_match[1].replace(",", "."))
    if quantity <= 0:
        return None
    source_unit = quantity_match[2]
    base = BASE.get(slug(source_unit))
    unit, factor = base if base else (source_unit, Decimal(1))
    return (f"PDF page {page},native-y {top:.2f},round {round_no}",
            date(2021, 9, 1), slug(product), product, market, category,
            presentation, quantity, source_unit, round_no, f"Ronda {round_no}",
            low, high, unit, low / (quantity * factor) if base else None,
            high / (quantity * factor) if base else None, page)


def _parse_child(child_bytes, spec):
    did = spec["document_id"]
    if digest(child_bytes) != did or not child_bytes.startswith(b"%PDF-"):
        raise ValueError("Sep 2021 child bytes/format changed")
    with pdfplumber.open(io.BytesIO(child_bytes)) as pdf:
        heading = pdf.pages[0].extract_text() or ""
        if accepted(PARENT_SHA, did, child_bytes, heading) != EXPECTED_MARKETS[did]:
            raise ValueError("Sep 2021 literal source heading changed")
        bounds, pages = _geometry_pages(pdf)
    pin_data = pins()
    market = EXPECTED_MARKETS[did]
    cross = _pinned_cross(did, pages, pin_data)
    if len(pages) != len(cross):
        raise ValueError("Sep 2021 pinned source page mismatch")
    priced, reviews, noquotes, blanks = [], [], [], []
    category = None
    line_count = category_count = 0
    for expected_page, (page, independent) in enumerate(zip(pages, cross), 1):
        if page["page"] != expected_page:
            raise ValueError("Sep 2021 source page numbering changed")
        source_lines = page["price_anchor_lines"]
        printed_lines = independent["money"]
        if len(source_lines) != len(printed_lines):
            raise ValueError("Sep 2021 independent money line count changed")
        native_headings = [line for line in page["unmatched_native_lines"]
                           if clean(line["cells"][0]) in KNOWN and not any(line["cells"][1:])]
        if len(native_headings) != len(independent["headings"]):
            raise ValueError("Sep 2021 independent category heading count changed")
        for native, source in zip(native_headings, independent["headings"]):
            if clean(native["cells"][0]) != source["literal"] or abs(native["top"] - source["top"]) > 3:
                raise ValueError("Sep 2021 independent category heading changed")
        category_count += len(native_headings)
        for line in page["unmatched_native_lines"]:
            cells = line["cells"]
            if cells[0] != "Producto" and all(cells[:3]) and not any(cells[3:]):
                blanks.append({"child_sha256": did, "page": page["page"],
                               "native_y": line["top"], "literal_cells": cells})
        events = [(line["top"], 0, line) for line in page["unmatched_native_lines"]] + [
            (line["top"], 1, (index, line)) for index, line in enumerate(source_lines)]
        for _, kind, item in sorted(events, key=lambda x: (x[0], x[1])):
            if kind == 0:
                cells = item["cells"]
                if clean(cells[0]) in KNOWN and not any(cells[1:]):
                    category = clean(cells[0])
                continue
            index, line = item
            line_count += 1
            cells = line["cells"]
            other = printed_lines[index]
            if abs(line["top"] - other["top"]) > 4.5 or ["".join(v.split()) for v in cells[3:]] != ["".join(v.split()) for v in other["cells"][3:]]:
                raise ValueError("Sep 2021 independent monetary cell changed")
            reasons = []
            if ["".join(v.split()) for v in cells[:3]] != ["".join(v.split()) for v in other["cells"][:3]]:
                reasons.append("native_decoder_identity_disagreement")
            if not category: reasons.append("category_not_explicit")
            if not cells[0]: reasons.append("product_missing")
            if not cells[1]: reasons.append("presentation_missing")
            if not cells[2]: reasons.append("unit_missing")
            elif not QTY.fullmatch(clean(cells[2])): reasons.append("quantity_not_explicit_or_unverified")
            for round_no, (a, b) in enumerate(((cells[3], cells[4]), (cells[5], cells[6])), 1):
                state, low, high = _range(a, b)
                evidence = {"child_sha256": did, "entry_name": spec["entry_name"],
                            "page": page["page"], "native_y": line["top"],
                            "round": round_no, "literal_cells": cells,
                            "category_literal": category, "range_literal": [a, b]}
                if state == "noquote":
                    noquotes.append(evidence)
                    continue
                issues = list(reasons)
                if state == "review": issues.append("price_cell_unresolved_or_invalid")
                row = _row(page["page"], line["top"], round_no, category, cells, market, low, high) if not issues else None
                if row is None and not issues: issues.append("full_field_construction_failed")
                if issues:
                    reviews.append({**evidence, "reasons": issues,
                                    "independent_poppler_identity_cells": other["cells"][:3]})
                else:
                    priced.append({"source": evidence, "fields_17": row})
    headings = [{"page": page["page"], "native_y": line["top"],
                 "literal": clean(line["cells"][0])}
                for page in pages for line in page["unmatched_native_lines"]
                if clean(line["cells"][0]) in KNOWN and not any(line["cells"][1:])]
    expected = next((item for item in pin_data["children"] if item["child_sha256"] == did), None)
    if not expected:
        raise ValueError("Sep 2021 child omitted from independent source registry")
    observed = {
        "priced_17_sha256": object_digest([x["fields_17"] for x in priced]),
        "priced_evidence_sha256": object_digest([x["source"] for x in priced]),
        "review_evidence_sha256": object_digest(reviews),
        "noquote_evidence_sha256": object_digest(noquotes),
        "blank_evidence_sha256": object_digest(blanks),
        "headings_sha256": object_digest(headings),
        "count": {k: len(v) for k, v in (("priced", priced), ("reviews", reviews),
                                           ("noquotes", noquotes), ("blanks", blanks))},
        "source_line_count": line_count, "category_heading_count": category_count,
        "page_count": len(pages),
    }
    for field, value in observed.items():
        if value != expected[field]:
            raise ValueError(f"Sep 2021 independent oracle mismatch: {field}")
    return {"child_sha256": did, "priced": priced, "reviews": reviews,
            "noquotes": noquotes, "blanks": blanks,
            "source_line_count": line_count, "category_heading_count": category_count,
            "page_count": len(pages), "derived_bounds": [round(v, 2) for v in bounds]}


def parse_exact_parent(source_url, parent_bytes):
    """Return source-local typed/evidence rows, or None for another source."""
    if source_url != URL:
        return None
    manifest = registry()
    if digest(parent_bytes) != PARENT_SHA or len(parent_bytes) != manifest["parent_byte_count"]:
        raise ValueError("Sep 2021 parent ZIP bytes changed")
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("Sep 2021 source ZIP CRC changed")
        members = [m for m in bundle.infolist() if not m.is_dir()]
        if {m.filename for m in members} != {c["entry_name"] for c in manifest["children"]}:
            raise ValueError("Sep 2021 source ZIP member names changed")
        results = []
        for spec in manifest["children"]:
            member = bundle.getinfo(spec["entry_name"])
            if member.CRC != int(spec["zip_crc32"], 16) or member.file_size != spec["byte_count"]:
                raise ValueError("Sep 2021 member CRC/size changed")
            results.append(_parse_child(bundle.read(member), spec))
    counts = {key: sum(len(child[key]) for child in results) for key in
              ("priced", "reviews", "noquotes", "blanks")}
    counts["lines"] = sum(child["source_line_count"] for child in results)
    counts["category_headings"] = sum(child["category_heading_count"] for child in results)
    counts["pages"] = sum(child["page_count"] for child in results)
    if counts != {"priced": 836, "reviews": 104, "noquotes": 634,
                  "blanks": 3, "lines": 787, "category_headings": 45, "pages": 22}:
        raise ValueError(f"Sep 2021 native source coverage changed: {counts}")
    return {"source_url": URL, "parent_sha256": PARENT_SHA,
            "parser_revision": VERSION, "counts": counts, "children": results}
