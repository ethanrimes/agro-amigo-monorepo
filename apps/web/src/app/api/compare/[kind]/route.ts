import { NextRequest, NextResponse } from "next/server";
import { comparison } from "@/lib/server/comparisons";
import { InputIdentityConflictError, InputIdentityGuardError } from "@/lib/input-identity-equivalence";
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
  let deadline: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      comparison(kind, query),
      new Promise<never>((_, reject) => {
        deadline = setTimeout(() => reject(new Error("COMPARISON_DEADLINE")), 55_000);
      }),
    ]);
    return NextResponse.json(result, {
      headers: { "Cache-Control": "public, max-age=300" },
    });
  } catch (error) {
    if (error instanceof InputIdentityConflictError || error instanceof InputIdentityGuardError)
      return NextResponse.json({ error: error.message }, { status: 409 });
    return NextResponse.json(
      { error: "No pudimos consultar la comparación. Intenta de nuevo." },
      { status: 503 },
    );
  } finally {
    if (deadline) clearTimeout(deadline);
  }
}
