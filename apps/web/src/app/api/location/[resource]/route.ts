import { NextRequest, NextResponse } from "next/server";
import {
  spatialLayer,
  spatialLayers,
  spatialPoint,
  forecastGrid,
  monthFilter,
} from "@/lib/server/location";
import { inColombia } from "@/lib/location-types";
export const dynamic = "force-dynamic";
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ resource: string }> },
) {
  try {
    const { resource } = await params,
      q = req.nextUrl.searchParams;
    if (resource === "layers")
      return NextResponse.json(await spatialLayers(), {
        headers: { "Cache-Control": "public, max-age=3600" },
      });
    if (resource === "grid" || resource === "point") {
      const latitude = Number(q.get("lat")),
        longitude = Number(q.get("lon"));
      if (
        !q.has("lat") ||
        !q.has("lon") ||
        !inColombia({ latitude, longitude })
      )
        return NextResponse.json(
          { error: "Selecciona un punto en Colombia." },
          { status: 400 },
        );
      if (resource === "grid") {
        const step = Number(q.get("step"));
        if (![0.25, 0.5, 1, 2, 4].includes(step))
          return NextResponse.json(
            { error: "Escala de mapa inválida." },
            { status: 400 },
          );
        return NextResponse.json(
          await forecastGrid(latitude, longitude, step),
          { headers: { "Cache-Control": "public, max-age=300" } },
        );
      }
      const layer = await spatialLayer(q.get("layer") || ""),
        month = Number(q.get("month") || "1");
      if (!layer || !Number.isInteger(month) || month < 1 || month > 12)
        return NextResponse.json(
          { error: "Capa o mes inválido." },
          { status: 400 },
        );
      return NextResponse.json(
        await spatialPoint(layer, latitude, longitude, month),
        { headers: { "Cache-Control": "public, max-age=3600" } },
      );
    }
    if (resource === "tile") {
      const layer = await spatialLayer(q.get("layer") || ""),
        month = Number(q.get("month") || "1"),
        bbox = (q.get("bbox") || "").split(",").map(Number);
      if (
        !layer ||
        !Number.isInteger(month) ||
        month < 1 ||
        month > 12 ||
        bbox.length !== 4 ||
        !bbox.every((n) => Number.isFinite(n) && Math.abs(n) <= 40075017) ||
        bbox[0] >= bbox[2] ||
        bbox[1] >= bbox[3]
      )
        return new Response(null, { status: 400 });
      const url = new URL(layer.service + "/export");
      url.search = new URLSearchParams({
        f: "image",
        bbox: bbox.join(","),
        bboxSR: "3857",
        imageSR: "3857",
        size: "256,256",
        format: "png32",
        transparent: "true",
        layers: "show:" + layer.layer,
        layerDefs: JSON.stringify({ [layer.layer]: monthFilter(layer, month) }),
      }).toString();
      const image = await fetch(url, {
        signal: AbortSignal.timeout(25000),
        next: { revalidate: 86400 },
      });
      if (!image.ok || !image.headers.get("content-type")?.includes("image/"))
        return new Response(null, { status: 502 });
      return new Response(image.body, {
        headers: {
          "Content-Type": "image/png",
          "Cache-Control": "public, max-age=86400",
          "X-Map-Source": layer.publisher,
        },
      });
    }
    return NextResponse.json(
      { error: "Consulta no encontrada." },
      { status: 404 },
    );
  } catch {
    return NextResponse.json(
      {
        error:
          "No pudimos consultar esta capa. Intenta nuevamente; la cobertura depende de la fuente.",
      },
      { status: 503 },
    );
  }
}
