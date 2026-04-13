import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator, Dimensions } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Rect, Text as SvgText } from 'react-native-svg';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { getInsumoById, getInsumoPricesByDepartment } from '../../src/api/insumos';
import { formatCOP, formatCOPCompact } from '../../src/lib/format';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_WIDTH = SCREEN_WIDTH - 64;

export default function InsumoDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
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

  // Aggregate latest price per department
  const latestByDept = new Map<string, { dept: string; price: number }>();
  for (const p of deptPrices) {
    const deptName = (p as any).dim_department?.canonical_name || 'Desconocido';
    if (!latestByDept.has(deptName) && p.avg_price) {
      latestByDept.set(deptName, { dept: deptName, price: p.avg_price });
    }
  }
  const deptBars = Array.from(latestByDept.values())
    .sort((a, b) => b.price - a.price)
    .slice(0, 15);

  const maxPrice = deptBars.length > 0 ? Math.max(...deptBars.map(d => d.price)) : 1;

  return (
    <>
      <Stack.Screen options={{ title: insumo.canonical_name }} />
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

        {/* Price by Department (horizontal bar chart) */}
        <Card style={styles.chartCard}>
          <Text style={styles.sectionTitle}>Precio por departamento</Text>
          {deptBars.length === 0 ? (
            <Text style={styles.noDataText}>Sin datos de precios por departamento</Text>
          ) : (
            <View style={styles.barsContainer}>
              {deptBars.map((d, i) => (
                <View key={d.dept} style={styles.barRow}>
                  <Text style={styles.barLabel} numberOfLines={1}>{d.dept}</Text>
                  <View style={styles.barTrack}>
                    <View
                      style={[
                        styles.barFill,
                        { width: `${(d.price / maxPrice) * 100}%` as any },
                      ]}
                    />
                  </View>
                  <Text style={styles.barValue}>{formatCOPCompact(d.price)}</Text>
                </View>
              ))}
            </View>
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
    backgroundColor: colors.secondary + '15',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerInfo: {
    flex: 1,
    gap: 2,
  },
  headerGrupo: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  headerName: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text.primary,
  },
  headerSubgrupo: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
  },
  headerCpc: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
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
    color: colors.secondary,
  },
  statLabel: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  chartCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
  },
  sectionTitle: {
    fontSize: fontSize.lg,
    fontWeight: '700',
    color: colors.text.primary,
    marginBottom: spacing.md,
  },
  barsContainer: {
    gap: spacing.sm,
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  barLabel: {
    width: 80,
    fontSize: fontSize.xs,
    color: colors.text.secondary,
    textAlign: 'right',
  },
  barTrack: {
    flex: 1,
    height: 16,
    backgroundColor: colors.borderLight,
    borderRadius: 4,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    backgroundColor: colors.secondary,
    borderRadius: 4,
  },
  barValue: {
    width: 50,
    fontSize: fontSize.xs,
    color: colors.text.primary,
    fontFamily: 'monospace',
    fontWeight: '600',
  },
  noDataText: {
    fontSize: fontSize.sm,
    color: colors.text.tertiary,
    textAlign: 'center',
    paddingVertical: spacing.xl,
  },
});
