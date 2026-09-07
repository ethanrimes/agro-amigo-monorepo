import { NextRequest, NextResponse } from "next/server";
import { catalog } from "@/lib/server/queries";
export const dynamic = "force-dynamic";
export async function GET(request: NextRequest) {
  try {
    return NextResponse.json(
      await catalog(
        (request.nextUrl.searchParams.get("region") || "").slice(0, 100),
      ),
      {
        headers: {
          "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
        },
      },
    );
  } catch {
    return NextResponse.json(
      {
        error:
          "No pudimos consultar los precios. Intenta de nuevo en un momento.",
      },
      { status: 503 },
    );
  }
}
