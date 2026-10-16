"""Conservative source-bound native daily prose first-price extraction."""
import hashlib
import io
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import pdfplumber

from pipelines.ingestion.daily_prose import _MONEY, _PERCENT, _paragraphs

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = json.loads((ROOT / "shared/label-normalization.json").read_text())["domains"]
PRODUCTS = DOMAINS["product"]
PLACES = DOMAINS["place"]
REGISTRY_SHA = hashlib.sha256((ROOT / "shared/label-normalization.json").read_bytes()).hexdigest()
VERSION = "daily-pdf-prose-generic-v1:labels-" + REGISTRY_SHA[:12]
OLD_UNBOUND_ASSET_VERSION = (
    "daily-pdf-v6:supply-daily-pdf-summary-v1:unbound-prose-review-v1"
)
MONTHS = {name: number for number, name in enumerate(
    ("ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"),1)}
MONTH_FULL = ("enero","febrero","marzo","abril","mayo","junio","julio","agosto",
              "septiembre","octubre","noviembre","diciembre")
URL_RE = re.compile(r"^https://www\.dane\.gov\.co/files/operaciones/SIPSA/"
                    r"bol-SIPSADiario-(\d{2})([a-z]{3})(\d{4})\.pdf$")


def eligible_url(url):
    return bool(URL_RE.fullmatch(url))


def retained_unbound_original(db, url, kind, expected_version):
    """Replay only an exact old review source under publisher cooldown.

    A different source revision or a partially priced source must use ordinary
    transport/adjudication. No DANE request is made by this selector.
    """
    match = URL_RE.fullmatch(url) if kind == "daily-pdf" else None
    if match is None:
        return None
    from .daily_prose import AUDITED

    if url in AUDITED or expected_version != OLD_UNBOUND_ASSET_VERSION + ":" + VERSION:
        return None
    row = db.execute(
        """SELECT d.id,d.content,a.observed_on FROM ingestion_asset a
        JOIN source_document d ON d.id=a.document_id
        WHERE a.url=%s AND a.kind='daily-pdf' AND a.status='review'
          AND a.records=0 AND a.processor_version=%s
          AND a.error ~ '^Native prose requires review for [0-9]+ monetary spans$'
          AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/pdf'
          AND d.metadata->>'ingestion_kind'='daily-pdf'
          AND NOT EXISTS(SELECT 1 FROM historical_price h
            WHERE h.document_id=d.id)""",
        (url, OLD_UNBOUND_ASSET_VERSION),
    ).fetchone()
    if row is None:
        return None
    did, content, observed_on = row
    try:
        url_day = date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
    except (KeyError, ValueError) as exc:
        raise ValueError("Retained prose source URL has invalid day") from exc
    if observed_on != url_day:
        raise ValueError("Retained prose observed day differs from exact URL")
    body = bytes(content or b"")
    if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != did:
        raise ValueError("Retained prose original bytes differ from immutable SHA")
    return body
UP = re.compile(r"\b(?:aument[oó]|increment[oó]|subi[oó]|subi[oó]eron|alza|ascenso)\b", re.I)
DOWN = re.compile(r"\b(?:disminuci[oó]n|reducci[oó]n|baj[oó]|descendi[oó]|decreci[oó]|redujo|cay[oó])\b", re.I)
UNIT = re.compile(r"\b(?:kilo|kilogramo)\b", re.I)
SCOPE = re.compile(r"\b(?:promedio|minimo|mínimo|maximo|máximo|rango)\b", re.I)
HISTORICAL_OR_CONDITIONAL = re.compile(
    r"\b(?:ayer|anteayer|anterior|pasad[oa]|historico|estimad[oa]|proyectad[oa]|"
    r"hipotetic[oa]|habria|podria|esperad[oa]|previo|condicional|si hubiera|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|"
    r"noviembre|diciembre|20\d{2})\b")
UNBOUND_NEGATION = re.compile(r"\b(?:no|sin|si)\b")
NEGATED_SALE = re.compile(
    r"\b(?:no|sin)\s+(?:(?:se|fue|hubo)\s+)?(?:vend|ofrec|cotiz|comercializ|precio)")
PRICE_LITERAL = r"\$\s*\d+(?:\.\d{3})*"
EXPLICIT_UNIT_SALE = re.compile(
    r"(?:\b(?:comercializandose|ofertandose|ofreciendose|cotizandose|vendiendose)\s+"
    r"(?:el\s+)?(?:kilo|kilogramo)\s+a\s+|"
    r"\b(?:el\s+)?(?:kilo|kilogramo)\s+se\s+"
    r"(?:ofrecio|vendio|comercializo|cotizo)\s+a\s+)" + PRICE_LITERAL)
AFTER_PRICE_UNIT_SALE = re.compile(
    r"\b(?:comercializandose|ofertandose|ofreciendose|cotizandose|vendiendose)\s+"
    r"a\s+" + PRICE_LITERAL + r"\s+(?:el|por)\s+(?:kilo|kilogramo)\b")


