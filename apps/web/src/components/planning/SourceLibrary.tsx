"use client";
import { useEffect, useState } from "react";
import { SearchBox } from "@/components/ui/SearchBox";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { useEvidence } from "./EvidenceProvider";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { fold } from "@/lib/planning-math";
import { archiveCopyLabel, archiveVersionLabel } from "@/lib/archive-copy-label";
import { sourceReferencePeriod } from "@/lib/evidence-period";
import { dateLabel } from "@/lib/market-types";
type Document = {
  id: string;
  alias?: string;
  title: string;
  subject?: string;
  verified_market?: string;
  publisher: string;
  reference_period: string;
  observed_first?: string;
  observed_last?: string;
  kind: string;
  media_type: string;
  filename?: string;
  retrieved_at?: string;
  municipality_filter?: boolean;
};
export function SourceLibrary() {
  const open = useEvidence();
  const { data, loading, error, retry } = useData<Document[]>(
      "/api/planning/library",
    ),
    [query, setQuery] = useState(""),
    [debouncedQuery, setDebouncedQuery] = useState(""),
    [municipality, setMunicipality] = useState(""),
    [cursor, setCursor] = useState<{ query: string; value: string } | null>(null),
    [archiveEntries, setArchiveEntries] = useState<{ query: string; rows: Document[]; nextCursor: string | null }>(
      { query: "", rows: [], nextCursor: null });
  const hasMunicipalSources = data?.some((document) => document.municipality_filter);
  const searchQuery = query.trim();
  const places = useData<{ id: string; name: string; department: string }[]>(
    hasMunicipalSources ? "/api/planning/municipalities" : null,
  );
  useEffect(() => {
    setCursor(null);
    setArchiveEntries({ query: "", rows: [], nextCursor: null });
  }, [searchQuery]);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 350);
    return () => clearTimeout(timer);
  }, [query]);
  const searching = query.trim().length >= 3;
  const archiveUrl = searching && debouncedQuery === query.trim()
    ? `/api/source-archive?q=${encodeURIComponent(debouncedQuery)}${cursor?.query === debouncedQuery ? `&cursor=${encodeURIComponent(cursor.value)}` : ""}`
    : null;
  const archive = useData<{ rows: Document[]; hasMore: boolean; nextCursor?: string | null }>(archiveUrl);
  useEffect(() => {
    if (!archive.data) return;
    const result = archive.data;
    setArchiveEntries((previous) => ({
      query: debouncedQuery,
      rows: [...new Map([...(previous.query === debouncedQuery ? previous.rows : []),
        ...result.rows].map((document) => [document.id, document])).values()],
      nextCursor: result.nextCursor || null,
    }));
  }, [archive.data, debouncedQuery]);
  const matchingCurated = (data || []).filter((d) =>
    fold(d.title + " " + d.publisher + " " + d.reference_period + " " + (d.subject || "")).includes(
      fold(query),
    ),
  );
  const curated = [...new Map(matchingCurated.map((d) => [d.id, d])).values()];
  const ids = new Set(curated.map((d) => d.id));
  const rows = searching
    ? [...curated, ...(archiveEntries.query === query.trim() ? archiveEntries.rows : []).filter((d) => !ids.has(d.id))]
    : curated;
  const archivePending = searching && (archive.loading || archiveUrl === null);
  const nextCursor = archiveEntries.query === query.trim() ? archiveEntries.nextCursor : null;
  const titleCopies = new Map<string, string[]>();
  const archivePeriod = (document: Document) =>
    document.observed_first && document.observed_last
      ? document.observed_first === document.observed_last
        ? dateLabel(document.observed_first)
        : `${dateLabel(document.observed_first)} al ${dateLabel(document.observed_last)}`
      : sourceReferencePeriod(document.reference_period);
  rows.forEach((document) => titleCopies.set(fold(document.title), [...(titleCopies.get(fold(document.title)) || []), document.id]));
  return (
    <section className="panel source-library" id="document-library">
      <h2>Biblioteca de documentos</h2>
      <p>
        Originales y métodos conservados en Azure. Los enlaces junto a cada dato
        llevan a su página o registro. Un documento archivado puede contener
        tablas aún pendientes de verificación; consulta las fichas para ver los
        precios publicados.
      </p>
      <SearchBox
        label="Buscar en los documentos"
        placeholder="Nombre de archivo, fecha o entidad…"
        value={query}
        onChange={(value) => setQuery(value.slice(0, 100))}
        filterOptions={false}
        replaceValueOnSelect={false}
        loading={loading || (archivePending && !rows.length)}
        error={Boolean(error || (searching && archive.error)) && !rows.length}
        paginateOptions
        moreLoading={archivePending}
        moreError={Boolean(searching && archive.error)}
        onMore={nextCursor ? () => archive.error ? archive.retry() : setCursor({ query: debouncedQuery, value: nextCursor }) : undefined}
        options={rows.map((d) => ({
          id: d.id,
          label: d.subject ? `${d.subject} · ${d.title}` : d.title,
          detail: [d.publisher, d.verified_market && `Mercado impreso: ${d.verified_market}`,
            archivePeriod(d), archiveCopyLabel(d.retrieved_at),
            archiveVersionLabel(d.id, titleCopies.get(fold(d.title)) || [])].filter(Boolean).join(" · "),
        }))}
        onSelect={(d) => open({
          id: d.id,
          query: rows.find((row) => row.id === d.id)?.municipality_filter && municipality
            ? new URLSearchParams({ municipality }).toString() : "",
        })}
      />
      {hasMunicipalSources && (
        <div className="form-grid">
          <SearchableSelect
            label="Municipio de referencia para mapas de aptitud"
            value={municipality}
            onChange={setMunicipality}
            options={(places.data || []).map((place) => ({ id: place.id, label: place.name, detail: place.department }))}
            loading={places.loading}
            error={Boolean(places.error)}
            emptyLabel="Todos los registros del archivo"
            placeholder="Busca municipio o departamento"
          />
          <p className="field-help">
            Los mapas de UPRA se consultan aunque el cultivo no figure en la producción municipal.
            Son referencias regionales; no determinan la aptitud de un predio.
          </p>
          {places.error && <ErrorState message={places.error} retry={places.retry} />}
        </div>
      )}
      <p className="field-help">
        Busca por nombre del PDF, Excel, ZIP o consulta diaria de DANE, fecha o entidad. Usa de 3 a 100 caracteres y hasta 5 palabras clave; las tildes son opcionales.
      </p>
      {loading ? (
        <p role="status">Consultando biblioteca…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <p className="field-help" role="status">
            {archivePending ? "Buscando originales…" : `${rows.length} ${rows.length === 1 ? "documento" : "documentos"}`}{searching && nextCursor ? " · Hay más coincidencias disponibles en el buscador." : ""}
          </p>
          {searching && archive.error && <ErrorState message={archive.error} retry={archive.retry} />}
          <p className="field-help">
            Abre un original desde el buscador. Las sugerencias se muestran en páginas de 8;
            usa Siguientes y Cargar más coincidencias para recorrerlas. Las copias conservan su fecha de archivo.
          </p>
        </>
      )}
    </section>
  );
}
