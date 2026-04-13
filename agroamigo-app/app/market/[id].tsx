import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { getMarketById, getMarketProducts } from '../../src/api/markets';
import { formatCOP } from '../../src/lib/format';

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
        getMarketProducts(id!, 100),
      ]);
      setMarket(mkt);

      // Deduplicate products by product_id, keeping most recent
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
            <Text style={styles.statValue}>{market.sipsa_id || '—'}</Text>
            <Text style={styles.statLabel}>SIPSA ID</Text>
          </View>
        </View>

        {/* Products at this market */}
        <Card style={styles.productsCard}>
          <Text style={styles.sectionTitle}>Productos recientes</Text>
          {products.length === 0 ? (
            <Text style={styles.noDataText}>Sin datos de precios recientes</Text>
          ) : (
            products.map((p) => (
              <Card
                key={p.product_id}
                style={styles.productRow}
                onPress={() => router.push(`/product/${p.product_id}`)}
                padding={spacing.md}
              >
                <View style={styles.productRowInner}>
                  <View style={styles.productInfo}>
                    <Text style={styles.productName} numberOfLines={1}>
                      {(p as any).dim_product?.canonical_name || 'Producto'}
                    </Text>
                    <Text style={styles.productDate}>{p.price_date}</Text>
                  </View>
                  <View style={styles.productPriceCol}>
                    <Text style={styles.productPrice}>
                      {formatCOP(p.min_price)} - {formatCOP(p.max_price)}
                    </Text>
                  </View>
                </View>
              </Card>
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
    marginBottom: spacing.md,
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
  },
  productName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  productDate: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  productPriceCol: {
    alignItems: 'flex-end',
  },
  productPrice: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.primary,
    fontFamily: 'monospace',
  },
  noDataText: {
    fontSize: fontSize.sm,
    color: colors.text.tertiary,
    textAlign: 'center',
    paddingVertical: spacing.xl,
  },
});
