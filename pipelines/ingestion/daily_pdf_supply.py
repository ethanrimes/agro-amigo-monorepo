"""Printed SIPSA daily bulletin market totals, kept separate from supply microdata."""

import io
import re
from datetime import date, timedelta

import pdfplumber

from .supply_summaries import KIND, publish_rows

__all__ = ["parse", "publish_rows"]

VERSION = "supply-daily-pdf-summary-v1"
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
MONTH_NAMES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _lines(words):
    lines = []
    for word in words:
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 1.5:
            lines.append([word])
        else:
            lines[-1].append(word)
    return lines


def _date_headers(words):
    """Recover literal day-month headings, including a day wrapped above its month."""
    headings = [w for w in words if re.fullmatch(r"\d{1,2}-[a-z]{3}\.", w["text"].lower())]
    for day in (w for w in words if re.fullmatch(r"\d{1,2}-", w["text"])):
        months = [w for w in words if re.fullmatch(r"[a-z]{3}\.", w["text"].lower())
                  and 0 < w["top"] - day["top"] < 16
                  and abs((w["x0"] + w["x1"] - day["x0"] - day["x1"]) / 2) < 8]
        if len(months) != 1:
            raise ValueError("Daily PDF supply wrapped date header is ambiguous")
        month = months[0]
        headings.append({"text": day["text"] + month["text"], "x0": min(day["x0"], month["x0"]),
                         "x1": max(day["x1"], month["x1"]), "top": month["top"]})
    return sorted(headings, key=lambda w: w["x0"])


def _validate_totals(rows, first_day):
    for day in (first_day + timedelta(days=i) for i in range(8)):
        dated = [row for row in rows if row["observed_on"] == day]
        totals = [row for row in dated if row["name"] == "Total"]
        markets = [row for row in dated if row["name"] != "Total"]
        if len(totals) != 1 or len(markets) != 32:
            raise ValueError("Daily PDF supply market table is incomplete")
        total = totals[0]["details"]["quantity_tonnes"]
        if total is None or abs(sum(row["details"]["quantity_tonnes"] or 0 for row in markets) - total) > 16:
            raise ValueError("Daily PDF supply market totals conflict with printed total")


