'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { IoStar, IoStarOutline, IoStorefrontOutline, IoNavigateOutline, IoPricetagsOutline, IoCubeOutline, IoArrowUp, IoArrowDown } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOP, formatCOPCompact, formatDateShort, formatKg, formatPriceContext, pctChange } from '@agroamigo/shared';
import { getProductById, getProductPrices, getProductPricesByMarket } from '@agroamigo/shared/api/products';
import { getProductSupply } from '@agroamigo/shared/api/supply';
import { Card } from '@/components/Card';
import { ExpandableSection } from '@/components/ExpandableSection';
import { PriceChangeIndicator } from '@/components/PriceChangeIndicator';
import { ProductImage } from '@/components/ProductImage';
import { LineChart } from '@/components/LineChart';
import { useWatchlist } from '@/context/WatchlistContext';
import { useLanguage } from '@/context/LanguageContext';
import { useSettings } from '@/context/SettingsContext';
import { CommentsSection } from '@/components/CommentsSection';

const SUPPLY_COLORS = [colors.primary, colors.accent.orange, colors.accent.blue, colors.secondary, colors.primaryLight, '#9C27B0', '#00BCD4', '#FF5722'];

/** Format market name with municipality: "Market (Municipality)" */
function fmtMarket(m: any): string {
  const name = m?.canonical_name || '';
  const city = m?.dim_city?.canonical_name || '';
  if (!city || name.toLowerCase().includes(city.toLowerCase())) return name;
  return `${name} (${city})`;
}

