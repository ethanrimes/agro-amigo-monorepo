import { NextRequest, NextResponse } from "next/server";
import { database } from "@/lib/server/db";
import {
  ARCHIVE_SEARCH_LIMIT,
  archiveSearchSql,
  archiveSearchTerms,
  archiveSearchCursor,
  archiveNextCursor,
} from "@/lib/server/source-archive-search";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const terms = archiveSearchTerms(req.nextUrl.searchParams.get("q") || "");
  const rawCursor = req.nextUrl.searchParams.get("cursor");
  const cursor = archiveSearchCursor(rawCursor);
  if (!terms)
    return NextResponse.json(
      { error: "Busca con 3 a 100 caracteres y hasta 5 palabras clave." },
      { status: 400 },
    );
  if (rawCursor !== null && !cursor)
    return NextResponse.json({ error: "La página de búsqueda no es válida. Busca nuevamente." }, { status: 400 });
  try {
    const client = await database().connect();
    let visible;
    let hasMore;
    try {
      await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
      const rows = (await client.query(archiveSearchSql(terms, Boolean(cursor)),
        cursor ? [...terms, cursor.at, cursor.id] : terms)).rows;
      visible = rows.slice(0, ARCHIVE_SEARCH_LIMIT);
      hasMore = rows.length > ARCHIVE_SEARCH_LIMIT;
      const ids = visible.filter((row) => row.reference_period === "Serie histórica completa" &&
        row.media_type === "application/pdf").map((row) => row.id as string);
      if (ids.length) {
        const periods = (await client.query(
          `SELECT p.document_id,min(p.observed_on)::text AS observed_first,
             max(p.observed_on)::text AS observed_last
           FROM published_regional_price p WHERE p.document_id=ANY($1::text[])
           GROUP BY p.document_id`, [ids],
        )).rows;
        const byId = new Map(periods.map((period) => [period.document_id, period]));
        visible = visible.map((row) => ({ ...row, ...byId.get(row.id) }));
      }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return NextResponse.json(
      { rows: visible, hasMore, nextCursor: hasMore ? archiveNextCursor(visible.at(-1)!) : null },
      { headers: { "Cache-Control": "public, max-age=300" } },
    );
  } catch {
    return NextResponse.json(
      { error: "No pudimos buscar en el archivo. Intenta nuevamente." },
      { status: 503 },
    );
  }
}
