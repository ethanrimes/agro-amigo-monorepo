import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Dimensions } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Polyline, Line, Text as SvgText, Defs, LinearGradient, Stop, Rect } from 'react-native-svg';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { ProductImage } from '../../src/components/ProductImage';
import { getProductById, getProductPrices, getProductPricesByMarket } from '../../src/api/products';
import { getProductSupply } from '../../src/api/supply';
import { formatCOP, formatCOPCompact, formatDateShort, formatKg, formatPriceContext, pctChange } from '../../src/lib/format';
import { useWatchlist } from '../../src/context/WatchlistContext';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_WIDTH = SCREEN_WIDTH - 64;
const CHART_HEIGHT = 200;
const TIME_RANGES = [
  { label: '1S', days: 7 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1A', days: 365 },
  { label: 'Todo', days: 0 },
];
const SUPPLY_COLORS = [
  colors.primary, colors.accent.orange, colors.accent.blue,
  colors.secondary, colors.primaryLight, '#9C27B0', '#00BCD4', '#FF5722',
];

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
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

  useEffect(() => {
    loadProduct();
  }, [id]);

  useEffect(() => {
    if (id) loadPrices();
  }, [id, timeRange, selectedMarketId]);

  useEffect(() => {
    if (id) loadSupply();
  }, [id, supplyTimeRange]);

  async function loadProduct() {
    try {
      const [prod, mktPrices] = await Promise.all([
        getProductById(id!),
        getProductPricesByMarket(id!),
      ]);
      setProduct(prod);
      setMarketPrices(mktPrices || []);
    } catch (err) {
      console.error('Error loading product:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadPrices() {
    try {
      const days = TIME_RANGES[timeRange].days;
      const data = await getProductPrices(id!, {
        days: days === 0 ? 36500 : days,
        marketId: selectedMarketId || undefined,
        limit: days === 0 ? 10000 : 2000,
      });
      setPrices(data || []);
    } catch (err) {
      console.error('Error loading prices:', err);
    }
  }

  async function loadSupply() {
    try {
      const days = TIME_RANGES[supplyTimeRange].days;
      const data = await getProductSupply(id!, days === 0 ? 36500 : days);
      setSupply(data || []);
    } catch (err) {
      console.error('Error loading supply:', err);
    }
  }

  // Available markets from market prices data
  const availableMarkets = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of marketPrices) {
      if (p.market_id && p.dim_market?.canonical_name) {
        map.set(p.market_id, p.dim_market.canonical_name);
      }
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [marketPrices]);

  // Available presentations from price data
  const availablePresentations = useMemo(() => {
    const set = new Map<string, string>();
    for (const p of prices) {
      const pres = p.dim_presentation?.canonical_name;
      if (pres && p.presentation_id) {
        set.set(p.presentation_id, pres);
      }
    }
    return Array.from(set.entries()).map(([id, name]) => ({ id, name }));
  }, [prices]);

  // Deduplicate market prices: latest per (market_id)
  const marketPriceRows = useMemo(() => {
    const map = new Map<string, any>();
    for (const p of marketPrices) {
      const key = p.market_id || 'unknown';
      if (!map.has(key) || p.price_date > map.get(key).price_date) {
        map.set(key, p);
      }
    }
    return [...map.values()].sort((a, b) =>
      (a.dim_market?.canonical_name || '').localeCompare(b.dim_market?.canonical_name || '')
    );
  }, [marketPrices]);

  const marketSharedDate = useMemo(() => {
    if (marketPriceRows.length === 0) return null;
    const first = marketPriceRows[0].price_date;
    return marketPriceRows.every((p: any) => p.price_date === first) ? first : null;
  }, [marketPriceRows]);

  // Filter prices by presentation for chart
  const filteredPrices = useMemo(() => {
    if (!selectedPresentation) return prices;
    return prices.filter(p => p.presentation_id === selectedPresentation);
  }, [prices, selectedPresentation]);

  // Chart label for what data is being shown
  const chartLabel = useMemo(() => {
    const parts: string[] = [];
    if (selectedMarketId) {
      const mkt = availableMarkets.find(m => m.id === selectedMarketId);
      if (mkt) parts.push(mkt.name);
    } else {
      parts.push('Todos los mercados');
    }
    if (selectedPresentation) {
      const pres = availablePresentations.find(p => p.id === selectedPresentation);
      if (pres) parts.push(pres.name);
    }
    return parts.join(' · ');
  }, [selectedMarketId, selectedPresentation, availableMarkets, availablePresentations]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!product) {
    return (
      <View style={styles.loadingContainer}>
        <Text>Producto no encontrado</Text>
      </View>
    );
  }

  const categoryName = (product as any).dim_subcategory?.dim_category?.canonical_name || '';
  const subcategoryName = (product as any).dim_subcategory?.canonical_name || '';

  // Aggregate prices by date for chart
  const priceByDate = new Map<string, { min: number; max: number; avg: number }>();
  for (const p of filteredPrices) {
    const existing = priceByDate.get(p.price_date);
    const min = p.min_price ?? p.avg_price ?? 0;
    const max = p.max_price ?? p.avg_price ?? 0;
    const avg = p.avg_price ?? (min + max) / 2;
    if (!existing) {
      priceByDate.set(p.price_date, { min, max, avg });
    } else {
      existing.min = Math.min(existing.min, min);
      existing.max = Math.max(existing.max, max);
      existing.avg = (existing.avg + avg) / 2;
    }
  }

  const chartData = Array.from(priceByDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }));

  const latestPrice = chartData.length > 0 ? chartData[chartData.length - 1] : null;
  const oldestPrice = chartData.length > 1 ? chartData[0] : null;
  const priceChangeVal = latestPrice && oldestPrice
    ? pctChange(oldestPrice.avg, latestPrice.avg)
    : null;

  // Latest presentation info from most recent observation
  const latestObs = prices.length > 0 ? prices[0] : null;
  const latestPresentation = latestObs?.dim_presentation?.canonical_name;
  const latestUnits = latestObs?.dim_units?.canonical_name;

  // Supply aggregation by date for chart
  const supplyByDate = new Map<string, number>();
  for (const s of supply) {
    const date = s.observation_date;
    supplyByDate.set(date, (supplyByDate.get(date) || 0) + (s.quantity_kg || 0));
  }
  const supplyChartData = Array.from(supplyByDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, kg]) => ({ date, kg }));

  const totalSupplyKg = supply.reduce((sum, s) => sum + (s.quantity_kg || 0), 0);
  const supplyStart = supplyChartData.length > 0 ? supplyChartData[0] : null;
  const supplyEnd = supplyChartData.length > 0 ? supplyChartData[supplyChartData.length - 1] : null;

  // Provenance: aggregate supply by origin department
  const provenanceMap = new Map<string, number>();
  for (const s of supply) {
    const dept = s.provenance_dept_name || 'Desconocido';
    provenanceMap.set(dept, (provenanceMap.get(dept) || 0) + (s.quantity_kg || 0));
  }
  const provenanceBars = Array.from(provenanceMap.entries())
    .map(([dept, kg]) => ({ dept, kg }))
    .sort((a, b) => b.kg - a.kg)
    .slice(0, 10);
  const maxProvenance = provenanceBars.length > 0 ? provenanceBars[0].kg : 1;

  return (
    <>
      <Stack.Screen options={{
        title: product.canonical_name,
        headerRight: () => (
          <Pressable
            onPress={() => toggle(id!, 'product', product.canonical_name)}
            hitSlop={12}
            style={{ marginRight: spacing.md }}
          >
            <Ionicons
              name={isWatched(id!) ? 'star' : 'star-outline'}
              size={22}
              color={isWatched(id!) ? '#FFD700' : colors.text.inverse}
            />
          </Pressable>
        ),
      }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <ProductImage
            productName={product.canonical_name}
            categoryName={categoryName}
            style={styles.headerImage}
          />
          <View style={styles.headerInfo}>
            <Text style={styles.headerCategory}>{categoryName} &gt; {subcategoryName}</Text>
            <Text style={styles.headerName}>{product.canonical_name}</Text>
            {product.cpc_code && (
              <Text style={styles.headerCpc}>CPC: {product.cpc_code}</Text>
            )}
            {latestPrice && (
              <>
                <View style={styles.headerPriceRow}>
                  <Text style={styles.headerPrice}>
                    {formatCOP(latestPrice.min)} - {formatCOP(latestPrice.max)}
                  </Text>
                  <PriceChangeIndicator value={priceChangeVal} size="md" />
                </View>
                <Text style={styles.headerPriceDate}>
                  Precio al {formatDateShort(latestPrice.date)}
                  {latestPresentation ? ` · ${latestPresentation}` : ''}
                  {latestUnits ? ` · ${latestUnits}` : ''}
                </Text>
              </>
            )}
          </View>
        </View>

        {/* Price Chart */}
        <Card style={styles.chartCard}>
          <Text style={styles.sectionTitle}>Precios</Text>

          {/* Time range selector */}
          <View style={styles.timeRangeRow}>
            {TIME_RANGES.map((tr, i) => (
              <Pressable
                key={tr.label}
                style={[styles.timeRangeBtn, i === timeRange && styles.timeRangeBtnActive]}
                onPress={() => setTimeRange(i)}
              >
                <Text style={[styles.timeRangeText, i === timeRange && styles.timeRangeTextActive]}>
                  {tr.label}
                </Text>
              </Pressable>
            ))}
          </View>

          {/* Market selector */}
          {availableMarkets.length > 0 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterScroll} contentContainerStyle={styles.filterRow}>
              <Pressable
                style={[styles.filterChip, !selectedMarketId && styles.filterChipActive]}
                onPress={() => setSelectedMarketId(null)}
              >
                <Text style={[styles.filterChipText, !selectedMarketId && styles.filterChipTextActive]}>
                  Todos
                </Text>
              </Pressable>
              {availableMarkets.map(m => (
                <Pressable
                  key={m.id}
                  style={[styles.filterChip, selectedMarketId === m.id && styles.filterChipActive]}
                  onPress={() => setSelectedMarketId(selectedMarketId === m.id ? null : m.id)}
                >
                  <Text style={[styles.filterChipText, selectedMarketId === m.id && styles.filterChipTextActive]} numberOfLines={1}>
                    {m.name}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          )}

          {/* Presentation selector */}
          {availablePresentations.length > 1 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterScroll} contentContainerStyle={styles.filterRow}>
              <Pressable
                style={[styles.filterChip, !selectedPresentation && styles.filterChipActive]}
                onPress={() => setSelectedPresentation(null)}
              >
                <Text style={[styles.filterChipText, !selectedPresentation && styles.filterChipTextActive]}>
                  Todas las presentaciones
                </Text>
              </Pressable>
              {availablePresentations.map(p => (
                <Pressable
                  key={p.id}
                  style={[styles.filterChip, selectedPresentation === p.id && styles.filterChipActive]}
                  onPress={() => setSelectedPresentation(selectedPresentation === p.id ? null : p.id)}
                >
                  <Text style={[styles.filterChipText, selectedPresentation === p.id && styles.filterChipTextActive]} numberOfLines={1}>
                    {p.name}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          )}

          {/* Chart label */}
          <Text style={styles.chartLabel}>{chartLabel}</Text>

          {chartData.length > 1 ? (
            <View style={styles.chartContainer}>
              <PriceChart data={chartData} width={CHART_WIDTH} height={CHART_HEIGHT} showRange />
              {/* Price range summary */}
              <View style={styles.chartSummary}>
                <View style={styles.chartSumItem}>
                  <Text style={styles.chartSumLabel}>Mín</Text>
                  <Text style={styles.chartSumValue}>{formatCOP(Math.min(...chartData.map(d => d.min)))}</Text>
                </View>
                <View style={styles.chartSumItem}>
                  <Text style={styles.chartSumLabel}>Prom</Text>
                  <Text style={[styles.chartSumValue, { color: colors.primary }]}>
                    {formatCOP(chartData.reduce((s, d) => s + d.avg, 0) / chartData.length)}
                  </Text>
                </View>
                <View style={styles.chartSumItem}>
                  <Text style={styles.chartSumLabel}>Máx</Text>
                  <Text style={styles.chartSumValue}>{formatCOP(Math.max(...chartData.map(d => d.max)))}</Text>
                </View>
              </View>
            </View>
          ) : (
            <View style={styles.noDataContainer}>
              <Text style={styles.noDataText}>Sin datos de precios para este período</Text>
            </View>
          )}
        </Card>

        {/* Prices by Market */}
        {marketPriceRows.length > 0 && (
          <Card style={styles.chartCard}>
            <ExpandableSection
              title="Precios por mercado"
              icon="storefront-outline"
              badge={marketPriceRows.length}
              subtitle={marketSharedDate ? `Precios al ${formatDateShort(marketSharedDate)}` : undefined}
              initiallyExpanded={false}
            >
              {marketPriceRows.map((p: any, i: number) => {
                const ctx = formatPriceContext(
                  p.dim_presentation?.canonical_name,
                  p.dim_units?.canonical_name,
                );
                return (
                  <View key={p.market_id || i} style={styles.marketRow}>
                    <View style={styles.marketInfo}>
                      <Text style={styles.marketName} numberOfLines={1}>
                        {p.dim_market?.canonical_name || 'Mercado'}
                      </Text>
                      {ctx ? <Text style={styles.marketContext}>{ctx}</Text> : null}
                    </View>
                    <View style={styles.marketPriceCol}>
                      <Text style={styles.marketPrice}>
                        {formatCOP(p.min_price)}{p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}
                      </Text>
                      {!marketSharedDate && (
                        <Text style={styles.marketDate}>{formatDateShort(p.price_date)}</Text>
                      )}
                    </View>
                  </View>
                );
              })}
            </ExpandableSection>
          </Card>
        )}

        {/* Supply */}
        <Card style={styles.chartCard}>
          <Text style={styles.sectionTitle}>Abastecimiento</Text>

          {/* Supply time range */}
          <View style={styles.timeRangeRow}>
            {TIME_RANGES.map((tr, i) => (
              <Pressable
                key={`sup-${tr.label}`}
                style={[styles.timeRangeBtn, i === supplyTimeRange && styles.timeRangeBtnActive]}
                onPress={() => setSupplyTimeRange(i)}
              >
                <Text style={[styles.timeRangeText, i === supplyTimeRange && styles.timeRangeTextActive]}>
                  {tr.label}
                </Text>
              </Pressable>
            ))}
          </View>

          {/* Supply stats */}
          <View style={styles.supplyStats}>
            <View style={styles.supplyStat}>
              <Text style={styles.supplyStatValue}>{formatKg(totalSupplyKg)}</Text>
              <Text style={styles.supplyStatLabel}>Total</Text>
            </View>
            {supplyStart && (
              <View style={styles.supplyStat}>
                <Text style={styles.supplyStatValue}>{formatKg(supplyStart.kg)}</Text>
                <Text style={styles.supplyStatLabel}>{formatDateShort(supplyStart.date)}</Text>
              </View>
            )}
            {supplyEnd && supplyEnd !== supplyStart && (
              <View style={styles.supplyStat}>
                <Text style={styles.supplyStatValue}>{formatKg(supplyEnd.kg)}</Text>
                <Text style={styles.supplyStatLabel}>{formatDateShort(supplyEnd.date)}</Text>
              </View>
            )}
          </View>

          {/* Supply chart */}
          {supplyChartData.length > 1 ? (
            <View style={styles.chartContainer}>
              <SupplyChart data={supplyChartData} width={CHART_WIDTH} height={CHART_HEIGHT} />
            </View>
          ) : supply.length === 0 ? (
            <Text style={styles.noDataText}>Sin datos de abastecimiento para este período</Text>
          ) : null}
        </Card>

        {/* Provenance */}
        {provenanceBars.length > 0 && (
          <Card style={styles.chartCard}>
            <ExpandableSection
              title="Procedencia"
              icon="navigate-outline"
              badge={provenanceBars.length}
              subtitle="Departamentos de origen"
              initiallyExpanded={true}
            >
              <View style={styles.barsContainer}>
                {provenanceBars.map((d, i) => (
                  <View key={d.dept} style={styles.barRow}>
                    <Text style={styles.barLabel} numberOfLines={1}>{d.dept}</Text>
                    <View style={styles.barTrack}>
                      <View
                        style={[
                          styles.barFill,
                          {
                            width: `${(d.kg / maxProvenance) * 100}%` as any,
                            backgroundColor: SUPPLY_COLORS[i % SUPPLY_COLORS.length],
                          },
                        ]}
                      />
                    </View>
                    <Text style={styles.barValue}>{formatKg(d.kg)}</Text>
                  </View>
                ))}
              </View>
            </ExpandableSection>
          </Card>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
  );
}

function PriceChart({ data, width, height, showRange }: { data: any[]; width: number; height: number; showRange?: boolean }) {
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
  const minPoints = showRange ? data.map((d, i) => `${scaleX(i)},${scaleY(d.min)}`).join(' ') : '';
  const maxPoints = showRange ? data.map((d, i) => `${scaleX(i)},${scaleY(d.max)}`).join(' ') : '';

  const yLabels = [minY, (minY + maxY) / 2, maxY].map(v => ({
    value: v,
    y: scaleY(v),
    label: formatCOPCompact(v),
  }));

  const step = Math.max(1, Math.floor(data.length / 5));
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <Svg width={width} height={height}>
      <Defs>
        <LinearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={colors.primary} stopOpacity={0.2} />
          <Stop offset="1" stopColor={colors.primary} stopOpacity={0.02} />
        </LinearGradient>
      </Defs>
      {yLabels.map((yl, i) => (
        <Line key={i} x1={padding.left} y1={yl.y} x2={width - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />
      ))}
      {yLabels.map((yl, i) => (
        <SvgText key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={10} fill={colors.text.tertiary}>{yl.label}</SvgText>
      ))}
      {xLabels.map((d, i) => {
        const idx = data.indexOf(d);
        return (
          <SvgText key={`xl-${i}`} x={scaleX(idx)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatDateShort(d.date)}</SvgText>
        );
      })}
      {/* Min/Max range band */}
      {showRange && minPoints && data.length > 1 && (
        <Polyline points={maxPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
      )}
      {showRange && maxPoints && data.length > 1 && (
        <Polyline points={minPoints} fill="none" stroke={colors.text.tertiary} strokeWidth={0.5} strokeDasharray="3,3" opacity={0.4} />
      )}
      <Polyline points={avgPoints} fill="none" stroke={colors.primary} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function SupplyChart({ data, width, height }: { data: { date: string; kg: number }[]; width: number; height: number }) {
  const padding = { top: 10, right: 10, bottom: 30, left: 55 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const allKg = data.map(d => d.kg);
  const minY = 0;
  const maxY = Math.max(...allKg) * 1.1 || 1;
  const rangeY = maxY - minY || 1;

  const scaleX = (i: number) => padding.left + (i / (data.length - 1)) * chartW;
  const scaleY = (v: number) => padding.top + (1 - (v - minY) / rangeY) * chartH;

  const points = data.map((d, i) => `${scaleX(i)},${scaleY(d.kg)}`).join(' ');

  const yLabels = [0, maxY / 2, maxY].map(v => ({
    y: scaleY(v),
    label: formatKg(v),
  }));

  const step = Math.max(1, Math.floor(data.length / 5));
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <Svg width={width} height={height}>
      {yLabels.map((yl, i) => (
        <Line key={i} x1={padding.left} y1={yl.y} x2={width - padding.right} y2={yl.y} stroke={colors.borderLight} strokeWidth={1} />
      ))}
      {yLabels.map((yl, i) => (
        <SvgText key={`yl-${i}`} x={padding.left - 4} y={yl.y + 4} textAnchor="end" fontSize={9} fill={colors.text.tertiary}>{yl.label}</SvgText>
      ))}
      {xLabels.map((d, i) => {
        const idx = data.indexOf(d);
        return (
          <SvgText key={`xl-${i}`} x={scaleX(idx)} y={height - 4} textAnchor="middle" fontSize={9} fill={colors.text.tertiary}>{formatDateShort(d.date)}</SvgText>
        );
      })}
      <Polyline points={points} fill="none" stroke={colors.accent.blue} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { paddingBottom: 20 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  header: {
    flexDirection: 'row', padding: spacing.lg, gap: spacing.lg,
    backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.borderLight,
  },
  headerImage: { width: 80, height: 80, borderRadius: borderRadius.lg, backgroundColor: colors.borderLight },
  headerInfo: { flex: 1, gap: 4 },
  headerCategory: { fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 },
  headerName: { fontSize: fontSize.xl, fontWeight: '700', color: colors.text.primary },
  headerCpc: { fontSize: fontSize.xs, color: colors.text.tertiary },
  headerPriceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: 4 },
  headerPrice: { fontSize: fontSize.md, fontWeight: '600', color: colors.primary, fontFamily: 'monospace' },
  headerPriceDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
  chartCard: { marginHorizontal: spacing.lg, marginTop: spacing.lg },
  sectionTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text.primary, marginBottom: spacing.md },
  timeRangeRow: { flexDirection: 'row', gap: spacing.xs, marginBottom: spacing.sm },
  timeRangeBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: borderRadius.sm, backgroundColor: colors.borderLight },
  timeRangeBtnActive: { backgroundColor: colors.primary },
  timeRangeText: { fontSize: fontSize.xs, fontWeight: '600', color: colors.text.secondary },
  timeRangeTextActive: { color: colors.text.inverse },
  // Filters
  filterScroll: { maxHeight: 36, marginBottom: spacing.xs },
  filterRow: { gap: spacing.xs, paddingRight: spacing.sm },
  filterChip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: borderRadius.full,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.borderLight,
  },
  filterChipActive: { backgroundColor: colors.primaryDark, borderColor: colors.primaryDark },
  filterChipText: { fontSize: fontSize.xs, color: colors.text.secondary, maxWidth: 120 },
  filterChipTextActive: { color: colors.text.inverse },
  chartLabel: { fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.sm, fontStyle: 'italic' },
  chartContainer: { alignItems: 'center' },
  chartSummary: { flexDirection: 'row', justifyContent: 'space-around', marginTop: spacing.sm, width: '100%' },
  chartSumItem: { alignItems: 'center', gap: 2 },
  chartSumLabel: { fontSize: fontSize.xs, color: colors.text.tertiary },
  chartSumValue: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary, fontFamily: 'monospace' },
  noDataContainer: { paddingVertical: spacing.xxl, alignItems: 'center' },
  noDataText: { fontSize: fontSize.sm, color: colors.text.tertiary, textAlign: 'center' },
  // Market prices
  marketRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight,
  },
  marketInfo: { flex: 1, gap: 2, marginRight: spacing.sm },
  marketName: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary },
  marketContext: { fontSize: fontSize.xs, color: colors.text.tertiary },
  marketPriceCol: { alignItems: 'flex-end', gap: 2 },
  marketPrice: { fontSize: fontSize.sm, fontWeight: '600', color: colors.primary, fontFamily: 'monospace' },
  marketDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
  // Supply
  supplyStats: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  supplyStat: {
    flex: 1, backgroundColor: colors.accent.blue + '10', borderRadius: borderRadius.md,
    padding: spacing.sm, alignItems: 'center', gap: 2,
  },
  supplyStatValue: { fontSize: fontSize.md, fontWeight: '700', color: colors.accent.blue },
  supplyStatLabel: { fontSize: fontSize.xs, color: colors.text.secondary },
  // Provenance bars
  barsContainer: { gap: spacing.sm },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  barLabel: { width: 80, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right' },
  barTrack: { flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 4 },
  barValue: { width: 55, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: '600' },
});
