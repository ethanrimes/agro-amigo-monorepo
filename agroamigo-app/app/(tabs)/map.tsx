import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Alert } from 'react-native';
import MapView, { Geojson, Marker, PROVIDER_GOOGLE } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { colors, spacing, borderRadius, fontSize } from '../../src/theme';
import { getPricesByDepartment, getSupplyByDepartment, getDepartments, getMarketLocations } from '../../src/api/map';
import { formatCOPCompact, formatKg } from '../../src/lib/format';
import colombiaGeoJson from '../../src/data/colombia-departments.json';

// Colombia center coordinates
const COLOMBIA_CENTER = { latitude: 4.5, longitude: -73.0 };
const COLOMBIA_DELTA = { latitudeDelta: 12, longitudeDelta: 12 };

// Color scales
const PRICE_COLORS = ['#2D7D46', '#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF9800', '#F44336'];
const SUPPLY_COLORS = ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1', '#1A237E'];

function interpolateColor(value: number, min: number, max: number, colorScale: string[]): string {
  if (max === min) return colorScale[3];
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const idx = Math.min(Math.floor(t * (colorScale.length - 1)), colorScale.length - 2);
  return colorScale[idx + 1]; // simple step, no lerp needed
}

type Mode = 'price' | 'supply';

interface MarketPoint {
  id: string;
  name: string;
  city: string;
  department: string;
  lat: number | null;
  lng: number | null;
}

