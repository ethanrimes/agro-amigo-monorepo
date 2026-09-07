import { NextRequest, NextResponse } from "next/server";
import { productDetail } from "@/lib/server/queries";
export const dynamic = "force-dynamic";
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const data = await productDetail(
      id.slice(0, 120),
      (request.nextUrl.searchParams.get("region") || "").slice(0, 100),
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