def fold(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def exact_token(haystack, needle):
    return re.search(r"(?<!\w)" + re.escape(fold(needle)) + r"(?!\w)", fold(haystack))


def product(pre_percent):
    hits = sorted((p for p in PRODUCTS if exact_token(pre_percent,p)), key=len, reverse=True)
    maximal = [p for p in hits if not any(fold(p) in fold(q) and p != q for q in hits)]
    return maximal[0] if len(maximal) == 1 else None, maximal


def place(pre_money):
    hits = []
    for label in PLACES:
        if ", " not in label:
            continue
        city, site = label.split(", ",1)
        if city == "Bogotá" and site.startswith("D.C., "):
            site = site[len("D.C., "):]
        source=fold(pre_money)
        city_f,site_f=fold(city),fold(site)
        city_site=re.search(r"\ben\s+"+re.escape(city_f)+r"\s*,\s*"+
                            re.escape(site_f)+r"\b",source)
        site_city=re.search(r"\ben\s+(?:(?:el|la)\s+)?(?:(?:mercado)\s+de\s+)?"+
                            re.escape(site_f)+r"\s+en\s+"+re.escape(city_f)+r"\b",source)
        if city_site or site_city:
            hits.append(label)
    return hits[0] if len(hits) == 1 else None,hits


def source_market_span(prefix, label):
    """Return only an explicit sale-market phrase, never a bare source city."""
    city,site=label.split(", ",1)
    if city=="Bogotá" and site.startswith("D.C., "):
        site=site[len("D.C., "):]
    source=fold(prefix)
    city_f,site_f=fold(city),fold(site)
    forms=(r"\ben\s+"+re.escape(city_f)+r"\s*,\s*"+re.escape(site_f)+r"\b",
           r"\ben\s+(?:(?:el|la)\s+)?(?:(?:mercado)\s+de\s+)?"+
           re.escape(site_f)+r"\s+en\s+"+re.escape(city_f)+r"\b")
    matches=[m for pattern in forms for m in re.finditer(pattern,source)]
    return matches[0] if len(matches)==1 else None


def literal_source_caption(prefix, market):
    """Bounded observed noun phrase, not a fuzzy catalog mapping.

    Only the grammatical subject of this very price sentence is allowed. The
    returned source caption is preserved verbatim as a distinct raw identity.
    """
    sale=source_market_span(prefix,market)
    if sale is None:
        return None
    if len(fold(prefix))!=len(prefix):
        return None
    without=prefix[:sale.start()]+" "+prefix[sale.end():]
    without=re.sub(r"^\s*[,;:]\s*","",without)
    without=re.sub(r"^(?:(?:Por el contrario|Para finalizar|Finalmente|Asimismo|Igualmente),\s*)",
                   "",without,flags=re.I)
    without=without.lstrip(" ,;:")
    folded=fold(without)
    starts=(
        r"^(?:en cuanto|respecto)\s+(?:a\s+(?:la|el)|al)\s+",
        r"^(?:el|la)\s+precio\s+de\s+(?:la|el|del)\s+",
        r"^(?:la|el)\s+precio\s+del\s+",
        r"^(?:la|el)\s+",
    )
    start=next((m.end() for pattern in starts if (m:=re.match(pattern,folded))),None)
    if start is None:
        return None
    remainder=without[start:]
    stop=re.search(r"(?:,|\b(?:presento|tuvo|subio|bajo|aumento|redujo|descendio|"
                   r"decrecio|crecio)\b)",fold(remainder))
    if stop is None:
        return None
    caption=remainder[:stop.start()].strip(" ,;:")
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ -][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+){0,5}",caption):
        return None
    if re.search(r"\b(?:y|e|o|u)\b",fold(caption)):
        return None
    if not 3<=len(caption)<=48 or fold(caption) in {
        "precio","mercado","cotizacion","producto","hortaliza","fruta",
        "tuberculo","raiz","citrico","alimento","verdura",
    }:
        return None
    return caption


