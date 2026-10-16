"""Process every PDF independently; keep text/tables and exact page provenance."""

import io
import re
import time
import unicodedata
from hashlib import sha256

import pdfplumber
from psycopg.types.json import Jsonb

VERSION = "pdf-text-tables-v1"


def check_run_budget():
    from .worker import RUN_DEADLINE
    from .resumable_inputs import WorkDeferred
    deadline = RUN_DEADLINE.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkDeferred("PDF page checkpoint retained; extraction will resume within the next run budget")
INPUT_PDF_VERSION = "inputs-pdf-v14"
GENERIC_DEPARTMENT_FOLD_VERSION = "inputs-pdf-v17"


def _unique_known_input_department(label):
    """A whole validated department after case/accent fold, never a guess."""
    from .special_prices import DEPARTMENTS

    def folded(text):
        return "".join(
            char for char in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(char)
        ).casefold()

    canonical = {}
    for name in DEPARTMENTS:
        key = folded(name)
        if key in canonical and canonical[key] != name:
            raise ValueError("Validated input departments collide after case/accent fold")
        canonical[key] = name
    return canonical.get(folded(label))


def _input_department_is_known(label, resolver=None):
    """Always run an active resolver, including exact spellings, to catch collisions."""
    if resolver is not None:
        return resolver(label) is not None
    from .special_prices import DEPARTMENTS

    return label in DEPARTMENTS
MIXED_FEB2018_INPUT_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Bol_Insumos_feb_2018.pdf"
)
MIXED_FEB2018_INPUT_SHA = (
    "54cb32e0d9f7a5f02468fa5efb56acac8618897e4c8210d5d39d019dba897de5"
)
MIXED_FEB2018_REVIEW_NOTE = (
    "Published 10,758 verified February 2018 rows from pages 1-140; "
    "pages 141-150 print 2017 (febrero) and remain in page-level review"
)

# A price mention elsewhere on a page is not evidence that a city matrix is
# monetary: modern monthly bulletins contain almost identical percentage grids.
PRICE_GRID_VERSIONS = {False: "daily-pdf-v6", True: "monthly-pdf-v5"}
_MONEY_KG = re.compile(
    r"precio(?:s)?\s*(?:\(\s*)?(?:\$|cop|pesos)\s*(?:/|por)\s*(?:kg|kilogramo(?:s)?)",
    re.IGNORECASE,
)


def legacy_pdf_price_needs_review(series, details):
    """Pure predicate for append-only quarantine; never changes original rows."""
    return series == "dane-monthly-bulletin" and (
        not isinstance(details, dict)
        or details.get("parser_version") != PRICE_GRID_VERSIONS[True]
    )


def price_grid_header(table, market_row):
    """Require currency/unit proof within this table's own header cells."""
    header = " ".join(
        " ".join(str(value or "").split())
        for row in table[: market_row + 1]
        for value in row
    )
    return header if _MONEY_KG.search(header) else None


def daily_price_variation(table, market_row, row, col):
    """Read only the literal Var% beside this headed daily monetary cell."""
    from .worker import clean

    if market_row + 1 >= len(table):
        return None, {}
    subheaders = table[market_row + 1]
    if col + 1 >= len(subheaders) or col + 1 >= len(row):
        return None, {}
    if clean(subheaders[col]).lower() != "precio" or not re.fullmatch(
        r"var(?:iaci[oó]n)?\s*%", clean(subheaders[col + 1]).lower()
    ):
        return None, {}
    if col + 1 < len(table[market_row]) and clean(table[market_row][col + 1]):
        return None, {}
    literal = clean(row[col + 1])
    details = {
        "variation_basis": "printed-daily-var-percent",
        "change_percent_literal": literal,
    }
    if literal.lower() in {"", "-", "n.d.", "n.d", "nd"}:
        return None, details
    if not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?\s*%?", literal):
        details["change_percent_review"] = "Unrecognized printed daily Var% cell"
        return None, details
    return float(literal.rstrip("%").strip().replace(",", ".")), details


def price_grid_evidence(page, table, table_no, market_row, day, monthly):
    """Verify unit and printed reference period before accepting numeric cells."""
    from .worker import MONTH_NUM, SourceDateMismatch, date_from_text

    header = price_grid_header(table, market_row)
    if header is None:
        return None
    # Native geometry gives the local caption, never an unrelated page title.
    # OCR must include the literal reference period in the table itself.
    caption = ""
    if hasattr(page, "find_tables"):
        native = page.find_tables()
        if table_no <= len(native):
            bounds = native[table_no - 1].bbox
            # Some older DANE slides contain table geometry beyond the PDF
            # canvas. Clip the caption to actual page coordinates instead of
            # failing the entire retained document on pdfplumber's strict crop.
            left = max(page.bbox[0], bounds[0])
            top = max(page.bbox[1], bounds[1] - 130)
            right = min(page.bbox[2], bounds[2])
            bottom = min(page.bbox[3], bounds[1])
            if left < right and top < bottom:
                caption = page.crop((left, top, right, bottom)).extract_text() or ""
            # Keep only the nearest table caption when more than one is visible.
            headings = list(
                re.finditer(r"(?:Cuadro|Anexo)\s+\d+", caption, re.IGNORECASE)
            )
            if headings:
                caption = caption[headings[-1].start() :]
    context = header + "\n" + caption
    if re.search(
        r"(?:cuadro|tabla)[^\n]*variaci[oó]n\s+porcentual", caption, re.IGNORECASE
    ):
        return None
    comparison = {}
    if monthly:
        # Older mixed price/change matrices explicitly label the reference and
        # comparison months as "Agosto/julio 2015".  The price is for the first
        # month; the second belongs to the adjacent Var % columns.  Only this
        # declared monthly-comparison layout permits a two-month caption.
        month_names = "|".join(sorted(MONTH_NUM, key=len, reverse=True))
        pair_pattern = (
            rf"\b({month_names})\s*(?:(20\d{{2}})\s*)?/\s*"
            rf"({month_names})\s+(?:de\s+)?(20\d{{2}})\b"
        )
        pairs = list(re.finditer(pair_pattern, context, re.IGNORECASE))
        period_context = context
        pair_periods = set()
        if pairs and not re.search(r"variaci[oó]n\s+mensual", context, re.IGNORECASE):
            return None
        if pairs:
            for pair in pairs:
                current_name, current_year, previous_name, final_year = pair.groups()
                current = MONTH_NUM[current_name.lower()]
                previous = MONTH_NUM[previous_name.lower()]
                year = int(current_year or final_year)
                previous_year = int(final_year)
                if (
                    previous != (current - 2) % 12 + 1
                    or previous_year != year - int(current == 1)
                    or (current == 1 and current_year is None)
                ):
                    raise SourceDateMismatch(
                        "PDF monthly comparison needs consecutive, explicitly dated months"
                    )
                pair_periods.add((year, current))
                comparison = {
                    "comparison_period": f"{previous_year:04d}-{previous:02d}",
                    "period_evidence": pair.group(0),
                }
            # Still validate any other printed dates outside the comparison.
            period_context = re.sub(pair_pattern, "", context, flags=re.IGNORECASE)
        periods = {
            (int(year), MONTH_NUM[month.lower()])
            for month, year in re.findall(
                r"\b(" + "|".join(MONTH_NUM) + r")\s+(?:de\s+)?(20\d{2})\b",
                period_context,
                re.IGNORECASE,
            )
        } | pair_periods
        if not periods:
            return None
        if periods != {(day.year, day.month)}:
            raise SourceDateMismatch(
                f"PDF monetary table period {sorted(periods)} disagrees with {day}"
            )
    else:
        printed_day = date_from_text(context)
        if printed_day is None:
            return None
        if printed_day != day:
            raise SourceDateMismatch(
                f"PDF monetary table date {printed_day} disagrees with {day}"
            )
    return {
        "parser_version": PRICE_GRID_VERSIONS[monthly],
        "source_type": "pdf",
        "source_header": header,
        "source_caption": caption,
        "published_basis": (
            "Precio mensual publicado por ciudad"
            if monthly
            else "Precio diario publicado por ciudad"
        ),
        "unit_basis": "Printed Precio $/Kg; SIPSA product unit exceptions preserved",
        **comparison,
    }


