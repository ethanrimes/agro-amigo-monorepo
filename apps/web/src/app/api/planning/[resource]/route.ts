import { NextRequest, NextResponse } from "next/server";
import { database } from "@/lib/server/db";
import {
  farmData,
  inputs,
  municipalities,
  seasonality,
  weatherFor,
} from "@/lib/server/planning";
export const dynamic = "force-dynamic";
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ resource: string }> },
) {
  const { resource } = await params,
    q = req.nextUrl.searchParams;
  try {
    let result;
    if (resource === "municipalities") result = await municipalities();
    else if (resource === "farm")
      result = await farmData((q.get("id") || "").slice(0, 5));
    else if (resource === "seasonality")
      result = await seasonality(
        (q.get("product") || "").slice(0, 180),
        (q.get("market") || "").slice(0, 200),
      );
    else if (resource === "inputs")
      result = await inputs((q.get("department") || "").slice(0, 100));
    else if (resource === "weather") {
      if (!q.has("lat") || !q.has("lon"))
        return NextResponse.json(
          { error: "Selecciona una ubicación." },
          { status: 400 },
        );
      const lat = Number(q.get("lat")),
        lon = Number(q.get("lon"));
      if (
        !Number.isFinite(lat) ||
        !Number.isFinite(lon) ||
        lat < -5 ||
        lat > 14 ||
        lon < -82 ||
        lon > -66
      )
        return NextResponse.json(
          { error: "La ubicación debe estar en Colombia." },
          { status: 400 },
        );
      result = await weatherFor(lat, lon);
    } else if (resource === "daily")
      result = (
        await database().query(
          "SELECT * FROM daily_price WHERE observed_on=(SELECT max(observed_on) FROM daily_price WHERE observed_on>((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date-interval '12 months') AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date) ORDER BY product_name,market_name",
        )
      ).rows;
    else if (resource === "library")
      result = (
        await database().query(
          `SELECT a.alias,d.id,d.title,d.publisher,d.reference_period,d.kind,d.media_type FROM document_alias a JOIN source_document d ON d.id=a.document_id WHERE a.alias NOT LIKE 'price-%' ORDER BY d.publisher,d.title`,
        )
      ).rows;
    else
      return NextResponse.json(
        { error: "Consulta no disponible." },
        { status: 404 },
      );
    if (!result)
      return NextResponse.json(
        { error: "No encontramos datos para esta ubicación." },
        { status: 404 },
      );
    return NextResponse.json(result, {
      headers: {
        "Cache-Control":
          resource === "weather"
            ? "private, max-age=300"
            : "public, max-age=300",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error:
          resource === "weather"
            ? "No pudimos consultar el clima. Intenta nuevamente; no mostraremos un pronóstico inventado."
            : "No pudimos consultar esta información. Intenta nuevamente.",
      },
      { status: 503 },
    );
  }
}
