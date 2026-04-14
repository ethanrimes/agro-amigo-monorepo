import React, { useEffect, useState, useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Pressable, TextInput,
  ActivityIndicator, Alert, Platform,
} from 'react-native';
import { Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { colors, spacing, borderRadius, fontSize } from '../src/theme';
import { useSettings, MarketLevel, DefaultMarket } from '../src/context/SettingsContext';
import { getMarkets } from '../src/api/markets';
import { supabase } from '../src/lib/supabase';

const FONT_STEPS = [
  { label: 'Pequeño', scale: 0.85 },
  { label: 'Normal', scale: 1 },
  { label: 'Grande', scale: 1.15 },
  { label: 'Muy grande', scale: 1.3 },
];

const LEVEL_OPTIONS: { level: MarketLevel; label: string; icon: string }[] = [
  { level: 'nacional', label: 'Promedio nacional', icon: 'globe-outline' },
  { level: 'departamento', label: 'Departamento', icon: 'map-outline' },
  { level: 'ciudad', label: 'Ciudad', icon: 'business-outline' },
  { level: 'mercado', label: 'Mercado específico', icon: 'storefront-outline' },
];

interface PickerItem {
  id: string;
  name: string;
  subtitle?: string;
}

export default function SettingsScreen() {
  const { settings, updateDefaultMarket, updateFontSizeScale } = useSettings();
  const [selectedLevel, setSelectedLevel] = useState<MarketLevel>(settings.defaultMarket.level);
  const [pickerItems, setPickerItems] = useState<PickerItem[]>([]);
  const [pickerSearch, setPickerSearch] = useState('');
  const [loadingPicker, setLoadingPicker] = useState(false);
  const [locating, setLocating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>(settings.defaultMarket.id);
  const [selectedName, setSelectedName] = useState(settings.defaultMarket.name);

  // Load picker items when level changes
  useEffect(() => {
    if (selectedLevel === 'nacional') {
      setPickerItems([]);
      setSelectedId(undefined);
      setSelectedName('Promedio nacional');
      return;
    }
    loadPickerItems(selectedLevel);
  }, [selectedLevel]);

  async function loadPickerItems(level: MarketLevel) {
    setLoadingPicker(true);
    try {
      if (level === 'departamento') {
        const { data } = await supabase
          .from('dim_department')
          .select('id, canonical_name')
          .order('canonical_name');
        setPickerItems((data || []).map(d => ({ id: d.id, name: d.canonical_name })));
      } else if (level === 'ciudad') {
        const { data } = await supabase
          .from('dim_city')
          .select('id, canonical_name, dim_department(canonical_name)')
          .order('canonical_name');
        setPickerItems((data || []).map((c: any) => ({
          id: c.id,
          name: c.canonical_name,
          subtitle: c.dim_department?.canonical_name,
        })));
      } else if (level === 'mercado') {
        const data = await getMarkets();
        setPickerItems((data || []).map((m: any) => ({
          id: m.id,
          name: m.canonical_name,
          subtitle: `${(m as any).dim_city?.canonical_name || ''}, ${(m as any).dim_city?.dim_department?.canonical_name || ''}`,
        })));
      }
    } catch (err) {
      console.error('Error loading picker items:', err);
    } finally {
      setLoadingPicker(false);
    }
  }

  const filteredItems = useMemo(() => {
    if (!pickerSearch || pickerSearch.length < 2) return pickerItems;
    const q = pickerSearch.toLowerCase();
    return pickerItems.filter(
      i => i.name.toLowerCase().includes(q) || i.subtitle?.toLowerCase().includes(q)
    );
  }, [pickerItems, pickerSearch]);

  function handleSelectLevel(level: MarketLevel) {
    setSelectedLevel(level);
    setPickerSearch('');
    if (level === 'nacional') {
      const market: DefaultMarket = { level: 'nacional', name: 'Promedio nacional' };
      updateDefaultMarket(market);
      setSelectedId(undefined);
      setSelectedName(market.name);
    }
  }

  function handleSelectItem(item: PickerItem) {
    const market: DefaultMarket = {
      level: selectedLevel,
      id: item.id,
      name: item.name,
    };
    updateDefaultMarket(market);
    setSelectedId(item.id);
    setSelectedName(item.name);
    setPickerSearch('');
  }

  async function handleUseLocation() {
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Ubicación', 'Se necesita permiso de ubicación para encontrar el mercado más cercano.');
        return;
      }
      // Use a timeout to avoid hanging on emulators or devices without GPS
      const locPromise = Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 10000)
      );
      let loc;
      try {
        loc = await Promise.race([locPromise, timeoutPromise]);
      } catch {
        Alert.alert(
          'Ubicación no disponible',
          'No se pudo obtener tu ubicación. Puedes seleccionar tu mercado manualmente.',
        );
        return;
      }
      const { latitude, longitude } = loc.coords;

      // Query markets with coordinates from divipola_municipios
      const { data: markets } = await supabase
        .from('dim_market')
        .select(`
          id, canonical_name, city_id,
          dim_city(
            id, canonical_name,
            dim_department(id, canonical_name),
            divipola_municipios(latitud, longitud)
          )
        `);

      if (!markets || markets.length === 0) {
        Alert.alert('Sin resultados', 'No se encontraron mercados con coordenadas.');
        return;
      }

      // Find closest market
      let closest: any = null;
      let minDist = Infinity;
      for (const m of markets) {
        const muni = (m as any).dim_city?.divipola_municipios;
        if (!muni) continue;
        // divipola_municipios may be array or object
        const coords = Array.isArray(muni) ? muni[0] : muni;
        if (!coords?.latitud || !coords?.longitud) continue;
        const dist = Math.sqrt(
          Math.pow(latitude - coords.latitud, 2) +
          Math.pow(longitude - coords.longitud, 2)
        );
        if (dist < minDist) {
          minDist = dist;
          closest = m;
        }
      }

      if (closest) {
        const market: DefaultMarket = {
          level: 'mercado',
          id: closest.id,
          name: closest.canonical_name,
        };
        updateDefaultMarket(market);
        setSelectedLevel('mercado');
        setSelectedId(closest.id);
        setSelectedName(closest.canonical_name);
        const cityName = (closest as any).dim_city?.canonical_name || '';
        const deptName = (closest as any).dim_city?.dim_department?.canonical_name || '';
        Alert.alert(
          'Mercado encontrado',
          `${closest.canonical_name}\n${cityName}, ${deptName}`
        );
      } else {
        Alert.alert('Sin resultados', 'No se encontraron mercados con coordenadas disponibles.');
      }
    } catch (err) {
      console.error('Location error:', err);
      Alert.alert('Error', 'No se pudo obtener la ubicación.');
    } finally {
      setLocating(false);
    }
  }

  const currentFontStep = FONT_STEPS.findIndex(s => s.scale === settings.fontSizeScale);
  const fontStepIndex = currentFontStep >= 0 ? currentFontStep : 1;

  return (
    <>
      <Stack.Screen options={{ title: 'Configuración' }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>

        {/* Default Market Section */}
        <Text style={styles.sectionTitle}>Mercado predeterminado</Text>
        <Text style={styles.sectionDescription}>
          Define qué precios se muestran en la pantalla de inicio. Puedes elegir un promedio nacional, departamental, por ciudad, o un mercado específico.
        </Text>

        {/* Location button */}
        <Pressable
          style={styles.locationButton}
          onPress={handleUseLocation}
          disabled={locating}
        >
          {locating ? (
            <ActivityIndicator size="small" color={colors.text.inverse} />
          ) : (
            <Ionicons name="locate" size={18} color={colors.text.inverse} />
          )}
          <Text style={styles.locationButtonText}>
            {locating ? 'Localizando...' : 'Usar mi ubicación'}
          </Text>
        </Pressable>

        {/* Level selector */}
        <View style={styles.levelContainer}>
          {LEVEL_OPTIONS.map((opt) => (
            <Pressable
              key={opt.level}
              style={[styles.levelOption, selectedLevel === opt.level && styles.levelOptionActive]}
              onPress={() => handleSelectLevel(opt.level)}
            >
              <Ionicons
                name={opt.icon as any}
                size={20}
                color={selectedLevel === opt.level ? colors.text.inverse : colors.text.secondary}
              />
              <Text style={[
                styles.levelOptionText,
                selectedLevel === opt.level && styles.levelOptionTextActive,
              ]}>
                {opt.label}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Current selection */}
        <View style={styles.currentSelection}>
          <Ionicons name="checkmark-circle" size={18} color={colors.primary} />
          <Text style={styles.currentSelectionText}>
            {selectedLevel === 'nacional'
              ? 'Promedio nacional'
              : selectedName || 'Selecciona una opción'}
          </Text>
        </View>

        {/* Picker (for non-national levels) */}
        {selectedLevel !== 'nacional' && (
          <View style={styles.pickerContainer}>
            <View style={styles.pickerSearchRow}>
              <Ionicons name="search" size={16} color={colors.text.tertiary} />
              <TextInput
                style={styles.pickerSearchInput}
                value={pickerSearch}
                onChangeText={setPickerSearch}
                placeholder={`Buscar ${LEVEL_OPTIONS.find(o => o.level === selectedLevel)?.label.toLowerCase()}...`}
                placeholderTextColor={colors.text.tertiary}
              />
              {pickerSearch.length > 0 && (
                <Pressable onPress={() => setPickerSearch('')} hitSlop={8}>
                  <Ionicons name="close-circle" size={16} color={colors.text.tertiary} />
                </Pressable>
              )}
            </View>

            {loadingPicker ? (
              <ActivityIndicator size="small" color={colors.primary} style={{ padding: spacing.lg }} />
            ) : (
              <ScrollView style={styles.pickerList} nestedScrollEnabled>
                {filteredItems.slice(0, 50).map((item) => (
                  <Pressable
                    key={item.id}
                    style={[styles.pickerItem, selectedId === item.id && styles.pickerItemActive]}
                    onPress={() => handleSelectItem(item)}
                  >
                    <View style={styles.pickerItemContent}>
                      <Text style={[
                        styles.pickerItemName,
                        selectedId === item.id && styles.pickerItemNameActive,
                      ]} numberOfLines={1}>
                        {item.name}
                      </Text>
                      {item.subtitle && (
                        <Text style={styles.pickerItemSubtitle} numberOfLines={1}>
                          {item.subtitle}
                        </Text>
                      )}
                    </View>
                    {selectedId === item.id && (
                      <Ionicons name="checkmark" size={18} color={colors.primary} />
                    )}
                  </Pressable>
                ))}
                {filteredItems.length === 0 && !loadingPicker && (
                  <Text style={styles.pickerEmpty}>Sin resultados</Text>
                )}
                {filteredItems.length > 50 && (
                  <Text style={styles.pickerHint}>
                    Mostrando 50 de {filteredItems.length}. Usa la búsqueda para filtrar.
                  </Text>
                )}
              </ScrollView>
            )}
          </View>
        )}

        {/* Divider */}
        <View style={styles.divider} />

        {/* Font Size Section */}
        <Text style={styles.sectionTitle}>Tamaño de texto</Text>
        <Text style={styles.sectionDescription}>
          Ajusta el tamaño de la tipografía en toda la aplicación.
        </Text>

        <View style={styles.fontSizeRow}>
          {FONT_STEPS.map((step, i) => (
            <Pressable
              key={step.label}
              style={[styles.fontSizeOption, fontStepIndex === i && styles.fontSizeOptionActive]}
              onPress={() => updateFontSizeScale(step.scale)}
            >
              <Text style={[
                styles.fontSizePreview,
                { fontSize: 15 * step.scale },
                fontStepIndex === i && styles.fontSizePreviewActive,
              ]}>
                Aa
              </Text>
              <Text style={[
                styles.fontSizeLabel,
                fontStepIndex === i && styles.fontSizeLabelActive,
              ]}>
                {step.label}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Preview */}
        <View style={styles.previewCard}>
          <Text style={[styles.previewTitle, { fontSize: fontSize.lg * settings.fontSizeScale }]}>
            Vista previa
          </Text>
          <Text style={[styles.previewBody, { fontSize: fontSize.sm * settings.fontSizeScale }]}>
            Así se verá el texto en la aplicación con el tamaño seleccionado.
          </Text>
          <Text style={[styles.previewPrice, { fontSize: fontSize.md * settings.fontSizeScale }]}>
            $2.500/kg
          </Text>
        </View>

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
    padding: spacing.lg,
    paddingBottom: 40,
  },
  sectionTitle: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  sectionDescription: {
    fontSize: fontSize.sm,
    color: colors.text.secondary,
    lineHeight: 20,
    marginBottom: spacing.lg,
  },
  locationButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.accent.blue,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.md,
    marginBottom: spacing.lg,
  },
  locationButtonText: {
    color: colors.text.inverse,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  levelContainer: {
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  levelOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  levelOptionActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  levelOptionText: {
    fontSize: fontSize.md,
    fontWeight: '500',
    color: colors.text.primary,
  },
  levelOptionTextActive: {
    color: colors.text.inverse,
  },
  currentSelection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.primary + '10',
    borderRadius: borderRadius.sm,
    marginBottom: spacing.lg,
  },
  currentSelectionText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: colors.primary,
  },
  pickerContainer: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    overflow: 'hidden',
    marginBottom: spacing.lg,
  },
  pickerSearchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  pickerSearchInput: {
    flex: 1,
    fontSize: fontSize.md,
    color: colors.text.primary,
    paddingVertical: Platform.OS === 'ios' ? spacing.xs : 0,
  },
  pickerList: {
    maxHeight: 260,
  },
  pickerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  pickerItemActive: {
    backgroundColor: colors.primary + '08',
  },
  pickerItemContent: {
    flex: 1,
    gap: 2,
  },
  pickerItemName: {
    fontSize: fontSize.md,
    fontWeight: '500',
    color: colors.text.primary,
  },
  pickerItemNameActive: {
    color: colors.primary,
    fontWeight: '600',
  },
  pickerItemSubtitle: {
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
  },
  pickerEmpty: {
    textAlign: 'center',
    padding: spacing.lg,
    fontSize: fontSize.sm,
    color: colors.text.tertiary,
  },
  pickerHint: {
    textAlign: 'center',
    padding: spacing.md,
    fontSize: fontSize.xs,
    color: colors.text.tertiary,
    fontStyle: 'italic',
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginVertical: spacing.xl,
  },
  fontSizeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  fontSizeOption: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  fontSizeOptionActive: {
    backgroundColor: colors.primary + '10',
    borderColor: colors.primary,
  },
  fontSizePreview: {
    fontWeight: '700',
    color: colors.text.primary,
  },
  fontSizePreviewActive: {
    color: colors.primary,
  },
  fontSizeLabel: {
    fontSize: fontSize.xs,
    color: colors.text.secondary,
  },
  fontSizeLabelActive: {
    color: colors.primary,
    fontWeight: '600',
  },
  previewCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    gap: spacing.sm,
  },
  previewTitle: {
    fontWeight: '700',
    color: colors.text.primary,
  },
  previewBody: {
    color: colors.text.secondary,
    lineHeight: 20,
  },
  previewPrice: {
    fontWeight: '600',
    color: colors.primary,
    fontFamily: 'monospace',
  },
});
