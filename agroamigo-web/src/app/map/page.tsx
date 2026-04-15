'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { IoCash, IoTrendingUp } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatCOPCompact, formatKg } from '@agroamigo/shared';
import { getPricesByDepartment, getSupplyByDepartment, getDepartments, getMarketLocations } from '@agroamigo/shared/api/map';
import dynamic from 'next/dynamic';

const MapComponent = dynamic(() => import('./map-component'), { ssr: false, loading: () => <div className="loading-container"><div className="spinner" /><span>Cargando mapa...</span></div> });

const PRICE_COLORS = ['#2D7D46', '#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF9800', '#F44336'];
const SUPPLY_COLORS = ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1', '#1A237E'];

type Mode = 'price' | 'supply';

export default function MapPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('price');
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState<any[]>([]);
  const [priceData, setPriceData] = useState<any[]>([]);
  const [supplyData, setSupplyData] = useState<any[]>([]);
  const [markets, setMarkets] = useState<any[]>([]);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [depts, prices, supply, mkts] = await Promise.all([getDepartments(), getPricesByDepartment(undefined, 30), getSupplyByDepartment(undefined, 30), getMarketLocations()]);
      setDepartments(depts || []); setPriceData(prices || []); setSupplyData(supply || []);
      setMarkets((mkts || []).filter((m: any) => m.lat && m.lng));
    } catch (err) { console.error(err); } finally { setLoading(false); }
  }

  const deptIdToDivipola = useMemo(() => {
    const codeMap = new Map<string, string>();
    const nameMap = new Map<string, string>();
    for (const d of departments) { if (d.divipola_code) codeMap.set(d.id, d.divipola_code); nameMap.set(d.id, d.canonical_name); }
    return { codeMap, nameMap };
  }, [departments]);

  const divipolaToValue = useMemo(() => {
    const map = new Map<string, number>();
    const dataset = mode === 'price' ? priceData : supplyData;
    const valueKey = mode === 'price' ? 'avg_price' : 'total_kg';
    for (const row of dataset) { const code = deptIdToDivipola.codeMap.get(row.department_id); if (code) map.set(code, (row as any)[valueKey] || 0); }
    return map;
  }, [mode, priceData, supplyData, deptIdToDivipola]);

  const { minVal, maxVal } = useMemo(() => {
    const values = Array.from(divipolaToValue.values()).filter(v => v > 0);
    if (values.length === 0) return { minVal: 0, maxVal: 1 };
    return { minVal: Math.min(...values), maxVal: Math.max(...values) };
  }, [divipolaToValue]);

  if (loading) return <div className="loading-container"><div className="spinner" /><span>Cargando mapa...</span></div>;

  const colorScale = mode === 'price' ? PRICE_COLORS : SUPPLY_COLORS;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      <MapComponent mode={mode} divipolaToValue={divipolaToValue} minVal={minVal} maxVal={maxVal} colorScale={colorScale} markets={markets} onMarketClick={(id: string) => router.push(`/market/${id}`)} />

      {/* Controls */}
      <div style={{ position: 'absolute', top: spacing.md, left: spacing.md, right: spacing.md, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, boxShadow: `0 2px 8px ${colors.shadow}`, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
        <div style={{ display: 'flex', gap: spacing.sm }}>
          {([['price', 'Precios', IoCash], ['supply', 'Abastecimiento', IoTrendingUp]] as const).map(([m, label, Icon]) => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: spacing.xs,
              padding: `${spacing.sm}px`, borderRadius: borderRadius.md, border: 'none', cursor: 'pointer',
              backgroundColor: mode === m ? colors.primary : colors.borderLight,
              color: mode === m ? colors.text.inverse : colors.text.secondary, fontSize: fontSize.sm, fontWeight: 600,
            }}>
              <Icon size={16} />{label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'center' }}>
          {mode === 'price' ? 'Precio promedio por departamento (30 d\u00edas)' : 'Volumen de abastecimiento por departamento (30 d\u00edas)'}
        </div>
      </div>

      {/* Legend */}
      <div style={{ position: 'absolute', bottom: spacing.lg, left: spacing.md, right: spacing.md, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, boxShadow: `0 -2px 8px ${colors.shadow}`, zIndex: 1000 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.xs, justifyContent: 'center', flexWrap: 'wrap' }}>
          <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[0] }} />
          <span style={{ fontSize: fontSize.xs, color: colors.text.secondary, marginRight: spacing.xs }}>{mode === 'price' ? formatCOPCompact(minVal) : formatKg(minVal)}</span>
          <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[3] }} />
          <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: colorScale[6] }} />
          <span style={{ fontSize: fontSize.xs, color: colors.text.secondary, marginRight: spacing.xs }}>{mode === 'price' ? formatCOPCompact(maxVal) : formatKg(maxVal)}</span>
          <div style={{ width: 20, height: 12, borderRadius: 2, backgroundColor: '#E0E0E0' }} />
          <span style={{ fontSize: fontSize.xs, color: colors.text.secondary }}>Sin datos</span>
        </div>
        <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary, textAlign: 'center', marginTop: 2 }}>Fuente: SIPSA-DANE</div>
      </div>
    </div>
  );
}
