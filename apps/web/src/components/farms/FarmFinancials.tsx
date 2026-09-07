"use client";
import { useState } from "react";
import Link from "next/link";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { useData } from "@/components/marketplace/useData";
import type { FarmRecord, ManagedCrop } from "@/lib/farm-types";
import type { FarmData, Evidence } from "@/lib/planning-types";
import { money, number, dateLabel } from "@/lib/market-types";
import { fold } from "@/lib/planning-math";
const periods: Record<string, string> = {
  annual: "Año en producción",
  cycle: "Un ciclo por cultivo",
  establishment: "Establecimiento",
};
export function budgetLink(farmId: string, cropId: string) {
  return (
    "/plan?tab=budget&farm=" +
    encodeURIComponent(farmId) +
    "&crop=" +
    encodeURIComponent(cropId)
  );
}
export function FarmFinancials({
  record,
  data,
}: {
  record: FarmRecord;
  data: FarmData;
}) {
  const available = record.crops.filter((c) => c.budget?.results?.length === 3),
    [selection, setSelection] = useState("");
  const groups = [
    ...new Set(
      available.map((c) => c.budget!.planYear + "|" + c.budget!.periodCode),
    ),
  ]
    .sort()
    .reverse();
  const group = groups.includes(selection) ? selection : groups[0] || "",
    crops = available.filter(
      (c) => c.budget!.planYear + "|" + c.budget!.periodCode === group,
    );
  const rows = crops
    .map((c) => ({
      crop: c,
      plan: c.budget!,
      result: c.budget!.results!.find((r) => r.key === "typical")!,
    }))
    .filter((r) => r.result);
  const sum = (fn: (r: (typeof rows)[number]) => number) =>
    rows.reduce((s, r) => s + fn(r), 0);
  const revenue = sum((r) => r.result.revenue),
    cost = sum((r) => r.plan.totalCost + r.result.fees),
    profit = revenue - cost,
    before = sum(
      (r) =>
        r.plan.costsPerHa
          .filter((c) => c.timing === "before")
          .reduce((s, c) => s + c.amount, 0) * r.plan.areaHa,
    );
  const scale = Math.max(revenue, cost, Math.abs(profit), 1);
  return (
    <section className="farm-financials">
      <div className="section-heading">
        <div>
          <span className="eyebrow">TUS CUENTAS, CLARAS</span>
          <h2>De la cosecha a la utilidad</h2>
          <p>Proyecciones con tus áreas, costos y precios guardados.</p>
        </div>
        {groups.length > 0 && (
          <label className="form-field">
            Período de las cuentas
            <select
              value={group}
              onChange={(e) => setSelection(e.target.value)}
            >
              {groups.map((g) => {
                const [year, period] = g.split("|");
                return (
                  <option key={g} value={g}>
                    {year} · {periods[period] || period}
                  </option>
                );
              })}
            </select>
          </label>
        )}
      </div>
      {!rows.length ? (
        <div className="finance-empty">
          <div>
            <h3>Empieza por las cuentas de un cultivo</h3>
            <p>
              Completa su rendimiento, gastos y precio de venta. Aquí verás qué
              entra, qué cuesta y cuánto podría quedar.
            </p>
          </div>
          {record.crops[0] ? (
            <Link
              className="button primary"
              href={budgetLink(record.id, record.crops[0].id)}
            >
              Hacer el primer presupuesto →
            </Link>
          ) : (
            <p>Agrega un cultivo para empezar.</p>
          )}
        </div>
      ) : (
        <>
          <div className="finance-kpis">
            <article>
              <span>Ingresos estimados</span>
              <strong data-kpi="revenue">{money(revenue)}</strong>
              <small>Valor de la cosecha vendible</small>
            </article>
            <article>
              <span>Costos totales</span>
              <strong data-kpi="cost">{money(cost)}</strong>
              <small>Producción + venta + comisión</small>
            </article>
            <article className={"profit-kpi " + (profit < 0 ? "negative" : "")}>
              <span>Utilidad estimada</span>
              <strong data-kpi="profit">{money(profit)}</strong>
              <small>
                {revenue
                  ? number((profit / revenue) * 100) + " % de los ingresos"
                  : "Sin ingresos previstos"}
              </small>
            </article>
            <article>
              <span>Dinero antes de cosechar</span>
              <strong data-kpi="cash">{money(before)}</strong>
              <small>Gastos marcados para antes de cosecha</small>
            </article>
          </div>
          <div className="finance-bridge panel">
            <h3>Así se forman tus resultados</h3>
            {[
              ["Ingresos", revenue, "income"],
              ["Costos", cost, "cost"],
              ["Utilidad", profit, profit < 0 ? "loss" : "profit"],
            ].map(([label, value, kind]) => (
              <div className="finance-bar" key={label}>
                <span>{label}</span>
                <div>
                  <i
                    className={String(kind)}
                    style={{
                      width:
                        Math.max(1, (Math.abs(+value) / scale) * 100) + "%",
                    }}
                  />
                </div>
                <strong>{money(+value)}</strong>
              </div>
            ))}
          </div>
          <div className="panel finance-table-panel">
            <h3>Cada cultivo aporta algo distinto</h3>
            <div className="finance-table-scroll">
              <table className="finance-table">
                <caption>
                  Proyección de {group.split("|")[0]} ·{" "}
                  {periods[group.split("|")[1]]}. COP nominales.
                </caption>
                <thead>
                  <tr>
                    <th>Cultivo / lote</th>
                    <th>Área</th>
                    <th>Cosecha vendible</th>
                    <th>Precio de equilibrio</th>
                    <th>Ingresos</th>
                    <th>Costos</th>
                    <th>Utilidad</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ crop, plan, result }) => (
                    <tr key={crop.id}>
                      <th>
                        <Link href={budgetLink(record.id, crop.id)}>
                          {crop.variety ||
                            data.crops.find(
                              (r) => r.crop_code === crop.cropCode,
                            )?.variety ||
                            crop.name}
                        </Link>
                        <small>
                          {periods[plan.periodCode]} ·{" "}
                          {dateLabel(plan.createdAt, true)}
                        </small>
                      </th>
                      <td data-label="Área">{number(plan.areaHa)} ha</td>
                      <td data-label="Cosecha vendible">
                        {number(result.quantity)} kg
                      </td>
                      <td data-label="Precio de equilibrio">
                        {plan.breakEven === null
                          ? "—"
                          : money(plan.breakEven) + "/kg"}
                      </td>
                      <td data-label="Ingresos">{money(result.revenue)}</td>
                      <td data-label="Costos">
                        {money(plan.totalCost + result.fees)}
                      </td>
                      <td data-label="Utilidad"
                        className={
                          result.profit < 0 ? "loss-text" : "gain-text"
                        }
                      >
                        {money(result.profit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="farm-scenarios">
            {[
              ["low", "Si las condiciones empeoran"],
              ["typical", "Escenario central"],
              ["high", "Si las condiciones mejoran"],
            ].map(([key, label]) => {
              const value = sum(
                (r) => r.plan.results!.find((s) => s.key === key)?.profit || 0,
              );
              return (
                <article
                  key={key}
                  className={key === "typical" ? "central" : ""}
                >
                  <span>{label}</span>
                  <strong>{money(value)}</strong>
                  <small>Utilidad bajo los supuestos de cada cultivo</small>
                </article>
              );
            })}
          </div>
          <p className="privacy-note">
            Se incluyen {rows.length} de {record.crops.length} cultivos, con
            presupuesto para el mismo año y tipo de período. Los ciclos
            representan un ciclo por cultivo; no se multiplican automáticamente
            por cosechas al año. Los escenarios no son ganancias garantizadas.
          </p>
          {groups.length > 1 && (
            <p className="inline-note">
              Hay otros períodos guardados. Cambia el selector para consultarlos
              por separado.
            </p>
          )}
        </>
      )}
      {record.crops.filter((c) => !c.budget?.results).length > 0 && (
        <div className="finance-pending">
          <strong>Pendientes de presupuestar</strong>
          {record.crops
            .filter((c) => !c.budget?.results)
            .map((c) => (
              <Link key={c.id} href={budgetLink(record.id, c.id)}>
                {c.variety ||
                  data.crops.find((r) => r.crop_code === c.cropCode)?.variety ||
                  c.name}{" "}
                →
              </Link>
            ))}
        </div>
      )}
    </section>
  );
}
export function CropBenchmarks({
  crop,
  record,
  data,
}: {
  crop: ManagedCrop;
  record: FarmRecord;
  data: FarmData;
}) {
  const ref = data.crops.find((r) => r.crop_code === crop.cropCode),
    plan = crop.budget,
    template = data.templates.find(
      (t) => t.id === plan?.costSource?.templateId,
    );
  const coffee = fold(ref?.crop || crop.name) === "cafe",
    costRef = useData<Evidence>(
      coffee ? "/api/evidence/coffee-cost-benchmark" : null,
    );
  const yourYield = plan?.yieldKgHa || +crop.yieldKgHa || 0,
    productionPerHa = plan?.costsPerHa.reduce((s, c) => s + c.amount, 0),
    benchmarkCost = template?.costs.reduce((s, c) => s + c.amount, 0);
  const sameState =
    !crop.physicalState ||
    fold(crop.physicalState) === fold(ref?.physical_state || "");
  const compatibleYield =
    !!ref?.yield_kg_ha &&
    sameState &&
    !!plan &&
    plan.periodCode === (ref.cycle === "Permanente" ? "annual" : "cycle");
  return (
    <section className="panel farm-benchmarks">
      <span className="eyebrow">REFERENCIAS PARA COMPARAR</span>
      <h3>Tu cultivo y los datos publicados</h3>
      <p>
        {crop.variety || ref?.variety || crop.name} · {data.municipality.name}
      </p>
      {ref && (
        <div className="benchmark-pair">
          <div>
            <span>Tu rendimiento esperado</span>
            <strong>
              {yourYield ? number(yourYield) + " kg/ha" : "Por completar"}
            </strong>
          </div>
          <div>
            <span>EVA {ref.reference_year} · municipio</span>
            <strong>
              {ref.yield_kg_ha
                ? number(ref.yield_kg_ha) + " kg/ha"
                : "Sin dato"}
            </strong>
          </div>
          {yourYield > 0 && compatibleYield && (
            <p>
              {number((yourYield / ref.yield_kg_ha! - 1) * 100)} % frente a la
              referencia publicada.
            </p>
          )}
          <small>
            {ref.physical_state} · Producción / área cosechada. El porcentaje
            requiere un presupuesto con período y estado del producto
            comparables. Referencia municipal, no un grupo de fincas
            equivalentes.
          </small>
          <EvidenceLink
            id={ref.document_id}
            municipality={record.profile.municipalityId}
          >
            Comprobar el rendimiento
          </EvidenceLink>
        </div>
      )}
      {template &&
        benchmarkCost !== undefined &&
        productionPerHa !== undefined && (
          <div className="benchmark-pair">
            <div>
              <span>Tu costo de producción</span>
              <strong>{money(productionPerHa)}/ha</strong>
            </div>
            <div>
              <span>
                UPRA {template.reference_year} · {template.region}
              </span>
              <strong>{money(benchmarkCost)}/ha</strong>
            </div>
            <small>
              {template.production_system}. Pesos del año publicado, sin ajuste
              por inflación. Revisa que el período y las labores sean
              comparables.
            </small>
            <EvidenceLink id={template.document_id} page={template.source_page}>
              Ver la estructura de costos
            </EvidenceLink>
          </div>
        )}
      {coffee && costRef.data && (
        <div className="benchmark-pair">
          <div>
            <span>Tu producción por kg cosechado</span>
            <strong>
              {productionPerHa !== undefined && yourYield > 0 && sameState
                ? money(productionPerHa / yourYield) + "/kg"
                : "Completa tus costos"}
            </strong>
          </div>
          <div>
            <span>FEPCafé · febrero 2026 · nacional</span>
            <strong>
              {money(Number(costRef.data.metadata.cost_per_125kg) / 125)}/kg
            </strong>
          </div>
          <small>
            Referencia de pergamino seco. Tu cálculo excluye gastos de venta y
            usa la cosecha antes de pérdidas; no se interpreta como una
            clasificación entre pares.
          </small>
          <EvidenceLink id={costRef.data.id} page={6}>
            Comprobar el costo cafetero
          </EvidenceLink>
        </div>
      )}
      {!ref && (
        <p>
          Sin rendimiento municipal comparable para este cultivo. Conservamos
          tus supuestos sin inventar una referencia.
        </p>
      )}
      <details className="source-explanation">
        <summary>¿Y los costos de otras fincas del censo?</summary>
        <p>
          El Censo Nacional Agropecuario de 2014 tiene microdatos, pero no
          recoge costos de producción, precios de venta ni ingresos. Por eso no
          mostramos posiciones ni utilidades de supuestos pares. Las referencias
          de UPRA, EVA y FEPCafé conservan su región, unidad y año.
        </p>
        <a
          className="evidence-link"
          href="https://microdatos.dane.gov.co/catalog/513"
          target="_blank"
          rel="noreferrer"
        >
          Consultar el alcance del censo en DANE ↗
        </a>
      </details>
    </section>
  );
}
