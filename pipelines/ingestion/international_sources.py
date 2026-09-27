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
VERSION = "official-international-v6"

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
        report_name = "MH_FV221" if "miami" in kind else "BH_FV201"
        for a in soup.select("a[href]"):
            child = urljoin(url, a["href"])
            parsed = urlparse(child)
            if parsed.hostname != "esmis.nal.usda.gov":
                continue
            child = parsed._replace(fragment="").geturl()
            if parsed.path.upper().endswith(
                ("/" + report_name + ".PDF", "/" + report_name + ".TXT")
            ):
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
        if urlparse(url).path.lower().endswith(".txt"):
            return parse_text_flowers(body, url, "Miami")
        return parse_miami_flowers(body, url)
    if kind == "international-usda-boston-flowers":
        if urlparse(url).path.lower().endswith(".txt"):
            return parse_text_flowers(body, url, "Boston")
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
UNIT = re.compile(
    r"per carton(?: \d+ bunches of \d+ stems)?|"
    r"(?:on stem )?per (?:stem|bunch|bloom|box)|bunched \d+s",
    re.I,
)


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
        "source_page": int(re.search(r"PDF page (\d+)", locator)[1])
        if locator.startswith("PDF page")
        else None,
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
        market_narrative = re.sub(
            r"\bFIRST REPORT\b[^.]*\.|\bno offerings\.", "", narrative
        )
        if (
            not narrative.endswith(".")
            or market_narrative != market_narrative.upper()
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
        # A printed color or "mostly" qualifier can wrap independently of its
        # price. Keep that qualifier with the next physical line, or a mostly
        # range becomes a second quote for the parent color. Join only within
        # this column and retain every original line in the source locator.
        end_index = index
        while PRICE.search(line):
            tail = list(PRICE.finditer(line))[-1]
            suffix = line[tail.end() :].strip(" ,;:.")
            needs_continuation = bool(suffix) and not re.fullmatch(
                r"(?:(?:occasional|few) (?:higher|lower)(?: and (?:higher|lower))?|"
                r"(?:and )?(?:higher|lower)|FIRST REPORT)",
                suffix,
                re.I,
            )
            if not needs_continuation or suffix.endswith("-"):
                break
            if re.fullmatch(r"(?:occasional|few) (?:higher|lower) and", suffix, re.I):
                break
            if end_index >= len(lines):
                raise ValueError("Unfinished USDA quote qualifier")
            following, next_page, next_column = lines[end_index]
            if not PRICE.search(following) and re.search(
                r"\bsupplies (?:in too few hands|insufficient and in too few hands) "
                r"to establish a market\.?$",
                suffix + " " + following,
                re.I,
            ):
                break
            if (
                (page, column) != (next_page, next_column)
                or following.startswith("---")
                or UNIT.match(following)
                or not PRICE.search(following)
            ):
                # Existing standalone higher/lower wrapping is handled below.
                if re.fullmatch(
                    r"(?:occasional|few) (?:higher|lower) and", suffix, re.I
                ):
                    break
                # A complete no-market notice contains no quote to continue.
                if re.search(
                    r"(?:establish a market|insufficient to quote)\.?$", suffix, re.I
                ):
                    break
                raise ValueError("Unrecognized USDA quote qualifier continuation")
            line += " " + following
            original_line += "\n" + following
            end_index += 1
            continued_rows.add(end_index)
            locator_rows = f"{index}-{end_index}"
        if re.search(r"(?<![\d.])\d*\.\d{1,2}-\s*$", line):
            # USDA sometimes wraps a literal price range after its hyphen.
            # Join only an adjacent numeric continuation in the same column;
            # retain both exact source lines and their original row numbers.
            if end_index >= len(lines):
                raise ValueError("Unfinished USDA printed price range")
            following, next_page, next_column = lines[end_index]
            if (page, column) != (next_page, next_column) or not re.match(
                r"^\d*\.\d{1,2}(?!\d|\.\d)", following
            ):
                raise ValueError("Unrecognized USDA price range continuation")
            line += following
            original_line += "\n" + following
            end_index += 1
            locator_rows = f"{index}-{end_index}"
            continued_rows.add(end_index)
        unit_match = UNIT.search(line)
        if unit_match:
            if unit_match.start() != 0:
                raise ValueError("Unexpected USDA package placement")
            unit = unit_match[0].lower()
            line_body = line[unit_match.end() :].strip()
        else:
            line_body = line
        if no_quote_continuation:
            if not (
                re.fullmatch(r"(?:(?:to )?establish a )?market\.?", line_body, re.I)
                or (
                    line_body == "REPORT."
                    and re.search(r"establish a market\. LAST$", lines[index - 2][0])
                )
            ):
                raise ValueError("Unrecognized USDA no-quote notice continuation")
            no_quote_continuation = False
            continue
        if re.search(r"\d\.\d+\s*-\s*\.\d+\.", line_body):
            raise ValueError("Malformed USDA printed price range")
        matches = list(PRICE.finditer(line_body))
        if not matches:
            if re.search(
                r"(?:supplies insufficient to quote|no offerings)\.?$", line_body, re.I
            ):
                last = None
                continue
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
            if line_body in {"Select", "Super Select", "Fancy", "Standard"}:
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
            ].strip(" ,;:.")
            # An unquoted inline color must not become part of the next
            # quoted color's identity. Its literal notice remains in evidence.
            prefix = re.sub(
                r"^.*?\bsupplies (?:in too few hands|insufficient and in too few hands) "
                r"to establish a market[;. ]+",
                "",
                prefix,
                flags=re.I,
            )
            if re.search(r"\d*\.\d", prefix):
                raise ValueError("Unrecognized USDA numeric quote qualifier")
            lo, hi = float(match["low"]), float(match["high"] or match["low"])
            quote_qualifier = None
            if re.fullmatch(r"(?:few|occasional)(?: (?:higher|lower))?", prefix, re.I):
                if lo <= 0 or hi < lo or (j and last is None):
                    raise ValueError("USDA exceptional price lacks its main quote")
                if j:
                    last["details"].setdefault("exceptional_prices", []).append(
                        {
                            "qualifier": prefix,
                            "min": lo,
                            "max": hi,
                            "source_locator": f"PDF page {page}, col {column}, text row {locator_rows}, quote {j + 1}",
                            "original_quote": original_line,
                        }
                    )
                    continue
                # "per bunch few 2.62" is the sole printed market quote;
                # retain its qualifier without inventing a flower variety.
                quote_qualifier, prefix = prefix, ""
            if re.search(r"\bmostly\s*$", prefix, re.I):
                if last is None or lo < last["min"] or hi > last["max"] or hi < lo:
                    raise ValueError("USDA mostly range is outside full quote")
                _record_mostly(
                    last,
                    lo,
                    hi,
                    f"PDF page {page}, col {column}, text row {locator_rows}, quote {j + 1}",
                )
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
            if quote_qualifier:
                last["details"]["quote_qualifier"] = quote_qualifier
        if re.search(r"\d*\.\d", line_body[matches[-1].end() :]):
            raise ValueError("Unrecognized USDA trailing numeric quote")
    if not found:
        raise ValueError("No Miami flower prices parsed")
    identities = {}
    for row in found:
        key = (row["product_id"], row["date"])
        # Some original bulletins repeat a whole commodity block. Preserve
        # every locator, but accept repeats only when the literal quotation and
        # all its numeric values agree; never merge competing source prices.
        value = (
            row["min"],
            row["max"],
            row["details"].get("mostly_min"),
            row["details"].get("mostly_max"),
            tuple(
                (p["qualifier"], p["min"], p["max"])
                for p in row["details"].get("exceptional_prices", [])
            ),
            row["details"]["original_quote"],
        )
        if key in identities and identities[key] != value:
            raise ValueError("Ambiguous duplicate USDA Miami flower identity")
        identities[key] = value
    return found


