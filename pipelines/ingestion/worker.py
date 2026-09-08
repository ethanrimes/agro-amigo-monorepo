"""Resumable official-source ingestion. Originals and observations are never deleted.

Each asset commits independently. Its SHA-256 and row locators make retries
idempotent and preserve every publisher revision. PostgreSQL serializes workers.
"""

import argparse
import calendar
import hashlib
import io
import json
import logging
import math
import os
import re
import tempfile
import time
import unicodedata
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

import certifi
import openpyxl
import psycopg
import requests
from bs4 import BeautifulSoup
from psycopg.types.json import Jsonb
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
MONTHLY = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-mensual-1"
DAILY = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas"
INPUTS = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-insumos-1"
SUPPLY = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-abastecimientos-1"
FNC = "https://federaciondecafeteros.org/estadisticas-cafeteras/"
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}
MONTH_NUM.update({m[:3]: i + 1 for i, m in enumerate(MONTHS)})
MONTH_NUM.update({"sept": 9, "agos": 8})
LOCK = 914070912
PARSER_VERSIONS = {
    "daily-index": "source-v2",
    "inputs": "inputs-v2",
    "inputs-municipal": "inputs-v2",
    "inputs-annex": "inputs-v2",
    "inputs-pdf": "inputs-pdf-v4",
    "inputs-reference": "inputs-reference-v2",
    "city-zip": "city-v3",
    "monthly": "monthly-units-v2",
    "monthly-annex": "monthly-annex-v1",
    "daily": "daily-units-v2",
    "daily-pdf": "daily-pdf-v3",
    "monthly-pdf": "monthly-pdf-v2",
    "milk": "milk-v3",
    "milk-pdf": "milk-pdf-v3",
    "rice": "rice-v1",
    "supply": "supply-v3",
}


def parser_version(kind):
    if kind.startswith(("international-", "colombia-")):
        from .official_sources import VERSION, adapter

        return VERSION + ":" + adapter(kind).VERSION
    return PARSER_VERSIONS.get(kind, "source-v1")


SESSION = requests.Session()
SESSION.headers["User-Agent"] = "AgroAmigo official-data archival importer/1.0"
SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )
    ),
)
LOG = logging.getLogger(__name__)
logging.getLogger("azure").setLevel(logging.WARNING)


class SourceDateMismatch(ValueError):
    """Publisher file date disagrees with its archive link; retain for review."""


def today():
    return datetime.now(ZoneInfo("America/Bogota")).date()


RELEASE_FILES = [
    "pipelines/ingestion/workbook_preview.py",
    "pipelines/ingestion/queue_plan.py",
    "pipelines/ingestion/official_sources.py",
    "pipelines/ingestion/international_sources.py",
    "pipelines/ingestion/colombia_sources.py",
    "pipelines/ingestion/ocr.py",
    "pipelines/ingestion/special_prices.py",
    "pipelines/ingestion/input_references.py",
    "pipelines/ingestion/city_reports.py",
    "pipelines/ingestion/worker.py",
    "pipelines/ingestion/inputs.py",
    "pipelines/ingestion/pdf_sources.py",
    "pipelines/ingestion/supply.py",
    "pipelines/demo/import_data.py",
]
RELEASE_FILES += [
    "pipelines/ingestion/function_app.py",
    "pipelines/ingestion/host.json",
    "pipelines/ingestion/requirements.txt",
]


def release_path(name):
    path = ROOT / name
    # Azure's three host files live at package root.
    return path if path.exists() else ROOT / Path(name).name


def release_fingerprint():
    return hashlib.sha256(
        b"".join(release_path(name).read_bytes() for name in RELEASE_FILES)
    ).hexdigest()


def slug(value):
    return re.sub(
        "[^a-z0-9]+",
        "-",
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode()
        .lower(),
    ).strip("-")


def clean(value):
    return " ".join(str(value or "").split())


def positive(value):
    return (
        isinstance(value, (int, float, Decimal)) and math.isfinite(value) and value > 0
    )


def connect():
    options = dict(
        sslmode="verify-full",
        sslrootcert=certifi.where(),
        connect_timeout=20,
        autocommit=True,
    )
    if os.environ.get("DATABASE_URL"):
        return psycopg.connect(os.environ["DATABASE_URL"], **options)
    c = json.loads((ROOT / ".azure-local/database.json").read_text())
    return psycopg.connect(
        host=c["host"],
        dbname=c["database"],
        user=c["user"],
        password=c["password"],
        **options,
    )


def fetch(url):
    response = SESSION.get(url, timeout=(20, 120))
    response.raise_for_status()
    return response.content


def fetch_asset(db, url, force=False):
    """Revalidate mutable URLs with publisher HTTP validators, then hash bytes."""
    prior = db.execute(
        "SELECT http_etag,http_last_modified,status,document_id FROM ingestion_asset WHERE url=%s",
        (url,),
    ).fetchone()
    headers = {}
    if (
        not force
        and prior
        and prior[2] in ("complete", "archived", "processed")
        and prior[3]
    ):
        if prior[0]:
            headers["If-None-Match"] = prior[0]
        elif prior[1]:
            headers["If-Modified-Since"] = prior[1]
    response = SESSION.get(url, headers=headers, timeout=(20, 120))
    if response.status_code == 304:
        db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (url,))
        return None
    response.raise_for_status()
    db.execute(
        "UPDATE ingestion_asset SET http_etag=%s,http_last_modified=%s WHERE url=%s",
        (response.headers.get("ETag"), response.headers.get("Last-Modified"), url),
    )
    return response.content


def links(url):
    html = fetch(url)
    return [
        (clean(a.get_text(" ", strip=True)), urljoin(url, a["href"]))
        for a in BeautifulSoup(html, "html.parser").select("a[href]")
    ]


def date_from_text(text):
    text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    )
    match = re.search(
        r"(\d{1,2})[\s_-]*(?:de[\s_-]+)?("
        + "|".join(sorted(MONTH_NUM, key=len, reverse=True))
        + r")[\s_-]*(?:de[\s_-]+)?(20\d{2})",
        text,
    )
    if match:
        return date(int(match[3]), MONTH_NUM[match[2]], int(match[1]))
    match = re.search(
        r"("
        + "|".join(sorted(MONTH_NUM, key=len, reverse=True))
        + r")[\s_-]+(\d{1,2})[\s_-]+(20\d{2})",
        text,
    )
    if match:
        return date(int(match[3]), MONTH_NUM[match[1]], int(match[2]))
    return None


