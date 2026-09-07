import { NextRequest, NextResponse } from "next/server";
import {
  markets,
  marketDetail,
  inputDetail,
  supply,
  mapData,
} from "@/lib/server/explore";
export const dynamic = "force-dynamic";
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ resource: string }> },
) {
  const { resource } = await params,
    q = req.nextUrl.searchParams;
  const get = (key: string) => (q.get(key) || "").slice(0, 220);
  try {
    let data;
    if (resource === "markets") data = await markets();
    else if (resource === "market") data = await marketDetail(get("id"));
    else if (resource === "input")
      data = await inputDetail(get("id"), get("department"));
    else if (resource === "supply")
      data = await supply(
        get("product"),
        get("market"),
        /^\d{4}-\d{2}-01$/.test(get("month")) ? get("month") : "",
      );
    else if (resource === "map")
      data = await mapData(get("kind"), get("id"), get("mode"));
    else
      return NextResponse.json(
        { error: "Consulta no disponible." },
        { status: 404 },
      );
    return NextResponse.json(
      data || { error: "No encontramos esta referencia." },
      {
        status: data ? 200 : 404,
        headers: { "Cache-Control": "public, max-age=300" },
      },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar esta información. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
