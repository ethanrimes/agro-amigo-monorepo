"""Official international benchmarks, kept separate from Colombian COP prices.

No network access occurs while parsing. The caller archives each original and
versions mutable URLs before publishing the returned observations.
"""

from __future__ import annotations

import calendar
import io
import math
import re
import unicodedata
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import openpyxl
from bs4 import BeautifulSoup

WORLD_BANK_HOME = "https://www.worldbank.org/en/research/commodity-markets"
WORLD_BANK_INDEX = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet"
WORLD_BANK_MONTHLY = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
USDA_MIAMI = "https://www.ams.usda.gov/mnreports/mh_fv221.pdf"
USDA_BOSTON = "https://www.ams.usda.gov/mnreports/bh_fv201.pdf"
VERSION = "official-international-v2"

# Explicit series selection excludes energy, metals, indices and tobacco import
# unit values. An import unit value is not an observed product market price.
# Tuple: Spanish display name, category, unique Description-sheet prefix.
WB_SERIES = {
    "Cocoa": ("Cacao · ICCO", "Cacao", "Cocoa (ICCO)"),
    "Coffee, Arabica": ("Café arábica · otros suaves ICO", "Café", "Coffee, Arabica"),
    "Coffee, Robusta": ("Café robusta · ICO", "Café", "Coffee, Robusta"),
    "Tea, avg 3 auctions": ("Té · promedio de tres subastas", "Té", "Tea, average"),
    "Tea, Colombo": ("Té · Colombo", "Té", "Tea (Colombo"),
    "Tea, Kolkata": ("Té · Kolkata", "Té", "Tea (Kolkata"),
    "Tea, Mombasa": ("Té · Mombasa", "Té", "Tea (Mombasa"),
    "Coconut oil": ("Aceite de coco", "Aceites y oleaginosas", "Coconut oil"),
    "Groundnuts": ("Maní", "Aceites y oleaginosas", "Peanut (Groundnut),"),
    "Fish meal": ("Harina de pescado", "Alimentos para animales", "Fish meal,"),
    "Groundnut oil": (
        "Aceite de maní",
        "Aceites y oleaginosas",
        "Peanut (Groundnut) oil",
    ),
    "Palm oil": ("Aceite de palma", "Aceites y oleaginosas", "Palm oil ("),
    "Palm kernel oil": (
        "Aceite de palmiste",
        "Aceites y oleaginosas",
        "Palmkernel oil",
    ),
    "Soybeans": ("Soya en grano", "Aceites y oleaginosas", "Soybeans,"),
    "Soybean oil": ("Aceite de soya", "Aceites y oleaginosas", "Soybean oil,"),
    "Soybean meal": ("Harina de soya", "Alimentos para animales", "Soybean meal,"),
    "Rapeseed oil": ("Aceite de colza", "Aceites y oleaginosas", "Rapeseed Oil,"),
    "Sunflower oil": ("Aceite de girasol", "Aceites y oleaginosas", "Sunflower oil,"),
    "Barley": ("Cebada forrajera", "Cereales", "Barley (U.S.)"),
    "Maize": ("Maíz amarillo", "Cereales", "Maize (U.S.)"),
    "Sorghum": ("Sorgo", "Cereales", "Sorghum (US)"),
    "Rice, Thai 5%": (
        "Arroz tailandés · 5 % partido",
        "Cereales",
        "Rice (Thailand), 5%",
    ),
    "Rice, Thai 25%": (
        "Arroz tailandés · 25 % partido",
        "Cereales",
        "Rice (Thailand), 25%",
    ),
    "Rice, Thai A.1": ("Arroz tailandés · A.1", "Cereales", "Rice (Thailand), 100%"),
    "Rice, Viet Namese 5%": (
        "Arroz vietnamita · 5 % partido",
        "Cereales",
        "Rice (Vietnam),",
    ),
    "Wheat, US SRW": (
        "Trigo estadounidense · SRW",
        "Cereales",
        "Wheat (U.S.), no. 2, soft",
    ),
    "Wheat, US HRW": (
        "Trigo estadounidense · HRW",
        "Cereales",
        "Wheat (U.S.), no. 2 hard",
    ),
    "Banana, Europe": (
        "Banano · importación en Europa",
        "Frutas",
        "Bananas (Central & South America), major brands, free",
    ),
    "Banana, US": (
        "Banano · importación en EE. UU.",
        "Frutas",
        "Bananas (Central & South America), major brands, US",
    ),
    "Orange": ("Naranja navel · importación europea", "Frutas", "Oranges ("),
    "Beef": ("Carne bovina · referencia de importación", "Carnes", "Beef ("),
    "Chicken": ("Pollo · referencia mayorista", "Carnes", "Chicken ("),
    "Lamb": ("Carne ovina · referencia internacional", "Carnes", "Lamb ("),
    "Shrimps, Mexican": (
        "Camarón · referencia mayorista EE. UU.",
        "Pescados y mariscos",
        "Shrimp ,",
    ),
    "Sugar, EU": ("Azúcar crudo · importación UE", "Azúcar", "Sugar (EU)"),
    "Sugar, US": ("Azúcar · futuros EE. UU.", "Azúcar", "Sugar (U.S.)"),
    "Sugar, world": ("Azúcar crudo · ISA mundial", "Azúcar", "Sugar (World)"),
    "Cotton, A Index": (
        "Algodón · Cotlook A",
        "Fibras y caucho",
        "Cotton (Cotton Outlook",
    ),
    "Rubber, TSR20": ("Caucho · TSR 20", "Fibras y caucho", "Rubber (Asia), TSR 20"),
    "Rubber, RSS3": ("Caucho · RSS3", "Fibras y caucho", "Rubber (Asia), RSS3"),
    "Phosphate rock": ("Roca fosfórica", "Fertilizantes", "Phosphate rock ,"),
    "DAP": ("Fosfato diamónico · DAP", "Fertilizantes", "DAP ("),
    "TSP": ("Superfosfato triple · TSP", "Fertilizantes", "TSP ("),
    "Urea": ("Urea", "Fertilizantes", "Urea,"),
    "Potassium chloride": (
        "Cloruro de potasio",
        "Fertilizantes",
        "Potassium chloride (",
    ),
}


