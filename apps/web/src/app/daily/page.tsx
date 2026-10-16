"use client";
import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { ReportProductPicture } from "@/components/explore/ReportProductPicture";
import { money, dateLabel, unitLabel } from "@/lib/market-types";
type Daily = {
  observed_on: string;
  product_name: string;
  market_name: string;
  price: number;
  unit: string;
  change_percent: number | null;
  document_id: string;
  source_page: number;
  source_locator: string;
};
function DailyContent() {
  const { ready } = usePreferences();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const selectedDate = searchParams.get("date") || "";
  const product = searchParams.get("product") || "";
  const market = searchParams.get("market") || "";
  const { data: dates } = useData<{ date: string }[]>("/api/planning/daily-dates");
  const { data, loading, error, retry } = useData<Daily[]>(
    `/api/planning/daily${selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : ""}`,
  );
  const displayedDate = selectedDate || data?.[0]?.observed_on.slice(0, 10) || dates?.[0]?.date || "";
  const updateFilters = (changes: Partial<Record<"date" | "product" | "market", string>>) => {
    const next = new URLSearchParams(window.location.search);
    // Commit the visible default date when another filter is selected so a
    // shared URL always captures the exact bulletin the user was viewing.
    if (!("date" in changes) && !next.has("date") && displayedDate)
      next.set("date", displayedDate);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    const query = next.toString();
    const href = pathname + (query ? `?${query}` : "") + window.location.hash;
    const current = window.location.pathname + window.location.search + window.location.hash;
    if (href !== current) window.history.pushState(null, "", href);
  };
  const { data: supplySource, loading: supplyLoading, error: supplyError, retry: retrySupply } = useData<{
    document_id: string; first_day: string; last_day: string; source_page: number | null; sheet: string | null;
  } | null>(`/api/planning/daily-supply-source${displayedDate ? `?date=${encodeURIComponent(displayedDate)}` : ""}`);
  const dateIndex = dates?.findIndex((entry) => entry.date === displayedDate) ?? -1;
  const marketOptions = Array.from(new Set((data || []).map((row) => row.market_name))).sort();
  const productOptions = Array.from(new Set((data || []).map((row) => row.product_name)))
    .sort((a, b) => a.localeCompare(b, "es"));
  const productUnavailable = !!product && !loading && !error && !productOptions.includes(product);
  const marketUnavailable = !!market && !loading && !error && !marketOptions.includes(market);
  const rows = (data || [])
    .filter(
      (r) =>
        !!product && r.product_name === product &&
        (!market || r.market_name === market),
    )
    .sort(
      (a, b) =>
        a.product_name.localeCompare(b.product_name, "es") || b.price - a.price,
    );
  return (
    <>
      <Link href="/products" className="back-link">
        ← Productos e historia mensual
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">UNA REFERENCIA MÁS CERCANA A TU VENTA</span>
          <h1>Boletines diarios</h1>
          <p>
            DANE SIPSA ·{" "}
            {displayedDate
              ? dateLabel(displayedDate)
              : "Consulta la fecha de publicación"}{" "}
            · COP por unidad indicada
          </p>
        </div>
      </div>
      <p><Link className="button primary" href="/regional">Ver informes por ciudades: rangos, empaques y rondas →</Link></p>
      <section className="panel">
        <p>
          Precios mayoristas reportados ese día. Confirma el pago en finca, la
          variedad y los gastos antes de acordar una venta.
        </p>
        {ready ? <div className="form-grid">
          <label className="form-field">
            Fecha del boletín
            <input
              aria-label="Fecha del boletín"
              type="date"
              value={displayedDate}
              min={dates?.at(-1)?.date}
              max={dates?.[0]?.date}
              onChange={(event) => updateFilters({ date: event.target.value })}
            />
          </label>
          <div className="form-field">
            <span>Otras fechas publicadas</span>
            <div className="form-grid">
              <button type="button" className="button" disabled={dateIndex < 0 || dateIndex >= (dates?.length || 0) - 1}
                onClick={() => updateFilters({ date: dates![dateIndex + 1].date })}>
                ← Anterior
              </button>
              <button type="button" className="button" disabled={dateIndex <= 0}
                onClick={() => updateFilters({ date: dates![dateIndex - 1].date })}>
                Siguiente →
              </button>
            </div>
          </div>
          <SearchableSelect
            label="Buscar producto en el boletín"
            value={product}
            onChange={(value) => updateFilters({ product: value })}
            options={productOptions.map((name) => ({ id: name, label: name }))}
            selectedLabel={product ? `${product}${productUnavailable ? " · sin datos en esta fecha" : ""}` : undefined}
            emptyLabel="Elige un producto para consultar sus precios"
            placeholder="Busca el producto del boletín"
          />
          <SearchableSelect
            label="Plaza del boletín"
            value={market}
            onChange={(value) => updateFilters({ market: value })}
            options={marketOptions.map((name) => ({ id: name, label: name }))}
            selectedLabel={market ? `${market}${marketUnavailable ? " · sin datos en esta fecha" : ""}` : undefined}
            emptyLabel="Todas las plazas"
            placeholder="Busca ciudad o plaza"
          />
        </div> : <p role="status">Preparando filtros del boletín…</p>}
        <AppliedFilters items={[
          { label: "Fecha", value: displayedDate ? dateLabel(displayedDate) : "" },
          { label: "Producto", value: product },
          { label: "Plaza", value: market },
        ]} />
        {marketUnavailable && <p className="field-help" role="status">
          El boletín de esta fecha no reporta precios para {market}. La plaza sigue seleccionada;
          elige otra plaza o Todas las plazas para ampliar la consulta.
        </p>}
        {productUnavailable && <p className="field-help" role="status">
          El boletín de esta fecha no reporta precios para {product}. El producto sigue seleccionado;
          elige otro producto para consultar sus precios.
        </p>}
        <p className="field-help">
          * La variedad predominante puede cambiar entre mercados. No se combina
          este boletín con la serie mensual de una variedad específica. Sin dato
          significa que la entidad no lo reportó.
        </p>
      </section>
      {loading ? (
        <p role="status">Consultando el boletín…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <p>{product ? `${rows.length} referencia${rows.length === 1 ? "" : "s"}` : `${data?.length || 0} referencias disponibles`}</p>
          {product && rows.length > 6 && <p>Se muestran los seis precios mayores. Busca y elige una plaza en el desplegable para consultar cualquiera de las {rows.length} referencias.</p>}
          {!product && <p className="empty-state">
            Busca y elige un producto en el desplegable para ver sus precios por plaza.
          </p>}
          <div className="input-grid">
            {rows.slice(0, 6).map((r) => (
              <article
                className="panel input-card"
                key={JSON.stringify([r.observed_on, r.product_name, r.market_name, r.unit, r.document_id, r.source_locator])}
              >
                <ReportProductPicture name={r.product_name} />
                <span className="eyebrow">{r.market_name}</span>
                <h2>{r.product_name}</h2>
                <strong className="input-price">
                  {money(r.price)} <small>/ {unitLabel(r.unit)}</small>
                </strong>
                <p>
                  {r.change_percent === null
                    ? "Sin variación reportada"
                    : `${r.change_percent > 0 ? "+" : ""}${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(r.change_percent)} % frente al anterior día de mercado`}
                </p>
                <EvidenceLink
                  id={r.document_id}
                  locator={r.source_locator}
                  page={r.source_page}
                  productName={r.product_name}
                  marketName={r.market_name}
                  units={r.unit}
                  currency="COP"
                  month={r.observed_on}
                >
                  Comprobar este precio
                </EvidenceLink>
              </article>
            ))}
          </div>
          {product && !rows.length && (
            <p className="empty-state">
              No hay referencias para esta búsqueda. Prueba otra plaza o
              producto.
            </p>
          )}
        </>
      )}
      <section className="panel">
        <h2>¿Cuánto producto llegó a las plazas?</h2>
        {supplyLoading ? <p role="status">Consultando la fuente de abastecimiento…</p>
          : supplyError ? <ErrorState message={supplyError} retry={retrySupply} />
          : supplySource ? <>
        <p>Este boletín reporta entradas del {dateLabel(supplySource.first_day, true)} al {dateLabel(supplySource.last_day, true)}.
          Son resúmenes de los mercados informados; los filtros de precio por producto y plaza no se aplican a estos totales.
          No representan inventario disponible para comprar.</p>
          <EvidenceLink
            id={supplySource.document_id}
            page={supplySource.source_page || undefined}
            sheet={supplySource.sheet || undefined}
            month={displayedDate}
          >
            Ver abastecimiento en el boletín DANE
          </EvidenceLink>
          </> : <p>No hay una tabla de abastecimiento verificada en el boletín de esta fecha.
            Puedes consultar las llegadas reportadas en los mercados.</p>}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", columnGap: 20 }}>
          <Link className="evidence-link" href="/markets">Consultar abastecimiento por mercado →</Link>
          <Link className="evidence-link" href="/offers">
            Comparar mis cotizaciones y gastos →
          </Link>
        </div>
      </section>
    </>
  );
}

export default function DailyPage() {
  return (
    <Suspense fallback={<p>Cargando boletines diarios…</p>}>
      <DailyContent />
    </Suspense>
  );
}
