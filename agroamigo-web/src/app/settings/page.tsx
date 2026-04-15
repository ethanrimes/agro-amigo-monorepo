'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { IoLocate, IoSearch, IoCloseCircle, IoCheckmark, IoCheckmarkCircle, IoGlobeOutline, IoMapOutline, IoBusinessOutline, IoStorefrontOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getSupabaseClient } from '@agroamigo/shared';
import { getMarkets } from '@agroamigo/shared/api/markets';
import { useSettings, type MarketLevel, type DefaultMarket } from '@/context/SettingsContext';

const FONT_STEPS = [
  { label: 'Peque\u00f1o', scale: 0.85 },
  { label: 'Normal', scale: 1 },
  { label: 'Grande', scale: 1.15 },
  { label: 'Muy grande', scale: 1.3 },
];

const LEVEL_OPTIONS: { level: MarketLevel; label: string; Icon: any }[] = [
  { level: 'nacional', label: 'Promedio nacional', Icon: IoGlobeOutline },
  { level: 'departamento', label: 'Departamento', Icon: IoMapOutline },
  { level: 'ciudad', label: 'Ciudad', Icon: IoBusinessOutline },
  { level: 'mercado', label: 'Mercado espec\u00edfico', Icon: IoStorefrontOutline },
];

interface PickerItem { id: string; name: string; subtitle?: string; }