def slug(text):
    text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    )
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


PUBLISHERS = {
    "international-worldbank-index": "World Bank",
    "international-worldbank-monthly": "World Bank",
    "international-usda-miami-flowers": "USDA AMS",
    "international-usda-boston-flowers": "USDA AMS",
    "international-usda-miami-index": "USDA AMS",
    "international-usda-boston-index": "USDA AMS",
}
USDA_MIAMI_ARCHIVE = "https://esmis.nal.usda.gov/publication/import-ornamental-shipping-point-report-miami-fl"
USDA_BOSTON_ARCHIVE = "https://esmis.nal.usda.gov/publication/ornamental-wholesale-market-report-boston-ma"
ROOTS = [
    (USDA_MIAMI_ARCHIVE, "international-usda-miami-index"),
    (USDA_BOSTON_ARCHIVE, "international-usda-boston-index"),
    (WORLD_BANK_HOME, "international-worldbank-index"),
    (USDA_MIAMI, "international-usda-miami-flowers"),
    (USDA_BOSTON, "international-usda-boston-flowers"),
]


def discover(body=None, url=None, kind=None):
    """Return mutable official assets. Optional index bytes make this testable.

    Fetching the index on each discovery notices revised workbook link paths.
    A missing expected link is reported for review rather than silently ignored.
    """
    if body is None:
        return list(ROOTS)
    if kind in {"international-usda-miami-index", "international-usda-boston-index"}:
        soup = BeautifulSoup(body, "html.parser")
        links = []
        report_name = "MH_FV221.PDF" if "miami" in kind else "BH_FV201.PDF"
        for a in soup.select("a[href]"):
            child = urljoin(url, a["href"])
            parsed = urlparse(child)
            if parsed.hostname != "esmis.nal.usda.gov":
                continue
            if parsed.path.upper().endswith("/" + report_name):
                links.append((child, kind.replace("-index", "-flowers")))
            elif parsed.path == urlparse(url).path and re.fullmatch(
                r"page=\d+", parsed.query
            ):
                links.append((child, kind))
        if not links:
            raise ValueError("USDA archive page has no expected releases or pagination")
        return list(dict.fromkeys(links))
    if kind != "international-worldbank-index":
        return []
    url = url or WORLD_BANK_HOME
    soup = BeautifulSoup(body, "html.parser")
    links = [
        urljoin(url, a["href"])
        for a in soup.select("a[href]")
        if urlparse(urljoin(url, a["href"])).hostname == "thedocs.worldbank.org"
        and urlparse(a["href"]).path.endswith("CMO-Historical-Data-Monthly.xlsx")
    ]
    if not links:
        raise ValueError("World Bank index no longer exposes the monthly workbook")
    return list(dict.fromkeys((u, "international-worldbank-monthly") for u in links))