def has_table_sized_image(page):
    """Exclude banners/logos when a supported price page has no parsed cells."""
    return any(
        (image["x1"] - image["x0"]) >= page.width * 0.35
        and (image["bottom"] - image["top"]) >= page.height * 0.20
        and (image["x1"] - image["x0"]) * (image["bottom"] - image["top"])
        >= page.width * page.height * 0.12
        for image in page.images
    )


class VerifiedPDFPage:
    """Literal, agreeing OCR cells presented to the ordinary table parser."""

    def __init__(self, result):
        self.result = result
        self.images = []

    def extract_text(self):
        return self.result["text"]

    def extract_tables(self):
        return self.result["tables"]

    def close(self):
        pass


def verified_page(db, page, did, kind, number):
    """Use cached independent readings or queue this failed page, not its peers."""
    from .ocr import VERSION as OCR_VERSION
    from .ocr import compare_city_price_readings, compare_readings, enqueue_image

    readings = db.execute(
        """SELECT r.result FROM source_ocr_task t JOIN source_ocr_result r ON r.image_id=t.image_id
        WHERE t.document_id=%s AND t.source_page=%s AND r.version=%s ORDER BY r.reading""",
        (did, number, OCR_VERSION),
    ).fetchall()
    agreed = len(readings) == 2 and (
        compare_city_price_readings(
            readings[0][0], readings[1][0],
            native_heading=page.pdf.pages[0].extract_text() or None,
        ) if kind == "city-pdf" else compare_readings(readings[0][0], readings[1][0])
    )
    if agreed:
        return VerifiedPDFPage(readings[0][0])
    enqueue_image(
        db,
        did,
        f"PDF page {number}",
        page.to_image(resolution=200).original,
        kind,
        number,
    )
    return None


class PDFOCRPending(ValueError):
    """Originals and failed pages are retained while independent OCR is pending."""


def _blank_repeated_stationery(page, text):
    """A blank leaf with only repeated margin artwork has no failed price grid.

    Require identical embedded image bytes and placement on a nearby readable
    page. A small body image, unfamiliar marginal image, or corrupt native text
    still takes the ordinary OCR path. No visual content is guessed from size.
    """
    if text.strip() or not 1 <= len(page.images) <= 4:
        return False

    def marginal(image):
        # The 2014-17 DANE daily stationery header extends to about 10.8%
        # of a blank final leaf. Exact image bytes and placement must still
        # match a nearby readable page before skipping it.
        return image["bottom"] - image["top"] <= page.height * 0.12 and (
            image["bottom"] <= page.height * 0.12 or image["top"] >= page.height * 0.90
        )

    if not all(marginal(image) for image in page.images):
        return False
    number = getattr(page, "page_number", 0)
    pdf = getattr(page, "pdf", None)
    if pdf is None or number < 2:
        return False

    def signature(image):
        return (
            *(round(image[key], 1) for key in ("x0", "x1", "top", "bottom")),
            sha256(image["stream"].get_data()).digest(),
        )

    earlier = set()
    for previous in pdf.pages[max(0, number - 3) : number - 1]:
        if len((previous.extract_text() or "").strip()) >= 100:
            earlier.update(
                signature(image) for image in previous.images if marginal(image)
            )
    return bool(earlier) and all(signature(image) in earlier for image in page.images)


