import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, SectionList, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SearchBar } from '../../src/components/SearchBar';
import { getMarkets } from '../../src/api/markets';
import { useTranslation } from '../../src/lib/useTranslation';

interface MarketItem {
  id: string;
  canonical_name: string;
  city_name: string;
  department_name: string;
}

interface Section {
  title: string;
  data: MarketItem[];
}

export default function MarketsScreen() {
  const router = useRouter();
  const t = useTranslation();
  const [sections, setSections] = useState<Section[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMarkets();
  }, []);

  async function loadMarkets() {
    try {
      const data = await getMarkets();
      if (!data) return;

      // Group by department
      const grouped = new Map<string, MarketItem[]>();
      for (const m of data) {
        const dept = (m as any).dim_city?.dim_department?.canonical_name || 'Otro';
        const city = (m as any).dim_city?.canonical_name || '';
        const item: MarketItem = {
          id: m.id,
          canonical_name: m.canonical_name,
          city_name: city,
          department_name: dept,
        };
        if (!grouped.has(dept)) grouped.set(dept, []);
        grouped.get(dept)!.push(item);
      }

      const secs: Section[] = Array.from(grouped.entries())
        .map(([title, data]) => ({ title, data }))
        .sort((a, b) => a.title.localeCompare(b.title));

      setSections(secs);
    } catch (err) {
      console.error('Error loading markets:', err);
    } finally {
      setLoading(false);
    }
  }

  const filteredSections = useMemo(() => {
    if (search.length < 2) return sections;
    return sections
      .map(s => ({
        ...s,
        data: s.data.filter(m =>
          m.canonical_name.toLowerCase().includes(search.toLowerCase()) ||
          m.city_name.toLowerCase().includes(search.toLowerCase())
        ),
      }))
      .filter(s => s.data.length > 0);
  }, [sections, search]);

  const renderMarket = useCallback(({ item }: { item: MarketItem }) => (
    <Card
      style={styles.marketCard}
      onPress={() => router.push(`/market/${item.id}`)}
    >
      <View style={styles.marketRow}>
        <View style={styles.marketIcon}>
          <Ionicons name="storefront" size={24} color={colors.primary} />
        </View>
        <View style={styles.marketInfo}>
          <Text style={styles.marketName}>{item.canonical_name}</Text>
          <Text style={styles.marketCity}>{item.city_name}</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
      </View>
    </Card>
  ), [router]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <SearchBar
        value={search}
        onChangeText={setSearch}
        placeholder={t.markets_search}
      />
      <View style={{ flex: 1 }}>
        <SectionList
          sections={filteredSections}
          keyExtractor={(item) => item.id}
          renderItem={renderMarket}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              <Ionicons name="location" size={14} color={colors.primary} />
              <Text style={styles.sectionTitle}>{section.title}</Text>
            </View>
          )}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text style={styles.emptyText}>{t.markets_not_found}</Text>
          }
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    paddingTop: spacing.md,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
  },
  listContent: {
    paddingBottom: 20,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: fontSize.md,
    fontWeight: '700',
    color: colors.text.primary,
  },
  marketCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  marketRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  marketIcon: {
    width: 44,
    height: 44,
    borderRadius: borderRadius.md,
    backgroundColor: colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  marketInfo: {
    flex: 1,
    gap: 2,
  },
  marketName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  marketCity: {
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