# Only countries/states actually represented in the validated Boston source
# family are recognized. Unexpected origin context fails instead of silently
# assigning a new price to a previous country.
ORIGINS = "THAILAND|SOUTH AFRICA|COLOMBIA|ECUADOR|COSTA RICA|GUATEMALA|CANADA|CHILE|NETHERLANDS|MEXICO|ISRAEL|KENYA|ETHIOPIA|PERU|ITALY|FRANCE|CALIFORNIA|FLORIDA|NEW JERSEY|NEW ENGLAND|MASSACHUSETTS|NEW YORK|OREGON|WASHINGTON|PENNSYLVANIA|VERMONT|MAINE|CONNECTICUT|HAWAII|TEXAS"
ORIGIN = re.compile(
    r"\b(?:NEW ENGLAND MASSACHUSETTS AND NEARBY PRODUCING AREAS|" + ORIGINS + r")\b"
)


def _record_mostly(row, low, high, locator):
    """Keep a contradictory printed qualifier in review without losing siblings."""
    details = row["details"]
    incoming = {"min": low, "max": high, "source_locator": locator}
    if "conflicting_mostly_quotes" in details:
        details["conflicting_mostly_quotes"].append(incoming)
    elif "mostly_min" in details and (details["mostly_min"], details["mostly_max"]) != (
        low,
        high,
    ):
        details["conflicting_mostly_quotes"] = [
            {
                "min": details.pop("mostly_min"),
                "max": details.pop("mostly_max"),
                "source_locator": row["source_locator"],
            },
            incoming,
        ]
    else:
        details.update(mostly_min=low, mostly_max=high)
        return
    details["quality_issue"] = (
        "Conflicting repeated USDA mostly qualifiers for the same printed quote"
    )
    row["price"] = None


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
        if PRICE.search(text[: first_unit.start()]):
            raise ValueError("Boston flower price appears before its package")
        text = text[first_unit.start() :]
        unit, origin, variant, last = None, None, "", None
        matches = list(PRICE.finditer(text))
        for j, match in enumerate(matches):
            prefix = text[(matches[j - 1].end() if j else 0) : match.start()].strip()
            lo, hi = float(match["low"]), float(match["high"] or match["low"])
            if re.search(r"\bmostly\s*$", prefix, re.I):
                if last is None or not (last["min"] <= lo <= hi <= last["max"]):
                    raise ValueError("Boston mostly range is outside the full range")
                _record_mostly(
                    last, lo, hi, f"PDF page {page}, commodity {title}, quote {j + 1}"
                )
                continue
            prefix = re.sub(r"^(?:(?:occasional|few) (?:higher|lower)\s*)+", "", prefix)
            units = list(UNIT.finditer(prefix))
            if units:
                unit = units[-1][0].lower()
                prefix = prefix[units[-1].end() :].strip()
            origins = list(ORIGIN.finditer(prefix))
            if origins:
                if len({m[0] for m in origins}) > 1:
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