def queue(db, url, kind, day=None):
    db.execute(
        "INSERT INTO ingestion_asset(url,kind,observed_on) VALUES(%s,%s,%s) ON CONFLICT(url) DO UPDATE SET kind=excluded.kind,observed_on=coalesce(ingestion_asset.observed_on,excluded.observed_on)",
        (url, kind, day),
    )


def discover_daily(db, url):
    count = 0
    for label, u in links(url):
        path = urlparse(u).path.lower()
        if (
            "/files/" in path
            and path.endswith(".zip")
            and any(x in path for x in ("regional", "ciudad"))
        ):
            day = date_from_text(path) or date_from_text(label)
            if day and day <= today():
                queue(db, u, "city-zip", day)
                count += 1
            continue
        if "/files/" not in path or not path.endswith((".xlsx", ".xls", ".pdf")):
            continue
        if not (
            any(x in path for x in ("diario", "mayoristas_"))
            or re.search(r"/sipsa/(?:bol|anex)_(?:may_)?[a-z]+_\d{1,2}_20\d{2}\.", path)
        ):
            continue
        day = date_from_text(path) or date_from_text(label)
        if day is None or day > today():
            continue
        queue(db, u, "daily" if path.endswith((".xls", ".xlsx")) else "daily-pdf", day)
        count += 1
    if count == 0:
        raise ValueError("No dated daily publications discovered: " + url)
    return count


def publication_month(label, url):
    text = slug(label + " " + Path(urlparse(url).path).name)
    for name in sorted(MONTH_NUM, key=len, reverse=True):
        match = re.search(r"(?:^|-)" + name + r"(?:-?\d{1,2})?-?(20\d{2})(?:-|$)", text)
        if match:
            year = int(match[1])
            month = MONTH_NUM[name]
            return date(year, month, calendar.monthrange(year, month)[1])
    # Human archive labels include "de" between month and year.
    for name in MONTHS:
        match = re.search(name + r"-de-(20\d{2})", text)
        if match:
            year = int(match[1])
            month = MONTH_NUM[name]
            return date(year, month, calendar.monthrange(year, month)[1])
    return None


def discover_input_sources(db):
    found = links(INPUTS)
    archive_url = next(
        u for _, u in found if u.endswith("/componente-insumos-historicos")
    )
    found += links(archive_url)
    for label, u in found:
        path = urlparse(u).path.lower()
        if "/files/" not in path:
            continue
        day = publication_month(label, u)
        if "serieshistoricasmun" in path or "anex-series-historicas-insumos-" in path:
            queue(db, u, "inputs-municipal")
        elif path.endswith(".pdf") and ("insumos" in path) and day:
            queue(db, u, "inputs-pdf", day)
        elif path.endswith((".xlsx", ".xls")) and not "serieshistoricasdep" in path:
            kind = (
                "inputs-annex"
                if any(x in path for x in ("insumosmunicipio", "insumosdepartamento"))
                else "inputs-reference"
            )
            queue(db, u, kind, day)


def discover_special(db):
    root = DAILY.rsplit("/", 1)[0]
    milk = links(root + "/boletin-mensual-precios-de-leche-cruda-en-finca")
    archives = [
        u
        for _, u in milk
        if u.endswith("/boletin-mensual-precios-de-leche-en-finca-historicos")
    ]
    for label, u in (
        links(root) + milk + [entry for u in archives for entry in links(u)]
    ):
        path = urlparse(u).path.lower()
        if "/files/" not in path:
            continue
        if path.endswith((".xlsx", ".xls")) and "arroz" in path:
            queue(db, u, "rice")
        if path.endswith((".xlsx", ".xls")) and "leche" in path:
            queue(db, u, "milk", publication_month(label, u))
        if path.endswith(".pdf") and "leche" in path:
            queue(db, u, "milk-pdf", publication_month(label, u))


def discover_monthly(db):
    found = links(MONTHLY)
    books = [
        u
        for label, u in found
        if u.lower().endswith(".xlsx")
        and ("historica" in u.lower() or "historica" in slug(label))
    ]
    if not books:
        raise ValueError("DANE monthly discovery returned no historical workbooks")
    for u in sorted(set(books)):
        queue(db, u, "monthly")
    archive = next(u for label, u in found if "mensual-sipsa-historicos" in u)
    for label, u in found + links(archive):
        day = publication_month(label, u)
        if u.lower().endswith((".xls", ".xlsx")) and day and "mensual" in u.lower():
            queue(db, u, "monthly-annex", day)
        if (
            u.lower().endswith(".pdf")
            and day
            and any(x in u.lower() for x in ("mensual", "bol-may", "mayoristas"))
        ):
            queue(db, u, "monthly-pdf", day)
        match = re.search(r"/mensual_([a-z]+)_2012\.pdf$", u)
        if match:
            month = MONTH_NUM[match[1]]
            queue(
                db,
                u,
                "monthly-pdf",
                date(2012, month, calendar.monthrange(2012, month)[1]),
            )


def discover_price_daily(db):
    daily_links = links(DAILY)
    for label, u in daily_links:
        if re.search(r"componente-precios-mayoristas-[^/?]+20\d{2}", u):
            match = re.search(r"-(" + "|".join(MONTHS) + r")-de-(20\d{2})", u)
            queue(
                db,
                u,
                "daily-index",
                date(int(match[2]), MONTH_NUM[match[1]], 1) if match else None,
            )
    discover_daily(db, DAILY)


def discover_coffee(db):
    fnc_links = links(FNC)
    queue(
        db,
        next(u for _, u in fnc_links if u.endswith(".xlsx") and "Precios" in u),
        "coffee",
    )
    queue(
        db, next(u for _, u in fnc_links if u.endswith("precio_cafe.pdf")), "coffee-pdf"
    )


def discover_inputs(db):
    discover_input_sources(db)
    input_links = links(INPUTS)
    input_books = [
        u for _, u in input_links if "SeriesHistoricasDep" in u and u.endswith(".xlsx")
    ]
    if not input_books:
        raise ValueError("DANE input history workbook not found")
    for u in input_books:
        queue(db, u, "inputs")


