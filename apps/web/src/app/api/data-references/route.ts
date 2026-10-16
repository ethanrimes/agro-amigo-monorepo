import { NextRequest, NextResponse } from "next/server";
import { database } from "@/lib/server/db";
import { normalizeLabel } from "@/lib/label-normalization";
import { categoryOptions, categoryVariants, displayDetails } from "@/lib/data-reference-labels";
import { fold } from "@/lib/planning-math";
import { sqlSearchFold } from "@/lib/server/sql-search-fold";
export const dynamic = "force-dynamic";
export async function GET(req: NextRequest) {
  try {
    const q = req.nextUrl.searchParams,
      kind = ["summary", "electricity", "wholesale"].includes(
        q.get("kind") || "",
      )
        ? q.get("kind")!
        : "summary",
      search = fold((q.get("q") || "").slice(0, 150)).replace(/[\\%_]/g, "\\$&"),
      category = (q.get("category") || "").slice(0, 180),
      page = Math.max(0, Number(q.get("page")) || 0),
      db = database();
    const verifiedWholesale = `h.series='dane-monthly-summary'
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=h.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=h.observed_on))`;
    const base =
      kind === "wholesale"
        ? `SELECT h.document_id,h.source_locator,h.observed_on,h.product_name AS name,'Productos mayoristas'::text category,jsonb_build_object('Producto',h.product_name,'Ciudad',h.market_name,'Precio (COP)',h.price,'Unidad',h.unit,'Variación (%)',h.change_percent) AS details FROM published_historical_price h WHERE ${verifiedWholesale}`
        : `SELECT document_id,source_locator,observed_on,name,category,details FROM input_reference_row WHERE kind=$1`;
    const bind = kind === "wholesale" ? [] : [kind];
    // A distinct scan of the full monthly series exceeds the database statement
    // limit. Ordered LIMIT seeks stop after the first eligible published row;
    // aggregating MAX over the publication view scans the full monthly series.
    const options = (
      await db.query(
        kind === "wholesale"
          ? `WITH RECURSIVE dates(observed_on) AS (
              (SELECT h.observed_on FROM published_historical_price h
                WHERE ${verifiedWholesale} AND h.observed_on<=CURRENT_DATE
                ORDER BY h.observed_on DESC LIMIT 1)
              UNION ALL
              SELECT (SELECT h.observed_on FROM published_historical_price h
                WHERE ${verifiedWholesale} AND h.observed_on<dates.observed_on
                ORDER BY h.observed_on DESC LIMIT 1)
              FROM dates WHERE dates.observed_on IS NOT NULL
            ) SELECT observed_on,'Productos mayoristas'::text category
              FROM dates WHERE observed_on IS NOT NULL ORDER BY observed_on DESC`
          : `WITH facts AS (${base}) SELECT DISTINCT observed_on,category FROM facts WHERE observed_on<=CURRENT_DATE ORDER BY observed_on DESC,category`,
        bind,
      )
    ).rows;
    const dates = [...new Set(options.map((x) => x.observed_on))],
      day = dates.includes(q.get("date")) ? q.get("date") : dates[0] || null;
    if (!day)
      return NextResponse.json({
        rows: [],
        total: 0,
        dates: [],
        categories: [],
        date: null,
        kind,
        page,
      });
    const rawCategories = options.map((x) => x.category as string),
      variants = categoryVariants(rawCategories, category),
      pos = bind.length,
      filter = `observed_on=$${pos + 1} AND ($${pos + 2}='' OR ${sqlSearchFold("name")} ILIKE '%' || $${pos + 2} || '%' ESCAPE '\\') AND ($${pos + 3}='' OR category=ANY($${pos + 4}::text[]))`;
    const args = [...bind, day, search, category, variants];
    const canonical = `WITH facts AS (${base}), latest AS (SELECT DISTINCT ON(f.name,f.category,coalesce(f.details->>'Estrato',f.details->>'Ciudad',''),coalesce(f.details->>'Unidad','')) f.* FROM facts f JOIN source_document d ON d.id=f.document_id WHERE ${filter} ORDER BY f.name,f.category,coalesce(f.details->>'Estrato',f.details->>'Ciudad',''),coalesce(f.details->>'Unidad',''),d.retrieved_at DESC,f.document_id,f.source_locator)`;
    const rows = (
      await db.query(
        `${canonical} SELECT * FROM latest ORDER BY name,category,coalesce(details->>'Estrato',details->>'Ciudad',''),coalesce(details->>'Unidad',''),document_id,source_locator LIMIT 60 OFFSET $${pos + 5}`,
        [...args, page * 60],
      )
    ).rows;
    const count = (
      await db.query(`${canonical} SELECT count(*) FROM latest`, args)
    ).rows[0].count;
    return NextResponse.json(
      {
        rows: rows.map((row) => ({ ...row,
          name: normalizeLabel(row.name, kind === "wholesale" ? "product" : "input"),
          category: normalizeLabel(row.category, "category"),
          details: displayDetails(row.details, kind),
        })),
        total: Number(count),
        dates,
        categories: categoryOptions(rawCategories),
        date: day,
        kind,
        page,
      },
      { headers: { "Cache-Control": "public,max-age=300" } },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos consultar el resumen de la fuente." },
      { status: 503 },
    );
  }
}