def first_quote(text):
    money = list(_MONEY.finditer(text))
    if not money:
        return None,"no_money"
    first = money[0]
    # _MONEY also matches a prefix of decimal/comma or abbreviated-scale
    # amounts. Such native tokens have no unambiguous whole-peso value.
    after_money=text[first.end():]
    if (int(first.group(1).replace(".","")) <= 0
            or re.match(r"[,.]\d",after_money)
            or re.match(r"\s*(?:mil|millon(?:es)?)\b",fold(after_money))):
        return None,"money_token_not_exact_positive_pesos"
    prefix = text[:first.start()]
    folded=fold(text[:first.end()+30])
    prefix_folded=fold(prefix)
    if re.search(r"\.\s+[A-ZÁÉÍÓÚ]",prefix):
        return None,"money_not_in_first_sentence"
    if (HISTORICAL_OR_CONDITIONAL.search(prefix_folded)
            or UNBOUND_NEGATION.search(prefix_folded)
            or NEGATED_SALE.search(prefix_folded)):
        return None,"historical_conditional_or_negated_quote"
    if not re.search(r"\b(?:precio|cotizacion)\b",prefix_folded):
        return None,"no_explicit_price_subject"
    changes = [p for p in _PERCENT.finditer(prefix)]
    if len(changes) != 1:
        return None,"first_percent_not_unique"
    market, market_hits = place(prefix)
    if not market:
        return None,"market_not_unique_or_named"
    # Extract the whole printed grammatical subject before any registry lookup.
    # A shorter known label within an unknown variety must never merge.
    raw_caption=literal_source_caption(prefix,market)
    if raw_caption is None:
        return None,"product_caption_not_explicit_unique"
    product_hits=[p for p in PRODUCTS if fold(p)==fold(raw_caption)]
    if len(product_hits)>1:
        return None,"product_label_collision"
    p=product_hits[0] if product_hits else raw_caption
    # Unit and money must be one observed sale relation; proximity is unsafe.
    relation_start=max(0,first.start()-80)
    source_relation=fold(text[relation_start:first.end()+30])
    relative_price_start=len(fold(text[relation_start:first.start()]))
    relative_price_end=relative_price_start+len(fold(first.group(0)))
    direct=[m for pattern in (EXPLICIT_UNIT_SALE,AFTER_PRICE_UNIT_SALE)
            for m in pattern.finditer(source_relation)]
    if len(direct)!=1 or not (direct[0].start()<=relative_price_start
                              and relative_price_end<=direct[0].end()):
        return None,"unit_money_sale_relation_absent"
    if SCOPE.search(prefix):
        return None,"aggregate_or_range_scope"
    # Direction belongs to the price-change predicate before its percentage.
    # A later increase in supply describes a cause, not the price direction.
    price_change_clause=prefix[:changes[0].start()]
    up = bool(UP.search(price_change_clause))
    down = bool(DOWN.search(price_change_clause))
    if up == down:
        return None,"direction_not_unique"
    return {"product":p,"market":market,"price":int(first.group(1).replace(".","")),
            "change_percent":float(changes[0].group(1).replace(",",".")) * (1 if up else -1),
            "literal_price":first.group(0),"literal_percent":changes[0].group(0),
            "price_span":[first.start(),first.end()],"market_candidates":market_hits,
            "product_candidates":product_hits,"source_product_caption":raw_caption,
            "product_basis":"known_exact_label" if product_hits else "literal_native_caption"},None


def bound_day(url, day, header):
    """Never infer a date from URL alone; URL, registered day and print must agree."""
    match = URL_RE.fullmatch(url)
    if not match or match.group(2) not in MONTHS:
        return False
    try:
        url_day = date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
    except ValueError:
        return False
    printed = f"{day.day} de {MONTH_FULL[day.month-1]} de {day.year}"
    # The graphic title is not native text in these PDFs. Use the actual
    # native section/publisher/form text, rather than pretending it is.
    return (url_day == day and printed in header and "VERDURAS Y HORTALIZAS" in header
            and "SIPSA" in header and "COM-070-GUI-009-f-001" in header)


def parse_generic(data, url, did, day):
    """Return native source rows and explicit review spans for one original."""
    if not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != did:
        raise ValueError("retained original signature or SHA mismatch")
    rows, reviews = [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not 1 <= len(pdf.pages) <= 12:
            raise ValueError("daily prose page count outside bounded native layout")
        header = pdf.pages[0].extract_text() or ""
        source_ok = bound_day(url,day,header)
        for page_no,page in enumerate(pdf.pages,1):
            for paragraph_no,text in enumerate(_paragraphs(page,10),1):
                spans=list(_MONEY.finditer(text))
                if not spans:
                    continue
                first, first_reason = first_quote(text) if source_ok and page_no <= 3 else (
                    None,"printed_date_or_layout_unbound")
                for ordinal,span in enumerate(spans,1):
                    locator=(f"PDF page {page_no},paragraph {paragraph_no},price {ordinal},"
                             f"span {span.start()}:{span.end()}; {VERSION}")
                    common={"source_page":page_no,"source_paragraph":paragraph_no,
                            "source_span_start":span.start(),"source_span_end":span.end(),
                            "source_quote":text,"price_literal":span.group(0),
                            "parser_version":VERSION,"label_registry_sha256":REGISTRY_SHA,
                            "source_type":"pdf-native-prose"}
                    if ordinal != 1 or first is None:
                        reason="later_money_requires_explicit_product_binding" if ordinal != 1 else first_reason
                        reviews.append((locator,{**common,"reason_code":reason},
                                        "Generic prose money mention lacks unique explicit source binding"))
                        continue
                    details={**common,"change_percent_literal":first["literal_percent"],
                             "source_product_caption":first["source_product_caption"],
                             "product_basis":first["product_basis"],
                             "unit_basis":"Explicit kilo/kilogramo adjacent to native money span",
                             "published_basis":"Quoted market price, not a mean or range",
                             "identity_basis":"Unique exact product/place lexicon matches before first price"}
                    rows.append((locator,"dane-daily",day,first["product"],first["market"],
                                 "kg",first["price"],first["change_percent"],details))
    return rows,reviews

