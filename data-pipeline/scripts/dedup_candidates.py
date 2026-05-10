"""
Print candidate duplicate pairs from a TSV of canonical names.

This is NOT a dedup script — it makes no decisions. It groups rows whose
canonical_name maps to the same normalized key (lowercase, no accents,
collapsed whitespace, no punctuation, doubled-character collapse) so a human
can then read the candidates and decide what's actually a duplicate.

Usage:
    python scripts/dedup_candidates.py /tmp/dedup/dim_insumo.tsv > pairs.txt
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict


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


def main(path: str) -> int:
    rows = []
    with open(path, encoding="utf-8") as f:
        header = next(f).rstrip("\n").split("\t")
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if not cols or len(cols) < 2:
                continue
            rows.append(cols)

    name_idx = header.index("canonical_name")
    total_idx = header.index("cnt_total") if "cnt_total" in header else None

    groups = defaultdict(list)
    for r in rows:
        k = norm_key(r[name_idx])
        if not k:
            continue
        groups[k].append(r)

    n_groups = 0
    for k, members in sorted(groups.items()):
        if len(members) <= 1:
            continue
        n_groups += 1
        print(f"\n# {k}")
        for m in sorted(members, key=lambda r: -int(r[total_idx]) if total_idx else 0):
            n = m[total_idx] if total_idx else "?"
            print(f"  [{n:>10}]  {m[name_idx]}  ({m[0]})")

    print(f"\n# {n_groups} candidate dup groups across {sum(len(g) for g in groups.values() if len(g)>1)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
