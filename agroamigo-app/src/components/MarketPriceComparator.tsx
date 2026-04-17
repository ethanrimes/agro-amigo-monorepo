import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, TextInput, Pressable, ScrollView, StyleSheet, ActivityIndicator, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../theme';
import { getMarketProducts, getNationalPriceAverages } from '../api/markets';
import { formatCOP, formatDateShort, formatPriceContext } from '../lib/format';
import { useTranslation } from '../lib/useTranslation';

const NATIONAL_AVG = '__national__';

interface Props {
  currentMarket: any;
  products: any[];
  markets: any[];
}

export function MarketPriceComparator({ currentMarket, products, markets }: Props) {
  const t = useTranslation();
  const [compId, setCompId] = useState<string | null>(null);
  const [compData, setCompData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [datePopup, setDatePopup] = useState<string | null>(null);

  useEffect(() => {
    if (!compId) { setCompData([]); return; }
    setLoading(true);
    const promise = compId === NATIONAL_AVG
      ? getNationalPriceAverages(products.map(p => p.product_id))
      : getMarketProducts(compId, 1000).then(data => {
          const map = new Map<string, any>();
          for (const p of (data || []) as any[]) {
            if (!map.has(p.product_id) || p.price_date > map.get(p.product_id).price_date)
              map.set(p.product_id, p);
          }
          return Array.from(map.values());
        });
    promise.then(setCompData).catch(console.error).finally(() => setLoading(false));
  }, [compId, products]);

  const comparison = useMemo(() => {
    if (!compId || compData.length === 0) return null;
    const bMap = new Map<string, any>();
    for (const p of compData) bMap.set(`${p.product_id}|${p.presentation_id}|${p.units_id}`, p);

    const rows: any[] = [];
    for (const a of products) {
      const key = `${a.product_id}|${a.presentation_id}|${a.units_id}`;
      const b = bMap.get(key);
      const priceA = a.avg_price ?? a.min_price;
      const priceB = b ? (b.avg_price ?? b.min_price) : null;
      const pctDiff = priceA > 0 && priceB != null ? ((priceB - priceA) / priceA) * 100 : null;
      rows.push({
        product_id: a.product_id, name: a.dim_product?.canonical_name || 'Producto',
        category: a.dim_product?.dim_subcategory?.dim_category?.canonical_name || 'Otro',
        subcategory: a.dim_product?.dim_subcategory?.canonical_name || 'General',
        context: formatPriceContext(a.dim_presentation?.canonical_name, a.dim_units?.canonical_name),
        priceA, priceB, pctDiff, dateA: a.price_date, dateB: b?.price_date || null,
      });
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
    return { groups, overallAvg, matchCount: matched.length, totalA: products.length };
  }, [products, compData, compId]);

  const filteredMarkets = useMemo(() => {
    const q = search.toLowerCase();
    return markets.filter(m => m.id !== currentMarket.id)
      .filter(m => !q || m.canonical_name.toLowerCase().includes(q) || (m as any).dim_city?.canonical_name?.toLowerCase()?.includes(q));
  }, [markets, search, currentMarket.id]);

  const compName = compId === NATIONAL_AVG ? t.compare_national_avg : markets.find(m => m.id === compId)?.canonical_name || '';

  const diffColor = (pct: number | null) => {
    if (pct == null) return colors.text.tertiary;
    if (pct > 2) return colors.price.up;
    if (pct < -2) return colors.price.down;
    return colors.text.tertiary;
  };
  const fmtDiff = (pct: number | null) => pct == null ? '\u2014' : `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;

  if (products.length === 0) return null;

  return (
    <View>
      <View style={s.header}>
        <Ionicons name="swap-horizontal" size={16} color={colors.primary} />
        <Text style={s.title}>{t.compare_prices_title}</Text>
      </View>

      {/* Market selector */}
      <Pressable onPress={() => setOpen(true)} style={s.selector}>
        <Ionicons name="search" size={14} color={colors.text.tertiary} />
        <Text style={[s.selectorText, !compId && { color: colors.text.tertiary }]} numberOfLines={1}>
          {compId ? compName : t.compare_select_market}
        </Text>
        {compId ? (
          <Pressable onPress={() => setCompId(null)} hitSlop={8}><Ionicons name="close-circle" size={16} color={colors.text.tertiary} /></Pressable>
        ) : null}
      </Pressable>

      {/* Picker modal */}
      <Modal visible={open} animationType="slide" transparent>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>{t.compare_search_market}</Text>
              <Pressable onPress={() => { setOpen(false); setSearch(''); }}><Ionicons name="close" size={24} color={colors.text.primary} /></Pressable>
            </View>
            <View style={s.searchRow}>
              <Ionicons name="search" size={16} color={colors.text.tertiary} />
              <TextInput value={search} onChangeText={setSearch} placeholder={t.compare_search_market}
                placeholderTextColor={colors.text.tertiary} style={s.searchInput} autoFocus />
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
          {/* Column headers */}
          <View style={s.colHeaders}>
            <Text style={[s.colH, { flex: 1 }]}>{t.compare_product}</Text>
            <Text style={[s.colH, { width: 68, textAlign: 'right' }]} numberOfLines={1}>{currentMarket.canonical_name}</Text>
            <Text style={[s.colH, { width: 68, textAlign: 'right' }]} numberOfLines={1}>{compName}</Text>
            <Text style={[s.colH, { width: 52, textAlign: 'right' }]}>{t.compare_diff}</Text>
          </View>

          {comparison.groups.map(group => (
            <View key={group.category}>
              <Text style={s.catHeader}>{group.category}</Text>
              {group.subcategories.map(sub => (
                <View key={sub.name}>
                  {group.subcategories.length > 1 && <Text style={s.subHeader}>{sub.name}</Text>}
                  {sub.items.map((row: any) => (
                    <Pressable key={row.product_id} style={s.row} onPress={() => row.dateA && setDatePopup(row.dateA)}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.rowName}>{row.name}</Text>
                        {row.context ? <Text style={s.rowCtx}>{row.context}</Text> : null}
                      </View>
                      <Text style={s.rowPrice}>{formatCOP(row.priceA)}</Text>
                      <Text style={[s.rowPrice, row.priceB == null && { color: colors.text.tertiary }]}>{row.priceB != null ? formatCOP(row.priceB) : '\u2014'}</Text>
                      <Text style={[s.rowDiff, { color: diffColor(row.pctDiff) }]}>{fmtDiff(row.pctDiff)}</Text>
                    </Pressable>
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
            <View style={s.overallRow}>
              <Text style={s.overallLabel}>{t.compare_overall_avg}</Text>
              <View style={{ width: 68 }} /><View style={{ width: 68 }} />
              <Text style={[s.rowDiff, { fontSize: fontSize.sm, fontWeight: '700', color: diffColor(comparison.overallAvg) }]}>{fmtDiff(comparison.overallAvg)}</Text>
            </View>
          )}
        </>
      )}

      {!loading && compId && (!comparison || comparison.matchCount === 0) && (
        <Text style={s.empty}>{t.compare_no_match}</Text>
      )}

      {/* Date popup */}
      <Modal visible={!!datePopup} transparent animationType="fade">
        <Pressable style={s.popupOverlay} onPress={() => setDatePopup(null)}>
          <View style={s.popupCard}>
            <Text style={s.popupText}>{t.compare_observed} {datePopup ? formatDateShort(datePopup) : ''}</Text>
          </View>
        </Pressable>
      </Modal>
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
  catHeader: { fontSize: fontSize.xs, fontWeight: '700', color: colors.primary, textTransform: 'uppercase', letterSpacing: 0.5, paddingVertical: spacing.xs, marginTop: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  subHeader: { fontSize: fontSize.xs, fontWeight: '600', color: colors.text.secondary, paddingVertical: spacing.xs, marginTop: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 3, paddingHorizontal: spacing.xs, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderLight + '20' },
  rowName: { fontSize: fontSize.sm, color: colors.text.primary },
  rowCtx: { fontSize: 10, color: colors.text.tertiary },
  rowPrice: { width: 68, textAlign: 'right', fontSize: fontSize.sm, fontFamily: 'monospace', color: colors.text.primary },
  rowDiff: { width: 52, textAlign: 'right', fontSize: fontSize.xs, fontWeight: '600', fontFamily: 'monospace' },
  subtotalRow: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: 3, paddingHorizontal: spacing.xs, backgroundColor: colors.background },
  subtotalLabel: { flex: 1, fontSize: fontSize.xs, fontWeight: '600', color: colors.text.secondary, fontStyle: 'italic' },
  overallRow: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingVertical: spacing.sm, paddingHorizontal: spacing.xs, borderTopWidth: 2, borderTopColor: colors.primary, marginTop: spacing.sm },
  overallLabel: { flex: 1, fontSize: fontSize.sm, fontWeight: '700', color: colors.text.primary },
  empty: { textAlign: 'center', padding: spacing.lg, fontSize: fontSize.sm, color: colors.text.tertiary },
  popupOverlay: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)' },
  popupCard: { backgroundColor: colors.dark, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: borderRadius.md },
  popupText: { color: colors.text.inverse, fontSize: fontSize.sm },
});
