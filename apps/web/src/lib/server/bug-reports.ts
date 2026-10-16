import "server-only";
import { createHmac } from "node:crypto";
import { database } from "./db";

export class InvalidBugReport extends Error {}
export type BugReport = { message: string; reply_email: string; page_path: string; source_document_id: string };

/** Only share internal navigation/filter context. Farm coordinates stay local. */
export function reportPagePath(value: unknown): string {
  if (typeof value !== "string" || value.length > 1000 || !value.startsWith("/") || value.startsWith("//") || /[\r\n\\]/.test(value)) return "";
  const url = new URL(value, "https://agroamigo.invalid");
  for (const key of [...url.searchParams.keys()]) {
    if (/lat|lon|coord|gps|location|email|token|password|address/i.test(key)) url.searchParams.delete(key);
  }
  return url.pathname + (url.searchParams.size ? "?" + url.searchParams.toString() : "");
}

export function validateBugReport(value: unknown): BugReport {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new InvalidBugReport();
  const row = value as Record<string, unknown>;
  if (row.consent !== true || (row.website !== undefined && row.website !== "")) throw new InvalidBugReport();
  if (typeof row.message !== "string") throw new InvalidBugReport();
  const message = row.message.trim();
  if (message.length < 10 || message.length > 5000 || /\u0000/.test(message)) throw new InvalidBugReport();
  if (row.reply_email !== undefined && typeof row.reply_email !== "string") throw new InvalidBugReport();
  const reply_email = ((row.reply_email as string) || "").trim();
  if (reply_email && (reply_email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(reply_email))) throw new InvalidBugReport();
  if (row.source_document_id !== undefined && typeof row.source_document_id !== "string") throw new InvalidBugReport();
  const source_document_id = (row.source_document_id as string) || "";
  if (source_document_id && !/^[a-f0-9]{64}$/.test(source_document_id)) throw new InvalidBugReport();
  return { message, reply_email, source_document_id, page_path: reportPagePath(row.page_path) };
}

export async function submitBugReport(report: BugReport, address: string) {
  const secret = process.env.BUG_REPORT_RATE_SECRET;
  if (!secret || secret.length < 32) throw new Error("BUG_REPORT_NOT_CONFIGURED");
  const rateKey = createHmac("sha256", secret).update(address.slice(0, 200)).digest("hex");
  const { rows } = await database().query<{id:string}>(
    "SELECT submit_bug_report($1,$2,$3,$4,$5,true) AS id",
    [report.message, report.reply_email, report.page_path, report.source_document_id, rateKey],
  );
  return rows[0].id;
}
