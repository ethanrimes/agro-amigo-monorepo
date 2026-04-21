import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Dimensions } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { ProductImage } from '../../src/components/ProductImage';
import { LineChart } from '../../src/components/LineChart';
import { CommentsSection } from '../../src/components/CommentsSection';
import { getProductById, getProductPrices, getProductPricesByMarket } from '../../src/api/products';
import { getProductSupplySummary, getProductTopDestinations, getProductTopOrigins, getProductSupplyByDate, SupplySummary } from '../../src/api/supply';
import { formatCOP, formatCOPCompact, formatDateShort, formatKg, formatPriceContext, pctChange } from '../../src/lib/format';
import { useWatchlist } from '../../src/context/WatchlistContext';
import { useSettings } from '../../src/context/SettingsContext';
import { useTranslation } from '../../src/lib/useTranslation';
import { cachedCall } from '../../src/lib/cache';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_WIDTH = SCREEN_WIDTH - 64;
const CHART_HEIGHT = 200;
const SUPPLY_COLORS = [colors.primary, colors.accent.orange, colors.accent.blue, colors.secondary, colors.primaryLight, '#9C27B0', '#00BCD4', '#FF5722'];

function fmtMarket(m: any): string {
  const name = m?.canonical_name || '';
  const city = m?.dim_city?.canonical_name || '';
  if (!city || name.toLowerCase().includes(city.toLowerCase())) return name;
  return `${name} (${city})`;
}

