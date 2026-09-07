"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { IoLocationOutline, IoArrowForward } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState, LoadingCards } from "@/components/marketplace/Shared";
import { SearchBox } from "@/components/ui/SearchBox";
import { MapButton } from "@/components/explore/ColombiaMap";
import { fold } from "@/lib/planning-math";
import { dateLabel } from "@/lib/market-types";
import { photoFor } from "@/lib/images";
import type { Market } from "@/lib/explore-types";
export default function Markets() {
  const { data, loading, error, retry } = useData<Market[]>(
      "/api/explore/markets",
    ),
    { region, setRegion } = usePreferences(),
    router = useRouter();
  const [query, setQuery] = useState(""),
    [limit, setLimit] = useState(24);
  const candidates = (data || []).filter(
    (m) => !region || fold(m.region) === fold(region),
  );
  const rows = candidates.filter((m) =>
    fold(m.name + " " + m.city).includes(fold(query)),
  );
  return (
    <>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">LAS PLAZAS DE NUESTRO PAÍS</span>
          <h1>Mercados</h1>
          <p>Consulta qué productos llegan y cómo están sus precios.</p>
        </div>
        <MapButton kind="market" />
      </div>
      <div className="catalog-controls">
        <SearchBox
          label="Buscar mercado"
          placeholder="Corabastos, Medellín, tu municipio…"
          value={query}
          onChange={(v) => {
            setQuery(v);
            setLimit(24);
          }}
          options={candidates.map((m) => ({
            id: m.id,
            label: m.name,
            detail: m.region,
          }))}
          onSelect={(m) => router.push("/market/" + m.id)}
        />
        <label className="region-field">
          <span>Departamento</span>
          <select
            value={region}
            onChange={(e) => {
              setRegion(e.target.value);
              setLimit(24);
            }}
          >
            <option value="">Toda Colombia</option>
            {[
              ...new Set([
                ...(data || []).map((m) => m.region),
                ...(region ? [region] : []),
              ]),
            ]
              .sort()
              .map((r) => (
                <option key={r}>{r}</option>
              ))}
          </select>
        </label>
      </div>
      {loading ? (
        <LoadingCards />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>{rows.length} mercados con información</span>
            <span>DANE SIPSA · FNC</span>
          </div>
          <div className="market-grid">
            {rows.slice(0, limit).map((m) => {
              const p = photoFor(m.name, "", "market");
              return (
                <Link
                  className="market-card"
                  key={m.id}
                  href={"/market/" + m.id}
                >
                  <img src={p.src} alt={p.alt} loading="lazy" />
                  <div>
                    <span className="entity-location">
                      <IoLocationOutline />
                      {m.city} · {m.region}
                    </span>
                    <h2>{m.name}</h2>
                    <p>
                      {m.product_count} productos con precio
                      {m.supply_date ? " · Abastecimiento disponible" : ""}
                    </p>
                    <div className="entity-card-footer">
                      <small>
                        {m.date
                          ? dateLabel(m.date, true)
                          : m.supply_date
                            ? dateLabel(m.supply_date, true)
                            : "Sin fecha"}
                      </small>
                      <span>
                        Ver mercado <IoArrowForward />
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
          {!rows.length && (
            <div className="empty-state">
              <h2>No encontramos mercados</h2>
              <p>Prueba otro nombre o departamento.</p>
            </div>
          )}
          {rows.length > limit && (
            <div className="load-more">
              <button
                className="button secondary"
                onClick={() => setLimit((n) => n + 24)}
              >
                Ver más mercados
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
