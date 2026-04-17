import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator, Pressable } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { CommentsSection } from '../../src/components/CommentsSection';
import { MarketPriceComparator } from '../../src/components/MarketPriceComparator';
import { MarketSupplyComparator } from '../../src/components/MarketSupplyComparator';
import { getMarketById, getMarketProducts, getMarkets, getMarketSupply, getMarketSupplySummary, getMarketTopProducts, getMarketTopProvenance, SupplySummary } from '../../src/api/markets';
import { formatCOP, formatDateShort, formatPriceContext, formatKg } from '../../src/lib/format';
import { useTranslation } from '../../src/lib/useTranslation';

const SUPPLY_COLORS = [colors.primary, colors.accent.orange, colors.accent.blue, colors.secondary, colors.primaryLight, '#9C27B0', '#00BCD4', '#FF5722'];

export default function MarketDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const t = useTranslation();
  const [market, setMarket] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [supply, setSupply] = useState<any[]>([]);
  const [allMarkets, setAllMarkets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Supply section — all aggregation is server-side via RPCs. These three
  // states are the only payload we carry for this section; state changes
  // re-fire the RPC effects below.
  const [supplyTimeRange, setSupplyTimeRange] = useState<number>(1); // default 1m
  const [selectedSupplyProduct, setSelectedSupplyProduct] = useState<string | null>(null);
  const [selectedSupplyProv, setSelectedSupplyProv] = useState<string | null>(null);
  const [supplySummary, setSupplySummary] = useState<SupplySummary | null>(null);
  const [topSuppliedProducts, setTopSuppliedProducts] = useState<{ product_id: string; product_name: string; total_kg: number }[]>([]);
  const [provenanceBars, setProvenanceBars] = useState<{ dept_name: string; total_kg: number }[]>([]);
  const [supplyLoading, setSupplyLoading] = useState(false);

  // Stable ref so useMemo closures capture the same array across renders.
  const SUPPLY_TIME_RANGES = useMemo(() => [
    { label: t.time_1w, days: 7 }, { label: t.time_1m, days: 30 }, { label: t.time_3m, days: 90 },
    { label: t.time_6m, days: 180 }, { label: t.time_1y, days: 365 }, { label: t.time_all, days: 0 },
  ], [t]);

  useEffect(() => {
    loadMarket();
  }, [id]);

  async function loadMarket() {
    try {
      // Note: getMarketSupply(..., 30) still runs for the comparator only;
      // it's capped to 30 days so it stays fast even on Corabastos-sized
      // markets. The main supply section below is driven by RPCs.
      const [mkt, prods, sup, mkts] = await Promise.all([
        getMarketById(id!),
        getMarketProducts(id!, 200),
        getMarketSupply(id!, 30).catch(() => []),
        getMarkets().catch(() => []),
      ]);
      setMarket(mkt);
      setSupply(sup || []);
      setAllMarkets(mkts || []);

      // Deduplicate: keep most recent observation per product
      const productMap = new Map<string, any>();
      for (const p of (prods || [])) {
        const pid = p.product_id;
        if (!productMap.has(pid) || p.price_date > productMap.get(pid).price_date) {
          productMap.set(pid, p);
        }
      }
      setProducts(Array.from(productMap.values()));
    } catch (err) {
      console.error('Error loading market:', err);
    } finally {
      setLoading(false);
    }
  }

  // Group products by category > subcategory
  const categoryGroups = useMemo(() => {
    const catMap = new Map<string, { subcategories: Map<string, any[]> }>();

    for (const p of products) {
      const catName = p.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro';
      const subName = p.dim_product?.dim_subcategory?.canonical_name || 'General';

      if (!catMap.has(catName)) catMap.set(catName, { subcategories: new Map() });
      const subMap = catMap.get(catName)!.subcategories;
      if (!subMap.has(subName)) subMap.set(subName, []);
      subMap.get(subName)!.push(p);
    }

    return [...catMap.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([catName, { subcategories }]) => ({
        category: catName,
        subcategories: [...subcategories.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([subName, items]) => ({ name: subName, items })),
      }));
  }, [products]);

  // Check if all products share the same date
  const sharedDate = useMemo(() => {
    if (products.length === 0) return null;
    const firstDate = products[0].price_date;
    return products.every(p => p.price_date === firstDate) ? firstDate : null;
  }, [products]);

  // ═══ SUPPLY CASCADE: server-side aggregation via RPCs ═══
  //
  // Whenever the user changes the time tile or clicks a bar to cross-filter,
  // fire three tiny parallel RPCs. No raw rows are fetched for this section.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    const tr = SUPPLY_TIME_RANGES[supplyTimeRange];
    const days = tr?.days ?? 30;
    setSupplyLoading(true);
    Promise.all([
      getMarketSupplySummary(id, days, selectedSupplyProduct, selectedSupplyProv).catch(() => null),
      // Top-products bars: filter by selected provenance (so user can pick).
      getMarketTopProducts(id, days, selectedSupplyProv, 10).catch(() => []),
      // Provenance bars: filter by selected product.
      getMarketTopProvenance(id, days, selectedSupplyProduct, 15).catch(() => []),
    ]).then(([summary, products, prov]) => {
      if (cancelled) return;
      setSupplySummary(summary);
      setTopSuppliedProducts(products);
      setProvenanceBars(prov);
    }).finally(() => { if (!cancelled) setSupplyLoading(false); });
    return () => { cancelled = true; };
  }, [id, supplyTimeRange, selectedSupplyProduct, selectedSupplyProv, SUPPLY_TIME_RANGES]);

  const totalSupplyKg = supplySummary?.total_kg ?? 0;
  const dailyAvgSupplyKg = supplySummary?.daily_avg_kg ?? 0;
  const supplyDateRange = supplySummary?.oldest_obs && supplySummary?.newest_obs
    ? { from: supplySummary.oldest_obs, to: supplySummary.newest_obs }
    : null;
  const availableSupplyRanges = SUPPLY_TIME_RANGES.map((tr, i) => ({ ...tr, index: i }));

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!market) {
    return (
      <View style={styles.loadingContainer}>
        <Text>{t.market_not_found}</Text>
      </View>
    );
  }

  const cityName = (market as any).dim_city?.canonical_name || '';
  const deptName = (market as any).dim_city?.dim_department?.canonical_name || '';

  return (
    <>
      <Stack.Screen options={{ title: market.canonical_name }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerIcon}>
            <Ionicons name="storefront" size={36} color={colors.primary} />
          </View>
          <View style={styles.headerInfo}>
            <Text style={styles.headerName}>{market.canonical_name}</Text>
            <View style={styles.locationRow}>
              <Ionicons name="location" size={14} color={colors.text.tertiary} />
              <Text style={styles.headerLocation}>{cityName}, {deptName}</Text>
            </View>
          </View>
        </View>

        {/* Stats */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{products.length}</Text>
            <Text style={styles.statLabel}>{t.market_products}</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{categoryGroups.length}</Text>
            <Text style={styles.statLabel}>{t.market_categories}</Text>
          </View>
        </View>

        {/* Price section header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingTop: 16, paddingBottom: 4 }}>
          <Ionicons name="pricetags-outline" size={18} color={colors.primary} />
          <Text style={{ fontSize: 17, fontWeight: '700', color: colors.text.primary }}>{t.product_price_section}</Text>
        </View>

        {/* Products grouped by category */}
        <Card style={styles.productsCard}>
          <Text style={styles.sectionTitle}>{t.market_recent_products}</Text>
          {sharedDate && (
            <Text style={styles.dateContext}>{t.market_prices_at} {formatDateShort(sharedDate)}</Text>
          )}

          {products.length === 0 ? (
            <Text style={styles.noDataText}>{t.market_no_recent_data}</Text>
          ) : (
            categoryGroups.map((group, gi) => (
              <ExpandableSection
                key={group.category}
                title={group.category}
                icon="leaf"
                badge={group.subcategories.reduce((s, sub) => s + sub.items.length, 0)}
                initiallyExpanded={gi < 3}
              >
                {group.subcategories.map((sub) => (
                  <View key={sub.name}>
                    {group.subcategories.length > 1 && (
                      <Text style={styles.subHeader}>{sub.name}</Text>
                    )}
                    {sub.items.map((p: any) => {
                      const presentation = p.dim_presentation?.canonical_name;
                      const units = p.dim_units?.canonical_name;
                      const ctx = formatPriceContext(presentation, units);
                      return (
                        <Card
                          key={p.product_id}
                          style={styles.productRow}
                          onPress={() => router.push(`/product/${p.product_id}`)}
                          padding={spacing.sm}
                        >
                          <View style={styles.productRowInner}>
                            <View style={styles.productInfo}>
                              <Text style={styles.productName}>
                                {p.dim_product?.canonical_name || t.market_product_fallback}
                              </Text>
                              {ctx ? <Text style={styles.productContext}>{ctx}</Text> : null}
                            </View>
                            <View style={styles.productPriceCol}>
                              <Text style={styles.productPrice}>
                                {formatCOP(p.min_price)}{p.max_price !== p.min_price ? ` - ${formatCOP(p.max_price)}` : ''}
                              </Text>
                              {!sharedDate && (
                                <Text style={styles.productDate}>{formatDateShort(p.price_date)}</Text>
                              )}
                            </View>
                          </View>
                        </Card>
                      );
                    })}
                  </View>
                ))}
              </ExpandableSection>
            ))
          )}
        </Card>

        {/* Price Comparator */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.sm }}>
          <MarketPriceComparator currentMarket={market} products={products} markets={allMarkets} />
        </Card>

        {/* Supply section header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingTop: 16, paddingBottom: 4 }}>
          <Ionicons name="cube-outline" size={18} color={colors.accent.blue} />
          <Text style={{ fontSize: 17, fontWeight: '700', color: colors.text.primary }}>{t.product_supply_section}</Text>
        </View>

        {/* Supply summary: time tiles + cumulative/daily-avg blocks +
            linked top-products and provenance bars. */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.xs }}>
          {supply.length === 0 ? (
            <Text style={styles.noDataText}>{t.product_no_supply_data}</Text>
          ) : (
            <>
              {/* Time range tiles */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                {availableSupplyRanges.map(tr => {
                  const active = tr.index === supplyTimeRange;
                  return (
                    <Pressable
                      key={`sup-${tr.label}`}
                      onPress={() => setSupplyTimeRange(tr.index)}
                      style={[styles.tile, active && { backgroundColor: colors.accent.blue, borderColor: colors.accent.blue }]}
                    >
                      <Text style={[styles.tileText, active && { color: colors.text.inverse }]}>{tr.label}</Text>
                    </Pressable>
                  );
                })}
              </View>

              {/* Active filter pills */}
              {(selectedSupplyProduct || selectedSupplyProv) && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
                  {selectedSupplyProduct && (
                    <Pressable
                      onPress={() => setSelectedSupplyProduct(null)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs, backgroundColor: colors.accent.blue + '15', paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: borderRadius.full }}
                    >
                      <Ionicons name="cube" size={12} color={colors.accent.blue} />
                      <Text style={{ fontSize: fontSize.xs, color: colors.accent.blue, fontWeight: '600' }} numberOfLines={1}>
                        {topSuppliedProducts.find(p => p.product_id === selectedSupplyProduct)?.product_name
                          || products.find(p => p.product_id === selectedSupplyProduct)?.dim_product?.canonical_name
                          || t.market_product_fallback}
                      </Text>
                      <Ionicons name="close-circle" size={14} color={colors.accent.blue} />
                    </Pressable>
                  )}
                  {selectedSupplyProv && (
                    <Pressable
                      onPress={() => setSelectedSupplyProv(null)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs, backgroundColor: colors.secondary + '15', paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: borderRadius.full }}
                    >
                      <Ionicons name="navigate" size={12} color={colors.secondary} />
                      <Text style={{ fontSize: fontSize.xs, color: colors.secondary, fontWeight: '600' }}>{selectedSupplyProv}</Text>
                      <Ionicons name="close-circle" size={14} color={colors.secondary} />
                    </Pressable>
                  )}
                </View>
              )}

              {supplyDateRange && (
                <Text style={styles.dateContext}>
                  {formatDateShort(supplyDateRange.from)} – {formatDateShort(supplyDateRange.to)}
                </Text>
              )}

              {/* Cumulative + daily average blocks */}
              <View style={styles.supplyStatsRow}>
                <View style={styles.supplyTotalBox}>
                  <Text style={styles.supplyTotalValue}>{formatKg(totalSupplyKg)}</Text>
                  <Text style={styles.supplyTotalLabel}>{t.product_total}</Text>
                </View>
                <View style={styles.supplyTotalBox}>
                  <Text style={styles.supplyTotalValue}>{formatKg(dailyAvgSupplyKg)}</Text>
                  <Text style={styles.supplyTotalLabel}>{t.product_daily_avg}</Text>
                </View>
              </View>

              {/* Top products (clickable — filters provenance) */}
              {topSuppliedProducts.length > 0 && (
                <>
                  <Text style={styles.supplySubHeader}>{t.market_products || 'Productos'}</Text>
                  <Text style={styles.supplyHint}>Toca para ver procedencia.</Text>
                  <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
                    {topSuppliedProducts.map(d => {
                      const active = selectedSupplyProduct === d.product_id;
                      const dim = selectedSupplyProduct && !active;
                      return (
                        <Pressable
                          key={d.product_id}
                          onPress={() => setSelectedSupplyProduct(active ? null : d.product_id)}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, opacity: dim ? 0.4 : 1 }}
                        >
                          <Text style={[styles.supplyBarName, active && { color: colors.accent.blue, fontWeight: '700' }]} numberOfLines={2}>{d.product_name}</Text>
                          <View style={styles.supplyBarTrack}>
                            <View style={[styles.supplyBarFill, { width: `${(d.total_kg / (topSuppliedProducts[0]?.total_kg || 1)) * 100}%` }]} />
                          </View>
                          <Text style={styles.supplyBarValue}>{formatKg(d.total_kg)}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </>
              )}

              {/* Provenance (clickable — filters top products) */}
              {provenanceBars.length > 0 && (
                <>
                  <Text style={styles.supplySubHeader}>{t.product_provenance || 'Procedencia'}</Text>
                  <Text style={styles.supplyHint}>Toca para ver solo este origen.</Text>
                  <View style={{ gap: spacing.sm }}>
                    {provenanceBars.map((d, i) => {
                      const active = selectedSupplyProv === d.dept_name;
                      const dim = selectedSupplyProv && !active;
                      return (
                        <Pressable
                          key={d.dept_name}
                          onPress={() => setSelectedSupplyProv(active ? null : d.dept_name)}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, opacity: dim ? 0.4 : 1 }}
                        >
                          <Text style={[styles.supplyBarName, active && { color: colors.secondary, fontWeight: '700' }]} numberOfLines={2}>{d.dept_name}</Text>
                          <View style={styles.supplyBarTrack}>
                            <View style={[styles.supplyBarFill, { width: `${(d.total_kg / (provenanceBars[0]?.total_kg || 1)) * 100}%`, backgroundColor: SUPPLY_COLORS[i % SUPPLY_COLORS.length] }]} />
                          </View>
                          <Text style={styles.supplyBarValue}>{formatKg(d.total_kg)}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </>
              )}
            </>
          )}
        </Card>

        {/* Supply Comparator */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.sm }}>
          <MarketSupplyComparator currentMarket={market} supply={supply} products={products} markets={allMarkets} />
        </Card>

        {/* Comments */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.lg }}>
          <CommentsSection entityType="market" entityId={id!} />
        </Card>

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
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
  header: {
    flexDirection: 'row',
    padding: spacing.lg,
    gap: spacing.lg,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
    alignItems: 'center',
  },
  headerIcon: {
    width: 64,
    height: 64,
    borderRadius: borderRadius.lg,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerInfo: {
    flex: 1,
    gap: 4,
  },
  headerName: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text.primary,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  headerLocation: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
  },
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  statBox: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    alignItems: 'center',
    gap: 4,
  },
  statValue: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.primary,
  },
  statLabel: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  productsCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
  },
  sectionTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  dateContext: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    marginBottom: spacing.md,
  },
  subHeader: {
    fontSize: fontSize.xs,
    fontWeight: '600',
    color: colors.text.tertiary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  productRow: {
    marginBottom: spacing.xs,
    backgroundColor: colors.background,
  },
  productRowInner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  productInfo: {
    flex: 1,
    gap: 2,
    marginRight: spacing.sm,
  },
  productName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  productContext: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  productPriceCol: {
    alignItems: 'flex-end',
    gap: 2,
  },
  productPrice: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.primary,
    fontFamily: 'monospace',
  },
  productDate: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  noDataText: {
    fontSize: fontSize.sm,
    color: colors.text.tertiary,
    textAlign: 'center',
    paddingVertical: spacing.xl,
  },
  supplyStatsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  supplyTotalBox: {
    flex: 1,
    backgroundColor: colors.accent.blue + '10',
    borderRadius: borderRadius.md,
    padding: spacing.sm,
    alignItems: 'center',
  },
  supplyTotalValue: {
    fontSize: fontSize.md,
    fontWeight: '700',
    color: colors.accent.blue,
  },
  supplyTotalLabel: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  supplyBarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  supplyBarName: {
    width: 100,
    fontSize: fontSize.xs,
    color: colors.text.secondary,
    textAlign: 'right',
  },
  supplyBarTrack: {
    flex: 1,
    height: 16,
    backgroundColor: colors.borderLight,
    borderRadius: 4,
    overflow: 'hidden',
  },
  supplyBarFill: {
    height: '100%',
    backgroundColor: colors.accent.blue,
    borderRadius: 4,
  },
  supplyBarValue: {
    width: 55,
    fontSize: fontSize.xs,
    color: colors.text.primary,
    fontFamily: 'monospace',
    fontWeight: '600',
  },
  supplySubHeader: {
    fontSize: fontSize.sm,
    fontWeight: '700',
    color: colors.text.primary,
    marginTop: spacing.sm,
    marginBottom: 2,
  },
  supplyHint: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    fontStyle: 'italic',
    marginBottom: spacing.xs,
  },
  tile: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  tileText: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
    fontWeight: '500',
  },
});
