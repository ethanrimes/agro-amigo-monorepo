"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { CropPicture } from "@/components/marketplace/CropPicture";
import { SearchBox } from "@/components/ui/SearchBox";
import {
  DetailTabs,
  type InformationMode,
} from "@/components/explore/DetailTabs";
import { SupplyPanel } from "@/components/explore/SupplyPanel";
import { MapButton } from "@/components/explore/ColombiaMap";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { fold } from "@/lib/planning-math";
import { money, dateLabel } from "@/lib/market-types";
import { photoFor } from "@/lib/images";
import type { MarketDetail } from "@/lib/explore-types";
export default function MarketPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    router = useRouter(),
    [mode, setMode] = useState<InformationMode>("price"),
    [query, setQuery] = useState("");
  const { data, loading, error, retry } = useData<MarketDetail>(
    "/api/explore/market?id=" + encodeURIComponent(id),
  );
  const photo = data ? photoFor(data.market.name, "", "market") : null;
  const rows = (data?.products || []).filter((p) =>
    fold(p.name).includes(fold(query)),
  );
  return (
    <>
      <Link href="/markets" className="back-link">
        ← Mercados
      </Link>
      {loading ? (
        <p role="status">Consultando mercado…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <div className="entity-hero">
              <img src={photo!.src} alt={photo!.alt} />
              <div>
                <span className="eyebrow">
                  {data.market.city} · {data.market.region}
                </span>
                <h1>{data.market.name}</h1>
                <p>
                  {data.market.product_count} productos con referencias de
                  precio
                </p>
                <MapButton kind="market" label="Ubicar mercados" />
              </div>
            </div>
            <DetailTabs mode={mode} onChange={setMode} />
            {mode === "supply" ? (
              <SupplyPanel market={id} name="este mercado" />
            ) : (
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Precios en este mercado</h2>
                    <p>
                      Referencias publicadas. Confirma el precio antes de
                      negociar.
                    </p>
                  </div>
                </div>
                <SearchBox
                  label="Buscar producto en el mercado"
                  value={query}
                  onChange={setQuery}
                  options={data.products.map((p) => ({
                    id: p.id,
                    label: p.name,
                    detail: p.category,
                  }))}
                  onSelect={(p) => router.push("/product/" + p.id)}
                />
                <div className="entity-price-list">
                  {rows.map((p) => (
                    <article key={p.id}>
                      <Link
                        href={"/product/" + p.id}
                        className="entity-price-product"
                      >
                        <CropPicture name={p.name} category={p.category} />
                        <div>
                          <strong>{p.name}</strong>
                          <small>
                            {p.period === "daily"
                              ? "Referencia FNC"
                              : "Promedio mensual"}{" "}
                            · {dateLabel(p.date, true)}
                          </small>
                        </div>
                      </Link>
                      <div>
                        <strong>{money(p.price)}</strong>
                        <small>
                          {p.unit === "125kg" ? "/ carga de 125 kg" : "/ kg"}
                        </small>
                        <EvidenceLink
                          id={p.document_id}
                          product={p.id}
                          market={id}
                          month={p.date}
                        >
                          Ver fuente
                        </EvidenceLink>
                      </div>
                    </article>
                  ))}
                </div>
                {!rows.length && <p>No hay precios para esta búsqueda.</p>}
              </section>
            )}
          </>
        )
      )}
    </>
  );
}
