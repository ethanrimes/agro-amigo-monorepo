import { NextRequest, NextResponse } from "next/server";
import { filteredProduct } from "@/lib/server/price-quotes";
export const dynamic = "force-dynamic";
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const q=request.nextUrl.searchParams;
    const data = await filteredProduct(
      id.slice(0, 120),
      (request.nextUrl.searchParams.get("region") || "").slice(0, 100),
      Object.fromEntries(['series','market','presentation','units','history'].map(k=>[k,(q.get(k)||'').slice(0,250)])),
    );
    return NextResponse.json(
      data ?? { error: "No encontramos este producto." },
      { status: data ? 200 : 404 },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar este producto. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