# The old text files print origin codes rather than country names. Preserve the
# exact code; CA/CD/CB must never be guessed from ISO country abbreviations.
TEXT_ORIGIN = re.compile(
    r"^(NENG|CB|CD|CA|CL|CR|EC|ET|FL|GU|HI|IS|IT|KE|MX|NJ|NL|NZ|PE|SF|TH|TL|VN)\b"
)
TEXT_UNIT = re.compile(UNIT.pattern + r"|per spray", re.I)
TEXT_SIZE = re.compile(
    r"(?:\d+\s*cm|extra long|exlong|long|short|medium|med|large|lge|small|sml)$", re.I
)
TEXT_GRADE = re.compile(
    r"^(?:Sup Sel|Sel|Fcy|Std|Super Select|Select|Fancy|Standard)\b", re.I
)
TEXT_COLORS = {
    "purple",
    "white",
    "blue",
    "pink",
    "red",
    "yellow",
    "green",
    "assorted",
    "assorted colors",
}


def _text_review(row, reason):
    row["price"] = None
    previous = row["details"].get("quality_issue")
    row["details"]["quality_issue"] = previous + "; " + reason if previous else reason


def _text_blocks(body, market):
    if len(body) > 5_000_000 or b"\x00" in body:
        raise ValueError("USDA native text report is not a bounded text document")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    lines = text.splitlines()
    # Archived USDA TXT files can begin with empty CRLF lines. Check the
    # first actual heading without removing lines from source locators.
    first_content = next((line.strip() for line in lines if line.strip()), "")
    heading = re.search(
        r"^"
        + market.upper()
        + r" Ornamental (?:Shipping Point|Terminal) Prices as of (\d{1,2}-[A-Z]{3}-\d{4})\s*$",
        first_content,
    )
    if (
        not heading
        or "Specialty Crops Market News" not in text[:1500]
        or "USDA" not in text[:1500]
    ):
        raise ValueError("Unexpected USDA native text report header")
    day = datetime.strptime(heading[1], "%d-%b-%Y").date()
    if day > date.today():
        raise ValueError("USDA native text report is in the future")
    starts = [i for i, line in enumerate(lines) if line.startswith("---")]
    if not starts:
        raise ValueError("USDA native text report contains no commodity blocks")
    return (
        day,
        text,
        [
            (
                " ".join(line.strip() for line in lines[start:stop] if line.strip()),
                start + 1,
                stop,
            )
            for start, stop in zip(starts, starts[1:] + [len(lines)])
        ],
    )


