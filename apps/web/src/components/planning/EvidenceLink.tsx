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
}) {
  const open = useEvidence();
  if (!id) return <span className="muted">Documento no disponible</span>;
  const q = new URLSearchParams();
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