export default function SettingsPage() {
  const { settings, updateDefaultMarket, updateFontSizeScale } = useSettings();
  const [selectedLevel, setSelectedLevel] = useState<MarketLevel>(settings.defaultMarket.level);
  const [pickerItems, setPickerItems] = useState<PickerItem[]>([]);
  const [pickerSearch, setPickerSearch] = useState('');
  const [loadingPicker, setLoadingPicker] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>(settings.defaultMarket.id);
  const [selectedName, setSelectedName] = useState(settings.defaultMarket.name);

  useEffect(() => {
    if (selectedLevel === 'nacional') { setPickerItems([]); return; }
    loadPickerItems(selectedLevel);
  }, [selectedLevel]);

  async function loadPickerItems(level: MarketLevel) {
    setLoadingPicker(true);
    const supabase = getSupabaseClient();
    try {
      if (level === 'departamento') {
        const { data } = await supabase.from('dim_department').select('id, canonical_name').order('canonical_name');
        setPickerItems((data || []).map(d => ({ id: d.id, name: d.canonical_name })));
      } else if (level === 'ciudad') {
        const { data } = await supabase.from('dim_city').select('id, canonical_name, dim_department(canonical_name)').order('canonical_name');
        setPickerItems((data || []).map((c: any) => ({ id: c.id, name: c.canonical_name, subtitle: c.dim_department?.canonical_name })));
      } else if (level === 'mercado') {
        const data = await getMarkets();
        setPickerItems((data || []).map((m: any) => ({ id: m.id, name: m.canonical_name, subtitle: `${m.dim_city?.canonical_name || ''}, ${m.dim_city?.dim_department?.canonical_name || ''}` })));
      }
    } catch (err) { console.error(err); } finally { setLoadingPicker(false); }
  }

  const filteredItems = useMemo(() => {
    if (!pickerSearch || pickerSearch.length < 2) return pickerItems;
    const q = pickerSearch.toLowerCase();
    return pickerItems.filter(i => i.name.toLowerCase().includes(q) || i.subtitle?.toLowerCase().includes(q));
  }, [pickerItems, pickerSearch]);

  function handleSelectLevel(level: MarketLevel) {
    setSelectedLevel(level); setPickerSearch('');
    if (level === 'nacional') { updateDefaultMarket({ level: 'nacional', name: 'Promedio nacional' }); setSelectedId(undefined); setSelectedName('Promedio nacional'); }
  }

  function handleSelectItem(item: PickerItem) {
    const market: DefaultMarket = { level: selectedLevel, id: item.id, name: item.name };
    updateDefaultMarket(market); setSelectedId(item.id); setSelectedName(item.name); setPickerSearch('');
  }

  const fontStepIndex = FONT_STEPS.findIndex(s => s.scale === settings.fontSizeScale);
  const currentStep = fontStepIndex >= 0 ? fontStepIndex : 1;

  return (
    <div style={{ padding: spacing.lg, paddingBottom: 40 }}>
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>Mercado predeterminado</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>
        Define qu&eacute; precios se muestran en la pantalla de inicio.
      </p>

      {/* Level selector */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm, marginBottom: spacing.lg }}>
        {LEVEL_OPTIONS.map(opt => (
          <button key={opt.level} onClick={() => handleSelectLevel(opt.level)} style={{
            display: 'flex', alignItems: 'center', gap: spacing.md, padding: `${spacing.md}px ${spacing.lg}px`,
            borderRadius: borderRadius.md, border: `1px solid ${selectedLevel === opt.level ? colors.primary : colors.borderLight}`,
            backgroundColor: selectedLevel === opt.level ? colors.primary : colors.surface, cursor: 'pointer',
            color: selectedLevel === opt.level ? colors.text.inverse : colors.text.primary, fontSize: fontSize.md, fontWeight: 500,
          }}>
            <opt.Icon size={20} />
            {opt.label}
          </button>
        ))}
      </div>

      {/* Current selection */}
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.sm}px ${spacing.md}px`, backgroundColor: colors.primary + '10', borderRadius: borderRadius.sm, marginBottom: spacing.lg }}>
        <IoCheckmarkCircle size={18} color={colors.primary} />
        <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary }}>{selectedLevel === 'nacional' ? 'Promedio nacional' : selectedName || 'Selecciona una opci\u00f3n'}</span>
      </div>

      {/* Picker */}
      {selectedLevel !== 'nacional' && (
        <div style={{ backgroundColor: colors.surface, borderRadius: borderRadius.md, border: `1px solid ${colors.borderLight}`, overflow: 'hidden', marginBottom: spacing.lg }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.sm}px ${spacing.md}px`, borderBottom: `1px solid ${colors.borderLight}` }}>
            <IoSearch size={16} color={colors.text.tertiary} />
            <input type="text" value={pickerSearch} onChange={e => setPickerSearch(e.target.value)}
              placeholder={`Buscar ${LEVEL_OPTIONS.find(o => o.level === selectedLevel)?.label.toLowerCase()}...`}
              style={{ flex: 1, fontSize: fontSize.md, color: colors.text.primary, border: 'none', outline: 'none', background: 'transparent', fontFamily: 'inherit' }} />
            {pickerSearch.length > 0 && <button onClick={() => setPickerSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><IoCloseCircle size={16} color={colors.text.tertiary} /></button>}
          </div>
          {loadingPicker ? <div style={{ padding: spacing.lg, textAlign: 'center' }}><div className="spinner" style={{ margin: '0 auto' }} /></div> : (
            <div style={{ maxHeight: 260, overflowY: 'auto' }}>
              {filteredItems.slice(0, 50).map(item => (
                <button key={item.id} onClick={() => handleSelectItem(item)} style={{
                  display: 'flex', alignItems: 'center', width: '100%', padding: `${spacing.md}px ${spacing.lg}px`, textAlign: 'left',
                  borderBottom: `1px solid ${colors.borderLight}`, background: selectedId === item.id ? colors.primary + '08' : 'none', border: 'none',
                  borderBlockEnd: `1px solid ${colors.borderLight}`, cursor: 'pointer',
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: fontSize.md, fontWeight: selectedId === item.id ? 600 : 500, color: selectedId === item.id ? colors.primary : colors.text.primary }}>{item.name}</div>
                    {item.subtitle && <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{item.subtitle}</div>}
                  </div>
                  {selectedId === item.id && <IoCheckmark size={18} color={colors.primary} />}
                </button>
              ))}
              {filteredItems.length === 0 && <p style={{ textAlign: 'center', padding: spacing.lg, fontSize: fontSize.sm, color: colors.text.tertiary }}>Sin resultados</p>}
              {filteredItems.length > 50 && <p style={{ textAlign: 'center', padding: spacing.md, fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic' }}>Mostrando 50 de {filteredItems.length}</p>}
            </div>
          )}
        </div>
      )}

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Font Size */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>Tama&ntilde;o de texto</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>Ajusta el tama&ntilde;o de la tipograf&iacute;a.</p>

      <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.lg }}>
        {FONT_STEPS.map((step, i) => (
          <button key={step.label} onClick={() => updateFontSizeScale(step.scale)} style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: spacing.xs,
            padding: `${spacing.md}px`, borderRadius: borderRadius.md, cursor: 'pointer',
            backgroundColor: currentStep === i ? colors.primary + '10' : colors.surface,
            border: `1px solid ${currentStep === i ? colors.primary : colors.borderLight}`,
          }}>
            <span style={{ fontWeight: 700, fontSize: 15 * step.scale, color: currentStep === i ? colors.primary : colors.text.primary }}>Aa</span>
            <span style={{ fontSize: fontSize.xs, color: currentStep === i ? colors.primary : colors.text.secondary, fontWeight: currentStep === i ? 600 : 400 }}>{step.label}</span>
          </button>
        ))}
      </div>

      {/* Preview */}
      <div style={{ backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.lg, border: `1px solid ${colors.borderLight}`, display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
        <span style={{ fontWeight: 700, color: colors.text.primary, fontSize: fontSize.lg * settings.fontSizeScale }}>Vista previa</span>
        <span style={{ color: colors.text.secondary, lineHeight: '20px', fontSize: fontSize.sm * settings.fontSizeScale }}>As&iacute; se ver&aacute; el texto con el tama&ntilde;o seleccionado.</span>
        <span style={{ fontWeight: 600, color: colors.primary, fontFamily: 'monospace', fontSize: fontSize.md * settings.fontSizeScale }}>$2.500/kg</span>
      </div>
    </div>
  );
}
