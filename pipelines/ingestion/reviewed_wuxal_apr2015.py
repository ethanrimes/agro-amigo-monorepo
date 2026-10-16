"""Source-bound correction for one April 2015 DANE input PDF heading.

The PDF literally prints ``Wuxal tapa Nnegra``. Its 47 market prices match
the independent DANE workbook's ``Wuxal Tapa Negra`` rows. Keep the literal
PDF heading and immutable v14 history; change only the v15 commercial name.
"""

import hashlib
import json
from collections import Counter
from datetime import date

URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Bol_Insumos31_abr_2015.pdf"
)
SHA256 = "58b12b179a9293e584e22473f60a97fab1b632cee35f27318953dc7de10e866c"
DAY = date(2015, 4, 30)
VERSION = "inputs-pdf-v15"
OLD_VERSION = "inputs-pdf-v14"
PAGE = 21
PRINTED_HEADING = "Wuxal tapa Nnegra, 1 litro"
PRINTED_NAME = "Wuxal tapa Nnegra"
COMMERCIAL_NAME = "Wuxal Tapa Negra"
CATEGORY = "Fertilizantes y enmiendas"
PRESENTATION = "1 litro"
FULL_PDF_ROWS = 6085

# Frozen from an independent, original DANE workbook and checked against all
# native PDF cells, not inferred from spelling similarity or other months.
MARKET_PRICES = (
    ("Andes", "Antioquia", 33177),
    ("Anserma", "Caldas", 33717),
    ("Aquitania", "Boyacá", 30667),
    ("Armenia", "Quindío", 30550),
    ("Belén de Umbría", "Risaralda", 32700),
    ("Bogotá, D.C.", "Bogotá, D.C.", 31360),
    ("Cajamarca", "Tolima", 32550),
    ("Chinchiná", "Caldas", 34650),
    ("Chiquinquirá", "Boyacá", 29733),
    ("Chitagá", "Norte de Santander", 31000),
    ("Chocontá", "Cundinamarca", 30333),
    ("Corinto", "Cauca", 30333),
    ("Cota", "Cundinamarca", 30750),
    ("Duitama", "Boyacá", 30267),
    ("El Carmen de Viboral", "Antioquia", 30013),
    ("El Santuario", "Antioquia", 29333),
    ("Funza", "Cundinamarca", 31293),
    ("Guarne", "Antioquia", 31325),
    ("Ipiales", "Nariño", 31500),
    ("La Ceja", "Antioquia", 32100),
    ("La Unión", "Antioquia", 30570),
    ("La Virginia", "Risaralda", 33233),
    ("Manizales", "Caldas", 33670),
    ("Marinilla", "Antioquia", 30720),
    ("Marsella", "Risaralda", 32150),
    ("Medellín", "Antioquia", 31510),
    ("Ocaña", "Norte de Santander", 31333),
    ("Pamplona", "Norte de Santander", 31750),
    ("Pasto", "Nariño", 31225),
    ("Pereira", "Risaralda", 31833),
    ("Peñol", "Antioquia", 29000),
    ("Piendamó", "Cauca", 31325),
    ("Popayán", "Cauca", 31250),
    ("Pupiales", "Nariño", 31333),
    ("Rionegro", "Antioquia", 31916),
    ("Samacá", "Boyacá", 29833),
    ("San Vicente Ferrer", "Antioquia", 32120),
    ("Santa Rosa de Cabal", "Risaralda", 32167),
    ("Sibaté", "Cundinamarca", 33440),
    ("Silos", "Norte de Santander", 33333),
    ("Sonsón", "Antioquia", 31560),
    ("Subachoque", "Cundinamarca", 31333),
    ("Tibaná", "Boyacá", 29800),
    ("Tunja", "Boyacá", 29667),
    ("Túquerres", "Nariño", 30320),
    ("Villapinzón", "Cundinamarca", 30667),
    ("Ábrego", "Norte de Santander", 30857),
)

# This digest covers every parsed row and physical locator before correction.
# The version tag is folded back to v14 solely for this baseline comparison.
FULL_PDF_V14_SEMANTIC_SHA256 = "b4b73b12d4ad442a007e14c0c71a81bb964c8ee743436af54e3364f7d9c69f5e"


