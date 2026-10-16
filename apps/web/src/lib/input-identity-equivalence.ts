import groups from "../../../../shared/input-identity-equivalences.json";

export type InputIdentityRow = {
  id: string;
  name: string;
  category: string;
  presentation: string;
  brand?: string | null;
  registration?: string | null;
  product_line?: string | null;
  department?: string;
  municipality?: string;
  observed_on?: string;
  price?: number;
  document_id?: string;
  source_locator?: string;
  [key: string]: unknown;
};

type IdentityGroup = (typeof groups.groups)[number];

function normalized(value: unknown): string {
  return String(value ?? "").normalize("NFC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");
}

function groupForId(id: string): IdentityGroup | undefined {
  return groups.groups.find((group) => group.members.some((member) => member.id === id));
}

function rowMatches(group: IdentityGroup, row: InputIdentityRow): boolean {
  const member = group.members.find((candidate) => candidate.id === row.id);
  return Boolean(member && member.names.some((name) => normalized(name) === normalized(row.name)) &&
    normalized(row.category) === normalized(group.guard.category) &&
    normalized(row.presentation) === normalized(group.guard.presentation) &&
    normalized(row.brand) === normalized(group.guard.brand) &&
    normalized(row.registration) === normalized(group.guard.registration) &&
    normalized(row.product_line) === normalized(group.guard.product_line));
}

function acceptedMemberGroup(row: InputIdentityRow): IdentityGroup | undefined {
  const sourceId = String(row.source_input_id || row.id);
  const group = groupForId(sourceId);
  if (!group) return undefined;
  return rowMatches(group, { ...row, id: sourceId, name: String(row.source_name || row.name) })
    ? group : undefined;
}

export type ResolvedInputIdentity = {
  canonicalId: string;
  canonicalName: string;
  memberIds: string[];
  equivalent: boolean;
  accepted: boolean;
};

export type InputIdentityEvidenceQuote = {
  price?: number;
  observed_on?: string;
  document_id?: string;
  source_locator?: string;
  source_input_id?: string;
  source_name?: string;
};

export function resolveInputIdentity(id: string, row?: InputIdentityRow): ResolvedInputIdentity {
  const group = groupForId(id);
  if (!group) return { canonicalId: id, canonicalName: row?.name || "", memberIds: [id], equivalent: false, accepted: true };
  const accepted = row ? rowMatches(group, row) : true;
  return {
    canonicalId: accepted ? group.canonical_id : id,
    canonicalName: accepted ? group.canonical_name : row?.name || "",
    memberIds: group.members.map((member) => member.id),
    equivalent: accepted,
    accepted,
  };
}

export function canonicalizeInputRow<T extends InputIdentityRow>(row: T): T & {
  source_input_id?: string;
  source_name?: string;
} {
  const resolved = resolveInputIdentity(row.id, row);
  if (!resolved.equivalent) return row;
  return {
    ...row,
    id: resolved.canonicalId,
    name: resolved.canonicalName,
    source_input_id: String(row.source_input_id || row.id),
    source_name: String(row.source_name || row.name),
  };
}

export function canonicalizeInputRows<T extends InputIdentityRow>(rows: T[]) {
  return rows.map((row) => canonicalizeInputRow(row));
}

/** Read every exact member ID and annotate accepted rows through one shared path. */
export async function readEquivalentInputRows<T extends InputIdentityRow>(
  requestedId: string,
  read: (memberIds: string[]) => Promise<T[]>,
): Promise<Array<T & { source_input_id?: string; source_name?: string }>> {
  const identity = resolveInputIdentity(requestedId);
  const rows = await read(identity.memberIds);
  assertInputIdentityMembers(rows, identity.memberIds);
  return canonicalizeInputRows(rows);
}

export class InputIdentityGuardError extends Error {
  constructor() {
    super("La referencia contiene datos incompatibles con la identidad del insumo seleccionado.");
    this.name = "InputIdentityGuardError";
  }
}

export function assertInputIdentityMembers<T extends InputIdentityRow>(rows: T[], memberIds: string[]): void {
  const selectedGroups = new Set(memberIds.map((id) => groupForId(id)?.canonical_id).filter(Boolean));
  if (!selectedGroups.size) return;
  for (const row of rows) {
    const group = groupForId(row.id);
    if (group && selectedGroups.has(group.canonical_id) && !rowMatches(group, row))
      throw new InputIdentityGuardError();
  }
}

export class InputIdentityConflictError extends Error {
  constructor() {
    super("Hay precios distintos para la misma fecha y ubicación de este insumo.");
    this.name = "InputIdentityConflictError";
  }
}

function locationKey(row: InputIdentityRow): string {
  return JSON.stringify([
    normalized(row.department),
    normalized(row.municipality),
  ]);
}