def discover_supply(db):
    for label, u in links(SUPPLY):
        if re.search(r"microdato-abastecimiento-20\d{2}\.xlsx$", u, re.I):
            queue(db, u, "supply")
        elif "Series-historicas-abastecimiento" in u and u.endswith(".xlsx"):
            queue(db, u, "supply-reference")


def discover(db):
    """One unavailable publisher family must not block other queued sources."""
    errors = []
    for name, operation in (
        ("DANE milk/rice", discover_special),
        ("DANE monthly", discover_monthly),
        ("DANE daily/city", discover_price_daily),
        ("FNC", discover_coffee),
        ("DANE inputs", discover_inputs),
        ("DANE supply", discover_supply),
    ):
        try:
            operation(db)
        except psycopg.Error:
            raise
        except Exception as exc:
            message = type(exc).__name__ + ": " + str(exc)
            LOG.error("Discovery failed %s: %s", name, message)
            errors.append({"source": name, "error": message[:500]})
    return errors


def archive(
    db, url, data, kind, day=None, filename=None, parents=None, publisher_override=None
):
    digest = hashlib.sha256(data).hexdigest()
    suffix = Path(filename or urlparse(url).path).suffix.lower()
    official = kind.startswith(("international-", "colombia-"))
    if official and suffix not in (".xlsx", ".xls", ".csv", ".pdf", ".json", ".html"):
        if data.lstrip().startswith(b"%PDF"):
            suffix = ".pdf"
        elif data.lstrip().startswith((b"{", b"[")):
            suffix = ".json"
        elif data[:2] == b"PK":
            suffix = ".xlsx"
        elif b"<html" in data[:1000].lower() or b"<!doctype" in data[:1000].lower():
            suffix = ".html"
        else:
            suffix = ".csv"
        filename = (filename or Path(urlparse(url).path).name or kind) + suffix
    media = {
        ".png": "image/png",
        ".html": "text/html",
        ".csv": "text/csv",
        ".zip": "application/zip",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pdf": "application/pdf",
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")
    if os.environ.get("AzureWebJobsStorage"):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient, ContentSettings

        service = BlobServiceClient.from_connection_string(
            os.environ["AzureWebJobsStorage"]
        )
        blob = service.get_blob_client("source-archive", digest + suffix)
        try:
            blob.upload_blob(
                data,
                overwrite=False,
                metadata={"sha256": digest},
                content_settings=ContentSettings(
                    content_type=media,
                    content_disposition='attachment; filename="agroamigo-'
                    + digest[:12]
                    + suffix
                    + '"',
                ),
            )
        except ResourceExistsError:
            pass
    publisher = (
        "FNC" if kind.startswith("coffee") else "SFC" if kind == "trm" else "DANE"
    )
    if official:
        from .official_sources import publisher as official_publisher

        publisher = official_publisher(kind)
    if publisher_override:
        publisher = publisher_override
    pages = None
    if suffix == ".pdf":
        from pypdf import PdfReader

        pages = len(PdfReader(io.BytesIO(data)).pages)
    db.execute(
        """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
        (
            digest,
            publisher + " - " + Path(filename or urlparse(url).path).name,
            publisher,
            url,
            media,
            "extract" if kind == "ocr-image" else "original",
            str(day or "Serie histórica completa"),
            pages,
            data,
            Jsonb(
                {
                    "ingestion_kind": kind,
                    "retention": "permanent",
                    "original_filename": Path(filename or urlparse(url).path).name,
                    **(
                        {"parents": parents, "archive_entry": filename}
                        if parents
                        else {}
                    ),
                    **({"dataset": "supply", "unit": "kg"} if kind == "supply" else {}),
                }
            ),
        ),
    )
    alias = (
        ("daily-" + str(day) + ("-bulletin" if kind == "daily-pdf" else "-workbook"))
        if kind in ("daily", "daily-pdf")
        else {"coffee": "fnc-workbook", "inputs": "inputs-workbook"}.get(kind)
    )
    if alias:
        db.execute(
            "INSERT INTO document_alias VALUES(%s,%s) ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id",
            (alias, digest),
        )
    return digest


def workbooks(data):
    if data[:2] == b"PK":
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            for sheet in book:
                yield sheet.title, sheet.iter_rows(values_only=True)
        finally:
            book.close()
    else:
        import xlrd

        book = xlrd.open_workbook(file_contents=data)
        for sheet in book.sheets():
            yield (
                sheet.name,
                (
                    [
                        xlrd.xldate_as_datetime(cell.value, book.datemode)
                        if cell.ctype == xlrd.XL_CELL_DATE
                        else cell.value
                        for cell in sheet.row(i)
                    ]
                    for i in range(sheet.nrows)
                ),
            )


def unit_for(name):
    key = slug(name)
    if key.startswith("huevo") or key.startswith("bocadillo"):
        return "unit"
    if key.startswith(("aceite", "jugo", "vinagre")):
        return "litre"
    return "kg"


def record(
    series, day, name, market, unit, price, locator, variation=None, details=None
):
    if day > today():
        raise ValueError("Future observation in source: " + str(day))
    return (
        locator,
        series,
        day,
        clean(name),
        clean(market),
        unit,
        float(price),
        variation,
        details or {},
    )


def parse_monthly(data):
    found = 0
    for sheet, rows in workbooks(data):
        header = None
        for rownum, row in enumerate(rows, 1):
            normalized = [clean(v) for v in row]
            if "Fecha" in normalized and "Producto" in normalized:
                header = {name: i for i, name in enumerate(normalized) if name}
                continue
            if header is None:
                continue

            def get(*names):
                return next(
                    (row[header[name]] for name in names if name in header), None
                )

            d = get("Fecha")
            if not isinstance(d, (date, datetime)):
                continue
            price = get(
                "Precio promedio por kilogramo*",
                "Precio promedio por kilogramo",
                "Precio por kilogramo*",
                "Precio por kilogramo",
                "Precio",
            )
            if price is None:
                raise ValueError(
                    f"Unknown monthly price column: {sheet} {list(header)}"
                )
            if not positive(price):
                continue
            day = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
            if day > today():
                continue  # Unclosed monthly periods are not completed observations.
            name = get("Producto")
            market = get("Mercado", "Fuente")
            if not clean(name) or not clean(market):
                raise ValueError("Missing monthly product/market")
            found += 1
            yield record(
                "dane-monthly",
                day,
                name,
                market,
                unit_for(name),
                price,
                f"{sheet}!row {rownum}",
                details={
                    "category": clean(get("Grupo")),
                    "city": clean(get("Municipio")),
                    "region": clean(get("Departamento")),
                    "unit_note": "SIPSA exceptions: eggs/bocadillo per unit; oil/juice/vinegar per litre.",
                },
            )
    if not found:
        raise ValueError("No monthly price rows parsed")


def parse_daily(data, expected_day):
    found = 0
    for sheet, source in workbooks(data):
        rows = list(source)
        if not rows or not any(clean(v) for row in rows for v in row):
            continue
        heading = " ".join(clean(v) for row in rows[:4] for v in row)
        day = next(
            (
                v.date() if isinstance(v, datetime) else v
                for row in rows[:4]
                for v in row
                if isinstance(v, (date, datetime))
            ),
            None,
        ) or date_from_text(heading)
        if not day:
            raise ValueError("Daily workbook has no verifiable publication date")
        if day != expected_day:
            raise SourceDateMismatch(
                f"Daily link date {expected_day} differs from workbook {day}"
            )
        headers = next(
            (
                i
                for i, r in enumerate(rows[:12])
                if sum(clean(x).lower() == "precio" for x in r) >= 3
            ),
            None,
        )
        if headers is None:
            raise ValueError("Daily price matrix header not found")
        price_columns = [
            i
            for i, value in enumerate(rows[headers])
            if clean(value).lower() == "precio"
        ]
        market_header = next(
            (
                i
                for i, r in enumerate(rows[:headers])
                if r and "precio" in clean(r[0]).lower()
            ),
            headers - 1,
        )
        markets = {
            col: ", ".join(
                dict.fromkeys(
                    clean(rows[i][col])
                    for i in range(market_header, headers)
                    if clean(rows[i][col])
                )
            )
            for col in price_columns
        }
        for rownum, row in enumerate(rows[headers + 1 :], headers + 2):
            name = clean(row[0])
            for col in price_columns:
                if not positive(row[col]):
                    continue
                market = clean(markets[col])
                if not market:
                    raise ValueError("Missing daily market header")
                variation = row[col + 1] if col + 1 < len(row) else None
                variation = (
                    float(variation) * 100
                    if isinstance(variation, (int, float)) and math.isfinite(variation)
                    else None
                )
                found += 1
                yield record(
                    "dane-daily",
                    day,
                    name,
                    market,
                    unit_for(name),
                    row[col],
                    f"{sheet}!row {rownum},col {col + 1}",
                    variation,
                    {"predominant_variety": "*" in name},
                )
    if not found:
        raise ValueError("No daily prices parsed")


def parse_monthly_summary(data, expected_day):
    """Eight-city annex: price matrix plus monthly/YTD/annual variations."""
    observations = {}
    changes = {}
    for sheet, source in workbooks(data):
        rows = list(source)
        heading = " ".join(clean(v) for row in rows[:9] for v in row)
        headers = next(
            (
                i
                for i, r in enumerate(rows[:15])
                if sum(clean(v) == "Precio" for v in r) >= 3
            ),
            None,
        )
        if headers is not None:
            day = publication_month(heading, "")
            if not day or (expected_day and day != expected_day):
                raise SourceDateMismatch("Monthly annex period differs from its link")
            columns = [i for i, v in enumerate(rows[headers]) if clean(v) == "Precio"]
            markets = {i: clean(rows[headers - 1][i]) for i in columns}
            for row_no, row in enumerate(rows[headers + 1 :], headers + 2):
                name = clean(row[0])
                for col in columns:
                    if col >= len(row) or not positive(row[col]):
                        continue
                    market = markets[col]
                    if not market or not name:
                        raise ValueError("Missing monthly summary label")
                    observations[(name, market)] = [
                        f"{sheet}!row {row_no},col {col + 1}",
                        "dane-monthly-summary",
                        day,
                        name,
                        market,
                        unit_for(name),
                        float(row[col]),
                        float(row[col + 1])
                        if isinstance(row[col + 1], (int, float))
                        else None,
                        {"variation_basis": "monthly"},
                    ]
        elif "Variación año corrido" in heading or "Variación anual" in heading:
            field = (
                "year_to_date_percent"
                if "año corrido" in heading
                else "year_over_year_percent"
            )
            h = next(
                (i for i, r in enumerate(rows[:15]) if clean(r[0]) == "Producto"), None
            )
            if h is None:
                continue
            for row in rows[h + 1 :]:
                name = clean(row[0])
                for col, market in enumerate(rows[h][1:], 1):
                    if (
                        clean(market)
                        and col < len(row)
                        and isinstance(row[col], (int, float))
                        and math.isfinite(row[col])
                    ):
                        changes.setdefault((name, clean(market)), {})[field] = row[col]
    if not observations:
        raise ValueError("No monthly annex prices found")
    for key, row in observations.items():
        row[-1].update(changes.get(key, {}))
        yield tuple(row)


def parse_pdf(data, day, monthly=False):
    """Use actual grid-cell ordering, never PDF text-stream city ordering."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        yield from parse_pdf_pages(pdf.pages, day, monthly)


def parse_pdf_pages(pages, day, monthly=False, *, allow_empty=False):
    """Shared literal-cell parser for native PDF grids and verified OCR grids."""
    found = 0
    for page_no, page in enumerate(pages, 1):
        for table_no, table in enumerate(page.extract_tables(), 1):
            market_row = next(
                (
                    i
                    for i, r in enumerate(table[:8])
                    if sum(
                        any(
                            c in clean(v)
                            for c in [
                                "Bogotá",
                                "Medellín",
                                "Barranquilla",
                                "Bucaramanga",
                                "Cúcuta",
                                "Armenia",
                                "Pereira",
                                "Cali",
                            ]
                        )
                        for v in r
                    )
                    >= 3
                ),
                None,
            )
            if market_row is None:
                continue
            header = table[market_row]
            markets = [
                (i, clean(v))
                for i, v in enumerate(header)
                if v
                and any(
                    c in clean(v)
                    for c in [
                        "Bogotá",
                        "Medellín",
                        "Barranquilla",
                        "Bucaramanga",
                        "Cúcuta",
                        "Armenia",
                        "Pereira",
                        "Cali",
                    ]
                )
            ]
            for rownum, row in enumerate(table[market_row + 1 :], market_row + 2):
                name = clean(row[0])
                if not name or name.lower().startswith(
                    ("precio", "variacion", "variación")
                ):
                    continue
                for col, market in markets:
                    if col >= len(row):
                        raise ValueError("PDF matrix width changed")
                    token = clean(row[col])
                    if not re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", token):
                        continue
                    price = float(token.replace(".", "").replace(",", "."))
                    if price <= 0:
                        continue
                    found += 1
                    yield record(
                        "dane-monthly-bulletin" if monthly else "dane-daily",
                        day,
                        name,
                        market,
                        unit_for(name),
                        price,
                        f"PDF page {page_no},table {table_no},row {rownum},col {col + 1}",
                        details={
                            "predominant_variety": "*" in name,
                            "source_header": "Precio por kilogramo; preserve SIPSA unit exceptions",
                        },
                    )
    if not found and not allow_empty:
        raise ValueError(
            "No supported price grids found in PDF; original retained for review"
        )


def parse_coffee(data):
    found = 0
    for sheet, rows in workbooks(data):
        if "Precio Interno Diario" not in sheet:
            continue
        for rownum, row in enumerate(rows, 1):
            if (
                len(row) > 2
                and isinstance(row[1], (date, datetime))
                and positive(row[2])
            ):
                d = row[1].date() if isinstance(row[1], datetime) else row[1]
                if d <= today():
                    found += 1
                    yield record(
                        "fnc-daily",
                        d,
                        "Café pergamino seco",
                        "FNC nacional",
                        "125kg",
                        row[2],
                        f"{sheet}!row {rownum}",
                    )
    if not found:
        raise ValueError("No FNC daily history parsed")


from pipelines.ingestion.inputs import parse_inputs


def save_rows(db, did, rows):
    count = 0
    with db.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE ingestion_stage (LIKE historical_price INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with cur.copy(
            "COPY ingestion_stage(document_id,source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details) FROM STDIN"
        ) as cp:
            for row in rows:
                cp.write_row((did, *row[:-1], Jsonb(row[-1])))
                count += 1
        cur.execute(
            "INSERT INTO historical_price SELECT * FROM ingestion_stage ON CONFLICT DO NOTHING"
        )
    return count


def project(db, did, url, kind):
    """Publish values and their matching immutable evidence in the same transaction."""
    if kind in ("inputs", "inputs-municipal", "inputs-annex", "inputs-pdf"):
        from pipelines.ingestion.inputs import project_inputs

        return project_inputs(db, did)
    if kind in ("milk", "milk-pdf", "rice"):
        from pipelines.ingestion.special_prices import project_special

        return project_special(db, did, url)
    rows = db.execute(
        """SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details
        FROM historical_price WHERE document_id=%s""",
        (did,),
    ).fetchall()
    products = {}
    markets = {}
    prices = {}
    conflicts = set()
    daily = {}
    coffee = {}
    inputs = {}
    for loc, series, d, name, market, unit, price, variation, meta in rows:
        if series == "dane-monthly":
            pid, mid = slug(name), "sipsa-" + slug(market)
            products[pid] = (pid, name, meta.get("category") or "Productos agrícolas")
            markets[mid] = (
                mid,
                market,
                meta.get("city") or market.split(",")[0],
                meta.get("region") or "",
            )
            key = (pid, mid, d, unit)
            if key in prices and prices[key][6] != price:
                conflicts.add(key)
            prices[key] = (
                pid,
                mid,
                "dane-sipsa",
                d,
                "monthly",
                unit,
                price,
                url,
                did,
                loc,
            )
        elif series == "dane-daily":
            key = (d, name, market)
            if key in daily and daily[key][4] != price:
                raise ValueError("Conflicting daily source row: " + str(key))
            daily[key] = (
                d,
                name,
                market,
                None,
                price,
                variation,
                did,
                int(re.search(r"PDF page (\d+)", loc)[1])
                if loc.startswith("PDF page")
                else None,
                loc,
                unit,
            )
        elif series == "fnc-daily":
            coffee[d] = (d, price, url, did)
    with db.cursor() as cur:
        if products:
            cur.executemany(
                "INSERT INTO product(id,name,category) VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                products.values(),
            )
            cur.executemany(
                "INSERT INTO market(id,name,city,region) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                markets.values(),
            )
            cur.executemany(
                """INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id,source_locator)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,source_id,observed_on,period,unit) DO UPDATE SET price=excluded.price,source_url=excluded.source_url,document_id=excluded.document_id,source_locator=excluded.source_locator WHERE (price_observation.price,price_observation.document_id) IS DISTINCT FROM (excluded.price,excluded.document_id)""",
                [v for k, v in prices.items() if k not in conflicts],
            )
        if daily:
            product_ids = {
                x[0] for x in cur.execute("SELECT id FROM product").fetchall()
            }
            daily_values = [
                (
                    d,
                    n,
                    m,
                    slug(n) if "*" not in n and slug(n) in product_ids else None,
                    p,
                    v,
                    doc,
                    page,
                    loc,
                    unit,
                )
                for d, n, m, _, p, v, doc, page, loc, unit in daily.values()
            ]
            cur.executemany(
                """INSERT INTO daily_price(observed_on,product_name,market_name,product_id,price,change_percent,document_id,source_page,source_locator,unit) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(observed_on,product_name,market_name) DO UPDATE SET price=excluded.price,change_percent=excluded.change_percent,document_id=excluded.document_id,source_locator=excluded.source_locator,source_page=excluded.source_page,unit=excluded.unit WHERE (daily_price.price,daily_price.document_id,daily_price.change_percent) IS DISTINCT FROM (excluded.price,excluded.document_id,excluded.change_percent)
                AND ((SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=excluded.document_id)='daily'
                 OR coalesce((SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=daily_price.document_id),'')<>'daily')""",
                daily_values,
            )
        if coffee:
            cur.executemany(
                """INSERT INTO coffee_reference(observed_on,price,source_url,document_id) VALUES(%s,%s,%s,%s) ON CONFLICT(observed_on) DO UPDATE SET price=excluded.price,source_url=excluded.source_url,document_id=excluded.document_id WHERE (coffee_reference.price,coffee_reference.document_id) IS DISTINCT FROM (excluded.price,excluded.document_id)""",
                coffee.values(),
            )
    return len(conflicts)


def process_asset(db, url, kind, day):
    try:
        count = _process_asset(db, url, kind, day)
    except ValueError as exc:
        if not enqueue_failed_workbook(db, url, kind, exc):
            raise
        count = 0
    db.execute(
        "UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
        (parser_version(kind), url),
    )
    return count


def enqueue_failed_workbook(db, url, kind, error):
    """A few native title cells do not prove the image price table was readable."""
    message = str(error)
    failed_layout = message.startswith(
        (
            "No input price rows",
            "No monthly price rows",
            "No daily prices",
            "No monthly annex prices",
            "No FNC daily history",
            "No milk price observations",
            "No rice price observations",
        )
    ) or message in (
        "Daily price matrix header not found",
        "Daily workbook has no verifiable publication date",
    )
    if not failed_layout or isinstance(error, SourceDateMismatch):
        return False
    original = db.execute(
        "SELECT d.id,d.content FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id WHERE a.url=%s",
        (url,),
    ).fetchone()
    if not original or not bytes(original[1]).startswith((b"PK", b"\xd0\xcf\x11\xe0")):
        return False
    from .ocr import scan_document

    scan_document(
        db, bytes(original[1]), original[0], kind, normal_extraction_failed=True
    )
    if not db.execute(
        "SELECT 1 FROM source_ocr_task WHERE document_id=%s LIMIT 1", (original[0],)
    ).fetchone():
        return False
    db.execute(
        "UPDATE ingestion_asset SET status='awaiting-ocr',checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s",
        (message[:1000], url),
    )
    return True


def _process_asset(db, url, kind, day):
    if kind == "daily-index":
        n = discover_daily(db, url)
        db.execute(
            "UPDATE ingestion_asset SET status='complete',processor_version='source-v2',records=%s,checked_at=now(),attempts=attempts+1,error=NULL WHERE url=%s",
            (n, url),
        )
        return n
    version = db.execute(
        "SELECT processor_version FROM ingestion_asset WHERE url=%s", (url,)
    ).fetchone()
    outdated = not version or version[0] != parser_version(kind)
    data = fetch_asset(db, url, force=outdated)
    if data is None:
        return 0
    did = archive(db, url, data, kind, day)
    prior = db.execute(
        "SELECT document_id,status,records FROM ingestion_asset WHERE url=%s", (url,)
    ).fetchone()
    if (
        not outdated
        and prior[0] == did
        and prior[1] in ("complete", "archived", "processed")
        and kind != "coffee-pdf"
        and (
            not kind.endswith("pdf")
            or db.execute(
                "SELECT 1 FROM source_pdf_page WHERE document_id=%s LIMIT 1", (did,)
            ).fetchone()
        )
    ):
        db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (url,))
        return 0
    # Retain the original even when parsing fails; pending also resumes safely
    # after a host interruption before this source's transaction commits.
    db.execute(
        "UPDATE ingestion_asset SET document_id=%s,status='pending',checked_at=NULL WHERE url=%s",
        (did, url),
    )
    if kind.startswith(("international-", "colombia-")):
        from .official_sources import process

        count = process(db, data, did, url, kind)
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,checked_at=now(),attempts=attempts+1,error=NULL WHERE url=%s",
            (did, "awaiting-ocr" if count is None else "complete", count or 0, url),
        )
        return count or 0
    if not kind.endswith("pdf") and kind != "city-zip":
        from .ocr import scan_document

        scan_document(db, data, did, kind)
    if kind == "inputs-reference":
        from pipelines.ingestion.input_references import (
            extract_context,
            extract_reference_rows,
        )

        with db.transaction():
            from itertools import chain

            count = extract_reference_rows(db, data, did, day)
            # Older annex filenames do not encode department/municipality. Let
            # their real headers decide whether they also contain price rows.
            candidates = parse_inputs(data)
            try:
                first = next(candidates)
            except ValueError as exc:
                if str(exc) != "No input price rows parsed":
                    raise
            except StopIteration:
                pass
            else:
                count += save_rows(db, did, chain([first], candidates))
                project(db, did, url, "inputs-annex")
            if not count:
                count = extract_context(db, data, did)
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status='complete',records=%s,checked_at=now(),attempts=attempts+1,error=NULL WHERE url=%s",
            (did, count, url),
        )
        return count
    if kind == "city-zip":
        from pipelines.ingestion.city_reports import publish_city_zip

        count = publish_city_zip(db, data, did, url, day)
        db.execute(
            """INSERT INTO product(id,name,category)
            SELECT DISTINCT ON (r.product_id) r.product_id,r.product_name,coalesce(c.category_path[1],r.category)
            FROM regional_price r JOIN source_archive_member m ON m.document_id=r.document_id
            LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
            WHERE m.archive_id=%s ORDER BY r.product_id,r.observed_on DESC ON CONFLICT DO NOTHING""",
            (did,),
        )
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status='complete',records=(SELECT count(*) FROM regional_price WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)),checked_at=now(),attempts=attempts+1,error=NULL WHERE url=%s",
            (did, did, url),
        )
        return count
    if kind.endswith("pdf"):
        from pipelines.ingestion.pdf_sources import extract_pages

        with db.transaction():
            extract_pages(db, data, did)
    if kind == "supply":
        from pipelines.ingestion.supply import publish_supply

        count = publish_supply(db, data, did)
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status='complete',records=%s,checked_at=now(),attempts=attempts+1,error=NULL WHERE url=%s",
            (did, count, url),
        )
        LOG.info("Imported supply: %s monthly aggregates (%s)", count, url)
        return count
    parser = {
        "monthly": parse_monthly,
        "monthly-annex": lambda b: parse_monthly_summary(b, day),
        "daily": lambda b: parse_daily(b, day),
        "monthly-pdf": lambda b: parse_pdf(b, day, True),
        "coffee": parse_coffee,
        "inputs": parse_inputs,
        "inputs-municipal": parse_inputs,
        "inputs-annex": parse_inputs,
    }.get(kind)
    if kind in ("milk", "rice"):
        from pipelines.ingestion.special_prices import parse_special

        parser = lambda b: parse_special(b, kind, day)
    if kind == "milk-pdf":
        from pipelines.ingestion.special_prices import parse_milk_pdf

        parser = lambda b: parse_milk_pdf(b, day)
    if kind == "daily-pdf":
        parser = lambda b: parse_pdf(b, day)
    if kind == "inputs-pdf":
        from pipelines.ingestion.pdf_sources import parse_input_pdf

        parser = lambda b: parse_input_pdf(b, day)
    if kind == "coffee-pdf":
        refresh_coffee_bulletin(db, data, did, url)
    if kind in ("daily-pdf", "monthly-pdf"):
        from .pdf_sources import PDFOCRPending, parse_archived_price_pdf

        # Queue failed pages outside the publication transaction; an OCR wait
        # must not roll back the retained image/task that will resolve it.
        try:
            pdf_rows = list(parse_archived_price_pdf(db, data, did, day, kind))
        except PDFOCRPending as exc:
            db.execute(
                "UPDATE ingestion_asset SET document_id=%s,status='awaiting-ocr',records=0,checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s",
                (did, str(exc), url),
            )
            return 0
        except ValueError as exc:
            if not str(exc).startswith("No supported price grids"):
                raise
            pdf_rows = []
    with db.transaction():
        if kind in ("daily-pdf", "monthly-pdf"):
            count = save_rows(db, did, pdf_rows) if pdf_rows else 0
        else:
            count = save_rows(db, did, parser(data)) if parser else 0
        if kind in ("inputs", "inputs-municipal", "inputs-annex"):
            from pipelines.ingestion.input_references import extract_reference_rows

            extract_reference_rows(db, data, did, day)
        conflicts = project(db, did, url, kind) if count else 0
        db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s",
            (
                did,
                "complete"
                if count or kind == "coffee-pdf"
                else "processed"
                if kind.endswith("pdf")
                else "archived",
                count,
                "Conflicting source keys retained but excluded from app: "
                + str(conflicts)
                if conflicts
                else None,
                url,
            ),
        )
    if kind == "monthly-annex":
        db.execute(
            "INSERT INTO document_alias VALUES('monthly-summary',%s) ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id WHERE (SELECT reference_period FROM source_document WHERE id=excluded.document_id)>=(SELECT reference_period FROM source_document WHERE id=document_alias.document_id)",
            (did,),
        )
    LOG.info("Imported %s: %s rows (%s)", kind, count, url)
    return count