function presKey(p: any): string { return `${p.presentation_id || ''}|${p.units_id || ''}`; }
function presLabel(p: any): string { return [p.dim_presentation?.canonical_name, p.dim_units?.canonical_name].filter(Boolean).join(' \u00b7 '); }

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const { settings } = useSettings();
  const t = useTranslation();
  const [product, setProduct] = useState<any>(null);
  const [prices, setPrices] = useState<any[]>([]);
  const [marketPrices, setMarketPrices] = useState<any[]>([]);
  const [timeRange, setTimeRange] = useState<number | null>(null);
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [selectedPresentation, setSelectedPresentation] = useState<string | null>(null);
  // Supply section — all aggregation is server-side via RPCs.
  const [supplyTimeRange, setSupplyTimeRange] = useState<number>(1); // default 1m
  const [supplyProvFilter, setSupplyProvFilter] = useState<string | null>(null);
  const [supplyMarketId, setSupplyMarketId] = useState<string | null>(null);
  const [supplySummary, setSupplySummary] = useState<SupplySummary | null>(null);
  const [supplyByDate, setSupplyByDate] = useState<{ date: string; kg: number }[]>([]);
  const [topDestinationMarkets, setTopDestinationMarkets] = useState<{ market_id: string; market_name: string; total_kg: number }[]>([]);
  const [topOriginDepts, setTopOriginDepts] = useState<{ dept_name: string; total_kg: number }[]>([]);
  const [mktPresFilter, setMktPresFilter] = useState<string | null>(null);
  const [mktSortAsc, setMktSortAsc] = useState(false);
  const [showWeekTooltip, setShowWeekTooltip] = useState(false);
  const [loading, setLoading] = useState(true);
  // Lazy-load gates — heavy fetches fire only once the user expands the section.
  const [priceChartExpanded, setPriceChartExpanded] = useState(false);
  const [supplyExpanded, setSupplyExpanded] = useState(false);

  const TIME_RANGES = [
    { label: t.time_1w, days: 7 }, { label: t.time_1m, days: 30 }, { label: t.time_3m, days: 90 },
    { label: t.time_6m, days: 180 }, { label: t.time_1y, days: 365 }, { label: t.time_all, days: 0 },
  ];

  useEffect(() => { loadProduct(); }, [id]);
  // Price history is heavy (~5000 rows) — fetch only after the user expands
  // the price chart section. Cached so collapse/re-expand is free.
  useEffect(() => {
    if (!id || !priceChartExpanded) return;
    cachedCall(`product:${id}:prices:all`, () => getProductPrices(id, { days: 36500, limit: 5000 }))
      .then(data => setPrices((data as any[]) || []))
      .catch(err => console.error(err));
  }, [id, priceChartExpanded]);

  // Supply RPCs: server-side aggregated. Deferred until the supply section
  // is opened; re-fires on time tile / cross-filter change within that
  // section. Each call is routed through the session cache.
  useEffect(() => {
    if (!id || !supplyExpanded) return;
    let cancelled = false;
    const tr = TIME_RANGES[supplyTimeRange];
    const days = tr?.days ?? 30;
    const keyBase = `product:${id}:supply:${days}:${supplyMarketId ?? ''}:${supplyProvFilter ?? ''}`;
    Promise.all([
      cachedCall(`${keyBase}:summary`, () => getProductSupplySummary(id, days, supplyMarketId, supplyProvFilter)).catch(() => null),
      cachedCall(`${keyBase}:byDate`, () => getProductSupplyByDate(id, days, supplyMarketId, supplyProvFilter)).catch(() => []),
      cachedCall(`${keyBase}:dests`, () => getProductTopDestinations(id, days, supplyProvFilter, 15)).catch(() => []),
      cachedCall(`${keyBase}:origins`, () => getProductTopOrigins(id, days, supplyMarketId, 15)).catch(() => []),
    ]).then(([summary, byDate, dests, origins]) => {
      if (cancelled) return;
      setSupplySummary(summary as SupplySummary | null);
      setSupplyByDate(byDate as { date: string; kg: number }[]);
      setTopDestinationMarkets(dests as { market_id: string; market_name: string; total_kg: number }[]);
      setTopOriginDepts(origins as { dept_name: string; total_kg: number }[]);
    });
    return () => { cancelled = true; };
  }, [id, supplyExpanded, supplyTimeRange, supplyMarketId, supplyProvFilter]);

  async function loadProduct() {
    try {
      const [prod, mktPrices] = await Promise.all([
        cachedCall(`product:${id}:entity`, () => getProductById(id!)),
        cachedCall(`product:${id}:prices-by-market`, () => getProductPricesByMarket(id!)),
      ]);
      setProduct(prod); setMarketPrices(((mktPrices as any[]) || []));
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  // ═══ PRICE CASCADE: time range → market → presentation ═══

  const availablePriceRanges = useMemo(() => {
    if (prices.length === 0) return [];
    const newest = prices[0]?.price_date;
    if (!newest) return [];
    const daysOld = Math.ceil((new Date().getTime() - new Date(newest + 'T00:00:00').getTime()) / 86400000);
    return TIME_RANGES.map((tr, i) => ({ ...tr, index: i, hasData: tr.days === 0 || daysOld <= tr.days })).filter(tr => tr.hasData);
  }, [prices]);

  useEffect(() => {
    if (availablePriceRanges.length > 0 && (timeRange === null || !availablePriceRanges.some(r => r.index === timeRange)))
      setTimeRange(availablePriceRanges[0].index);
  }, [availablePriceRanges]);

  const timeFilteredPrices = useMemo(() => {
    const tr = TIME_RANGES[timeRange ?? 0];
    if (!tr || tr.days === 0) return prices;
    const since = new Date(); since.setDate(since.getDate() - tr.days);
    const sinceStr = since.toISOString().split('T')[0];
    return prices.filter(p => p.price_date >= sinceStr);
  }, [prices, timeRange]);

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

  const marketFilteredPrices = useMemo(() => {
    if (!selectedMarketId) return timeFilteredPrices;
    return timeFilteredPrices.filter(p => p.market_id === selectedMarketId);
  }, [timeFilteredPrices, selectedMarketId]);

  const availablePresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of marketFilteredPrices) {
      const pres = p.dim_presentation?.canonical_name;
      if (pres && p.presentation_id) { const key = presKey(p); if (!set.has(key)) set.set(key, presLabel(p)); }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [marketFilteredPrices]);

  useEffect(() => {
    if (selectedPresentation && !availablePresentations.some(p => p.id === selectedPresentation))
      setSelectedPresentation(availablePresentations.length > 0 ? availablePresentations[0].id : null);
    else if (!selectedPresentation && availablePresentations.length > 0)
      setSelectedPresentation(availablePresentations[0].id);
  }, [availablePresentations]);

  const filteredPrices = useMemo(() => {
    if (!selectedPresentation) return marketFilteredPrices;
    return marketFilteredPrices.filter(p => presKey(p) === selectedPresentation);
  }, [marketFilteredPrices, selectedPresentation]);

  const mktPresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of marketPrices) {
      const pres = p.dim_presentation?.canonical_name;
      if (pres && p.presentation_id) { const key = presKey(p); if (!set.has(key)) set.set(key, presLabel(p)); }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [marketPrices]);

  const headerInfo = useMemo(() => {
    if (marketPrices.length === 0) return { latestObs: null, mostCommonPres: '', geoSource: t.product_national_avg, weekChange: null, displayMin: 0, displayMax: 0 };
    const presCounts = new Map<string, { count: number; label: string }>();
    for (const p of marketPrices) { const key = presKey(p); const ex = presCounts.get(key); if (ex) ex.count++; else presCounts.set(key, { count: 1, label: presLabel(p) }); }
    let mostCommonKey = ''; let mostCommonPres = ''; let maxCount = 0;
    for (const [k, v] of presCounts) { if (v.count > maxCount) { maxCount = v.count; mostCommonKey = k; mostCommonPres = v.label; } }
    // Restrict to the most-common presentation+units bucket so prices are comparable
    const bucket = marketPrices.filter((p: any) => presKey(p) === mostCommonKey);
    const dm = settings.defaultMarket;
    let latestObs: any = null; let geoSource = t.product_national_avg;
    let displayMin = 0; let displayMax = 0;
    if (dm.level === 'mercado' && dm.id) {
      const matches = bucket.filter((p: any) => p.market_id === dm.id);
      if (matches.length > 0) {
        latestObs = matches.reduce((a: any, b: any) => a.price_date > b.price_date ? a : b);
        geoSource = fmtMarket(latestObs.dim_market);
        displayMin = latestObs.min_price ?? latestObs.avg_price ?? 0;
        displayMax = latestObs.max_price ?? latestObs.avg_price ?? 0;
      }
    }
    if (!latestObs && bucket.length > 0) {
      // National avg: take latest date in bucket, avg min/max across markets on that date
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
      const latestDate = new Date(latestObs.price_date); const weekAgo = new Date(latestDate); weekAgo.setDate(weekAgo.getDate() - 7);
      const weekAgoStr = weekAgo.toISOString().split('T')[0];
      const candidates = dm.level === 'mercado' && dm.id
        ? bucket.filter((p: any) => p.market_id === dm.id && p.price_date <= weekAgoStr)
        : bucket.filter((p: any) => p.price_date <= weekAgoStr);
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

  const marketPriceRows = useMemo(() => {
    let rows = [...marketPrices];
    if (mktPresFilter) { const [presId, unitsId] = mktPresFilter.split('|'); rows = rows.filter((p: any) => p.presentation_id === presId && (p.units_id || '') === unitsId); }
    const map = new Map<string, any>();
    for (const p of rows) { const key = p.market_id || 'unknown'; if (!map.has(key) || p.price_date > map.get(key).price_date) map.set(key, p); }
    return [...map.values()].sort((a, b) => { const aP = a.avg_price || a.min_price || 0; const bP = b.avg_price || b.min_price || 0; return mktSortAsc ? aP - bP : bP - aP; });
  }, [marketPrices, mktPresFilter, mktSortAsc]);

  const mktStats = useMemo(() => {
    const avgPrices = marketPriceRows.map((p: any) => p.avg_price || (p.min_price + p.max_price) / 2).filter((v: number) => v > 0);
    if (avgPrices.length === 0) return { median: 0, mean: 0 };
    const sorted = [...avgPrices].sort((a: number, b: number) => a - b); const mid = Math.floor(sorted.length / 2);
    return { median: sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid], mean: avgPrices.reduce((s: number, v: number) => s + v, 0) / avgPrices.length };
  }, [marketPriceRows]);

  // ═══ SUPPLY SECTION: driven by server-side RPCs (see useEffect above) ═══

  const totalSupplyKg = supplySummary?.total_kg ?? 0;
  const dailyAvgKg = supplySummary?.daily_avg_kg ?? 0;
  const availableSupplyRanges = TIME_RANGES.map((tr, i) => ({ ...tr, index: i }));
  const supplyMarkets = topDestinationMarkets.map(m => ({ id: m.market_id, name: m.market_name }));
  const filteredSupply: any[] = []; // legacy — no longer used for rendering

  if (loading) return <View style={styles.loadingContainer}><ActivityIndicator size="large" color={colors.primary} /></View>;
  if (!product) return <View style={styles.loadingContainer}><Text>{t.product_not_found}</Text></View>;

  const categoryName = product.dim_subcategory?.dim_category?.canonical_name || '';
  const subcategoryName = product.dim_subcategory?.canonical_name || '';

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
  const selectedPresLabel = availablePresentations.find(p => p.id === selectedPresentation)?.name || '';

  const chipStyle = (active: boolean, activeColor: string = colors.primaryDark) => ({
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: borderRadius.full,
    backgroundColor: active ? activeColor : colors.surface,
    borderWidth: 1, borderColor: active ? activeColor : colors.borderLight,
  });
  const chipTextStyle = (active: boolean) => ({
    fontSize: fontSize.xs, color: active ? colors.text.inverse : colors.text.secondary,
  });

  return (
    <>
      <Stack.Screen options={{
        title: product.canonical_name,
        headerRight: () => (
          <Pressable onPress={() => toggle(id!, 'product', product.canonical_name)} hitSlop={12} style={{ marginRight: spacing.md }}>
            <Ionicons name={isWatched(id!) ? 'star' : 'star-outline'} size={22} color={isWatched(id!) ? '#FFD700' : colors.text.inverse} />
          </Pressable>
        ),
      }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <ProductImage productName={product.canonical_name} categoryName={categoryName} style={styles.headerImage} />
          <View style={styles.headerInfo}>
            <Text style={styles.headerCategory}>{categoryName} &gt; {subcategoryName}</Text>
            <Text style={styles.headerName}>{product.canonical_name}</Text>
            {headerInfo.latestObs && (
              <>
                <View style={styles.headerPriceRow}>
                  <Text style={styles.headerPrice}>
                    {formatCOP(headerInfo.displayMin)}
                    {headerInfo.displayMax !== headerInfo.displayMin ? ` - ${formatCOP(headerInfo.displayMax)}` : ''}
                  </Text>
                  <Pressable onPress={() => setShowWeekTooltip(!showWeekTooltip)}>
                    <PriceChangeIndicator value={headerInfo.weekChange} size="md" />
                  </Pressable>
                </View>
                {showWeekTooltip && (
                  <View style={{ backgroundColor: colors.dark, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: borderRadius.sm, alignSelf: 'flex-start' }}>
                    <Text style={{ color: '#fff', fontSize: fontSize.xs }}>{t.product_vs_prev_week}</Text>
                  </View>
                )}
                <Text style={styles.headerPriceDate}>
                  {[formatDateShort(headerInfo.latestObs.price_date), headerInfo.geoSource, headerInfo.mostCommonPres].filter(Boolean).join(' \u00b7 ')}
                </Text>
              </>
            )}
          </View>
        </View>

        {/* ── PRICE SECTION ── */}
        <Card style={styles.card}>
          <ExpandableSection
            title={t.product_price_section}
            icon="pricetags-outline"
            initiallyExpanded={false}
            onExpandChange={setPriceChartExpanded}
          >
          {/* Time range */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
            {availablePriceRanges.map(tr => (
              <Pressable key={tr.label} style={chipStyle(tr.index === timeRange)} onPress={() => setTimeRange(tr.index)}>
                <Text style={chipTextStyle(tr.index === timeRange)}>{tr.label}</Text>
              </Pressable>
            ))}
          </View>
          {/* Markets */}
          {availableMarkets.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.xs }}>
              <Pressable style={chipStyle(!selectedMarketId)} onPress={() => setSelectedMarketId(null)}>
                <Text style={chipTextStyle(!selectedMarketId)}>{t.product_national_avg}</Text>
              </Pressable>
              {availableMarkets.map(m => (
                <Pressable key={m.id} style={chipStyle(selectedMarketId === m.id)} onPress={() => setSelectedMarketId(selectedMarketId === m.id ? null : m.id)}>
                  <Text style={chipTextStyle(selectedMarketId === m.id)} numberOfLines={1}>{m.name}</Text>
                </Pressable>
              ))}
            </View>
          )}
          {/* Presentations */}
          {availablePresentations.length >= 1 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
              {availablePresentations.map(p => (
                <Pressable key={p.id} style={chipStyle(selectedPresentation === p.id || availablePresentations.length === 1)} onPress={() => setSelectedPresentation(p.id)}>
                  <Text style={chipTextStyle(selectedPresentation === p.id || availablePresentations.length === 1)}>{p.name}</Text>
                </Pressable>
              ))}
            </View>
          )}
          {/* Chart */}
          {chartData.length >= 1 ? (
            <View style={{ alignItems: 'center' }}>
              {chartData.length > 1 && (
                <LineChart data={chartData.map(d => ({ date: d.date, value: d.avg, min: d.min, max: d.max }))} width={CHART_WIDTH} height={CHART_HEIGHT} color={colors.primary} showBands formatValue={formatCOPCompact} minPointSpacing={6} />
              )}
              <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: spacing.sm, width: '100%' }}>
                {[{ label: t.product_min, value: formatCOP(Math.min(...chartData.map(d => d.min))) },
                  { label: t.product_avg, value: formatCOP(chartData.reduce((s, d) => s + d.avg, 0) / chartData.length), color: colors.primary },
                  { label: t.product_max, value: formatCOP(Math.max(...chartData.map(d => d.max))) }]
                  .map(s => (
                    <View key={s.label} style={{ alignItems: 'center' }}>
                      <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{s.label}</Text>
                      <Text style={{ fontSize: fontSize.sm, fontWeight: '600', color: s.color || colors.text.primary, fontFamily: 'monospace' }}>{s.value}</Text>
                    </View>
                  ))}
              </View>
              {selectedPresLabel ? <Text style={{ textAlign: 'center', marginTop: spacing.xs, fontSize: fontSize.xs, color: colors.text.tertiary }}>{selectedPresLabel}</Text> : null}
            </View>
          ) : <Text style={styles.noDataText}>{t.product_no_price_data}</Text>}
          </ExpandableSection>
        </Card>

        {/* Prices by Market */}
        {marketPrices.length > 0 && (
          <Card style={styles.card}>
            <ExpandableSection title={t.product_prices_by_market} icon="storefront-outline" badge={marketPriceRows.length} initiallyExpanded={false}>
              <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic', marginBottom: spacing.sm }}>{t.product_prices_by_market_note}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                {mktPresentations.map(p => (
                  <Pressable key={p.id} style={chipStyle(mktPresFilter === p.id)} onPress={() => setMktPresFilter(mktPresFilter === p.id ? null : p.id)}>
                    <Text style={chipTextStyle(mktPresFilter === p.id)}>{p.name}</Text>
                  </Pressable>
                ))}
                <Pressable style={chipStyle(false)} onPress={() => setMktSortAsc(!mktSortAsc)}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name={mktSortAsc ? 'arrow-up' : 'arrow-down'} size={12} color={colors.text.secondary} />
                    <Text style={chipTextStyle(false)}>{mktSortAsc ? t.product_sort_asc : t.product_sort_desc}</Text>
                  </View>
                </Pressable>
              </View>
              {marketPriceRows.length > 0 && (
                <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm }}>
                  <View style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.sm, padding: spacing.xs, alignItems: 'center' }}>
                    <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.product_median}</Text>
                    <Text style={{ fontSize: fontSize.sm, fontWeight: '600', color: colors.accent.blue, fontFamily: 'monospace' }}>{formatCOP(mktStats.median)}</Text>
                  </View>
                  <View style={{ flex: 1, backgroundColor: colors.primary + '10', borderRadius: borderRadius.sm, padding: spacing.xs, alignItems: 'center' }}>
                    <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.product_mean}</Text>
                    <Text style={{ fontSize: fontSize.sm, fontWeight: '600', color: colors.primary, fontFamily: 'monospace' }}>{formatCOP(mktStats.mean)}</Text>
                  </View>
                </View>
              )}
              {marketPriceRows.map((p: any, i: number) => {
                const ctx = formatPriceContext(p.dim_presentation?.canonical_name, p.dim_units?.canonical_name);
                return (
                  <View key={p.market_id || i} style={styles.marketRow}>
                    <View style={{ flex: 1, marginRight: spacing.sm }}>
                      <Text style={styles.marketName}>{fmtMarket(p.dim_market) || t.product_market_fallback}</Text>
                      {ctx ? <Text style={styles.marketContext}>{ctx}</Text> : null}
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.marketPrice}>{formatCOP(p.min_price)}{p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}</Text>
                      <Text style={styles.marketDate}>{formatDateShort(p.price_date)}</Text>
                    </View>
                  </View>
                );
              })}
            </ExpandableSection>
          </Card>
        )}

        {/* ── SUPPLY SECTION ── */}
        <Card style={styles.card}>
          <ExpandableSection
            title={t.product_supply_section}
            icon="cube-outline"
            initiallyExpanded={false}
            onExpandChange={setSupplyExpanded}
          >
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
            {availableSupplyRanges.map(tr => (
              <Pressable key={`sup-${tr.label}`} style={chipStyle(tr.index === supplyTimeRange, colors.accent.blue)} onPress={() => setSupplyTimeRange(tr.index)}>
                <Text style={chipTextStyle(tr.index === supplyTimeRange)}>{tr.label}</Text>
              </Pressable>
            ))}
          </View>
          {supplyProvFilter && (
            <Pressable
              onPress={() => setSupplyProvFilter(null)}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
                alignSelf: 'flex-start', paddingHorizontal: spacing.sm, paddingVertical: spacing.xs,
                backgroundColor: colors.secondary + '15', borderRadius: borderRadius.full,
                marginBottom: spacing.sm,
              }}
            >
              <Ionicons name="navigate" size={12} color={colors.secondary} />
              <Text style={{ fontSize: fontSize.xs, color: colors.secondary, fontWeight: '600' }}>{supplyProvFilter}</Text>
              <Ionicons name="close-circle" size={14} color={colors.secondary} />
            </Pressable>
          )}
          {supplyMarkets.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
              <Pressable style={chipStyle(!supplyMarketId, colors.accent.blue)} onPress={() => setSupplyMarketId(null)}>
                <Text style={chipTextStyle(!supplyMarketId)}>{t.product_national_avg}</Text>
              </Pressable>
              {supplyMarkets.map(m => (
                <Pressable key={m.id} style={chipStyle(supplyMarketId === m.id, colors.accent.blue)} onPress={() => setSupplyMarketId(supplyMarketId === m.id ? null : m.id)}>
                  <Text style={chipTextStyle(supplyMarketId === m.id)} numberOfLines={1}>{m.name}</Text>
                </Pressable>
              ))}
            </View>
          )}
          <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md }}>
            <View style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, alignItems: 'center' }}>
              <Text style={{ fontSize: fontSize.md, fontWeight: '700', color: colors.accent.blue }}>{formatKg(totalSupplyKg)}</Text>
              <Text style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.product_total_sum}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md, padding: spacing.sm, alignItems: 'center' }}>
              <Text style={{ fontSize: fontSize.md, fontWeight: '700', color: colors.accent.blue }}>{formatKg(dailyAvgKg)}</Text>
              <Text style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>{t.product_daily_avg}</Text>
            </View>
          </View>
          {supplyByDate.length > 1 ? (
            <LineChart data={supplyByDate.map(d => ({ date: d.date, value: d.kg }))} width={CHART_WIDTH} height={CHART_HEIGHT} color={colors.accent.blue} formatValue={formatKg} minPointSpacing={6} />
          ) : filteredSupply.length === 0 ? <Text style={styles.noDataText}>{t.product_no_supply_data}</Text> : null}

          {/* ── Joint bar graphic: destinations (top) ↔ origins (bottom) ── */}
          {topDestinationMarkets.length > 0 && (
            <>
              <Text style={styles.supplySubHeader}>Mercados de destino</Text>
              <Text style={styles.supplyHint}>Toca para ver la procedencia de ese mercado.</Text>
              <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
                {topDestinationMarkets.map(d => {
                  const active = supplyMarketId === d.market_id;
                  const dim = supplyMarketId && !active;
                  return (
                    <Pressable
                      key={d.market_id}
                      onPress={() => setSupplyMarketId(active ? null : d.market_id)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, opacity: dim ? 0.4 : 1 }}
                    >
                      <Text style={[styles.supplyBarName, active && { color: colors.accent.blue, fontWeight: '700' }]} numberOfLines={2}>{d.market_name}</Text>
                      <View style={styles.supplyBarTrack}>
                        <View style={[styles.supplyBarFill, { width: `${(d.total_kg / (topDestinationMarkets[0]?.total_kg || 1)) * 100}%` as any }]} />
                      </View>
                      <Text style={styles.supplyBarValue}>{formatKg(d.total_kg)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </>
          )}

          {topOriginDepts.length > 0 && (
            <>
              <Text style={styles.supplySubHeader}>{t.product_provenance || 'Procedencia'}</Text>
              <Text style={styles.supplyHint}>Toca para ver los mercados que reciben de ese origen.</Text>
              <View style={{ gap: spacing.sm }}>
                {topOriginDepts.map((d, i) => {
                  const active = supplyProvFilter === d.dept_name;
                  const dim = supplyProvFilter && !active;
                  return (
                    <Pressable
                      key={d.dept_name}
                      onPress={() => setSupplyProvFilter(active ? null : d.dept_name)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, opacity: dim ? 0.4 : 1 }}
                    >
                      <Text style={[styles.supplyBarName, active && { color: colors.secondary, fontWeight: '700' }]} numberOfLines={2}>{d.dept_name}</Text>
                      <View style={styles.supplyBarTrack}>
                        <View style={[styles.supplyBarFill, { width: `${(d.total_kg / (topOriginDepts[0]?.total_kg || 1)) * 100}%` as any, backgroundColor: SUPPLY_COLORS[i % SUPPLY_COLORS.length] }]} />
                      </View>
                      <Text style={styles.supplyBarValue}>{formatKg(d.total_kg)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </>
          )}
          </ExpandableSection>
        </Card>

        {/* Comments */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.lg }}>
          <CommentsSection entityType="product" entityId={id!} />
        </Card>

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { paddingBottom: 20 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  header: { flexDirection: 'row', padding: spacing.lg, gap: spacing.lg, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  headerImage: { width: 80, height: 80, borderRadius: borderRadius.lg, backgroundColor: colors.borderLight },
  headerInfo: { flex: 1, gap: 4 },
  headerCategory: { fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 },
  headerName: { fontSize: fontSize.xl, fontWeight: '700', color: colors.text.primary },
  headerPriceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: 4 },
  headerPrice: { fontSize: fontSize.md, fontWeight: '600', color: colors.primary, fontFamily: 'monospace' },
  headerPriceDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xs },
  sectionHeaderText: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text.primary },
  card: { marginHorizontal: spacing.lg, marginTop: spacing.xs },
  noDataText: { fontSize: fontSize.sm, color: colors.text.tertiary, textAlign: 'center', paddingVertical: spacing.xxl },
  marketRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  marketName: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary },
  marketContext: { fontSize: fontSize.xs, color: colors.text.tertiary },
  marketPrice: { fontSize: fontSize.sm, fontWeight: '600', color: colors.primary, fontFamily: 'monospace' },
  marketDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
  supplySubHeader: { fontSize: fontSize.sm, fontWeight: '700', color: colors.text.primary, marginTop: spacing.sm, marginBottom: 2 },
  supplyHint: { fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic', marginBottom: spacing.xs },
  supplyBarName: { width: 100, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right' },
  supplyBarTrack: { flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' },
  supplyBarFill: { height: '100%', backgroundColor: colors.accent.blue, borderRadius: 4 },
  supplyBarValue: { width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: '600' },
});
