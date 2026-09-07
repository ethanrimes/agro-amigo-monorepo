import Link from "next/link";
import { IoDocumentTextOutline } from "react-icons/io5";
export function EvidenceLink({
  id,
  children = "Ver de dónde sale este dato",
  page,
  municipality,
  department,
  input,
}: {
  id?: string;
  children?: React.ReactNode;
  page?: number;
  municipality?: string;
  department?: string;
  input?: string;
}) {
  if (!id) return <span className="muted">Documento no disponible</span>;
  const q = new URLSearchParams();
  if (page) q.set("page", String(page));
  if (municipality) q.set("municipality", municipality);
  if (department) q.set("department", department);
  if (input) q.set("input", input);
  return (
    <Link
      className="evidence-link"
      href={
        "/evidence/" +
        encodeURIComponent(id) +
        (q.size ? "?" + q.toString() : "")
      }
    >
      <IoDocumentTextOutline />
      {children}
    </Link>
  );
}