# These exact image streams were independently rendered and checked in 43
# official PDFs: DANE logos, campaign/social closing slides and section art.
# A new image, monetary text, or a corrupt heading never receives this exemption.
VERIFIED_DECORATIVE_IMAGE_SHA256 = frozenset({
    # Rendered February 18, 2019 daily PDF pp4-5: exact fruit/tuber section
    # artwork, no monetary grid. Unknown full-page scans still require OCR.
    '5863f18041a7eed718cef551a819f2bf50ecdc08c69726681dea44ee896da3ce',
    '8b10815133e6a3c2e1f46cd25e327fc2ec5e99afaa61e7bc92a2c8a8e2d2ef56',
    '049bc80becd49f1adaefc45a2475ef64e3f33ef855083d19dbcbf4b7554fb759',
    '0cd2f9e3d582b4436cf0608562c5e82d2999a68c7a37bec63dd161dd261823c7',
    '14e6965e0ad60dce001c00650bfe0a18c8899688afb875fd709014a083f5f167',
    '19daa52cf0e46df1eb0b8beb6b9dec519cdb111029b21ae9bace2113142fe8a5',
    '1b9114c9a3052419c369df648174d5a387244bc63654dc69f4691892fdaafefb',
    '1bdaca45d2c41cda94c8b10ef3b47870f5b9df609139c9638d502abc3073df7d',
    '1bdee5d41950cc25797a4cc77c75c5cb044d2cfe011f197a79793d71e27de99a',
    '1c02886c7ba1ccfd803ceecd229b1fc6b9e5e9f2d740972fa6b90672c34e9077',
    '1efdda8c2c97d9c34f5dd88fc225514e9b53f2afacaaddc3240978123f3a8d76',
    '20bcf952752099f268433255b781d771ce2b223ab62fc017efb1405fface0829',
    '22c55af230fdb55cb9794ca85cf06724f617dc83604d48ab5ddfdd99d9054d1f',
    '2b3574fdc0ccb3e3a1d0f89b8359b8bdd8aa48ad0fb36efce198c25491007f9d',
    '353abd768419c8ab2590092b61c5885f42faf2f191b293f196d3909dd9d24219',
    '37575ddf7fecc6e78e5949c79030d6a43f64943069e9d050baf2490fdfd4089a',
    '3874b0af127ed81b62ed7f7337cb05e4911e7952f9e722c056852742673364f0',
    '3ee4cf01a37cb6f8fb6cce96d6c1dc2cb941e9e001c7cedc4ab29d8983a4df92',
    '484eea7beab0ddf61977dbc84eb796655e384cbaf174860e103d563086043586',
    '48c505cb503d7839591372e96d460c6af7fb94a183d6efd69fd68d4ce12f66d3',
    '4b6c0a17d50a43dfb7442188d6ae41cdedc960d1c369a37dc783ac52f81f2bc6',
    '4d94a254798e5072aaa5cfc7d9d4e3f0ad467065d8f3d373a93338affc8bb22c',
    '4daae72db4737f623324ae3e58d7d8af7b25a877fc467c3f5f1f773d51d06c67',
    '4dd676bd9a8e90f1a50fe9bf968ce8ff19dd2667873da73d5691778b26951645',
    '4e4bf8f0240d9f1cf7ba986c2269ad30e17eb9abf90d488ea6c899fc390b9572',
    '61611bff011254ee8e0f218128555556acdc8ff30be73f60e7b2e11df823109f',
    '69629dd004538f9c0f6103b9b91bc585d2f9b6655c20b73f660f7b45410c0d10',
    '6cf4ebd7d891abb7d2e46c464bc84a683ece55ce398a010894ed001b868f38d2',
    '6ec6992cd83803f82cba81f72f6cf27a0d996f2aeadeca0e5d143c09e13d414c',
    '7292c3fbbc2f108ac823b9757efdb6b63a174895a00f1a4150315afc3b4419a1',
    '84e65c4b940ff4b1d9c072151333dc3ed17dc267f5aa6e86c1ed40a293230faa',
    '85d91f518e473b3acaf299357f04199c4e937b2f205209a3b41367b3140ea0a8',
    '87ba6d12874c0373d79a8bca69893e67c91411ea3fc9e8cb89b18357e0d8bd62',
    '8979a7f09461b1e013f462ca5a868ca5f9ca96fe37c9b46fb6fc958ab04fd1eb',
    '8ba24eb1900e971dc0a0b619a54f7c74dec1931bf1868ad440f1560d7f04e8a3',
    '8d00e4fd36ae4abb2f49bc06bff3dfb64a0884db26598390a3f0b060a4c61024',
    '8f4ba18659cddf80f5008140606103a611fe3e90d7bf22985cd701e42f10d323',
    '9035b91aee5493c2c2f2dcce273f46ad7328ffb13417db789be6b2b3f6980300',
    '930f1828ea03cc740b9a635885c1e1d8f78dca50b1061d2a660e1095bed37a37',
    '9463924c822f93719001bb2959f49ff029e67f6e59800698f8b66030718fd0b4',
    '9503694fc73f7e99320d529388f6107b20eed692f843edf2f7d14dfc3a23c9e5',
    '9b5033886d4eb6917fc9109af632bee2f4933a5906a476360006d399515d1ef0',
    '9e94b18544af64181ad1200cdfdc073937f15758179cf5fd8eb83d1571fb2531',
    'a4d6588ae08c2e975994e6dfd831c256292ce37e80ff7f843dcc05dcc2a3a5e4',
    'a65718641b02f3b898a2d71d6b85ef4b32d609a163e581eb21a6b4bc7265d65e',
    'b0aacc18ca3fa365e07e5a447f505ccbc7019ace8f0f76ea007275520760de4b',
    'b364f66773dcc132e19f5a8db5445edf843bd9f6c8534ab4cefbb388c8d2f3e0',
    'b3e8e1457f27720fb5d00fe64da6a87e924e9512ab29cab1456bb87f0376a210',
    'bcaa6947f46be9049946018f8f4bf52fb612ced9d8c65a61575ba4727ed592eb',
    'c21a62dc17f67ef6175a26a268401a99a5d358580e46286733588d1e6b027e36',
    'c82d3dafb934427695c1a13c51ad1befb81dd3d699ef6fe806c6e9976ed7e63c',
    'c9fc7632ac53b85609ad316526d5ce49fd52f4cc6b1452baa523136ce787989c',
    'd6c4d00bf1ca38c04d790f5efb9ef4cef4505f39ad477a22b4fbb701f079b603',
    'e878c00714aed67d43213b12f7e9941fcf213164aa7df941beed9b1dcbd02e37',
    'eacbbb4174f4b3f42a8596e56f8391d5e87811530b651bbebad2f885193f32f2',
    'fa8c20c5b7f69bd78ccb3f7e0e8462f3926dd793ba88454b11b544afa408b88a',
    'fc4eeeb83f6d07126a75990b238d4f5c043abd332154a052755626455b0f5650',
})
_DECORATIVE_NATIVE_HEADINGS = frozenset({
    "", "comunicado de prensa", "verduras y hortalizas",
    "variación 12 meses", "comparación ipc", "comparación ipc e ipp",
})


def _verified_decorative_page(page, text):
    """Recognize only verified artwork with a fully readable known heading."""
    if " ".join(text.split()).casefold() not in _DECORATIVE_NATIVE_HEADINGS:
        return False
    if not page.images:
        return False
    try:
        return all(
            sha256(image["stream"].get_data()).hexdigest()
            in VERIFIED_DECORATIVE_IMAGE_SHA256
            for image in page.images
        )
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def native_price_page_failure(page, text, native_prices, previous_price_grid=False):
    """The shared native-first decision for parsing and old queued PDF pages."""
    from .ocr import needs_ocr

    if _verified_decorative_page(page, text):
        return False
    if _blank_repeated_stationery(page, text):
        return False
    # Some presentation dividers have fewer than 20 readable characters and
    # only footer logos / thin decorative bands. That is successful extraction
    # of a short title, not an unreadable price table. Keep the exception narrow:
    # a body image, substantial raster table or corrupt title still needs OCR.
    if " ".join(text.split()).casefold() in {"frutas frescas", "abastecimiento"}:
        decorative = all(
            image["top"] >= page.height * 0.8
            or image["bottom"] <= page.height * 0.05
            or (
                image["bottom"] - image["top"] <= page.height * 0.02
                and image["x1"] - image["x0"] >= page.width * 0.75
            )
            for image in page.images
        )
        if decorative and not has_table_sized_image(page):
            return False
    if needs_ocr(page, text):
        return True
    if native_prices or not has_table_sized_image(page):
        return False
    # Readable percentage charts and decorative covers are not failed prices.
    if re.search(
        r"(?:cuadro|gr[aá]fico)[^\n]*variaci[oó]n\s+porcentual", text, re.IGNORECASE
    ):
        return False
    return bool(
        (
            _MONEY_KG.search(text)
            and sum(
                city in text
                for city in ("Bogotá", "Medellín", "Cali", "Armenia", "Pereira")
            )
            >= 3
        )
        or (
            previous_price_grid
            and re.search(r"precios?[^\n]*continuaci[oó]n", text, re.IGNORECASE)
        )
    )


def queued_price_page_needs_ocr(data, day, kind, number):
    """Recheck only a queued page and its immediate native-price predecessor."""
    from .worker import parse_pdf_pages

    if kind not in ("daily-pdf", "monthly-pdf") or day is None:
        raise ValueError("Native OCR eligibility needs a supported dated PDF")
    monthly = kind == "monthly-pdf"
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not isinstance(number, int) or not 1 <= number <= len(pdf.pages):
            raise ValueError("Native OCR eligibility has an invalid source page")
        page = pdf.pages[number - 1]
        native = list(parse_pdf_pages([page], day, monthly, allow_empty=True))
        previous = number > 1 and bool(
            list(
                parse_pdf_pages([pdf.pages[number - 2]], day, monthly, allow_empty=True)
            )
        )
        return native_price_page_failure(
            page, page.extract_text() or "", native, previous
        )


def parse_archived_price_pdf(db, data, did, day, kind):
    """Native-first extraction for supported DANE daily/monthly price matrices."""
    from .worker import parse_pdf_pages

    monthly = kind == "monthly-pdf"
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = list(pdf.pages)
        pending = []
        previous_price_grid = False
        for number, page in enumerate(pages, 1):
            check_run_budget()
            text = page.extract_text() or ""
            native_prices = list(
                parse_pdf_pages([page], day, monthly, allow_empty=True)
            )
            failed = native_price_page_failure(
                page, text, native_prices, previous_price_grid
            )
            previous_price_grid = bool(native_prices)
            if not failed:
                continue
            verified = verified_page(db, page, did, kind, number)
            if verified is None:
                pending.append(number)
            else:
                pages[number - 1] = verified
        if pending:
            raise PDFOCRPending(
                f"Price PDF pages {pending} await agreeing OCR readings"
            )
        yield from parse_pdf_pages(pages, day, monthly)


