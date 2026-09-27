import { NextRequest, NextResponse } from "next/server";
import { unifiedCatalog } from "@/lib/server/catalog";
import { paginateCatalog } from "@/lib/catalog-page";
import type { CatalogPageRequest } from "@/lib/catalog-types";
export const dynamic = "force-dynamic";

const unavailable = () => NextResponse.json(
  { error: "No pudimos consultar los precios. Intenta de nuevo en un momento." },
  { status: 503 },
);

function pageRequest(value: unknown): CatalogPageRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("INVALID_QUERY");
  const raw = value as Record<string, unknown>;
  const result: CatalogPageRequest = {};
  for (const [key, max] of [["region", 100], ["q", 250], ["category", 200], ["currency", 10]] as const) {
    if (raw[key] !== undefined && (typeof raw[key] !== "string" || raw[key].length > max)) throw new Error("INVALID_QUERY");
    result[key] = typeof raw[key] === "string" ? raw[key] : "";
  }
  for (const key of ["offset", "limit"] as const) {
    if (raw[key] !== undefined && (!Number.isSafeInteger(raw[key]) || Number(raw[key]) < 0)) throw new Error("INVALID_QUERY");
    if (raw[key] !== undefined) result[key] = Number(raw[key]);
  }
  if (raw.saved !== undefined) {
    if (!Array.isArray(raw.saved) || raw.saved.length > 5000 || raw.saved.some((key) => typeof key !== "string" || key.length > 300)) throw new Error("INVALID_QUERY");
    result.saved = raw.saved;
  }
  return result;
}

export async function GET(request: NextRequest) {
  try {
    const query = request.nextUrl.searchParams;
    const catalog = await unifiedCatalog((query.get("region") || "").slice(0, 100), query.get("view") === "canonical");
    return NextResponse.json(catalog, {
      headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
    });
  } catch {
    return unavailable();
  }
}

/** Read-only pagination uses a body so large saved lists never enter URL logs. */
export async function POST(request: NextRequest) {
  let selection: CatalogPageRequest;
  try {
    const body = await request.text();
    if (body.length > 1_000_000) throw new Error("INVALID_QUERY");
    selection = pageRequest(JSON.parse(body));
  } catch {
    return NextResponse.json({ error: "Los filtros de productos no son válidos." }, { status: 400 });
  }
  try {
    const catalog = await unifiedCatalog(selection.region || "");
    return NextResponse.json(paginateCatalog(catalog, selection), {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return unavailable();
  }
}