def _number(value, cell):
    if value is None or str(value).strip() in {
        "",
        "...",
        "…",
        "..",
        "-",
        "n/a",
        "N/A",
        "#VALUE!",
        "#N/A",
        "#DIV/0!",
        "#REF!",
    }:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid price in {cell}")
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Unrecognized price or missing marker in {cell}") from None
    if number == 0:
        return None  # Upstream zero placeholders are archived, never published as free goods.
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Nonpositive or nonfinite price in {cell}")
    return number


def parse_world_bank(body, url):
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        if "Monthly Prices" not in book or "Description" not in book:
            raise ValueError("World Bank workbook lacks price or description sheet")
        descriptions = []
        for i, row in enumerate(book["Description"].iter_rows(values_only=True), 1):
            if len(row) > 1 and isinstance(row[1], str):
                sources = next(
                    (v for v in row[2:] if isinstance(v, str) and len(v) > 5), None
                )
                descriptions.append((row[1].strip(), sources, i))
        rows = list(book["Monthly Prices"].iter_rows(values_only=True))
        header = next(
            (
                i
                for i, row in enumerate(rows[:30])
                if "Coffee, Arabica" in row and "Cocoa" in row
            ),
            None,
        )
        if header is None or "nominal US dollars" not in str(rows[:header]):
            raise ValueError("Unrecognized World Bank header or currency")
        selected = {}
        for col, raw_name in enumerate(rows[header]):
            key = re.sub(r"\s*\*+\s*$", "", str(raw_name or "")).strip()
            if key not in WB_SERIES:
                continue
            name, category, prefix = WB_SERIES[key]
            matching = [
                (text, src, row)
                for text, src, row in descriptions
                if text.startswith(prefix)
            ]
            if len(matching) != 1:
                raise ValueError(f"Missing or ambiguous World Bank methodology: {key}")
            raw_unit = str(rows[header + 1][col]).strip()
            if raw_unit not in {"($/kg)", "($/mt)"}:
                raise ValueError(f"Changed World Bank price unit for {key}: {raw_unit}")
            selected[col] = (key, name, category, raw_unit, matching[0])
        if len(selected) != len(WB_SERIES):
            raise ValueError("World Bank agricultural series selection changed")
        found = []
        seen = set()
        for row_no, row in enumerate(rows[header + 2 :], header + 3):
            raw_period = str(row[0] or "").strip()
            if not re.fullmatch(r"\d{4}M\d{2}", raw_period):
                if raw_period and any(isinstance(v, (int, float)) for v in row[1:]):
                    raise ValueError(f"Unrecognized World Bank period at row {row_no}")
                continue
            year, month = int(raw_period[:4]), int(raw_period[-2:])
            day = date(year, month, calendar.monthrange(year, month)[1])
            if day > date.today():
                raise ValueError(
                    "World Bank workbook contains a future monthly observation"
                )
            if day in seen:
                raise ValueError("Duplicate World Bank monthly period")
            seen.add(day)
            for col, (key, name, category, raw_unit, description) in selected.items():
                locator = f"Monthly Prices!{openpyxl.utils.get_column_letter(col + 1)}{row_no}"
                value = _number(row[col], locator)
                if value is None:
                    continue
                method, sources, description_row = description
                found.append(
                    {
                        "product_id": "wb-" + slug(key),
                        "product_name": name,
                        "category": category,
                        "publisher": "World Bank",
                        "series": "international-worldbank-monthly",
                        "basis": "Referencia internacional mensual",
                        "currency": "USD",
                        "unit": "kg" if raw_unit == "($/kg)" else "tonne",
                        "market": "Banco Mundial · " + key,
                        "date": day,
                        "period_start": date(year, month, 1),
                        "price": value,
                        "source_locator": locator,
                        "details": {
                            "frequency": "monthly",
                            "source_product": key,
                            "original_unit": raw_unit,
                            "source_description": method,
                            "underlying_sources": sources,
                            "methodology_locator": f"Description!B{description_row}",
                            "methodology_may_change": True,
                            "price_statistic": "published_monthly_benchmark",
                            "source_url": url,
                        },
                    }
                )
        if not found:
            raise ValueError("No World Bank observations parsed")
        return found
    finally:
        book.close()


