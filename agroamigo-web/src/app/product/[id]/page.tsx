'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { IoStar, IoStarOutline, IoStorefrontOutline, IoNavigateOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort, formatKg, formatPriceContext, pctChange } from '@agroamigo/shared';
import { getProductById, getProductPrices, getProductPricesByMarket } from '@agroamigo/shared/api/products';
import { getProductSupply } from '@agroamigo/shared/api/supply';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';
import { PriceChangeIndicator } from '@/components/PriceChangeIndicator';
import { ProductImage } from '@/components/ProductImage';
import { useWatchlist } from '@/context/WatchlistContext';

const TIME_RANGES = [
  { label: '1S', days: 7 }, { label: '1M', days: 30 }, { label: '3M', days: 90 },
  { label: '6M', days: 180 }, { label: '1A', days: 365 }, { label: 'Todo', days: 0 },
];
const SUPPLY_COLORS = [colors.primary, colors.accent.orange, colors.accent.blue, colors.secondary, colors.primaryLight, '#9C27B0', '#00BCD4', '#FF5722'];

function PriceChart({ data, width, height }: { data: any[]; width: number; height: number }) {
  const padding = { top: 10, right: 10, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const allPrices = data.flatMap(d => [d.min, d.max].filter(Boolean));
  const minY = Math.min(...allPrices) * 0.95;
  const maxY = Math.max(...allPrices) * 1.05;
  const rangeY = maxY - minY || 1;
  const scaleX = (i: number) => padding.left + (i / (data.length - 1)) * chartW;
  const scaleY = (v: number) => padding.top + (1 - (v - minY) / rangeY) * chartH;
  const avgPoints = data.map((d, i) => `${scaleX(i)},${scaleY(d.avg)}`).join(' ');
  const minPoints = data.map((d, i) => `${scaleX(i)},${scaleY(d.min)}`).join(' ');
  const maxPoints = data.map((d, i) => `${scaleX(i)},${scaleY(d.max)}`).join(' ');
  const yLabels = [minY, (minY + maxY) / 2, maxY].map(v => ({ value: v, y: scaleY(v), label: formatCOPCompact(v) }));
  const step = Math.max(1, Math.floor(data.length / 5));
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <svg width={width} height={height}>
      {yLabels.map((yl, i) => <line key={i} x1={padding.left} y1={yl.y} x2={width - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />)}
      {yLabels.map((yl, i) => <text key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={10} fill={colors.text.tertiary}>{yl.label}</text>)}
      {xLabels.map((d, i) => { const idx = data.indexOf(d); return <text key={`xl-${i}`} x={scaleX(idx)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatDateShort(d.date)}</text>; })}
      <polyline points={maxPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
      <polyline points={minPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
      <polyline points={avgPoints} fill="none" stroke={colors.primary} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SupplyChart({ data, width, height }: { data: { date: string; kg: number }[]; width: number; height: number }) {
  const padding = { top: 10, right: 10, bottom: 30, left: 55 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const maxY = Math.max(...data.map(d => d.kg)) * 1.1 || 1;
  const scaleX = (i: number) => padding.left + (i / (data.length - 1)) * chartW;
  const scaleY = (v: number) => padding.top + (1 - v / maxY) * chartH;
  const points = data.map((d, i) => `${scaleX(i)},${scaleY(d.kg)}`).join(' ');
  const yLabels = [0, maxY / 2, maxY].map(v => ({ y: scaleY(v), label: formatKg(v) }));
  const step = Math.max(1, Math.floor(data.length / 5));
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <svg width={width} height={height}>
      {yLabels.map((yl, i) => <line key={i} x1={padding.left} y1={yl.y} x2={width - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />)}
      {yLabels.map((yl, i) => <text key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={9} fill={colors.text.tertiary}>{yl.label}</text>)}
      {xLabels.map((d, i) => { const idx = data.indexOf(d); return <text key={`xl-${i}`} x={scaleX(idx)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatDateShort(d.date)}</text>; })}
      <polyline points={points} fill="none" stroke={colors.accent.blue} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const [product, setProduct] = useState<any>(null);
  const [prices, setPrices] = useState<any[]>([]);
  const [marketPrices, setMarketPrices] = useState<any[]>([]);
  const [supply, setSupply] = useState<any[]>([]);
  const [timeRange, setTimeRange] = useState(1);
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [selectedPresentation, setSelectedPresentation] = useState<string | null>(null);
  const [supplyTimeRange, setSupplyTimeRange] = useState(1);
  const [loading, setLoading] = useState(true);
  const chartWidth = 440;

  useEffect(() => { loadProduct(); }, [id]);
  useEffect(() => { if (id) loadPrices(); }, [id, timeRange, selectedMarketId]);
  useEffect(() => { if (id) loadSupply(); }, [id, supplyTimeRange]);

  async function loadProduct() {
    try {
      const [prod, mktPrices] = await Promise.all([getProductById(id!), getProductPricesByMarket(id!)]);
      setProduct(prod); setMarketPrices(mktPrices || []);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }
  async function loadPrices() {
    try {
      const days = TIME_RANGES[timeRange].days;
      const data = await getProductPrices(id!, { days: days === 0 ? 36500 : days, marketId: selectedMarketId || undefined, limit: days === 0 ? 10000 : 2000 });
      setPrices(data || []);
    } catch (err) { console.error(err); }
  }
  async function loadSupply() {
    try {
      const days = TIME_RANGES[supplyTimeRange].days;
      const data = await getProductSupply(id!, days === 0 ? 36500 : days);
      setSupply(data || []);
    } catch (err) { console.error(err); }
  }

  const availableMarkets = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of marketPrices) { if (p.market_id && p.dim_market?.canonical_name) map.set(p.market_id, p.dim_market.canonical_name); }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [marketPrices]);

  const availablePresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of prices) { const pres = p.dim_presentation?.canonical_name; if (pres && p.presentation_id) set.set(p.presentation_id, pres); }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [prices]);

  const filteredPrices = useMemo(() => selectedPresentation ? prices.filter(p => p.presentation_id === selectedPresentation) : prices, [prices, selectedPresentation]);

  const marketPriceRows = useMemo(() => {
    const map = new Map<string, any>();
    for (const p of marketPrices) { const key = p.market_id || 'unknown'; if (!map.has(key) || p.price_date > map.get(key).price_date) map.set(key, p); }
    return [...map.values()].sort((a, b) => (a.dim_market?.canonical_name || '').localeCompare(b.dim_market?.canonical_name || ''));
  }, [marketPrices]);

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!product) return <div className="loading-container">Producto no encontrado</div>;

  const categoryName = product.dim_subcategory?.dim_category?.canonical_name || '';
  const subcategoryName = product.dim_subcategory?.canonical_name || '';

  const priceByDate = new Map<string, { min: number; max: number; avg: number }>();
  for (const p of filteredPrices) {
    const min = p.min_price ?? p.avg_price ?? 0, max = p.max_price ?? p.avg_price ?? 0, avg = p.avg_price ?? (min + max) / 2;
    const existing = priceByDate.get(p.price_date);
    if (!existing) priceByDate.set(p.price_date, { min, max, avg });
    else { existing.min = Math.min(existing.min, min); existing.max = Math.max(existing.max, max); existing.avg = (existing.avg + avg) / 2; }
  }
  const chartData = Array.from(priceByDate.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, vals]) => ({ date, ...vals }));
  const latestPrice = chartData.length > 0 ? chartData[chartData.length - 1] : null;
  const oldestPrice = chartData.length > 1 ? chartData[0] : null;
  const priceChangeVal = latestPrice && oldestPrice ? pctChange(oldestPrice.avg, latestPrice.avg) : null;

  const supplyByDate = new Map<string, number>();
  for (const s of supply) supplyByDate.set(s.observation_date, (supplyByDate.get(s.observation_date) || 0) + (s.quantity_kg || 0));
  const supplyChartData = Array.from(supplyByDate.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, kg]) => ({ date, kg }));
  const totalSupplyKg = supply.reduce((sum, s) => sum + (s.quantity_kg || 0), 0);

  const provenanceMap = new Map<string, number>();
  for (const s of supply) { const dept = s.provenance_dept_name || 'Desconocido'; provenanceMap.set(dept, (provenanceMap.get(dept) || 0) + (s.quantity_kg || 0)); }
  const provenanceBars = Array.from(provenanceMap.entries()).map(([dept, kg]) => ({ dept, kg })).sort((a, b) => b.kg - a.kg).slice(0, 10);
  const maxProvenance = provenanceBars.length > 0 ? provenanceBars[0].kg : 1;

  const chipStyle = (active: boolean, color: string = colors.primaryDark) => ({
    padding: `${spacing.xs}px ${spacing.md}px`, borderRadius: borderRadius.full, whiteSpace: 'nowrap' as const,
    backgroundColor: active ? color : colors.surface, color: active ? colors.text.inverse : colors.text.secondary,
    border: `1px solid ${active ? color : colors.borderLight}`, cursor: 'pointer', fontSize: fontSize.xs,
  });

  return (
    <div style={{ paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ display: 'flex', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottom: `1px solid ${colors.borderLight}` }}>
        <ProductImage productName={product.canonical_name} categoryName={categoryName} style={{ width: 80, height: 80, borderRadius: borderRadius.lg, backgroundColor: colors.borderLight }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 }}>{categoryName} &gt; {subcategoryName}</span>
          <span style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>{product.canonical_name}</span>
          {latestPrice && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginTop: 4 }}>
                <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(latestPrice.min)} - {formatCOP(latestPrice.max)}</span>
                <PriceChangeIndicator value={priceChangeVal} size="md" />
              </div>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>Precio al {formatDateShort(latestPrice.date)}</span>
            </>
          )}
          <button onClick={() => toggle(id!, 'product', product.canonical_name)}
            style={{ position: 'absolute', right: spacing.lg, top: spacing.lg, background: 'none', border: 'none', cursor: 'pointer' }}>
            {isWatched(id!) ? <IoStar size={22} color="#FFD700" /> : <IoStarOutline size={22} color={colors.text.tertiary} />}
          </button>
        </div>
      </div>

      {/* Price Chart */}
      <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
        <div style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.md }}>Precios</div>
        <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.sm, flexWrap: 'wrap' }}>
          {TIME_RANGES.map((tr, i) => <button key={tr.label} onClick={() => setTimeRange(i)} style={chipStyle(i === timeRange)}>{tr.label}</button>)}
        </div>
        {availableMarkets.length > 0 && (
          <div className="chip-scroll" style={{ marginBottom: spacing.xs }}>
            <button onClick={() => setSelectedMarketId(null)} style={chipStyle(!selectedMarketId)}>Todos</button>
            {availableMarkets.map(m => <button key={m.id} onClick={() => setSelectedMarketId(selectedMarketId === m.id ? null : m.id)} style={chipStyle(selectedMarketId === m.id)}>{m.name}</button>)}
          </div>
        )}
        {availablePresentations.length > 1 && (
          <div className="chip-scroll" style={{ marginBottom: spacing.xs }}>
            <button onClick={() => setSelectedPresentation(null)} style={chipStyle(!selectedPresentation)}>Todas</button>
            {availablePresentations.map(p => <button key={p.id} onClick={() => setSelectedPresentation(selectedPresentation === p.id ? null : p.id)} style={chipStyle(selectedPresentation === p.id)}>{p.name}</button>)}
          </div>
        )}
        {chartData.length > 1 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <PriceChart data={chartData} width={chartWidth} height={200} />
            <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: spacing.sm, width: '100%' }}>
              {[{ label: 'M\u00edn', value: formatCOP(Math.min(...chartData.map(d => d.min))) },
                { label: 'Prom', value: formatCOP(chartData.reduce((s, d) => s + d.avg, 0) / chartData.length), color: colors.primary },
                { label: 'M\u00e1x', value: formatCOP(Math.max(...chartData.map(d => d.max))) }]
                .map(s => (
                  <div key={s.label} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{s.label}</div>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: s.color || colors.text.primary, fontFamily: 'monospace' }}>{s.value}</div>
                  </div>
                ))}
            </div>
          </div>
        ) : <p style={{ textAlign: 'center', padding: `${spacing.xxl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>Sin datos de precios para este per&iacute;odo</p>}
      </Card>

      {/* Prices by Market */}
      {marketPriceRows.length > 0 && (
        <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
          <ExpandableSection title="Precios por mercado" icon={<IoStorefrontOutline size={16} color={colors.text.secondary} />} badge={marketPriceRows.length} initiallyExpanded={false}>
            {marketPriceRows.map((p: any, i: number) => {
              const ctx = formatPriceContext(p.dim_presentation?.canonical_name, p.dim_units?.canonical_name);
              return (
                <div key={p.market_id || i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: `${spacing.sm}px 0`, borderBottom: `1px solid ${colors.borderLight}` }}>
                  <div style={{ flex: 1, marginRight: spacing.sm }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.dim_market?.canonical_name || 'Mercado'}</div>
                    {ctx && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{ctx}</div>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(p.min_price)}{p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}</div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{formatDateShort(p.price_date)}</div>
                  </div>
                </div>
              );
            })}
          </ExpandableSection>
        </Card>
      )}

      {/* Supply */}
      <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
        <div style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.md }}>Abastecimiento</div>
        <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.sm, flexWrap: 'wrap' }}>
          {TIME_RANGES.map((tr, i) => <button key={`sup-${tr.label}`} onClick={() => setSupplyTimeRange(i)} style={chipStyle(i === supplyTimeRange, colors.accent.blue)}>{tr.label}</button>)}
        </div>
        <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.md }}>
          {[{ value: formatKg(totalSupplyKg), label: 'Total' }, ...(supplyChartData.length > 0 ? [{ value: formatKg(supplyChartData[0].kg), label: formatDateShort(supplyChartData[0].date) }] : [])]
            .map(s => (
              <div key={s.label} style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, textAlign: 'center' }}>
                <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.accent.blue }}>{s.value}</div>
                <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{s.label}</div>
              </div>
            ))}
        </div>
        {supplyChartData.length > 1 ? (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <SupplyChart data={supplyChartData} width={chartWidth} height={200} />
          </div>
        ) : supply.length === 0 ? <p style={{ textAlign: 'center', color: colors.text.tertiary, fontSize: fontSize.sm }}>Sin datos de abastecimiento</p> : null}
      </Card>

      {/* Provenance */}
      {provenanceBars.length > 0 && (
        <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
          <ExpandableSection title="Procedencia" icon={<IoNavigateOutline size={16} color={colors.text.secondary} />} badge={provenanceBars.length} subtitle="Departamentos de origen" initiallyExpanded>
            <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
              {provenanceBars.map((d, i) => (
                <div key={d.dept} style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
                  <span style={{ width: 80, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.dept}</span>
                  <div style={{ flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(d.kg / maxProvenance) * 100}%`, backgroundColor: SUPPLY_COLORS[i % SUPPLY_COLORS.length], borderRadius: 4 }} />
                  </div>
                  <span style={{ width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: 600 }}>{formatKg(d.kg)}</span>
                </div>
              ))}
            </div>
          </ExpandableSection>
        </Card>
      )}
    </div>
  );
}
