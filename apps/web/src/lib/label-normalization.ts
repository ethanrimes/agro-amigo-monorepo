import lexicon from "../../../../shared/label-normalization.json";

export type LabelDomain = "product" | "input" | "category" | "presentation" | "place";

/** Remove only invisible extraction artifacts; retain punctuation and ñ. */
function hygiene(value: string): string {
  return value.normalize("NFC").replace(/[\u00ad\u200b\ufeff]/g, "")
    .replace(/[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/gu, " ")
    .replace(/^ +| +$/g, "").normalize("NFC");
}

/** Case and accent-insensitive lookup, limited to Spanish vowel variants. */
function key(value: string): string {
  return hygiene(value).toLowerCase().replace(/[áéíóúü]/gu, (v) => ({
    á: "a", é: "e", í: "i", ó: "o", ú: "u", ü: "u",
  })[v]!);
}

function slug(value: string): string {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/gu, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

const domains = ["product", "category", "presentation", "place"] as const;
const aliases: Partial<Record<(typeof domains)[number], Record<string, string>>> = lexicon.aliases;
type SourceScopedProductDisplayRule = {
  document_id: string; source_locator: string; product_id: string;
  source_product: string; raw: string; canonical: string;
};
const canonical = new Map<Exclude<LabelDomain, "input">, Map<string, string>>();
for (const domain of domains) {
  const labels = new Map<string, string>();
  for (const label of lexicon.domains[domain]) {
    const normalized = hygiene(label);
    const lookup = key(normalized);
    if (!lookup || (labels.has(lookup) && labels.get(lookup) !== normalized))
      throw new Error(`Ambiguous ${domain} label normalization`);
    labels.set(lookup, normalized);
  }
  for (const [alias, target] of Object.entries(aliases[domain] ?? {})) {
    const lookup = key(alias);
    if (!lookup || hygiene(alias) !== alias || labels.get(key(target)) !== target
      || (labels.has(lookup) && labels.get(lookup) !== target))
      throw new Error(`Unreviewed or ambiguous ${domain} label alias`);
    labels.set(lookup, target);
  }
  if (domain === "product") for (const entry of lexicon.product_display_only) {
    const lookup = key(entry.raw);
    if (!lookup || hygiene(entry.raw) !== entry.raw
      || hygiene(entry.canonical) !== entry.canonical
      || lookup !== key(entry.canonical)
      || slug(entry.raw) !== entry.product_id
      || slug(entry.canonical) !== entry.product_id
      || (labels.has(lookup) && labels.get(lookup) !== entry.canonical))
      throw new Error("Unreviewed or identity-changing product display label");
    labels.set(lookup, entry.canonical);
  }
  canonical.set(domain, labels);
}

const sourceScopedRules = lexicon.source_scoped_product_display_only as SourceScopedProductDisplayRule[];
const sourceScopedSelectors = new Set<string>();
for (const rule of sourceScopedRules) {
  const selector = JSON.stringify([rule.document_id, rule.source_locator, rule.product_id,
    rule.raw, rule.source_product]);
  if (!/^[a-f0-9]{64}$/.test(rule.document_id) || !rule.source_locator || !rule.product_id ||
      !rule.raw || !rule.source_product || !rule.canonical ||
      canonical.get("product")?.get(key(rule.canonical)) !== rule.canonical ||
      key(rule.raw) !== key(rule.source_product) || slug(rule.raw) !== rule.product_id ||
      sourceScopedSelectors.has(selector))
    throw new Error("Unreviewed, duplicate or ambiguous source-scoped product display rule");
  sourceScopedSelectors.add(selector);
}

type OfficialLabelRow = {
  document_id?: unknown; source_locator?: unknown; product_id?: unknown;
  product_name: string; details?: unknown;
};

function sourceProductLiteral(row: OfficialLabelRow): unknown {
  const details = row.details && typeof row.details === "object"
    ? row.details as Record<string, unknown> : {};
  const identity = details.identity_dimensions && typeof details.identity_dimensions === "object"
    ? details.identity_dimensions as Record<string, unknown> : {};
  return identity.source_product;
}

function sourceScopedProductName(row: OfficialLabelRow): string {
  const sourceProduct = sourceProductLiteral(row);
  const matches = sourceScopedRules.filter((rule) => row.document_id === rule.document_id &&
    row.source_locator === rule.source_locator && row.product_id === rule.product_id &&
    row.product_name === rule.raw && sourceProduct === rule.source_product);
  if (matches.length > 1)
    throw new Error("Ambiguous source-scoped product display match");
  return matches[0]?.canonical ?? row.product_name;
}

/** Search both the displayed spelling and exact raw source title. */
export function officialProductSearchNames(row: OfficialLabelRow): string[] {
  const sourceProduct = sourceProductLiteral(row);
  return [...new Set([row.product_name, sourceScopedProductName(row),
    ...(typeof sourceProduct === "string" ? [sourceProduct] : [])])];
}

/** Display spelling only. Never use this result to build a source or quote ID. */
export function normalizeLabel(value: string, domain: LabelDomain): string {
  const cleaned = hygiene(value);
  if (domain === "input") return cleaned;
  if (domain === "category" && cleaned.includes(" > "))
    return cleaned.split(" > ").map((part) =>
      canonical.get("category")?.get(key(part)) ?? part).join(" > ");
  return canonical.get(domain)?.get(key(cleaned)) ?? cleaned;
}

/** Copy only display fields. Raw publication details and identity are retained. */
export function normalizeOfficialLabels<T extends {
  product_name: string; category: string; market: string; department?: string;
}>(row: T): T {
  return { ...row,
    product_name: normalizeLabel(sourceScopedProductName(row), "product"),
    category: normalizeLabel(row.category, "category"),
    market: normalizeLabel(row.market, "place"),
    ...(row.department ? { department: normalizeLabel(row.department, "place") } : {}),
  };
}

export function normalizeInputLabels<T extends {
  name: string; category: string; presentation: string;
  department: string; municipality: string;
}>(row: T): T {
  return { ...row,
    name: normalizeLabel(row.name, "input"),
    category: normalizeLabel(row.category, "category"),
    // Presentation and municipality are exact selector values returned to
    // this API; changing them could redirect a later price/history read.
    department: normalizeLabel(row.department, "place"),
  };
}
