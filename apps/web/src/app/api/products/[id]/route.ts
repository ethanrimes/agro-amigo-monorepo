import { NextRequest, NextResponse } from "next/server";
import { filteredProduct } from "@/lib/server/price-quotes";
import { productDetailFailureEvent } from "@/lib/server/product-detail-diagnostics";
export const dynamic = "force-dynamic";
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const started = performance.now();
  let id = "";
  let region = "";
  let filters: Record<string, string> = {};
  try {
    const q = request.nextUrl.searchParams;
    region = (q.get("region") || "").slice(0, 100);
    filters = Object.fromEntries(
      (["series", "market", "presentation", "units", "history"] as const)
        .map((key) => [key, (q.get(key) || "").slice(0, 250)]),
    );
    id = (await params).id.slice(0, 120);
    const data = await filteredProduct(
      id,
      region,
      filters,
    );
    return NextResponse.json(
      data ?? { error: "No encontramos este producto." },
      { status: data ? 200 : 404 },
    );
  } catch (error) {
    console.error(JSON.stringify(productDetailFailureEvent(
      error, id, { ...filters, region }, performance.now() - started,
    )));
    return NextResponse.json(
      { error: "No pudimos consultar este producto. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
