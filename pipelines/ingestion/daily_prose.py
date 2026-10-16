"""Exact-original native daily prose prices; no inferred market or monetary answer."""

import hashlib
import io
import re
from datetime import date

import pdfplumber

VERSION = "daily-pdf-prose-v1"
# Paragraph fingerprints bind source layout; entries hold identity/direction only.
# Prices and percentages are parsed afresh from the PDF native text.
AUDITED = {
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf': ('9d73376d4a1297c7654bb7ccb0e865c099822843f4900be2fdeec1e3cfd3bf4a', '2020-02-04', 10, {
        (1, 2): ('29d998cf3d4c57b765ab79314bd1927e08b46a6d6fe7ff1d4b40a0057c641578', (('habichuela', 'mercado de La 41 de Pereira', '+'), ('habichuela', 'mercado de La 21 de Ibagué', '+'), ('habichuela', 'Cúcuta (Cenabastos)', '+'))),
        (1, 3): ('95f9392be958862b4945cad3b5d0eb101b63d7d0844e69666dd034b83008b0ae', (('cebolla junca', 'Cali (Santa Helena)', '+'), ('cebolla junca', 'Neiva (Surabastos)', '+'))),
        (1, 4): ('9e2a6ab3c152c5e8a07d2198621fbf041fec8c0f858140a779a64fd72511290e', (('ahuyama', 'mercado de La 41 de Pereira', '-'), ('ahuyama', 'Cali (Santa Helena)', '-'))),
        (1, 5): ('98a1fcafc0127d998cb4e23969294f5415699b3c6abcbfada9f9381e2082970d', (('pimentón', 'capital del Huila', '+'), ('pimentón', 'capital de Tolima', '-'))),
        (2, 0): ('dd46a6eb3b8bb96aa5e668c526523da9918c8f972cf667c1c097a06ed68fdfc5', (('mango Tommy', 'Tunja', '+'), ('mango Tommy', 'Bucaramanga', '+'))),
        (2, 1): ('ba761c27c35f43bd9977f7fd1b28417eebab472653dd22ec62e0f2c3f2cb63da', (('limón común', 'Cúcuta', '+'), ('limón común', 'Bucaramanga', '+'))),
        (2, 2): ('35893987c206ea23da4300541c5f1c104a1dc9d4532d2f541c698e38980f5e94', (('maracuyá', 'Tunja', '+'), ('maracuyá', 'Medellín', '+'))),
        (2, 3): ('6ac903fa133cfe4e4f612087a7356ef5bca03ded96de50b84956f5ea709ae206', (('mandarina', 'Bucaramanga', '-'), ('mandarina', 'Cúcuta', '-'), ('mandarina', 'Medellín', '+'))),
        (2, 4): ('88d69516a45c12a93f239d29ee31f331d69b8f296d22151ae647d080d82cc8c2', (('guayaba', 'Medellín', '-'), ('guayaba', 'Ibagué', '-'))),
        (3, 1): ('b1f2c89f193d59234bf05c2493ed67a2b17fcf000b2d93fdaafd9727504bc34f', (('arracacha', 'Cúcuta (Cenabastos)', '+'), ('arracacha', 'mercado La 21 de Ibagué', '+'))),
        (3, 2): ('384f1b322764f9ceca5bed5fb9a375986bafe1fd3fe68515a161453646b97541', (('yuca', 'Bucaramanga (Centroabastos)', '+'),)),
        (3, 3): ('99fc4de9cdf011ebef7692b550c3a06dcb5780a993c11d8343c1fba41707b9e6', (('papa negra', 'Cúcuta (Cenabastos)', '+'), ('papa negra', 'Pereira', '-'))),
        (3, 4): ('ae402bcb8c1cede0a57985c2d244d3d7acf6a78756ce0417c942ab78cd2437a8', (('plátano guineo', 'Central Mayorista de Antioquia (CMA)', '-'),)),
        (3, 5): ('50bcca68ad577eca5f83ecaa7ba2d5176b82de965f9457b585e73641369b9a3d', (('papa criolla', 'Central Mayorista de Antioquia (CMA)', '-'), ('papa criolla', 'Tunja', '+'))),
    }),
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf': ('2b9cd5e40d5b888bd965eedf0ce3f4e347698d80713795f841aea07c7e89769f', '2026-08-21', 12, {
        (1, 2): ('2aaaa6cc8b4791ae76acbedf0bfc0160eef9feb2a0b13c55e70efb72e21d7d5a', (('pepino cohombro', 'Ibagué, Plaza La 21', '-'), ('pepino cohombro', 'Montería, Mercado del Sur', '-'))),
        (1, 3): ('fc1151d7e6d7fe8d8b1637acb00bd8279f20af838c98e292a6c2fe8cdec14eaa', (('zanahoria', 'Villavicencio, CAV', '-'), ('zanahoria', 'Sincelejo, Nuevo Mercado', '-'))),
        (1, 4): ('a8bb73a6090775aa0e4fdd29cba2d352753ace4c99409d648572c5dde763bb25', (('chócolo mazorca', 'Ibagué, Plaza La 21', '-'), ('chócolo mazorca', 'Villavicencio, CAV', '-'))),
        (1, 5): ('570f08d755fb7479ed12ed3266d96dcafccef44c0d8a1e732d7069693da09449', (('fríjol verde', 'Ibagué, Plaza La 21', '+'), ('fríjol verde', 'Popayán, Plaza de mercado del barrio Bolívar', '+'))),
        (1, 6): ('446ab0face61f9426e59c3a0f660291ef13255aa0a4a26ea161f6845e9e89887', (('habichuela', 'Neiva, Surabastos', '+'), ('habichuela', 'Villavicencio, CAV', '+'))),
        (2, 2): ('2e0ed4f9e62bb50b494f3756c1dd18b47d83329a4c34a48636479dd05bb25449', (('banano', 'Ibagué, Plaza La 21', '-'),)),
        (2, 3): ('45fea3b9a7617253eaa9108392c13ecc763e2675bc71a8b76071622d33ea1056', (('granadilla', 'Neiva, Surabastos', '-'),)),
        (2, 4): ('f070df3c7e94259891d15f5d69fa74c7b975918b195e1b5c4a616a9bfa97e932', (('guayaba', 'Pereira, Mercasa', '-'),)),
        (2, 5): ('e1de10695032f07922c7b69824a7574a871e1ed22da81e87aefb116000d831c1', (('limón Tahití', 'Ibagué, Plaza La 21', '+'), ('limón Tahití', 'Cartagena, Bazurto', '+'))),
        (2, 6): ('f96a1ea0fda3ed6e687819bbe0eb893917655b015aab1dff8039884295472984', (('mango Tommy', 'Popayán, Plaza de mercado del barrio Bolívar', '+'), ('mango Tommy', 'Barranquilla', '+'))),
        (3, 2): ('89fd8f796d8506f60b67918e10e13a6ddcf37a23e50bb4f446786dd38d94341c', (('arracacha', 'Ibagué, Plaza La 21', '-'),)),
        (3, 3): ('0a57c5284151b5d16364242778808f30628fbcded5d5f77e32e28639486d237c', (('papa negra', 'Popayán, Plaza de mercado del barrio Bolívar', '-'),)),
        (3, 4): ('93ef8832ee1bc930052ab12ca7d1fc04e1338a53f1366a39ef6b43d8cb77c052', (('papa criolla', 'Villavicencio, CAV', '-'),)),
        (3, 5): ('2cd01e0e1b0b31959ad3393e1382a7d5d7cf6276fd98aa1b99cd035b01dffff6', (('plátano hartón verde', 'Montería, Mercado del Sur', '+'), ('plátano hartón verde', 'Villavicencio, CAV', '+'))),
    }),
}
_MONEY = re.compile(r"\$\s*(\d+(?:\.\d{3})*)")
_PERCENT = re.compile(r"(?<!\d)(\d+(?:,\d+)?)\s*%")
_DATE_PRINT = {
    date(2020, 2, 4): "4 de febrero de 2020",
    date(2026, 8, 21): "21 de agosto de 2026",
}


