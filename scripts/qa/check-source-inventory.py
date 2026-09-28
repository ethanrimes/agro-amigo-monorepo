#!/usr/bin/env python3
"""Fail on undocumented ingestion kinds without importing code or opening DBs."""

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/private/qa/APP_SOURCE_INVENTORY_2026-09-27.md"


def registry_keys(path, variable):
    tree = ast.parse(path.read_text())
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == variable
            for target in statement.targets
        ):
            continue
        value = statement.value
        if isinstance(value, ast.Dict):
            return {ast.literal_eval(key) for key in value.keys}
        # The weekly publisher registry uses a literal, single-generator mapping.
        if (
            isinstance(value, ast.DictComp)
            and len(value.generators) == 1
            and not value.generators[0].ifs
            and isinstance(value.key, ast.Name)
            and isinstance(value.generators[0].target, ast.Name)
            and value.key.id == value.generators[0].target.id
        ):
            return set(ast.literal_eval(value.generators[0].iter))
        raise ValueError(f"Unsupported registry declaration: {path.name}:{variable}")
    raise ValueError(f"Missing registry: {path.name}:{variable}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document", type=Path, default=DOCUMENT,
        help="Local source inventory; internal QA documents are intentionally not tracked",
    )
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    if not args.document.is_file():
        parser.error(f"Private source inventory not found: {args.document}; supply --document PATH")
    document = args.document.read_text()
    rows = {}
    for line in document.splitlines():
        match = re.match(r"\| `([^`]+)` /", line)
        if match:
            if match[1] in rows:
                raise ValueError(f"Duplicate source kind: {match[1]}")
            rows[match[1]] = line
    required = registry_keys(ROOT / "pipelines/ingestion/worker.py", "PARSER_VERSIONS")
    for name in ("colombia_sources", "international_sources", "coffee_sources", "dane_weekly"):
        required |= registry_keys(ROOT / f"pipelines/ingestion/{name}.py", "PUBLISHERS")
    required |= {"city-pdf", "coffee", "coffee-pdf", "trm", "ocr-image"}
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text())
        required |= {row["kind"] for row in snapshot["asset_kinds"]}
        required |= {
            row["ingestion_kind"] for row in snapshot["document_families"]
            # Collector labels genuinely absent legacy metadata explicitly;
            # these are inventoried by publisher/type/format, not a parser kind.
            if row["ingestion_kind"] not in (None, "", "(legacy or other)")
        }
    missing = sorted(required - rows.keys())
    incomplete = sorted(kind for kind, row in rows.items() if "**OCR:** " not in row)
    references = json.loads((ROOT / "pipelines/planning/reference-downloads.json").read_text())
    omitted_references = sorted(name for name, url in references.items() if url not in document)
    layers = json.loads((ROOT / "pipelines/spatial/layers.json").read_text())
    omitted_layers = sorted(
        layer["id"] for layer in layers
        if f"{layer['service']}/{layer['layer']}" not in document
    )
    if missing or incomplete or omitted_references or omitted_layers:
        raise SystemExit(
            f"Inventory incomplete: missing={missing}; missing OCR contract={incomplete}; "
            f"missing planning references={omitted_references}; missing spatial layers={omitted_layers}"
        )
    print(f"PASS: {len(rows)} documented kinds; {len(required)} required by registries/snapshot; explicit OCR contract for each")


if __name__ == "__main__":
    main()