def retained_exact_wuxal_pdf(db, url, kind, expected_version):
    """Read the exact archived original for a pending v15 replay, without HTTP.

    A mismatched asset/document pointer is ineligible. Corrupt bytes behind an
    otherwise matching pointer are an error, so callers must not fetch around
    a failed source-integrity check during host cooldown.
    """
    if url != URL or kind != "inputs-pdf" or expected_version != VERSION:
        return None
    row = db.execute(
        """SELECT d.content FROM ingestion_asset a JOIN source_document d
           ON d.id=a.document_id
           WHERE a.url=%s AND a.kind='inputs-pdf' AND a.observed_on=%s
             AND a.document_id=%s AND a.status IN ('complete','review','failed','pending')
             AND d.id=%s AND d.kind='original' AND d.source_url=a.url
             AND d.media_type='application/pdf'
             AND d.metadata->>'ingestion_kind'='inputs-pdf'
             AND NOT coalesce((a.processor_version ~ '^inputs-pdf-v[0-9]+$'
               AND substring(a.processor_version from '([0-9]+)$')::numeric>15),false)
             AND NOT EXISTS (
               SELECT 1 FROM ingestion_checkpoint c
               WHERE c.document_id=a.document_id AND c.step='inputs-pdf:published'
                 AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
                 AND substring(c.processor_version from '([0-9]+)$')::numeric>=15)
           LIMIT 1""",
        (URL, DAY, SHA256, SHA256),
    ).fetchone()
    if row is None:
        return None
    body = bytes(row[0] or b"")
    if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != SHA256:
        raise ValueError("Retained April 2015 Wuxal PDF bytes do not match its source SHA")
    return body


def _baseline_digest(rows):
    baseline = []
    for row in rows:
        values = list(row)
        values[0] = values[0].replace("; " + VERSION, "; " + OLD_VERSION)
        values[-1] = {**values[-1], "parser_version": OLD_VERSION}
        baseline.append(values)
    body = json.dumps(
        baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def validate_reviewed_rows(rows):
    """Reject a partial or changed source before any row can be published."""
    if len(rows) != FULL_PDF_ROWS or _baseline_digest(rows) != FULL_PDF_V14_SEMANTIC_SHA256:
        raise ValueError("April 2015 input PDF full native projection changed")
    target = [
        row for row in rows
        if row[-1].get("page") == PAGE
        and row[-1].get("printed_heading") == PRINTED_HEADING
    ]
    if len(target) != len(MARKET_PRICES):
        raise ValueError("April 2015 Wuxal printed table is incomplete")
    actual = Counter()
    for row in target:
        locator, series, day, name, market, unit, price, _, details = row
        if (
            series != "dane-inputs-pdf" or day != DAY
            or name != PRINTED_NAME or unit != PRESENTATION
            or details.get("category") != CATEGORY
            or details.get("presentation") != PRESENTATION
            or details.get("parser_version") != VERSION
            or details.get("printed_heading_lines") != [PRINTED_HEADING]
            or not locator.startswith(f"PDF page {PAGE},col ")
            or not locator.endswith("; " + VERSION)
            or price != int(price)
        ):
            raise ValueError("April 2015 Wuxal heading, date, package or locator changed")
        actual[(market, details.get("department"), int(price))] += 1
    if actual != Counter(MARKET_PRICES):
        raise ValueError("April 2015 Wuxal market/price vector changed")
    return target


def parse_reviewed_wuxal_apr2015(data, day, url):
    """Return all v15 rows only for the exact retained official original."""
    if (
        url != URL or day != DAY or not data.startswith(b"%PDF-")
        or hashlib.sha256(data).hexdigest() != SHA256
    ):
        raise ValueError("April 2015 Wuxal repair requires exact URL, date and PDF SHA")
    from .pdf_sources import parse_input_pdf

    rows = list(parse_input_pdf(data, day, parser_version=VERSION))
    target = validate_reviewed_rows(rows)
    target_ids = {id(row) for row in target}
    return [
        (*row[:3], COMMERCIAL_NAME, *row[4:]) if id(row) in target_ids else row
        for row in rows
    ]