def _paragraphs(page, gap):
    """Only visible on-page native lines; 2020 has an off-canvas stale date."""
    lines = [line for line in page.extract_text_lines()
             if 0 <= line["top"] and line["bottom"] <= page.height]
    groups = []
    for line in lines:
        if not groups or line["top"] - groups[-1][-1]["bottom"] > gap:
            groups.append([])
        groups[-1].append(line)
    return [" ".join(line["text"] for line in group) for group in groups]


def _review(page, paragraph, index, token, text, reason):
    locator = (f"PDF page {page},paragraph {paragraph + 1},price {index + 1},"
               f"span {token.start()}:{token.end()}; {VERSION}")
    return (locator, {"native_price_literal": token.group(0), "native_paragraph": text,
                      "source_page": page, "paragraph": paragraph + 1,
                      "span_start": token.start(), "span_end": token.end()}, reason)


def parse_exact_daily_prose(data, url, did, day):
    """Return (rows,reviews) for two audited URLs, or None for other PDFs.

    A changed original or paragraph is review-only. Binding metadata contains
    no price or percentage answers; all numbers come from current native spans.
    """
    case = AUDITED.get(url)
    if case is None:
        return None
    expected_sha, expected_day, gap, schema = case
    if not data.startswith(b"%PDF-"):
        raise ValueError("Daily prose original lacks PDF signature")
    if hashlib.sha256(data).hexdigest() != did:
        raise ValueError("Daily prose retained original SHA mismatch")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        inspected_pages = pdf.pages[:3] if did == expected_sha else pdf.pages
        paragraphs = {
            (page_no, index): text
            for page_no, page in enumerate(inspected_pages, 1)
            for index, text in enumerate(_paragraphs(page, gap))
        }
        money = {
            key: list(_MONEY.finditer(text))
            for key, text in paragraphs.items() if _MONEY.search(text)
        }
        header = " ".join(
            line["text"] for line in pdf.pages[0].extract_text_lines()
            if 0 <= line["top"] and line["bottom"] <= pdf.pages[0].height
        )
        header_ok = (_DATE_PRINT.get(day, "\0") in header
                     and "SIPSA" in header.upper()
                     and day.isoformat() == expected_day)
        source_ok = (did == expected_sha and header_ok
                     and set(money) == set(schema)
                     and all(
                         hashlib.sha256(paragraphs[key].encode()).hexdigest() == schema[key][0]
                         and len(money[key]) == len(schema[key][1])
                         for key in schema
                     ))
        rows, reviews = [], []
        for (page_no, paragraph), tokens in sorted(money.items()):
            text = paragraphs[(page_no, paragraph)]
            binding = schema.get((page_no, paragraph), (None, ()))[1] if source_ok else ()
            changes = list(_PERCENT.finditer(text))
            unit = re.search(r"\b(?:kilo|kilogramo)\b", text, re.IGNORECASE)
            for index, token in enumerate(tokens):
                reason = None
                if not source_ok:
                    reason = "Unaudited changed daily prose bytes, printed date or paragraph layout"
                elif page_no == 1 and paragraph == 5 and day == date(2020, 2, 4):
                    reason = "Capital anaphora and five variations cannot bind two market prices"
                elif not unit:
                    reason = "No explicit kilo or kilogramo unit in native price paragraph"
                elif len(changes) != len(tokens):
                    reason = "Price and percentage spans cannot be paired in native order"
                elif not all(anchor.casefold() in text.casefold()
                             for anchor in binding[index][:2]):
                    reason = "Product or market anchor absent from native paragraph"
                if reason:
                    reviews.append(_review(page_no, paragraph, index,
                                           token, text, reason))
                    continue
                product, market, direction = binding[index]
                literal_change = changes[index].group(1)
                literal_price = token.group(1)
                price = int(literal_price.replace(".", ""))
                change = float(literal_change.replace(",", ".")) * (
                    -1 if direction == "-" else 1)
                locator = (f"PDF page {page_no},paragraph {paragraph + 1},"
                           f"price {index + 1},span {token.start()}:{token.end()}; {VERSION}")
                rows.append((
                    locator, "dane-daily", day, product, market, "kg", price,
                    change,
                    {"parser_version": VERSION, "source_type": "pdf-native-prose",
                     "source_page": page_no, "source_paragraph": paragraph + 1,
                     "source_span_start": token.start(),
                     "source_span_end": token.end(),
                     "source_quote": text, "price_literal": token.group(0),
                     "change_percent_literal": changes[index].group(0),
                     "variation_basis": "printed-paragraph-percent",
                     "unit_basis": "Explicit kilo/kilogramo in same paragraph",
                     "published_basis": "Quoted city/market price, not a mean or range",
                     "identity_basis": "Audited exact original and paragraph anchors"},
                ))
        if not source_ok and not reviews:
            reviews.append((f"PDF source; {VERSION}",
                            {"source_sha256": did, "source_url": url},
                            "Changed or unverified daily prose original has no audited monetary layout"))
        return rows, reviews


def review_unbound_daily_prose(data, url, did, registered_day):
    """Retain native money spans from an unrecognized zero-grid daily PDF.

    No value here is a typed price: product, market, date and unit have not
    passed the source-bound paragraph audit. Scanned image grids still go
    through the separate OCR path before this function is called.
    """
    if not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != did:
        raise ValueError("Unbound daily prose original signature or SHA mismatch")
    reviews = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            for paragraph, text in enumerate(_paragraphs(page, 10)):
                for index, token in enumerate(_MONEY.finditer(text)):
                    locator, record, _ = _review(
                        page_no, paragraph, index, token, text,
                        "Unbound daily prose monetary span")
                    record.update({"source_sha256": did, "source_url": url,
                                   "registered_day_unverified": str(registered_day)})
                    reviews.append((
                        locator, record,
                        "Native money mention lacks audited product, place, unit or printed-date binding",
                    ))
    return reviews
