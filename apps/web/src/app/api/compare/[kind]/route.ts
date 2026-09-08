import { NextRequest, NextResponse } from "next/server";
import { comparison } from "@/lib/server/comparisons";
export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ kind: string }> },
) {
  const { kind } = await params;
  if (kind !== "markets" && kind !== "inputs")
    return NextResponse.json(
      { error: "Comparación no disponible." },
      { status: 404 },
    );
  const query = Object.fromEntries(
    [...request.nextUrl.searchParams].map(([key, value]) => [
      key,
      value.slice(0, 700),
    ]),
  );
  try {
    return NextResponse.json(await comparison(kind, query), {
      headers: { "Cache-Control": "public, max-age=300" },
    });
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar la comparación. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