/** Keep only the latest equivalent observation per location, preserving all conflicting prices. */
export function latestEquivalentInputRows<T extends InputIdentityRow>(rows: T[]): T[] {
  const result: T[] = [];
  const grouped = new Map<string, T[]>();
  for (const row of canonicalizeInputRows(rows)) {
    const key = JSON.stringify([row.id, locationKey(row)]);
    grouped.set(key, [...(grouped.get(key) || []), row]);
  }
  for (const groupRows of grouped.values()) {
    const latestDate = groupRows.reduce((latest, row) =>
      (row.observed_on || "") > latest ? row.observed_on || "" : latest, "");
    const latest = groupRows.filter((row) => row.observed_on === latestDate);
    const first = latest[0];
    const memberGroup = first ? acceptedMemberGroup(first) : undefined;
    if (!memberGroup) {
      result.push(latest.sort((a, b) => Number(a.price || 0) - Number(b.price || 0))[0]);
      continue;
    }
    // Distinct same-day prices are not candidates for a deterministic winner.
    result.push(...latest);
  }
  return result;
}

export function inputLocationOptions<T extends InputIdentityRow>(rows: T[]): Array<T & {
  identity_conflict?: boolean;
  identity_conflict_quotes?: InputIdentityEvidenceQuote[];
}> {
  const grouped = new Map<string, T[]>();
  for (const row of latestEquivalentInputRows(rows)) {
    const key = JSON.stringify([row.id, locationKey(row)]);
    grouped.set(key, [...(grouped.get(key) || []), row]);
  }
  return [...grouped.values()].map((quotes) => {
    if (quotes.length < 2) return quotes[0];
    const first = quotes[0];
    const prices = new Set(quotes.map((row) => Number(row.price)));
    return {
      ...first,
      identity_conflict: prices.size > 1,
      identity_conflict_quotes: quotes.map((row) => ({ price: row.price,
        observed_on: row.observed_on, document_id: row.document_id,
        source_locator: row.source_locator, source_input_id: row.source_input_id,
        source_name: row.source_name })),
    };
  });
}

/** One catalog row per group, unless latest source rows conflict; then mark every value. */
export function canonicalInputCatalogRows<T extends InputIdentityRow>(rows: T[]): Array<T & {
  identity_conflict?: boolean;
  identity_conflict_quotes?: InputIdentityEvidenceQuote[];
}> {
  const canonical = canonicalizeInputRows(rows);
  const byIdentity = new Map<string, typeof canonical>();
  for (const row of canonical) byIdentity.set(row.id, [...(byIdentity.get(row.id) || []), row]);
  const output: Array<T & {
    identity_conflict?: boolean;
    identity_conflict_quotes?: InputIdentityEvidenceQuote[];
  }> = [];
  for (const [id, identityRows] of byIdentity) {
    const group = identityRows[0] ? acceptedMemberGroup(identityRows[0]) : undefined;
    if (!group) {
      output.push(...identityRows);
      continue;
    }
    const latestDate = identityRows.reduce((latest, row) =>
      (row.observed_on || "") > latest ? row.observed_on || "" : latest, "");
    const latest = identityRows.filter((row) => row.observed_on === latestDate);
    const prices = new Set(latest.map((row) => Number(row.price)));
    const first = latest[0];
    if (!first) continue;
    if (prices.size > 1) {
      const quotes = latest.map((row) => ({ price: row.price, observed_on: row.observed_on,
        document_id: row.document_id, source_locator: row.source_locator,
        source_input_id: row.source_input_id, source_name: row.source_name }));
      output.push({ ...first, identity_conflict: true, identity_conflict_quotes: quotes });
    } else {
      output.push({ ...first, identity_conflict_quotes: latest.map((row) => ({
        price: row.price, observed_on: row.observed_on, document_id: row.document_id,
        source_locator: row.source_locator, source_input_id: row.source_input_id, source_name: row.source_name,
      })) });
    }
  }
  return output;
}

/** Comparison arithmetic cannot choose between different same-day equivalent quotes. */
export function assertNoLatestInputIdentityConflicts<T extends InputIdentityRow>(rows: T[]): void {
  const current = latestEquivalentInputRows(rows);
  const groupKeys = new Set<string>();
  for (const row of current) {
    if (!row.source_input_id) continue;
    const group = groupForId(String(row.source_input_id));
    if (!group) continue;
    const key = JSON.stringify([row.id, locationKey(row), row.observed_on]);
    groupKeys.add(key);
  }
  for (const key of groupKeys) {
    const matching = current.filter((row) => JSON.stringify([row.id, locationKey(row), row.observed_on]) === key);
    if (new Set(matching.map((row) => Number(row.price))).size > 1) throw new InputIdentityConflictError();
  }
}
