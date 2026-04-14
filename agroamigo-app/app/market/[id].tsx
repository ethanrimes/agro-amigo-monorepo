import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { getMarketById, getMarketProducts } from '../../src/api/markets';
import { formatCOP, formatDateShort, formatPriceContext } from '../../src/lib/format';

export default function MarketDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [market, setMarket] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMarket();
  }, [id]);

  async function loadMarket() {
    try {
      const [mkt, prods] = await Promise.all([
        getMarketById(id!),
        getMarketProducts(id!, 200),
      ]);
      setMarket(mkt);

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
        <Text>Mercado no encontrado</Text>
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
            <Text style={styles.statLabel}>Productos</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{categoryGroups.length}</Text>
            <Text style={styles.statLabel}>Categorías</Text>
          </View>
        </View>

        {/* Products grouped by category */}
        <Card style={styles.productsCard}>
          <Text style={styles.sectionTitle}>Productos recientes</Text>
          {sharedDate && (
            <Text style={styles.dateContext}>Precios al {formatDateShort(sharedDate)}</Text>
          )}

          {products.length === 0 ? (
            <Text style={styles.noDataText}>Sin datos de precios recientes</Text>
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
                              <Text style={styles.productName} numberOfLines={1}>
                                {p.dim_product?.canonical_name || 'Producto'}
                              </Text>
                              {ctx ? <Text style={styles.productContext} numberOfLines={1}>{ctx}</Text> : null}
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
});