def refresh_coffee_bulletin(db, data, did, url):
    from pipelines.demo import import_data as legacy

    legacy.TODAY = today()
    legacy.START = today() - timedelta(days=366)
    parse_fnc = legacy.parse_fnc
    # The checked legacy parser validates 13 factors and 16 branch prices.
    workbook = db.execute(
        "SELECT s.content FROM ingestion_asset a JOIN source_document s ON s.id=a.document_id WHERE a.kind='coffee' AND a.status='complete' ORDER BY a.checked_at DESC LIMIT 1"
    ).fetchone()
    if not workbook:
        raise ValueError("FNC workbook must import before bulletin")
    with tempfile.TemporaryDirectory() as tmp:
        excel = Path(tmp) / "fnc.xlsx"
        pdf = Path(tmp) / "fnc.pdf"
        excel.write_bytes(workbook[0])
        pdf.write_bytes(data)
        history, factors, markets, observations = parse_fnc(
            excel, pdf, "https://federaciondecafeteros.org/history.xlsx", url
        )
    # Workbook rows were already imported with their real source URL and locators.
    latest = [r for r in history if r[2] == url]
    with db.transaction():
        with db.cursor() as cur:
            cur.executemany(
                "INSERT INTO market(id,name,city,region) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                markets.values(),
            )
            cur.executemany(
                "INSERT INTO coffee_reference(observed_on,price,source_url,document_id) VALUES(%s,%s,%s,%s) ON CONFLICT(observed_on) DO UPDATE SET price=excluded.price,source_url=excluded.source_url,document_id=excluded.document_id WHERE coffee_reference.document_id IS DISTINCT FROM excluded.document_id",
                [(*r, did) for r in latest],
            )
            cur.executemany(
                "INSERT INTO coffee_factor(observed_on,factor,price,source_url,document_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(observed_on,factor) DO UPDATE SET price=excluded.price,source_url=excluded.source_url,document_id=excluded.document_id WHERE coffee_factor.document_id IS DISTINCT FROM excluded.document_id",
                [(*r, did) for r in factors],
            )
            cur.executemany(
                """INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url,document_id,source_locator) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'PDF page 2; Almacafé') ON CONFLICT(product_id,market_id,source_id,observed_on,period,unit) DO UPDATE SET price=excluded.price,document_id=excluded.document_id WHERE price_observation.document_id IS DISTINCT FROM excluded.document_id""",
                [(*r, did) for r in observations],
            )
            cur.execute(
                "INSERT INTO document_alias VALUES('fnc-price',%s) ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id",
                (did,),
            )