def parse_text_flowers(body, url, market):
    """Publish explicit native TXT identities; isolate uncertain continuations.

    Unlike PDFs, text reports serialize type/grade/size hierarchies inline. We
    only inherit an unambiguous trailing size or a flat color. Other implicit
    parent relationships remain review records with every literal price intact.
    """
    if market not in {"Miami", "Boston"}:
        raise ValueError("Unsupported USDA text market")
    day, report, blocks = _text_blocks(body, market)
    found = []
    for block, start, stop in blocks:
        if ":" not in block:
            raise ValueError("USDA native text commodity lacks its heading boundary")
        title, text = block[3:].split(":", 1)
        commodity_origin = re.search(r"\bMostly ([^.]+)\.", text)
        default_origin = "Imports through Miami; " + (
            commodity_origin[0]
            if commodity_origin
            else "country not specified per quote"
        )
        unit, origin, variant, last = None, None, "", None
        matches = list(PRICE.finditer(text))
        for index, match in enumerate(matches):
            prefix = text[
                (matches[index - 1].end() if index else 0) : match.start()
            ].strip(" ,;.")
            low, high = float(match["low"]), float(match["high"] or match["low"])
            locator = f"Text lines {start}-{stop}, commodity {title}, quote {index + 1}"
            if re.search(r"\bmostly\s*$", prefix, re.I) and last is not None:
                if not (last["min"] <= low <= high <= last["max"]):
                    last["details"].setdefault("out_of_range_mostly_quotes", []).append(
                        {"min": low, "max": high, "source_locator": locator}
                    )
                    _text_review(
                        last,
                        "Printed mostly range is outside the full native text quote",
                    )
                else:
                    _record_mostly(last, low, high, locator)
                continue
            if (
                re.fullmatch(
                    r"(?:few|occas|occasional)(?: (?:higher|lower))?", prefix, re.I
                )
                and last is not None
            ):
                last["details"].setdefault("exceptional_prices", []).append(
                    {
                        "qualifier": prefix,
                        "min": low,
                        "max": high,
                        "source_locator": locator,
                    }
                )
                continue
            prefix = re.sub(
                r"^(?:(?:few|occas|occasional) (?:higher|lower)\s*[,;]?\s*)+",
                "",
                prefix,
                flags=re.I,
            )
            units = list(TEXT_UNIT.finditer(prefix))
            reset_unit = bool(units)
            if reset_unit:
                unit = units[-1][0].lower()
                prefix = prefix[units[-1].end() :].strip(" ,;.")
            issue = None
            if not unit:
                issue = "Price precedes its first explicit package in native text"
            explicit_origin = False
            if market == "Boston":
                code = TEXT_ORIGIN.match(prefix)
                if code:
                    origin = "USDA origin code " + code[1]
                    prefix = prefix[code.end() :].strip(" ,;.")
                    explicit_origin = True
                elif reset_unit:
                    # The next explicit package can omit an origin only when
                    # the previous origin remains in the same commodity block.
                    issue = issue or (
                        None if origin else "Native text origin code is not recognized"
                    )
            else:
                country = re.match(
                    r"^(?:Ecuador|Colombia|Costa Rica|Mexico|Guatemala)\b", prefix, re.I
                )
                if country:
                    origin = country[0]
                    prefix = prefix[country.end() :].strip(" ,;.")
                    explicit_origin = True
                elif last is not None and last["details"].get("inline_origin"):
                    issue = (
                        issue
                        or "Origin after an inline country comparison is not explicit"
                    )
                    origin = default_origin
                else:
                    origin = default_origin
            if not origin:
                issue = issue or "Native text origin is not explicit"
            qualifier = None
            qualified = re.search(r"\b(few|occas|occasional)\s*$", prefix, re.I)
            if qualified:
                qualifier = qualified[1]
                prefix = prefix[: qualified.start()].strip(" ,;.")
            previous_variant = variant
            if (
                reset_unit
                or explicit_origin
                or last is None
                or TEXT_GRADE.match(prefix)
            ):
                variant = prefix or (
                    previous_variant if explicit_origin and not reset_unit else ""
                )
            elif TEXT_SIZE.fullmatch(prefix) and previous_variant:
                variant = TEXT_SIZE.sub("", previous_variant).strip() + " " + prefix
                variant = variant.strip()
                if last["details"].get("quality_issue"):
                    issue = (
                        issue
                        or "Size continuation inherits an unresolved native text identity"
                    )
            elif (
                prefix.lower() in TEXT_COLORS
                and previous_variant.lower() in TEXT_COLORS
            ):
                variant = prefix
            else:
                variant = prefix
                issue = (
                    issue or "Implicit native text variety/grade parent requires review"
                )
            # A no-market notice may precede the next actual price. Its implied
            # scope is not safe to inherit as a product variant.
            if re.search(
                r"insufficient|no offerings|too few hands|to quote", prefix, re.I
            ):
                issue = (
                    issue or "Unquoted variant scope crosses the next native text price"
                )
            row = _flower_row(
                title,
                variant,
                unit or "unspecified package",
                1,
                1,
                day,
                market,
                locator,
                block,
                url,
                origin or "unspecified origin",
            )
            row.update(price=(low + high) / 2, min=low, max=high)
            row["details"].update(
                native_format="TXT",
                literal_prefix=prefix,
                previous_variant=previous_variant,
                inline_origin=explicit_origin and market == "Miami",
                line_start=start,
                line_end=stop,
            )
            if market == "Miami":
                row["basis"] = (
                    "EE. UU. · FOB sur de Florida; derechos y empaque incluidos"
                    if re.search(r"SALES F\.O\.B\. SOUTH\s+FLORIDA", report)
                    and "PACKING CHARGES INCLUDED" in report
                    else "EE. UU. · importación en Miami; base del informe original"
                )
                row["details"]["commodity_origin_note"] = (
                    commodity_origin[0] if commodity_origin else None
                )
            else:
                row["details"]["origin_code_note"] = (
                    "Original USDA code retained without an inferred country mapping"
                )
            if qualifier:
                row["details"]["quote_qualifier"] = qualifier
            if low <= 0 or high < low:
                issue = issue or "Invalid literal native text price range"
            if issue:
                _text_review(row, issue)
            found.append(row)
            last = row
    if not found:
        raise ValueError("No native USDA flower prices found")
    identities = {}
    for row in found:
        key = (row["product_id"], row["unit"], row["basis"], row["date"])
        if key in identities:
            prior = identities[key]
            if (prior["min"], prior["max"]) != (row["min"], row["max"]):
                _text_review(prior, "Conflicting duplicate native text quote identity")
                _text_review(row, "Conflicting duplicate native text quote identity")
        else:
            identities[key] = row
    return found
