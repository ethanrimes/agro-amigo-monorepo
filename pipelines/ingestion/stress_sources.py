"""Replay complete downloaded official fixtures without changing the database.

Run: PYTHONPATH=. .venv/bin/python -m pipelines.ingestion.stress_sources
The report captures real row counts, dates, products, elapsed time and process RSS.
"""

import collections
import hashlib
import json
import resource
import time
import zipfile
from datetime import date

from .city_reports import parse_city_pdf
from .pdf_sources import parse_input_pdf
from .special_prices import parse_milk_pdf, parse_special
from .worker import ROOT, parse_inputs, parse_monthly_summary, publication_month


def main():
    cache = ROOT / "pipelines/ingestion/cache"
    report = []
    files = []
    for p in sorted(cache.glob("*.xlsx")):
        name = p.name.lower()
        if "arroz" in name:
            files.append((p, "rice", lambda b: parse_special(b, "rice")))
        elif "leche" in name or "sipsal" in name:
            day = publication_month("", p.name)
            files.append((p, "milk", lambda b, day=day: parse_special(b, "milk", day)))
        elif any(
            s in name
            for s in (
                "serieshistoricasmun",
                "series-historicas-insumos-2013",
                "insumosmunicipio-jul",
                "insumosdepartamento-jul",
            )
        ):
            files.append((p, "inputs", parse_inputs))
    files.append(
        (ROOT / "pipelines/planning/cache/inputs-history.xlsx", "inputs", parse_inputs)
    )
    files.append(
        (
            cache / "anex-SIPSAMensual-jul2026.xlsx",
            "monthly-annex",
            lambda b: parse_monthly_summary(b, date(2026, 7, 31)),
        )
    )
    for p in cache.glob("insumos*2012.pdf"):
        day = publication_month("", p.name)
        if day is None:
            raise ValueError("Unknown fixture month: " + p.name)
        files.append((p, "inputs-pdf", lambda b, day=day: parse_input_pdf(b, day)))
    for p in cache.glob("*.pdf"):
        if "leche" in p.name.lower():
            day = publication_month("", p.name)
            if day:
                files.append((p, "milk-pdf", lambda b, day=day: parse_milk_pdf(b, day)))
    for path, kind, parser in files:
        if not path.exists():
            continue
        start = time.monotonic()
        data = path.read_bytes()
        count = 0
        products = set()
        categories = collections.Counter()
        earliest = None
        latest = None
        issues = 0
        try:
            for r in parser(data):
                count += 1
                products.add(r[3])
                categories[r[-1].get("category", "")] += 1
                issues += bool(r[-1].get("quality_issue"))
                earliest = min(earliest or r[2], r[2])
                latest = max(latest or r[2], r[2])
                assert r[6] > 0
            item = {
                "file": path.name,
                "kind": kind,
                "rows": count,
                "products": len(products),
                "categories": dict(categories),
                "earliest": earliest,
                "latest": latest,
                "quality_issues": issues,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            assert count > 0
        except Exception as exc:
            rejection = type(exc).__name__ + ": " + str(exc)
            # This exact official December URL repeats November's identical bytes.
            # The test must reject it; the correctly dated December PDF fills it.
            expected = (
                path.name == "Anexo-SipsaLeche_dic_2020.xlsx"
                and hashlib.sha256(data).hexdigest()
                == "bc9e16af972eac40d3cb876c494d38581f61927e52b8a18f645e5ee5c0447c69"
                and type(exc).__name__ == "SourceDateMismatch"
            )
            item = {
                "file": path.name,
                "expected_rejection" if expected else "error": rejection,
            }
        item.update(
            seconds=round(time.monotonic() - start, 2),
            peak_rss_mb=round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 1
            ),
        )
        report.append(item)
        print(json.dumps(item, default=str), flush=True)
    with zipfile.ZipFile(cache / "cities-2026-09-07.zip") as z:
        for name in z.namelist():
            if not name.lower().endswith(".pdf"):
                continue
            rows = list(parse_city_pdf(z.read(name), date(2026, 9, 7)))
            assert rows and all(0 < r[11] <= r[12] for r in rows)
            if "barranquillita" in name.lower():
                lemon = next(r for r in rows if r[3] == "Limón tahití")
                assert lemon[7] == 24 and lemon[11:13] == (85000, 87000)
                assert lemon[5].casefold() == "frutas > cítricos"
                mora = [r for r in rows if r[3] == "Mora de castilla"]
                assert {(r[7], r[11], r[12]) for r in mora} == {
                    (2.5, 20000, 22000),
                    (12.5, 79000, 80000),
                }
            report.append(
                {
                    "file": name,
                    "kind": "city-pdf",
                    "rows": len(rows),
                    "earliest": min(r[1] for r in rows),
                    "latest": max(r[1] for r in rows),
                }
            )
    output = ROOT / "artifacts/extraction-stress-report.json"
    output.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2))
    errors = [r for r in report if r.get("error")]
    print(
        "Completed",
        len(report),
        "files;",
        sum(r.get("rows", 0) for r in report),
        "rows;",
        len(errors),
        "errors",
        flush=True,
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
