import { NextRequest, NextResponse } from "next/server";
import {
  markets,
  marketDetail,
  inputDetail,
  inputAliases,
  supply,
  mapData,
} from "@/lib/server/explore";
import { normalizeInputLabels, normalizeLabel } from "@/lib/label-normalization";
import { mapPointDisplayName } from "@/lib/input-locations";
import { InputIdentityConflictError, InputIdentityGuardError } from "@/lib/input-identity-equivalence";
export const dynamic = "force-dynamic";
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ resource: string }> },
) {
  const { resource } = await params,
    q = req.nextUrl.searchParams;
  const get = (key: string) => (q.get(key) || "").slice(0, 700);
  try {
    let data;
    if (resource === "markets") data = (await markets()).map((row) => ({ ...row,
      name: normalizeLabel(row.name, "place"),
    }));
    else if (resource === "market") {
      const raw = await marketDetail(get("id"));
      data = raw && { ...raw,
        market: { ...raw.market, name: normalizeLabel(raw.market.name, "place") },
        products: raw.products.map((product) => ({ ...product,
          name: normalizeLabel(product.name, "product"),
          category: normalizeLabel(product.category, "category"),
        })),
      };
    }
    else if (resource === "input")
      data = await inputDetail(
        get("id"),
        get("department"),
        get("scope"),
        get("municipality"),
        get("history") === "all",
      ).then((raw) => raw && ({ ...raw,
        input: normalizeInputLabels(raw.input),
        regions: raw.regions.map(normalizeInputLabels),
        current_quotes: raw.current_quotes.map(normalizeInputLabels),
        history: raw.history.map((point) => ({ ...point,
          sources: point.sources?.map((source) => ({ ...source,
            market_name: normalizeLabel(source.market_name, "place"),
          })),
        })),
      }));
    else if (resource === "input-aliases")
      data = (await inputAliases(
        get("id"),
        get("department"),
        get("scope"),
        get("municipality"),
      )).map((row) => ({ ...row,
        name: normalizeLabel(row.name, "input"),
        department: normalizeLabel(row.department, "place"),
      }));
    else if (resource === "supply")
      data = await supply(
        get("product"),
        get("market"),
        /^\d{4}-\d{2}-01$/.test(get("month")) ? get("month") : "",
        get("history") === "all",
      ).then((raw) => ({ ...raw,
        rows: raw.rows.map((row) => ({ ...row,
          food_name: normalizeLabel(row.food_name, "product"),
          market_name: normalizeLabel(row.market_name, "place"),
        })),
      }));
    else if (resource === "map")
      data = await mapData(get("kind"), get("id"), get("mode"), {
        series: get("series"),
        market: get("market"),
        presentation: get("presentation"),
        units: get("units"),
        history: get("history"),
        region: get("region"),
        scope: get("scope"),
        municipality: get("municipality"),
        category: get("category"),
        query: get("query"),
      }).then((raw) => ({ ...raw,
        points: raw.points.map((point) => ({ ...point,
          name: mapPointDisplayName(get("kind"), point.name,
            point.region || "", point.municipality || ""),
        })),
      }));
    else
      return NextResponse.json(
        { error: "Consulta no disponible." },
        { status: 404 },
      );
    return NextResponse.json(
      data || { error: "No encontramos esta referencia." },
      {
        status: data ? 200 : 404,
        headers: { "Cache-Control": "public, max-age=300" },
      },
    );
  } catch (error) {
    if (error instanceof InputIdentityConflictError || error instanceof InputIdentityGuardError)
      return NextResponse.json({ error: error.message }, { status: 409 });
    return NextResponse.json(
      { error: "No pudimos consultar esta información. Intenta de nuevo." },
      { status: 503 },
    );
  }
}
