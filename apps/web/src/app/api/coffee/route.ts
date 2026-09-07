import { NextResponse } from "next/server";
import { coffee } from "@/lib/server/queries";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const data = await coffee();
    return NextResponse.json(
      data ?? { error: "Todavía no hay precios de café disponibles." },
      {
        status: data ? 200 : 404,
        headers: { "Cache-Control": "public, s-maxage=300" },
      },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar el precio del café. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
