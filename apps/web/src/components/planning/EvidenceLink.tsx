"use client";
import { useEvidence } from "./EvidenceProvider";
import { IoDocumentTextOutline } from "react-icons/io5";
import { workbookLocation } from "@/lib/workbook-locator";
import { pdfLocationPage } from "@/lib/pdf-locator";
export function EvidenceLink({
  id,
  children = "Ver de dónde sale este dato",
  page,
  municipality,
  department,
  input,
  product,
  productName,
  market,
  marketName,
  providerName,
  stratum,
  presentation,
  units,
  currency,
  food,
  month,
  locator,
  sheet,
  row,
}: {
  id?: string;
  children?: React.ReactNode;
  page?: number;
  municipality?: string;
  department?: string;
  input?: string;
  product?: string;
  productName?: string;
  market?: string;
  marketName?: string;
  providerName?: string;
  stratum?: string;
  presentation?: string;
  units?: string;
  currency?: string;
  food?: string;
  month?: string;
  locator?: string;
  sheet?: string;
  row?: number;
}) {
  const open = useEvidence();
  if (!id) return <span className="muted">Documento no disponible</span>;
  const q = new URLSearchParams();
  if(locator) q.set("locator",locator);
  const cell = workbookLocation(locator);
  if (sheet || cell?.sheet) q.set("sheet", sheet || cell!.sheet);
  if (row || cell?.row) q.set("row", String(row || cell!.row));
  if (cell?.column) q.set("col", String(cell.column));
  const sourcePage = page || pdfLocationPage(locator);
  if (sourcePage) q.set("page", String(sourcePage));
  if (municipality) q.set("municipality", municipality);
  if (department) q.set("department", department);
  if (input) q.set("input", input);
  for (const [key, value] of Object.entries({ product, productName, market, marketName, providerName, stratum, presentation, units, currency, food, month }))
    if (value) q.set(key, value);
  return (
    <a
      className="evidence-link"
      onClick={(event) => {
        if (
          !event.metaKey &&
          !event.ctrlKey &&
          !event.shiftKey &&
          !event.altKey
        ) {
          event.preventDefault();
          event.currentTarget.focus({ preventScroll: true });
          open({ id, query: q.toString() });
        }
      }}
      href={
        "/evidence/" +
        encodeURIComponent(id) +
        (q.size ? "?" + q.toString() : "")
      }
    >
      <IoDocumentTextOutline />
      {children}
    </a>
  );
}
