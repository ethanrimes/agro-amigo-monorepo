import { NextRequest, NextResponse } from "next/server";
import { InvalidBugReport, submitBugReport, validateBugReport } from "@/lib/server/bug-reports";
export const dynamic = "force-dynamic";

async function boundedBody(req: NextRequest) {
  if (Number(req.headers.get("content-length") || 0) > 24_000) throw new InvalidBugReport();
  const reader = req.body?.getReader();
  if (!reader) throw new InvalidBugReport();
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 24_000) { await reader.cancel(); throw new InvalidBugReport(); }
      chunks.push(value);
    }
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch { throw new InvalidBugReport(); }
  finally { reader.releaseLock(); }
}

export async function POST(req: NextRequest) {
  const headers = { "Cache-Control": "private, no-store" };
  const origin = req.headers.get("origin");
  const trustedHosts = new Set([req.nextUrl.host, req.headers.get("host"), process.env.WEBSITE_HOSTNAME].filter(Boolean));
  if (origin) {
    try {
      const caller = new URL(origin);
      if (!trustedHosts.has(caller.host) || !["http:", "https:"].includes(caller.protocol)) throw new Error();
    } catch { return NextResponse.json({error:"La solicitud debe enviarse desde AgroAmigo."},{status:403,headers}); }
  }
  try {
    const report = validateBugReport(await boundedBody(req));
    // App Service's proxy adds the client address. Only its hash reaches SQL.
    const address = (req.headers.get("x-forwarded-for") || "unknown").split(",")[0].trim();
    const id = await submitBugReport(report, address);
    return NextResponse.json({id,status:"queued"},{status:201,headers});
  } catch (error) {
    const code = (error as {code?:string}).code;
    if (error instanceof InvalidBugReport || code === "PBR01") return NextResponse.json({error:"Revisa el mensaje, el correo y tu autorización para enviar el reporte."},{status:400,headers});
    if (code === "PBR02") return NextResponse.json({error:"Has enviado varios reportes. Intenta de nuevo en una hora."},{status:429,headers:{...headers,"Retry-After":"3600"}});
    return NextResponse.json({error:"No pudimos guardar tu reporte. Tu mensaje sigue en el formulario; intenta nuevamente."},{status:503,headers});
  }
}