def refresh_trm(db):
    # The official source extends to 1991. First fetch the complete series, then overlap 14 days.
    earliest = db.execute("SELECT min(observed_on) FROM exchange_rate").fetchone()[0]
    start = (
        date(1991, 1, 1)
        if earliest is None or earliest.year > 1991
        else today() - timedelta(days=14)
    )
    url = "https://www.datos.gov.co/resource/32sa-8pi3.json?" + urlencode(
        {
            "$where": f"vigenciadesde >= '{start}T00:00:00' AND vigenciadesde <= '{today()}T23:59:59'",
            "$order": "vigenciadesde ASC",
            "$limit": 50000,
        }
    )
    data = fetch(url)
    rows = json.loads(data)
    if not rows or len(rows) >= 50000:
        raise ValueError("TRM empty response or pagination limit reached")
    did = archive(db, url, data, "trm")
    rates = []
    for r in rows:
        d = date.fromisoformat(r["vigenciadesde"][:10])
        until = date.fromisoformat(r["vigenciahasta"][:10])
        value = float(r["valor"])
        if not positive(value) or until < d or d > today():
            raise ValueError("Invalid TRM row")
        rates.append((d, until, value, url, did))
    with db.transaction():
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO exchange_rate(observed_on,valid_until,price,source_url,document_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(observed_on) DO UPDATE SET price=excluded.price,valid_until=excluded.valid_until,document_id=excluded.document_id WHERE (exchange_rate.price,exchange_rate.valid_until) IS DISTINCT FROM (excluded.price,excluded.valid_until)""",
                rates,
            )
    return len(rates)


def refresh_seasons(db):
    # Rebuild comparable COMPLETE market-years; retained versions preserve changes.
    rows = db.execute(
        "SELECT product_id,market_id,extract(year from observed_on)::int,extract(month from observed_on)::int,price,document_id,source_locator FROM price_observation WHERE source_id='dane-sipsa' AND period='monthly' AND extract(year from observed_on)<%s ORDER BY product_id,market_id,observed_on",
        (today().year,),
    ).fetchall()
    years = defaultdict(dict)
    for pid, mid, year, month, price, did, loc in rows:
        years[(pid, mid, year)][month] = (price, did, loc)
    vals = []
    for (pid, mid, year), months in years.items():
        if len(months) == 12:
            vals.append(
                (
                    pid,
                    mid,
                    year,
                    Jsonb([float(months[m][0]) for m in range(1, 13)]),
                    months[12][1],
                    Jsonb([months[m][2] for m in range(1, 13)]),
                )
            )
    coffee = db.execute(
        "SELECT observed_on,price,document_id FROM coffee_reference WHERE extract(year from observed_on)<%s ORDER BY observed_on",
        (today().year,),
    ).fetchall()
    coffee_years = defaultdict(lambda: defaultdict(list))
    for day, price, did in coffee:
        coffee_years[day.year][day.month].append((float(price) / 125, did))
    for year, months in coffee_years.items():
        if len(months) == 12:
            vals.append(
                (
                    "cafe-pergamino-seco",
                    "fnc-national",
                    year,
                    Jsonb(
                        [
                            sum(v for v, _ in months[m]) / len(months[m])
                            for m in range(1, 13)
                        ]
                    ),
                    months[12][-1][1],
                    Jsonb(
                        [
                            f"FNC daily references for {year}-{m:02d}; {len(months[m])} observations; COP/125kg divided by 125"
                            for m in range(1, 13)
                        ]
                    ),
                )
            )
    with db.transaction():
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO seasonal_year VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,reference_year) DO UPDATE SET monthly_prices=excluded.monthly_prices,document_id=excluded.document_id,source_rows=excluded.source_rows WHERE (seasonal_year.monthly_prices,seasonal_year.document_id) IS DISTINCT FROM (excluded.monthly_prices,excluded.document_id)""",
                vals,
            )


