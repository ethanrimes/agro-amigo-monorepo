"""Exact retained-source evidence for one Corabastos image-only city PDF.

This is a source-specific adjudication candidate, not a generic OCR policy.
The independent local geometry remains separate from the five Gemini results.
"""

import copy
import io
import json
import zipfile
from datetime import date
from hashlib import sha256
from pathlib import Path

from pipelines.ingestion import city_reports
from pipelines.ingestion.pdf_sources import VerifiedPDFPage

URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-19oct2023.zip"
DAY = date(2023, 10, 19)
VERSION = "city-v8:corabastos-oct2023-ocr-whole-v1"
PARENT = "c9ecd972491184f1bb1df8b8df556f1aa9ee6d70a0a28336dcdf8d07dad82cd7"
CHILD = "6e7e5c976a1c49579f36df98ce72d1df29b6b6c22cbac1c656abc7fd08afa89a"
ENTRY = "Bogotá, D.C., Corabastos-19-10-2023.pdf"
OTHER_CORABASTOS = "Bogotá, D.C., Corabastos-19-10-2023 (1).pdf"
OTHER_CORABASTOS_SHA = "f57206e9fc8c948097a41dbb10c0692eca8442bea4270b868373adb2f8cbed7a"
MEMBER_OFFSET = 2080544
MEMBER_CRC = 255802679
MEMBER_SIZE = 877921
ROSTER_SHA = "eac253c04ec865fe73a953c60cf84ba8eebb002be6da02af65fd401c624c39c4"
MEMBER_STEP = "city-member:678a54eb3df9caf25c71c856134e4e662c40e0a7a6ced19e321eb11f134a6ffe"
EVIDENCE_SHA = "f46a80c16bef2b3071cb999f1fa9043c7fd873a5870af6316cdde9feee9f85a1"
EVIDENCE_NAME = "city_corabastos_20231019_local_geometry_evidence.zip"
GRID_NAME = "LOCAL_VISION_PAGE2_GRID_FIRST_B.json"
GRID_SHA = "c08fe20d2639f53f09cdeeed9d55bf22da7c725a0c02b73daeca4940ec0647d3"
GEOMETRY_SHA = "ff0ade237cad0c7433dd58715479c5cb08f6f99634e8c4b01f1a273050fe7bf9"
RENDER_SHA = "5e3171871331c3ca32347bdb525dbcac71243939c7f2281c1e553ec3f2a08d17"
# This digest is a parser-output consistency gate, not an independent source oracle.
ROWS_SHA = "957497a12b7ce88172239ef7f38626961ff4b39a729293aa9de1cc5081fa3e3e"
IMAGES = {
    1: "29af041419bf681bf76399ccd1ce925aede0496e7a2e63293f2575379aabf987",
    2: "2830361a9b5cf493605930e5d9d9f7f6480abb55e372334fc1113a815aa2447a",
    3: "1247ccf1f98cd3cae1c4a04f4f321eb9339cf44817209f3220e8ae7631de780a",
}
READINGS = {
    (1, 0): "1c31bb1b4a5052d7cfae6b35fff0c20a532057d6835eb4313c34d9dad403996a",
    (1, 1): "7af3c4d9273bc37ab48f8282235676855332351dfed3c7e52651ae4c6bb6a6d5",
    (2, 0): "30b469baaf3da4b1faf65d50b258376d960a5f27157a73c5b048e163444514ac",
    (3, 0): "878728b874d7c4625e742f1851f1a3cb6fea78e0a06ecd430789464dc6047201",
    (3, 1): "aa21a59a7607bbfc332a0fed2241f507460298dc3b81e367f13465bafccd1465",
}
OLD_ERRORS = {
    1: "Independent OCR readings disagree or contain uncertainty; not published as prices",
    2: "OCR output was blocked or truncated",
    3: "Independent OCR readings disagree or contain uncertainty; not published as prices",
}
P1_WRONG = "PRECIOS DE VENTA MAYORISTAS\nBogotá, D.C., Corabastos"
P1_PRINTED = "PRECIOS DE VENTA MAYORISTA\nBogotá, D.C., Corabastos"
P2_CELLS = (
    (5, 0, "Tuberculos, raices y platanos", "Tubérculos, raíces y platanos"),
    (6, 0, "Otros tuberculos", "Otros tubérculos"),
    (8, 0, "PIÁtano", "PlÁtano"),
    (30, 1, "Caja de cartÓn", "Caja de cartón"),
    (37, 1, "Caja de cartÓn", "Caja de cartón"),
)


def require(condition, reason):
    if not condition:
        raise ValueError("Exact Corabastos OCR source gate: " + reason)


def digest(value):
    return sha256(bytes(value)).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def rows_digest(rows):
    return digest(json.dumps([[str(v) for v in row] for row in rows],
                             ensure_ascii=False, separators=(",", ":")).encode())


