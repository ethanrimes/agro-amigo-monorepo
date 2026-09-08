import { NextRequest, NextResponse } from "next/server";
import { database } from "@/lib/server/db";
export const dynamic = "force-dynamic";
export async function GET(req: NextRequest) {
  try {
    const q = req.nextUrl.searchParams,
      kind = ["summary", "electricity", "wholesale"].includes(
        q.get("kind") || "",
      )
        ? q.get("kind")!
        : "summary",
      search = (q.get("q") || "").slice(0, 150),
      category = (q.get("category") || "").slice(0, 180),
      page = Math.max(0, Number(q.get("page")) || 0),
      db = database();
    const base =
      kind === "wholesale"
        ? `SELECT h.document_id,h.source_locator,h.observed_on,h.product_name AS name,'Productos mayoristas'::text category,jsonb_build_object('Producto',h.product_name,'Ciudad',h.market_name,'Precio (COP)',h.price,'Unidad',h.unit,'Variación (%)',h.change_percent) AS details FROM historical_price h WHERE series='dane-monthly-summary'`
        : `SELECT document_id,source_locator,observed_on,name,category,details FROM input_reference_row WHERE kind=$1`;
    const bind = kind === "wholesale" ? [] : [kind];
    const options = (
      await db.query(
        `WITH facts AS (${base}) SELECT DISTINCT observed_on,category FROM facts WHERE observed_on<=CURRENT_DATE ORDER BY observed_on DESC,category`,
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
    const pos = bind.length,
      filter = `observed_on=$${pos + 1} AND ($${pos + 2}='' OR name ILIKE '%' || $${pos + 2} || '%') AND ($${pos + 3}='' OR category=$${pos + 3})`;
    const args = [...bind, day, search, category];
    const canonical = `WITH facts AS (${base}), latest AS (SELECT DISTINCT ON(f.name,f.category,coalesce(f.details->>'Estrato',f.details->>'Ciudad','')) f.* FROM facts f JOIN source_document d ON d.id=f.document_id WHERE ${filter} ORDER BY f.name,f.category,coalesce(f.details->>'Estrato',f.details->>'Ciudad',''),d.retrieved_at DESC)`;
    const rows = (
      await db.query(
        `${canonical} SELECT * FROM latest ORDER BY name LIMIT 60 OFFSET $${pos + 4}`,
        [...args, page * 60],
      )
    ).rows;
    const count = (
      await db.query(`${canonical} SELECT count(*) FROM latest`, args)
    ).rows[0].count;
    return NextResponse.json(
      {
        rows,
        total: Number(count),
        dates,
        categories: [...new Set(options.map((x) => x.category))],
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
