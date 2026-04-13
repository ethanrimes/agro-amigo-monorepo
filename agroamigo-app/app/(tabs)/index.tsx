import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Image, Pressable, FlatList, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SectionHeader } from '../../src/components/SectionHeader';
import { Sparkline } from '../../src/components/Sparkline';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { getCategories, getTrendingProducts } from '../../src/api/products';
import { getCategoryImageUrl } from '../../src/lib/images';
import { formatCOP, formatCOPCompact, pctChange } from '../../src/lib/format';

const CATEGORY_ICONS: Record<string, string> = {
  'Frutas': 'nutrition',
  'Verduras y hortalizas': 'leaf',
  'Tubérculos, raíces y plátanos': 'earth',
  'Carnes': 'restaurant',
  'Pescados': 'fish',
  'Granos y cereales': 'grid',
  'Procesados': 'cube',
  'Lácteos y huevos': 'water',
};

export default function HomeScreen() {
  const router = useRouter();
  const [categories, setCategories] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [cats, trend] = await Promise.all([
        getCategories(),
        getTrendingProducts(200),
      ]);
      setCategories(cats || []);

      // Aggregate trending by product — compute a simple price change
      const productMap = new Map<string, { name: string; prices: number[]; productId: string }>();
      for (const obs of (trend || [])) {
        const pid = obs.product_id;
        const name = obs.dim_product?.canonical_name || 'Unknown';
        const price = obs.avg_price || obs.max_price || obs.min_price || 0;
        if (!productMap.has(pid)) {
          productMap.set(pid, { name, prices: [], productId: pid });
        }
        productMap.get(pid)!.prices.push(price);
      }

      const trendingList = Array.from(productMap.values())
        .filter(p => p.prices.length >= 2)
        .map(p => {
          const oldest = p.prices[p.prices.length - 1];
          const newest = p.prices[0];
          return {
            ...p,
            change: pctChange(oldest, newest),
            latestPrice: newest,
          };
        })
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
        .slice(0, 15);

      setTrending(trendingList);
    } catch (err) {
      console.error('Error loading home data:', err);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Cargando datos...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Price Ticker */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.ticker}
        contentContainerStyle={styles.tickerContent}
      >
        {trending.slice(0, 8).map((item, i) => (
          <Pressable
            key={item.productId}
            style={styles.tickerItem}
            onPress={() => router.push(`/product/${item.productId}`)}
          >
            <Text style={styles.tickerName} numberOfLines={1}>{item.name}</Text>
            <Text style={styles.tickerPrice}>{formatCOPCompact(item.latestPrice)}</Text>
            <PriceChangeIndicator value={item.change} size="sm" />
          </Pressable>
        ))}
      </ScrollView>

      {/* Categories */}
      <SectionHeader title="Categorías" />
      <View style={styles.categoryGrid}>
        {categories.map((cat) => (
          <Pressable
            key={cat.id}
            style={styles.categoryCard}
            onPress={() => router.push({ pathname: '/products', params: { categoryId: cat.id } } as any)}
          >
            <Image
              source={{ uri: getCategoryImageUrl(cat.canonical_name) }}
              style={styles.categoryImage}
            />
            <View style={styles.categoryOverlay}>
              <Ionicons
                name={(CATEGORY_ICONS[cat.canonical_name] || 'leaf') as any}
                size={22}
                color={colors.text.inverse}
              />
              <Text style={styles.categoryName} numberOfLines={2}>
                {cat.canonical_name}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>

      {/* Trending */}
      <SectionHeader title="Tendencias de la semana" />
      {trending.map((item) => (
        <Card
          key={item.productId}
          style={styles.trendingCard}
          onPress={() => router.push(`/product/${item.productId}`)}
        >
          <View style={styles.trendingRow}>
            <View style={styles.trendingInfo}>
              <Text style={styles.trendingName} numberOfLines={1}>{item.name}</Text>
              <Text style={styles.trendingPrice}>{formatCOP(item.latestPrice)}</Text>
            </View>
            <View style={styles.trendingRight}>
              <Sparkline data={[...item.prices].reverse()} width={50} height={20} />
              <PriceChangeIndicator value={item.change} size="sm" />
            </View>
          </View>
        </Card>
      ))}

      <View style={{ height: 40 }} />
    </ScrollView>
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
    gap: spacing.md,
  },
  loadingText: {
    fontSize: fontSize.md,
    color: colors.text.secondary,
  },
  // Ticker
  ticker: {
    backgroundColor: colors.dark,
    maxHeight: 56,
  },
  tickerContent: {
    paddingHorizontal: spacing.md,
    gap: spacing.lg,
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  tickerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingRight: spacing.lg,
  },
  tickerName: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontWeight: '600',
    maxWidth: 80,
  },
  tickerPrice: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontFamily: 'monospace',
  },
  // Categories
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  categoryCard: {
    width: '48%' as any,
    height: 100,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    flexGrow: 1,
    flexBasis: '46%',
  },
  categoryImage: {
    width: '100%',
    height: '100%',
    position: 'absolute',
  },
  categoryOverlay: {
    flex: 1,
    backgroundColor: 'rgba(26, 46, 26, 0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.sm,
    gap: 4,
  },
  categoryName: {
    color: colors.text.inverse,
    fontSize: fontSize.sm,
    fontWeight: '700',
    textAlign: 'center',
  },
  // Trending
  trendingCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  trendingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  trendingInfo: {
    flex: 1,
    gap: 2,
  },
  trendingName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  trendingPrice: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    fontFamily: 'monospace',
  },
  trendingRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
});
