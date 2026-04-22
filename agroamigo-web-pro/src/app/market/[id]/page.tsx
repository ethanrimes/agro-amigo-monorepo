'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { IoArrowBack, IoStorefront, IoLocation } from 'react-icons/io5';
import { colors, formatCOP, formatDateShort, formatKg, cachedCall } from '@agroamigo/shared';
import { getMarketById, getMarketProducts, getMarketSupplySummary, getMarketTopProducts, getMarketTopProvenance } from '@agroamigo/shared/api/markets';
import { LazyPanel } from '@/components/LazyPanel';

const TIME_RANGES = [
  { label: '1s', days: 7 },
  { label: '1m', days: 30 },
  { label: '3m', days: 90 },
  { label: '6m', days: 180 },
  { label: '1a', days: 365 },
];

export default function MarketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [market, setMarket] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const [priceTableExpanded, setPriceTableExpanded] = useState(false);
  const [supplyExpanded, setSupplyExpanded] = useState(false);
  const [timeRange, setTimeRange] = useState(1);

  const [supplySummary, setSupplySummary] = useState<any>(null);
  const [topProducts, setTopProducts] = useState<any[]>([]);
  const [topProv, setTopProv] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const [mkt, prods] = await Promise.all([
          cachedCall(`market:${id}:entity`, () => getMarketById(id!)),
          cachedCall(`market:${id}:products:200`, () => getMarketProducts(id!, 200)),
        ]);
        setMarket(mkt);
        const map = new Map<string, any>();
        for (const p of (((prods as any[]) || []))) {
          const pid = p.product_id;
          if (!map.has(pid) || p.price_date > map.get(pid).price_date) map.set(pid, p);
        }
        setProducts(Array.from(map.values()));
      } catch (err) { console.error(err); }
      finally { setLoading(false); }
    })();
  }, [id]);

  useEffect(() => {
    if (!id || !supplyExpanded) return;
    const days = TIME_RANGES[timeRange]?.days ?? 30;
    const base = `market:${id}:supply:${days}::`;
    Promise.all([
      cachedCall(`${base}summary`, () => getMarketSupplySummary(id, days, null, null)).catch(() => null),
      cachedCall(`${base}products`, () => getMarketTopProducts(id, days, null, 10)).catch(() => []),
      cachedCall(`${base}prov`, () => getMarketTopProvenance(id, days, null, 15)).catch(() => []),
    ]).then(([s, p, prov]) => {
      setSupplySummary(s);
      setTopProducts((p as any[]) || []);
      setTopProv((prov as any[]) || []);
    });
  }, [id, supplyExpanded, timeRange]);

  const productsByCategory = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const p of products) {
      const cat = p.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro';
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(p);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [products]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!market) return <div className="card"><h2>Mercado no encontrado</h2></div>;

  return (
    <div className="vstack" style={{ gap: 20 }}>
      <div className="hstack">
        <button onClick={() => router.back()} className="chip"><IoArrowBack size={14} /> Volver</button>
      </div>

      <section className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 14,
            background: `color-mix(in srgb, ${colors.primary} 12%, transparent)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <IoStorefront size={28} color={colors.primary} />
          </div>
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>{market.canonical_name}</h1>
            <div className="muted" style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}>
              <IoLocation size={13} />
              {market.dim_city?.canonical_name}{market.dim_city?.dim_department?.canonical_name ? `, ${market.dim_city.dim_department.canonical_name}` : ''}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 20 }}>
            <div className="stat"><span className="value" style={{ fontSize: 22 }}>{products.length}</span><span className="label">Productos</span></div>
            <div className="stat"><span className="value" style={{ fontSize: 22 }}>{productsByCategory.length}</span><span className="label">Categorías</span></div>
          </div>
        </div>
      </section>

      <div className="grid-2">
        <LazyPanel
          title="Productos y precios"
          badge={products.length}
          initiallyExpanded
          onExpandChange={setPriceTableExpanded}
        >
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Producto</th><th>Categoría</th><th className="num">Precio</th><th>Fecha</th></tr></thead>
              <tbody>
                {products.slice(0, 60).map((p: any) => (
                  <tr key={p.product_id} onClick={() => router.push(`/product/${p.product_id}`)} style={{ cursor: 'pointer' }}>
                    <td style={{ fontWeight: 600 }}>{p.dim_product?.canonical_name}</td>
                    <td className="muted">{p.dim_product?.dim_subcategory?.dim_category?.canonical_name || '—'}</td>
                    <td className="num" style={{ color: colors.primary, fontWeight: 600 }}>{formatCOP(p.min_price ?? p.avg_price)}{p.max_price && p.max_price !== p.min_price ? ` – ${formatCOP(p.max_price)}` : ''}</td>
                    <td className="muted">{formatDateShort(p.price_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </LazyPanel>

        <LazyPanel
          title="Abastecimiento"
          subtitle="Top productos y orígenes"
          initiallyExpanded={false}
          onExpandChange={setSupplyExpanded}
          right={supplyExpanded && (
            <div style={{ display: 'flex', gap: 4 }} onClick={e => e.stopPropagation()}>
              {TIME_RANGES.map((tr, i) => (
                <button key={tr.label} onClick={() => setTimeRange(i)} className={`chip ${i === timeRange ? 'active' : ''}`} style={{ padding: '4px 10px', fontSize: 11 }}>{tr.label}</button>
              ))}
            </div>
          )}
        >
          {supplySummary && (
            <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
              <div className="stat"><span className="value" style={{ color: colors.accent.blue, fontSize: 20 }}>{formatKg(supplySummary.total_kg || 0)}</span><span className="label">Total</span></div>
              <div className="stat"><span className="value" style={{ color: colors.accent.blue, fontSize: 20 }}>{formatKg(supplySummary.daily_avg_kg || 0)}</span><span className="label">Prom. diario</span></div>
            </div>
          )}
          <h3 style={{ fontSize: 13, margin: '0 0 10px 0', color: 'var(--color-text-secondary)' }}>Productos más abastecidos</h3>
          <BarList rows={topProducts.map((p: any) => ({ label: p.product_name, value: p.total_kg }))} color={colors.accent.blue} />
          <h3 style={{ fontSize: 13, margin: '16px 0 10px 0', color: 'var(--color-text-secondary)' }}>Principales orígenes</h3>
          <BarList rows={topProv.map((p: any) => ({ label: p.dept_name, value: p.total_kg }))} color={colors.secondary} />
        </LazyPanel>
      </div>
    </div>
  );
}

function BarList({ rows, color }: { rows: { label: string; value: number }[]; color: string }) {
  const max = rows[0]?.value || 1;
  if (rows.length === 0) return <span className="muted">Sin datos.</span>;
  return (
    <div className="vstack" style={{ gap: 8 }}>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
          <div style={{ flex: 1, height: 8, background: 'var(--color-border-light)', borderRadius: 4 }}>
            <div style={{ width: `${(r.value / max) * 100}%`, height: '100%', background: color, borderRadius: 4 }} />
          </div>
          <span className="num" style={{ width: 70, fontSize: 11, fontWeight: 600 }}>{formatKg(r.value)}</span>
        </div>
      ))}
    </div>
  );
}