def parse(data, expected_day=None):
    """Parse only the proven eight-date, two-page Cuadro 1 native layout.

    A recognized but damaged table raises rather than publishing partial rows.
    Unknown bulletin layouts return [] and retain their original PDF.
    """
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        matching = [
            (number, page, page.extract_text() or "")
            for number, page in enumerate(pdf.pages, 1)
            if "Cuadro 1. Abastecimiento de alimentos que ingresó a los mercados mayoristas" in (page.extract_text() or "")
        ]
        if len(matching) != 1:
            return []
        start_number, first_page, text = matching[0]
        caption = re.search(
            r"Cuadro 1\. Abastecimiento de alimentos que ingresó a los mercados mayoristas del "
            r"(\d{1,2}) (?:al (\d{1,2})\s+de|de ([a-záéíóúñ]+) y el (\d{1,2})\s+de)\s*"
            r"([a-záéíóúñ]+) de (20\d{2}) \(toneladas\)\*",
            text,
        )
        if not caption or caption[5].lower() not in MONTH_NAMES or start_number >= len(pdf.pages):
            return []
        last_year = int(caption[6])
        last_month = MONTH_NAMES[caption[5].lower()]
        first_month = MONTH_NAMES.get((caption[3] or caption[5]).lower())
        if first_month is None:
            return []
        first_day = date(last_year - (first_month > last_month), first_month, int(caption[1]))
        last_day = date(last_year, last_month, int(caption[2] or caption[4]))
        if (last_day - first_day).days != 7 or (expected_day and last_day > expected_day):
            raise ValueError("Daily PDF supply caption conflicts with archive day or eight-date layout")
        pages = [(start_number, first_page), (start_number + 1, pdf.pages[start_number])]
        out, market_names, total_count = [], set(), 0
        for page_number, page in pages:
            words = page.extract_words()
            lines = _lines(words)
            dates = _date_headers(words)
            if len(dates) != 8:
                raise ValueError("Daily PDF supply header lacks eight literal dates")
            parsed_days = []
            for word in dates:
                day, mon = word["text"].lower().rstrip(".").split("-")
                month = MONTHS.get(mon)
                if month is None:
                    raise ValueError("Daily PDF supply date header has an unknown month")
                parsed_days.append(date(last_year - (month > last_month), month, int(day)))
            if parsed_days != [first_day + timedelta(days=i) for i in range(8)]:
                raise ValueError("Daily PDF supply column dates disagree with caption")
            weekday_words = [
                w for w in words
                if re.fullmatch(r"(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)p?", w["text"].lower())
                and min(d["top"] for d in dates) - 30 <= w["top"] < min(d["top"] for d in dates) - 5
            ]
            weekday_names = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
            headers = []
            for index, heading in enumerate(dates):
                matches = [w for w in weekday_words if abs((w["x0"] + w["x1"]) / 2 - (heading["x0"] + heading["x1"]) / 2) <= 20]
                if len(matches) != 1 or matches[0]["text"].lower().removesuffix("p") != weekday_names[parsed_days[index].weekday()]:
                    raise ValueError("Daily PDF supply weekday/provisional header is ambiguous")
                headers.append(matches[0]["text"])
            edges = [w["x1"] for w in dates]
            body_start = max(w["top"] for w in dates) + 4
            footer = next((line for line in lines if " ".join(w["text"] for w in line).startswith("Fuente: DANE-SIPSA")), None)
            if page_number == start_number + 1 and not footer:
                raise ValueError("Daily PDF supply continuation lacks DANE source footer")
            body_end = footer[0]["top"] if footer else page.height - 20
            for line in lines:
                y = line[0]["top"]
                if not body_start <= y < body_end:
                    continue
                label_words = [w for w in line if w["x0"] < 205]
                value_words = [w for w in line if 205 <= w["x0"] < 500]
                if not label_words:
                    continue
                name = " ".join(w["text"] for w in label_words)
                if not value_words or name.startswith("COM-"):
                    continue
                if name != "Total" and (name in market_names or "," not in name and "(" not in name):
                    raise ValueError("Daily PDF supply market label is missing or repeated")
                if name == "Total":
                    total_count += 1
                else:
                    market_names.add(name)
                amounts = [None] * 8
                literals = [None] * 8
                for word in value_words:
                    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*|\d+", word["text"]):
                        raise ValueError("Daily PDF supply contains non-tonnage table token")
                    index = min(range(8), key=lambda i: abs(word["x1"] - edges[i]))
                    if abs(word["x1"] - edges[index]) > 13 or amounts[index] is not None:
                        raise ValueError("Daily PDF supply tonnage crosses or repeats a date column")
                    amounts[index] = int(word["text"].replace(".", ""))
                    literals[index] = word["text"]
                for index, amount in enumerate(amounts):
                    out.append({
                        "source_locator": f"PDF page {page_number}, row y{y:.2f}, column {index + 1}; {VERSION}",
                        "kind": KIND,
                        "observed_on": parsed_days[index],
                        "name": name,
                        "category": "Abastecimiento diario — totales de mercado",
                        "details": {
                            "statistic": "daily_market_arrivals",
                            "quantity_tonnes": amount,
                            "unit": "t",
                            "source_unit": "toneladas",
                            "literal_value": literals[index],
                            "availability": "not_reported" if amount is None else "reported",
                            "aggregation_level": "reported_markets_total" if name == "Total" else "market_total",
                            "provisional": True if headers[index].lower().endswith("p") else None,
                            "provisional_mark": "p" if headers[index].lower().endswith("p") else None,
                            "non_additive": True,
                            "extraction_method": "native-pdf-printed-table",
                            "precision": "printed_rounded_tonnes",
                            "parser_version": VERSION,
                            "source_page": page_number,
                            "row_y": round(y, 2),
                            "column": index + 1,
                            "date_header": dates[index]["text"],
                            "weekday_header": headers[index],
                            "coverage_caption": caption[0],
                            "period_start": first_day.isoformat(),
                            "period_end": last_day.isoformat(),
                        },
                    })
        if total_count != 1 or len(market_names) != 32 or len(out) != 264:
            raise ValueError("Daily PDF supply market table is incomplete")
        _validate_totals(out, first_day)
        continuation = pages[-1][1].extract_text() or ""
        if "(p) Información provisional" not in continuation:
            raise ValueError("Daily PDF supply provisional note is absent")
        return out
