import React, { useEffect, useState, useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, Pressable, TextInput,
  ActivityIndicator, Alert, Platform,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { colors, spacing, borderRadius, fontSize } from '../src/theme';
import { useSettings, MarketLevel, DefaultMarket, Locale } from '../src/context/SettingsContext';
import { useTranslation } from '../src/lib/useTranslation';
import { useAuth } from '../src/context/AuthContext';
import { getMarkets } from '../src/api/markets';
import { supabase } from '../src/lib/supabase';

const FONT_STEPS = [
  { label: 'Pequeño', scale: 0.85 },
  { label: 'Normal', scale: 1 },
  { label: 'Grande', scale: 1.15 },
  { label: 'Muy grande', scale: 1.3 },
];

interface PickerItem {
  id: string;
  name: string;
  subtitle?: string;
  level: MarketLevel;
}

export default function SettingsScreen() {
  const router = useRouter();
  const { settings, updateDefaultMarket, updateFontSizeScale, updateChartSettings, updateLocale, updateCommentsEnabled } = useSettings();
  const t = useTranslation();
  const { userId, profile, signOut: authSignOut } = useAuth();
  const [pickerItems, setPickerItems] = useState<PickerItem[]>([]);
  const [pickerSearch, setPickerSearch] = useState('');
  const [loadingPicker, setLoadingPicker] = useState(false);
  const [locating, setLocating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>(settings.defaultMarket.id);
  const [selectedName, setSelectedName] = useState(settings.defaultMarket.name);

  const isNational = settings.defaultMarket.level === 'nacional';

  // One-shot load of every selectable location (depts + cities + markets)
  // into a single searchable list. Each item carries its own level so we
  // store the right shape when the user picks.
  useEffect(() => { loadPickerItems(); }, []);

  async function loadPickerItems() {
    setLoadingPicker(true);
    try {
      const [depts, cities, markets] = await Promise.all([
        supabase.from('dim_department').select('id, canonical_name').order('canonical_name'),
        supabase.from('dim_city').select('id, canonical_name, dim_department(canonical_name)').order('canonical_name'),
        getMarkets(),
      ]);
      const items: PickerItem[] = [];
      for (const d of (depts.data || [])) {
        items.push({ id: d.id, name: d.canonical_name, subtitle: 'Departamento', level: 'departamento' });
      }
      for (const c of (cities.data || []) as any[]) {
        items.push({
          id: c.id,
          name: c.canonical_name,
          subtitle: ['Ciudad', c.dim_department?.canonical_name].filter(Boolean).join(' · '),
          level: 'ciudad',
        });
      }
      for (const m of (markets || []) as any[]) {
        const where = [m.dim_city?.canonical_name, m.dim_city?.dim_department?.canonical_name].filter(Boolean).join(', ');
        items.push({
          id: m.id,
          name: m.canonical_name,
          subtitle: ['Mercado', where].filter(Boolean).join(' · '),
          level: 'mercado',
        });
      }
      setPickerItems(items);
    } catch (err) {
      console.error('Error loading picker items:', err);
    } finally {
      setLoadingPicker(false);
    }
  }

  const filteredItems = useMemo(() => {
    if (!pickerSearch || pickerSearch.length < 2) return [];
    const q = pickerSearch.toLowerCase();
    return pickerItems.filter(
      i => i.name.toLowerCase().includes(q) || i.subtitle?.toLowerCase().includes(q)
    );
  }, [pickerItems, pickerSearch]);

  function selectNational() {
    const market: DefaultMarket = { level: 'nacional', name: 'Promedio nacional' };
    updateDefaultMarket(market);
    setSelectedId(undefined);
    setSelectedName(market.name);
    setPickerSearch('');
  }

  function handleSelectItem(item: PickerItem) {
    const market: DefaultMarket = { level: item.level, id: item.id, name: item.name };
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
          Elige el promedio nacional o busca un departamento, ciudad o mercado específico.
        </Text>

        {/* Location button */}
        <Pressable style={styles.locationButton} onPress={handleUseLocation} disabled={locating}>
          {locating ? <ActivityIndicator size="small" color={colors.text.inverse} /> : <Ionicons name="locate" size={18} color={colors.text.inverse} />}
          <Text style={styles.locationButtonText}>{locating ? 'Localizando...' : 'Usar mi ubicación'}</Text>
        </Pressable>

        {/* Two primary tiles: national average + search */}
        <View style={styles.levelContainer}>
          <Pressable
            style={[styles.levelOption, isNational && styles.levelOptionActive]}
            onPress={selectNational}
          >
            <Ionicons name="globe-outline" size={20} color={isNational ? colors.text.inverse : colors.text.secondary} />
            <Text style={[styles.levelOptionText, isNational && styles.levelOptionTextActive]}>Promedio nacional</Text>
          </Pressable>
        </View>

        {/* Current selection */}
        <View style={styles.currentSelection}>
          <Ionicons name="checkmark-circle" size={18} color={colors.primary} />
          <Text style={styles.currentSelectionText}>{selectedName || 'Selecciona una opción'}</Text>
        </View>

        {/* Unified search: typing shows matching depts/cities/markets */}
        <View style={styles.pickerContainer}>
          <View style={styles.pickerSearchRow}>
            <Ionicons name="search" size={16} color={colors.text.tertiary} />
            <TextInput
              style={styles.pickerSearchInput}
              value={pickerSearch}
              onChangeText={setPickerSearch}
              placeholder="Buscar departamento, ciudad o mercado..."
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
          ) : pickerSearch.length >= 2 ? (
            <ScrollView style={styles.pickerList} nestedScrollEnabled keyboardShouldPersistTaps="handled">
              {filteredItems.slice(0, 50).map((item) => {
                const icon = item.level === 'departamento' ? 'map-outline'
                  : item.level === 'ciudad' ? 'business-outline' : 'storefront-outline';
                return (
                  <Pressable
                    key={`${item.level}-${item.id}`}
                    style={[styles.pickerItem, selectedId === item.id && styles.pickerItemActive]}
                    onPress={() => handleSelectItem(item)}
                  >
                    <Ionicons name={icon as any} size={16} color={colors.text.tertiary} style={{ marginRight: spacing.sm }} />
                    <View style={styles.pickerItemContent}>
                      <Text style={[styles.pickerItemName, selectedId === item.id && styles.pickerItemNameActive]}>
                        {item.name}
                      </Text>
                      {item.subtitle && <Text style={styles.pickerItemSubtitle}>{item.subtitle}</Text>}
                    </View>
                    {selectedId === item.id && <Ionicons name="checkmark" size={18} color={colors.primary} />}
                  </Pressable>
                );
              })}
              {filteredItems.length === 0 && <Text style={styles.pickerEmpty}>Sin resultados</Text>}
              {filteredItems.length > 50 && (
                <Text style={styles.pickerHint}>Mostrando 50 de {filteredItems.length}. Escribe más para filtrar.</Text>
              )}
            </ScrollView>
          ) : (
            <Text style={styles.pickerHint}>Escribe al menos 2 caracteres para buscar.</Text>
          )}
        </View>

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

        {/* Divider */}
        <View style={styles.divider} />

        {/* Language */}
        <Text style={styles.sectionTitle}>{t.settings_language}</Text>
        <Text style={styles.sectionDescription}>{t.settings_language_desc}</Text>
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg }}>
          {([['es', 'Español'], ['en', 'English']] as [Locale, string][]).map(([lang, label]) => (
            <Pressable key={lang} onPress={() => updateLocale(lang)}
              style={[styles.levelOption, { flex: 1, justifyContent: 'center' }, settings.locale === lang && styles.levelOptionActive]}>
              <Ionicons name="language-outline" size={18} color={settings.locale === lang ? colors.text.inverse : colors.text.secondary} />
              <Text style={[styles.levelOptionText, settings.locale === lang && styles.levelOptionTextActive]}>{label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Divider */}
        <View style={styles.divider} />

        {/* Chart Settings */}
        <Text style={styles.sectionTitle}>{t.settings_charts}</Text>
        <Text style={styles.sectionDescription}>{t.settings_charts_desc}</Text>
        <View style={{ gap: spacing.sm }}>
          {([
            { key: 'showAvgLine' as const, label: t.settings_chart_avg_line },
            { key: 'showTrendLine' as const, label: t.settings_chart_trend_line },
            { key: 'showMinMaxCallouts' as const, label: t.settings_chart_min_max_callouts },
            { key: 'showInteractiveCallout' as const, label: t.settings_chart_interactive },
          ]).map(opt => (
            <Pressable key={opt.key} onPress={() => updateChartSettings({ [opt.key]: !settings.chart[opt.key] })}
              style={[styles.toggleRow, settings.chart[opt.key] && styles.toggleRowActive]}>
              <Text style={styles.toggleLabel}>{opt.label}</Text>
              <View style={[styles.toggleTrack, settings.chart[opt.key] && styles.toggleTrackActive]}>
                <View style={[styles.toggleThumb, settings.chart[opt.key] && styles.toggleThumbActive]} />
              </View>
            </Pressable>
          ))}
        </View>

        {/* Divider */}
        <View style={styles.divider} />

        {/* Comments Toggle */}
        <Text style={styles.sectionTitle}>{t.settings_comments}</Text>
        <Text style={styles.sectionDescription}>{t.settings_comments_desc}</Text>
        <Pressable onPress={() => updateCommentsEnabled(!settings.commentsEnabled)}
          style={[styles.toggleRow, settings.commentsEnabled && styles.toggleRowActive]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
            <Ionicons name="chatbubble-outline" size={20} color={settings.commentsEnabled ? colors.primary : colors.text.secondary} />
            <Text style={styles.toggleLabel}>{t.settings_comments_toggle}</Text>
          </View>
          <View style={[styles.toggleTrack, settings.commentsEnabled && styles.toggleTrackActive]}>
            <View style={[styles.toggleThumb, settings.commentsEnabled && styles.toggleThumbActive]} />
          </View>
        </Pressable>

        {/* Divider */}
        <View style={styles.divider} />

        {/* Account */}
        <Text style={styles.sectionTitle}>{t.settings_account}</Text>
        <Text style={styles.sectionDescription}>{t.settings_account_desc}</Text>
        {userId && profile ? (
          <View style={styles.previewCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md }}>
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary + '15', alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="person-outline" size={20} color={colors.primary} />
              </View>
              <View>
                <Text style={{ fontSize: fontSize.md, fontWeight: '700', color: colors.text.primary }}>{profile.username}</Text>
                <Text style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.auth_member_since} {new Date(profile.created_at).toLocaleDateString()}</Text>
              </View>
            </View>
            <Pressable onPress={async () => { await authSignOut(); }}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.borderLight, borderRadius: borderRadius.md, paddingVertical: spacing.sm, alignItems: 'center' }}>
              <Text style={{ fontSize: fontSize.sm, color: colors.text.primary }}>{t.auth_sign_out}</Text>
            </Pressable>
          </View>
        ) : (
          <Pressable onPress={() => router.push('/auth')}
            style={[styles.locationButton, { backgroundColor: colors.primary }]}>
            <Ionicons name="person-outline" size={20} color={colors.text.inverse} />
            <Text style={styles.locationButtonText}>{t.settings_sign_in}</Text>
          </Pressable>
        )}

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
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    backgroundColor: colors.surface,
  },
  toggleRowActive: {
    borderColor: colors.primary,
    backgroundColor: colors.primary + '08',
  },
  toggleLabel: {
    fontSize: fontSize.md,
    fontWeight: '500',
    color: colors.text.primary,
  },
  toggleTrack: {
    width: 40,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.borderLight,
    padding: 2,
  },
  toggleTrackActive: {
    backgroundColor: colors.primary,
  },
  toggleThumb: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#fff',
  },
  toggleThumbActive: {
    transform: [{ translateX: 18 }],
  },
});
