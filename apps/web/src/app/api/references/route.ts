import { NextRequest, NextResponse } from "next/server";
import { officialReferences } from "@/lib/server/official-references";
export const dynamic = "force-dynamic";
export async function GET(req: NextRequest) {
  try {
    const result = await officialReferences(req.nextUrl.searchParams);
    return NextResponse.json(
      result || { error: "No encontramos esta referencia." },
      {
        status: result ? 200 : 404,
        headers: { "Cache-Control": "public,max-age=300" },
      },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar las referencias. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