export default function MapScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('price');
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState<any[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [supplyData, setSupplyData] = useState<any[]>([]);
  const [markets, setMarkets] = useState<MarketPoint[]>([]);
  const [selectedDept, setSelectedDept] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [depts, prices, supply, mkts] = await Promise.all([
        getDepartments(),
        getPricesByDepartment(undefined, 30),
        getSupplyByDepartment(undefined, 30),
        getMarketLocations(),
      ]);
      setDepartments(depts || []);
      setPriceData(prices || []);
      setSupplyData(supply || []);
      setMarkets((mkts || []).filter((m: any) => m.lat && m.lng));
    } catch (err) {
      console.error('Error loading map data:', err);
    } finally {
      setLoading(false);
    }
  }

  // Build dept_id -> divipola_code lookup
  const deptIdToDivipola = useMemo(() => {
    const map = new Map<string, string>();
    const nameMap = new Map<string, string>();
    for (const d of departments) {
      if (d.divipola_code) map.set(d.id, d.divipola_code);
      nameMap.set(d.id, d.canonical_name);
    }
    return { codeMap: map, nameMap };
  }, [departments]);

  // Build divipola_code -> value lookup for choropleth
  const divipolaToValue = useMemo(() => {
    const map = new Map<string, number>();
    const dataset = mode === 'price' ? priceData : supplyData;
    const valueKey = mode === 'price' ? 'avg_price' : 'total_kg';

    for (const row of dataset) {
      const code = deptIdToDivipola.codeMap.get(row.department_id);
      if (code) {
        map.set(code, (row as any)[valueKey] || 0);
      }
    }
    return map;
  }, [mode, priceData, supplyData, deptIdToDivipola]);

  // Compute min/max for color scale
  const { minVal, maxVal } = useMemo(() => {
    const values = Array.from(divipolaToValue.values()).filter(v => v > 0);
    if (values.length === 0) return { minVal: 0, maxVal: 1 };
    return { minVal: Math.min(...values), maxVal: Math.max(...values) };
  }, [divipolaToValue]);

  // Build colored GeoJSON — set per-feature "fill" properties
  const coloredGeoJson = useMemo(() => {
    const colorScale = mode === 'price' ? PRICE_COLORS : SUPPLY_COLORS;

    const features = (colombiaGeoJson as any).features.map((feature: any) => {
      const code = feature.properties.DPTO;
      const value = divipolaToValue.get(code);
      const fillColor = value != null && value > 0
        ? interpolateColor(value, minVal, maxVal, colorScale)
        : '#E0E0E0'; // no data = grey

      return {
        ...feature,
        properties: {
          ...feature.properties,
          fill: fillColor,
          'fill-opacity': '0.7',
          stroke: '#FFFFFF',
          'stroke-width': 1.5,
        },
      };
    });

    return { type: 'FeatureCollection' as const, features };
  }, [divipolaToValue, minVal, maxVal, mode]);

  const handleDeptPress = useCallback((event: any) => {
    const feature = event?.feature || event?.nativeEvent?.feature;
    if (!feature?.properties) return;

    const code = feature.properties.DPTO;
    const name = feature.properties.NOMBRE_DPT;
    const value = divipolaToValue.get(code);

    const formattedValue = mode === 'price'
      ? formatCOPCompact(value ?? 0)
      : formatKg(value ?? 0);

    const label = mode === 'price' ? 'Precio promedio' : 'Abastecimiento';

    setSelectedDept(code);
    Alert.alert(
      name,
      `${label}: ${value ? formattedValue : 'Sin datos'}`,
      [{ text: 'OK', onPress: () => setSelectedDept(null) }],
    );
  }, [divipolaToValue, mode]);

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Cargando mapa...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <MapView
        style={styles.map}
        initialRegion={{ ...COLOMBIA_CENTER, ...COLOMBIA_DELTA }}
        mapType="standard"
        rotateEnabled={false}
        pitchEnabled={false}
      >
        {/* Department choropleth polygons */}
        <Geojson
          geojson={coloredGeoJson as any}
          tappable
          onPress={handleDeptPress}
        />

        {/* Market markers */}
        {markets.map((m) => (
          m.lat && m.lng ? (
            <Marker
              key={m.id}
              coordinate={{ latitude: m.lat, longitude: m.lng }}
              title={m.name}
              description={`${m.city}, ${m.department}`}
              pinColor={colors.primary}
              onCalloutPress={() => router.push(`/market/${m.id}`)}
            />
          ) : null
        ))}
      </MapView>

      {/* Control panel overlay */}
      <View style={styles.controlPanel}>
        <View style={styles.modeSelector}>
          <Pressable
            style={[styles.modeButton, mode === 'price' && styles.modeButtonActive]}
            onPress={() => setMode('price')}
          >
            <Ionicons
              name="cash"
              size={16}
              color={mode === 'price' ? colors.text.inverse : colors.text.secondary}
            />
            <Text style={[styles.modeText, mode === 'price' && styles.modeTextActive]}>
              Precios
            </Text>
          </Pressable>
          <Pressable
            style={[styles.modeButton, mode === 'supply' && styles.modeButtonActive]}
            onPress={() => setMode('supply')}
          >
            <Ionicons
              name="trending-up"
              size={16}
              color={mode === 'supply' ? colors.text.inverse : colors.text.secondary}
            />
            <Text style={[styles.modeText, mode === 'supply' && styles.modeTextActive]}>
              Abastecimiento
            </Text>
          </Pressable>
        </View>
        <Text style={styles.controlLabel}>
          {mode === 'price'
            ? 'Precio promedio por departamento (30 días)'
            : 'Volumen de abastecimiento por departamento (30 días)'
          }
        </Text>
      </View>

      {/* Legend */}
      <View style={styles.legend}>
        <View style={styles.legendRow}>
          {mode === 'price' ? (
            <>
              <View style={[styles.legendBar, { backgroundColor: PRICE_COLORS[0] }]} />
              <Text style={styles.legendText}>{formatCOPCompact(minVal)}</Text>
              <View style={[styles.legendBar, { backgroundColor: PRICE_COLORS[3] }]} />
              <View style={[styles.legendBar, { backgroundColor: PRICE_COLORS[6] }]} />
              <Text style={styles.legendText}>{formatCOPCompact(maxVal)}</Text>
            </>
          ) : (
            <>
              <View style={[styles.legendBar, { backgroundColor: SUPPLY_COLORS[0] }]} />
              <Text style={styles.legendText}>{formatKg(minVal)}</Text>
              <View style={[styles.legendBar, { backgroundColor: SUPPLY_COLORS[3] }]} />
              <View style={[styles.legendBar, { backgroundColor: SUPPLY_COLORS[6] }]} />
              <Text style={styles.legendText}>{formatKg(maxVal)}</Text>
            </>
          )}
          <View style={[styles.legendBar, { backgroundColor: '#E0E0E0' }]} />
          <Text style={styles.legendText}>Sin datos</Text>
        </View>
        <Text style={styles.legendSource}>Fuente: SIPSA-DANE</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  map: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
    gap: spacing.md,
  },
  loadingText: {
    fontSize: fontSize.md,
    color: colors.text.secondary,
  },
  controlPanel: {
    position: 'absolute',
    top: spacing.md,
    left: spacing.md,
    right: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    shadowColor: colors.dark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
    gap: spacing.sm,
  },
  modeSelector: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  modeButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    backgroundColor: colors.borderLight,
  },
  modeButtonActive: {
    backgroundColor: colors.primary,
  },
  modeText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.text.secondary,
  },
  modeTextActive: {
    color: colors.text.inverse,
  },
  controlLabel: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textAlign: 'center',
  },
  legend: {
    position: 'absolute',
    bottom: spacing.lg,
    left: spacing.md,
    right: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    shadowColor: colors.dark,
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 5,
    gap: spacing.xs,
  },
  legendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    justifyContent: 'center',
    flexWrap: 'wrap',
  },
  legendBar: {
    width: 20,
    height: 12,
    borderRadius: 2,
  },
  legendText: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
    marginRight: spacing.xs,
  },
  legendSource: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    textAlign: 'center',
    marginTop: 2,
  },
});