def run(
    mode="daily",
    limit=100,
    time_budget=2100,
    ocr_limit=5,
    ocr_scan_limit=3,
    asset_url=None,
):
    started = time.monotonic()
    ident = uuid.uuid4()
    summary = {"assets": 0, "rows": 0, "errors": []}
    with connect() as db:
        if not db.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
            LOG.info(
                "Another ingestion is active; next scheduled invocation will resume"
            )
            return {"status": "skipped_overlap"}
        db.execute(
            "UPDATE ingestion_run SET status='interrupted',finished_at=now() WHERE status='running'"
        )
        db.execute("INSERT INTO ingestion_run(id,mode) VALUES(%s,%s)", (ident, mode))
        try:
            if mode in ("daily", "discover", "all"):
                summary["errors"].extend(discover(db))
                from .official_sources import discover_roots

                discover_roots(db)
            if asset_url:
                # Operational repair is limited to a registered source. Never
                # fetch an arbitrary URL supplied to the authenticated endpoint.
                candidates = db.execute(
                    "SELECT url,kind,observed_on FROM ingestion_asset WHERE url=%s",
                    (asset_url,),
                ).fetchall()
            elif mode == "discover":
                candidates = []
            elif mode == "daily":
                from .queue_plan import daily_candidates

                candidates = daily_candidates(db, today())
            else:
                from .queue_plan import backfill_candidates

                candidates = backfill_candidates(db, limit)
            # Re-select once after root processing so newly linked price files can
            # be fetched during this daily run, with the same elapsed-time bound.
            remaining_passes = 1 if mode == "daily" else 0
            processed = set()
            index = 0
            while index < len(candidates):
                url, kind, day = candidates[index]
                index += 1
                processed.add(url)
                if time.monotonic() - started > time_budget:
                    summary["time_budget_reached"] = True
                    break
                try:
                    summary["rows"] += process_asset(db, url, kind, day)
                    summary["assets"] += 1
                except Exception as exc:
                    message = type(exc).__name__ + ": " + str(exc)
                    # Source errors only; database connection strings are never logged.
                    LOG.error("Asset failed %s: %s", url, message)
                    summary["errors"].append({"url": url, "error": message[:500]})
                    db.execute(
                        "UPDATE ingestion_asset SET status=%s,attempts=attempts+1,checked_at=now(),error=%s WHERE url=%s",
                        (
                            "review"
                            if isinstance(exc, SourceDateMismatch)
                            else "failed",
                            message[:1000],
                            url,
                        ),
                    )
                    if kind == "daily":
                        # An unavailable or invalid workbook must not prevent
                        # extraction from its available official daily bulletin.
                        db.execute(
                            "UPDATE ingestion_asset SET status='pending',checked_at=NULL WHERE kind='daily-pdf' AND observed_on=%s AND status='archived'",
                            (day,),
                        )
                if index == len(candidates) and remaining_passes:
                    remaining_passes -= 1
                    candidates.extend(
                        row
                        for row in daily_candidates(db, today())
                        if row[0] not in processed
                    )
            if mode in ("daily", "all"):
                summary["trm"] = refresh_trm(db)
                refresh_seasons(db)
            from .ocr import drain

            summary["ocr"] = drain(db, limit=ocr_limit, scan_limit=ocr_scan_limit)
            summary["seconds"] = round(time.monotonic() - started, 1)
            status = "partial" if summary["errors"] else "succeeded"
            db.execute(
                "UPDATE ingestion_run SET status=%s,finished_at=now(),summary=%s WHERE id=%s",
                (status, Jsonb(summary), ident),
            )
            print(
                json.dumps(
                    {"run_id": str(ident), "status": status, **summary}, default=str
                ),
                flush=True,
            )
            if mode == "daily" and summary["errors"]:
                raise RuntimeError(
                    "Daily ingestion has failed assets; see ingestion_run and ingestion_asset"
                )
            return summary
        except Exception as exc:
            db.execute(
                "UPDATE ingestion_run SET status='failed',finished_at=now(),summary=%s WHERE id=%s",
                (Jsonb({**summary, "fatal": type(exc).__name__}), ident),
            )
            raise
        finally:
            db.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["daily", "backfill", "discover", "all"])
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    run(args.mode, args.limit)
