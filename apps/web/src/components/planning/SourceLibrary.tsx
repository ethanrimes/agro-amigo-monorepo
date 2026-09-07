"use client";
import { useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { fold } from "@/lib/planning-math";
import { EvidenceLink } from "./EvidenceLink";
type Document = {
  id: string;
  alias: string;
  title: string;
  publisher: string;
  reference_period: string;
  kind: string;
  media_type: string;
};
export function SourceLibrary() {
  const { data, loading, error, retry } = useData<Document[]>(
      "/api/planning/library",
    ),
    [query, setQuery] = useState("");
  const rows = (data || []).filter((d) =>
    fold(d.title + " " + d.publisher + " " + d.reference_period).includes(
      fold(query),
    ),
  );
  return (
    <section className="panel source-library">
      <h2>Biblioteca de documentos</h2>
      <p>
        Originales y métodos conservados en Azure. Los enlaces junto a cada dato
        llevan a su página o registro.
      </p>
      <label className="form-field">
        Buscar en los documentos
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ej. costos, Cenicafé, 2025…"
        />
      </label>
      {loading ? (
        <p role="status">Consultando biblioteca…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <p className="field-help">{rows.length} documentos</p>
          <div className="library-list">
            {rows.map((d) => (
              <div className="library-row" key={d.alias}>
                <div>
                  <EvidenceLink id={d.id}>{d.title}</EvidenceLink>
                  <small>
                    {d.reference_period} ·{" "}
                    {d.media_type === "application/pdf"
                      ? "PDF"
                      : d.kind === "extract"
                        ? "Extracto de datos"
                        : "Archivo original"}
                  </small>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
