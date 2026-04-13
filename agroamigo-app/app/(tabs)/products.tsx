import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, FlatList, StyleSheet, Image, Pressable, ActivityIndicator } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SearchBar } from '../../src/components/SearchBar';
import { Sparkline } from '../../src/components/Sparkline';
import { PriceChangeIndicator } from '../../src/components/PriceChangeIndicator';
import { getProducts, getCategories, getSubcategories } from '../../src/api/products';
import { getProductImageUrl } from '../../src/lib/images';
import { formatCOP } from '../../src/lib/format';

export default function ProductsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ categoryId?: string }>();
  const [products, setProducts] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(params.categoryId);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCategories().then(c => setCategories(c || []));
  }, []);

  useEffect(() => {
    loadProducts();
  }, [selectedCategory, search]);

  async function loadProducts() {
    setLoading(true);
    try {
      const data = await getProducts({
        categoryId: selectedCategory,
        search: search.length >= 2 ? search : undefined,
        limit: 60,
      });
      setProducts(data || []);
    } catch (err) {
      console.error('Error loading products:', err);
    } finally {
      setLoading(false);
    }
  }

  const renderProduct = useCallback(({ item }: { item: any }) => {
    const categoryName = item.dim_subcategory?.dim_category?.canonical_name;
    const subcategoryName = item.dim_subcategory?.canonical_name;

    return (
      <Card
        style={styles.productCard}
        onPress={() => router.push(`/product/${item.id}`)}
      >
        <View style={styles.productRow}>
          <Image
            source={{ uri: getProductImageUrl(item.canonical_name, categoryName) }}
            style={styles.productImage}
          />
          <View style={styles.productInfo}>
            <Text style={styles.productName} numberOfLines={1}>{item.canonical_name}</Text>
            <Text style={styles.productCategory} numberOfLines={1}>
              {subcategoryName || categoryName || ''}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
        </View>
      </Card>
    );
  }, [router]);

  return (
    <View style={styles.container}>
      <SearchBar
        value={search}
        onChangeText={setSearch}
        placeholder="Buscar producto..."
      />

      {/* Category filter chips */}
      <FlatList
        horizontal
        data={[{ id: undefined, canonical_name: 'Todos' }, ...categories]}
        keyExtractor={(item) => item.id || 'all'}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipContainer}
        style={styles.chipList}
        renderItem={({ item }) => (
          <Pressable
            style={[
              styles.chip,
              selectedCategory === item.id && styles.chipActive,
            ]}
            onPress={() => setSelectedCategory(item.id)}
          >
            <Text style={[
              styles.chipText,
              selectedCategory === item.id && styles.chipTextActive,
            ]}>
              {item.canonical_name}
            </Text>
          </Pressable>
        )}
      />

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={products}
          keyExtractor={(item) => item.id}
          renderItem={renderProduct}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text style={styles.emptyText}>No se encontraron productos</Text>
          }
        />
      )}
    </View>
  );
}

import { Ionicons } from '@expo/vector-icons';

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    paddingTop: spacing.md,
  },
  chipList: {
    maxHeight: 44,
    marginBottom: spacing.sm,
  },
  chipContainer: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    fontWeight: '500',
  },
  chipTextActive: {
    color: colors.text.inverse,
  },
  listContent: {
    paddingBottom: 20,
  },
  productCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  productRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  productImage: {
    width: 48,
    height: 48,
    borderRadius: borderRadius.md,
    backgroundColor: colors.borderLight,
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
  productCategory: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 40,
    fontSize: fontSize.md,
    color: colors.text.tertiary,
  },
});
