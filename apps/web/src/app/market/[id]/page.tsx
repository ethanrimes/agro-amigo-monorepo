"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import {
  DetailTabs,
  type InformationMode,
} from "@/components/explore/DetailTabs";
import { SupplyPanel } from "@/components/explore/SupplyPanel";
import { MapButton } from "@/components/explore/ColombiaMap";
import { photoFor } from "@/lib/images";
import { MarketPrices } from "@/components/comparison/MarketPrices";
import type { MarketDetail } from "@/lib/explore-types";
export default function MarketPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    [mode, setMode] = useState<InformationMode>("price");
  const { data, loading, error, retry } = useData<MarketDetail>(
    "/api/explore/market?id=" + encodeURIComponent(id),
  );
  const photo = data ? photoFor(data.market.name, "", "market") : null;
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
              <SupplyPanel market={id} name={data.market.name} />
            ) : (
              <MarketPrices id={id} name={data.market.name} />
            )}
          </>
        )
      )}
    </>
  );
}
