"use client";
import Link from "next/link";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
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
}: {
  markets: MarketPrice[];
  coffee?: boolean;
}) {
  const [order, setOrder] = useState("high");
  const [showAll, setShowAll] = useState(false);
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
      <div className="market-sort">
        <span className="muted" style={{ fontSize: 12 }}>
          {markets.length} {coffee ? "sucursales Almacafé" : "mercados"} ·{" "}
          {coffee
            ? "COP por carga de 125 kg"
            : markets[0]?.series === "city"
              ? "Informe diario · " +
                markets[0].presentation +
                " · " +
                markets[0].units
              : "Promedios mensuales, COP por " +
                unitLabel(markets[0]?.unit || "kg")}
        </span>
        <label>
          Ordenar
          <select value={order} onChange={(e) => setOrder(e.target.value)}>
            <option value="high">Mayor precio primero</option>
            <option value="low">Menor precio primero</option>
          </select>
        </label>
      </div>
      {!sorted.length ? (
        <p className="empty-state">
          No hay mercados disponibles para este departamento.
        </p>
      ) : (
        sorted.slice(0, showAll ? undefined : 6).map((m, i) => (
          <article className="market-row" key={m.id}>
            <span className="market-number">{i + 1}</span>
            <div className="market-info">
              <h3>
                <Link href={"/market/" + m.id}>{m.name}</Link>
              </h3>
              <p>
                {m.region} · {dateLabel(m.date, true)}
              </p>
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
                  ? `${m.presentation} · ${m.units}`
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
                market={m.id}
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
      {sorted.length > 6 && (
        <button
          className="button secondary"
          onClick={() => setShowAll((x) => !x)}
        >
          {showAll
            ? "Ver menos"
            : `Ver los ${sorted.length} ${coffee ? "puntos" : "mercados"}`}
        </button>
      )}
    </section>
  );
}
