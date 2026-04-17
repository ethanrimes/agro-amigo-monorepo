import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, SectionList, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { SearchBar } from '../../src/components/SearchBar';
import { getInsumoGrupos, getInsumoSubgrupos, getInsumos, getInsumoCpcTree } from '../../src/api/insumos';
import { useTranslation } from '../../src/lib/useTranslation';

interface Section {
  key: string;
  title: string;         // subgrupo name
  grupo: string;
  grupoId: string;
  isFirstInGrupo: boolean;
  isFirstInSubgrupo: boolean;  // first section of this subgrupo (covers the collapsible header row)
  subgrupoKey: string;   // grupo + subgrupo, used as collapse-state key
  subgrupoCount: number; // total items across all CPC splits of this subgrupo
  cpcCode: string;       // CPC code for this batch (or '' if none/single)
  cpcTitle: string;      // CPC description
  showCpcHeader: boolean; // show CPC sub-header within the subgrupo
  data: any[];
}

function buildSections(insumos: any[], cpcEntries: any[]): Section[] {
  const cpcMap = new Map<string, string>();
  for (const c of cpcEntries) cpcMap.set(c.code, c.title);

  // grupo -> subgrupo -> cpc -> items
  const grupoMap = new Map<string, { id: string; subMap: Map<string, { id: string; cpcMap: Map<string, any[]> }> }>();

  for (const ins of insumos) {
    const grupoName = ins.grupo || 'Otro';
    const grupoId = ins.grupo_id || 'other';
    const subgrupoName = ins.subgrupo || 'General';
    const subgrupoId = ins.subgrupo_id || 'general';
    const cpcCode = ins.cpc_id || '_none';

    if (!grupoMap.has(grupoName)) grupoMap.set(grupoName, { id: grupoId, subMap: new Map() });
    const g = grupoMap.get(grupoName)!;
    if (!g.subMap.has(subgrupoName)) g.subMap.set(subgrupoName, { id: subgrupoId, cpcMap: new Map() });
    const s = g.subMap.get(subgrupoName)!;
    if (!s.cpcMap.has(cpcCode)) s.cpcMap.set(cpcCode, []);
    s.cpcMap.get(cpcCode)!.push(ins);
  }

  const sections: Section[] = [];
  for (const [grupoName, grupo] of [...grupoMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    let firstInGrupo = true;
    for (const [subName, sub] of [...grupo.subMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      const cpcEntryList = [...sub.cpcMap.entries()].sort(([a], [b]) => {
        if (a === '_none') return 1; if (b === '_none') return -1; return a.localeCompare(b);
      });
      const subgrupoCount = cpcEntryList.reduce((n, [, items]) => n + items.length, 0);
      const subgrupoKey = `${grupoName}__${subName}`;
      let firstInSubgrupo = true;

      for (const [code, items] of cpcEntryList) {
        sections.push({
          key: `${grupoName}-${subName}-${code}`,
          title: subName,
          grupo: grupoName,
          grupoId: grupo.id,
          isFirstInGrupo: firstInGrupo,
          isFirstInSubgrupo: firstInSubgrupo,
          subgrupoKey,
          subgrupoCount,
          cpcCode: code !== '_none' ? code : '',
          cpcTitle: code !== '_none' ? (cpcMap.get(code) || '') : '',
          showCpcHeader: code !== '_none',
          data: items.sort((a: any, b: any) => a.canonical_name.localeCompare(b.canonical_name)),
        });
        firstInGrupo = false;
        firstInSubgrupo = false;
      }
    }
  }
  return sections;
}

export default function InsumosScreen() {
  const router = useRouter();
  const t = useTranslation();
  const [openSubgrupos, setOpenSubgrupos] = useState<Set<string>>(new Set());
  const [grupos, setGrupos] = useState<any[]>([]);
  const [subgrupos, setSubgrupos] = useState<any[]>([]);
  const [insumos, setInsumos] = useState<any[]>([]);
  const [cpcEntries, setCpcEntries] = useState<any[]>([]);
  const [selectedGrupo, setSelectedGrupo] = useState<string | undefined>();
  const [selectedSubgrupo, setSelectedSubgrupo] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInsumoGrupos().then(g => setGrupos(g || []));
    getInsumoCpcTree().then(c => setCpcEntries(c || [])).catch(() => {});
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

  useEffect(() => { loadInsumos(); }, [selectedGrupo, selectedSubgrupo, search]);

  async function loadInsumos() {
    setLoading(true);
    try {
      const data = await getInsumos({
        grupoId: selectedGrupo,
        subgrupoId: selectedSubgrupo,
        search: search.length >= 2 ? search : undefined,
        limit: 2000,
      });
      setInsumos(data || []);
    } catch (err) {
      console.error('Error loading insumos:', err);
    } finally {
      setLoading(false);
    }
  }

  const sections = useMemo(() => buildSections(insumos, cpcEntries), [insumos, cpcEntries]);

  // Hide items + CPC sub-headers for collapsed subgrupos; the tappable
  // subgrupo header itself stays visible via renderSectionHeader.
  const visibleSections = useMemo(
    () => sections.map(s => ({ ...s, data: openSubgrupos.has(s.subgrupoKey) ? s.data : [] })),
    [sections, openSubgrupos],
  );

  const toggleSubgrupo = useCallback((key: string) => {
    setOpenSubgrupos(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);

  const renderInsumo = useCallback(({ item }: { item: any }) => (
    <Card style={styles.insumoCard} onPress={() => router.push(`/insumo/${item.id}`)}>
      <View style={styles.insumoRow}>
        <View style={styles.insumoIcon}>
          <Ionicons name="flask" size={18} color={colors.secondary} />
        </View>
        <View style={styles.insumoInfo}>
          <Text style={styles.insumoName}>{item.canonical_name}</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
      </View>
    </Card>
  ), [router]);

  const renderSectionHeader = useCallback(({ section }: { section: Section }) => {
    const isOpen = openSubgrupos.has(section.subgrupoKey);
    return (
      <View>
        {section.isFirstInGrupo && (
          <View style={styles.grupoHeader}>
            <Ionicons name="flask" size={14} color={colors.secondary} />
            <Text style={styles.grupoHeaderText}>{section.grupo}</Text>
            <Text style={styles.grupoCount}>
              {sections.filter(s => s.grupo === section.grupo).reduce((n, s) => n + s.data.length, 0)}
            </Text>
          </View>
        )}
        {section.isFirstInSubgrupo && (
          <Pressable style={styles.subgrupoHeader} onPress={() => toggleSubgrupo(section.subgrupoKey)}>
            <Text style={styles.subgrupoHeaderText}>{section.title}</Text>
            <View style={styles.subgrupoMeta}>
              <Text style={styles.subgrupoCount}>{section.subgrupoCount}</Text>
              <Ionicons name={isOpen ? 'chevron-up' : 'chevron-down'} size={14} color={colors.text.tertiary} />
            </View>
          </Pressable>
        )}
        {isOpen && section.showCpcHeader && (
          <View style={styles.cpcHeader}>
            <Text style={styles.cpcCode}>{section.cpcCode}</Text>
            <Text style={styles.cpcTitle} numberOfLines={1}>{section.cpcTitle}</Text>
            <Text style={styles.cpcCount}>{section.data.length}</Text>
          </View>
        )}
      </View>
    );
  }, [sections, openSubgrupos, toggleSubgrupo]);

  return (
    <View style={styles.container}>
      <SearchBar value={search} onChangeText={setSearch} placeholder={t.inputs_search} />

      <View style={styles.chipWrap}>
        {[{ id: undefined, canonical_name: t.inputs_all }, ...grupos].map(item => (
          <Pressable
            key={item.id || 'all'}
            style={[styles.chip, selectedGrupo === item.id && styles.chipActive]}
            onPress={() => setSelectedGrupo(item.id === selectedGrupo ? undefined : item.id)}
          >
            <Text style={[styles.chipText, selectedGrupo === item.id && styles.chipTextActive]}>
              {item.canonical_name}
            </Text>
          </Pressable>
        ))}
      </View>

      {subgrupos.length > 0 && (
        <View style={styles.chipWrap}>
          {subgrupos.map(item => (
            <Pressable
              key={item.id}
              style={[styles.chipSmall, selectedSubgrupo === item.id && styles.chipActive]}
              onPress={() => setSelectedSubgrupo(item.id === selectedSubgrupo ? undefined : item.id)}
            >
              <Text style={[styles.chipTextSmall, selectedSubgrupo === item.id && styles.chipTextActive]}>
                {item.canonical_name}
              </Text>
            </Pressable>
          ))}
        </View>
      )}

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
      ) : (
        <View style={{ flex: 1 }}>
          <SectionList
            sections={visibleSections}
            keyExtractor={(item) => item.id}
            renderItem={renderInsumo}
            renderSectionHeader={renderSectionHeader as any}
            contentContainerStyle={styles.listContent}
            stickySectionHeadersEnabled={false}
            initialNumToRender={25}
            ListEmptyComponent={
              <Text style={styles.emptyText}>{t.inputs_not_found}</Text>
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
    marginBottom: spacing.xs,
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
  grupoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
    backgroundColor: colors.secondary + '12',
    borderBottomWidth: 2,
    borderBottomColor: colors.secondary + '33',
    marginTop: spacing.sm,
  },
  grupoHeaderText: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.secondary,
    flex: 1,
  },
  grupoCount: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  subgrupoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  subgrupoHeaderText: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.text.primary,
  },
  subgrupoCount: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  subgrupoMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  cpcHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    backgroundColor: colors.primary + '08',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderLight,
  },
  cpcCode: {
    fontSize: fontSize.xs,
    fontFamily: 'monospace',
    fontWeight: '600',
    color: colors.primary,
  },
  cpcTitle: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    flex: 1,
  },
  cpcCount: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  insumoCard: {
    marginHorizontal: spacing.lg,
    marginLeft: spacing.xl,
    marginBottom: spacing.xs,
  },
  insumoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  insumoIcon: {
    width: 36,
    height: 36,
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
  emptyText: {
    textAlign: 'center',
    marginTop: 40,
    fontSize: fontSize.md,
    color: colors.text.tertiary,
  },
});
