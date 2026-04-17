'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoLocate, IoSearch, IoCloseCircle, IoCheckmark, IoCheckmarkCircle, IoGlobeOutline, IoMapOutline, IoBusinessOutline, IoStorefrontOutline, IoLanguageOutline, IoPersonOutline, IoChatbubbleOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { getSupabaseClient } from '@agroamigo/shared';
import { getMarkets } from '@agroamigo/shared/api/markets';
import { useSettings, type MarketLevel, type DefaultMarket } from '@/context/SettingsContext';
import { useLanguage } from '@/context/LanguageContext';
import { useAuth } from '@/context/AuthContext';
import type { Locale } from '@/translations';

interface PickerItem { id: string; name: string; subtitle?: string; }

export default function SettingsPage() {
  const router = useRouter();
  const { settings, updateDefaultMarket, updateFontSizeScale, updateChartSettings, updateCommentsEnabled } = useSettings();
  const { t, locale, setLocale } = useLanguage();
  const { userId, profile, signOut } = useAuth();
  const [selectedLevel, setSelectedLevel] = useState<MarketLevel>(settings.defaultMarket.level);
  const [pickerItems, setPickerItems] = useState<PickerItem[]>([]);
  const [pickerSearch, setPickerSearch] = useState('');
  const [loadingPicker, setLoadingPicker] = useState(false);
  const [selectedId, setSelectedId] = useState<string | undefined>(settings.defaultMarket.id);
  const [selectedName, setSelectedName] = useState(settings.defaultMarket.name);

  const FONT_STEPS = [
    { label: t.settings_font_small, scale: 0.85 },
    { label: t.settings_font_normal, scale: 1 },
    { label: t.settings_font_large, scale: 1.15 },
    { label: t.settings_font_xlarge, scale: 1.3 },
  ];

  const LEVEL_OPTIONS: { level: MarketLevel; label: string; Icon: any }[] = [
    { level: 'nacional', label: t.settings_national_avg, Icon: IoGlobeOutline },
    { level: 'departamento', label: t.settings_department, Icon: IoMapOutline },
    { level: 'ciudad', label: t.settings_city, Icon: IoBusinessOutline },
    { level: 'mercado', label: t.settings_specific_market, Icon: IoStorefrontOutline },
  ];

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
    if (level === 'nacional') { updateDefaultMarket({ level: 'nacional', name: t.settings_national_avg }); setSelectedId(undefined); setSelectedName(t.settings_national_avg); }
  }

  function handleSelectItem(item: PickerItem) {
    const market: DefaultMarket = { level: selectedLevel, id: item.id, name: item.name };
    updateDefaultMarket(market); setSelectedId(item.id); setSelectedName(item.name); setPickerSearch('');
  }

  const fontStepIndex = FONT_STEPS.findIndex(s => s.scale === settings.fontSizeScale);
  const currentStep = fontStepIndex >= 0 ? fontStepIndex : 1;

  return (
    <div style={{ padding: spacing.lg, paddingBottom: 40 }}>
      {/* Language */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_language}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>{t.settings_language_desc}</p>

      <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.lg }}>
        {([['es', 'Espa\u00f1ol'], ['en', 'English']] as [Locale, string][]).map(([lang, label]) => (
          <button key={lang} onClick={() => setLocale(lang)} style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.sm,
            padding: `${spacing.md}px ${spacing.lg}px`,
            borderRadius: borderRadius.md, border: `1px solid ${locale === lang ? colors.primary : colors.borderLight}`,
            backgroundColor: locale === lang ? colors.primary : colors.surface, cursor: 'pointer',
            color: locale === lang ? colors.text.inverse : colors.text.primary, fontSize: fontSize.md, fontWeight: 500,
          }}>
            <IoLanguageOutline size={18} />
            {label}
          </button>
        ))}
      </div>

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Default Market */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_default_market}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>
        {t.settings_default_market_desc}
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
        <span style={{ fontSize: fontSize.sm, fontWeight: 600, color: colors.primary }}>{selectedLevel === 'nacional' ? t.settings_national_avg : selectedName || t.settings_select_option}</span>
      </div>

      {/* Picker */}
      {selectedLevel !== 'nacional' && (
        <div style={{ backgroundColor: colors.surface, borderRadius: borderRadius.md, border: `1px solid ${colors.borderLight}`, overflow: 'hidden', marginBottom: spacing.lg }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, padding: `${spacing.sm}px ${spacing.md}px`, borderBottom: `1px solid ${colors.borderLight}` }}>
            <IoSearch size={16} color={colors.text.tertiary} />
            <input type="text" value={pickerSearch} onChange={e => setPickerSearch(e.target.value)}
              placeholder={`${t.settings_search_placeholder} ${LEVEL_OPTIONS.find(o => o.level === selectedLevel)?.label.toLowerCase()}...`}
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
              {filteredItems.length === 0 && <p style={{ textAlign: 'center', padding: spacing.lg, fontSize: fontSize.sm, color: colors.text.tertiary }}>{t.settings_no_results}</p>}
              {filteredItems.length > 50 && <p style={{ textAlign: 'center', padding: spacing.md, fontSize: fontSize.xs, color: colors.text.tertiary, fontStyle: 'italic' }}>{t.settings_showing_n_of} {filteredItems.length}</p>}
            </div>
          )}
        </div>
      )}

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Font Size */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_font_size}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>{t.settings_font_size_desc}</p>

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
        <span style={{ fontWeight: 700, color: colors.text.primary, fontSize: fontSize.lg * settings.fontSizeScale }}>{t.settings_preview}</span>
        <span style={{ color: colors.text.secondary, lineHeight: '20px', fontSize: fontSize.sm * settings.fontSizeScale }}>{t.settings_preview_desc}</span>
        <span style={{ fontWeight: 600, color: colors.primary, fontFamily: 'monospace', fontSize: fontSize.md * settings.fontSizeScale }}>$2.500/kg</span>
      </div>

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Chart Settings */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_charts}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>{t.settings_charts_desc}</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
        {([
          { key: 'showAvgLine' as const, label: t.settings_chart_avg_line },
          { key: 'showTrendLine' as const, label: t.settings_chart_trend_line },
          { key: 'showMinMaxCallouts' as const, label: t.settings_chart_min_max_callouts },
          { key: 'showInteractiveCallout' as const, label: t.settings_chart_interactive },
        ]).map(opt => (
          <button key={opt.key} onClick={() => updateChartSettings({ [opt.key]: !settings.chart[opt.key] })} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: `${spacing.md}px ${spacing.lg}px`, borderRadius: borderRadius.md,
            border: `1px solid ${settings.chart[opt.key] ? colors.primary : colors.borderLight}`,
            backgroundColor: settings.chart[opt.key] ? colors.primary + '08' : colors.surface,
            cursor: 'pointer',
          }}>
            <span style={{ fontSize: fontSize.md, fontWeight: 500, color: colors.text.primary }}>{opt.label}</span>
            <div style={{
              width: 40, height: 22, borderRadius: 11, padding: 2,
              backgroundColor: settings.chart[opt.key] ? colors.primary : colors.borderLight,
              transition: 'background-color 0.2s',
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: 9, backgroundColor: '#fff',
                transform: settings.chart[opt.key] ? 'translateX(18px)' : 'translateX(0)',
                transition: 'transform 0.2s',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              }} />
            </div>
          </button>
        ))}
      </div>

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Comments Toggle */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_comments}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>{t.settings_comments_desc}</p>

      <button onClick={() => updateCommentsEnabled(!settings.commentsEnabled)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
        padding: `${spacing.md}px ${spacing.lg}px`, borderRadius: borderRadius.md,
        border: `1px solid ${settings.commentsEnabled ? colors.primary : colors.borderLight}`,
        backgroundColor: settings.commentsEnabled ? colors.primary + '08' : colors.surface,
        cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
          <IoChatbubbleOutline size={20} color={settings.commentsEnabled ? colors.primary : colors.text.secondary} />
          <span style={{ fontSize: fontSize.md, fontWeight: 500, color: colors.text.primary }}>{t.settings_comments_toggle}</span>
        </div>
        <div style={{
          width: 40, height: 22, borderRadius: 11, padding: 2,
          backgroundColor: settings.commentsEnabled ? colors.primary : colors.borderLight,
          transition: 'background-color 0.2s',
        }}>
          <div style={{
            width: 18, height: 18, borderRadius: 9, backgroundColor: '#fff',
            transform: settings.commentsEnabled ? 'translateX(18px)' : 'translateX(0)',
            transition: 'transform 0.2s',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
          }} />
        </div>
      </button>

      <hr style={{ border: 'none', borderTop: `1px solid ${colors.border}`, margin: `${spacing.xl}px 0` }} />

      {/* Account */}
      <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.xs }}>{t.settings_account}</h2>
      <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, lineHeight: '20px', marginBottom: spacing.lg }}>{t.settings_account_desc}</p>

      {userId && profile ? (
        <div style={{ backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.lg, border: `1px solid ${colors.borderLight}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md }}>
            <div style={{ width: 40, height: 40, borderRadius: borderRadius.full, backgroundColor: colors.primary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <IoPersonOutline size={20} color={colors.primary} />
            </div>
            <div>
              <div style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{profile.username}</div>
              <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.auth_member_since} {new Date(profile.created_at).toLocaleDateString()}</div>
            </div>
          </div>
          <button onClick={async () => { await signOut(); }} style={{
            width: '100%', padding: `${spacing.sm}px`, borderRadius: borderRadius.md,
            backgroundColor: colors.background, border: `1px solid ${colors.borderLight}`,
            color: colors.text.primary, fontSize: fontSize.sm, cursor: 'pointer',
          }}>
            {t.auth_sign_out}
          </button>
        </div>
      ) : (
        <button onClick={() => router.push('/auth')} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, width: '100%',
          padding: `${spacing.md}px`, borderRadius: borderRadius.md,
          backgroundColor: colors.primary, border: 'none',
          color: colors.text.inverse, fontSize: fontSize.md, fontWeight: 600, cursor: 'pointer',
        }}>
          <IoPersonOutline size={20} />
          {t.settings_sign_in}
        </button>
      )}
    </div>
  );
}
