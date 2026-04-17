import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, TextInput, Pressable, ScrollView, StyleSheet, ActivityIndicator, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../theme';
import { getMarketSupply, getNationalSupplyAverages } from '../api/markets';
import { formatKg } from '../lib/format';
import { useTranslation } from '../lib/useTranslation';

const NATIONAL_AVG = '__national__';

interface Props {
  currentMarket: any;
  supply: any[];
  products: any[];
  markets: any[];
}

export function MarketSupplyComparator({ currentMarket, supply, products, markets }: Props) {
  const t = useTranslation();
  const [compId, setCompId] = useState<string | null>(null);
  const [compData, setCompData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);

  const supplyA = useMemo(() => {
    const map = new Map<string, number>();
    for (const s of supply) map.set(s.product_id, (map.get(s.product_id) || 0) + (s.quantity_kg || 0));
    return map;
  }, [supply]);

  const productInfo = useMemo(() => {
    const map = new Map<string, { name: string; category: string; subcategory: string }>();
    for (const p of products) {
      map.set(p.product_id, { name: p.dim_product?.canonical_name || 'Producto',
        category: p.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro',
        subcategory: p.dim_product?.dim_subcategory?.canonical_name || 'General' });
    }
    for (const s of supply) {
      if (!map.has(s.product_id)) map.set(s.product_id, { name: (s as any).dim_product?.canonical_name || 'Producto', category: 'Otro', subcategory: 'General' });
    }
    return map;
  }, [products, supply]);

  useEffect(() => {
    if (!compId) { setCompData([]); return; }
    setLoading(true);
    const pids = Array.from(supplyA.keys());
    const promise = compId === NATIONAL_AVG
      ? getNationalSupplyAverages(pids, 30)
      : getMarketSupply(compId, 30).then(data => {
          const map = new Map<string, number>();
          for (const s of (data || []) as any[]) map.set(s.product_id, (map.get(s.product_id) || 0) + (s.quantity_kg || 0));
          return Array.from(map.entries()).map(([product_id, quantity_kg]) => ({ product_id, quantity_kg }));
        });
    promise.then(setCompData).catch(console.error).finally(() => setLoading(false));
  }, [compId, supplyA]);

  const comparison = useMemo(() => {
    if (!compId || compData.length === 0) return null;
    const bMap = new Map<string, number>();
    for (const s of compData) bMap.set(s.product_id, s.quantity_kg);

    const rows: any[] = [];
    for (const [pid, kgA] of supplyA) {
      const kgB = bMap.get(pid);
      if (kgB == null) continue;
      const info = productInfo.get(pid);
      const pctDiff = kgA > 0 ? ((kgB - kgA) / kgA) * 100 : null;
      rows.push({ product_id: pid, name: info?.name || 'Producto', category: info?.category || 'Otro', subcategory: info?.subcategory || 'General', kgA, kgB, pctDiff });
    }

    const catMap = new Map<string, Map<string, any[]>>();
    for (const r of rows) {
      if (!catMap.has(r.category)) catMap.set(r.category, new Map());
      const sub = catMap.get(r.category)!;
      if (!sub.has(r.subcategory)) sub.set(r.subcategory, []);
      sub.get(r.subcategory)!.push(r);
    }
    const groups = [...catMap.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([cat, subMap]) => ({
      category: cat,
      subcategories: [...subMap.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, items]) => {
        const matched = items.filter((r: any) => r.pctDiff != null);
        return { name, items: items.sort((a: any, b: any) => a.name.localeCompare(b.name)),
          avgDiff: matched.length > 0 ? matched.reduce((s: number, r: any) => s + r.pctDiff, 0) / matched.length : null,
          matchCount: matched.length };
      }),
    }));
    const matched = rows.filter(r => r.pctDiff != null);
    const overallAvg = matched.length > 0 ? matched.reduce((s, r) => s + r.pctDiff, 0) / matched.length : null;
    return { groups, overallAvg, matchCount: matched.length, totalA: supplyA.size };
  }, [supplyA, compData, productInfo, compId]);

  const filteredMarkets = useMemo(() => {
    const q = search.toLowerCase();
    return markets.filter(m => m.id !== currentMarket.id)
      .filter(m => !q || m.canonical_name.toLowerCase().includes(q) || (m as any).dim_city?.canonical_name?.toLowerCase()?.includes(q));
  }, [markets, search, currentMarket.id]);

  const compName = compId === NATIONAL_AVG ? t.compare_national_avg : markets.find(m => m.id === compId)?.canonical_name || '';
  const diffColor = (pct: number | null) => { if (pct == null) return colors.text.tertiary; if (pct > 2) return colors.price.up; if (pct < -2) return colors.price.down; return colors.text.tertiary; };
  const fmtDiff = (pct: number | null) => pct == null ? '\u2014' : `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;

  if (supply.length === 0) return null;

  return (
    <View>
      <View style={s.header}>
        <Ionicons name="swap-horizontal" size={16} color={colors.accent.blue} />
        <Text style={s.title}>{t.compare_supply_title}</Text>
      </View>

      <Pressable onPress={() => setOpen(true)} style={s.selector}>
        <Ionicons name="search" size={14} color={colors.text.tertiary} />
        <Text style={[s.selectorText, !compId && { color: colors.text.tertiary }]} numberOfLines={1}>
          {compId ? compName : t.compare_select_market}
        </Text>
        {compId ? <Pressable onPress={() => setCompId(null)} hitSlop={8}><Ionicons name="close-circle" size={16} color={colors.text.tertiary} /></Pressable> : null}
      </Pressable>

      <Modal visible={open} animationType="slide" transparent>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>{t.compare_search_market}</Text>
              <Pressable onPress={() => { setOpen(false); setSearch(''); }}><Ionicons name="close" size={24} color={colors.text.primary} /></Pressable>
            </View>
            <View style={s.searchRow}>
              <Ionicons name="search" size={16} color={colors.text.tertiary} />
              <TextInput value={search} onChangeText={setSearch} placeholder={t.compare_search_market} placeholderTextColor={colors.text.tertiary} style={s.searchInput} autoFocus />
            </View>
            <ScrollView style={{ maxHeight: 350 }}>
              <Pressable onPress={() => { setCompId(NATIONAL_AVG); setOpen(false); setSearch(''); }} style={s.pickerItem}>
                <Text style={[s.pickerName, { color: colors.primary, fontWeight: '600' }]}>{t.compare_national_avg}</Text>
                <Text style={s.pickerSub}>{t.compare_all_markets}</Text>
              </Pressable>
              {filteredMarkets.map(m => (
                <Pressable key={m.id} onPress={() => { setCompId(m.id); setOpen(false); setSearch(''); }} style={s.pickerItem}>
                  <Text style={s.pickerName}>{m.canonical_name}</Text>
                  <Text style={s.pickerSub}>{(m as any).dim_city?.canonical_name}{(m as any).dim_city?.dim_department ? `, ${(m as any).dim_city.dim_department.canonical_name}` : ''}</Text>
                </Pressable>
              ))}
              {filteredMarkets.length === 0 && <Text style={s.empty}>{t.compare_no_results}</Text>}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {loading && <ActivityIndicator size="small" color={colors.text.tertiary} style={{ padding: spacing.lg }} />}

      {!loading && compId && comparison && comparison.matchCount > 0 && (
        <>
          <Text style={s.matchCount}>{comparison.matchCount} / {comparison.totalA} {t.compare_matching}</Text>
          <View style={s.colHeaders}>
            <Text style={[s.colH, { flex: 1 }]}>{t.compare_product}</Text>
            <Text style={[s.colH, { width: 68, textAlign: 'right' }]} numberOfLines={1}>{currentMarket.canonical_name}</Text>
            <Text style={[s.colH, { width: 68, textAlign: 'right' }]} numberOfLines={1}>{compName}</Text>
            <Text style={[s.colH, { width: 52, textAlign: 'right' }]}>{t.compare_diff}</Text>
          </View>
          {comparison.groups.map(group => (
            <View key={group.category}>
              <Text style={[s.catHeader, { color: colors.accent.blue }]}>{group.category}</Text>
              {group.subcategories.map(sub => (
                <View key={sub.name}>
                  {group.subcategories.length > 1 && <Text style={s.subHeader}>{sub.name}</Text>}
                  {sub.items.map((row: any) => (
                    <View key={row.product_id} style={s.row}>
                      <View style={{ flex: 1 }}><Text style={s.rowName}>{row.name}</Text></View>
                      <Text style={s.rowPrice}>{formatKg(row.kgA)}</Text>
                      <Text style={s.rowPrice}>{formatKg(row.kgB)}</Text>
                      <Text style={[s.rowDiff, { color: diffColor(row.pctDiff) }]}>{fmtDiff(row.pctDiff)}</Text>
                    </View>
                  ))}
                  {sub.avgDiff != null && sub.matchCount > 1 && (
                    <View style={s.subtotalRow}>
                      <Text style={s.subtotalLabel}>{sub.name}</Text>
                      <View style={{ width: 68 }} /><View style={{ width: 68 }} />
                      <Text style={[s.rowDiff, { fontWeight: '700', color: diffColor(sub.avgDiff) }]}>{fmtDiff(sub.avgDiff)}</Text>
                    </View>
                  )}
                </View>
              ))}
            </View>
          ))}
          {comparison.overallAvg != null && (
            <View style={[s.overallRow, { borderTopColor: colors.accent.blue }]}>
              <Text style={s.overallLabel}>{t.compare_overall_avg}</Text>
              <View style={{ width: 68 }} /><View style={{ width: 68 }} />
              <Text style={[s.rowDiff, { fontSize: fontSize.sm, fontWeight: '700', color: diffColor(comparison.overallAvg) }]}>{fmtDiff(comparison.overallAvg)}</Text>
            </View>
          )}
        </>
      )}

      {!loading && compId && (!comparison || comparison.matchCount === 0) && <Text style={s.empty}>{t.compare_no_match}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
  title: { fontSize: fontSize.md, fontWeight: '700', color: colors.text.primary },
  selector: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.borderLight, borderRadius: borderRadius.md, marginBottom: spacing.md },
  selectorText: { flex: 1, fontSize: fontSize.sm, color: colors.text.primary },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: borderRadius.lg, borderTopRightRadius: borderRadius.lg, maxHeight: '70%', paddingBottom: 30 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  modalTitle: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text.primary },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  searchInput: { flex: 1, fontSize: fontSize.md, color: colors.text.primary },
  pickerItem: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderLight },
  pickerName: { fontSize: fontSize.sm, color: colors.text.primary },
  pickerSub: { fontSize: fontSize.xs, color: colors.text.tertiary },
  matchCount: { fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.sm },
  colHeaders: { flexDirection: 'row', gap: 2, paddingHorizontal: spacing.xs, marginBottom: spacing.xs },
  colH: { fontSize: fontSize.xs, color: colors.text.tertiary, fontWeight: '600' },
  catHeader: { fontSize: fontSize.xs, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, paddingVertical: spacing.xs, marginTop: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  subHeader: { fontSize: fontSize.xs, fontWeight: '600', color: colors.text.secondary, paddingVertical: spacing.xs, marginTop: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 3, paddingHorizontal: spacing.xs, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderLight + '20' },
  rowName: { fontSize: fontSize.sm, color: colors.text.primary },
  rowPrice: { width: 68, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: colors.text.primary },
  rowDiff: { width: 52, textAlign: 'right', fontSize: fontSize.xs, fontWeight: '600', fontFamily: 'monospace' },
  subtotalRow: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 3, paddingHorizontal: spacing.xs, backgroundColor: colors.background },
  subtotalLabel: { flex: 1, fontSize: fontSize.xs, fontWeight: '600', color: colors.text.secondary, fontStyle: 'italic' },
  overallRow: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: spacing.sm, paddingHorizontal: spacing.xs, borderTopWidth: 2, marginTop: spacing.sm },
  overallLabel: { flex: 1, fontSize: fontSize.sm, fontWeight: '700', color: colors.text.primary },
  empty: { textAlign: 'center', padding: spacing.lg, fontSize: fontSize.sm, color: colors.text.tertiary },
});
