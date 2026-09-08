"use client";
import { useEvidence } from "./EvidenceProvider";
import { IoDocumentTextOutline } from "react-icons/io5";
export function EvidenceLink({
  id,
  children = "Ver de dónde sale este dato",
  page,
  municipality,
  department,
  input,
  product,
  market,
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
  market?: string;
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
  const cell = locator?.match(/^(.*?)!(?:row\s+|[A-Z]+)?(\d+)/);
  if (sheet || cell?.[1]) q.set("sheet", sheet || cell![1]);
  if (row || cell?.[2]) q.set("row", String(row || cell![2]));
  if (page) q.set("page", String(page));
  if (municipality) q.set("municipality", municipality);
  if (department) q.set("department", department);
  if (input) q.set("input", input);
  for (const [key, value] of Object.entries({ product, market, food, month }))
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
