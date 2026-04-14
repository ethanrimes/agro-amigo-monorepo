import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { getInsumoById, getInsumoPricesByDepartment } from '../../src/api/insumos';
import { formatCOP, formatCOPCompact, formatDateShort, formatPriceContext } from '../../src/lib/format';
import { useWatchlist } from '../../src/context/WatchlistContext';

export default function InsumoDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const [insumo, setInsumo] = useState<any>(null);
  const [deptPrices, setDeptPrices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInsumo();
  }, [id]);

  async function loadInsumo() {
    try {
      const [ins, prices] = await Promise.all([
        getInsumoById(id!),
        getInsumoPricesByDepartment(id!, 300),
      ]);
      setInsumo(ins);
      setDeptPrices(prices || []);
    } catch (err) {
      console.error('Error loading insumo:', err);
    } finally {
      setLoading(false);
    }
  }

  // Aggregate latest price per department for bar chart
  const latestByDept = useMemo(() => {
    const map = new Map<string, { dept: string; price: number }>();
    for (const p of deptPrices) {
      const deptName = (p as any).dim_department?.canonical_name || 'Desconocido';
      if (!map.has(deptName) && p.avg_price) {
        map.set(deptName, { dept: deptName, price: p.avg_price });
      }
    }
    return map;
  }, [deptPrices]);

  const deptBars = useMemo(() =>
    Array.from(latestByDept.values())
      .sort((a, b) => b.price - a.price)
      .slice(0, 15),
    [latestByDept]
  );

  const maxPrice = deptBars.length > 0 ? Math.max(...deptBars.map(d => d.price)) : 1;

  // Detail rows: latest per department with context
  const detailRows = useMemo(() => {
    const map = new Map<string, any>();
    for (const p of deptPrices) {
      const deptName = (p as any).dim_department?.canonical_name || 'Desconocido';
      if (!map.has(deptName)) map.set(deptName, p);
    }
    return [...map.values()].sort((a, b) =>
      ((a as any).dim_department?.canonical_name || '').localeCompare((b as any).dim_department?.canonical_name || '')
    );
  }, [deptPrices]);

  // Shared presentation across all detail rows
  const sharedPresentation = useMemo(() => {
    if (detailRows.length === 0) return null;
    const first = detailRows[0].presentation;
    return detailRows.every((r: any) => r.presentation === first) ? first : null;
  }, [detailRows]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!insumo) {
    return (
      <View style={styles.loadingContainer}>
        <Text>Insumo no encontrado</Text>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{
        title: insumo.canonical_name,
        headerRight: () => (
          <Pressable
            onPress={() => toggle(id!, 'insumo', insumo.canonical_name)}
            hitSlop={12}
            style={{ marginRight: spacing.md }}
          >
            <Ionicons
              name={isWatched(id!) ? 'star' : 'star-outline'}
              size={22}
              color={isWatched(id!) ? '#FFD700' : colors.text.inverse}
            />
          </Pressable>
        ),
      }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerIcon}>
            <Ionicons name="flask" size={36} color={colors.secondary} />
          </View>
          <View style={styles.headerInfo}>
            <Text style={styles.headerGrupo}>{insumo.grupo || ''}</Text>
            <Text style={styles.headerName}>{insumo.canonical_name}</Text>
            {insumo.subgrupo && (
              <Text style={styles.headerSubgrupo}>{insumo.subgrupo}</Text>
            )}
            {insumo.cpc_code && (
              <Text style={styles.headerCpc}>CPC: {insumo.cpc_code}</Text>
            )}
          </View>
        </View>

        {/* Stats */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{latestByDept.size}</Text>
            <Text style={styles.statLabel}>Departamentos</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{deptPrices.length}</Text>
            <Text style={styles.statLabel}>Observaciones</Text>
          </View>
        </View>

        {/* Bar chart */}
        <Card style={styles.chartCard}>
          <ExpandableSection
            title="Precio por departamento"
            icon="bar-chart-outline"
            badge={deptBars.length}
            initiallyExpanded={true}
          >
            {deptBars.length === 0 ? (
              <Text style={styles.noDataText}>Sin datos de precios por departamento</Text>
            ) : (
              <View style={styles.barsContainer}>
                {deptBars.map((d) => (
                  <View key={d.dept} style={styles.barRow}>
                    <Text style={styles.barLabel} numberOfLines={1}>{d.dept}</Text>
                    <View style={styles.barTrack}>
                      <View
                        style={[styles.barFill, { width: `${(d.price / maxPrice) * 100}%` as any }]}
                      />
                    </View>
                    <Text style={styles.barValue}>{formatCOPCompact(d.price)}</Text>
                  </View>
                ))}
              </View>
            )}
          </ExpandableSection>
        </Card>

        {/* Price detail list */}
        {detailRows.length > 0 && (
          <Card style={styles.chartCard}>
            <ExpandableSection
              title="Detalle de precios"
              icon="list-outline"
              badge={detailRows.length}
              subtitle={sharedPresentation ? `Presentación: ${sharedPresentation}` : undefined}
              initiallyExpanded={false}
            >
              {detailRows.map((p: any, i: number) => {
                const deptName = p.dim_department?.canonical_name || 'Desconocido';
                const ctx = !sharedPresentation && p.presentation ? p.presentation : '';
                return (
                  <View key={deptName} style={styles.detailRow}>
                    <View style={styles.detailInfo}>
                      <Text style={styles.detailDept}>{deptName}</Text>
                      {ctx ? <Text style={styles.detailContext}>{ctx}</Text> : null}
                    </View>
                    <View style={styles.detailPriceCol}>
                      <Text style={styles.detailPrice}>{formatCOP(p.avg_price)}</Text>
                      <Text style={styles.detailDate}>{formatDateShort(p.price_date)}</Text>
                    </View>
                  </View>
                );
              })}
            </ExpandableSection>
          </Card>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { paddingBottom: 20 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  header: {
    flexDirection: 'row', padding: spacing.lg, gap: spacing.lg,
    backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.borderLight, alignItems: 'center',
  },
  headerIcon: {
    width: 64, height: 64, borderRadius: borderRadius.lg,
    backgroundColor: colors.secondary + '15', justifyContent: 'center', alignItems: 'center',
  },
  headerInfo: { flex: 1, gap: 2 },
  headerGrupo: { fontSize: fontSize.xs, color: colors.text.tertiary, textTransform: 'uppercase', letterSpacing: 0.5 },
  headerName: { fontSize: fontSize.xl, fontWeight: '700', color: colors.text.primary },
  headerSubgrupo: { fontSize: fontSize.sm, color: colors.text.secondary },
  headerCpc: { fontSize: fontSize.xs, color: colors.text.tertiary },
  statsRow: { flexDirection: 'row', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.md },
  statBox: {
    flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md,
    padding: spacing.md, alignItems: 'center', gap: 4,
  },
  statValue: { fontSize: fontSize.xl, fontWeight: '700', color: colors.secondary },
  statLabel: { fontSize: fontSize.xs, color: colors.text.secondary },
  chartCard: { marginHorizontal: spacing.lg, marginTop: spacing.md },
  barsContainer: { gap: spacing.sm },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  barLabel: { width: 80, fontSize: fontSize.xs, color: colors.text.secondary, textAlign: 'right' },
  barTrack: { flex: 1, height: 16, backgroundColor: colors.borderLight, borderRadius: 4, overflow: 'hidden' },
  barFill: { height: '100%', backgroundColor: colors.secondary, borderRadius: 4 },
  barValue: { width: 50, fontSize: fontSize.xs, color: colors.text.primary, fontFamily: 'monospace', fontWeight: '600' },
  noDataText: { fontSize: fontSize.sm, color: colors.text.tertiary, textAlign: 'center', paddingVertical: spacing.xl },
  // Detail rows
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight,
  },
  detailInfo: { flex: 1, gap: 2, marginRight: spacing.sm },
  detailDept: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary },
  detailContext: { fontSize: fontSize.xs, color: colors.text.tertiary },
  detailPriceCol: { alignItems: 'flex-end', gap: 2 },
  detailPrice: { fontSize: fontSize.sm, fontWeight: '600', color: colors.secondary, fontFamily: 'monospace' },
  detailDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
});
