"use client";
import Link from "next/link";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { priceSeriesLabel } from "@/components/explore/AppliedFilters";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { normalizeLabel } from "@/lib/label-normalization";
import { useMemo, useState } from "react";
import {
  dateLabel,
  money,
  unitLabel,
  type MarketPrice,
} from "@/lib/market-types";
export function MarketList({
  markets,
  coffee = false,
  productName,
}: {
  markets: MarketPrice[];
  coffee?: boolean;
  productName?: string;
}) {
  const [order, setOrder] = useState("high");
  const [selectedMarket, setSelectedMarket] = useState("");
  const sorted = useMemo(
    () =>
      [...markets].sort((a, b) => {
        return (
          (order === "low" ? a.price - b.price : b.price - a.price) ||
          b.date.localeCompare(a.date)
        );
      }),
    [markets, order],
  );
  const selectedIndex = sorted.findIndex((market) => market.id === selectedMarket);
  const visible = sorted.slice(0, 6);
  if (selectedIndex >= 6) visible.push(sorted[selectedIndex]);
  return (
    <section className="market-section">
      <div className="section-title">
        <h2>
          {coffee
            ? "Referencia por punto de entrega"
            : markets[0]?.name.includes(" · ")
              ? "Compara las referencias por municipio"
              : "Compara los mercados"}
        </h2>
      </div>
      {markets.length > 0 && <div className="market-sort">
        <span className="muted" style={{ fontSize: 12 }}>
          {markets.length}{" "}
          {coffee
            ? markets.length === 1 ? "sucursal Almacafé" : "sucursales Almacafé"
            : markets.length === 1 ? "mercado" : "mercados"} ·{" "}
          {coffee
            ? "COP por carga de 125 kg"
            : markets[0]?.series === "city"
              ? "Informe diario · " +
                normalizeLabel(markets[0].presentation || "", "presentation") +
                " · " +
                markets[0].units
              : (priceSeriesLabel[markets[0]?.series || "monthly"] || "Precio reportado") + ", COP por " +
                unitLabel(markets[0]?.unit || "kg")}
        </span>
        <label>
          Ordenar
          <select value={order} onChange={(e) => setOrder(e.target.value)}>
            <option value="high">Mayor precio primero</option>
            <option value="low">Menor precio primero</option>
          </select>
        </label>
      </div>}
      {(sorted.length > 6 || selectedMarket) && (
        <SearchableSelect
          label="Consultar un mercado de la comparación"
          placeholder="Busca mercado, departamento o fecha…"
          emptyLabel="Se muestran los seis primeros; busca otro mercado por su nombre"
          value={selectedMarket}
          onChange={setSelectedMarket}
          selectedLabel={selectedMarket ? "Mercado ya no disponible con estos filtros" : undefined}
          options={sorted.map((market) => ({
            id: market.id,
            label: market.name,
            detail: `${market.region} · ${dateLabel(market.date)} · ${normalizeLabel(market.presentation || "", "presentation") || unitLabel(market.unit)}${market.units ? ` · ${market.units}` : ""}`,
          }))}
        />
      )}
      {!sorted.length ? (
        <p className="empty-state">
          Sin cotizaciones para los filtros aplicados.
        </p>
      ) : (
        visible.map((m) => (
          <article className="market-row" key={m.id}>
            <span className="market-number">{sorted.findIndex((market) => market.id === m.id) + 1}</span>
            <div className="market-info">
              <h3>
                <Link href={"/market/" + m.id}>{m.name}</Link>
              </h3>
              <p>
                {m.region} · {dateLabel(m.date)}
              </p>
              {m.id === selectedMarket && <p>Mercado seleccionado para consultar</p>}
              {m.date !==
                markets.reduce((d, r) => (r.date > d ? r.date : d), "") && (
                <p>Dato de un período anterior</p>
              )}
            </div>
            <div className="market-value">
              <strong>{money(m.price)}</strong>
              <small>
                {" "}
                /{" "}
                {m.series === "city"
                  ? `${normalizeLabel(m.presentation || "", "presentation")} · ${m.units}`
                  : unitLabel(m.unit)}
              </small>
              {m.series === "city" && (
                <small>
                  Rango: {money(m.min_price!)}–{money(m.max_price!)}
                </small>
              )}
              <EvidenceLink
                id={m.document_id}
                locator={m.source_locator}
                product={m.product_id}
                productName={productName}
                market={m.id}
                marketName={m.name}
                department={m.region}
                presentation={m.presentation}
                units={m.source_units || m.units}
                currency="COP"
                month={m.date}
                page={
                  m.source_page ||
                  Number(
                    m.source_locator?.match(/PDF (?:p\.|page) (\d+)/)?.[1],
                  ) ||
                  (coffee ? 2 : 1)
                }
              >
                Ver fuente
              </EvidenceLink>
            </div>
          </article>
        ))
      )}
    </section>
  );
}
