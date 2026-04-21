import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Alert, TextInput, ScrollView } from 'react-native';
import MapView, { Geojson, Marker } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { getPricesByDepartment, getSupplyByDepartment, getDepartments, getMarketLocations, getMarketsWithProductData, getProductPresentationsForMap } from '../../src/api/map';
import { getProducts } from '../../src/api/products';
import { formatCOPCompact, formatKg } from '../../src/lib/format';
import { useTranslation } from '../../src/lib/useTranslation';
import { cachedCall } from '../../src/lib/cache';
import colombiaGeoJson from '../../src/data/colombia-departments.json';

const COLOMBIA_CENTER = { latitude: 4.5, longitude: -73.0 };
const COLOMBIA_DELTA = { latitudeDelta: 12, longitudeDelta: 12 };
const PRICE_COLORS = ['#2D7D46', '#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF9800', '#F44336'];
const SUPPLY_COLORS = ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1', '#1A237E'];

function interpolateColor(value: number, min: number, max: number, colorScale: string[]): string {
  if (max === min) return colorScale[3];
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const idx = Math.min(Math.floor(t * (colorScale.length - 1)), colorScale.length - 2);
  return colorScale[idx + 1];
}

type Mode = 'price' | 'supply';

export default function MapScreen() {
  const router = useRouter();
  const t = useTranslation();
  const [mode, setMode] = useState<Mode>('price');
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState<any[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [supplyData, setSupplyData] = useState<any[]>([]);
  const [allMarkets, setAllMarkets] = useState<any[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<{ id: string; name: string } | null>(null);
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productResults, setProductResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeMarketIds, setActiveMarketIds] = useState<Set<string> | null>(null);
  const [presentations, setPresentations] = useState<any[]>([]);
  const [selectedPresentation, setSelectedPresentation] = useState<any>(null);

  useEffect(() => {
    (async () => {
      try {
        // Base map layers — cached across visits so panning away and back is
        // instant on the second mount.
        const [depts, mkts] = await Promise.all([
          cachedCall(`map:departments`, () => getDepartments()),
          cachedCall(`map:marketLocations`, () => getMarketLocations()),
        ]);
        setDepartments(((depts as any[]) || []));
        setAllMarkets((((mkts as any[]) || [])).filter((m: any) => m.lat && m.lng));
      } catch (err) { console.error(err); }
    })();
  }, []);

  // Load presentations when product changes — deferred until a product is
  // actually picked, and cached per-product.
  useEffect(() => {
    if (selectedProduct && mode === 'price') {
      cachedCall(`map:presentations:${selectedProduct.id}:30`, () => getProductPresentationsForMap(selectedProduct.id, 30))
        .then(p => {
          const list = ((p as any[]) || []);
          setPresentations(list);
          setSelectedPresentation(list.length > 0 ? list[0] : null);
        })
        .catch(() => { setPresentations([]); setSelectedPresentation(null); });
    } else { setPresentations([]); setSelectedPresentation(null); }
  }, [selectedProduct, mode]);

  useEffect(() => { loadMapData(); }, [selectedProduct, mode, selectedPresentation]);

  async function loadMapData() {
    const pid = selectedProduct?.id;
    const presId = selectedPresentation?.presentation_id;
    const uId = selectedPresentation?.units_id;
    // No product → skip the cross-product aggregate. Averaging every product's
    // price (papa vs aguacate vs tomate) has no meaning, and summing every
    // product's kg scans 30 days of the whole table — the source of the 57014
    // timeouts on mount. Show the map neutral and prompt the user to pick one.
    if (!pid) {
      setPriceData([]); setSupplyData([]); setActiveMarketIds(null); setLoading(false);
      return;
    }
    // Product picked but presentation not yet resolved in price mode — hold
    // the current map during that brief gap instead of thrashing.
    if (mode === 'price' && !presId) return;
    setLoading(true);
    try {
      const keySuffix = `${pid}:${mode}:30:${presId ?? ''}:${uId ?? ''}`;
      const [prices, supply] = await Promise.all([
        mode === 'price'
          ? cachedCall(`map:prices:${keySuffix}`, () => getPricesByDepartment(pid, 30, presId, uId))
          : Promise.resolve([]),
        mode === 'supply'
          ? cachedCall(`map:supply:${keySuffix}`, () => getSupplyByDepartment(pid, 30))
          : Promise.resolve([]),
      ]);
      setPriceData(((prices as any[]) || []));
      setSupplyData(((supply as any[]) || []));
      const ids = await cachedCall(`map:activeMarkets:${keySuffix}`, () => getMarketsWithProductData(pid, mode, 30, presId, uId));
      setActiveMarketIds(new Set(ids as string[]));
    } catch (err) { console.error('loadMapData failed:', err); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (productSearch.length < 2) { setProductResults([]); return; }
      setSearchLoading(true);
      try {
        const data = await getProducts({ search: productSearch, limit: 20 });
        setProductResults(data || []);
      } catch (err) { console.error(err); }
      finally { setSearchLoading(false); }
    }, 300);
    return () => clearTimeout(timer);
  }, [productSearch]);

  const deptIdToDivipola = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of departments) { if (d.divipola_code) map.set(d.id, d.divipola_code); }
    return map;
  }, [departments]);

  const divipolaToValue = useMemo(() => {
    const map = new Map<string, number>();
    const dataset = mode === 'price' ? priceData : supplyData;
    const valueKey = mode === 'price' ? 'avg_price' : 'total_kg';
    for (const row of dataset) { const code = deptIdToDivipola.get(row.department_id); if (code) map.set(code, (row as any)[valueKey] || 0); }
    return map;
  }, [mode, priceData, supplyData, deptIdToDivipola]);

  const { minVal, maxVal } = useMemo(() => {
    const values = Array.from(divipolaToValue.values()).filter(v => v > 0);
    if (values.length === 0) return { minVal: 0, maxVal: 1 };
    return { minVal: Math.min(...values), maxVal: Math.max(...values) };
  }, [divipolaToValue]);

  const visibleMarkets = useMemo(() => {
    if (!activeMarketIds) return allMarkets;
    return allMarkets.filter(m => activeMarketIds.has(m.id));
  }, [allMarkets, activeMarketIds]);

  const colorScale = mode === 'price' ? PRICE_COLORS : SUPPLY_COLORS;

  const coloredGeoJson = useMemo(() => {
    const features = (colombiaGeoJson as any).features.map((feature: any) => {
      const code = feature.properties.DPTO;
      const value = divipolaToValue.get(code);
      const fillColor = value != null && value > 0 ? interpolateColor(value, minVal, maxVal, colorScale) : '#E0E0E0';
      return { ...feature, properties: { ...feature.properties, fill: fillColor, 'fill-opacity': '0.7', stroke: '#FFFFFF', 'stroke-width': 1.5 } };
    });
    return { type: 'FeatureCollection' as const, features };
  }, [divipolaToValue, minVal, maxVal, colorScale]);

  const handleDeptPress = useCallback((event: any) => {
    const feature = event?.feature || event?.nativeEvent?.feature;
    if (!feature?.properties) return;
    const code = feature.properties.DPTO;
    const name = feature.properties.NOMBRE_DPT;
    const value = divipolaToValue.get(code);
    const formattedValue = mode === 'price' ? formatCOPCompact(value ?? 0) : formatKg(value ?? 0);
    const label = mode === 'price' ? t.map_prices : t.map_supply;
    Alert.alert(name, `${label}: ${value ? formattedValue : t.map_no_data}`);
  }, [divipolaToValue, mode, t]);

  return (
    <View style={styles.container}>
      {!loading && (
        <MapView style={styles.map} initialRegion={{ ...COLOMBIA_CENTER, ...COLOMBIA_DELTA }} rotateEnabled={false} pitchEnabled={false}>
          <Geojson geojson={coloredGeoJson as any} tappable onPress={handleDeptPress} />
          {visibleMarkets.map(m => m.lat && m.lng ? (
            <Marker key={m.id} coordinate={{ latitude: m.lat, longitude: m.lng }} title={m.name} description={`${m.city}, ${m.department}`} pinColor={colors.primary} onCalloutPress={() => router.push(`/market/${m.id}`)} />
          ) : null)}
        </MapView>
      )}
      {loading && <View style={styles.loadingContainer}><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.loadingText}>{t.map_loading}</Text></View>}

      {/* Control panel */}
      <View style={styles.controlPanel}>
        {/* Product selector */}
        <Pressable onPress={() => setShowProductPicker(!showProductPicker)} style={[styles.productSelector, selectedProduct && styles.productSelectorActive]}>
          <Text style={[styles.productSelectorText, selectedProduct && { color: colors.primary }]} numberOfLines={1}>
            {selectedProduct ? selectedProduct.name : t.map_all_products}
          </Text>
          <Ionicons name="chevron-down" size={14} color={selectedProduct ? colors.primary : colors.text.secondary} />
        </Pressable>

        {showProductPicker && (
          <View style={styles.pickerDropdown}>
            <View style={styles.pickerSearch}>
              <Ionicons name="search" size={14} color={colors.text.tertiary} />
              <TextInput value={productSearch} onChangeText={setProductSearch} placeholder={t.map_search_product} placeholderTextColor={colors.text.tertiary} style={styles.pickerInput} autoFocus />
              {productSearch ? <Pressable onPress={() => setProductSearch('')}><Ionicons name="close-circle" size={14} color={colors.text.tertiary} /></Pressable> : null}
            </View>
            <ScrollView style={{ maxHeight: 200 }}>
              <Pressable onPress={() => { setSelectedProduct(null); setShowProductPicker(false); setProductSearch(''); }} style={[styles.pickerItem, !selectedProduct && styles.pickerItemActive]}>
                <Text style={[styles.pickerItemText, !selectedProduct && { color: colors.primary, fontWeight: '600' }]}>{t.map_all_products}</Text>
              </Pressable>
              {searchLoading && <ActivityIndicator size="small" color={colors.primary} style={{ padding: spacing.md }} />}
              {productResults.map((p: any) => (
                <Pressable key={p.id} onPress={() => { setSelectedProduct({ id: p.id, name: p.canonical_name }); setShowProductPicker(false); setProductSearch(''); }} style={[styles.pickerItem, selectedProduct?.id === p.id && styles.pickerItemActive]}>
                  <Text style={[styles.pickerItemText, selectedProduct?.id === p.id && { color: colors.primary, fontWeight: '600' }]}>{p.canonical_name}</Text>
                  <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{p.dim_subcategory?.dim_category?.canonical_name}</Text>
                </Pressable>
              ))}
              {productSearch.length >= 2 && !searchLoading && productResults.length === 0 && (
                <Text style={{ textAlign: 'center', padding: spacing.md, fontSize: fontSize.sm, color: colors.text.tertiary }}>{t.settings_no_results}</Text>
              )}
            </ScrollView>
          </View>
        )}

        {/* Presentation selector */}
        {selectedProduct && mode === 'price' && presentations.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingVertical: spacing.xs }}>
            {presentations.map((p: any) => (
              <Pressable key={`${p.presentation_id}|${p.units_id}`}
                onPress={() => setSelectedPresentation(p)}
                style={{
                  paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: borderRadius.full,
                  backgroundColor: selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.primary : colors.surface,
                  borderWidth: 1,
                  borderColor: selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.primary : colors.borderLight,
                }}>
                <Text style={{
                  fontSize: fontSize.xs,
                  color: selectedPresentation?.presentation_id === p.presentation_id && selectedPresentation?.units_id === p.units_id ? colors.text.inverse : colors.text.secondary,
                }}>{p.label}</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}

        {/* Mode toggle */}
        <View style={styles.modeSelector}>
          <Pressable style={[styles.modeButton, mode === 'price' && styles.modeButtonActive]} onPress={() => setMode('price')}>
            <Ionicons name="cash" size={16} color={mode === 'price' ? colors.text.inverse : colors.text.secondary} />
            <Text style={[styles.modeText, mode === 'price' && styles.modeTextActive]}>{t.map_prices}</Text>
          </Pressable>
          <Pressable style={[styles.modeButton, mode === 'supply' && styles.modeButtonActive]} onPress={() => setMode('supply')}>
            <Ionicons name="trending-up" size={16} color={mode === 'supply' ? colors.text.inverse : colors.text.secondary} />
            <Text style={[styles.modeText, mode === 'supply' && styles.modeTextActive]}>{t.map_supply}</Text>
          </Pressable>
        </View>
        <Text style={styles.controlLabel}>
          {selectedProduct ? `${selectedProduct.name} — ` : ''}{mode === 'price' ? t.map_price_legend : t.map_supply_legend}
        </Text>
      </View>

      {/* Legend */}
      {!loading && (
        <View style={styles.legend}>
          {selectedProduct ? (
            <View style={styles.legendRow}>
              <View style={[styles.legendBar, { backgroundColor: colorScale[0] }]} />
              <Text style={styles.legendText}>{mode === 'price' ? formatCOPCompact(minVal) : formatKg(minVal)}</Text>
              <View style={[styles.legendBar, { backgroundColor: colorScale[3] }]} />
              <View style={[styles.legendBar, { backgroundColor: colorScale[6] }]} />
              <Text style={styles.legendText}>{mode === 'price' ? formatCOPCompact(maxVal) : formatKg(maxVal)}</Text>
              <View style={[styles.legendBar, { backgroundColor: '#E0E0E0' }]} />
              <Text style={styles.legendText}>{t.map_no_data}</Text>
            </View>
          ) : (
            <Text style={{ fontSize: fontSize.sm, color: colors.text.secondary, textAlign: 'center' }}>{t.map_pick_product_prompt}</Text>
          )}
          <View style={{ flexDirection: 'row', justifyContent: 'center', gap: spacing.md, marginTop: 2 }}>
            <Text style={styles.legendSource}>{t.map_source}</Text>
            {selectedProduct && <Text style={{ fontSize: fontSize.xs, color: colors.primary, fontWeight: '600' }}>{visibleMarkets.length} mercados</Text>}
          </View>
          {selectedProduct && (
            <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic', textAlign: 'center', marginTop: spacing.xs }}>{t.map_no_highlight_note}</Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background, gap: spacing.md },
  loadingText: { fontSize: fontSize.md, color: colors.text.secondary },
  controlPanel: {
    position: 'absolute', top: spacing.md, left: spacing.md, right: spacing.md,
    backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md,
    shadowColor: colors.dark, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.15, shadowRadius: 8, elevation: 5, gap: spacing.sm,
  },
  productSelector: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: borderRadius.md,
    borderWidth: 1, borderColor: colors.borderLight,
  },
  productSelectorActive: { borderColor: colors.primary, backgroundColor: colors.primary + '08' },
  productSelectorText: { fontSize: fontSize.sm, fontWeight: '500', color: colors.text.secondary, flex: 1 },
  pickerDropdown: { backgroundColor: colors.surface, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.borderLight, overflow: 'hidden' },
  pickerSearch: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  pickerInput: { flex: 1, fontSize: fontSize.sm, color: colors.text.primary },
  pickerItem: { paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
  pickerItemActive: { backgroundColor: colors.primary + '08' },
  pickerItemText: { fontSize: fontSize.sm, color: colors.text.primary },
  modeSelector: { flexDirection: 'row', gap: spacing.sm },
  modeButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, paddingVertical: spacing.sm, borderRadius: borderRadius.md, backgroundColor: colors.borderLight },
  modeButtonActive: { backgroundColor: colors.primary },
  modeText: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.secondary },
  modeTextActive: { color: colors.text.inverse },
  controlLabel: { fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'center' },
  legend: {
    position: 'absolute', bottom: spacing.lg, left: spacing.md, right: spacing.md,
    backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md,
    shadowColor: colors.dark, shadowOffset: { width: 0, height: -2 }, shadowOpacity: 0.15, shadowRadius: 8, elevation: 5, gap: spacing.xs,
  },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, justifyContent: 'center', flexWrap: 'wrap' },
  legendBar: { width: 20, height: 12, borderRadius: 2 },
  legendText: { fontSize: fontSize.xs, color: colors.text.secondary, marginRight: spacing.xs },
  legendSource: { fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'center' },
});