def parse(body, url, kind):
    if kind in PUBLISHERS and kind.endswith("-index"):
        return []
    if kind == "international-worldbank-monthly":
        return parse_world_bank(body, url)
    if kind == "international-usda-miami-flowers":
        return parse_miami_flowers(body, url)
    if kind == "international-usda-boston-flowers":
        return parse_boston_flowers(body, url)
    raise ValueError("Unknown international source kind: " + kind)


FLOWER_NAMES = {
    "ALSTROEMERIA": "Alstroemeria",
    "ANTIRRHINUM (SNAPDRAGON)": "Boca de dragón",
    "ASTER": "Áster",
    "CARNATIONS": "Clavel",
    "CARNATIONS, MINIATURE": "Miniclavel",
    "CHRYSANTHEMUM": "Crisantemo",
    "GYPSOPHILA": "Gypsophila",
    "HYDRANGEA": "Hortensia",
    "LIATRIS": "Liatris",
    "LIMONIUM": "Limonium",
    "ROSE, HYBRID TEA": "Rosa híbrida de té",
    "ROSE, SPRAY TYPE": "Rosa spray",
    "SOLIDAGO": "Solidago",
    "ZANTEDESCHIA (CALLA)": "Cala",
}
PRICE = re.compile(
    r"(?<![\d.])(?P<low>\d*\.\d{1,2})(?:\s*-\s*(?P<high>\d*\.\d{1,2}))?(?!\d|\.\d)"
)
UNIT = re.compile(r"(?:on stem )?per (?:stem|bunch|bloom|box)|bunched \d+s", re.I)


def _pdf_parts(body, report, columns):
    import pdfplumber

    result, report_day = [], None
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            header = page.crop((0, 0, page.width, 110)).extract_text() or ""
            if report not in header:
                raise ValueError("Unexpected USDA report or PDF layout")
            match = re.search(r"([A-Z][a-z]+ \d{1,2},\s*\d{4})", header)
            if not match:
                raise ValueError("USDA report date missing")
            d = datetime.strptime(re.sub(r",\s*", ", ", match[1]), "%B %d, %Y").date()
            if d > date.today() or (report_day and d != report_day):
                raise ValueError("Inconsistent USDA observation date")
            report_day = d
            words = page.extract_words()
            footer = min(
                (
                    w["top"]
                    for w in words
                    if w["text"] in {"Source:", "Phone"} and w["top"] > 600
                ),
                default=page.height - 60,
            )
            for col in range(columns):
                section = (
                    page.crop(
                        (
                            col * page.width / columns,
                            106,
                            (col + 1) * page.width / columns,
                            footer - 1,
                        )
                    ).extract_text()
                    or ""
                )
                result.extend(
                    (line.strip(), page_no, col + 1)
                    for line in section.splitlines()
                    if line.strip() and not re.match(r"^Page \d+\b", line.strip())
                )
    return report_day, result


