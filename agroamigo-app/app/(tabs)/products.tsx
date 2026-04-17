import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, SectionList, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SearchBar } from '../../src/components/SearchBar';
import { ProductImage } from '../../src/components/ProductImage';
import { getProducts, getCategories } from '../../src/api/products';
import { useTranslation } from '../../src/lib/useTranslation';

interface Section {
  title: string;
  category: string;
  isFirstInCategory: boolean;
  data: any[];
}

function buildSections(products: any[]): Section[] {
  const catMap = new Map<string, Map<string, any[]>>();

  for (const p of products) {
    const catName = p.dim_subcategory?.dim_category?.canonical_name || 'Otro';
    const subName = p.dim_subcategory?.canonical_name || 'General';
    if (!catMap.has(catName)) catMap.set(catName, new Map());
    const subMap = catMap.get(catName)!;
    if (!subMap.has(subName)) subMap.set(subName, []);
    subMap.get(subName)!.push(p);
  }

  const sections: Section[] = [];
  for (const [catName, subMap] of [...catMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    let first = true;
    for (const [subName, items] of [...subMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      sections.push({ title: subName, category: catName, isFirstInCategory: first, data: items });
      first = false;
    }
  }
  return sections;
}

export default function ProductsScreen() {
  const router = useRouter();
  const t = useTranslation();
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
        limit: 600,
      });
      setProducts(data || []);
    } catch (err) {
      console.error('Error loading products:', err);
    } finally {
      setLoading(false);
    }
  }

  const sections = useMemo(() => buildSections(products), [products]);

  const renderProduct = useCallback(({ item }: { item: any }) => {
    const categoryName = item.dim_subcategory?.dim_category?.canonical_name;

    return (
      <Card
        style={styles.productCard}
        onPress={() => router.push(`/product/${item.id}`)}
      >
        <View style={styles.productRow}>
          <ProductImage
            productName={item.canonical_name}
            categoryName={categoryName}
            style={styles.productImage}
          />
          <View style={styles.productInfo}>
            <Text style={styles.productName}>{item.canonical_name}</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
        </View>
      </Card>
    );
  }, [router]);

  const renderSectionHeader = useCallback(({ section }: { section: Section }) => {
    return (
      <View>
        {section.isFirstInCategory && (
          <View style={styles.categoryHeader}>
            <Ionicons name="leaf" size={14} color={colors.primary} />
            <Text style={styles.categoryHeaderText}>{section.category}</Text>
          </View>
        )}
        <View style={styles.subcategoryHeader}>
          <Text style={styles.subcategoryHeaderText}>{section.title}</Text>
          <Text style={styles.subcategoryCount}>{section.data.length}</Text>
        </View>
      </View>
    );
  }, []);

  return (
    <View style={styles.container}>
      <SearchBar
        value={search}
        onChangeText={setSearch}
        placeholder={t.products_search}
      />

      <View style={styles.chipWrap}>
        {[{ id: undefined, canonical_name: t.products_all }, ...categories].map(item => (
          <Pressable
            key={item.id || 'all'}
            style={[styles.chip, selectedCategory === item.id && styles.chipActive]}
            onPress={() => setSelectedCategory(item.id)}
          >
            <Text style={[styles.chipText, selectedCategory === item.id && styles.chipTextActive]}>
              {item.canonical_name}
            </Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <View style={{ flex: 1 }}>
          <SectionList
            sections={sections}
            keyExtractor={(item) => item.id}
            renderItem={renderProduct}
            renderSectionHeader={renderSectionHeader as any}
            contentContainerStyle={styles.listContent}
            stickySectionHeadersEnabled={false}
            initialNumToRender={20}
            ListEmptyComponent={
              <Text style={styles.emptyText}>{t.products_not_found}</Text>
            }
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    paddingTop: spacing.md,
  },
  chipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
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
  categoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xs,
  },
  categoryHeaderText: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.primary,
  },
  subcategoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs,
  },
  subcategoryHeaderText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.text.secondary,
  },
  subcategoryCount: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  productCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.xs,
  },
  productRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  productImage: {
    width: 44,
    height: 44,
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
  emptyText: {
    textAlign: 'center',
    marginTop: 40,
    fontSize: fontSize.md,
    color: colors.text.tertiary,
  },
});