def checked_member(parent):
    require(digest(parent) == PARENT, "parent ZIP bytes changed")
    with zipfile.ZipFile(io.BytesIO(parent)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        require(len(members) == 28 and all(m.filename.lower().endswith(".pdf") for m in members),
                "PDF member count changed")
        require(len({m.filename for m in members}) == 28, "duplicate member name")
        roster = [(m.filename, m.header_offset, m.CRC, m.file_size,
                   digest(archive.read(m))) for m in members]
        require(digest(json.dumps(roster, ensure_ascii=False,
                                  separators=(",", ":")).encode()) == ROSTER_SHA,
                "archive roster or bytes changed")
        matches = [m for m in members if m.filename == ENTRY]
        other = [m for m in members if m.filename == OTHER_CORABASTOS]
        require(len(matches) == len(other) == 1 and
                digest(archive.read(other[0])) == OTHER_CORABASTOS_SHA,
                "distinct Corabastos sibling changed")
        member = matches[0]
        require((member.header_offset, member.CRC, member.file_size) ==
                (MEMBER_OFFSET, MEMBER_CRC, MEMBER_SIZE), "target member ZIP identity changed")
        child = archive.read(member)
    require(digest(child) == CHILD and len(child) == MEMBER_SIZE, "target PDF bytes changed")
    require(city_reports._member_step(member, DAY) == MEMBER_STEP,
            "target member checkpoint identity changed")
    return member, child


def local_evidence():
    body = (Path(__file__).resolve().parent / EVIDENCE_NAME).read_bytes()
    require(digest(body) == EVIDENCE_SHA, "local geometry evidence archive changed")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) == 560 and
                all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
                "geometry evidence roster changed")
        grid_bytes = archive.read(GRID_NAME)
        geometry_bytes = archive.read("CELL_GEOMETRY_FIRST_A.json")
        render = archive.read("source-render/corabastos-page2-220dpi.png")
        require(digest(grid_bytes) == GRID_SHA and digest(geometry_bytes) == GEOMETRY_SHA
                and digest(render) == RENDER_SHA,
                "local grid, crop geometry or source render changed")
        grid = json.loads(grid_bytes)
        geometry = json.loads(geometry_bytes)
        require(geometry["source_pdf_sha256"] == CHILD and
                geometry["archived_page_image_id"] == IMAGES[2] and
                geometry["source_render_sha256"] == RENDER_SHA and
                len(geometry["cells"]) == 273,
                "local cell geometry source binding changed")
        for cell in geometry["cells"]:
            name = "cells-3x-first-a/" + cell["png"]
            require(digest(archive.read(name)) == cell["sha256"],
                    "local source crop changed")
        for n in range(1, 40):
            for c in range(7):
                name = f"vision-273-first-a/r{n:02d}_c{c}-vision.json"
                require(name in names, "local cell OCR output missing")
        for n in (24, 25, 26, 27, 28, 29, 30):
            require(f"vision-7-first-a/r{n:02d}_c5-vision.json" in names,
                    "local price recovery cell missing")
    return body, grid


def projected_pages(readings, local_grid):
    require(set(readings) == set(READINGS), "cached provider result set changed")
    for key, expected in READINGS.items():
        require(digest(canonical(readings[key])) == expected and
                readings[key].get("review_notes") == [],
                "cached provider result or uncertainty changed")
    p1a = copy.deepcopy(readings[(1, 0)])
    require(p1a["text"].count(P1_WRONG) == 1, "page 1 plural transcription drift")
    p1a["text"] = p1a["text"].replace(P1_WRONG, P1_PRINTED)
    p1b = copy.deepcopy(readings[(1, 1)])
    require(p1b["text"].count(P1_PRINTED) == 1, "page 1 printed heading drift")
    changed = []
    for index, row in enumerate(p1b["tables"][0], 1):
        if row[1] == "Caja de cartÓn":
            changed.append(index)
            row[1] = "Caja de cartón"
    require(changed == [13, 30, 31, 32, 40, 46], "page 1 package case positions changed")
    p2local = copy.deepcopy(local_grid)
    require(len(p2local["tables"]) == 1 and len(p2local["tables"][0]) == 51,
            "page 2 local grid size changed")
    for row, col, before, after in P2_CELLS:
        require(p2local["tables"][0][row - 1][col] == before,
                "page 2 bounded source label moved")
        p2local["tables"][0][row - 1][col] = after
    return (p1a, p1b), (readings[(2, 0)], p2local), (
        readings[(3, 0)], readings[(3, 1)])


def checked_rows(readings, local_grid):
    variants = projected_pages(readings, local_grid)
    expected = None
    for first in variants[0]:
        for second in variants[1]:
            for third in variants[2]:
                pages = [VerifiedPDFPage(v) for v in (first, second, third)]
                rows = list(city_reports.parse_city_pages(pages, heading=first["text"]))
                require(len(rows) == 196 and all(len(row) == 17 for row in rows),
                        "whole three-page price vector changed")
                require([sum(row[0].startswith(f"PDF page {p},") for row in rows)
                         for p in (1, 2, 3)] == [86, 78, 32],
                        "page locator distribution changed")
                require(len({row[0] for row in rows}) == 196 and
                        {row[1] for row in rows} == {DAY} and
                        {row[4] for row in rows} == {"Bogotá, D.C., Corabastos"} and
                        all(row[7] > 0 and row[11] > 0 and row[12] >= row[11]
                            and row[16] in (1, 2, 3) for row in rows),
                        "date, market, quantity, amount or locator changed")
                row_sha = rows_digest(rows)
                require(row_sha == ROWS_SHA, "whole parser-output consistency changed")
                if expected is None:
                    expected = rows
                else:
                    require(rows == expected, "cached/local source readings disagree")
    return expected
