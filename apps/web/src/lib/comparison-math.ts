import type {
  ComparisonQuote,
  ComparisonRow,
  ComparisonSummary,
} from "./comparison-types";

/** Commercial identity and price basis must match before any arithmetic. */
export function quoteIdentity(q: ComparisonQuote): string {
  const label = (value: string) =>
    value.normalize("NFC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");
  return JSON.stringify([
    q.id,
    label(q.presentation),
    label(q.units),
    q.unit,
    q.series,
    label(q.brand || ""),
    label(q.registration || ""),
    label(q.product_line || ""),
  ]);
}

export function compareQuotes(
  a: ComparisonQuote[],
  b: ComparisonQuote[],
  sameDate: boolean,
  includeSources = false,
  national = false,
): ComparisonRow[] {
  const latest = (quotes: ComparisonQuote[]) => {
    const found = new Map<string, ComparisonQuote>();
    for (const q of quotes) {
      const key = JSON.stringify([quoteIdentity(q), q.location_id]);
      const previous = found.get(key);
      if (!previous || q.date > previous.date) found.set(key, q);
    }
    return [...found.values()];
  };
  const references = new Map<string, ComparisonQuote[]>();
  for (const q of latest(b)) {
    const key = quoteIdentity(q);
    references.set(key, [...(references.get(key) || []), q]);
  }
  return latest(a).map((q) => {
    const key = quoteIdentity(q);
    let matches = (references.get(key) || []).filter(
      (r) => r.price > 0 && (!sameDate || r.date === q.date),
    );
    if (national && !matches.some((r) => r.location_id !== q.location_id))
      matches = [];
    const dates = matches.map((r) => r.date).sort();
    const price = matches.length
      ? matches.reduce((sum, r) => sum + r.price, 0) / matches.length
      : null;
    return {
      key,
      a: q,
      b:
        price === null
          ? null
          : {
              price,
              date_from: dates[0],
              date_to: dates.at(-1)!,
              location_count: matches.length,
              ...(includeSources || matches.length === 1
                ? { sources: matches }
                : {}),
            },
      difference: price === null ? null : price - q.price,
      percent:
        price === null || q.price <= 0
          ? null
          : ((price - q.price) / q.price) * 100,
    };
  });
}

export function summarizeComparisons(rows: ComparisonRow[]) {
  const matched = rows.filter((r) => r.percent !== null);
  const groups = new Map<
    string,
    { category: string; subcategory: string | null; values: number[] }
  >();
  for (const r of matched) {
    const category =
      r.a.category_path[0] || r.a.category || "Sin clasificación";
    const subcategory = r.a.category_path.slice(1).join(" > ") || null;
    for (const sub of subcategory ? [null, subcategory] : [null]) {
      const key = JSON.stringify([category, sub]);
      const group = groups.get(key) || {
        category,
        subcategory: sub,
        values: [],
      };
      group.values.push(r.percent!);
      groups.set(key, group);
    }
  }
  const summaries: ComparisonSummary[] = [...groups.values()]
    .map((g) => ({
      category: g.category,
      subcategory: g.subcategory,
      count: g.values.length,
      percent: g.values.reduce((a, b) => a + b, 0) / g.values.length,
    }))
    .sort(
      (a, b) =>
        a.category.localeCompare(b.category, "es") ||
        (a.subcategory || "").localeCompare(b.subcategory || "", "es"),
    );
  return {
    matched: matched.length,
    unmatched: rows.length - matched.length,
    percent: matched.length
      ? matched.reduce((sum, r) => sum + r.percent!, 0) / matched.length
      : null,
    summaries,
  };
}