/** Build a composite key for presentation + units */
function presKey(p: any): string {
  return `${p.presentation_id || ''}|${p.units_id || ''}`;
}
function presLabel(p: any): string {
  return [p.dim_presentation?.canonical_name, p.dim_units?.canonical_name].filter(Boolean).join(' \u00b7 ');
}

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const { t } = useLanguage();
  const { settings } = useSettings();
  const [product, setProduct] = useState<any>(null);
  const [prices, setPrices] = useState<any[]>([]);
  const [marketPrices, setMarketPrices] = useState<any[]>([]);
  const [supply, setSupply] = useState<any[]>([]);
  const [timeRange, setTimeRange] = useState<number | null>(null);
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [selectedPresentation, setSelectedPresentation] = useState<string | null>(null);
  const [supplyTimeRange, setSupplyTimeRange] = useState<number | null>(null);
  const [supplyMarketId, setSupplyMarketId] = useState<string | null>(null);
  const [provTimeRange, setProvTimeRange] = useState<number | null>(null);
  const [provMarketId, setProvMarketId] = useState<string | null>(null);
  const [mktPresFilter, setMktPresFilter] = useState<string | null>(null);
  const [mktSortAsc, setMktSortAsc] = useState(false);
  const [showWeekTooltip, setShowWeekTooltip] = useState(false);
  const [loading, setLoading] = useState(true);
  const chartWidth = 440;

  const TIME_RANGES = [
    { label: t.time_1w, days: 7 }, { label: t.time_1m, days: 30 }, { label: t.time_3m, days: 90 },
    { label: t.time_6m, days: 180 }, { label: t.time_1y, days: 365 }, { label: t.time_all, days: 0 },
  ];

  useEffect(() => { loadProduct(); }, [id]);
  useEffect(() => { if (id) loadPrices(); }, [id]);
  useEffect(() => { if (id) loadSupply(); }, [id]);

  async function loadProduct() {
    try {
      const [prod, mktPrices] = await Promise.all([getProductById(id!), getProductPricesByMarket(id!)]);
      setProduct(prod); setMarketPrices(mktPrices || []);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }
  async function loadPrices() {
    try {
      const data = await getProductPrices(id!, { days: 36500, limit: 5000 });
      setPrices(data || []);
    } catch (err) { console.error(err); }
  }
  async function loadSupply() {
    try {
      const data = await getProductSupply(id!, 36500);
      setSupply(data || []);
    } catch (err) { console.error(err); }
  }

  // ═══ PRICE CASCADE: time range → market → presentation ═══

  // 1. Available time ranges (from ALL price data)
  const availablePriceRanges = useMemo(() => {
    if (prices.length === 0) return [];
    const newest = prices[0]?.price_date;
    if (!newest) return [];
    const today = new Date();
    const daysOld = Math.ceil((today.getTime() - new Date(newest + 'T00:00:00').getTime()) / 86400000);
    return TIME_RANGES.map((tr, i) => ({ ...tr, index: i, hasData: tr.days === 0 || daysOld <= tr.days })).filter(tr => tr.hasData);
  }, [prices]);

  useEffect(() => {
    if (availablePriceRanges.length > 0 && (timeRange === null || !availablePriceRanges.some(r => r.index === timeRange)))
      setTimeRange(availablePriceRanges[0].index);
  }, [availablePriceRanges]);

  // 2. Time-filtered prices
  const timeFilteredPrices = useMemo(() => {
    const tr = TIME_RANGES[timeRange ?? 0];
    if (!tr || tr.days === 0) return prices;
    const since = new Date(); since.setDate(since.getDate() - tr.days);
    const sinceStr = since.toISOString().split('T')[0];
    return prices.filter(p => p.price_date >= sinceStr);
  }, [prices, timeRange]);

  // 3. Available markets (from time-filtered prices)
  const availableMarkets = useMemo(() => {
    const map = new Map<string, { id: string; name: string }>();
    for (const p of timeFilteredPrices) {
      if (p.market_id && p.dim_market?.canonical_name && !map.has(p.market_id))
        map.set(p.market_id, { id: p.market_id, name: fmtMarket(p.dim_market) });
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [timeFilteredPrices]);

  useEffect(() => {
    if (selectedMarketId && !availableMarkets.some(m => m.id === selectedMarketId))
      setSelectedMarketId(null);
  }, [availableMarkets]);

  // 4. Market-filtered prices
  const marketFilteredPrices = useMemo(() => {
    if (!selectedMarketId) return timeFilteredPrices;
    return timeFilteredPrices.filter(p => p.market_id === selectedMarketId);
  }, [timeFilteredPrices, selectedMarketId]);

  // 5. Available presentations (from market-filtered prices)
  const availablePresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of marketFilteredPrices) {
      const pres = p.dim_presentation?.canonical_name;
      if (pres && p.presentation_id) {
        const key = presKey(p);
        if (!set.has(key)) set.set(key, presLabel(p));
      }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [marketFilteredPrices]);

  useEffect(() => {
    if (selectedPresentation && !availablePresentations.some(p => p.id === selectedPresentation))
      setSelectedPresentation(availablePresentations.length > 0 ? availablePresentations[0].id : null);
    else if (!selectedPresentation && availablePresentations.length > 0)
      setSelectedPresentation(availablePresentations[0].id);
  }, [availablePresentations]);

  // 6. Final filtered prices (by presentation — null means all)
  const filteredPrices = useMemo(() => {
    if (!selectedPresentation) return marketFilteredPrices;
    return marketFilteredPrices.filter(p => presKey(p) === selectedPresentation);
  }, [marketFilteredPrices, selectedPresentation]);

  // ── Market-level presentation combos (for Prices by Market section) ──
  const mktPresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of marketPrices) {
      const pres = p.dim_presentation?.canonical_name;
      if (pres && p.presentation_id) {
        const key = presKey(p);
        if (!set.has(key)) set.set(key, presLabel(p));
      }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [marketPrices]);

  // ── Header: most common pres+units on the latest date; prices averaged within that bucket ──
  const headerInfo = useMemo(() => {
    if (marketPrices.length === 0) return { latestObs: null, mostCommonPres: '', geoSource: t.product_national_avg, weekChange: null, displayMin: 0, displayMax: 0 };

    let latestDateAll = '';
    for (const p of marketPrices) if (p.price_date > latestDateAll) latestDateAll = p.price_date;

    const recentObs = latestDateAll ? marketPrices.filter(p => p.price_date === latestDateAll) : marketPrices;
    const presCounts = new Map<string, { count: number; label: string }>();
    for (const p of recentObs) {
      const key = presKey(p);
      const existing = presCounts.get(key);
      if (existing) existing.count++;
      else presCounts.set(key, { count: 1, label: presLabel(p) });
    }
    let mostCommonPresKey = ''; let mostCommonPres = ''; let maxCount = 0;
    for (const [key, v] of presCounts) { if (v.count > maxCount) { maxCount = v.count; mostCommonPres = v.label; mostCommonPresKey = key; } }

    // Restrict to the most-common presentation+units bucket so prices are comparable
    const bucket = mostCommonPresKey ? marketPrices.filter(p => presKey(p) === mostCommonPresKey) : marketPrices;

    const dm = settings.defaultMarket;
    let latestObs: any = null;
    let geoSource = t.product_national_avg;
    let displayMin = 0; let displayMax = 0;

    if (dm.level === 'mercado' && dm.id) {
      const matches = bucket.filter(p => p.market_id === dm.id);
      if (matches.length > 0) {
        latestObs = matches.reduce((a, b) => a.price_date > b.price_date ? a : b);
        geoSource = fmtMarket(latestObs.dim_market);
        displayMin = latestObs.min_price ?? latestObs.avg_price ?? 0;
        displayMax = latestObs.max_price ?? latestObs.avg_price ?? 0;
      }
    }
    if (!latestObs && bucket.length > 0) {
      // National avg: latest date in bucket, then average min/max across markets on that date
      const latestDate = bucket.reduce((a: string, p: any) => p.price_date > a ? p.price_date : a, '');
      const sameDay = bucket.filter((p: any) => p.price_date === latestDate);
      const mins = sameDay.map((p: any) => p.min_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
      const maxs = sameDay.map((p: any) => p.max_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
      if (mins.length > 0) displayMin = mins.reduce((s: number, v: number) => s + v, 0) / mins.length;
      if (maxs.length > 0) displayMax = maxs.reduce((s: number, v: number) => s + v, 0) / maxs.length;
      latestObs = { price_date: latestDate, dim_market: null };
      geoSource = t.product_national_avg;
    }

    let weekChange: number | null = null;
    if (latestObs) {
      const latestDate = new Date(latestObs.price_date);
      const weekAgo = new Date(latestDate); weekAgo.setDate(weekAgo.getDate() - 7);
      const weekAgoStr = weekAgo.toISOString().split('T')[0];
      const candidates = dm.level === 'mercado' && dm.id
        ? bucket.filter(p => p.market_id === dm.id && p.price_date <= weekAgoStr)
        : bucket.filter(p => p.price_date <= weekAgoStr);
      if (candidates.length > 0) {
        const curAvg = (displayMin + displayMax) / 2;
        let prevAvg = 0;
        if (dm.level === 'mercado' && dm.id) {
          const prev = candidates.reduce((a: any, b: any) => a.price_date > b.price_date ? a : b);
          prevAvg = prev.avg_price || (prev.min_price + prev.max_price) / 2;
        } else {
          const prevDate = candidates.reduce((a: string, p: any) => p.price_date > a ? p.price_date : a, '');
          const prevDay = candidates.filter((p: any) => p.price_date === prevDate);
          const pMins = prevDay.map((p: any) => p.min_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
          const pMaxs = prevDay.map((p: any) => p.max_price ?? p.avg_price).filter((v: any) => typeof v === 'number' && v > 0);
          const pMin = pMins.length > 0 ? pMins.reduce((s: number, v: number) => s + v, 0) / pMins.length : 0;
          const pMax = pMaxs.length > 0 ? pMaxs.reduce((s: number, v: number) => s + v, 0) / pMaxs.length : 0;
          prevAvg = (pMin + pMax) / 2;
        }
        if (prevAvg > 0 && curAvg > 0) weekChange = pctChange(prevAvg, curAvg);
      }
    }

    return { latestObs, mostCommonPres, geoSource, weekChange, displayMin, displayMax };
  }, [marketPrices, settings.defaultMarket, t]);

  // ── Prices by market (filtered by mktPresFilter, sorted) ──
  const marketPriceRows = useMemo(() => {
    let rows = [...marketPrices];
    if (mktPresFilter) {
      const [presId, unitsId] = mktPresFilter.split('|');
      rows = rows.filter(p => p.presentation_id === presId && (p.units_id || '') === unitsId);
    }
    const map = new Map<string, any>();
    for (const p of rows) { const key = p.market_id || 'unknown'; if (!map.has(key) || p.price_date > map.get(key).price_date) map.set(key, p); }
    const sorted = [...map.values()].sort((a, b) => {
      const aPrice = a.avg_price || a.min_price || 0;
      const bPrice = b.avg_price || b.min_price || 0;
      return mktSortAsc ? aPrice - bPrice : bPrice - aPrice;
    });
    return sorted;
  }, [marketPrices, mktPresFilter, mktSortAsc]);

  // Median and mean for market prices
  const mktStats = useMemo(() => {
    const avgPrices = marketPriceRows.map(p => p.avg_price || (p.min_price + p.max_price) / 2).filter(v => v > 0);
    if (avgPrices.length === 0) return { median: 0, mean: 0 };
    const sorted = [...avgPrices].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
    const mean = avgPrices.reduce((s, v) => s + v, 0) / avgPrices.length;
    return { median, mean };
  }, [marketPriceRows]);

  // ═══ SUPPLY CASCADE: time range → market ═══

  const availableSupplyRanges = useMemo(() => {
    if (supply.length === 0) return [];
    const newest = supply.reduce((max: string, s: any) => s.observation_date > max ? s.observation_date : max, supply[0].observation_date);
    const daysOld = Math.ceil((new Date().getTime() - new Date(newest + 'T00:00:00').getTime()) / 86400000);
    return TIME_RANGES.map((tr, i) => ({ ...tr, index: i, hasData: tr.days === 0 || daysOld <= tr.days })).filter(tr => tr.hasData);
  }, [supply]);

  useEffect(() => {
    if (availableSupplyRanges.length > 0 && (supplyTimeRange === null || !availableSupplyRanges.some(r => r.index === supplyTimeRange)))
      setSupplyTimeRange(availableSupplyRanges[0].index);
  }, [availableSupplyRanges]);

  const timeFilteredSupply = useMemo(() => {
    const tr = TIME_RANGES[supplyTimeRange ?? 0];
    if (!tr || tr.days === 0) return supply;
    const since = new Date(); since.setDate(since.getDate() - tr.days);
    const sinceStr = since.toISOString().split('T')[0];
    return supply.filter(s => s.observation_date >= sinceStr);
  }, [supply, supplyTimeRange]);

  const supplyMarkets = useMemo(() => {
    const set = new Map<string, string>();
    for (const s of timeFilteredSupply) {
      if (s.market_id && !set.has(s.market_id)) {
        if (s.dim_market?.canonical_name) set.set(s.market_id, fmtMarket(s.dim_market));
      }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [timeFilteredSupply]);

  useEffect(() => {
    if (supplyMarketId && !supplyMarkets.some(m => m.id === supplyMarketId))
      setSupplyMarketId(null);
  }, [supplyMarkets]);

  const filteredSupply = useMemo(() => {
    if (!supplyMarketId) return timeFilteredSupply;
    return timeFilteredSupply.filter(s => s.market_id === supplyMarketId);
  }, [timeFilteredSupply, supplyMarketId]);

  const supplyByDate = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of filteredSupply) map.set(s.observation_date, (map.get(s.observation_date) || 0) + (s.quantity_kg || 0));
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, kg]) => ({ date, kg }));
  }, [filteredSupply]);

  const totalSupplyKg = filteredSupply.reduce((sum, s) => sum + (s.quantity_kg || 0), 0);
  const supplyDays = supplyByDate.length || 1;
  const dailyAvgKg = totalSupplyKg / supplyDays;

  // ═══ PROVENANCE CASCADE: time range → market ═══

  const timeFilteredProv = useMemo(() => {
    const tr = TIME_RANGES[provTimeRange ?? 0];
    if (!tr || tr.days === 0) return supply;
    const since = new Date(); since.setDate(since.getDate() - tr.days);
    const sinceStr = since.toISOString().split('T')[0];
    return supply.filter(s => s.observation_date >= sinceStr);
  }, [supply, provTimeRange]);

  const provMarkets = useMemo(() => {
    const set = new Map<string, string>();
    for (const s of timeFilteredProv) {
      if (s.market_id && !set.has(s.market_id)) {
        if (s.dim_market?.canonical_name) set.set(s.market_id, fmtMarket(s.dim_market));
      }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [timeFilteredProv]);

  useEffect(() => {
    if (provMarketId && !provMarkets.some(m => m.id === provMarketId))
      setProvMarketId(null);
  }, [provMarkets]);

  const filteredProvSupply = useMemo(() => {
    if (!provMarketId) return timeFilteredProv;
    return timeFilteredProv.filter(s => s.market_id === provMarketId);
  }, [timeFilteredProv, provMarketId]);

  const provenanceBars = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of filteredProvSupply) {
      const dept = s.provenance_dept_name || t.product_unknown;
      map.set(dept, (map.get(dept) || 0) + (s.quantity_kg || 0));
    }
    return Array.from(map.entries()).map(([dept, kg]) => ({ dept, kg })).sort((a, b) => b.kg - a.kg).slice(0, 15);
  }, [filteredProvSupply, t]);

  const provTotal = provenanceBars.reduce((s, d) => s + d.kg, 0);
  const maxProvenance = provenanceBars.length > 0 ? provenanceBars[0].kg : 1;

  if (loading) return <div className="loading-container"><div className="spinner" /></div>;
  if (!product) return <div className="loading-container">{t.product_not_found}</div>;

  const categoryName = product.dim_subcategory?.dim_category?.canonical_name || '';
  const subcategoryName = product.dim_subcategory?.canonical_name || '';

  // ── Price chart data ──
  // Compute avg from (min+max)/2 client-side — most observations have null avg_price
  const priceByDate = new Map<string, { min: number; max: number; avg: number; count: number }>();
  for (const p of filteredPrices) {
    // Fall back to avg_price when min/max are null OR zero (some observations only carry avg_price)
    const rawMin = (p.min_price != null && p.min_price > 0) ? p.min_price : (p.avg_price ?? p.max_price);
    const rawMax = (p.max_price != null && p.max_price > 0) ? p.max_price : (p.avg_price ?? p.min_price);
    const min = rawMin;
    const max = rawMax;
    if (min == null || max == null || (min <= 0 && max <= 0)) continue;
    const avg = (min + max) / 2;
    const existing = priceByDate.get(p.price_date);
    if (!existing) priceByDate.set(p.price_date, { min, max, avg, count: 1 });
    else { existing.min = Math.min(existing.min, min); existing.max = Math.max(existing.max, max); existing.avg = (existing.avg * existing.count + avg) / (existing.count + 1); existing.count++; }
  }
  const chartData = Array.from(priceByDate.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, vals]) => ({ date, ...vals }));

  const selectedPresLabel = selectedPresentation
    ? availablePresentations.find(p => p.id === selectedPresentation)?.name || ''
    : availablePresentations.map(p => p.name).join(', ');

  const chipStyle = (active: boolean, color: string = colors.primaryDark) => ({
    padding: `${spacing.xs}px ${spacing.md}px`, borderRadius: borderRadius.full, whiteSpace: 'nowrap' as const,
    backgroundColor: active ? color : colors.surface, color: active ? colors.text.inverse : colors.text.secondary,
    border: `1px solid ${active ? color : colors.borderLight}`, cursor: 'pointer', fontSize: fontSize.xs,
  });

  return (
    <div style={{ paddingBottom: 40 }}>
      {/* ══ HEADER ══ */}
      <div style={{ display: 'flex', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottom: `1px solid ${colors.borderLight}` }}>
        <ProductImage productName={product.canonical_name} categoryName={categoryName} style={{ width: 80, height: 80, borderRadius: borderRadius.lg, backgroundColor: colors.borderLight }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 }}>{categoryName} &gt; {subcategoryName}</span>
          <span style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>{product.canonical_name}</span>
          {headerInfo.latestObs && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginTop: 4, position: 'relative' }}>
                <span style={{ fontSize: fontSize.md, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>
                  {formatCOP(headerInfo.displayMin)}
                  {headerInfo.displayMax !== headerInfo.displayMin ? ` - ${formatCOP(headerInfo.displayMax)}` : ''}
                </span>
                <button onClick={() => setShowWeekTooltip(!showWeekTooltip)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center' }}>
                  <PriceChangeIndicator value={headerInfo.weekChange} size="md" />
                </button>
                {showWeekTooltip && (
                  <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: 4, backgroundColor: colors.dark, color: '#fff', padding: `${spacing.xs}px ${spacing.sm}px`, borderRadius: borderRadius.sm, fontSize: fontSize.xs, whiteSpace: 'nowrap', zIndex: 10 }}>
                    {t.product_vs_prev_week}
                  </div>
                )}
              </div>
              <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                {[formatDateShort(headerInfo.latestObs.price_date), headerInfo.geoSource, headerInfo.mostCommonPres].filter(Boolean).join(' \u00b7 ')}
              </span>
            </>
          )}
          <button onClick={() => toggle(id!, 'product', product.canonical_name)}
            style={{ position: 'absolute', right: spacing.lg, top: spacing.lg, background: 'none', border: 'none', cursor: 'pointer' }}>
            {isWatched(id!) ? <IoStar size={22} color="#FFD700" /> : <IoStarOutline size={22} color={colors.text.tertiary} />}
          </button>
        </div>
      </div>

      {/* ══ PRICE SECTION ══ */}
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
        <IoPricetagsOutline size={18} color={colors.primary} />
        <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.product_price_section}</span>
      </div>

      {/* Price Chart (with filters inside) */}
      <Card style={{ margin: `${spacing.xs}px ${spacing.lg}px 0` }}>
        <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.sm, flexWrap: 'wrap' }}>
          {availablePriceRanges.map(tr => <button key={tr.label} onClick={() => setTimeRange(tr.index)} style={chipStyle(tr.index === timeRange)}>{tr.label}</button>)}
        </div>
        {availableMarkets.length > 0 && (
          <div className="chip-scroll" style={{ marginBottom: spacing.xs }}>
            <button onClick={() => setSelectedMarketId(null)} style={chipStyle(!selectedMarketId)}>{t.product_national_avg}</button>
            {availableMarkets.map(m => <button key={m.id} onClick={() => setSelectedMarketId(selectedMarketId === m.id ? null : m.id)} style={chipStyle(selectedMarketId === m.id)}>{m.name}</button>)}
          </div>
        )}
        {availablePresentations.length >= 1 && (
          <div className="chip-scroll" style={{ marginBottom: spacing.sm }}>
            {availablePresentations.map(p => <button key={p.id} onClick={() => setSelectedPresentation(p.id)} style={chipStyle(selectedPresentation === p.id || (availablePresentations.length === 1))}>{p.name}</button>)}
          </div>
        )}

        {chartData.length >= 1 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            {chartData.length > 1 && (
              <LineChart
                data={chartData.map(d => ({ date: d.date, value: d.avg, min: d.min, max: d.max }))}
                width={chartWidth} height={200} color={colors.primary} showBands
                formatValue={formatCOPCompact}
              />
            )}
            <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: spacing.sm, width: '100%' }}>
              {[{ label: t.product_min, value: formatCOP(Math.min(...chartData.map(d => d.min))) },
                { label: t.product_avg, value: formatCOP(chartData.reduce((s, d) => s + d.avg, 0) / chartData.length), color: colors.primary },
                { label: t.product_max, value: formatCOP(Math.max(...chartData.map(d => d.max))) }]
                .map(s => (
                  <div key={s.label} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{s.label}</div>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: s.color || colors.text.primary, fontFamily: 'monospace' }}>{s.value}</div>
                  </div>
                ))}
            </div>
            {selectedPresLabel && <div style={{ textAlign: 'center', marginTop: spacing.xs, fontSize: fontSize.xs, color: colors.text.tertiary }}>{selectedPresLabel}</div>}
          </div>
        ) : <p style={{ textAlign: 'center', padding: `${spacing.xxl}px 0`, color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.product_no_price_data}</p>}
      </Card>

      {/* Prices by Market */}
      {marketPrices.length > 0 && (
        <Card style={{ margin: `${spacing.sm}px ${spacing.lg}px 0` }}>
          <ExpandableSection title={t.product_prices_by_market} icon={<IoStorefrontOutline size={16} color={colors.text.secondary} />} badge={marketPriceRows.length} initiallyExpanded={false}>
            <p style={{ fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic', marginBottom: spacing.sm }}>{t.product_prices_by_market_note}</p>

            {/* Filters: presentation + sort */}
            <div style={{ display: 'flex', gap: spacing.xs, flexWrap: 'wrap', marginBottom: spacing.sm }}>
              {mktPresentations.map(p => (
                <button key={p.id} onClick={() => setMktPresFilter(mktPresFilter === p.id ? null : p.id)}
                  style={chipStyle(mktPresFilter === p.id)}>{p.name}</button>
              ))}
              <button onClick={() => setMktSortAsc(!mktSortAsc)} style={{
                ...chipStyle(false), display: 'flex', alignItems: 'center', gap: 4,
              }}>
                {mktSortAsc ? <IoArrowUp size={12} /> : <IoArrowDown size={12} />}
                {mktSortAsc ? t.product_sort_asc : t.product_sort_desc}
              </button>
            </div>

            {/* Median / Mean summary */}
            {marketPriceRows.length > 0 && (
              <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.sm }}>
                <div style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.sm, padding: `${spacing.xs}px ${spacing.sm}px`, textAlign: 'center' }}>
                  <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.product_median}</div>
                  <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.accent.blue, fontFamily: 'monospace' }}>{formatCOP(mktStats.median)}</div>
                </div>
                <div style={{ flex: 1, backgroundColor: colors.primary + '10', borderRadius: borderRadius.sm, padding: `${spacing.xs}px ${spacing.sm}px`, textAlign: 'center' }}>
                  <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.product_mean}</div>
                  <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(mktStats.mean)}</div>
                </div>
              </div>
            )}

            {marketPriceRows.map((p: any, i: number) => {
              const ctx = formatPriceContext(p.dim_presentation?.canonical_name, p.dim_units?.canonical_name);
              return (
                <div key={p.market_id || i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: `${spacing.sm}px 0`, borderBottom: `1px solid ${colors.borderLight}` }}>
                  <div style={{ flex: 1, marginRight: spacing.sm }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fmtMarket(p.dim_market) || t.product_market_fallback}</div>
                    {ctx && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{ctx}</div>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(p.min_price ?? p.avg_price)}{p.max_price != null && p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}</div>
                    <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{formatDateShort(p.price_date)}</div>
                  </div>
                </div>
              );
            })}
          </ExpandableSection>
        </Card>
      )}

      {/* ══ SUPPLY SECTION ══ */}
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.lg}px ${spacing.lg}px ${spacing.xs}px` }}>
        <IoCubeOutline size={18} color={colors.accent.blue} />
        <span style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{t.product_supply_section}</span>
      </div>

      <Card style={{ margin: `${spacing.xs}px ${spacing.lg}px 0` }}>
        {/* Filters: time period + market */}
        <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.sm, flexWrap: 'wrap' }}>
          {availableSupplyRanges.map(tr => <button key={`sup-${tr.label}`} onClick={() => setSupplyTimeRange(tr.index)} style={chipStyle(tr.index === supplyTimeRange, colors.accent.blue)}>{tr.label}</button>)}
        </div>
        {supplyMarkets.length > 0 && (
          <div className="chip-scroll" style={{ marginBottom: spacing.sm }}>
            <button onClick={() => setSupplyMarketId(null)} style={chipStyle(!supplyMarketId, colors.accent.blue)}>{t.product_national_avg}</button>
            {supplyMarkets.map(m => <button key={m.id} onClick={() => setSupplyMarketId(supplyMarketId === m.id ? null : m.id)} style={chipStyle(supplyMarketId === m.id, colors.accent.blue)}>{m.name}</button>)}
          </div>
        )}

        {/* Summary stats */}
        <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.md }}>
          <div style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, textAlign: 'center' }}>
            <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.accent.blue }}>{formatKg(totalSupplyKg)}</div>
            <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.product_total_sum}</div>
          </div>
          <div style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, textAlign: 'center' }}>
            <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.accent.blue }}>{formatKg(dailyAvgKg)}</div>
            <div style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.product_daily_avg}</div>
          </div>
        </div>

        {/* Supply chart */}
        {supplyByDate.length > 1 ? (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <LineChart
              data={supplyByDate.map(d => ({ date: d.date, value: d.kg }))}
              width={chartWidth} height={200} color={colors.accent.blue}
              formatValue={formatKg}
            />
          </div>
        ) : filteredSupply.length === 0 ? <p style={{ textAlign: 'center', color: colors.text.tertiary, fontSize: fontSize.sm }}>{t.product_no_supply_data}</p> : null}
      </Card>

      {/* Provenance */}
      {provenanceBars.length > 0 && (
        <Card style={{ margin: `${spacing.sm}px ${spacing.lg}px 0` }}>
          <ExpandableSection title={t.product_provenance} icon={<IoNavigateOutline size={16} color={colors.text.secondary} />} badge={provenanceBars.length} subtitle={t.product_provenance_subtitle} initiallyExpanded>
            {/* Provenance filters (separate from supply filters) */}
            <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.xs, flexWrap: 'wrap' }}>
              {availableSupplyRanges.map(tr => <button key={`prov-${tr.label}`} onClick={() => setProvTimeRange(tr.index)} style={chipStyle(tr.index === provTimeRange, colors.secondary)}>{tr.label}</button>)}
            </div>
            {provMarkets.length > 0 && (
              <div className="chip-scroll" style={{ marginBottom: spacing.sm }}>
                <button onClick={() => setProvMarketId(null)} style={chipStyle(!provMarketId, colors.secondary)}>{t.product_national_avg}</button>
                {provMarkets.map(m => <button key={m.id} onClick={() => setProvMarketId(provMarketId === m.id ? null : m.id)} style={chipStyle(provMarketId === m.id, colors.secondary)}>{m.name}</button>)}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
              {provenanceBars.map((d, i) => (
                <div key={d.dept} style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
                  <span style={{ width: 80, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.dept}</span>
                  <div style={{ flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(d.kg / maxProvenance) * 100}%`, backgroundColor: SUPPLY_COLORS[i % SUPPLY_COLORS.length], borderRadius: 4 }} />
                  </div>
                  <span style={{ width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: 600 }}>{formatKg(d.kg)}</span>
                  <span style={{ width: 36, fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'right' }}>{provTotal > 0 ? `${Math.round(d.kg / provTotal * 100)}%` : ''}</span>
                </div>
              ))}
              {/* Total row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, borderTop: `2px solid ${colors.border}`, paddingTop: spacing.sm }}>
                <span style={{ width: 80, fontSize: fontSize.xs, fontWeight: 700, color: colors.text.primary, textAlign: 'right' }}>{t.product_total_sum}</span>
                <div style={{ flex: 1 }} />
                <span style={{ width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: 700 }}>{formatKg(provTotal)}</span>
                <span style={{ width: 36, fontSize: fontSize.xs, color: colors.text.primary, fontWeight: 700, textAlign: 'right' }}>100%</span>
              </div>
            </div>
          </ExpandableSection>
        </Card>
      )}

      {/* ══ COMMENTS SECTION ══ */}
      <Card style={{ margin: `${spacing.lg}px ${spacing.lg}px 0` }}>
        <CommentsSection entityType="product" entityId={id!} />
      </Card>
    </div>
  );
}