def _flower_row(
    name, variant, unit, low, high, day, market, locator, original, url, origin, **extra
):
    if not unit or not origin or not name or low <= 0 or high < low:
        raise ValueError("USDA flower quote lacks a valid identity, range or unit")
    display = FLOWER_NAMES.get(name, name.title())
    if variant:
        display += " · " + variant
    return {
        "product_id": "usda-flower-"
        + slug(name + "-" + variant + "-" + unit + "-" + origin),
        "product_name": display,
        "category": "Flores",
        "publisher": "USDA AMS",
        "series": "international-usda-miami-flowers"
        if market == "Miami"
        else "international-usda-boston-flowers",
        "basis": "EE. UU. · ventas FOB/entrega, base punto de embarque"
        if market == "Miami"
        else "EE. UU. · ventas mayoristas en terminal",
        "currency": "USD",
        "unit": unit,
        "market": "Miami · importación de flores"
        if market == "Miami"
        else "Boston · terminal de flores",
        "date": day,
        "price": (low + high) / 2,
        "min": low,
        "max": high,
        "source_page": int(re.search(r"PDF page (\d+)", locator)[1]),
        "identity_dimensions": {
            "flower": name,
            "variant": variant,
            "package": unit,
            "origin": origin,
        },
        "source_locator": locator,
        "details": {
            "source_product": name,
            "variety": variant,
            "origin": origin,
            "frequency": "weekly",
            "price_statistic": "range_midpoint",
            "original_quote": original,
            "source_url": url,
            **extra,
        },
    }


def _legacy_miami_narrative_ends(lines):
    """Locate explicit older commodity narratives without the spot-sales note.

    A narrative consists of uppercase SUPPLY/DEMAND/MARKET sentences, including
    wrapped continuations. A completed sentence followed by a variety/package
    starts the data. Numeric prices inside an unfinished narrative still fail.
    Newer blocks keep their existing, more specific spot-sales boundary.
    """
    starts = [i for i, (line, _, _) in enumerate(lines) if line.startswith("---")]
    ends = {}
    for start, stop in zip(starts, starts[1:] + [len(lines)]):
        block = lines[start:stop]
        text = " ".join(line for line, _, _ in block)
        if re.search(r"Prices represent few spot market sales\.", text, re.I):
            continue
        header = block[0][0]
        if ":" not in header:
            raise ValueError("Wrapped USDA commodity title needs review")
        narrative = header.split(":", 1)[1].strip()
        if not narrative:
            # Some older unquoted commodities print only the title/colon,
            # followed by an explicit package and no-market notice. Normal row
            # validation still requires a package before any numeric quote.
            ends[start + 1] = start + 1
            continue
        if not re.match(r"^(?:SUPPLY|DEMAND|MARKET)\b", narrative):
            raise ValueError("Unrecognized USDA historical narrative")
        last = start
        for offset, (line, _, _) in enumerate(block[1:], 1):
            if narrative.endswith(".") and not re.match(
                r"^(?:SUPPLY|DEMAND|MARKET)\b", line
            ):
                break
            narrative += " " + line
            last = start + offset
        if (
            not narrative.endswith(".")
            or narrative != narrative.upper()
            or PRICE.search(narrative)
        ):
            raise ValueError("Unrecognized USDA historical narrative boundary")
        ends[start + 1] = last + 1
    return ends


