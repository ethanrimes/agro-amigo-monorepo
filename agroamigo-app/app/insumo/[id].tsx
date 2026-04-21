import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, FlatList } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { Card } from '../../src/components/Card';
import { ExpandableSection } from '../../src/components/ExpandableSection';
import { LineChart, LineChartPoint } from '../../src/components/LineChart';
import { getInsumoById, getInsumoPricesByDepartment, getInsumoPricesByMunicipality, getCpcLatestPrices, getCpcTitle, getSubgrupoLatestPrices } from '../../src/api/insumos';
import { formatCOP, formatCOPCompact, formatDateShort } from '../../src/lib/format';
import { useWatchlist } from '../../src/context/WatchlistContext';
import { useTranslation } from '../../src/lib/useTranslation';
import { CommentsSection } from '../../src/components/CommentsSection';
import { cachedCall } from '../../src/lib/cache';

type PriceSeries = 'department' | 'municipality';

export default function InsumoDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { isWatched, toggle } = useWatchlist();
  const t = useTranslation();

  const [insumo, setInsumo] = useState<any>(null);
  const [cpcTitle, setCpcTitle] = useState('');
  const [deptPrices, setDeptPrices] = useState<any[]>([]);
  const [muniPrices, setMuniPrices] = useState<any[]>([]);
  const [cpcPrices, setCpcPrices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Chart filters
  const [series, setSeries] = useState<PriceSeries>('department');
  const [chartPresentation, setChartPresentation] = useState<string | null>(null);
  const [chartDept, setChartDept] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<number | null>(null);

  const TIME_RANGES = [
    { label: t.time_1w, days: 7 }, { label: t.time_1m, days: 30 }, { label: t.time_3m, days: 90 },
    { label: t.time_6m, days: 180 }, { label: t.time_1y, days: 365 }, { label: t.time_all, days: 0 },
  ];

  // CPC detail filters
  const [cpcSortAsc, setCpcSortAsc] = useState(false);
  const [showCpcHelp, setShowCpcHelp] = useState(false);
  const [cpcDept, setCpcDept] = useState<string[]>([]);
  const [cpcCasa, setCpcCasa] = useState<string[]>([]);
  const [cpcArticulo, setCpcArticulo] = useState<string[]>([]);
  const [cpcPresentation, setCpcPresentation] = useState<string[]>([]);

  // Lazy-load gates for heavy data blocks.
  const [priceChartExpanded, setPriceChartExpanded] = useState(false);
  const [cpcDetailExpanded, setCpcDetailExpanded] = useState(false);

  useEffect(() => { loadInsumoEntity(); }, [id]);

  async function loadInsumoEntity() {
    try {
      const ins = await cachedCall(`insumo:${id}:entity`, () => getInsumoById(id!));
      setInsumo(ins);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  // Price history (dept + muni series) is fetched only when the price chart
  // section is first expanded. Cached so re-expanding is free.
  useEffect(() => {
    if (!id || !priceChartExpanded) return;
    Promise.all([
      cachedCall(`insumo:${id}:prices:dept:2000`, () => getInsumoPricesByDepartment(id, 2000)).catch(() => []),
      cachedCall(`insumo:${id}:prices:muni:2000`, () => getInsumoPricesByMunicipality(id, undefined, 2000)).catch(() => []),
    ]).then(([dept, muni]) => {
      setDeptPrices(((dept as any[]) || []));
      setMuniPrices(((muni as any[]) || []));
      if ((!dept || (dept as any[]).length === 0) && muni && (muni as any[]).length > 0) setSeries('municipality');
    });
  }, [id, priceChartExpanded]);

  // CPC / subgrupo comparison table. Potentially large — defer until the
  // user opens the CPC detail section.
  useEffect(() => {
    if (!id || !cpcDetailExpanded || !insumo) return;
    if (insumo.cpc_id) {
      Promise.all([
        cachedCall(`cpc:${insumo.cpc_id}:latestPrices`, () => getCpcLatestPrices(insumo.cpc_id)).catch(() => []),
        cachedCall(`cpc:${insumo.cpc_id}:title`, () => getCpcTitle(insumo.cpc_id)).catch(() => ''),
      ]).then(([cpcData, title]) => {
        setCpcPrices(((cpcData as any[]) || []));
        if (title) setCpcTitle(title as string);
      });
    } else if (insumo.subgrupo_id) {
      cachedCall(`subgrupo:${insumo.subgrupo_id}:latestPrices`, () => getSubgrupoLatestPrices(insumo.subgrupo_id))
        .then(d => setCpcPrices(((d as any[]) || [])))
        .catch(() => {});
    }
  }, [id, cpcDetailExpanded, insumo]);

  const hasDept = deptPrices.length > 0;
  const hasMuni = muniPrices.length > 0;
  const activePrices = series === 'department' ? deptPrices : muniPrices;

  // Header summary: latest price + most-common presentation, mirroring the
  // product detail pattern. Prefers dept-level data (richer) when available.
  const headerInfo = useMemo(() => {
    const source = hasDept ? deptPrices : muniPrices;
    if (source.length === 0) return null;
    const presCounts = new Map<string, number>();
    for (const p of source) {
      const pres = (p.presentation || '').trim();
      if (pres) presCounts.set(pres, (presCounts.get(pres) || 0) + 1);
    }
    let mostCommonPres = '';
    let maxCount = 0;
    for (const [pres, count] of presCounts) {
      if (count > maxCount) { maxCount = count; mostCommonPres = pres; }
    }
    const filtered = mostCommonPres
      ? source.filter(p => (p.presentation || '').trim() === mostCommonPres)
      : source;
    const latest = filtered.reduce((a: any, b: any) =>
      (a?.price_date || '') > (b?.price_date || '') ? a : b,
    );
    if (!latest) return null;
    const deptName = (latest as any).dim_department?.canonical_name || '';
    return {
      avg_price: latest.avg_price,
      price_date: latest.price_date,
      presentation: mostCommonPres,
      deptName,
      seriesLabel: hasDept ? 'Promedio departamental' : 'Promedio municipal',
    };
  }, [deptPrices, muniPrices, hasDept]);

  const deptLocationCount = useMemo(() => new Set(deptPrices.map(p => p.department_id)).size, [deptPrices]);
  const muniLocationCount = useMemo(() => new Set(muniPrices.map(p => p.department_id)).size, [muniPrices]);

  // ═══ CHART CASCADE: series → time range → presentation → department ═══

  // Available time-range tiles: hide tiles whose window contains no data.
  const availableTimeRanges = useMemo(() => {
    if (activePrices.length === 0) return [];
    const newest = activePrices.reduce(
      (max: string, p: any) => (p.price_date > max ? p.price_date : max),
      activePrices[0].price_date,
    );
    if (!newest) return [];
    const daysOld = Math.ceil((new Date().getTime() - new Date(newest + 'T00:00:00').getTime()) / 86400000);
    return TIME_RANGES.map((tr, i) => ({ ...tr, index: i, hasData: tr.days === 0 || daysOld <= tr.days }))
      .filter(tr => tr.hasData);
  }, [activePrices]);

  useEffect(() => {
    if (availableTimeRanges.length > 0 && (timeRange === null || !availableTimeRanges.some(r => r.index === timeRange))) {
      setTimeRange(availableTimeRanges[0].index);
    }
  }, [availableTimeRanges]);

  const timeFilteredPrices = useMemo(() => {
    const tr = TIME_RANGES[timeRange ?? 0];
    if (!tr || tr.days === 0) return activePrices;
    const since = new Date(); since.setDate(since.getDate() - tr.days);
    const sinceStr = since.toISOString().split('T')[0];
    return activePrices.filter(p => p.price_date >= sinceStr);
  }, [activePrices, timeRange]);

  const chartPresentations = useMemo(() => Array.from(new Set(timeFilteredPrices.map(p => p.presentation).filter(Boolean))).sort(), [timeFilteredPrices]);

  useEffect(() => {
    if (chartPresentation && !chartPresentations.includes(chartPresentation))
      setChartPresentation(chartPresentations[0] || null);
    else if (!chartPresentation && chartPresentations.length > 0)
      setChartPresentation(chartPresentations[0]);
  }, [chartPresentations]);

  const presFilteredPrices = useMemo(() => {
    if (!chartPresentation) return timeFilteredPrices;
    return timeFilteredPrices.filter(p => p.presentation === chartPresentation);
  }, [timeFilteredPrices, chartPresentation]);

  // Detect whether the muni series actually carries city-level data for this
  // insumo. Some categories (e.g. "Arrendamiento de tierras") live in the
  // muni table but have city_id=null on every row — in that case fall back
  // to department grouping so the geo chips still populate.
  const muniHasCityData = useMemo(
    () => series === 'municipality' && muniPrices.some(p => (p as any).city_id),
    [series, muniPrices],
  );

  const chartDepts = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of presFilteredPrices) {
      if (series === 'municipality' && muniHasCityData) {
        const key = (p as any).city_id;
        const name = (p as any).dim_city?.canonical_name;
        if (key && name) map.set(key, name);
      } else {
        const name = (p as any).dim_department?.canonical_name;
        if (name) map.set(p.department_id, name);
      }
    }
    return Array.from(map.entries()).sort(([, a], [, b]) => a.localeCompare(b));
  }, [presFilteredPrices, series, muniHasCityData]);

  useEffect(() => {
    if (chartDept && !chartDepts.some(([id]) => id === chartDept)) setChartDept(null);
  }, [chartDepts]);

  const chartData: LineChartPoint[] = useMemo(() => {
    let filtered = presFilteredPrices;
    if (chartDept) {
      filtered = filtered.filter(p =>
        series === 'municipality' && muniHasCityData
          ? (p as any).city_id === chartDept
          : p.department_id === chartDept,
      );
    }
    const byDate = new Map<string, { sum: number; count: number }>();
    for (const p of filtered) {
      if (!p.avg_price || !p.price_date) continue;
      const e = byDate.get(p.price_date);
      if (e) { e.sum += Number(p.avg_price); e.count++; }
      else byDate.set(p.price_date, { sum: Number(p.avg_price), count: 1 });
    }
    return Array.from(byDate.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([date, { sum, count }]) => ({ date, value: sum / count }));
  }, [presFilteredPrices, chartDept, series, muniHasCityData]);

  // ═══ CPC FILTERS: independent multi-select ═══

  const cpcDepts = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.dept_name).filter(Boolean))).sort(), [cpcPrices]);
  const cpcCasas = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.casa_comercial_name).filter(Boolean))).sort(), [cpcPrices]);
  const cpcArticulos = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.articulo).filter(Boolean))).sort(), [cpcPrices]);
  const cpcPresentations = useMemo(() => Array.from(new Set(cpcPrices.map(p => p.presentation).filter(Boolean))).sort(), [cpcPrices]);

  const toggleCpc = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val]);
  };

  const cpcFilteredRows = useMemo(() => {
    let rows = cpcPrices;
    if (cpcDept.length > 0) rows = rows.filter(r => cpcDept.includes(r.dept_name));
    if (cpcCasa.length > 0) rows = rows.filter(r => cpcCasa.includes(r.casa_comercial_name));
    if (cpcArticulo.length > 0) rows = rows.filter(r => cpcArticulo.includes(r.articulo));
    if (cpcPresentation.length > 0) rows = rows.filter(r => cpcPresentation.includes(r.presentation));
    return [...rows].sort((a, b) => {
      const diff = (Number(a.avg_price) || 0) - (Number(b.avg_price) || 0);
      return cpcSortAsc ? diff : -diff;
    });
  }, [cpcPrices, cpcDept, cpcCasa, cpcArticulo, cpcPresentation, cpcSortAsc]);

  if (loading) return <View style={styles.loadingContainer}><ActivityIndicator size="large" color={colors.primary} /></View>;
  if (!insumo) return <View style={styles.loadingContainer}><Text>{t.input_not_found}</Text></View>;

  const Chip = ({ label, active, onPress, color = colors.secondary }: { label: string; active: boolean; onPress: () => void; color?: string }) => (
    <Pressable onPress={onPress} style={[styles.chip, active && { backgroundColor: color, borderColor: color }]}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );

  const ChipRow = ({ children }: { children: React.ReactNode }) => (
    <View style={styles.chipRow}>{children}</View>
  );

  return (
    <>
      <Stack.Screen options={{
        title: insumo.canonical_name,
        headerRight: () => (
          <Pressable onPress={() => toggle(id!, 'insumo', insumo.canonical_name)} hitSlop={12} style={{ marginRight: spacing.md }}>
            <Ionicons name={isWatched(id!) ? 'star' : 'star-outline'} size={22} color={isWatched(id!) ? '#FFD700' : colors.text.inverse} />
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
            {insumo.subgrupo && <Text style={styles.headerSubgrupo}>{insumo.subgrupo}</Text>}
            {insumo.cpc_id && (
              <Pressable onPress={() => setShowCpcHelp(v => !v)} hitSlop={6}>
                <Text style={styles.headerCpc}>
                  CPC {insumo.cpc_id}{cpcTitle ? ` — ${cpcTitle}` : ''}
                  <Text style={{ color: colors.text.tertiary }}> {showCpcHelp ? '▲' : '▼'}</Text>
                </Text>
              </Pressable>
            )}
            {headerInfo && (
              <>
                <Text style={styles.headerPrice}>{formatCOP(headerInfo.avg_price)}</Text>
                <Text style={styles.headerPriceMeta}>
                  {[
                    formatDateShort(headerInfo.price_date),
                    headerInfo.seriesLabel,
                    headerInfo.presentation,
                  ].filter(Boolean).join(' \u00b7 ')}
                </Text>
              </>
            )}
          </View>
        </View>

        {/* CPC explanation — collapsed by default */}
        {insumo.cpc_id && showCpcHelp && (
          <Text style={styles.cpcExplanation}>
            El código CPC (Clasificación Central de Productos de la ONU) agrupa productos similares bajo un mismo identificador.
            Lo usamos para comparar este insumo con otros artículos equivalentes — misma categoría, distintas marcas — y mostrar
            precios de referencia por departamento.
          </Text>
        )}

        {/* Stats */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{deptLocationCount}</Text>
            <Text style={styles.statLabel}>{t.input_departments}</Text>
            <Text style={styles.statSublabel}>Serie departamental</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>{muniLocationCount}</Text>
            <Text style={styles.statLabel}>{t.input_municipalities}</Text>
            <Text style={styles.statSublabel}>Serie municipal</Text>
          </View>
        </View>

        {/* Series explanation */}
        <Text style={styles.seriesExplanation}>
          DANE publica dos series independientes: precios promedio por departamento (incluye marca comercial y artículo) y precios promedio por municipio (sin detalle de marca). Seleccione la serie para visualizar.
        </Text>

        {/* Price history chart */}
        <Card style={styles.chartCard}>
          <ExpandableSection
            title={t.input_price_history}
            icon="analytics-outline"
            initiallyExpanded={false}
            onExpandChange={setPriceChartExpanded}
          >
          <View style={styles.chipRowInline}>
            <Chip label={`Departamento (${deptLocationCount})`} active={series === 'department'} onPress={() => { setSeries('department'); setChartDept(null); setChartPresentation(null); }} />
            <Chip label={`Municipio (${muniLocationCount})`} active={series === 'municipality'} onPress={() => { setSeries('municipality'); setChartDept(null); setChartPresentation(null); }} />
          </View>

          {availableTimeRanges.length > 1 && (
            <View style={styles.chipRowInline}>
              {availableTimeRanges.map(tr => (
                <Chip key={tr.label} label={tr.label} active={tr.index === timeRange} onPress={() => setTimeRange(tr.index)} color={colors.primaryDark} />
              ))}
            </View>
          )}

          {chartPresentations.length >= 1 && (
            <ChipRow>
              {chartPresentations.map(p => (
                <Chip key={p} label={p} active={chartPresentation === p || chartPresentations.length === 1} onPress={() => setChartPresentation(p)} color={colors.primaryDark} />
              ))}
            </ChipRow>
          )}

          {chartDepts.length >= 1 && (
            <ChipRow>
              {chartDepts.length > 1 && <Chip label="Nacional" active={!chartDept} onPress={() => setChartDept(null)} color={colors.accent.blue} />}
              {chartDepts.map(([dId, name]) => (
                <Chip key={dId} label={name} active={chartDept === dId || chartDepts.length === 1} onPress={() => setChartDept(chartDepts.length === 1 ? dId : (chartDept === dId ? null : dId))} color={colors.accent.blue} />
              ))}
            </ChipRow>
          )}

          {chartData.length > 1 ? (
            <View style={{ alignItems: 'center', marginTop: spacing.sm }}>
              <LineChart data={chartData} width={340} height={180} color={colors.secondary} formatValue={formatCOPCompact} minPointSpacing={6} />
            </View>
          ) : priceChartExpanded ? (
            <Text style={styles.noDataText}>{t.input_no_data}</Text>
          ) : null}
          </ExpandableSection>
        </Card>

        {/* CPC-wide price detail (falls back to full subgrupo when no CPC).
            The data is fetched only when the section is first expanded. */}
        {(insumo.cpc_id || insumo.subgrupo_id) && (
          <Card style={styles.chartCard}>
            <ExpandableSection
              title={insumo.cpc_id ? `Precios CPC ${insumo.cpc_id}` : `Precios ${insumo.subgrupo || 'subgrupo'}`}
              subtitle={insumo.cpc_id ? (cpcTitle || undefined) : undefined}
              icon="list-outline"
              badge={cpcPrices.length > 0 ? cpcFilteredRows.length : undefined}
              initiallyExpanded={false}
              onExpandChange={setCpcDetailExpanded}
            >
              {/* Sort */}
              <View style={styles.chipRowInline}>
                <Text style={styles.filterLabel}>Ordenar:</Text>
                <Chip label="Mayor ↓" active={!cpcSortAsc} onPress={() => setCpcSortAsc(false)} color={colors.dark} />
                <Chip label="Menor ↑" active={cpcSortAsc} onPress={() => setCpcSortAsc(true)} color={colors.dark} />
              </View>

              <Text style={{ fontSize: 11, color: colors.text.tertiary, fontStyle: 'italic', marginBottom: spacing.sm }}>
                Puedes seleccionar varios filtros a la vez en cada nivel.
              </Text>

              {cpcDepts.length >= 1 && (
                <ChipRow>
                  <Chip label="Todos dptos" active={cpcDept.length === 0} onPress={() => setCpcDept([])} color={colors.accent.blue} />
                  {cpcDepts.map(d => (
                    <Chip key={d} label={d} active={cpcDept.includes(d)} onPress={() => toggleCpc(cpcDept, d, setCpcDept)} color={colors.accent.blue} />
                  ))}
                </ChipRow>
              )}

              {cpcCasas.length >= 1 && (
                <ChipRow>
                  <Chip label="Todas marcas" active={cpcCasa.length === 0} onPress={() => setCpcCasa([])} color={colors.secondary} />
                  {cpcCasas.map(c => (
                    <Chip key={c} label={c} active={cpcCasa.includes(c)} onPress={() => toggleCpc(cpcCasa, c, setCpcCasa)} color={colors.secondary} />
                  ))}
                </ChipRow>
              )}

              {cpcArticulos.length >= 1 && (
                <ChipRow>
                  <Chip label="Todos art." active={cpcArticulo.length === 0} onPress={() => setCpcArticulo([])} color={colors.primary} />
                  {cpcArticulos.map(a => (
                    <Chip key={a} label={a} active={cpcArticulo.includes(a)} onPress={() => toggleCpc(cpcArticulo, a, setCpcArticulo)} color={colors.primary} />
                  ))}
                </ChipRow>
              )}

              {cpcPresentations.length >= 1 && (
                <ChipRow>
                  <Chip label="Todas present." active={cpcPresentation.length === 0} onPress={() => setCpcPresentation([])} color={colors.primaryDark} />
                  {cpcPresentations.map(p => (
                    <Chip key={p} label={p} active={cpcPresentation.includes(p)} onPress={() => toggleCpc(cpcPresentation, p, setCpcPresentation)} color={colors.primaryDark} />
                  ))}
                </ChipRow>
              )}

              {cpcFilteredRows.length === 0 ? (
                <Text style={styles.noDataText}>{t.input_no_data}</Text>
              ) : (
                cpcFilteredRows.map((row: any, i: number) => (
                  <View key={i} style={styles.detailRow}>
                    <View style={styles.detailInfo}>
                      <Text style={styles.detailDept}>{row.articulo || '—'}</Text>
                      <Text style={styles.detailContext}>{row.dept_name}</Text>
                      <Text style={styles.detailMeta}>{[row.casa_comercial_name, row.presentation].filter(Boolean).join(' · ')}</Text>
                    </View>
                    <View style={styles.detailPriceCol}>
                      <Text style={styles.detailPrice}>{formatCOP(row.avg_price)}</Text>
                      <Text style={styles.detailDate}>{formatDateShort(row.price_date)}</Text>
                    </View>
                  </View>
                ))
              )}
            </ExpandableSection>
          </Card>
        )}

        {/* Comments */}
        <Card style={{ marginHorizontal: spacing.lg, marginTop: spacing.lg }}>
          <CommentsSection entityType="insumo" entityId={id!} />
        </Card>

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
  headerPrice: { fontSize: fontSize.lg, fontWeight: '700', color: colors.secondary, marginTop: 2 },
  headerPriceMeta: { fontSize: fontSize.xs, color: colors.text.tertiary },
  statsRow: { flexDirection: 'row', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.md },
  statBox: { flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center', gap: 2 },
  statValue: { fontSize: fontSize.xl, fontWeight: '700', color: colors.secondary },
  statLabel: { fontSize: fontSize.xs, color: colors.text.secondary },
  statSublabel: { fontSize: 9, color: colors.text.tertiary },
  seriesExplanation: {
    paddingHorizontal: spacing.lg, paddingBottom: spacing.sm,
    fontSize: fontSize.xs, color: colors.text.tertiary, lineHeight: 16,
  },
  cpcExplanation: {
    marginHorizontal: spacing.lg, marginTop: spacing.xs, marginBottom: spacing.sm,
    padding: spacing.sm, backgroundColor: colors.surface, borderRadius: borderRadius.md,
    fontSize: fontSize.xs, color: colors.text.secondary, lineHeight: 16,
  },
  chartCard: { marginHorizontal: spacing.lg, marginTop: spacing.md },
  sectionTitle: { fontSize: fontSize.md, fontWeight: '700', color: colors.text.primary, marginBottom: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderRadius: borderRadius.full, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.borderLight,
  },
  chipText: { fontSize: fontSize.xs, color: colors.text.secondary, fontWeight: '500' },
  chipTextActive: { color: colors.text.inverse },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, paddingVertical: spacing.xs },
  chipRowInline: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  filterLabel: { fontSize: fontSize.xs, color: colors.text.tertiary, alignSelf: 'center', marginRight: spacing.xs },
  noDataText: { fontSize: fontSize.sm, color: colors.text.tertiary, textAlign: 'center', paddingVertical: spacing.xl },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start',
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight,
  },
  detailInfo: { flex: 1, gap: 1, marginRight: spacing.sm },
  detailDept: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.primary },
  detailContext: { fontSize: fontSize.xs, color: colors.text.secondary },
  detailMeta: { fontSize: fontSize.xs, color: colors.text.tertiary },
  detailPriceCol: { alignItems: 'flex-end', gap: 2 },
  detailPrice: { fontSize: fontSize.sm, fontWeight: '600', color: colors.secondary, fontFamily: 'monospace' },
  detailDate: { fontSize: fontSize.xs, color: colors.text.tertiary },
});
