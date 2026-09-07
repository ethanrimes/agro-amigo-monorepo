import { NextResponse } from "next/server";
import { database } from "@/lib/server/db";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    await database().query("SELECT 1");
    return NextResponse.json({ status: "ok", database: "connected" });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