def parse_miami_flowers(body, url=USDA_MIAMI):
    """Parse the native two-column layout, retaining both full and mostly ranges.

    Miami quotes identify the entry point, not a country on each line. Never
    label these as exclusively Colombian. Inline alternative colors preserve
    their literal printed parent context instead of inventing a classification.
    """
    day, lines = _pdf_parts(body, "MH_FV221", 2)
    legacy_ends = _legacy_miami_narrative_ends(lines)
    found, name, variant, grade, unit = [], None, "", "", None
    in_intro = False
    intro_end, no_quote_continuation = None, False
    last = None
    continued_rows = set()
    for index, (line, page, column) in enumerate(lines, 1):
        if index in continued_rows:
            continue
        if line.startswith("---"):
            name = line[3:].split(":", 1)[0]
            if ":" not in line:
                raise ValueError("Wrapped USDA commodity title needs review")
            variant, grade, unit, last = "", "", None, None
            in_intro = True
            intro_end = legacy_ends.get(index)
            no_quote_continuation = False
        if not name:
            continue
        if in_intro:
            # New reports use the spot-sales sentence; older ones end their
            # explicit uppercase market narrative before variety/package rows.
            if PRICE.search(line):
                raise ValueError(
                    "USDA numeric quote before recognized narrative boundary"
                )
            if (
                index == intro_end
                or line.endswith("spot market sales.")
                or line
                in {
                    "sales.",
                    "represent few spot market sales.",
                }
            ):
                in_intro = False
            continue
        original_line, locator_rows = line, str(index)
        if re.search(r"(?<![\d.])\d*\.\d{1,2}-\s*$", line):
            # USDA sometimes wraps a literal price range after its hyphen.
            # Join only an adjacent numeric continuation in the same column;
            # retain both exact source lines and their original row numbers.
            if index >= len(lines):
                raise ValueError("Unfinished USDA printed price range")
            following, next_page, next_column = lines[index]
            if (page, column) != (next_page, next_column) or not re.match(
                r"^\d*\.\d{1,2}(?!\d|\.\d)", following
            ):
                raise ValueError("Unrecognized USDA price range continuation")
            line += following
            original_line += "\n" + following
            locator_rows = f"{index}-{index + 1}"
            continued_rows.add(index + 1)
        unit_match = UNIT.search(line)
        if unit_match:
            if unit_match.start() != 0:
                raise ValueError("Unexpected USDA package placement")
            unit = unit_match[0].lower()
            line_body = line[unit_match.end() :].strip()
        else:
            line_body = line
        if no_quote_continuation:
            if not re.fullmatch(r"(?:(?:to )?establish a )?market\.?", line_body, re.I):
                raise ValueError("Unrecognized USDA no-quote notice continuation")
            no_quote_continuation = False
            continue
        if re.search(r"\d\.\d+\s*-\s*\.\d+\.", line_body):
            raise ValueError("Malformed USDA printed price range")
        matches = list(PRICE.finditer(line_body))
        if not matches:
            if (
                "supplies in" in line_body.lower()
                or "too few hands" in line_body
                or "to establish a market" in line_body
            ):
                last = None
                no_quote_continuation = not bool(
                    re.search(r"\bmarket\.?$", line_body, re.I)
                )
                continue
            if unit_match or line_body in {
                "lower",
                "higher",
                "and lower",
                "and higher",
            }:
                continue
            if line_body in {"Select", "Super Select", "Fancy"}:
                grade = line_body
            elif not re.search(r"\d", line_body):
                variant, grade = line_body, ""
            elif not re.fullmatch(r"\d+ cm", line_body):
                raise ValueError("Unrecognized USDA numeric row: " + line_body)
            last = None
            continue
        for j, match in enumerate(matches):
            prefix = line_body[
                (matches[j - 1].end() if j else 0) : match.start()
            ].strip(" ;")
            if re.search(r"\d*\.\d", prefix):
                raise ValueError("Unrecognized USDA numeric quote qualifier")
            lo, hi = float(match["low"]), float(match["high"] or match["low"])
            if re.search(r"\bmostly\s*$", prefix, re.I):
                if last is None or lo < last["min"] or hi > last["max"] or hi < lo:
                    raise ValueError("USDA mostly range is outside full quote")
                last["details"].update(mostly_min=lo, mostly_max=hi)
                continue
            prefix = re.sub(
                r"^(?:occasional|few) (?:higher|lower)(?: and (?:higher|lower))?\s*;?\s*",
                "",
                prefix,
            )
            if not j and index > 1:
                continued = re.search(
                    r"\b(?:occasional|few) (higher|lower) and$", lines[index - 2][0]
                )
                if continued:
                    opposite = "lower" if continued[1] == "higher" else "higher"
                    prefix = re.sub(r"^" + opposite + r"\b\s*", "", prefix)
            quote_variant = " / ".join(v for v in (variant, grade) if v)
            if prefix:
                if re.fullmatch(r"\d+ cm", prefix):
                    quote_variant += (" / " if quote_variant else "") + prefix
                else:
                    # The PDF prints e.g. "Assorted Colors ... ; Yellow ...".
                    # Retain that exact qualifier relationship for review/UI.
                    quote_variant += ("; " if quote_variant else "") + prefix
            last = _flower_row(
                name,
                quote_variant,
                unit,
                lo,
                hi,
                day,
                "Miami",
                f"PDF page {page}, col {column}, text row {locator_rows}, quote {j + 1}",
                original_line,
                url,
                "Imports through Miami; country not specified per quote",
            )
            found.append(last)
        if re.search(r"\d*\.\d", line_body[matches[-1].end() :]):
            raise ValueError("Unrecognized USDA trailing numeric quote")
    if not found:
        raise ValueError("No Miami flower prices parsed")
    identities = [(r["product_id"], r["date"]) for r in found]
    if len(identities) != len(set(identities)):
        raise ValueError("Ambiguous duplicate USDA Miami flower identity")
    return found


