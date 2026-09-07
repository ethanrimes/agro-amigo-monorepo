"use client";
import { createContext, useContext, useState } from "react";
import { Overlay } from "@/components/ui/Overlay";
import { EvidenceContent } from "./EvidenceContent";
type Request = { id: string; query: string };
const EvidenceContext = createContext<(request: Request) => void>(() => {});
export const useEvidence = () => useContext(EvidenceContext);
export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const [documents, setDocuments] = useState<Request[]>([]);
  const current = documents.at(-1);
  return (
    <EvidenceContext.Provider
      value={(request) => setDocuments((old) => [...old, request])}
    >
      {children}
      {current && (
        <Overlay
          title="Documento de la fuente"
          className="document-overlay"
          onClose={() => setDocuments([])}
        >
          {documents.length > 1 && (
            <button
              className="document-back"
              onClick={() => setDocuments((old) => old.slice(0, -1))}
            >
              ← Documento anterior
            </button>
          )}
          <div className="document-workspace">
            <EvidenceContent key={current.id + current.query} {...current} />
          </div>
        </Overlay>
      )}
    </EvidenceContext.Provider>
  );
}
