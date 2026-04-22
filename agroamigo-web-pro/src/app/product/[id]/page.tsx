'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { IoArrowBack, IoTrendingUp, IoTrendingDown, IoStarOutline, IoStar } from 'react-icons/io5';
import { colors, formatCOP, formatCOPCompact, formatDateShort, formatKg, pctChange, cachedCall } from '@agroamigo/shared';
import { getProductById, getProductPrices, getProductPricesByMarket } from '@agroamigo/shared/api/products';
import { getProductSupplySummary, getProductSupplyByDate, getProductTopDestinations, getProductTopOrigins } from '@agroamigo/shared/api/supply';
import { LazyPanel } from '@/components/LazyPanel';
import { ResponsiveChart } from '@/components/ResponsiveChart';
import { useWatchlist } from '@/context/WatchlistContext';

const TIME_RANGES = [
  { label: '1s', days: 7 },
  { label: '1m', days: 30 },
  { label: '3m', days: 90 },
  { label: '6m', days: 180 },
  { label: '1a', days: 365 },
  { label: 'Todo', days: 0 },
];

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { isWatched, toggle } = useWatchlist();

  const [product, setProduct] = useState<any>(null);
  const [marketPrices, setMarketPrices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // lazy states
  const [priceExpanded, setPriceExpanded] = useState(false);
  const [marketTableExpanded, setMarketTableExpanded] = useState(false);
  const [supplyExpanded, setSupplyExpanded] = useState(false);

  const [prices, setPrices] = useState<any[]>([]);
  const [supplySummary, setSupplySummary] = useState<any>(null);
  const [supplyByDate, setSupplyByDate] = useState<{ date: string; kg: number }[]>([]);
  const [topDest, setTopDest] = useState<any[]>([]);
  const [topOrigin, setTopOrigin] = useState<any[]>([]);

  const [timeRange, setTimeRange] = useState(1);

  useEffect(() => {
    (async () => {
      try {
        const [prod, mkt] = await Promise.all([
          cachedCall(`product:${id}:entity`, () => getProductById(id!)),
          cachedCall(`product:${id}:prices-by-market`, () => getProductPricesByMarket(id!)),
        ]);
        setProduct(prod);
        setMarketPrices(((mkt as any[]) || []));
      } catch (err) { console.error(err); }
      finally { setLoading(false); }
    })();
  }, [id]);

  // Price history — lazy
  useEffect(() => {
    if (!id || !priceExpanded) return;
    cachedCall(`product:${id}:prices:all`, () => getProductPrices(id, { days: 36500, limit: 5000 }))
      .then(d => setPrices(((d as any[]) || [])))
      .catch(e => console.error(e));
  }, [id, priceExpanded]);

  // Supply — lazy, refetches on time range change
  useEffect(() => {
    if (!id || !supplyExpanded) return;
    const days = TIME_RANGES[timeRange]?.days ?? 30;
    const base = `product:${id}:supply:${days}::`;
    Promise.all([
      cachedCall(`${base}summary`, () => getProductSupplySummary(id, days, null, null)).catch(() => null),
      cachedCall(`${base}byDate`, () => getProductSupplyByDate(id, days, null, null)).catch(() => []),
      cachedCall(`${base}dest`, () => getProductTopDestinations(id, days, null, 10)).catch(() => []),
      cachedCall(`${base}origin`, () => getProductTopOrigins(id, days, null, 10)).catch(() => []),
    ]).then(([s, byDate, dest, origin]) => {
      setSupplySummary(s);
      setSupplyByDate((byDate as any) || []);
      setTopDest((dest as any[]) || []);
      setTopOrigin((origin as any[]) || []);
    });
  }, [id, supplyExpanded, timeRange]);

  const headerInfo = useMemo(() => {
    if (marketPrices.length === 0) return null;
    const latestDate = marketPrices.reduce((a: string, p: any) => p.price_date > a ? p.price_date : a, '');
    const same = marketPrices.filter((p: any) => p.price_date === latestDate);
    const mins = same.map((p: any) => p.min_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
    const maxs = same.map((p: any) => p.max_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
    const minP = mins.length ? mins.reduce((s: number, v: number) => s + v, 0) / mins.length : 0;
    const maxP = maxs.length ? maxs.reduce((s: number, v: number) => s + v, 0) / maxs.length : 0;
    // week-ago comparison
    const weekAgo = new Date(latestDate); weekAgo.setDate(weekAgo.getDate() - 7);
    const weekStr = weekAgo.toISOString().split('T')[0];
    const prev = marketPrices.filter((p: any) => p.price_date <= weekStr);
    let change: number | null = null;
    if (prev.length > 0) {
      const prevDate = prev.reduce((a: string, p: any) => p.price_date > a ? p.price_date : a, '');
      const prevSame = prev.filter((p: any) => p.price_date === prevDate);
      const pMins = prevSame.map((p: any) => p.min_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
      const pMaxs = prevSame.map((p: any) => p.max_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
      const prevMin = pMins.length ? pMins.reduce((s: number, v: number) => s + v, 0) / pMins.length : 0;
      const prevMax = pMaxs.length ? pMaxs.reduce((s: number, v: number) => s + v, 0) / pMaxs.length : 0;
      const prevAvg = (prevMin + prevMax) / 2;
      const curAvg = (minP + maxP) / 2;
      if (prevAvg > 0 && curAvg > 0) change = pctChange(prevAvg, curAvg);
    }
    return { latestDate, minP, maxP, change, marketCount: new Set(marketPrices.map((p: any) => p.market_id)).size };
  }, [marketPrices]);

  const chartData = useMemo(() => {
    const tr = TIME_RANGES[timeRange];
    let rows = prices;
    if (tr && tr.days > 0) {
      const since = new Date(); since.setDate(since.getDate() - tr.days);
      const sinceStr = since.toISOString().split('T')[0];
      rows = rows.filter((p: any) => p.price_date >= sinceStr);
    }
    const byDate = new Map<string, { sum: number; count: number; min: number; max: number }>();
    for (const p of rows) {
      const v = (p.min_price != null && p.min_price > 0 && p.max_price != null && p.max_price > 0)
        ? (p.min_price + p.max_price) / 2
        : p.avg_price;
      if (!v || v <= 0) continue;
      const ex = byDate.get(p.price_date);
      if (ex) {
        ex.sum += v; ex.count++;
        ex.min = Math.min(ex.min, p.min_price ?? v);
        ex.max = Math.max(ex.max, p.max_price ?? v);
      } else {
        byDate.set(p.price_date, { sum: v, count: 1, min: p.min_price ?? v, max: p.max_price ?? v });
      }
    }
    return Array.from(byDate.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, vals]) => ({ date, value: vals.sum / vals.count, min: vals.min, max: vals.max }));
  }, [prices, timeRange]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!product) return <div className="card"><h2>Producto no encontrado</h2></div>;

  return (
    <div className="vstack" style={{ gap: 20 }}>
      {/* Back + header */}
      <div className="hstack">
        <button onClick={() => router.back()} className="chip">
          <IoArrowBack size={14} /> Volver
        </button>
        <span className="spacer" />
        <button
          onClick={() => toggle(id!, 'product', product.canonical_name)}
          className="chip"
          style={{ color: isWatched(id!) ? '#c7a700' : undefined }}
        >
          {isWatched(id!) ? <IoStar size={14} /> : <IoStarOutline size={14} />}
          {isWatched(id!) ? 'En seguimiento' : 'Seguir'}
        </button>
      </div>

      <section className="card">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 300px' }}>
            <div className="muted" style={{ textTransform: 'uppercase', fontSize: 11, letterSpacing: 0.4 }}>
              {product.dim_subcategory?.dim_category?.canonical_name} &rsaquo; {product.dim_subcategory?.canonical_name}
            </div>
            <h1 style={{ margin: '4px 0 10px 0', fontSize: 26, fontWeight: 700 }}>{product.canonical_name}</h1>
            {headerInfo && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                <div className="stat">
                  <span className="value" style={{ color: colors.primary }}>
                    {formatCOP(headerInfo.minP)}
                    {headerInfo.maxP !== headerInfo.minP ? ` – ${formatCOP(headerInfo.maxP)}` : ''}
                  </span>
                  <span className="label">Rango nacional · {formatDateShort(headerInfo.latestDate)}</span>
                </div>
                {headerInfo.change != null && (
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '6px 12px', borderRadius: 999,
                    background: headerInfo.change > 0
                      ? `color-mix(in srgb, ${colors.accent.orange} 15%, transparent)`
                      : `color-mix(in srgb, ${colors.accent.blue} 15%, transparent)`,
                    color: headerInfo.change > 0 ? colors.accent.orange : colors.accent.blue,
                    fontWeight: 600, fontSize: 13,
                  }}>
                    {headerInfo.change > 0 ? <IoTrendingUp size={14} /> : <IoTrendingDown size={14} />}
                    {headerInfo.change > 0 ? '+' : ''}{headerInfo.change.toFixed(1)}% vs semana anterior
                  </div>
                )}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <div className="stat">
              <span className="value" style={{ fontSize: 22 }}>{headerInfo?.marketCount ?? 0}</span>
              <span className="label">Mercados</span>
            </div>
            <div className="stat">
              <span className="value" style={{ fontSize: 22 }}>{marketPrices.length}</span>
              <span className="label">Observaciones</span>
            </div>
          </div>
        </div>
      </section>

      <div className="grid-2">
        {/* Main chart column */}
        <div className="vstack" style={{ gap: 16 }}>
          <LazyPanel
            title="Historial de precios"
            subtitle="Promedio diario a nivel nacional"
            initiallyExpanded={false}
            onExpandChange={setPriceExpanded}
            right={priceExpanded && (
              <div style={{ display: 'flex', gap: 4 }} onClick={e => e.stopPropagation()}>
                {TIME_RANGES.map((tr, i) => (
                  <button key={tr.label} onClick={() => setTimeRange(i)}
                    className={`chip ${i === timeRange ? 'active' : ''}`}
                    style={{ padding: '4px 10px', fontSize: 11 }}>{tr.label}</button>
                ))}
              </div>
            )}
          >
            {chartData.length > 1 ? (
              <ResponsiveChart
                data={chartData}
                height={320}
                color={colors.primary}
                showBands
                formatValue={formatCOPCompact}
              />
            ) : priceExpanded ? (
              <p className="muted" style={{ textAlign: 'center', padding: 40 }}>Sin suficientes datos para graficar.</p>
            ) : null}
          </LazyPanel>

          <LazyPanel
            title="Abastecimiento"
            subtitle="Volumen agregado (kg) y orígenes"
            initiallyExpanded={false}
            onExpandChange={setSupplyExpanded}
            right={supplyExpanded && (
              <div style={{ display: 'flex', gap: 4 }} onClick={e => e.stopPropagation()}>
                {TIME_RANGES.map((tr, i) => (
                  <button key={tr.label} onClick={() => setTimeRange(i)}
                    className={`chip ${i === timeRange ? 'active' : ''}`}
                    style={{ padding: '4px 10px', fontSize: 11 }}>{tr.label}</button>
                ))}
              </div>
            )}
          >
            {supplySummary && (
              <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
                <div className="stat">
                  <span className="value" style={{ color: colors.accent.blue, fontSize: 20 }}>{formatKg(supplySummary.total_kg || 0)}</span>
                  <span className="label">Total</span>
                </div>
                <div className="stat">
                  <span className="value" style={{ color: colors.accent.blue, fontSize: 20 }}>{formatKg(supplySummary.daily_avg_kg || 0)}</span>
                  <span className="label">Promedio diario</span>
                </div>
              </div>
            )}
            {supplyByDate.length > 1 && (
              <ResponsiveChart
                data={supplyByDate.map(d => ({ date: d.date, value: d.kg }))}
                height={240}
                color={colors.accent.blue}
                formatValue={formatKg}
              />
            )}
            <div className="grid-2" style={{ marginTop: 16, gap: 16 }}>
              <BarList title="Mercados destino" rows={topDest.map((d: any) => ({ label: d.market_name, value: d.total_kg }))} color={colors.accent.blue} />
              <BarList title="Orígenes (departamento)" rows={topOrigin.map((d: any) => ({ label: d.dept_name, value: d.total_kg }))} color={colors.secondary} />
            </div>
          </LazyPanel>
        </div>

        {/* Side column */}
        <div className="vstack" style={{ gap: 16 }}>
          <LazyPanel
            title="Precios por mercado"
            badge={marketPrices.length}
            initiallyExpanded={false}
            onExpandChange={setMarketTableExpanded}
          >
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Mercado</th><th className="num">Precio</th><th>Fecha</th></tr>
                </thead>
                <tbody>
                  {marketPrices.slice(0, 30).map((p: any, i: number) => (
                    <tr key={p.market_id || i} onClick={() => p.market_id && router.push(`/market/${p.market_id}`)} style={{ cursor: p.market_id ? 'pointer' : 'default' }}>
                      <td>{p.dim_market?.canonical_name || '—'}</td>
                      <td className="num" style={{ color: colors.primary, fontWeight: 600 }}>{formatCOP(p.min_price ?? p.avg_price)}{p.max_price && p.max_price !== p.min_price ? ` – ${formatCOP(p.max_price)}` : ''}</td>
                      <td className="muted">{formatDateShort(p.price_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </LazyPanel>
        </div>
      </div>
    </div>
  );
}

function BarList({ title, rows, color }: { title: string; rows: { label: string; value: number }[]; color: string }) {
  const max = rows[0]?.value || 1;
  return (
    <div>
      <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 10px 0', color: 'var(--color-text-secondary)' }}>{title}</h3>
      <div className="vstack" style={{ gap: 8 }}>
        {rows.length === 0 && <span className="muted">Sin datos.</span>}
        {rows.map((r, i) => (
          <div key={`${r.label}-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
            <div style={{ flex: 1, height: 8, background: 'var(--color-border-light)', borderRadius: 4 }}>
              <div style={{ width: `${(r.value / max) * 100}%`, height: '100%', background: color, borderRadius: 4 }} />
            </div>
            <span className="num" style={{ width: 70, fontSize: 11, fontWeight: 600 }}>{formatKg(r.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
