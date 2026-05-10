"""
Diff two canonical-entity snapshots produced by dump_canonical_entities.py
and produce, per dim_* table:

  - new.tsv: rows present only in `after` (newly created canonical entities)
  - dedup_candidates.txt: groups of canonical names that normalize to the same
    key, where at least one member is new in `after` and at least one other
    member exists in either snapshot. Each group is a hint for a human dedup
    decision.

Usage:
    python scripts/diff_canonical_snapshots.py /tmp/dedup-before /tmp/dedup-after /tmp/dedup-diff
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_doubled(s: str) -> bool:
    if len(s) < 4:
        return False
    pairs = sum(1 for i in range(0, len(s) - 1, 2) if s[i] == s[i + 1])
    return pairs >= len(s) * 0.3


def undouble(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        out.append(s[i])
        if i + 1 < len(s) and s[i] == s[i + 1]:
            i += 2
        else:
            i += 1
    return "".join(out)


def norm_key(s: str) -> str:
    if not s:
        return ""
    if is_doubled(s):
        s = undouble(s)
    s = strip_accents(s.strip()).lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_tsv(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        header = next(f).rstrip("\n").split("\t")
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 2:
                continue
            rows.append(dict(zip(header, cols)))
    return rows


def diff_table(name: str, before: Path, after: Path, out_dir: Path) -> dict:
    before_rows = load_tsv(before / f"{name}.tsv")
    after_rows = load_tsv(after / f"{name}.tsv")

    before_ids = {r["id"]: r for r in before_rows}
    after_ids = {r["id"]: r for r in after_rows}

    new_ids = set(after_ids) - set(before_ids)
    new_rows = [after_ids[i] for i in sorted(new_ids, key=lambda x: after_ids[x]["canonical_name"])]

    # Write new.tsv
    new_path = out_dir / f"{name}__new.tsv"
    with new_path.open("w", encoding="utf-8") as f:
        if after_rows:
            cols = list(after_rows[0].keys())
            f.write("\t".join(cols) + "\n")
            for r in new_rows:
                f.write("\t".join(r[c] for c in cols) + "\n")

    # Build dedup-candidate groups: for each new row, find existing rows
    # (in before OR after-not-new) whose canonical_name normalizes to the
    # same key.
    existing_by_key = defaultdict(list)
    for r in after_rows:
        if r["id"] not in new_ids:
            existing_by_key[norm_key(r["canonical_name"])].append(r)

    new_by_key = defaultdict(list)
    for r in new_rows:
        new_by_key[norm_key(r["canonical_name"])].append(r)

    cand_path = out_dir / f"{name}__dedup_candidates.txt"
    n_groups = 0
    n_new_with_match = 0
    n_new_with_new_match = 0
    with cand_path.open("w", encoding="utf-8") as f:
        f.write(f"# {name}: dedup candidates\n")
        f.write(f"# {len(new_rows)} new rows; {len(after_rows)} total\n\n")

        # Groups: new + at least one existing (potential merge into existing)
        f.write("## NEW + EXISTING (likely merge into existing)\n")
        for k in sorted(new_by_key):
            if not k:
                continue
            existing_members = existing_by_key.get(k, [])
            new_members = new_by_key[k]
            if not existing_members:
                continue
            n_groups += 1
            n_new_with_match += len(new_members)
            f.write(f"\n# key={k!r}\n")
            for m in existing_members:
                tot = m.get("cnt_total", "?")
                f.write(f"  EXISTING [{tot:>10}]  {m['canonical_name']!r}  ({m['id']})\n")
            for m in new_members:
                tot = m.get("cnt_total", "?")
                f.write(f"  NEW      [{tot:>10}]  {m['canonical_name']!r}  ({m['id']})\n")

        # Groups: 2+ new with same key (collisions among newly created)
        f.write("\n\n## NEW + NEW (multiple new rows with same normalized key)\n")
        for k in sorted(new_by_key):
            if not k:
                continue
            new_members = new_by_key[k]
            if len(new_members) <= 1:
                continue
            if existing_by_key.get(k):
                continue  # already covered above
            n_new_with_new_match += len(new_members)
            f.write(f"\n# key={k!r}\n")
            for m in new_members:
                tot = m.get("cnt_total", "?")
                f.write(f"  NEW      [{tot:>10}]  {m['canonical_name']!r}  ({m['id']})\n")

    return {
        "table": name,
        "before_count": len(before_rows),
        "after_count": len(after_rows),
        "new_count": len(new_rows),
        "groups_new_with_existing": n_groups,
        "new_with_match_count": n_new_with_match,
        "new_with_new_match_count": n_new_with_new_match,
    }


def main(before: str, after: str, out_dir: str) -> int:
    bp = Path(before)
    ap = Path(after)
    op = Path(out_dir)
    op.mkdir(parents=True, exist_ok=True)

    DIMS = [
        "dim_category", "dim_subcategory", "dim_product",
        "dim_presentation", "dim_units",
        "dim_department", "dim_city", "dim_market",
        "dim_insumo", "dim_insumo_grupo", "dim_insumo_subgrupo",
        "dim_casa_comercial",
    ]

    summary = []
    for d in DIMS:
        s = diff_table(d, bp, ap, op)
        summary.append(s)

    print("\nSummary of changes:")
    print(f"{'table':25}  {'before':>7}  {'after':>7}  {'new':>5}  {'NEW+EXISTING':>13}  {'NEW+NEW':>8}")
    for s in summary:
        print(f"{s['table']:25}  {s['before_count']:>7}  {s['after_count']:>7}  "
              f"{s['new_count']:>5}  {s['new_with_match_count']:>13}  {s['new_with_new_match_count']:>8}")

    print(f"\nDiff files written to: {op}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scripts/diff_canonical_snapshots.py <before> <after> <out_dir>")
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
