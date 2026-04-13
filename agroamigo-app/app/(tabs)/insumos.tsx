import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, FlatList, SectionList, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SearchBar } from '../../src/components/SearchBar';
import { getInsumoGrupos, getInsumoSubgrupos, getInsumos } from '../../src/api/insumos';

export default function InsumosScreen() {
  const router = useRouter();
  const [grupos, setGrupos] = useState<any[]>([]);
  const [subgrupos, setSubgrupos] = useState<any[]>([]);
  const [insumos, setInsumos] = useState<any[]>([]);
  const [selectedGrupo, setSelectedGrupo] = useState<string | undefined>();
  const [selectedSubgrupo, setSelectedSubgrupo] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInsumoGrupos().then(g => setGrupos(g || []));
    loadInsumos();
  }, []);

  useEffect(() => {
    if (selectedGrupo) {
      getInsumoSubgrupos(selectedGrupo).then(s => setSubgrupos(s || []));
      setSelectedSubgrupo(undefined);
    } else {
      setSubgrupos([]);
      setSelectedSubgrupo(undefined);
    }
  }, [selectedGrupo]);

  useEffect(() => {
    loadInsumos();
  }, [selectedGrupo, selectedSubgrupo, search]);

  async function loadInsumos() {
    setLoading(true);
    try {
      const data = await getInsumos({
        grupoId: selectedGrupo,
        subgrupoId: selectedSubgrupo,
        search: search.length >= 2 ? search : undefined,
        limit: 60,
      });
      setInsumos(data || []);
    } catch (err) {
      console.error('Error loading insumos:', err);
    } finally {
      setLoading(false);
    }
  }

  const renderInsumo = useCallback(({ item }: { item: any }) => (
    <Card
      style={styles.insumoCard}
      onPress={() => router.push(`/insumo/${item.id}`)}
    >
      <View style={styles.insumoRow}>
        <View style={styles.insumoIcon}>
          <Ionicons name="flask" size={22} color={colors.secondary} />
        </View>
        <View style={styles.insumoInfo}>
          <Text style={styles.insumoName} numberOfLines={1}>{item.canonical_name}</Text>
          <Text style={styles.insumoSubgrupo} numberOfLines={1}>
            {item.subgrupo || item.grupo || ''}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
      </View>
    </Card>
  ), [router]);

  return (
    <View style={styles.container}>
      <SearchBar
        value={search}
        onChangeText={setSearch}
        placeholder="Buscar insumo..."
      />

      {/* Grupo filter chips */}
      <FlatList
        horizontal
        data={[{ id: undefined, canonical_name: 'Todos' }, ...grupos]}
        keyExtractor={(item) => item.id || 'all'}
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipContainer}
        style={styles.chipList}
        renderItem={({ item }) => (
          <Pressable
            style={[styles.chip, selectedGrupo === item.id && styles.chipActive]}
            onPress={() => setSelectedGrupo(item.id === selectedGrupo ? undefined : item.id)}
          >
            <Text style={[styles.chipText, selectedGrupo === item.id && styles.chipTextActive]}>
              {item.canonical_name}
            </Text>
          </Pressable>
        )}
      />

      {/* Subgrupo chips (when grupo selected) */}
      {subgrupos.length > 0 && (
        <FlatList
          horizontal
          data={subgrupos}
          keyExtractor={(item) => item.id}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipContainer}
          style={styles.chipList}
          renderItem={({ item }) => (
            <Pressable
              style={[styles.chipSmall, selectedSubgrupo === item.id && styles.chipActive]}
              onPress={() => setSelectedSubgrupo(item.id === selectedSubgrupo ? undefined : item.id)}
            >
              <Text style={[styles.chipTextSmall, selectedSubgrupo === item.id && styles.chipTextActive]}>
                {item.canonical_name}
              </Text>
            </Pressable>
          )}
        />
      )}

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={insumos}
          keyExtractor={(item) => item.id}
          renderItem={renderInsumo}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text style={styles.emptyText}>No se encontraron insumos</Text>
          }
        />
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
  chipList: {
    maxHeight: 40,
    marginBottom: spacing.xs,
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
  chipSmall: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  chipActive: {
    backgroundColor: colors.secondary,
    borderColor: colors.secondary,
  },
  chipText: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    fontWeight: '500',
  },
  chipTextSmall: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
    fontWeight: '500',
  },
  chipTextActive: {
    color: colors.text.inverse,
  },
  listContent: {
    paddingBottom: 20,
    paddingTop: spacing.sm,
  },
  insumoCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  insumoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  insumoIcon: {
    width: 44,
    height: 44,
    borderRadius: borderRadius.md,
    backgroundColor: colors.secondary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  insumoInfo: {
    flex: 1,
    gap: 2,
  },
  insumoName: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  insumoSubgrupo: {
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
