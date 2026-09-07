"use client";
import { Suspense, use } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { EvidenceContent } from "@/components/planning/EvidenceContent";
function DirectEvidence({ id }: { id: string }) {
  const q = useSearchParams();
  return (
    <>
      <Link className="back-link" href="/sources">
        ← Fuentes y ayuda
      </Link>
      <h1>Comprueba el dato</h1>
      <EvidenceContent id={id} query={q.toString()} />
    </>
  );
}
export default function EvidencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Suspense fallback={<p>Cargando fuente…</p>}>
      <DirectEvidence id={id} />
    </Suspense>
  );
}