# Only countries/states actually represented in the validated Boston source
# family are recognized. Unexpected origin context fails instead of silently
# assigning a new price to a previous country.
ORIGINS = "THAILAND|SOUTH AFRICA|COLOMBIA|ECUADOR|COSTA RICA|GUATEMALA|CANADA|CHILE|NETHERLANDS|MEXICO|ISRAEL|KENYA|ETHIOPIA|PERU|CALIFORNIA|FLORIDA|NEW JERSEY|NEW ENGLAND|MASSACHUSETTS|NEW YORK|OREGON|WASHINGTON|PENNSYLVANIA|VERMONT|MAINE|CONNECTICUT|HAWAII"
ORIGIN = re.compile(r"\b(?:" + ORIGINS + r")\b")


def parse_boston_flowers(body, url=USDA_BOSTON):
    day, lines = _pdf_parts(body, "BH_FV201", 1)
    blocks = []
    for line, page, col in lines:
        if line.startswith("---"):
            blocks.append([line, page])
        elif blocks:
            blocks[-1][0] += " " + line
    found = []
    for block, page in blocks:
        title, text = block[3:].split(":", 1)
        first_unit = UNIT.search(text)
        if not first_unit:
            if PRICE.search(text):
                raise ValueError("Boston flower price has no package")
            continue
        text = text[first_unit.start() :]
        unit, origin, variant, last = None, None, "", None
        matches = list(PRICE.finditer(text))
        for j, match in enumerate(matches):
            prefix = text[(matches[j - 1].end() if j else 0) : match.start()].strip()
            lo, hi = float(match["low"]), float(match["high"] or match["low"])
            if re.search(r"\bmostly\s*$", prefix, re.I):
                if last is None or not (last["min"] <= lo <= hi <= last["max"]):
                    raise ValueError("Boston mostly range is outside the full range")
                last["details"].update(mostly_min=lo, mostly_max=hi)
                continue
            prefix = re.sub(r"^(?:(?:occasional|few) (?:higher|lower)\s*)+", "", prefix)
            units = list(UNIT.finditer(prefix))
            if units:
                unit = units[-1][0].lower()
                prefix = prefix[units[-1].end() :].strip()
            origins = list(ORIGIN.finditer(prefix))
            if origins:
                if len(origins) > 1:
                    raise ValueError("Ambiguous Boston flower origin")
                origin = origins[0][0]
                prefix = prefix[origins[0].end() :].strip()
                variant = ""
            if prefix:
                variant = prefix
            if not origin:
                raise ValueError("Unrecognized Boston flower origin: " + prefix)
            last = _flower_row(
                title,
                variant,
                unit,
                lo,
                hi,
                day,
                "Boston",
                f"PDF page {page}, commodity {title}, quote {j + 1}",
                block,
                url,
                origin,
            )
            found.append(last)
    if not found:
        raise ValueError("No Boston flower prices parsed")
    keys = [(r["product_id"], r["market"], r["date"]) for r in found]
    if len(keys) != len(set(keys)):
        raise ValueError("Ambiguous duplicate Boston flower identity")
    return found
