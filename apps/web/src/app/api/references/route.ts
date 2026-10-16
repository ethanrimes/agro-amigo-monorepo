import { NextRequest, NextResponse } from "next/server";
import { officialReferences } from "@/lib/server/official-references";
import { isWeeklyCapitalizationConflict } from "@/lib/server/weekly-capitalization-continuity";
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
  } catch (error) {
    if (isWeeklyCapitalizationConflict(error)) {
      const code = typeof error === "object" && error !== null && "message" in error &&
        typeof error.message === "string" ? error.message : "WEEKLY_CAPITALIZATION_SOURCE_CONFLICT";
      return NextResponse.json({
        error: "Encontramos precios oficiales incompatibles para una misma semana. Revisa las fuentes originales antes de comparar o promediar.",
        code,
      }, { status: 409 });
    }
    return NextResponse.json(
      { error: "No pudimos consultar las referencias. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
