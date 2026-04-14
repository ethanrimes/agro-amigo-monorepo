import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Dimensions, Linking } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Polyline, Line, Text as SvgText, Rect, Defs, LinearGradient, Stop } from 'react-native-svg';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { ProductImage } from '../../src/components/ProductImage';
import { getProductById, getProductPrices } from '../../src/api/products';
import { getProductSupply } from '../../src/api/supply';
import { getImageAttribution, ImageAttribution } from '../../src/api/imageAttribution';
import { slugify } from '../../src/lib/images';
import { formatCOP, formatCOPCompact, formatDateShort, formatKg, pctChange } from '../../src/lib/format';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_WIDTH = SCREEN_WIDTH - 64;
const CHART_HEIGHT = 200;
const TIME_RANGES = [
  { label: '1S', days: 7 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1A', days: 365 },
  { label: 'Todo', days: 3650 },
];

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [prices, setPrices] = useState<any[]>([]);
  const [supply, setSupply] = useState<any[]>([]);
  const [attribution, setAttribution] = useState<ImageAttribution | null>(null);
  const [timeRange, setTimeRange] = useState(1); // index into TIME_RANGES
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProduct();
  }, [id]);

  useEffect(() => {
    if (id) loadPrices();
  }, [id, timeRange]);

  async function loadProduct() {
    try {
      const [prod, sup] = await Promise.all([
        getProductById(id!),
        getProductSupply(id!, 30),
      ]);
      setProduct(prod);
      setSupply(sup || []);

      // Load image attribution
      if (prod?.canonical_name) {
        const attr = await getImageAttribution('product', slugify(prod.canonical_name));
        setAttribution(attr);
      }
    } catch (err) {
      console.error('Error loading product:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadPrices() {
    try {
      const data = await getProductPrices(id!, {
        days: TIME_RANGES[timeRange].days,
        limit: 1000,
      });
      setPrices(data || []);
    } catch (err) {
      console.error('Error loading prices:', err);
    }
  }

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
  for (const p of prices) {
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

  // Total supply
  const totalSupplyKg = supply.reduce((sum, s) => sum + (s.quantity_kg || 0), 0);

  return (
    <>
      <Stack.Screen options={{ title: product.canonical_name }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <ProductImage
              productName={product.canonical_name}
              categoryName={categoryName}
              style={styles.headerImage}
            />
            {attribution && attribution.source_name !== 'unknown' && (
              <Pressable
                onPress={() => attribution.source_url && Linking.openURL(attribution.source_url)}
                style={styles.attributionRow}
              >
                <Ionicons name="camera-outline" size={10} color={colors.text.tertiary} />
                <Text style={styles.attributionText} numberOfLines={1}>
                  {attribution.author !== 'Unknown' ? attribution.author : attribution.source_name}
                  {attribution.license ? ` (${attribution.license})` : ''}
                </Text>
              </Pressable>
            )}
          </View>
          <View style={styles.headerInfo}>
            <Text style={styles.headerCategory}>{categoryName} &gt; {subcategoryName}</Text>
            <Text style={styles.headerName}>{product.canonical_name}</Text>
            {product.cpc_code && (
              <Text style={styles.headerCpc}>CPC: {product.cpc_code}</Text>
            )}
            {latestPrice && (
              <View style={styles.headerPriceRow}>
                <Text style={styles.headerPrice}>
                  {formatCOP(latestPrice.min)} - {formatCOP(latestPrice.max)}
                </Text>
                <PriceChangeIndicator value={priceChangeVal} size="md" />
              </View>
            )}
          </View>
        </View>

        {/* Price Chart Section */}
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

          {/* SVG Chart */}
          {chartData.length > 1 ? (
            <View style={styles.chartContainer}>
              <PriceChart data={chartData} width={CHART_WIDTH} height={CHART_HEIGHT} />
            </View>
          ) : (
            <View style={styles.noDataContainer}>
              <Text style={styles.noDataText}>Sin datos de precios para este período</Text>
            </View>
          )}
        </Card>

        {/* Supply Section */}
        <Card style={styles.chartCard}>
          <Text style={styles.sectionTitle}>Abastecimiento</Text>
          <View style={styles.supplyStats}>
            <View style={styles.supplyStat}>
              <Text style={styles.supplyStatValue}>{formatKg(totalSupplyKg)}</Text>
              <Text style={styles.supplyStatLabel}>Total (30 días)</Text>
            </View>
            <View style={styles.supplyStat}>
              <Text style={styles.supplyStatValue}>{supply.length}</Text>
              <Text style={styles.supplyStatLabel}>Observaciones</Text>
            </View>
          </View>
          {supply.length === 0 && (
            <Text style={styles.noDataText}>Sin datos de abastecimiento recientes</Text>
          )}
        </Card>

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
  );
}

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

  // Y-axis labels
  const yLabels = [minY, (minY + maxY) / 2, maxY].map(v => ({
    value: v,
    y: scaleY(v),
    label: formatCOPCompact(v),
  }));

  // X-axis labels (show ~5 evenly spaced)
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

      {/* Grid lines */}
      {yLabels.map((yl, i) => (
        <Line
          key={i}
          x1={padding.left}
          y1={yl.y}
          x2={width - padding.right}
          y2={yl.y}
          stroke={colors.borderLight}
          strokeWidth={1}
        />
      ))}

      {/* Y-axis labels */}
      {yLabels.map((yl, i) => (
        <SvgText
          key={`yl-${i}`}
          x={padding.left - 4}
          y={yl.y + 4}
          textAnchor="end"
          fontSize={10}
          fill={colors.text.tertiary}
        >
          {yl.label}
        </SvgText>
      ))}

      {/* X-axis labels */}
      {xLabels.map((d, i) => {
        const idx = data.indexOf(d);
        return (
          <SvgText
            key={`xl-${i}`}
            x={scaleX(idx)}
            y={height - 4}
            textAnchor="middle"
            fontSize={9}
            fill={colors.text.tertiary}
          >
            {formatDateShort(d.date)}
          </SvgText>
        );
      })}

      {/* Average price line */}
      <Polyline
        points={avgPoints}
        fill="none"
        stroke={colors.primary}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingBottom: 20,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
  },
  // Header
  header: {
    flexDirection: 'row',
    padding: spacing.lg,
    gap: spacing.lg,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  headerImage: {
    width: 80,
    height: 80,
    borderRadius: borderRadius.lg,
    backgroundColor: colors.borderLight,
  },
  attributionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: 2,
    maxWidth: 80,
  },
  attributionText: {
    fontSize: 8,
    color: colors.text.tertiary,
    flex: 1,
  },
  headerInfo: {
    flex: 1,
    gap: 4,
  },
  headerCategory: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  headerName: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text.primary,
  },
  headerCpc: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  headerPriceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: 4,
  },
  headerPrice: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.primary,
    fontFamily: 'monospace',
  },
  // Chart
  chartCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
  },
  sectionTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
    marginBottom: spacing.md,
  },
  timeRangeRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  timeRangeBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.borderLight,
  },
  timeRangeBtnActive: {
    backgroundColor: colors.primary,
  },
  timeRangeText: {
    fontSize: fontSize.xs,
    fontWeight: '600',
    color: colors.text.secondary,
  },
  timeRangeTextActive: {
    color: colors.text.inverse,
  },
  chartContainer: {
    alignItems: 'center',
  },
  noDataContainer: {
    paddingVertical: spacing.xxl,
    alignItems: 'center',
  },
  noDataText: {
    fontSize: fontSize.sm,
    color: colors.text.tertiary,
    textAlign: 'center',
  },
  // Supply
  supplyStats: {
    flexDirection: 'row',
    gap: spacing.lg,
  },
  supplyStat: {
    flex: 1,
    backgroundColor: colors.primary + '10',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    alignItems: 'center',
    gap: 4,
  },
  supplyStatValue: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.primary,
  },
  supplyStatLabel: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
});