def publish_price_ocr(db, did, kind):
    from .worker import project, save_rows

    source = db.execute(
        "SELECT d.content,a.url,a.observed_on FROM source_document d JOIN ingestion_asset a ON a.document_id=d.id WHERE d.id=%s AND a.kind=%s LIMIT 1",
        (did, kind),
    ).fetchone()
    if not source:
        raise ValueError("PDF OCR has no original dated ingestion asset")
    data, url, day = source
    if day is None:
        raise ValueError("PDF OCR has no verified reference period")
    rows = list(parse_archived_price_pdf(db, bytes(data), did, day, kind))
    with db.transaction():
        count = save_rows(db, did, rows)
        conflicts = project(db, did, url, kind)
        db.execute(
            "UPDATE ingestion_asset SET status='complete',records=%s,checked_at=now(),error=%s WHERE document_id=%s AND kind=%s",
            (
                count,
                f"Conflicting source keys retained but excluded from app: {conflicts}"
                if conflicts
                else None,
                did,
                kind,
            ),
        )
        db.execute(
            "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_kind=%s",
            (did, kind),
        )
    return count


def extract_pages(db, data, did):
    # The immutable cache key is (document SHA, page, extraction version).
    # Fetch only its small page-number index; retained text/tables need not be
    # transferred or re-extracted on parser retries of the same original.
    cached_pages = {
        row[0]
        for row in db.execute(
            "SELECT page FROM source_pdf_page WHERE document_id=%s AND extraction_version=%s",
            (did, VERSION),
        ).fetchall()
    }
    count = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            check_run_budget()
            if number not in cached_pages:
                db.execute(
                    """INSERT INTO source_pdf_page(document_id,page,text_content,tables,extraction_version)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (
                        did,
                        number,
                        page.extract_text() or "",
                        Jsonb(page.extract_tables()),
                        VERSION,
                    ),
                )
            count += 1
            page.close()
    from .ocr import scan_document

    kind = db.execute(
        "SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=%s", (did,)
    ).fetchone()[0]
    scan_document(db, data, did, kind)
    return count


def input_category(title):
    from .inputs import CATEGORIES
    from .worker import clean

    text = re.sub(
        r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)", "", title, flags=re.IGNORECASE
    )
    text = re.sub(r"^.*?Precios de\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^Insumos (?:agrícolas|pecuarios)\.\s*", "", text, flags=re.IGNORECASE
    )
    text = clean(text).strip(" .").capitalize()
    prefixes = {
        "alimentos balanceados": "2.1",
        "antibióticos": "2.2",
        "antisépticos": "2.3",
        "vitaminas": "2.7",
        "sales y minerales": "2.7",
        "antinflamatorios": "2.6",
        "fertilizantes": "1.3",
        "coadyudantes": "1.2",
        "coadyuvantes": "1.2",
        "especie productiva": "3.4",
        "material de propagación": "3.6",
        "empaques": "3.3",
        "jornales": "3.5",
        "elementos pecuarios": "3.2",
    }
    return next(
        (
            CATEGORIES[key]
            for prefix, key in prefixes.items()
            if text.lower().startswith(prefix)
        ),
        text,
    )


def _input_line_text(words):
    """Join glyph runs split only by a font change, without inventing spaces."""
    parts = []
    previous = None
    for word in words:
        gap = word["x0"] - previous["x1"] if previous else None
        parts.append((" " if gap is not None and gap > 0.5 else "") + word["text"])
        previous = word
    return "".join(parts).strip()


def _input_presentation(heading, heading_lines):
    # A decimal comma belongs to the product/quantity, whereas a separator may
    # have no following space (the July 2014 source prints "15 litros,unidad").
    separators = [
        match.start()
        for match in re.finditer(",", heading)
        if not (
            match.start() > 0
            and heading[match.start() - 1].isdigit()
            and heading[match.end() : match.end() + 1].isdigit()
        )
    ]
    if separators:
        index = separators[-1]
        name, presentation = heading[:index].strip(), heading[index + 1 :].strip()
        if name and presentation:
            return name, presentation
    # Some originals omit the separator but put an explicit presentation on
    # its own heading line. Keep even publisher duplication verbatim; do not
    # silently turn the printed "unidad 1 unidad" into an inferred package.
    if len(heading_lines) > 1 and re.fullmatch(
        r"(?:unidad\s+)?(?:\d+(?:[.,]\d+)?\s+)?unidad(?:es)?",
        heading_lines[-1],
        re.IGNORECASE,
    ):
        return " ".join(heading_lines[:-1]), heading_lines[-1]
    return None


def _input_heading_word(word):
    """The 2019 native layout uses FuturaStd-Heavy for literal headings."""
    font = word["fontname"]
    return "Bold" in font or font.endswith("FuturaStd-Heavy")


def _input_ruled_left(page, header_bottom, left, right, price_left):
    """Use the literal underlined column boundary for centered 2019 headers."""
    edges = sorted(
        [
            e
            for e in page.horizontal_edges
            if left <= e["x0"] < e["x1"] <= right and abs(e["top"] - header_bottom) <= 5
        ],
        key=lambda e: (round(e["top"], 1), e["x0"]),
    )
    spans = []
    for edge in edges:
        if (
            spans
            and abs(spans[-1][2] - edge["top"]) < 0.5
            and abs(spans[-1][1] - edge["x0"]) < 0.5
        ):
            spans[-1][1] = edge["x1"]
        else:
            spans.append([edge["x0"], edge["x1"], edge["top"]])
    candidates = [x0 for x0, x1, _ in spans if x0 < price_left and x1 > price_left + 40]
    if len(set(candidates)) != 1:
        raise ValueError("Input PDF centered header lacks a unique ruled body boundary")
    return candidates[0]


def _input_wrapped_department(lines, index, price_left, numeric, percentage,
                              *, department_resolver=None):
    """Bind only an adjacent explicit parenthesized department to its price row.

    Some tables put a municipality and its numeric cells on one line, then the
    department on the next. Others vertically center the cells between those
    location lines. Never infer a department or carry it across a product.
    """
    from .special_prices import DEPARTMENTS
    from .worker import clean

    top, words = lines[index]
    if any(_input_heading_word(w) for w in words):
        return None
    if numeric:
        location, price = numeric.group(1, 2)
        variation = numeric[3] if percentage else "n.d."
        location_words = [w for w in words if w["x0"] < price_left]
    else:
        raw = clean(_input_line_text(words))
        match = re.fullmatch(
            r"(\d[\d.,]*)" + (r"\s+(n\.d\.|[-+]?\d[\d.,]*)" if percentage else ""),
            raw,
            re.IGNORECASE,
        )
        if not match or index == 0 or min(w["x0"] for w in words) < price_left - 10:
            return None
        _, location_words = lines[index - 1]
        if (
            any(_input_heading_word(w) for w in location_words)
            or max(w["x1"] for w in location_words) >= price_left
        ):
            return None
        # In this native layout the numeric baseline is vertically centered
        # between the municipality and department baselines. Their word boxes
        # overlap by about 2.3 pt although the printed lines are distinct.
        if not -3.5 <= top - max(w["bottom"] for w in location_words) <= 5:
            return None
        location = clean(_input_line_text(location_words))
        price = match[1]
        variation = match[2] if percentage else "n.d."
    if not location_words or not re.fullmatch(
        r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'(\-]{1,119}", location
    ):
        return None
    if index + 1 >= len(lines):
        return None
    next_top, suffix_words = lines[index + 1]
    if (
        any(_input_heading_word(w) for w in suffix_words)
        or max(w["x1"] for w in suffix_words) >= price_left
        or abs(
            min(w["x0"] for w in suffix_words) - min(w["x0"] for w in location_words)
        )
        > 5
        or not -3.5 <= next_top - max(w["bottom"] for w in words) <= 5
    ):
        return None
    suffix = clean(_input_line_text(suffix_words))
    combined = (
        location[:-1] + suffix if location.endswith("-") else location + " " + suffix
    )
    match = re.fullmatch(r"(.+?)\s*\(([^)]+)\)\s*\*?", combined)
    if not match and "(" not in location:
        # The publisher twice omits the opening parenthesis on a separately
        # printed, otherwise literal department. Its full name is required.
        department = re.fullmatch(r"([^()]+)\)", suffix)
        if department and _input_department_is_known(department[1], department_resolver):
            combined = location + " (" + suffix
            match = re.fullmatch(r"(.+?)\s*\(([^)]+)\)", combined)
    if not match or not _input_department_is_known(match[2], department_resolver):
        return None
    return combined, price, variation, [location, suffix]


def _input_displaced_location(lines, index, price_left, percentage,
                              *, department_resolver=None):
    """Read a native municipality printed after the prior row's numeric cells.

    Two 2015 originals place the next municipality after a touching price and
    percentage. Require both complete native rows, an explicit department,
    adjacent baselines and aligned price boxes; no OCR or inferred place text.
    """
    from .special_prices import DEPARTMENTS
    from .worker import clean

    if not percentage:
        return None
    for first in (index, index - 1):
        if first < 0 or first + 1 >= len(lines):
            continue
        _, prior = lines[first]
        _, current = lines[first + 1]
        if not prior or not current or any(_input_heading_word(w) for w in prior + current):
            continue
        left = [w for w in prior if w["x0"] < price_left]
        cells = [w for w in prior if w["x0"] >= price_left]
        suffix = [w for w in current if w["x0"] < price_left]
        next_cells = [w for w in current if w["x0"] >= price_left]
        if not left or not suffix or len(cells) < 3 or len(next_cells) != 2:
            continue
        previous_place = clean(_input_line_text(left))
        complete_place = re.fullmatch(r"(.+?)\s*\(([^)]+)\)", previous_place)
        department_line = clean(_input_line_text(suffix))
        department = re.fullmatch(r"\(([^)]+)\)", department_line)
        name_words = cells[2:]
        name = clean(_input_line_text(name_words))
        price, variation = cells[:2]
        if (
            not complete_place or not _input_department_is_known(complete_place[2], department_resolver)
            or not department or not _input_department_is_known(department[1], department_resolver)
            or not re.fullmatch(r"[A-Za-zÀ-ÿ]+(?: [A-Za-zÀ-ÿ]+)*", name)
            or max(w["x1"] for w in left + suffix) >= price_left
            or abs(left[0]["x0"] - suffix[0]["x0"]) > 2
            or not -1 <= current[0]["top"] - max(w["bottom"] for w in prior) <= 5
            or abs(price["x1"] - next_cells[0]["x1"]) > 2
            or not -0.1 <= variation["x0"] - price["x1"] <= 0.5
            or not 0 <= name_words[0]["x0"] - variation["x1"] <= 5
            or any(not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", w["text"])
                   for w in (price, next_cells[0]))
            or any(not re.fullmatch(r"[-+]?\d+(?:,\d+)?", w["text"])
                   for w in (variation, next_cells[1]))
        ):
            continue
        first_row = index == first
        location = previous_place if first_row else name + " " + department_line
        numbers = cells[:2] if first_row else next_cells
        return {
            "line": location + " " + " ".join(w["text"] for w in numbers),
            "location_lines": [previous_place] if first_row else [name, department_line],
            "evidence": {
                "method": "native-displaced-municipality",
                "municipality": name,
                "department": department[1],
                "preceding_printed_line": clean(_input_line_text(prior)),
                "following_printed_line": clean(_input_line_text(current)),
                "municipality_bbox": [name_words[0]["x0"], name_words[0]["top"],
                                      name_words[-1]["x1"], name_words[-1]["bottom"]],
            },
        }
    return None


def _input_location_prefix(previous, words, price_left, *, department_resolver=None):
    """Recover an adjacent, visibly wrapped municipality without guessing names.

    A grammatical connector or a complete parenthesized department permits
    joining. The first line must contain location-column text only, not a heading,
    price, note, or another complete municipality/department row.
    """
    if not previous or not words:
        return ""
    prior = previous[1]
    if not prior or any(_input_heading_word(w) for w in prior):
        return ""
    prefix = " ".join(previous[2])
    connectors = {"de", "del", "la", "las", "los"}
    from .special_prices import DEPARTMENTS

    department = re.fullmatch(
        r"\(([^)]+)\)\s*\*?",
        _input_line_text([w for w in words if w["x0"] < price_left]).strip(),
    )
    explicit_department = bool(
        department and _input_department_is_known(department[1], department_resolver)
    )
    if (
        len(prefix) > 80
        or not re.fullmatch(
            r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?: [A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*", prefix
        )
        or max(w["x1"] for w in prior) >= price_left
        or abs(min(w["x0"] for w in prior) - min(w["x0"] for w in words)) > 2
        or not -1 <= min(w["top"] for w in words) - max(w["bottom"] for w in prior) <= 5
        or not (
            explicit_department
            or words[0]["text"] in connectors
            or prefix.split()[-1] in connectors
        )
    ):
        return ""
    return prefix


def _input_continuation_review(current, previous):
    """Check explicit continuation against the adjacent, same-table block.

    A contradictory printed presentation is retained literally, never repaired
    from the preceding column or another source. Nonadjacent/different tables
    provide no evidence of contradiction and are not used to infer identity.
    """
    from .worker import slug

    if not previous or not current["table"][0] or current["table"] != previous["table"]:
        return None
    if not (
        (
            current["page"] == previous["page"]
            and current["column"] >= previous["column"]
        )
        or (current["page"] == previous["page"] + 1 and current["column"] == 1)
    ):
        return None
    if tuple(map(slug, current["identity"])) != tuple(map(slug, previous["identity"])):
        return {
            "reason": "Printed continuation product/presentation conflicts with the preceding same-table block",
            "preceding_heading": previous["heading"],
            "preceding_page": previous["page"],
            "preceding_column": previous["column"],
            "continued_heading": current["heading"],
        }
    return previous.get("continuation_review")


def _input_pdf_place(location, *, department_resolver=None):
    """Bind a printed municipality to an actual named department.

    The publisher may append the literal table marker `(continuación)` after
    an already complete place. Remove only that terminal marker; retain the
    printed line separately in `printed_location_lines`.
    """
    from .special_prices import DEPARTMENTS
    from .worker import clean

    original = clean(location)
    suffix = re.fullmatch(r"(.+?\([^)]+\))\s*\(continuaci[oó]n\)\s*\*?", original, re.IGNORECASE)
    candidate = suffix[1] if suffix else original
    place = re.fullmatch(r"(.*?)\s*\(([^)]+)\)\s*\*?", candidate)
    if place:
        municipality, department = map(clean, place.groups())
        if department_resolver is not None:
            canonical = department_resolver(department)
            if canonical is not None:
                return municipality, canonical, bool(suffix)
            return None
        if department in DEPARTMENTS:
            return municipality, department, bool(suffix)
        return None
    if re.fullmatch(r"Bogot[aá],?\s*D\.?\s*C\.?\s*\*?", candidate):
        return "Bogotá, D.C.", "Bogotá, D.C.", False
    return None


def parse_input_pdf(data, day, *, last_page=None, parser_version=None):
    """Read each dated two-column table, including layouts without variation.

    Table-local titles/date stamps avoid borrowing the date of an unrelated chart
    or electricity table above. Price rows require explicit geographic identity.
    """
    from .worker import MONTH_NUM, SourceDateMismatch, clean, record

    version = parser_version or INPUT_PDF_VERSION
    if not re.fullmatch(r"inputs-pdf-v[0-9]+", version):
        raise ValueError("Unsupported input PDF parser version")
    department_resolver = None
    if int(version.rsplit("v", 1)[1]) > 14:
        from .reviewed_wuxal_apr2015 import DAY as APR_DAY, SHA256 as APR_SHA, VERSION as APR_VERSION
        from .reviewed_quindio_sep2014 import (
            DAY as SEP_DAY, SHA256 as SEP_SHA, VERSION as SEP_VERSION,
            canonical_department,
        )

        digest = sha256(data).hexdigest()
        if version == APR_VERSION and day == APR_DAY and digest == APR_SHA:
            pass
        elif version == SEP_VERSION and day == SEP_DAY and digest == SEP_SHA:
            department_resolver = canonical_department
        elif version == GENERIC_DEPARTMENT_FOLD_VERSION:
            department_resolver = _unique_known_input_department
        else:
            raise ValueError("Input PDF revision requires the exact reviewed original and date")

    last_row_heading = None
    exact_wuxal_continuation = sha256(data).hexdigest() == "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            check_run_budget()
            if last_page is not None and page_no > last_page:
                break
            text = page.extract_text() or ""
            if "mercados" not in text or "Precio" not in text or "medio" not in text:
                page.close()
                continue
            all_words = [
                w for w in page.extract_words(extra_attrs=["fontname"]) if w["upright"]
            ]
            heading = ""
            heading_lines = []
            previous_category = None
            for col, (left, right) in enumerate(
                [(0, page.width / 2), (page.width / 2, page.width)], 1
            ):
                words = [w for w in all_words if left <= w["x0"] < right]
                headers = [w for w in words if w["text"] == "mercados"]
                for header in headers:
                    nearby = [w for w in words if abs(w["top"] - header["top"]) < 24]
                    price_headers = [w for w in nearby if w["text"] == "Precio"]
                    if not price_headers:
                        continue
                    # January 2019 prints Precio above medio enero. Reading
                    # order interleaves the neighbouring prose/variation column,
                    # so the words need not be adjacent in page-level text.
                    mean_headers = [
                        w
                        for w in nearby
                        if w["text"] == "medio"
                        and any(
                            w["x0"] <= p["x1"] + 12
                            and w["x1"] >= p["x0"] - 12
                            and abs(w["top"] - p["top"]) < 20
                            for p in price_headers
                        )
                    ]
                    if "Precio medio" not in text and not mean_headers:
                        continue
                    price_left = min(w["x0"] for w in price_headers)
                    location_headers = [
                        w
                        for w in nearby
                        if abs(w["top"] - header["top"]) < 3 and w["x0"] < price_left
                    ]
                    table_left = min(w["x0"] for w in location_headers) - 8
                    percentage_headers = [
                        w for w in nearby if w["text"] == "porcentual"
                    ]
                    month_headers = [
                        w
                        for w in nearby
                        if w["text"].lower() in MONTH_NUM and w["x0"] >= price_left
                    ]
                    header_bottom = max(
                        w["bottom"]
                        for w in [
                            header,
                            *percentage_headers,
                            *month_headers,
                            *mean_headers,
                        ]
                    )
                    if "FuturaStd-" in header["fontname"]:
                        table_left = _input_ruled_left(
                            page, header_bottom, left, right, price_left
                        )
                    end = min(
                        [h["top"] for h in headers if h["top"] > header_bottom]
                        or [page.height - 18]
                    )
                    prefix = " ".join(
                        w["text"]
                        for w in sorted(
                            all_words, key=lambda w: (round(w["top"], 1), w["x0"])
                        )
                        if w["top"] < header["top"] - 8
                    )
                    stamps = list(
                        re.finditer(
                            r"(20\d{2})\s*\(([a-záéíóú]+)\)|\(([a-záéíóú]+)\s+de\s+(20\d{2})\)",
                            prefix,
                            re.IGNORECASE,
                        )
                    )
                    if not stamps:
                        raise SourceDateMismatch(
                            f"Input PDF table has no month: page {page_no}"
                        )
                    stamp = stamps[-1]
                    if (
                        int(stamp[1] or stamp[4]),
                        MONTH_NUM.get((stamp[2] or stamp[3]).lower()),
                    ) != (
                        day.year,
                        day.month,
                    ):
                        raise SourceDateMismatch(
                            f"Input PDF table month differs from archive link: page {page_no}, {stamp[0]}"
                        )
                    printed_price_months = sorted(
                        {w["text"].lower() for w in month_headers}
                    )
                    date_issue = (
                        "Printed price-column month "
                        + ", ".join(printed_price_months)
                        + " conflicts with table caption "
                        + stamp[0]
                        if any(MONTH_NUM[m] != day.month for m in printed_price_months)
                        else None
                    )
                    # Use the last table title, not an earlier table on the same page.
                    title = re.split(
                        r"(?:Cuadro|Tabla)\s+\d+\.\s+", prefix[: stamp.start()]
                    )[-1]
                    category = input_category(title)
                    irrigation = bool(
                        re.search(
                            r"Precios del agua en los distritos de riego",
                            title,
                            re.IGNORECASE,
                        )
                    )
                    if irrigation:
                        category = "Servicios agrícolas"
                    table_numbers = re.findall(r"(?:Cuadro|Tabla)\s+(\d+)\.", prefix)
                    table_key = (
                        table_numbers[-1] if table_numbers else None,
                        category,
                        day,
                    )
                    if category != previous_category:
                        heading = ""
                        heading_lines = []
                    previous_category = category
                    table_right = (
                        max(w["x1"] for w in percentage_headers) + 10
                        if percentage_headers
                        else right - 12
                    )
                    lines = []
                    body = [
                        w
                        for w in words
                        if w["x0"] >= table_left
                        and w["x1"] <= table_right
                        and w["top"] > header_bottom
                        and w["bottom"] < end
                    ]
                    for w in sorted(body, key=lambda w: (round(w["top"], 1), w["x0"])):
                        if not lines or abs(lines[-1][0] - w["top"]) > 2:
                            lines.append((w["top"], [w]))
                        else:
                            lines[-1][1].append(w)
                    previous_heading = False
                    heading_bottom = None
                    unresolved = False
                    last_line = None
                    table_rows = 0
                    heading_continues = False
                    heading_checked = False
                    continuation_review = None
                    literal_heading_lines = heading_lines.copy()
                    for line_no, (top, ws) in enumerate(lines, 1):
                        ws.sort(key=lambda w: w["x0"])
                        line = clean(_input_line_text(ws))
                        if irrigation:
                            # This table prints the irrigation district between
                            # the municipality and price. The apparent variation
                            # header has no variation cells in its body.
                            if all(_input_heading_word(w) for w in ws):
                                heading = line
                                heading_lines = [line]
                                continue
                            water = re.fullmatch(
                                r"(.+?\([^)]+\))\s+(.+?)\s+(\d[\d.,]*)",
                                line,
                            )
                            if water:
                                place = re.fullmatch(r"(.+?)\s*\(([^)]+)\)", water[1])
                                if not place or not heading or not water[2].strip():
                                    raise ValueError(
                                        f"Input PDF irrigation row lacks printed identity: page {page_no}, col {col}, line {line_no}"
                                    )
                                municipality, department = map(clean, place.groups())
                                value = float(water[3].replace(".", "").replace(",", "."))
                                if value <= 0:
                                    raise ValueError(
                                        f"Input PDF irrigation price is not positive: page {page_no}, col {col}, line {line_no}"
                                    )
                                table_rows += 1
                                yield record(
                                    "dane-inputs-pdf",
                                    day,
                                    clean(water[2]),
                                    municipality,
                                    heading,
                                    value,
                                    f"PDF page {page_no},col {col},y {top:.1f}; {version}",
                                    None,
                                    {
                                        "sheet": "pdf",
                                        "parser_version": version,
                                        "extraction_method": "native-pdf-word-geometry",
                                        "printed_category": clean(title),
                                        "category": category,
                                        "presentation": heading,
                                        "brand": "",
                                        "ica": "",
                                        "department": department,
                                        "municipality": municipality,
                                        "page": page_no,
                                        "printed_heading": heading,
                                        "printed_heading_lines": heading_lines.copy(),
                                        "printed_irrigation_district": clean(water[2]),
                                        "quality_issue": None,
                                    },
                                )
                                continue
                            if re.match(r"^.+?\([^)]+\)\s+", line):
                                raise ValueError(
                                    f"Input PDF irrigation row cannot be verified: page {page_no}, col {col}, line {line_no}"
                                )
                            continue
                        displaced = _input_displaced_location(
                            lines, line_no - 1, price_left, bool(percentage_headers),
                            department_resolver=department_resolver,
                        )
                        if displaced:
                            line = displaced["line"]
                        preceding_line = last_line
                        location_prefix = _input_location_prefix(
                            preceding_line, ws, price_left,
                            department_resolver=department_resolver,
                        )
                        location_lines = (
                            preceding_line[2] + [line] if location_prefix else [line]
                        )
                        last_line = (top, ws, location_lines)
                        if len(line) == 1 and line.isalpha():
                            continue  # Decorative vertical margin lettering.
                        # Preserve overprinted product identities for review;
                        # never borrow the preceding product's name.
                        if line.startswith("Cuadro"):
                            heading = ""
                            heading_lines = []
                            unresolved = True
                            previous_heading = False
                            continue
                        line = re.sub(
                            r"^20\d{2}\s*\([a-záéíóú]+\)\s*",
                            "",
                            line,
                            flags=re.IGNORECASE,
                        )
                        pattern = (
                            r"^(.+?)\s+(\d[\d.,]*)"
                            + (
                                r"\s+(n\.d\.|[-+]?\d[\d.,]*)"
                                if percentage_headers
                                else ""
                            )
                            + r"\s*$"
                        )
                        numeric = re.match(pattern, line, re.IGNORECASE)
                        wrapped = _input_wrapped_department(
                            lines,
                            line_no - 1,
                            price_left,
                            numeric,
                            bool(percentage_headers),
                            department_resolver=department_resolver,
                        )
                        if wrapped:
                            location, price, variation, wrapped_location_lines = wrapped
                            line = (
                                location
                                + " "
                                + price
                                + (" " + variation if percentage_headers else "")
                            )
                            numeric = re.match(pattern, line, re.IGNORECASE)
                        if numeric and (
                            re.match(r"^(.*?)\s*\(([^)]+)\)\s*\*?$", numeric[1])
                            or re.fullmatch(
                                r"Bogot[aá],?\s*D\.?\s*C\.?\s*\*?", numeric[1]
                            )
                        ):
                            location, price = numeric.group(1, 2)
                            printed_location_lines = (
                                wrapped_location_lines if wrapped else
                                displaced["location_lines"] if displaced else [location]
                            )
                            if location_prefix and not wrapped:
                                printed_location_lines = preceding_line[2] + [location]
                                location = location_prefix + " " + location
                            variation = numeric[3] if percentage_headers else "n.d."
                            place = _input_pdf_place(
                                location, department_resolver=department_resolver
                            )
                            if place is None:
                                continue
                            municipality, department, location_suffix = place
                            if not heading and not unresolved:
                                raise ValueError(
                                    f"Input PDF price without product/presentation: page {page_no}, col {col}, line {line_no}"
                                )
                            if not municipality:
                                raise ValueError(
                                    f"Input PDF numeric row lacks a municipality: page {page_no}, col {col}"
                                )
                            quality_issue = None
                            split_heading = _input_presentation(heading, heading_lines)
                            if unresolved:
                                name, presentation = (
                                    "Identidad ilegible en el original",
                                    "Sin presentación verificable",
                                )
                                quality_issue = "Publisher overprinted the product heading with a duplicate table title"
                            elif split_heading:
                                name, presentation = split_heading
                            elif category == "Jornales":
                                name, presentation = heading, "Jornal"
                            elif any(
                                term in category.lower()
                                for term in ("arrendamiento", "servicios", "riego")
                            ):
                                name, presentation = (
                                    heading,
                                    "Según descripción del servicio",
                                )
                            else:
                                name, presentation = (
                                    heading,
                                    "Sin presentación verificable",
                                )
                                quality_issue = "Native product heading has no explicit, separable presentation"
                            current_heading = {
                                "table": table_key,
                                "page": page_no,
                                "column": col,
                                "heading": " ".join(literal_heading_lines),
                                "identity": (name, presentation),
                            }
                            if not heading_checked:
                                continuation_review = (
                                    _input_continuation_review(
                                        current_heading, last_row_heading
                                    )
                                    if heading_continues and not unresolved
                                    else None
                                )
                                heading_checked = True
                            if continuation_review:
                                quality_issue = "; ".join(
                                    issue
                                    for issue in [
                                        quality_issue,
                                        continuation_review["reason"],
                                    ]
                                    if issue
                                )
                            current_heading["continuation_review"] = continuation_review
                            last_row_heading = current_heading
                            if date_issue:
                                quality_issue = "; ".join(
                                    issue
                                    for issue in [quality_issue, date_issue]
                                    if issue
                                )
                            value = float(price.replace(".", "").replace(",", "."))
                            if value <= 0:
                                continue
                            change = (
                                None
                                if variation.lower() == "n.d."
                                else float(variation.replace(".", "").replace(",", "."))
                            )
                            table_rows += 1
                            yield record(
                                "dane-inputs-pdf-unresolved"
                                if quality_issue
                                else "dane-inputs-pdf",
                                day,
                                name,
                                municipality,
                                presentation,
                                value,
                                f"PDF page {page_no},col {col},y {top:.1f}; {version}",
                                change,
                                {
                                    "sheet": "pdf",
                                    "parser_version": version,
                                    "extraction_method": "native-pdf-word-geometry",
                                    "printed_category": clean(title),
                                    "category": category,
                                    "presentation": presentation,
                                    "brand": "",
                                    "ica": "",
                                    "department": department,
                                    "municipality": municipality,
                                    "printed_location_lines": printed_location_lines,
                                    **({"printed_location_suffix": "(continuación)"} if location_suffix else {}),
                                    **({"location_recovery": displaced["evidence"]} if displaced else {}),
                                    "page": page_no,
                                    "printed_heading": heading,
                                    "printed_heading_lines": heading_lines.copy(),
                                    **({"printed_heading_suffix": "(continaución)",
                                        "source_heading_literal": "Wuxal Tapa Negra, 1 litro (continaución)"}
                                       if exact_wuxal_continuation and page_no == 20 and col == 1
                                       and abs(top - 158.3) < 0.6 and name == "Wuxal Tapa Negra"
                                       and presentation == "1 litro" else {}),
                                    **(
                                        {
                                            "printed_table_caption": stamp[0],
                                            "printed_price_column_months": printed_price_months,
                                        }
                                        if date_issue
                                        else {}
                                    ),
                                    **(
                                        {
                                            "continuation_review": continuation_review,
                                            "literal_heading_lines": literal_heading_lines.copy(),
                                        }
                                        if continuation_review
                                        else {}
                                    ),
                                    "quality_issue": quality_issue,
                                },
                            )
                            previous_heading = False
                        elif (
                            all(_input_heading_word(w) for w in ws)
                            or (
                                # Native continuation lines can change font on
                                # one suffix, or entirely. Require an adjacent
                                # established heading, left-aligned text, and
                                # explicit unit vocabulary, never a numeric
                                # cell in the price/variation columns.
                                previous_heading
                                and heading_bottom is not None
                                and -1 <= top - heading_bottom <= 5
                                and abs(ws[0]["x0"] - (table_left + 8)) < 5
                                and re.search(
                                    r"\b(?:kilo\w*|gramos?|litros?|cent[ií]metros?|mililitros?|unidad(?:es)?|metros?|bolsas?|dosis|gal[oó]n(?:es)?|jeringas?|paquetes?|rollos?)\b",
                                    line,
                                    re.IGNORECASE,
                                )
                                and not any(
                                    w["x0"] >= price_left
                                    and re.fullmatch(
                                        r"[-+]?\d[\d.,]*|n\.d\.",
                                        w["text"],
                                        re.IGNORECASE,
                                    )
                                    for w in ws
                                )
                            )
                            or (
                                max(w["x1"] for w in ws) < price_left
                                and re.search(
                                    r",\s*(?:[\d.,]+\s+)?(?:kilo|gram|litro|cent|mili|unidad|metro|bolsa|dosis|gal[oó]n)",
                                    line,
                                    re.IGNORECASE,
                                )
                            )
                        ) and not line.startswith(
                            ("Fuente:", "Nota:", "Cuadro", "Precios")
                        ):
                            is_continuation = bool(
                                re.search(
                                    r"\((?:continuaci[oó]n|conclusi[oó]n)\)",
                                    line,
                                    re.IGNORECASE,
                                )
                            ) or (exact_wuxal_continuation and line.strip() == "(continaución)")
                            literal_heading_lines = (
                                literal_heading_lines + [line]
                                if previous_heading
                                else [line]
                            )
                            heading_continues = (
                                heading_continues or is_continuation
                                if previous_heading
                                else is_continuation
                            )
                            heading_checked = False
                            continuation_review = None
                            line = re.sub(
                                r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)",
                                "",
                                line,
                                flags=re.IGNORECASE,
                            ).strip()
                            if exact_wuxal_continuation and line == "(continaución)":
                                line = ""
                            if line:
                                heading_lines = (
                                    heading_lines + [line]
                                    if previous_heading
                                    else [line]
                                )
                                heading = " ".join(heading_lines)
                            heading_bottom = max(w["bottom"] for w in ws)
                            unresolved = False
                            previous_heading = True
                        else:
                            previous_heading = False
                    if not table_rows:
                        raise ValueError(
                            f"Recognized input monetary table has no verified rows: page {page_no}, col {col}"
                        )
            page.close()


def parse_mixed_feb2018_input(data, day):
    """Keep the exact 2018 price tables and identify every old-year table page.

    This exception is tied to one immutable original. A changed download, date,
    page count, table title, or printed period returns to ordinary date review.
    """
    from datetime import date

    from .worker import SourceDateMismatch

    if sha256(data).hexdigest() != MIXED_FEB2018_INPUT_SHA or day != date(2018, 2, 28):
        raise SourceDateMismatch("Mixed input PDF exception requires the exact retained February 2018 original")
    reviews = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) != 151 or (pdf.pages[150].extract_text() or "").strip():
            raise SourceDateMismatch("Mixed input PDF page boundary differs from reviewed original")
        for page_no in range(141, 151):
            text = pdf.pages[page_no - 1].extract_text() or ""
            captions = re.findall(r"\b20\d{2}\s*\([a-záéíóú]+\)", text, re.IGNORECASE)
            table = 14 if page_no <= 144 else 15
            if (
                captions != ["2017 (febrero)"]
                or not re.search(rf"Cuadro\s+{table}\.\s+Precios de", text)
                or "Precio medio" not in text
                or "mercados" not in text
            ):
                raise SourceDateMismatch(
                    f"Mixed input PDF reviewed table changed: page {page_no}"
                )
            reviews.append(
                {
                    "page": page_no,
                    "source_locator": f"PDF page {page_no}; printed period",
                    "table": table,
                    "printed_caption": captions[0],
                    "archive_period": "2018-02",
                    "reason": "Printed 2017 (febrero) table conflicts with February 2018 archive link",
                }
            )
    rows = list(parse_input_pdf(data, day, last_page=140))
    if len(rows) != 10758 or {r[-1]["page"] for r in rows} != set(range(8, 141)):
        raise SourceDateMismatch("Mixed input PDF verified 2018 page coverage changed")
    return rows, reviews


def publish_mixed_feb2018_input(db, data, did, url, day):
    """Commit valid rows, page reviews, checkpoint, and review status together."""
    from .worker import SourceDateMismatch, project, save_rows

    if url != MIXED_FEB2018_INPUT_URL or did != MIXED_FEB2018_INPUT_SHA:
        raise SourceDateMismatch("Mixed input PDF exception requires the exact source URL and document")
    rows, reviews = parse_mixed_feb2018_input(data, day)
    with db.transaction():
        count = save_rows(db, did, rows)
        if count != 10758:
            raise SourceDateMismatch("Mixed input PDF validated row count changed")
        project(db, did, url, "inputs-pdf")
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO official_source_review
                (document_id,source_locator,parser_version,record,reason)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                [
                    (
                        did,
                        review["source_locator"],
                        INPUT_PDF_VERSION,
                        Jsonb({"source_sha256": did, **review}),
                        review["reason"],
                    )
                    for review in reviews
                ],
            )
            cur.executemany(
                """INSERT INTO ingestion_checkpoint
                (document_id,processor_version,step,records)
                VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING""",
                [
                    (did, INPUT_PDF_VERSION, f"inputs-pdf:date-review:page-{r['page']}")
                    for r in reviews
                ],
            )
        db.execute(
            """UPDATE ingestion_asset SET document_id=%s,status='review',records=%s,
            processor_version=%s,checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s""",
            (
                did,
                count,
                INPUT_PDF_VERSION,
                MIXED_FEB2018_REVIEW_NOTE,
                url,
            ),
        )
    return count
