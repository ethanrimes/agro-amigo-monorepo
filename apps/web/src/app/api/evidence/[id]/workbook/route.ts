import { NextRequest, NextResponse } from "next/server";
import { database } from "@/lib/server/db";

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const id = (await params).id;
  if (!/^[a-f0-9]{64}$/.test(id)) return NextResponse.json({ error: "Archivo no encontrado." }, { status: 404 });
  try {
    const found = await database().query("SELECT 1 FROM source_document WHERE id=$1 AND (publisher IN ('DANE','FNC') OR metadata->>'ingestion_kind' LIKE 'international-%' OR metadata->>'ingestion_kind' LIKE 'colombia-%') AND media_type IN ('application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')", [id]);
    if (!found.rowCount) return NextResponse.json({ error: "Archivo no encontrado." }, { status: 404 });
    const query = new URLSearchParams({ sheet: (req.nextUrl.searchParams.get("sheet") || "").slice(0,31), start: String(Math.max(1, Math.min(1048576, Number(req.nextUrl.searchParams.get("start")) || 1))), limit: "100" });
    const base = process.env.SOURCE_WORKBOOK_API_URL || "https://agroamigo-data-9a04.azurewebsites.net";
    const response = await fetch(`${base}/api/workbook/${id}?${query}`, { signal: AbortSignal.timeout(45000), next: { revalidate: 86400 } });
    if (!response.ok) throw new Error("Workbook preview unavailable");
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff" } });
  } catch {
    return NextResponse.json({ error: "No pudimos abrir esta hoja. Intenta de nuevo o descarga el original." }, { status: 503 });
  }
}
